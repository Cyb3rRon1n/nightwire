"""python -m tools.shorts <command> <slug> ... — see docs/shorts-guide.md."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

from narrator import designs as _designs
from tools.shorts import SHORTS_DIR, approve, data_dir, guides, remote
from tools.shorts.backends import manual
from tools.shorts.greybox.scene import FPS, scene_json
from tools.shorts.model import load_short, scene_look, scene_mood, validate_short
from tools.shorts.prompt import build_prompt, expected_refs, ref_files
from tools.shorts.takes import BudgetError, Ledger, apply_verdicts, estimate

PICKS_API = "http://192.168.10.19:8080/designs/api/images"


class CliError(Exception):
    pass


def load_designs():
    return _designs.load_designs()  # all designs: the pilot cast includes "new:" ones


def _short(slug):
    if not (SHORTS_DIR / slug / "short.toml").exists():
        raise CliError(f"no short {slug!r} under {SHORTS_DIR}")
    return load_short(SHORTS_DIR / slug)


def _shot(short, shot_id):
    for s in short.shots:
        if s.id == shot_id:
            return s
    raise CliError(f"unknown shot {shot_id!r}; shots: {', '.join(s.id for s in short.shots)}")


def _work(slug):
    return data_dir() / slug


def cmd_check(a) -> int:
    problems = validate_short(_short(a.slug), load_designs())
    for p in problems:
        print(p)
    print("ok" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


def cmd_prompt(a) -> int:
    s = _short(a.slug)
    try:
        shot = _shot(s, a.shot)
        if s.model:
            from tools.shorts.backends import fal
            print(_preflight(s, shot, fal.shot_model(shot, s.model), load_designs())[1])  # the exact text submit would send
        else:
            print(build_prompt(s, shot, load_designs(), has_still=(_work(s.slug) / "shots" / shot.id / "still.png").exists()))
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1
    return 0


def cmd_greybox(a) -> int:
    s, work, designs = _short(a.slug), _work(a.slug), load_designs()
    palettes = {cid: designs[slug].palette[0] for cid, slug in s.cast.items() if a.tint and designs[slug].palette}
    work.mkdir(parents=True, exist_ok=True)
    for shot in s.shots:  # stale frames from a longer earlier run would be encoded too; only frames, never takes/costs/verdicts
        shutil.rmtree(work / "shots" / shot.id / "frames", ignore_errors=True)
    (work / "scene.json").write_text(json.dumps(scene_json(s, palettes), indent=1))
    if a.local:
        subprocess.run([os.path.expanduser(remote.BLENDER), "-b", "-P", str(remote.SCRIPT), "--", str(work / "scene.json"), str(work)], check=True)
    else:
        remote.run(work, a.slug)
    for shot in s.shots:
        sd = work / "shots" / shot.id
        subprocess.run(remote.encode(sd / "frames", sd / "greybox.mp4", FPS), check=True)
        print(sd / "greybox.mp4")
    return 0


def cmd_guides(a) -> int:
    """Guide renders come out of the same Blender job as the grey-box; this adds the lineart post-processing."""
    cmd_greybox(a)
    work = _work(a.slug)
    for shot in _short(a.slug).shots:
        g = work / "shots" / shot.id / "guide"
        for n in ("start", "end", "start-room", "end-room"):
            if (g / f"{n}.png").exists():
                print(guides.lineart(g / f"{n}.png", g / f"{n}-lineart.png"))
        for n in ("start", "end"):
            if (g / f"{n}-pose.json").exists():
                print(guides.pose_image(g.parent, n, _short(a.slug).cast))
        if (g / "regions.json").exists():
            (g / "regions.json").write_text(json.dumps(guides.visible_regions(g.parent), indent=1))
    return 0


def cmd_bundle(a) -> int:
    s, work = _short(a.slug), _work(a.slug)
    shot_dir = work / "shots" / a.shot
    shot = _shot(s, a.shot)
    out = manual.write_bundle(shot_dir, build_prompt(s, shot, load_designs(), has_still=(shot_dir / "still.png").exists()),
                              ref_files(s, data_dir().parent, shot_dir))
    print(out)
    return 0


def cmd_inbox(a) -> int:
    work = _work(a.slug)
    print(manual.import_inbox(work, a.shot, a.cost, a.model, Ledger(work / "costs.json")))
    return 0


def cmd_submit(a) -> int:
    import httpx

    from tools.shorts.backends import fal
    if a.model not in fal.MODELS:
        raise CliError(f"unknown model {a.model!r}; choose from: {', '.join(fal.MODELS)}")
    s, work, designs = _short(a.slug), _work(a.slug), load_designs()
    shot = _shot(s, a.shot)
    shot_dir = work / "shots" / a.shot
    api = _images_api()  # approvals.json is only refreshed by `verdicts`; a later Reject must stop this submit
    if api is None:
        print("can't reach the review store; nothing was spent", file=sys.stderr)
        return 1
    approve.apply_approvals(work, s.slug, api)
    report, prompt, refs = _preflight(s, shot, a.model, designs, api)
    for w in report.warnings:
        print(f"warning: {w}")
    if not report.ok:
        for p in report.problems:
            print(f"problem: {p}", file=sys.stderr)
        print("pre-flight failed: nothing was spent", file=sys.stderr)
        return 1
    refs, left_out = fal.usable_refs(a.model, refs)
    if left_out:
        print(f"{a.model} can't take every reference; left out: {', '.join(left_out)}")
    if a.override is not None and not a.override.strip():
        raise CliError('--override needs a reason, e.g. --override "owner approved in chat"; nothing was spent')
    override = (a.override or "").strip()
    seconds = int(round(a.seconds or shot.duration))  # fal bills whole seconds; the approval covers this length
    fp = approve.fingerprint(a.model, prompt, refs, seconds, approve.fp_extra(s, shot, data_dir().parent))
    ok = approve.approval(work, a.shot, fp)
    if not (ok and ok.get("verdict") == "keep"):
        if not override:
            print(f"{a.shot} is not approved for this exact prompt and references (fingerprint {fp}); "
                  "approve it on the production sheet, run `verdicts`, or pass --override \"<reason>\"", file=sys.stderr)
            return 1
        print(f"override: {override}")
    made = approve.attempts(work, a.shot, fp)
    if made >= 1 + s.retry_cap:
        print(f"{a.shot} already has {made} paid attempts for this approval (cap {1 + s.retry_cap}); raise retry_cap in short.toml",
              file=sys.stderr)
        return 1
    cost = estimate(a.model, seconds)
    print(f"{a.model} {seconds}s ≈ ${cost:.2f}; spent ${Ledger(work / 'costs.json').total():.2f} of ${s.budget_usd:.0f}")
    try:
        if not a.yes and input("submit? [y/N] ").strip().lower() != "y":
            return 1
    except EOFError:
        print("no answer on stdin; pass --yes to submit non-interactively", file=sys.stderr)
        return 1
    try:
        with httpx.Client() as client:
            tid = fal.run_take(work, a.shot, a.model, prompt, refs, seconds, s.budget_usd, key=fal.load_key(), client=client,
                               meta={"fp": fp}, note=f"override: {override}" if override else "")
    except (ValueError, BudgetError, RuntimeError) as e:
        print(e, file=sys.stderr)
        return 1
    except (httpx.HTTPError, TimeoutError) as e:  # after the POST the job is paid; the ledger row is written at POST
        print(f"network error talking to fal ({type(e).__name__}: {e}); the money may already be spent — "
              f"check {work / 'costs.json'} for this shot's row before retrying", file=sys.stderr)
        return 1
    print(shot_dir / "takes" / f"{tid}.mp4")
    return 0


def _prev(short, shot):
    i = [s.id for s in short.shots].index(shot.id)
    return short.shots[i - 1] if i else None


IMAGES_API = "http://192.168.10.19:8080/designs/api/images"


def _images_api() -> dict | None:
    """Review verdicts by image id; None when the store can't be reached (an empty store is {})."""
    try:
        with urllib.request.urlopen(IMAGES_API, timeout=10) as r:
            return json.load(r)
    except Exception:
        return None


