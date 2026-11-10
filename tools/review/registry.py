"""Everything the owner reviews in AI Lab, as one list. Producers (producers.py) each return Items for one kind of
work; the inbox page reads the list plus the shared verdict store (/designs/api/images). A new kind of work needs a
producer, never a new review page."""

import datetime as dt
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

STAGES = ("designs", "pre-production", "production", "finished")
_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,99}")  # same rule as the verdict store (tools/design_picks.py _IMAGE_ID)


def valid_id(s: str) -> bool:
    return bool(_ID.fullmatch(s))


@dataclass
class Item:
    id: str
    kind: str
    stage: str
    project: str
    title: str
    files: list[str]                                  # URLs of what is judged (image or video)
    compare: list[dict] = field(default_factory=list)  # [{"label": ..., "url": ...}] shown beside it
    context: str = ""                                  # prompt, bible, notes
    choices: tuple = ("keep", "fix", "reject")
    extra: dict = field(default_factory=dict)         # kind-specific data the page understands (e.g. pick rounds)

    def __post_init__(self):
        if not valid_id(self.id):
            raise ValueError(f"review id {self.id!r} must match {_ID.pattern}")
        if self.stage not in STAGES:
            raise ValueError(f"stage {self.stage!r} not in {STAGES}")


def web_copy(src: Path, site: Path, rel: str, max_side: int = 2048) -> str:
    """A JPEG no longer than max_side under site/media/rel; returns its URL. Skips work when the copy is newer."""
    from PIL import Image
    out = site / "media" / rel
    if not out.exists() or out.stat().st_mtime < src.stat().st_mtime:
        out.parent.mkdir(parents=True, exist_ok=True)
        im = Image.open(src).convert("RGB")
        im.thumbnail((max_side, max_side))
        im.save(out, "JPEG", quality=88)
    return f"/review/media/{rel}"


def build_items(producers, ctx: dict) -> tuple[list[Item], list[str]]:
    items, errors, seen = [], [], set()
    for p in producers:
        try:
            got = p(ctx)
        except Exception as e:  # one broken producer must not hide every other review
            errors.append(f"{p.__name__}: {e}")
            continue
        for it in got:
            if it.id in seen:
                errors.append(f"{p.__name__}: duplicate id {it.id}")
                continue
            seen.add(it.id)
            items.append(it)
    return items, errors


def write_items(items: list[Item], site: Path) -> Path:
    site.mkdir(parents=True, exist_ok=True)
    path = site / "items.json"
    rows = [{**asdict(i), "choices": list(i.choices)} for i in items]
    path.write_text(json.dumps({"built": dt.datetime.now().isoformat(timespec="seconds"), "items": rows}, indent=1))
    return path
