"""Night recap renderer (spec 2026-11-24-night-recap-design.md): a saved session -> recap.html (panels and a facts box,
images copied beside it, opens from disk) and recap.mp4 (a silent animatic: 3.5 s a panel, a slow push-in, the
caption and line as a lower third, 0.5 s fades).

    python -m tools.recap sessions/<id>.json [--out DIR] [--no-video]
"""

import argparse
import html
import shutil
import subprocess
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from engine.persistence import JSONFileSessionStore
from engine.session import Session
from narrator import recap
from narrator.place_art import ART_DIR, location_art
from tools.shorts.animatic import _camera, _fit, zoom_pan
from tools.shorts.remote import h264_encoder

HOLD_S, FADE_S, FPS, SIZE = 3.5, 0.5, 12, (1216, 832)
CHARACTER_ART = ART_DIR.parent / "character_art"


def source(art: str | None, media_root: Path) -> Path | None:
    """The file behind a panel's art path, or None when it isn't on disk (the panel gets a dark card)."""
    if not art:
        return None
    for prefix, root in (("place-art/", ART_DIR), ("character-art/", CHARACTER_ART)):
        if art.startswith(prefix):
            p = root / art[len(prefix):]
            return p if p.is_file() else None
    p = media_root / art
    return p if p.is_file() else None


def art_for(p: dict, media_root: Path) -> Path | None:
    """The panel's art, else its place's art when a scene image is gone from disk, else None (a dark card)."""
    return source(p["art"], media_root) or source(location_art(p["place"]), media_root)


def _quote(p: dict) -> str:
    return f"{p['speaker']}: “{p['text']}”" if p["speaker"] else p["text"]


