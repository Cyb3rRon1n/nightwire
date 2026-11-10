"""Foyege's layered prompt: L1 grey-box role, L2 who is who, L3 look, L4 state, L5 timecodes.
Each fact lives in one layer; positions only in the floor plan / grey-box and in L5's camera terms."""

import re
from pathlib import Path

from tools.shorts.model import Short, Shot, scene_text, wardrobe_state, wardrobe_text

POSITION_WORDS = re.compile(
    r"\b(left|right|behind|beside|next to|in front of|across from|opposite|near|corner|at the (?:counter|door|bar|table|window))\b",
    re.IGNORECASE)
# colorguide.png repeats the turnaround, so a short sends the prop close-ups instead.
# portrait.png is the head close-up that holds hair and face. That makes 8 sheets + place + floor plan = 10 images,
# so models with a 9-image limit (Seedance 2.0) skip the floor plan; the grey-box video carries positions.
LOCKS = "; locks: "
CHARACTER_SHEETS = ("turnaround.png", "expressions.png", "props.png", "portrait.png")
SHEET_ROLES = {"turnaround.png": "full-body turnaround (outfit)", "expressions.png": "expression sheet",
               "props.png": "hands and props close-ups", "portrait.png": "face and hair close-up"}
OTHER_ROLES = {"place.png": "the location: this exact room, its counter, shelves, lanterns and light, in every shot",
               "start_frame.png": "the draft board: match this composition and staging; grey figures are placeholders for the characters",
               "end_frame.png": "the draft board for the closing frame: match this composition and staging at the end; grey figures are placeholders for the characters",
               "floorplan.png": "top-down floor plan, characters marked"}


def ref_roles(short: Short, designs: dict, sent: list[str]) -> str:
    """Seedance on fal names references @Image1.. and @Video1.. in the order sent; say what each one is for."""
    imgs, vids = [l for l in sent if not l.endswith(".mp4")], [l for l in sent if l.endswith(".mp4")]
    rows = []
    for i, label in enumerate(imgs, 1):
        cid, _, sheet = label.partition("_")
        role = (f"{cid} {designs[short.cast[cid]].name}, {SHEET_ROLES.get(sheet, sheet)}" if cid in short.cast
                else OTHER_ROLES.get(label, label))
        rows.append(f"@Image{i} is {role}")
    rows += [f"@Video{i} is the grey-box: camera path, positions and timing only" for i in range(1, len(vids) + 1)]
    return "Use the references as follows: " + "; ".join(rows) + "."


def _identity(design) -> str:
    marks = list(getattr(design, "identity", None) or [])
    return f" (always: {'; '.join(marks)})" if marks else ""


def _package_lines(short: Short, designs: dict) -> list[str]:
    out = [scene_text(short)] if short.scene else []
    if short.wardrobe:
        out.append("Wardrobe: " + "; ".join(f"{cid} {designs[short.cast[cid]].name}: {wardrobe_text(short, designs, cid)}"
                                              + _identity(designs[short.cast[cid]]) for cid in short.wardrobe) + ".")
    if short.blocking:
        out.append("Seating: " + "; ".join(short.blocking.values()) + ".")
    return [x for x in out if x]


def _positions(short: Short, shot: Shot) -> str:
    parts = [f"{c} {w}" for c, w in shot.frame.items()] + ([short.line_rule] if short.line_rule else [])
    return ("Screen positions: " + "; ".join(parts) + ".") if parts else ""


def i2v_prompt(short: Short, shot: Shot, designs: dict) -> str:
    """Image-to-video: the start (and end) keyframe already shows the room, people and outfits; the text says what
    moves, restates what must not change, and lists what must not appear."""
    head = [shot.motion or shot.action, *_package_lines(short, designs), _positions(short, shot)]
    if shot.move == "static":
        head.append("Keep the camera completely locked off.")
    l5 = layers(short, shot, designs)["L5"]
    return "\n\n".join([" ".join(x for x in head if x), short.style, l5])


def _t(a: float, b: float) -> str:
    return f"{a:.1f}-{b:.1f}s"