def _images_or_warn() -> dict:
    """For read-only checks: an unreachable store reads as {} (everything unapproved, the safe side), with one warning."""
    api = _images_api()
    if api is None:
        print("review store unreachable: approvals read as missing", file=sys.stderr)
        return {}
    return api


def _approvals(work, images=None) -> dict:
    f = work / "approvals.json"
    return {**(json.loads(f.read_text()) if f.exists() else {}), "images": _images_or_warn() if images is None else images}


def _preflight(s, shot, model, designs, images=None, design_dir=None, plates_root=None):
    from tools.shorts import preflight
    dd = design_dir or data_dir().parent
    work = dd / "shorts" / s.slug
    shot_dir = work / "shots" / shot.id
    from tools.shorts.backends import fal
    from tools.shorts.plates import load_plates, plate_path
    plates = load_plates(s.place, plates_root)
    plate = plate_path(dd, s.place, plates[shot.plate]) if shot.plate in plates else None
    if shot.mode == "i2v":  # an i2v take sends only its keyframes
        expected = [(f"keyframe-{w}.png", shot_dir / f"keyframe-{w}.png") for w in ("start", "end")]
        expected = [(label, p) for label, p in expected if p.exists()]
    else:
        expected = expected_refs(s, dd, shot_dir, plate=plate)
    refs = [(label, p) for label, p in expected if p.exists()]  # what is sent and fingerprinted
    sent = [label for label, _ in fal.usable_refs(model, refs)[0]]
    prompt = build_prompt(s, shot, designs, has_still=(shot_dir / "still.png").exists(), sent=sent)
    approvals = _approvals(work, images)
    report = preflight.run(s, shot, _prev(s, shot), prompt, expected, model, Ledger(work / "costs.json").total(),
                           package_problems=preflight.package(s, shot, _prev(s, shot), plates, shot_dir, approvals, dd),
                           bible=preflight.bible_words(s, shot))
    if shot.mode == "i2v" and not fal.MODELS[model].get("i2v"):
        report.problems.append(f"mode i2v needs an -i2v model, got {model}; use {fal.shot_model(shot, model)}")
    elif shot.mode == "reference" and fal.MODELS[model].get("i2v"):
        report.problems.append(f"mode reference can't use an -i2v model, got {model}; use {fal.shot_model(shot, model)}")
    return report, prompt, refs