def write_html(session: Session, panels: list[dict], media_root: Path, out: Path) -> Path:
    img = out / "img"
    img.mkdir(parents=True, exist_ok=True)

    def copy(src: Path | None) -> str | None:
        if not src:
            return None
        dst = img / f"{src.parent.name}-{src.name}"
        if not dst.exists():
            shutil.copyfile(src, dst)
        return f"img/{dst.name}"

    e = html.escape
    cells = []
    for p in panels:
        art, face = copy(art_for(p, media_root)), copy(source(p["portrait"], media_root))
        pic = f'<img class="art" src="{e(art)}" alt="">' if art else '<div class="art dark"></div>'
        inset = f'<img class="face" src="{e(face)}" alt="">' if face else ""
        cells.append(f'<figure>{pic}{inset}<figcaption><b>{e(p["caption"])}</b>'
                     f'<p>{e(_quote(p))}</p><small>{e(p["action"])}</small></figcaption></figure>')
    f = recap.facts(session)
    facts = "".join(f"<h3>{e(title)}</h3><ul>{''.join(f'<li>{e(x)}</li>' for x in items)}</ul>"
                    for title, items in (("People met", f["people"]), ("Promises open", f["promises_open"]),
                                         ("Promises kept or broken", f["promises_done"]), ("Leads", f["leads"]))
                    if items)
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Night recap</title><style>
body{{margin:0;padding:16px;background:#07080b;color:#e6dccb;font:15px/1.45 Georgia,serif}}
h1,h3{{font-family:system-ui,sans-serif;letter-spacing:.12em;text-transform:uppercase;color:#f9d066}}
h1{{font-size:18px}} h3{{font-size:13px;margin:14px 0 4px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px}}
figure{{margin:0;position:relative;background:#0b0d11;border:1.5px solid #2a4647}}
.art{{display:block;width:100%;aspect-ratio:1216/832;object-fit:cover}} .dark{{background:#16161a}}
.face{{position:absolute;top:8px;right:8px;width:64px;height:64px;object-fit:cover;border:1.5px solid #7aeaee}}
figcaption{{padding:8px 10px}} figcaption b{{font:600 12px system-ui,sans-serif;letter-spacing:.1em;color:#7aeaee}}
figcaption p{{margin:4px 0}} small{{color:#9aa3ad;font-family:system-ui,sans-serif}}
ul{{margin:0;padding-left:18px}}</style></head><body>
<h1>Night {f["night"]} · {e(session.characters and next(iter(session.characters.values())).name or "")}</h1>
<div class="grid">{"".join(cells)}</div><section>{facts}</section></body></html>"""
    path = out / "recap.html"
    path.write_text(page, encoding="utf-8")
    return path


def _lower_third(im: Image.Image, p: dict, face: Path | None) -> Image.Image:
    im = im.copy()
    w, h = im.size
    big, small = h // 30, h // 44
    lines = textwrap.wrap(_quote(p), width=int(w / (big * 0.55)))[:3]
    band_h = big // 2 + small + 8 + len(lines) * (big + 6) + small + 14
    band = Image.new("RGB", (w, band_h), (0, 0, 0))
    im.paste(Image.blend(im.crop((0, h - band_h, w, h)), band, 0.7), (0, h - band_h))
    d, y = ImageDraw.Draw(im), h - band_h + big // 2
    d.text((big, y), p["caption"].upper(), fill=(122, 234, 238), font=ImageFont.load_default(size=small))
    y += small + 8
    for line in lines:
        d.text((big, y), line, fill=(240, 236, 226), font=ImageFont.load_default(size=big))
        y += big + 6
    d.text((big, y + 4), p["action"][:140], fill=(154, 163, 173), font=ImageFont.load_default(size=small))
    if face:
        side = h // 5
        im.paste(_fit(face, (side, side)), (w - side - big, big))
    return im


def frames(panels: list[dict], media_root: Path, fps: int = FPS, size: tuple[int, int] = SIZE):
    n = round(HOLD_S * fps)
    fade = round(FADE_S * fps)
    black = Image.new("RGB", size)
    for p in panels:
        base, face = _fit(art_for(p, media_root), size), source(p["portrait"], media_root)
        for i in range(n):
            im = _lower_third(_camera(base, *zoom_pan("push-in", i / max(1, n - 1))), p, face)
            edge = min(i + 1, n - i)
            yield Image.blend(black, im, edge / fade) if edge < fade else im


def write_video(panels: list[dict], media_root: Path, out: Path, fps: int = FPS) -> Path:
    path = out / "recap.mp4"
    enc = h264_encoder()
    quality = ["-crf", "22"] if enc == "libx264" else ["-b:v", "3M"]
    ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s",
                           f"{SIZE[0]}x{SIZE[1]}", "-r", str(fps), "-i", "-", "-c:v", enc, "-pix_fmt", "yuv420p",
                           *quality, str(path)], stdin=subprocess.PIPE)
    try:
        for im in frames(panels, media_root, fps):
            ff.stdin.write(im.tobytes())
    finally:
        ff.stdin.close()
        if ff.wait() != 0:
            raise RuntimeError(f"ffmpeg failed writing {path}")
    return path


def build(session_file: Path, out: Path, video: bool = True) -> list[Path]:
    session_file = Path(session_file)
    session = JSONFileSessionStore(session_file.parent).load(session_file.stem)
    if session is None:
        raise SystemExit(f"no session at {session_file}")
    panels = recap.panels(session)
    if not panels:
        raise SystemExit(f"{session_file.name}: no turns to recap")
    out.mkdir(parents=True, exist_ok=True)
    made = [write_html(session, panels, session_file.parent, out)]
    if video:
        made.append(write_video(panels, session_file.parent, out))
    return made


def main(argv: list[str] | None = None) -> int:
    a = argparse.ArgumentParser(prog="python -m tools.recap", description=__doc__.splitlines()[0])
    a.add_argument("session", type=Path)
    a.add_argument("--out", type=Path)
    a.add_argument("--no-video", action="store_true")
    args = a.parse_args(argv)
    for p in build(args.session, args.out or args.session.with_name(f"{args.session.stem}-recap"), not args.no_video):
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
