"""Draft boards: the shot's plate (or a dark placeholder card) with grey-box library figures inserted per [[board]]."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from tools.greybox_library import build as lib_build
from tools.greybox_library import insert
from tools.shorts import plates as plate_mod

CARD = (1216, 832)


def _placeholder(name: str, out: Path) -> Path:
    im = Image.new("RGB", CARD, (22, 22, 26))
    ImageDraw.Draw(im).text((24, 24), f"plate: {name or '(none named)'}", fill=(235, 235, 240), font=ImageFont.load_default(size=36))
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
    return out


def build(short, design_dir: Path, work: Path, lib: Path | None = None, plates_root: Path | None = None, shot: str | None = None) -> list[Path]:
    """Writes work/shots/<id>/board-<which>.png for every shot with [[board]] entries (only `shot` when given)."""
    lib = lib or lib_build.default_out()
    catalogue = plate_mod.load_plates(short.place, plates_root)
    out = []
    for sh in short.shots:
        if (shot and sh.id != shot) or not sh.boards:
            continue
        sd = work / "shots" / sh.id
        plate = catalogue.get(sh.plate)
        src = plate_mod.plate_path(design_dir, short.place, plate) if plate else None
        if src is None or not src.exists():
            src = _placeholder(sh.plate, sd / "plate-placeholder.png")  # drafting never waits for a plate
        for which in ("start", "end"):
            figs = []
            for b in (b for b in sh.boards if b.which == which):
                entry = lib / b.pose / b.camera
                if not (entry / "board.png").exists():
                    raise ValueError(f"{sh.id}: no library cell {b.pose}/{b.camera} in {lib} (python -m tools.greybox_library build)")
                figs.append({"entry": entry, "feet": b.feet, "height": b.height, "label": b.figure})
            if figs:
                out.append(insert.insert_many(src, figs, sd / f"board-{which}.png"))
    return out
