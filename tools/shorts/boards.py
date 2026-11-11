"""Draft boards: the shot's plate (or a dark placeholder card) with grey-box library figures inserted per [[board]]."""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from tools.greybox_library import build as lib_build
from tools.greybox_library import insert
from tools.greybox_library.presets import CAMERA_TWINS
from tools.shorts import plate_camera
from tools.shorts import plates as plate_mod

CARD = (1216, 832)


def _placeholder(name: str, out: Path) -> Path:
    im = Image.new("RGB", CARD, (22, 22, 26))
    ImageDraw.Draw(im).text((24, 24), f"plate: {name or '(none named)'}", fill=(235, 235, 240), font=ImageFont.load_default(size=36))
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
    return out


def crop_box(size: tuple[int, int], x: float) -> tuple[int, int, int, int]:
    """The 9:16 window: full frame height, centred at x (0..1 of the width), kept inside the frame."""
    W, H = size
    w = min(W, round(H * 9 / 16) // 2 * 2)
    left = min(max(round(x * W - w / 2), 0), W - w)
    return left, 0, left + w, H


def _safe_zone(png: Path, x: float) -> Path:
    """Writes <stem>-9x16.png (the clean crop) beside the board, then marks the window on the board itself."""
    im = Image.open(png).convert("RGB")
    box = crop_box(im.size, x)
    im.crop(box).save(png.with_name(png.stem + "-9x16.png"))
    marked = Image.eval(im, lambda v: int(v * 0.8))
    marked.paste(im.crop(box), box[:2])
    d = ImageDraw.Draw(marked)
    l, t, r, b = box
    for a in range(t, b, 16):  # dashed light outline
        d.line((l, a, l, min(a + 8, b - 1)), fill=(235, 235, 240))
        d.line((r - 1, a, r - 1, min(a + 8, b - 1)), fill=(235, 235, 240))
    for a in range(l, r, 16):
        d.line((a, t, min(a + 8, r - 1), t), fill=(235, 235, 240))
        d.line((a, b - 1, min(a + 8, r - 1), b - 1), fill=(235, 235, 240))
    marked.save(png)
    return png


PITCH_GAP = 0.25  # cell horizon vs plate horizon (0..1 of the frame) beyond which the figure is seen from the wrong height


def build(short, design_dir: Path, work: Path, lib: Path | None = None, plates_root: Path | None = None, shot: str | None = None,
          heights_cm: dict | None = None, warnings: list | None = None) -> list[Path]:
    """Writes work/shots/<id>/board-<which>.png for every shot with [[board]] entries (only `shot` when given).
    On a plate with a camera file, a figure without `height` gets its size from where its feet stand (heights_cm: cast id
    -> the character's height), and whatever the depth map shows nearer than its feet hides it."""
    warnings = [] if warnings is None else warnings
    lib = lib or lib_build.default_out()
    catalogue = plate_mod.load_plates(short.place, plates_root)
    out = []
    for sh in short.shots:
        if (shot and sh.id != shot) or not sh.boards:
            continue
        sd = work / "shots" / sh.id
        plate = catalogue.get(sh.plate)
        src = plate_mod.plate_path(design_dir, short.place, plate) if plate else None
        real = src is not None and src.exists()
        if not real:
            src = _placeholder(sh.plate, sd / "plate-placeholder.png")  # drafting never waits for a plate
        cam = plate_camera.load(src) if real else None
        dpath = plate_camera.depth_path(src)
        depth = Image.open(dpath) if real and dpath.exists() else None
        for which in ("start", "end"):
            figs = []
            for b in (b for b in sh.boards if b.which == which):
                entry = lib / b.pose / b.camera
                if not (entry / "board.png").exists():
                    raise ValueError(f"{sh.id}: no library cell {b.pose}/{b.camera} in {lib} (python -m tools.greybox_library build)")
                if cam is not None:  # the twin of the named camera whose horizon is nearest the plate's
                    twins = [lib / b.pose / c for c in CAMERA_TWINS.get(b.camera, (b.camera,)) if (lib / b.pose / c / "meta.json").exists()]
                    entry = min(twins or [entry], key=lambda e: abs(json.loads((e / "meta.json").read_text())["horizon_y"] - cam["horizon_y"]))
                meta = json.loads((entry / "meta.json").read_text())
                height = b.height
                if height is None:
                    if cam is None:
                        raise ValueError(f"{sh.id} {b.figure}: no height and plate {sh.plate!r} has no camera "
                                         f"(python -m tools.shorts camera {short.slug})")
                    cm = (heights_cm or {}).get(b.figure) or 165
                    try:
                        height = plate_camera.figure_height(b.feet[1], cam, plate_camera.pose_height_m(meta), cm)
                    except ValueError as e:
                        raise ValueError(f"{sh.id} {b.figure}: {e}")
                if cam is not None and abs(meta["horizon_y"] - cam["horizon_y"]) > PITCH_GAP:
                    warnings.append(f"{sh.id} {b.figure}: camera {entry.name} sees the figure from a different height than plate "
                                    f"{sh.plate} (horizon {meta['horizon_y']:.2f} vs {cam['horizon_y']:.2f})")
                in_front = (plate_camera.in_front_mask(depth, b.feet) if depth is not None and b.hidden_below is None else None)
                figs.append({"entry": entry, "feet": b.feet, "height": height, "label": b.figure, "hidden_below": b.hidden_below,
                             "in_front": in_front, "figure_only": real and not b.keep_props})
            if figs:
                out.append(_safe_zone(insert.insert_many(src, figs, sd / f"board-{which}.png"), sh.vertical))
    return out
