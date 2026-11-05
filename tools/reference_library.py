"""Local, labelled reference library: turnaround views per character and drawn pose skeletons.

    python -m tools.reference_library build rin-kageyama hachi
    python -m tools.reference_library add rin-kageyama path.png --lighting "pink neon" --place bar --note "soft tint"

Writes design-data/library/<slug>/ and design-data/library/poses/, each with a manifest.json of labels. Images stay out
of git like the rest of design-data. Scene images start as owner_ok false: only the owner promotes them.
"""

import argparse
import json
import shutil
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

LIBRARY = Path("design-data/library")
VIEWS = ("front", "side", "back")
_GREY_TOLERANCE = 24
# OpenPose body keypoint order and colours, which pose ControlNets are trained on.
_ORDER = ("nose", "neck", "rsho", "relb", "rwri", "lsho", "lelb", "lwri", "rhip", "rkne", "rank", "lhip", "lkne", "lank", "reye", "leye", "rear", "lear")
_LIMBS = (("neck", "rsho"), ("neck", "lsho"), ("rsho", "relb"), ("relb", "rwri"), ("lsho", "lelb"), ("lelb", "lwri"), ("neck", "rhip"), ("rhip", "rkne"),
          ("rkne", "rank"), ("neck", "lhip"), ("lhip", "lkne"), ("lkne", "lank"), ("neck", "nose"), ("nose", "reye"), ("reye", "rear"), ("nose", "leye"), ("leye", "lear"))
_COLOURS = ((255, 0, 0), (255, 85, 0), (255, 170, 0), (255, 255, 0), (170, 255, 0), (85, 255, 0), (0, 255, 0), (0, 255, 85), (0, 255, 170), (0, 255, 255),
            (0, 170, 255), (0, 85, 255), (0, 0, 255), (85, 0, 255), (170, 0, 255), (255, 0, 255), (255, 0, 170), (255, 0, 85))
_HEAD = {"nose": (0, .06), "neck": (0, .15), "reye": (-.02, .045), "leye": (.02, .045), "rear": (-.045, .055), "lear": (.045, .055)}
_TORSO = {"rsho": (-.10, .16), "lsho": (.10, .16), "rhip": (-.06, .50), "lhip": (.06, .50)}
_LEGS = {"rkne": (-.07, .72), "rank": (-.08, .95), "lkne": (.07, .72), "lank": (.08, .95)}
_ARMS = {"relb": (-.13, .30), "rwri": (-.14, .43), "lelb": (.13, .30), "lwri": (.14, .43)}
# x from the body's centre and y from the top of the head, both in body heights. Front-facing: the face points are all visible.
POSES = {
    "standing": {**_ARMS, **_LEGS},
    "hand-on-hip": {**_ARMS, **_LEGS, "lelb": (.19, .33), "lwri": (.08, .47)},
    "arms-crossed": {**_LEGS, "relb": (-.14, .32), "rwri": (.06, .30), "lelb": (.14, .32), "lwri": (-.06, .32)},
    "hands-in-pockets": {**_LEGS, "relb": (-.17, .33), "rwri": (-.08, .50), "lelb": (.17, .33), "lwri": (.08, .50)},
    "wide-stance": {**_ARMS, "rkne": (-.12, .72), "rank": (-.17, .95), "lkne": (.12, .72), "lank": (.17, .95)},
    "walking": {**_ARMS, "rwri": (-.09, .41), "lwri": (.18, .41), "rkne": (-.09, .72), "rank": (-.13, .95), "lkne": (.05, .71), "lank": (.03, .92)},
    "hand-raised": {**_ARMS, **_LEGS, "relb": (-.16, .19), "rwri": (-.14, .05)},
    "sitting": {**_ARMS, "rwri": (-.10, .48), "lwri": (.10, .48), "rhip": (-.07, .52), "lhip": (.07, .52), "rkne": (-.12, .60), "rank": (-.12, .85),
                "lkne": (.12, .60), "lank": (.12, .85)},
}