def cmd_ledger_sync(a) -> int:
    s, work = _short(a.slug), _work(a.slug)
    led = Ledger(work / "costs.json")
    if not 0 <= a.balance <= s.budget_usd:
        raise CliError(f"--balance ${a.balance:.2f} must be between 0 and the ${s.budget_usd:.2f} budget; nothing written")
    spent = led.total()
    new = round(s.budget_usd - a.balance, 2)
    print(f"adjusting ledger by ${new - spent:.2f} (spent ${spent:.2f} -> ${new:.2f}; ${a.balance:.2f} left)")
    led.adjust(a.balance, s.budget_usd, f"ledger-sync to fal balance ${a.balance:.2f}")
    return 0


def cmd_preflight(a) -> int:
    s, designs = _short(a.slug), load_designs()
    model = a.model or s.model
    if not model:
        raise CliError("no model: pass --model or set model in short.toml")
    from tools.shorts.backends import fal
    if model not in fal.MODELS:
        raise CliError(f"unknown model {model!r}; choose from: {', '.join(fal.MODELS)}")
    bad, images = 0, _images_or_warn()
    for shot in [_shot(s, a.shot)] if a.shot else s.shots:
        report = _preflight(s, shot, model if a.model else fal.shot_model(shot, model), designs, images)[0]
        print(f"{shot.id}: {'ok' if report.ok else 'FAIL'}")
        for p in report.problems:
            print(f"  problem: {p}")
        for w in report.warnings:
            print(f"  warning: {w}")
        bad += not report.ok
    return 1 if bad else 0


