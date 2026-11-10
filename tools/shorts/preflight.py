"""Checks a shot must pass before money is spent on it. Problems block `submit`; warnings are shown only.
Numbers are defaults to tune (spec 2026-11-09): 2.5 spoken words per second with 1 s of air in each shot."""

import re
from dataclasses import dataclass, field
from pathlib import Path

from tools.shorts.approve import keyframe_id, scene_fp
from tools.shorts import lookbook
from tools.shorts.backends import fal
from tools.shorts.model import Shot, Short
from tools.shorts.plates import plate_id, plate_path
from tools.shorts.takes import estimate

WORDS_PER_S = 2.5
AIR_S = 1.0
# Phrases that tripped ByteDance's content filter on the pilot (S02, 2026-11-08); a warning, not a block.
FILTER_WORDS = ("plug it in", "plug in", "open it", "stuck", "jack in")
REQUIRED = ("size", "angle", "move", "action")
OPTIONAL_REFS = ("floorplan.png",)  # nice to have; 9-image models skip it anyway
SIDE = re.compile(r"screen[- ]?(left|right)", re.IGNORECASE)


@dataclass
class Report:
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def required(shot: Shot) -> list[str]:
    out = [f"missing {f}" for f in REQUIRED if not getattr(shot, f).strip()]
    environment = shot.mode == "i2v" and shot.plate and not shot.frame and not shot.at_start and not shot.at_end
    for name in () if environment else ("frame", "at_start", "at_end"):  # an empty-room shot has no cast to place
        if not getattr(shot, name):
            out.append(f"missing {name}")
    return out


def pace(shot: Shot) -> list[str]:
    words = sum(len(ln.text.split()) for ln in shot.lines)
    room = max(shot.duration - AIR_S, 0.5)
    rate = words / room
    return [f"dialogue {words} words in {room:g} s = {rate:.1f} words/s (limit {WORDS_PER_S})"] if rate > WORDS_PER_S else []


def one_action(shot: Shot) -> list[str]:
    out = []
    if len(re.findall(r"[.!?](?:\s|$)", shot.action.strip())) > 1:
        out.append("action must be one sentence (one main thing happens)")
    if re.search(r"\b(and|then)\b|,", shot.move):
        out.append(f"move {shot.move!r}: one camera move per shot")
    return out


def _side(text: str) -> str | None:
    m = SIDE.search(text)
    return m.group(1).lower() if m else None


def continuity(prev: Shot | None, shot: Shot) -> list[str]:
    if prev is None:
        return []
    out = []
    for cid in sorted(set(prev.props) & set(shot.props)):
        if prev.props[cid] != shot.props[cid] and cid not in shot.prop_change:
            out.append(f"{cid} props change from {prev.id} ({prev.props[cid]!r} -> {shot.props[cid]!r}); "
                       f"add {cid} to prop_change if that is on purpose")
    for cid in sorted(set(prev.frame) & set(shot.frame)):
        a, b = _side(prev.frame[cid]), _side(shot.frame[cid])
        if a and b and a != b and shot.cross_ok is not True:
            out.append(f"{cid} swaps screen side ({prev.id} {a} -> {shot.id} {b}); set cross_ok = true if that is on purpose")
    return out


def refs(model: str, ref_list: list[tuple[str, Path]]) -> list[str]:
    out = [f"{label}: file missing ({p})" for label, p in ref_list if not p.exists() and label not in OPTIONAL_REFS]
    ref_list = [(label, p) for label, p in ref_list if p.exists()]
    images = sum(1 for label, _ in ref_list if label.endswith(".png"))
    limit = fal.MODELS[model].get("max_images", 2)
    if images > limit:
        out.append(f"{images} images, {model} limit {limit}")
    return out


def filter_words(prompt: str) -> list[str]:
    low = prompt.lower()
    return [f"content filter risk: {w!r} (tripped ByteDance's filter on the pilot; prefer plain technical words)"
            for w in FILTER_WORDS if w in low]


def budget(short: Short, shot: Shot, model: str, spent: float) -> list[str]:
    cost = estimate(model, int(round(shot.duration)))
    left = short.budget_usd - spent
    return [f"${cost:.2f} would pass the budget (${left:.2f} left of ${short.budget_usd:.0f})"] if cost > left else []


WEATHER = ("rain", "wet street", "snow", "fog", "daylight", "sunlight", "window")


def character_shot(short, shot, shot_dir, images: dict, design_dir, keep, designs) -> list[str]:
    """A character shot needs its draft board approved and every stated cast member's v2 sheet set approved."""
    from tools.review.producers import SET_ORDER, sheet_set_id
    from tools.shorts.approve import board_id
    from tools.shorts.model import wardrobe_state
    p = []
    board = shot_dir / "board-start.png"
    if not board.exists():
        p.append("no draft board (board-start.png)")
    elif not keep(images.get(board_id(short.slug, shot.id, board))):
        p.append("draft board not approved")
    for cid in shot.frame:
        st = wardrobe_state(short, designs, cid) if cid in short.cast else None
        if not st:
            continue  # free-text wardrobe: the old sheets are sent, no set to approve
        folder = design_dir / short.cast[cid] / "wardrobe" / st
        if not all((folder / f"{x}.png").exists() for x in SET_ORDER):
            p.append(f"{cid} {st}: v2 sheet set missing")
        elif not keep(images.get(sheet_set_id(short.cast[cid], st, folder))):
            p.append(f"{cid} {st}: v2 sheet set not approved")
    return p


