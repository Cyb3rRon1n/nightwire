"""Location plates: the empty room from each camera direction a short needs. A plate is approved once (review id
plate--<place>--<name>) and reused by every later short at that place. Catalogues live in narrator/worlds/plates/,
outside the designs folder, because every design tool globs designs/*.toml as a design."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

PLATES_ROOT = Path(__file__).resolve().parents[2] / "narrator" / "worlds" / "plates"


@dataclass
class Plate:
    name: str
    view: str
    source: str = ""   # an existing approved image of the place adopted as this plate


def load_plates(place: str, plates_root: Path | None = None) -> dict[str, Plate]:
    path = (plates_root or PLATES_ROOT) / f"{place}.toml"
    if not path.exists():
        return {}
    return {p["name"]: Plate(**p) for p in tomllib.loads(path.read_text()).get("plate", [])}


def plate_path(design_dir: Path, place: str, plate: Plate) -> Path:
    return design_dir / place / (plate.source or f"plates/{plate.name}.png")


def plate_id(place: str, name: str) -> str:
    return f"plate--{place}--{name}"