def cmd_sheet(a) -> int:
    from tools.shorts import sheet
    s, designs = _short(a.slug), load_designs()
    model = a.model or s.model
    if not model:
        raise CliError("no model: pass --model or set model in short.toml")
    from tools.shorts.backends import fal
    if model not in fal.MODELS:
        raise CliError(f"unknown model {model!r}; choose from: {', '.join(fal.MODELS)}")
    images = _images_or_warn()
    plans = {shot.id: _preflight(s, shot, fal.shot_model(shot, model), designs, images) for shot in s.shots}
    data = sheet.collect(s, designs, data_dir().parent, _work(a.slug), model, plans, _approvals(_work(a.slug), images))
    site = sheet.build(data, data_dir().parent, _work(a.slug), data_dir() / "_site")
    print(site)
    print(f"rsync -a {data_dir() / '_site'}/ 192.168.10.19:anvil-deploy/stack/dashboard/shorts/")
    return 0


def cmd_stills(a) -> int:
    from tools.design_scenes import gpu_busy
    from tools.shorts import stills
    s, designs, work = _short(a.slug), load_designs(), _work(a.slug)
    url = os.environ.get("COMFYUI_URL", "http://192.168.10.19:8188")
    if gpu_busy(url):
        print("ComfyUI is busy; wait for the current job to finish.", file=sys.stderr)
        return 1
    jobs, errors = [], []
    for shot in [_shot(s, a.shot)] if a.shot else s.shots:
        out = work / "shots" / shot.id / "still.png"
        if out.exists() and not a.redo:
            continue
        try:
            wf = stills.still_workflow(s, shot, designs, a.seed)
        except ValueError as e:  # no [frame] yet: skip this shot, render the rest
            errors.append(str(e))
            continue
        if len(shot.frame) > 2:
            print(f"note: {shot.id} has {len(shot.frame)} characters in frame; the still shows the first two "
                  f"({', '.join(stills.in_frame_order(shot)[:2])})")
        out.parent.mkdir(parents=True, exist_ok=True)
        jobs.append((out, wf))
    errors += stills.run(jobs, url)
    for e in errors:
        print(e, file=sys.stderr)
    return 1 if errors else 0


def cmd_plates(a) -> int:
    from tools.design_scenes import gpu_busy
    from tools.shorts import plates
    s, designs, work = _short(a.slug), load_designs(), _work(a.slug)
    design_dir = Path(os.environ.get("NIGHTWIRE_DESIGN_DIR", "design-data"))
    if a.choose:
        name, n = a.choose
        plate = plates.load_plates(s.place).get(name)
        if plate is None:
            raise CliError(f"no plate {name!r} for {s.place}")
        try:
            print(plates.choose(design_dir, s.place, plate, int(n)))
        except ValueError as e:
            raise CliError(str(e))
        return 0
    url = os.environ.get("COMFYUI_URL", "http://192.168.10.19:8188")
    jobs = plates.plan_jobs(s, work, design_dir, seeds=a.seeds, redo=a.redo)
    if jobs:
        print("Run `python -m tools.taste` first if you haven't this session.", file=sys.stderr)
        try:
            busy = gpu_busy(url)
        except OSError:  # URLError is an OSError
            raise CliError(f"ComfyUI is not reachable at {url}")
        if busy:
            print("ComfyUI is busy; wait for the current job to finish.", file=sys.stderr)
            return 1
    for out, plate, art, _ in jobs:
        if art is None:
            print(f"note: {plate.name} has no guide lineart (run guides first); rendering without it", file=sys.stderr)
    errors = plates.run(jobs, url, designs[s.place], scene_look(s),
                        s.scene.not_visible if s.scene else [], a.seed, scene_mood(s))
    for e in errors:
        print(e, file=sys.stderr)
    return 1 if errors else 0


def cmd_keyframes(a) -> int:
    from tools.design_scenes import gpu_busy
    from tools.shorts import keyframes
    s, designs, work = _short(a.slug), load_designs(), _work(a.slug)
    shot = _shot(s, a.shot) if a.shot else None
    if a.choose:
        if shot is None:
            raise CliError("--choose needs a shot")
        try:
            print(keyframes.choose(work, shot.id, a.choose[0], int(a.choose[1])))
        except ValueError as e:
            raise CliError(str(e))
        return 0
    url = os.environ.get("COMFYUI_URL", "http://192.168.10.19:8188")
    jobs, skipped = keyframes.plan_jobs(s, work, shot.id if shot else None, a.which, a.seeds, a.redo)
    for line in skipped:
        print(f"note: {line}", file=sys.stderr)
    if jobs:
        print("Run `python -m tools.taste` first if you haven't this session.", file=sys.stderr)
        try:
            busy = gpu_busy(url)
        except OSError:  # URLError is an OSError
            raise CliError(f"ComfyUI is not reachable at {url}")
        if busy:
            print("ComfyUI is busy; wait for the current job to finish.", file=sys.stderr)
            return 1
    errors = keyframes.run(jobs, url, s, designs, a.seed)
    for e in errors:
        print(e, file=sys.stderr)
    return 1 if errors else 0


