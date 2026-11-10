"""Browse-only gallery of the library: design-data/shorts/_site/library/index.html + <pose>/<camera>/board.jpg thumbnails."""

import html
import os
from pathlib import Path

from PIL import Image

from tools.greybox_library import presets

THUMB = 360
GROUPS = {"basic": "Basic", "cinematic": "Cinematic", "editorial": "Editorial (magazine poses)", "character": "Character-specific"}


def site_dir() -> Path:
    return Path(os.environ.get("NIGHTWIRE_DESIGN_DIR", "design-data")) / "shorts" / "_site" / "library"


def build(lib: Path, site: Path) -> Path:
    sections = []
    for group, title in GROUPS.items():
        poses = [p for p, v in presets.POSES.items() if v["group"] == group]
        found = _poses(lib, site, poses)
        if found:
            sections += [f"<h2 class=grp>{html.escape(title)}</h2>", *found]
    return _write(site, sections)


def _poses(lib: Path, site: Path, poses) -> list[str]:
    sections = []
    for pose in poses:
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
            who = presets.POSES[pose].get("for")
            name = html.escape(pose) + (f" <small>for {html.escape(who)}</small>" if who else "")
            sections.append(f"<section><h3>{name}</h3><div class=g>{''.join(figs)}</div></section>")
    return sections


def _write(site: Path, sections: list[str]) -> Path:
    page = ("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>Grey-box library</title>"
            "<style>body{background:#161618;color:#ddd;font:15px system-ui;margin:16px}.g{display:flex;flex-wrap:wrap;gap:10px}"
            "h2.grp{border-bottom:1px solid #444;margin-top:28px}small{color:#999;font-weight:400}figure{margin:0;width:240px}img{width:100%;display:block;border-radius:4px}figcaption{padding:2px 0;color:#aaa}</style>"
            "<h1>Grey-box library</h1><p>Browse only: pose by camera stand-ins used for grey draft boards.</p>" + "".join(sections))
    site.mkdir(parents=True, exist_ok=True)
    (site / "index.html").write_text(page)
    return site / "index.html"