def package(short, shot, prev, plates: dict, shot_dir, approvals: dict, design_dir, designs: dict | None = None) -> list[str]:
    p = []
    images = approvals.get("images", {})
    keep = lambda v: (v or {}).get("verdict") == "keep"  # noqa: E731
    if not shot.plate:
        p.append("no plate")
    elif shot.plate not in plates:
        p.append(f"plate {shot.plate} is not in {short.place}.plates.toml")
    elif not (chosen := plate_path(design_dir, short.place, plates[shot.plate])).exists():
        p.append(f"plate {shot.plate} not rendered")
    elif not keep(images.get(plate_id(short.place, shot.plate, chosen))):
        p.append(f"plate {shot.plate} not approved")
    if short.scene is None:
        p.append("no [scene] bible")
    elif not keep(approvals.get("SCENE", {}).get(scene_fp(short))):
        p.append("scene bible not approved (or changed since)")
    environment = shot.mode == "i2v" and not shot.frame  # no cast in frame: the plate is the opening frame
    if shot.mode == "reference" and shot.frame:
        p += character_shot(short, shot, shot_dir, images, design_dir, keep, designs or {})
    if environment:
        if not shot.motion:
            p.append("missing motion")
    elif shot.mode == "i2v":
        def key(which):
            f = shot_dir / f"keyframe-{which}.png"
            return keep(images.get(keyframe_id(short.slug, shot.id, which, f)))
        start, end = shot_dir / "keyframe-start.png", shot_dir / "keyframe-end.png"
        if not start.exists():
            p.append("no approved start keyframe")
        elif not key("start"):
            p.append("start keyframe not approved")
        if end.exists():  # sent whenever present, so it must always be approved
            if not key("end"):
                p.append("end keyframe not approved")
        elif shot.end_frame or set(shot.at_start) != set(shot.at_end):
            p.append("needs an end keyframe (end_frame, or someone enters or leaves)")
        if not shot.motion:
            p.append("missing motion")
    p += [f"{cid} has no [wardrobe] line" for cid in shot.frame if cid not in short.wardrobe]
    return p


SUFFIX = "(?:s|es|ing|y)?"
NEGATORS = {"no", "not", "without", "never"}


def _rx(w: str) -> re.Pattern:
    return re.compile(rf"\b{re.escape(w)}{SUFFIX}\b", re.IGNORECASE)


def _allowed(w: str, weather: str) -> bool:
    """Allowed only if the weather text names it as a whole word and it is not negated: a negator within the 3 words
    before it, or within 6 when it sits in a list ("no rain or snow", "no rain, snow and fog")."""
    for m in _rx(w).finditer(weather):
        before = re.findall(r"[a-z']+|,", weather[:m.start()].lower())
        listed = bool(before) and before[-1] in ("or", "and", ",")
        near = [t for t in before if t != ","][-(6 if listed else 3):]
        if not NEGATORS & set(near):
            return True
    return False


def _banned(short) -> list[str]:
    if short.scene is None:
        return []
    extra = [w for w in WEATHER if not _allowed(w, short.scene.weather)]
    return list(dict.fromkeys([w.lower() for w in short.scene.not_visible] + extra))


def bible_words(short, shot) -> tuple[list[str], list[str]]:
    texts = [("style", short.style), ("summary", shot.summary), ("action", shot.action), ("motion", shot.motion)]
    texts += [(f"frame {cid}", v) for cid, v in shot.frame.items()] + [("line_rule", short.line_rule)]  # both reach the video prompt
    texts += [("beat", b.text) for b in shot.beats]
    texts += [(f"{a.who} acting", " ".join([a.goal, a.emotion, a.face, a.gaze, a.voice, a.end])) for a in shot.acting]
    problems, warnings = [], []
    for w in _banned(short):
        rx = _rx(w)
        problems += [f"'{w}' in {where} contradicts the scene bible" for where, t in texts if rx.search(t)]
        warnings += [f"'{w}' in a line of dialogue (fine if spoken, not shown)" for ln in shot.lines if rx.search(ln.text)]
    return problems, warnings


def run(short: Short, shot: Shot, prev: Shot | None, prompt: str, ref_list, model: str, spent: float,
        package_problems=(), bible=((), ())) -> Report:
    used, _ = fal.usable_refs(model, ref_list)
    return Report(problems=required(shot) + pace(shot) + one_action(shot) + continuity(prev, shot) + refs(model, used)
                  + budget(short, shot, model, spent) + list(package_problems) + list(bible[0]),
                  warnings=filter_words(prompt) + list(bible[1]) + lookbook.warnings(short, shot)
                  + ([] if shot.why.strip() else [f"missing why (one line: the cinematographic reason for this shot). Hint: {h}" if (h := lookbook.why_hint(shot)) else "missing why (one line: the cinematographic reason for this shot)"]))