def cmd_verdicts(a) -> int:
    with urllib.request.urlopen(PICKS_API, timeout=10) as r:
        api = json.load(r)
    print(f"{len(apply_verdicts(_work(a.slug), a.slug, api))} take verdict(s), "
          f"{len(approve.apply_approvals(_work(a.slug), a.slug, api))} plan verdict(s)")
    return 0


def cmd_idcheck(a) -> int:
    from tools.shorts import check
    s = _short(a.slug)
    report = check.run(_work(a.slug), a.shot, a.take, list(s.cast.values()), _shot(s, a.shot).duration)
    print(json.dumps(report, indent=1))
    return 0


def cmd_page(a) -> int:
    from tools.shorts.page import build
    titles, notes = {}, {}
    for folder in SHORTS_DIR.iterdir():
        if (folder / "short.toml").exists():
            s = load_short(folder)
            titles[s.slug] = (s.title, s.budget_usd)
            notes[s.slug] = {"logline": s.logline,
                             "cast": {cid: slug.split("-")[0].title() for cid, slug in s.cast.items()},
                             "shots": {sh.id: {"time": f"{sh.duration:g} s clip, {sh.start:g}–{sh.end:g} s of the short", "summary": sh.summary,
                                               "beats": [f"{b.t[0] - sh.start:g}–{b.t[1] - sh.start:g} s: {b.text}" for b in sh.beats]}
                                       for sh in s.shots}}
            for variant in data_dir().glob(f"{s.slug}-*"):  # e.g. the all-grey doll copy made for comparison
                titles[variant.name] = (f"{s.title} ({variant.name.removeprefix(s.slug + '-')} version)", s.budget_usd)
                notes[variant.name] = notes[s.slug]
    site = build(data_dir(), data_dir() / "_site", titles, notes)
    print(f"rsync -a --delete {site}/ 192.168.10.19:anvil-deploy/stack/dashboard/shorts/")
    return 0


def cmd_assemble(a) -> int:
    from tools.shorts.assemble import concat_cmd, kept_takes, needs_normalise, norm_cmd, probe, srt
    s, work = _short(a.slug), _work(a.slug)
    takes = kept_takes(s, work)
    if not takes:
        print("no kept takes yet — run verdicts first", file=sys.stderr)
        return 1
    (work / "draft.srt").write_text(srt(s, [t.parent.parent.name for t in takes]))
    infos = [probe(t) for t in takes]
    if needs_normalise(infos):
        norm = work / "norm"
        norm.mkdir(exist_ok=True)
        normed = []
        for t, info in zip(takes, infos):
            dst = norm / f"{t.parent.parent.name}-{t.name}"
            subprocess.run(norm_cmd(t, dst, info["audio"]), check=True)
            normed.append(dst)
        takes = normed
    # cwd=work + bare subtitle name keeps every path out of the ffmpeg filter graph
    subprocess.run(concat_cmd(takes, work / "draft.txt", a.music, Path("draft.srt"), work / "draft.mp4"), check=True, cwd=work)
    print(work / "draft.mp4")
    return 0


def cmd_status(a) -> int:
    s, work = _short(a.slug), _work(a.slug)
    for shot in s.shots:
        sd = work / "shots" / shot.id
        takes = sorted(p.stem for p in (sd / "takes").glob("t*.mp4"))
        verdicts = json.loads((sd / "verdicts.json").read_text()) if (sd / "verdicts.json").exists() else {}
        print(shot.id, f"{shot.duration}s", "takes:", ", ".join(f"{t}({verdicts.get(t, {}).get('verdict', '-')})" for t in takes) or "none")
    print(f"spent ${Ledger(work / 'costs.json').total():.2f} of ${s.budget_usd:.0f}")
    return 0


