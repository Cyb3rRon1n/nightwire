"""Checks a shot must pass before money is spent on it. Problems block `submit`; warnings are shown only.
Numbers are defaults to tune (spec 2026-11-09): 2.5 spoken words per second with 1 s of air in each shot."""

import re
from dataclasses import dataclass, field
from pathlib import Path

from tools.shorts.approve import scene_fp
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
    for name in ("frame", "at_start", "at_end"):
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
    limit = fal.MODELS[model]["max_images"]
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


WEATHER = ("rain", "raining", "wet street", "snow", "fog", "daylight", "sunlight", "window")


def package(short, shot, prev, plates: dict, shot_dir, approvals: dict, design_dir) -> list[str]:
    p = []
    images = approvals.get("images", {})
    keep = lambda v: (v or {}).get("verdict") == "keep"  # noqa: E731
    if not shot.plate:
        p.append("no plate")
    elif shot.plate not in plates:
        p.append(f"plate {shot.plate} is not in {short.place}.plates.toml")
    elif not plate_path(design_dir, short.place, plates[shot.plate]).exists():
        p.append(f"plate {shot.plate} not rendered")
    elif not keep(images.get(plate_id(short.place, shot.plate))):
        p.append(f"plate {shot.plate} not approved")
    if short.scene is None:
        p.append("no [scene] bible")
    elif not keep(approvals.get("SCENE", {}).get(scene_fp(short))):
        p.append("scene bible not approved (or changed since)")
    if shot.mode == "i2v":
        def key(which):
            return keep(images.get(f"key--{short.slug}--{shot.id.lower()}--{which}"))
        start, end = shot_dir / "keyframe-start.png", shot_dir / "keyframe-end.png"
        if not start.exists():
            p.append("no approved start keyframe")
        elif not key("start"):
            p.append("start keyframe not approved")
        if shot.end_frame or set(shot.at_start) != set(shot.at_end):
            if not end.exists():
                p.append("needs an end keyframe (end_frame, or someone enters or leaves)")
            elif not key("end"):
                p.append("end keyframe not approved")
        if not shot.motion:
            p.append("missing motion")
    p += [f"{cid} has no [wardrobe] line" for cid in shot.frame if cid not in short.wardrobe]
    return p


def _banned(short) -> list[str]:
    if short.scene is None:
        return []
    allowed = short.scene.weather.lower()
    extra = [w for w in WEATHER if w not in allowed or f"no {w}" in allowed]
    return list(dict.fromkeys([w.lower() for w in short.scene.not_visible] + extra))


def bible_words(short, shot) -> tuple[list[str], list[str]]:
    texts = [("style", short.style), ("summary", shot.summary), ("action", shot.action), ("motion", shot.motion)]
    texts += [("beat", b.text) for b in shot.beats]
    texts += [(f"{a.who} acting", " ".join([a.goal, a.emotion, a.face, a.gaze, a.voice, a.end])) for a in shot.acting]
    problems, warnings = [], []
    for w in _banned(short):
        rx = re.compile(rf"\b{re.escape(w)}\b", re.IGNORECASE)
        problems += [f"'{w}' in {where} contradicts the scene bible" for where, t in texts if rx.search(t)]
        warnings += [f"'{w}' in a line of dialogue (fine if spoken, not shown)" for ln in shot.lines if rx.search(ln.text)]
    return problems, warnings


def run(short: Short, shot: Shot, prev: Shot | None, prompt: str, ref_list, model: str, spent: float,
        package_problems=(), bible=((), ())) -> Report:
    used, _ = fal.usable_refs(model, ref_list)
    return Report(problems=required(shot) + pace(shot) + one_action(shot) + continuity(prev, shot) + refs(model, used)
                  + budget(short, shot, model, spent) + list(package_problems) + list(bible[0]),
                  warnings=filter_words(prompt) + list(bible[1]))