def layers(short: Short, shot: Shot, designs: dict, has_still: bool = False,
           sent: list[str] | None = None) -> dict[str, str]:
    board = bool(sent) and not any(l.endswith(".mp4") for l in sent)  # draft-board route: no grey-box video is sent
    grey = ("Replace each grey figure in the draft board with its character, keep no grey material. " if board else
            "The grey-box reference video provides camera path, character positions, silhouettes and timing. "
            "Replace each grey mannequin with its character, keep no grey material. ")
    l1 = (ref_roles(short, designs, sent) + " " if sent else "") + (grey +
          f"Camera: {shot.summary}." + ("" if sent and "floorplan.png" not in sent
                                        else f" Floor plan: C1..C{len(short.cast)} as marked."))
    plan = [f"{shot.size} {shot.angle}".strip(), f"camera {shot.move}" if shot.move else ""]
    if any(plan):
        l1 += " Shot: " + ", ".join(x for x in plan if x) + "."
    if shot.action:
        l1 += f" Main action: {shot.action}"
    if _positions(short, shot):
        l1 += " " + _positions(short, shot)
    if shot.move == "static":
        l1 += " Keep the camera completely locked off."
    if shot.mode == "reference":
        l1 += "".join(" " + x for x in _package_lines(short, designs))
    if has_still:
        l1 += " start_frame.png is the approved opening frame: match its composition, characters and light at 0 s."
    # The design's required tags name what must not drift (hair, eyes, signature clothes).
    # Locks (short.toml) are the owner's "never changes" notes; they may name hands ("chrome right hand"), so
    # position_problems checks L2 only up to LOCKS.
    def refs(cid):
        if not sent:
            return f"refs {cid}_*; {cid}_portrait is the face close-up"
        imgs = [l for l in sent if not l.endswith(".mp4")]
        return ", ".join(f"@Image{i}" for i, l in enumerate(imgs, 1) if l.startswith(cid + "_"))
    in_frame = {c: sl for c, sl in short.cast.items() if c in shot.frame} or short.cast
    l2 = "\n".join(f"{cid} = {designs[slug].name} ({refs(cid)}; always: "
                   f"{', '.join(designs[slug].required)})" + (f"{LOCKS}{short.locks[cid]}" if cid in short.locks else "")
                   for cid, slug in in_frame.items())
    l3 = short.style
    l4 = "\n".join(f"{cid}: {state}" for cid, state in shot.state.items())
    o = shot.start  # each shot is generated as its own clip from 0; TOML times are absolute
    rows: list[tuple[float, str]] = [(b.t[0], f"{_t(b.t[0] - o, b.t[1] - o)} {b.text}") for b in shot.beats]
    for a in shot.acting:
        parts = [f"goal: {a.goal}", f"emotion: {a.emotion}"]
        parts += [f"{k}: {v}" for k, v in (("trigger word", a.trigger), ("face", a.face), ("gaze/body", a.gaze),
                                          ("voice/breath", a.voice), ("ends", a.end)) if v]
        rows.append((a.t[0], f"{_t(a.t[0] - o, a.t[1] - o)} {a.who} acting - " + "; ".join(parts)))
    for ln in shot.lines:
        extra = []
        if ln.early_s:
            extra.append(f"enters {ln.early_s:.1f}s early")
        if ln.overlap_s:
            extra.append(f"overlaps {ln.overlap_s:.1f}s")
        if ln.disfluency:
            extra.append(f'{ln.disfluency} on "{ln.on_word}"' if ln.on_word else ln.disfluency)
        rows.append((ln.t, f'{ln.t - o:.1f}s {ln.who} says: "{ln.text}"' + (f" ({', '.join(extra)})" if extra else "")))
    rows.sort(key=lambda r: r[0])
    l5 = "\n".join(r for _, r in rows)
    l5 += "\nNo turn-by-turn reading; do not finish interrupted lines."
    return {"L1": l1, "L2": l2, "L3": l3, "L4": l4, "L5": l5}