def cmd_boards(a) -> int:
    from tools.shorts import boards
    s = _short(a.slug)
    if a.shot:
        _shot(s, a.shot)
    try:
        for f in boards.build(s, data_dir().parent, _work(a.slug), shot=a.shot):
            print(f)
    except ValueError as e:
        raise CliError(str(e))
    return 0


def cmd_wall(a) -> int:
    from tools.shorts import film, wall
    try:
        f = film.load_film(a.slug, shorts_dir=SHORTS_DIR)
    except ValueError as e:
        raise CliError(str(e))
    print(wall.build(f, a.slug, SHORTS_DIR, data_dir().parent, data_dir() / "_site"))
    return 0


def cmd_animatic(a) -> int:
    from tools.shorts import animatic, film
    try:
        f = film.load_film(a.slug, shorts_dir=SHORTS_DIR)
        w, h = (int(v) for v in a.size.split("x"))
    except ValueError as e:
        raise CliError(str(e))
    print(animatic.build(f, a.slug, SHORTS_DIR, data_dir().parent, data_dir() / "_site", a.fps, (w, h)))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m tools.shorts")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("check", "status", "verdicts"):
        sub.add_parser(name).add_argument("slug")
    for name in ("prompt", "bundle"):
        q = sub.add_parser(name)
        q.add_argument("slug"); q.add_argument("shot")
    q = sub.add_parser("greybox"); q.add_argument("slug"); q.add_argument("--tint", action="store_true"); q.add_argument("--local", action="store_true")
    q = sub.add_parser("guides"); q.add_argument("slug"); q.set_defaults(tint=False, local=False)
    q = sub.add_parser("inbox"); q.add_argument("slug"); q.add_argument("shot"); q.add_argument("--cost", type=float, required=True); q.add_argument("--model", required=True)
    q = sub.add_parser("submit"); q.add_argument("slug"); q.add_argument("shot"); q.add_argument("--model", required=True)
    q.add_argument("--seconds", type=float); q.add_argument("--yes", action="store_true")
    q.add_argument("--override")
    q = sub.add_parser("ledger-sync"); q.add_argument("slug"); q.add_argument("--balance", type=float, required=True)
    q = sub.add_parser("preflight"); q.add_argument("slug"); q.add_argument("shot", nargs="?"); q.add_argument("--model")
    q = sub.add_parser("idcheck"); q.add_argument("slug"); q.add_argument("shot"); q.add_argument("take")
    q = sub.add_parser("sheet"); q.add_argument("slug"); q.add_argument("--model")
    q = sub.add_parser("stills"); q.add_argument("slug"); q.add_argument("shot", nargs="?")
    q.add_argument("--seed", type=int, default=703); q.add_argument("--redo", action="store_true")
    q = sub.add_parser("plates"); q.add_argument("slug"); q.add_argument("--seeds", type=int, default=3)
    q.add_argument("--seed", type=int, default=703); q.add_argument("--redo", action="store_true")
    q.add_argument("--choose", nargs=2, metavar=("NAME", "N"))
    q = sub.add_parser("keyframes"); q.add_argument("slug"); q.add_argument("shot", nargs="?")
    q.add_argument("--which", choices=("start", "end", "both"), default="both"); q.add_argument("--seeds", type=int, default=4)
    q.add_argument("--seed", type=int, default=703); q.add_argument("--redo", action="store_true")
    q.add_argument("--choose", nargs=2, metavar=("WHICH", "N"))
    sub.add_parser("page")
    q = sub.add_parser("boards"); q.add_argument("slug"); q.add_argument("shot", nargs="?")
    sub.add_parser("wall").add_argument("slug")
    q = sub.add_parser("animatic"); q.add_argument("slug"); q.add_argument("--fps", type=int, default=24); q.add_argument("--size", default="1216x832")
    q = sub.add_parser("assemble"); q.add_argument("slug"); q.add_argument("--music", type=Path)
    a = p.parse_args(argv)
    try:
        return globals()[f"cmd_{a.cmd.replace('-', '_')}"](a)
    except CliError as e:
        print(e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
