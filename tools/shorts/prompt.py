"""Foyege's layered prompt: L1 grey-box role, L2 who is who, L3 look, L4 state, L5 timecodes.
Each fact lives in one layer; positions only in the floor plan / grey-box and in L5's camera terms."""

import re
from pathlib import Path

from tools.shorts.model import Short, Shot

POSITION_WORDS = re.compile(
    r"\b(left|right|behind|beside|next to|in front of|across from|opposite|near|corner|at the (?:counter|door|bar|table|window))\b",
    re.IGNORECASE)
# colorguide.png repeats the turnaround, so a short sends the prop close-ups instead.
# portrait.png is the head close-up that holds hair and face. That makes 8 sheets + place + floor plan = 10 images,
# so models with a 9-image limit (Seedance 2.0) skip the floor plan; the grey-box video carries positions.
LOCKS = "; locks: "
CHARACTER_SHEETS = ("turnaround.png", "expressions.png", "props.png", "portrait.png")


def _t(a: float, b: float) -> str:
    return f"{a:.1f}-{b:.1f}s"


def layers(short: Short, shot: Shot, designs: dict, has_still: bool = False) -> dict[str, str]:
    l1 = ("The grey-box reference video provides camera path, character positions, silhouettes and timing. "
          "Replace each grey mannequin with its character, keep no grey material. "
          f"Camera: {shot.summary}. Floor plan: C1..C{len(short.cast)} as marked.")
    plan = [f"{shot.size} {shot.angle}".strip(), f"camera {shot.move}" if shot.move else ""]
    if any(plan):
        l1 += " Shot: " + ", ".join(x for x in plan if x) + "."
    if shot.action:
        l1 += f" Main action: {shot.action}"
    if has_still:
        l1 += " start_frame.png is the approved opening frame: match its composition, characters and light at 0 s."
    # The design's required tags name what must not drift (hair, eyes, signature clothes).
    # Locks (short.toml) are the owner's "never changes" notes; they may name hands ("chrome right hand"), so
    # position_problems checks L2 only up to LOCKS.
    l2 = "\n".join(f"{cid} = {designs[slug].name} (refs {cid}_*; {cid}_portrait is the face close-up; always: "
                   f"{', '.join(designs[slug].required)})" + (f"{LOCKS}{short.locks[cid]}" if cid in short.locks else "")
                   for cid, slug in short.cast.items())
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


def build_prompt(short: Short, shot: Shot, designs: dict, has_still: bool = False) -> str:
    L = layers(short, shot, designs, has_still)
    problems = position_problems(L)
    if problems:
        raise ValueError("; ".join(problems))
    return "\n\n".join(L[k] for k in ("L1", "L2", "L3", "L4", "L5"))


def expected_refs(short: Short, design_dir: Path, shot_dir: Path) -> list[tuple[str, Path]]:
    """Every reference a shot should send, whether or not the file exists yet (pre-flight reports the missing ones)."""
    out = []
    for cid, slug in short.cast.items():
        out += [(f"{cid}_{f}", design_dir / slug / f) for f in CHARACTER_SHEETS]
    still = shot_dir / "still.png"
    out.append(("start_frame.png", still) if still.exists() else ("place.png", design_dir / short.place / "play.png"))
    out.append(("floorplan.png", shot_dir.parent.parent / "floorplan.png"))
    out.append(("greybox.mp4", shot_dir / "greybox.mp4"))
    return out


def ref_files(short: Short, design_dir: Path, shot_dir: Path) -> list[tuple[str, Path]]:
    return [(label, p) for label, p in expected_refs(short, design_dir, shot_dir) if p.exists()]