def position_problems(L: dict[str, str]) -> list[str]:
    checked = {"L2": "\n".join(row.split(LOCKS)[0] for row in L["L2"].splitlines()), "L4": L["L4"]}
    return [f"{k}: position word {m.group(0)!r} (positions belong to the floor plan and L5)"
            for k in ("L2", "L4") for m in POSITION_WORDS.finditer(checked[k])]


def build_prompt(short: Short, shot: Shot, designs: dict, has_still: bool = False,
                 sent: list[str] | None = None) -> str:
    """sent: labels of the references this model will get, in order; names them @Image1.. in the prompt."""
    if shot.mode == "i2v":
        return i2v_prompt(short, shot, designs)
    L = layers(short, shot, designs, has_still, sent)
    problems = position_problems(L)
    if problems:
        raise ValueError("; ".join(problems))
    return "\n\n".join(L[k] for k in ("L1", "L2", "L3", "L4", "L5"))


def _sheet(design: Path, name: str) -> Path:
    """A design's shorts/ copy of a sheet (e.g. an outfit the video filter accepts) wins over the approved original."""
    alt = design / "shorts" / name
    return alt if alt.exists() else design / name


SET = ("turnaround", "portrait", "expressions", "props")


def state_folder(design_dir: Path, slug: str, state: str) -> Path:
    return design_dir / slug / "wardrobe" / state


def v2_set_exists(design_dir: Path, slug: str, state: str) -> bool:
    return all((state_folder(design_dir, slug, state) / f"{x}.png").exists() for x in SET)


def expected_refs(short: Short, design_dir: Path, shot_dir: Path, plate: Path | None = None, designs: dict | None = None,
                  shot: Shot | None = None, warnings: list[str] | None = None) -> list[tuple[str, Path]]:
    """Every reference a shot should send, whether or not the file exists yet (pre-flight reports the missing ones).
    With a shot: the cast in frame, their state's v2 sheets (v1 when the v2 set isn't made yet), the plate, and the draft boards."""
    out = []
    for cid, slug in short.cast.items():
        if shot is not None and shot.frame and cid not in shot.frame:
            continue
        state = wardrobe_state(short, designs, cid) if designs else None
        if state and v2_set_exists(design_dir, slug, state):
            out += [(f"{cid}_{f}", state_folder(design_dir, slug, state) / f) for f in CHARACTER_SHEETS]
            continue
        if state and warnings is not None:
            warnings.append(f"{cid} {state}: no v2 sheet set yet, sending the v1 sheets")
        out += [(f"{cid}_{f}", _sheet(design_dir / slug, f)) for f in CHARACTER_SHEETS]
    plate_file = plate or design_dir / short.place / "play.png"
    if shot is None:  # old route: a still replaces the place, plus floor plan and grey-box video
        still = shot_dir / "still.png"
        out.append(("start_frame.png", still) if still.exists() else ("place.png", plate_file))
        out.append(("floorplan.png", shot_dir.parent.parent / "floorplan.png"))
        out.append(("greybox.mp4", shot_dir / "greybox.mp4"))
        return out
    out.append(("place.png", plate_file))
    out.append(("start_frame.png", shot_dir / "board-start.png"))
    if (shot_dir / "board-end.png").exists():
        out.append(("end_frame.png", shot_dir / "board-end.png"))
    return out


def trim_refs(refs: list[tuple[str, Path]], limit: int, shot: Shot) -> list[tuple[str, Path]]:
    """Fit an image limit: drop the closing board, then expressions, then props the shot doesn't feature, then portraits."""
    refs = list(refs)
    featured = set(shot.props)
    tiers = (lambda l: l == "end_frame.png", lambda l: l.endswith("_expressions.png"),
             lambda l: l.endswith("_props.png") and l.partition("_")[0] not in featured, lambda l: l.endswith("_portrait.png"))
    for hit in tiers:
        for r in reversed([r for r in refs if hit(r[0])]):
            if sum(1 for l, _ in refs if l.endswith(".png")) <= limit:
                return refs
            refs.remove(r)
    return refs


def ref_files(short: Short, design_dir: Path, shot_dir: Path) -> list[tuple[str, Path]]:
    return [(label, p) for label, p in expected_refs(short, design_dir, shot_dir) if p.exists()]
