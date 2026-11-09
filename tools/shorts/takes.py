"""What a take costs, what has been spent, and where takes and verdicts are filed."""

import datetime as dt
import json
import re
import shutil
from pathlib import Path

# USD per generated second at 720p. From docs/superpowers/research/2026-11-08-ai-shorts-tools-and-hardware.md;
# Task 5 re-checks the fal ones against fal.ai before the first paid run. "manual" costs are typed in by hand.
RATES = {
    "seedance-2.5": 0.473,
    "seedance-2.0": 0.3034,
    "seedance-2.0-fast": 0.2419,
    "kling-3": 0.14,
    "veo-3.1-fast": 0.10,
}


class BudgetError(Exception):
    pass


def estimate(model: str, seconds: float) -> float:
    return round(RATES[model] * seconds, 4)


class Ledger:
    def __init__(self, path: Path):
        self.path = path

    def _rows(self) -> list[dict]:
        return json.loads(self.path.read_text()) if self.path.exists() else []

    def total(self) -> float:
        return round(sum(r["cost"] for r in self._rows()), 4)

    def add(self, shot: str, take: str, model: str, cost: float, note: str = "") -> None:
        row = {"shot": shot, "take": take, "model": model, "cost": cost,
               "at": dt.datetime.now().isoformat(timespec="seconds")}
        if note:
            row["note"] = note
        rows = self._rows() + [row]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(rows, indent=1))

    def check(self, budget: float, cost: float) -> None:
        if self.total() + cost > budget:
            raise BudgetError(f"spent ${self.total():.2f} + ${cost:.2f} would pass the ${budget:.0f} budget; "
                              "raise budget_usd in short.toml to continue")


def next_take_id(shot_dir: Path) -> str:
    nums = [int(p.stem[1:]) for p in (shot_dir / "takes").glob("t*.mp4") if p.stem[1:].isdigit()]
    return f"t{max(nums, default=0) + 1:03d}"


def file_take(shot_dir: Path, video: Path, meta: dict) -> str:
    tid = next_take_id(shot_dir)
    (shot_dir / "takes").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(video, shot_dir / "takes" / f"{tid}.mp4")
    meta = {**meta, "id": tid, "at": dt.datetime.now().isoformat(timespec="seconds")}
    (shot_dir / "takes" / f"{tid}.json").write_text(json.dumps(meta, indent=1))
    return tid


SLUG = re.compile(r"[a-z0-9][a-z0-9-]*")


def take_image_id(slug: str, shot: str, take: str) -> str:
    if "--" in slug or not SLUG.fullmatch(slug):
        raise ValueError(f"slug {slug!r} must match [a-z0-9][a-z0-9-]* and must not contain '--'")
    return f"short--{slug}--{shot.lower()}--{take}"


def apply_verdicts(short_dir: Path, slug: str, api: dict) -> dict[str, dict]:
    prefix = f"short--{slug}--"
    mine: dict[str, dict] = {}
    per_shot: dict[str, dict] = {}
    for key, v in api.items():
        if not key.startswith(prefix):
            continue
        parts = key[len(prefix):].split("--")
        if len(parts) != 2:
            continue  # malformed id from the shared picks API; skip it, do not fail the whole sync
        mine[key] = v
        shot, take = parts
        shot = shot.upper()
        per_shot.setdefault(shot, {})[take] = {k: v[k] for k in ("verdict", "note") if k in v}
    for shot, verdicts in per_shot.items():
        (short_dir / "shots" / shot).mkdir(parents=True, exist_ok=True)
        (short_dir / "shots" / shot / "verdicts.json").write_text(json.dumps(verdicts, indent=1, sort_keys=True))
    return mine