def split_figures(im: Image.Image) -> list[Image.Image]:
    """Cut a turnaround on plain grey into its figures, left to right, at empty columns."""
    a = np.asarray(im.convert("RGB")).astype(int)
    fg = np.abs(a - 128).sum(axis=2) > _GREY_TOLERANCE
    cols = fg.any(axis=0)
    min_width = im.width * 0.05  # narrower runs are stray marks or props, not people
    figures, start = [], None
    for x, on in enumerate([*cols, False]):
        if on and start is None:
            start = x
        elif not on and start is not None:
            if x - start >= min_width:
                rows = np.where(fg[:, start:x].any(axis=1))[0]
                figures.append(im.crop((start, int(rows[0]), x, int(rows[-1]) + 1)))
            start = None
    return figures


def pose_points(name: str) -> dict[str, tuple[float, float]]:
    return {**_HEAD, **_TORSO, **POSES[name]}


def draw_pose(size: tuple[int, int], placed: list[tuple[str, float]], body_h: float, top: float) -> Image.Image:
    """Skeletons on black. `placed` is (pose name, centre x in pixels) per person, so the count in the frame is exact."""
    im = Image.new("RGB", size, "black")
    d = ImageDraw.Draw(im)
    for name, cx in placed:
        pts = {k: (cx + x * body_h, top + y * body_h) for k, (x, y) in pose_points(name).items()}
        for i, (a, b) in enumerate(_LIMBS):
            d.line([pts[a], pts[b]], fill=tuple(int(c * .6) for c in _COLOURS[i]), width=max(3, int(body_h * .012)))
        for key, p in pts.items():
            r = max(3, int(body_h * .008))
            d.ellipse((p[0] - r, p[1] - r, p[0] + r, p[1] + r), fill=_COLOURS[_ORDER.index(key)])
    return im


def _load(path: Path) -> list[dict]:
    return json.loads(path.read_text()) if path.exists() else []


def build_character(slug: str, design_dir: Path, library: Path) -> list[dict]:
    out = library / slug
    out.mkdir(parents=True, exist_ok=True)
    figures = split_figures(Image.open(design_dir / slug / "turnaround.png"))
    # Only a clean three-view split can be labelled by view. Anything else needs a person's eye first.
    views = VIEWS if len(figures) == 3 else tuple(f"figure-{i}" for i in range(len(figures)))
    keep = [e for e in _load(out / "manifest.json") if e["kind"] != "view"]
    entries = []
    for view, figure in zip(views, figures):
        figure.save(out / f"{view}.png")
        entries.append({"file": f"{view}.png", "kind": "view", "view": view, "lighting": "plain grey", "source": "turnaround", "owner_ok": True})
    (out / "manifest.json").write_text(json.dumps(entries + keep, indent=1))
    return entries


def build_poses(library: Path) -> None:
    out = library / "poses"
    out.mkdir(parents=True, exist_ok=True)
    entries = []
    for name in POSES:
        draw_pose((832, 1216), [(name, 416.0)], 1216 * .9, 1216 * .05).save(out / f"{name}.png")
        entries.append({"file": f"{name}.png", "kind": "pose", "name": name, "people": 1, "facing": "viewer"})
    (out / "manifest.json").write_text(json.dumps(entries, indent=1))


def add_scene(slug: str, source: Path, library: Path, **labels) -> dict:
    out = library / slug
    out.mkdir(parents=True, exist_ok=True)
    existing = _load(out / "manifest.json")
    name = f"scene-{sum(e['kind'] == 'scene' for e in existing):02d}.png"
    shutil.copyfile(source, out / name)
    entry = {"file": name, "kind": "scene", "source": source.name, "owner_ok": False, **labels}
    (out / "manifest.json").write_text(json.dumps([*existing, entry], indent=1))
    return entry


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--design-dir", type=Path, default=Path("design-data"))
    p.add_argument("--library", type=Path, default=LIBRARY)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("build").add_argument("slugs", nargs="+")
    a = sub.add_parser("add")
    a.add_argument("slug"); a.add_argument("image", type=Path)
    a.add_argument("--lighting", required=True); a.add_argument("--place", required=True); a.add_argument("--note", default="")
    args = p.parse_args(argv)
    if args.command == "build":
        build_poses(args.library)
        for slug in args.slugs:
            print(slug, [e["view"] for e in build_character(slug, args.design_dir, args.library)])
    else:
        print(add_scene(args.slug, args.image, args.library, lighting=args.lighting, place=args.place, note=args.note))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
