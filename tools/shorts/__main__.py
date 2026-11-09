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
from tools.shorts import SHORTS_DIR, approve, data_dir, remote
from tools.shorts.backends import manual
from tools.shorts.greybox.scene import FPS, scene_json
from tools.shorts.model import load_short, validate_short
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
    report, prompt, refs = _preflight(s, shot, a.model, designs)
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
    seconds = int(round(a.seconds or shot.duration))  # fal bills whole seconds; the approval covers this length
    fp = approve.fingerprint(a.model, prompt, refs, seconds)
    ok = approve.approval(work, a.shot, fp)
    if not (ok and ok.get("verdict") == "keep"):
        if not a.override:
            print(f"{a.shot} is not approved for this exact prompt and references (fingerprint {fp}); "
                  "approve it on the production sheet, run `verdicts`, or pass --override \"<reason>\"", file=sys.stderr)
            return 1
        print(f"override: {a.override}")
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
                               meta={"fp": fp}, note=f"override: {a.override}" if a.override else "")
    except (ValueError, BudgetError, RuntimeError) as e:
        print(e, file=sys.stderr)
        return 1
    print(shot_dir / "takes" / f"{tid}.mp4")
    return 0


def _prev(short, shot):
    i = [s.id for s in short.shots].index(shot.id)
    return short.shots[i - 1] if i else None


def _preflight(s, shot, model, designs):
    from tools.shorts import preflight
    work = _work(s.slug)
    shot_dir = work / "shots" / shot.id
    prompt = build_prompt(s, shot, designs, has_still=(shot_dir / "still.png").exists())
    expected = expected_refs(s, data_dir().parent, shot_dir)
    refs = [(label, p) for label, p in expected if p.exists()]  # what is sent and fingerprinted
    return preflight.run(s, shot, _prev(s, shot), prompt, expected, model, Ledger(work / "costs.json").total()), prompt, refs


def cmd_preflight(a) -> int:
    s, designs = _short(a.slug), load_designs()
    model = a.model or s.model
    if not model:
        raise CliError("no model: pass --model or set model in short.toml")
    from tools.shorts.backends import fal
    if model not in fal.MODELS:
        raise CliError(f"unknown model {model!r}; choose from: {', '.join(fal.MODELS)}")
    bad = 0
    for shot in [_shot(s, a.shot)] if a.shot else s.shots:
        report = _preflight(s, shot, model, designs)[0]
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
    plans = {shot.id: _preflight(s, shot, model, designs) for shot in s.shots}
    data = sheet.collect(s, designs, data_dir().parent, _work(a.slug), model, plans)
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
    jobs = []
    for shot in [_shot(s, a.shot)] if a.shot else s.shots:
        out = work / "shots" / shot.id / "still.png"
        if out.exists() and not a.redo:
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        jobs.append((out, stills.still_workflow(s, shot, designs, a.seed)))
    errors = stills.run(jobs, url)
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


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m tools.shorts")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("check", "status", "verdicts"):
        sub.add_parser(name).add_argument("slug")
    for name in ("prompt", "bundle"):
        q = sub.add_parser(name)
        q.add_argument("slug"); q.add_argument("shot")
    q = sub.add_parser("greybox"); q.add_argument("slug"); q.add_argument("--tint", action="store_true"); q.add_argument("--local", action="store_true")
    q = sub.add_parser("inbox"); q.add_argument("slug"); q.add_argument("shot"); q.add_argument("--cost", type=float, required=True); q.add_argument("--model", required=True)
    q = sub.add_parser("submit"); q.add_argument("slug"); q.add_argument("shot"); q.add_argument("--model", required=True)
    q.add_argument("--seconds", type=float); q.add_argument("--yes", action="store_true")
    q.add_argument("--override", default="")
    q = sub.add_parser("preflight"); q.add_argument("slug"); q.add_argument("shot", nargs="?"); q.add_argument("--model")
    q = sub.add_parser("idcheck"); q.add_argument("slug"); q.add_argument("shot"); q.add_argument("take")
    q = sub.add_parser("sheet"); q.add_argument("slug"); q.add_argument("--model")
    q = sub.add_parser("stills"); q.add_argument("slug"); q.add_argument("shot", nargs="?")
    q.add_argument("--seed", type=int, default=703); q.add_argument("--redo", action="store_true")
    sub.add_parser("page")
    q = sub.add_parser("assemble"); q.add_argument("slug"); q.add_argument("--music", type=Path)
    a = p.parse_args(argv)
    try:
        return globals()[f"cmd_{a.cmd}"](a)
    except CliError as e:
        print(e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
