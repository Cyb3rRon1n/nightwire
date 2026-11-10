"""The film wall: one column per scene, one card per shot. Static and browse-only; decisions happen in the review inbox."""

import html
from pathlib import Path

from PIL import Image

from tools.shorts import preflight
from tools.shorts.model import load_short

THUMB = 480
CSS = ("body{background:#161618;color:#ddd;font:15px system-ui;margin:16px}.cols{display:flex;gap:14px;overflow-x:auto;align-items:flex-start}"
       ".col{flex:0 0 280px}.col h2{margin:0 0 4px;font-size:17px}.meta{color:#aaa;font-size:13px;margin:2px 0}"
       ".card{background:#222226;border-radius:6px;padding:8px;margin:10px 0}.card img{width:100%;display:block;border-radius:4px}"
       ".none{background:#111;color:#777;padding:40px 0;text-align:center;border-radius:4px}.warn{color:#e8b64a;font-size:13px}a{color:#8cf}")


def board_file(work: Path, shot_id: str) -> Path | None:
    return next((f for f in (work / "shots" / shot_id / "board-start.png", work / "shots" / shot_id / "board-end.png") if f.exists()), None)


def _e(s) -> str:
    return html.escape(str(s))


def _card(scene: str, short, sh, work: Path, site: Path) -> str:
    src = board_file(work, sh.id)
    if src:
        dst = site / "boards" / f"{scene}-{sh.id}.jpg"
        dst.parent.mkdir(parents=True, exist_ok=True)
        im = Image.open(src).convert("RGB")
        im.thumbnail((THUMB, THUMB))
        im.save(dst, "JPEG", quality=85)
        img = f'<img loading="lazy" src="boards/{_e(scene)}-{_e(sh.id)}.jpg" alt="{_e(scene)} {_e(sh.id)}">'
    else:
        img = '<div class="none">no board yet</div>'
    warns = preflight.one_action(sh) + preflight.pace(sh)
    return (f'<div class="card">{img}<div><b>{_e(sh.id)}</b> {_e(sh.size)} {_e(sh.move or "static")} {sh.duration:g} s</div>'
            f'<div class="meta">{_e(sh.action or sh.summary)}</div>'
            + "".join(f'<div class="warn">{_e(w)}</div>' for w in warns) + "</div>")


def build(film, film_slug: str, shorts_dir: Path, design_dir: Path, site_root: Path) -> Path:
    """site_root is design-data/shorts/_site; writes films/<film>/index.html plus boards/ thumbnails."""
    site = site_root / "films" / film_slug
    site.mkdir(parents=True, exist_ok=True)
    cols = []
    for scene in film.scenes:
        short = load_short(shorts_dir / scene)
        work = design_dir / "shorts" / scene
        sc = short.scene
        mood = "; ".join(x for x in ([sc.weather] + sc.light) if x) if sc else ""
        wardrobe = "".join(f'<div class="meta">{_e(cid)} ({_e(short.cast.get(cid, ""))}): {_e(w)}</div>' for cid, w in short.wardrobe.items())
        cols.append(f'<div class="col"><h2>{_e(short.title)}</h2><div class="meta">{_e(sc.time if sc else "")} · {_e(short.place)}</div>'
                    f'{wardrobe}<div class="meta">{_e(mood)}</div>' + "".join(_card(scene, short, sh, work, site) for sh in short.shots) + "</div>")
    page = ("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{_e(film.title)}</title><style>{CSS}</style><h1>{_e(film.title)}</h1><p>{_e(film.logline)}</p><p class=meta>Mood: {_e(film.mood)}</p>"
            f'<p><a href="/review/?project={_e(film_slug)}">Review in the inbox</a></p><div class="cols">{"".join(cols)}</div>')
    (site / "index.html").write_text(page)
    return site / "index.html"
