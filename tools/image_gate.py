"""Automatic first pass over new renders, before anyone looks at them. CPU only, ONNX models.

    ~/.cache/nightwire-qa/bin/python -m tools.image_gate IMAGE... [--character SLUG] [--people N] [--empty] [--out DIR]

Flags are prompts to look: a clean result doesn't prove an image right, and a person still reviews it
(see "Review before publishing" in docs/image-generation-guide.md). Writes report.json and heads.jpg, a
full-size sheet of every head for the age check.
"""

import argparse
import json
import statistics
from pathlib import Path

from narrator.designs import load_design
from tools.design_check import REQUIRED_MIN, TAG_MODEL, panels_of, rank_of

AGE_TAGS = ("child", "loli", "shota", "toddler", "aged down", "kindergarten uniform", "elementary schooler", "middle schooler")
AGE_MIN = 0.2  # deliberately low: a false alarm costs a look, a miss breaks the adults-only rule
HANDS_PER_HEAD = 2


def judge(*, heads: int, hands: int, text_regions: int, age_hits: dict[str, float], expected_people: int | None = None,
          empty: bool = False, persons: int = 0, rank: int | None = None, closest: str | None = None,
          missing: tuple[str, ...] = ()) -> list[str]:
    flags = []
    if age_hits:
        flags.append("age: " + ", ".join(f"{t} {s:.2f}" for t, s in sorted(age_hits.items())))
    if empty and (heads or persons):
        flags.append(f"people in an empty shot: {max(heads, persons)}")
    if expected_people is not None and heads != expected_people:
        flags.append(f"people: {heads} heads, expected {expected_people}")
    if not empty and heads and hands > heads * HANDS_PER_HEAD:
        flags.append(f"hands: {hands} for {heads} heads")
    if text_regions:
        flags.append(f"lettering: {text_regions} regions, check for gibberish")
    if rank is not None and rank > 1:
        flags.append(f"likeness: ranks {rank} in the cast, closest is {closest}")
    if missing:
        flags.append("missing: " + ", ".join(missing))
    return flags


def _crop(im, box, pad_ratio=3):
    pad = (box[2] - box[0]) // pad_ratio
    return im.crop((max(box[0] - pad, 0), max(box[1] - pad, 0), min(box[2] + pad, im.width), min(box[3] + pad, im.height)))


def _head_sheet(crops: list, path: Path, cell: int = 300, columns: int = 6) -> None:
    from PIL import Image, ImageDraw
    rows = (len(crops) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * cell, max(rows, 1) * cell))
    draw = ImageDraw.Draw(sheet)
    for n, (label, crop) in enumerate(crops):
        x, y = (n % columns) * cell, (n // columns) * cell
        sheet.paste(crop.resize((cell, cell)), (x, y))
        draw.text((x + 4, y + 4), label, fill="white")
    sheet.save(path, quality=88)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+", type=Path)
    parser.add_argument("--character", help="approved character the image should show")
    parser.add_argument("--people", type=int, help="how many people the image should show")
    parser.add_argument("--empty", action="store_true", help="the shot must have nobody in it")
    parser.add_argument("--out", type=Path, default=Path("design-data/qa/gate"))
    parser.add_argument("--designs-dir", type=Path, default=Path("narrator/worlds/designs"))
    parser.add_argument("--design-dir", type=Path, default=Path("design-data"))
    args = parser.parse_args(argv)
    from imgutils.detect import detect_hands, detect_heads, detect_person, detect_text
    from imgutils.metrics import ccip_batch_differences, ccip_extract_feature
    from imgutils.tagging import get_wd14_tags
    from PIL import Image

    panels = {}
    if args.character:
        for p in sorted(args.designs_dir.glob("*.toml")):
            d, sheet = load_design(p), args.design_dir / p.stem / "expressions.png"
            if d.kind == "character" and sheet.exists():
                panels[p.stem] = [ccip_extract_feature(c) for c in panels_of(sheet)]
    report, crops = {}, []
    for path in args.images:
        im = Image.open(path).convert("RGB")
        boxes = [h[0] for h in detect_heads(im)]
        age_hits, likeness, missing = {}, {}, ()
        for n, box in enumerate(boxes):
            crop = _crop(im, box)
            crops.append((f"{path.stem} {n}", crop))
            tags = get_wd14_tags(crop, model_name=TAG_MODEL, general_threshold=0.0, character_threshold=1.0,
                                 no_underline=True, drop_overlap=False)[1]
            for t in AGE_TAGS:
                if tags.get(t, 0) >= AGE_MIN:
                    age_hits[t] = max(age_hits.get(t, 0), float(tags[t]))
        if args.character and boxes:
            big = max(boxes, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
            feature = ccip_extract_feature(_crop(im, big))
            medians = {o: statistics.median(float(ccip_batch_differences([feature, x])[0][1]) for x in fs) for o, fs in panels.items()}
            likeness = {"rank": rank_of(args.character, medians), "closest": min(medians, key=medians.get),
                        "difference": medians[args.character]}
            whole = get_wd14_tags(im, model_name=TAG_MODEL, general_threshold=0.0, character_threshold=1.0,
                                  no_underline=True, drop_overlap=False)[1]
            d = load_design(args.designs_dir / f"{args.character}.toml")
            missing = tuple(t for t in d.required if whole.get(t, 0) < REQUIRED_MIN)
        counts = {"heads": len(boxes), "hands": len(detect_hands(im)), "text_regions": len(detect_text(im)),
                  "persons": len(detect_person(im))}
        flags = judge(**counts, age_hits=age_hits, expected_people=args.people, empty=args.empty,
                      rank=likeness.get("rank"), closest=likeness.get("closest"), missing=missing)
        report[str(path)] = {**counts, **likeness, "age_hits": age_hits, "flags": flags}
        print(path.name, flags or "no flags")
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "report.json").write_text(json.dumps(report, indent=1, sort_keys=True))
    _head_sheet(crops, args.out / "heads.jpg")
    print(args.out / "heads.jpg")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
