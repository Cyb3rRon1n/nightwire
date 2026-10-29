"""Phase 19b design records: one small TOML per character or location in
narrator/worlds/designs/, the full-size sheets live outside git.
See docs/superpowers/specs/2026-10-28-design-studio-19b-design.md."""

import functools
import re
import tomllib
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

DESIGNS_DIR = Path(__file__).parent / "worlds" / "designs"
KINDS = ("character", "location")
STATUSES = ("draft", "candidates", "approved")
PRESENTATIONS = ("feminine", "masculine", "androgynous")
_ORDER = ("name", "kind", "source", "presentation", "tags", "negative", "alt_tags", "props",
          "status", "seed", "palette", "notes")


def slugify(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    ascii_name = ascii_name.lower().replace("'", "")
    return re.sub(r"[^a-z0-9]+", "-", ascii_name).strip("-")


@dataclass
class Design:
    name: str
    kind: str
    source: str
    tags: str
    presentation: str | None = None
    negative: str = ""
    alt_tags: str = ""
    props: list[str] = field(default_factory=list)
    status: str = "draft"
    seed: int = 0
    palette: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def slug(self) -> str:
        return slugify(self.name)


def validate(d: Design) -> None:
    if not d.name.strip():
        raise ValueError("design name is required")
    if d.kind not in KINDS:
        raise ValueError(f"unknown kind {d.kind!r}")
    if d.status not in STATUSES:
        raise ValueError(f"unknown status {d.status!r}")
    if not d.tags.strip():
        raise ValueError(f"{d.name}: tags are required")
    if d.kind == "character":
        if d.presentation is not None and d.presentation not in PRESENTATIONS:
            raise ValueError(f"{d.name}: presentation must be one of {PRESENTATIONS}")
        if d.alt_tags or d.props:
            raise ValueError(f"{d.name}: alt_tags and props are for locations only")
    elif d.presentation is not None:
        raise ValueError(f"{d.name}: presentation is for characters only")
    if d.status == "approved" and not d.seed:
        raise ValueError(f"{d.name}: an approved design needs a seed")


def _toml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def save_design(d: Design, path: Path) -> None:
    validate(d)
    lines = []
    for key in _ORDER:
        value = getattr(d, key)
        if key == "presentation" and (d.kind != "character" or value is None):
            continue
        if key in ("alt_tags", "props") and d.kind != "location":
            continue
        lines.append(f"{key} = {_toml_value(value)}")
    path.write_text("\n".join(lines) + "\n")


def load_design(path: Path) -> Design:
    with path.open("rb") as f:
        data = tomllib.load(f)
    unknown = set(data) - set(_ORDER)
    if unknown:
        raise ValueError(f"{path.name}: unknown fields {sorted(unknown)}")
    d = Design(**data)
    validate(d)
    return d


def load_designs(directory: Path = DESIGNS_DIR) -> dict[str, Design]:
    designs = {}
    for path in sorted(Path(directory).glob("*.toml")):
        d = load_design(path)
        designs[d.slug] = d
    return designs


@functools.cache
def kuroshio_designs() -> dict[str, Design]:
    return load_designs(DESIGNS_DIR)
