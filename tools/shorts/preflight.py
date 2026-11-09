"""Checks a shot must pass before money is spent on it. Problems block `submit`; warnings are shown only.
Numbers are defaults to tune (spec 2026-11-09): 2.5 spoken words per second with 1 s of air in each shot."""

import re
from dataclasses import dataclass, field
from pathlib import Path

from tools.shorts.backends import fal
from tools.shorts.model import Shot, Short
from tools.shorts.takes import estimate

WORDS_PER_S = 2.5
AIR_S = 1.0
# Phrases that tripped ByteDance's content filter on the pilot (S02, 2026-11-08); a warning, not a block.
FILTER_WORDS = ("plug it in", "plug in", "open it", "stuck", "jack in")
REQUIRED = ("size", "angle", "move", "action")
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
        if a and b and a != b and not shot.cross_ok:
            out.append(f"{cid} swaps screen side ({prev.id} {a} -> {shot.id} {b}); set cross_ok = true if that is on purpose")
    return out


def refs(model: str, ref_list: list[tuple[str, Path]]) -> list[str]:
    out = [f"{label}: file missing ({p})" for label, p in ref_list if not p.exists()]
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


def run(short: Short, shot: Shot, prev: Shot | None, prompt: str, ref_list, model: str, spent: float) -> Report:
    used, _ = fal.usable_refs(model, ref_list)
    return Report(problems=required(shot) + pace(shot) + one_action(shot) + continuity(prev, shot) + refs(model, used)
                  + budget(short, shot, model, spent),
                  warnings=filter_words(prompt))
