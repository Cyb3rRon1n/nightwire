"""Browse-only gallery of the library: design-data/shorts/_site/library/index.html + <pose>/<camera>/board.jpg thumbnails."""

import html
import os
from pathlib import Path

from PIL import Image

from tools.greybox_library import presets

THUMB = 360


def site_dir() -> Path:
    return Path(os.environ.get("NIGHTWIRE_DESIGN_DIR", "design-data")) / "shorts" / "_site" / "library"


def build(lib: Path, site: Path) -> Path:
    sections = []
    for pose in presets.POSES:
        figs = []
        for cam in presets.CAMERAS:
            src = lib / pose / cam / "board.png"
            if not src.exists():
                continue
            dst = site / pose / cam / "board.jpg"
            dst.parent.mkdir(parents=True, exist_ok=True)
            im = Image.open(src).convert("RGB")
            im.thumbnail((THUMB, THUMB))
            im.save(dst, "JPEG", quality=82)
            figs.append(f'<figure><img loading="lazy" src="{html.escape(pose)}/{html.escape(cam)}/board.jpg" alt="{html.escape(pose)} {html.escape(cam)}"><figcaption>{html.escape(cam)}</figcaption></figure>')
        if figs:
            sections.append(f"<section><h2>{html.escape(pose)}</h2><div class=g>{''.join(figs)}</div></section>")
    page = ("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>Grey-box library</title>"
            "<style>body{background:#161618;color:#ddd;font:15px system-ui;margin:16px}.g{display:flex;flex-wrap:wrap;gap:10px}"
            "figure{margin:0;width:240px}img{width:100%;display:block;border-radius:4px}figcaption{padding:2px 0;color:#aaa}</style>"
            "<h1>Grey-box library</h1><p>Browse only: pose by camera stand-ins used for grey draft boards.</p>" + "".join(sections))
    site.mkdir(parents=True, exist_ok=True)
    (site / "index.html").write_text(page)
    return site / "index.html"
