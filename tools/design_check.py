"""Checks rendered character sheets against each character's reference record and against each other.

    ~/.cache/nightwire-qa/bin/python -m tools.design_check [slug ...]
    ~/.cache/nightwire-qa/bin/python -m tools.design_check --scenes

Needs the `qa` extra (dghs-imgutils, onnxruntime); CPU only, models download on first run. Writes
design-data/qa/report.json, which the Review page shows. Flags are prompts to look, not verdicts:
the tagger is reliable for big features (hair and eye colour, cigarettes, extra views) and weak on
small ones (scars, piercings), so a pass doesn't prove a sheet right.
"""

import argparse
import itertools
import json
import statistics
from pathlib import Path

from narrator.designs import load_design

TAG_MODEL = "EVA02_Large"
PANEL_COLUMNS, PANEL_ROWS = 3, 2
REQUIRED_MIN = 0.35
FORBIDDEN_MIN = 0.5
SAME_CHARACTER_MAX = 0.178  # CCIP's published threshold, below which two crops read as one character
LOOKS_ALIKE_MAX = 0.07  # median across panel pairs; set from this cast's own scores (same character sits near 0.03)
COLOURS = ("aqua", "black", "blonde", "blue", "brown", "green", "grey", "orange", "pink", "purple", "red", "white", "silver")
SHEET_GREY = (60, 215)  # border brightness a turnaround's plain background should fall in
ALWAYS_FORBIDDEN = ("cigarette", "smoking", "holding", "multiple views", "2girls", "2boys", "multiple boys",
                    "multiple girls", "extra arms", "extra hands", "fangs", "visor")


def forbidden_terms(d) -> list[str]:
    own = [t.strip() for t in (d.negative or "").split(",")] + [h.strip() for h in d.held]
    canon = {t.strip() for t in d.tags.split(",")} - {h.strip() for h in d.held} | set(d.required)
    # "fang" and "fangs" are one feature to the tagger
    return [t for t in dict.fromkeys((*ALWAYS_FORBIDDEN, *own)) if t and t not in canon and t.rstrip("s") not in canon]


def judge_tags(required: list[str], forbidden: list[str], panels: list[dict[str, float]]) -> dict:
    """Which required details are missing and which forbidden ones appear. Tags the tagger doesn't know go in
    `unchecked`, so nothing reads as verified that wasn't looked at."""
    vocab = panels[0] if panels else {}
    missing = {t: sum(p.get(t, 0) < REQUIRED_MIN for p in panels) for t in required if t in vocab}
    found = {t: sum(p.get(t, 0) >= FORBIDDEN_MIN for p in panels) for t in forbidden if t in vocab}
    return {"missing": {t: n for t, n in missing.items() if n}, "forbidden": {t: n for t, n in found.items() if n},
            "unchecked": [t for t in required if t not in vocab]}


def colour_drift(panels: list[dict[str, float]], canon: set[str]) -> dict:
    """Eye and hair colours that change between panels. Colours the record asks for don't count against hair with
    coloured tips, but two different colours where the record names one do."""
    out = {}
    for part in ("eyes", "hair"):
        seen = {}
        for p in panels:
            colour = max(COLOURS, key=lambda c: p.get(f"{c} {part}", 0))
            if p.get(f"{colour} {part}", 0) >= REQUIRED_MIN:
                seen[colour] = seen.get(colour, 0) + 1
        if len(seen) > 1 and not all(f"{c} {part}" in canon for c in seen):
            out[part] = seen
    return out


def border_brightness(im) -> float:
    """Median brightness of the outermost 2% of the picture, which on a plain sheet is the background."""
    grey = im.convert("L")
    w, h = grey.size
    m = max(w, h) // 50
    boxes = ((0, 0, w, m), (0, h - m, w, h), (0, 0, m, h), (w - m, 0, w, h))
    return statistics.median(v for b in boxes for v in grey.crop(b).resize((32, 32)).tobytes())


def flags_for(entry: dict, n_panels: int = 6) -> list[str]:
    out = [f"{t}: shows in {n} of {n_panels} panels" for t, n in entry["forbidden"].items()]
    # One or two misses are mostly tagger noise on small details; half the sheet is worth a look.
    out += [f"{t}: missing from {n} of {n_panels} panels" for t, n in entry["missing"].items() if n >= n_panels / 2]
    worst = entry.get("worst_panel_pair")
    if worst and worst["difference"] > SAME_CHARACTER_MAX:
        out.append(f"{worst['a']} and {worst['b']} may not read as the same character ({worst['difference']:.2f})")
    out += [f"{part} colour changes between panels: {seen}" for part, seen in entry.get("drift", {}).items()]
    for sheet, diff in entry.get("sheets", {}).items():
        if diff > SAME_CHARACTER_MAX:
            out.append(f"{sheet} may not read as the same character as its matching sheet ({diff:.2f})")
    out += [f"{t}: missing from turnaround" for t in entry.get("body_hair_missing", [])]
    for sheet, level in entry.get("background", {}).items():
        if not SHEET_GREY[0] <= level <= SHEET_GREY[1]:
            out.append(f"{sheet} background isn't mid-grey (brightness {level:.0f})")
    near = entry.get("nearest")
    if near and near["difference"] <= LOOKS_ALIKE_MAX:
        out.append(f"looks like {near['slug']} ({near['difference']:.2f})")
    return out


def scene_people(name: str) -> list[str]:
    """Who each scene file should show, left to right: a--loc.png or pair--a--b--loc.png."""
    parts = name.removesuffix(".png").split("--")
    return parts[1:3] if parts[0] == "pair" else parts[:1]


def rank_of(slug: str, medians: dict[str, float]) -> int:
    """1 means this crop reads as closer to the character it should be than to anyone else in the cast."""
    return sorted(medians, key=medians.get).index(slug) + 1


def check_scenes(args) -> int:
    """Finds each person's head in a scene and compares it with every character's expression panels, so the score
    doesn't depend on a fixed threshold: the test is whether the right character comes out closest."""
    from imgutils.detect import detect_heads
    from imgutils.metrics import ccip_batch_differences, ccip_extract_feature
    from imgutils.tagging import get_wd14_tags
    from PIL import Image

    panels = {}
    for p in sorted(args.designs_dir.glob("*.toml")):
        d, sheet = load_design(p), args.design_dir / p.stem / "expressions.png"
        if d.kind == "character" and sheet.exists():
            panels[p.stem] = [ccip_extract_feature(c) for c in panels_of(sheet)]
    report = {}
    for scene in sorted((args.design_dir / "scenes").glob("*.png")):
        im = Image.open(scene).convert("RGB")
        people = scene_people(scene.name)
        heads = sorted(detect_heads(im), key=lambda h: h[2], reverse=True)[:len(people)]
        boxes = sorted((h[0] for h in heads), key=lambda b: b[0])
        entry = {"heads_found": len(heads), "expected": len(people), "people": {}}
        for slug, box in zip(people, boxes):
            pad = (box[2] - box[0]) // 3
            crop = im.crop((max(box[0] - pad, 0), max(box[1] - pad, 0), min(box[2] + pad, im.width), min(box[3] + pad, im.height)))
            feature = ccip_extract_feature(crop)
            medians = {o: statistics.median(float(ccip_batch_differences([feature, x])[0][1]) for x in fs) for o, fs in panels.items()}
            d = load_design(args.designs_dir / f"{slug}.toml")
            tags = get_wd14_tags(crop, model_name=TAG_MODEL, general_threshold=0.0, character_threshold=1.0,
                                 no_underline=True, drop_overlap=False)[1]
            verdict = judge_tags(d.required, [t for t in ("cigarette", "visor") if t not in d.required and t not in d.tags], [tags])
            entry["people"][slug] = {"rank": rank_of(slug, medians), "of": len(medians), "difference": medians[slug],
                                     "closest": min(medians, key=medians.get), "missing": list(verdict["missing"])}
        report[scene.name] = entry
    out = args.design_dir / "qa" / "scenes.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1, sort_keys=True))
    for name, entry in report.items():
        print(name, f"heads {entry['heads_found']}/{entry['expected']}",
              {s: (f"rank {v['rank']}/{v['of']}", f"closest {v['closest']}", v["missing"]) for s, v in entry["people"].items()})
    print(out)
    return 0


def sheet_consistency(slug_dir: Path, panels: list) -> tuple[dict[str, float], dict[str, float]]:
    """Largest-head difference between sheets in the same look (portrait against expressions, colour guide against
    turnaround), and the body sheets' background brightness. Across E and F the score didn't separate characters
    (pilot, 2026-11-02: two of five turnarounds sat closer to someone else's expressions), so it isn't compared."""
    from imgutils.detect import detect_heads
    from imgutils.metrics import ccip_batch_differences, ccip_extract_feature
    from PIL import Image

    features, background = {}, {}
    for sheet in ("portrait", "turnaround"):
        path = slug_dir / f"{sheet}.png"
        if not path.exists():
            continue
        im = Image.open(path).convert("RGB")
        im.thumbnail((1216, 1216))
        if sheet != "portrait":
            background[sheet] = border_brightness(im)
        heads = detect_heads(im)
        if heads:
            box = max((h[0] for h in heads), key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
            features[sheet] = ccip_extract_feature(im.crop(box))
    same = {}
    if "portrait" in features:
        same["portrait"] = statistics.median(float(ccip_batch_differences([features["portrait"], x])[0][1]) for x in panels)
    return same, background


def body_hair_missing(d, slug_dir: Path) -> list[str]:
    """Hair colours the record asks for that the turnaround doesn't show: the one check that crosses from E to F."""
    from imgutils.tagging import get_wd14_tags
    from PIL import Image

    path = slug_dir / "turnaround.png"
    if not path.exists():
        return []
    tags = get_wd14_tags(Image.open(path).convert("RGB"), model_name=TAG_MODEL, general_threshold=0.0, character_threshold=1.0,
                         no_underline=True, drop_overlap=False)[1]
    return [t for t in d.required if t.endswith(" hair") and t.split()[0] in COLOURS and tags.get(t, 0) < REQUIRED_MIN]


def panels_of(path: Path):
    from PIL import Image
    im = Image.open(path).convert("RGB")
    w, h = im.width // PANEL_COLUMNS, im.height // PANEL_ROWS
    # Skip the top strip so the printed label isn't read as part of the picture.
    return [im.crop((c * w, r * h + h // 12, (c + 1) * w, (r + 1) * h)) for r in range(PANEL_ROWS) for c in range(PANEL_COLUMNS)]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slugs", nargs="*")
    parser.add_argument("--designs-dir", type=Path, default=Path("narrator/worlds/designs"))
    parser.add_argument("--design-dir", type=Path, default=Path("design-data"))
    parser.add_argument("--scenes", action="store_true", help="check design-data/scenes instead of the expression sheets")
    args = parser.parse_args(argv)
    if args.scenes:
        return check_scenes(args)
    from imgutils.metrics import ccip_batch_differences, ccip_extract_feature
    from imgutils.tagging import get_wd14_tags
    from narrator.design_sheets import expressions_for

    report, features = {}, {}
    for p in sorted(args.designs_dir.glob("*.toml")):
        d, sheet = load_design(p), args.design_dir / p.stem / "expressions.png"
        if d.kind != "character" or not sheet.exists() or (args.slugs and p.stem not in args.slugs):
            continue
        crops = panels_of(sheet)
        labels = [label for label, _ in expressions_for(d)]
        tags = [get_wd14_tags(c, model_name=TAG_MODEL, general_threshold=0.0, character_threshold=1.0,
                              no_underline=True, drop_overlap=False)[1] for c in crops]
        entry = judge_tags(d.required, forbidden_terms(d), tags)
        features[p.stem] = [ccip_extract_feature(c) for c in crops]
        diffs = ccip_batch_differences(features[p.stem])
        a, b = max(itertools.combinations(range(len(crops)), 2), key=lambda ij: diffs[ij[0]][ij[1]])
        entry["worst_panel_pair"] = {"a": labels[a], "b": labels[b], "difference": float(diffs[a][b])}
        entry["drift"] = colour_drift(tags, set(d.required) | {t.strip() for t in d.tags.split(",")})
        entry["sheets"], entry["background"] = sheet_consistency(args.design_dir / p.stem, features[p.stem])
        entry["body_hair_missing"] = body_hair_missing(d, args.design_dir / p.stem)
        report[p.stem] = entry
    # ponytail: every panel against every other character's, O(n²) but this cast is 20 characters
    for slug, entry in report.items():
        others = [(o, statistics.median(float(ccip_batch_differences([x, y])[0][1]) for x in features[slug] for y in fs))
                  for o, fs in features.items() if o != slug]
        if others:
            near, diff = min(others, key=lambda t: t[1])
            entry["nearest"] = {"slug": near, "difference": diff}
        entry["flags"] = flags_for(entry)
    out = args.design_dir / "qa" / "report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1, sort_keys=True))
    for slug, entry in report.items():
        print(slug, entry["flags"] or "clean", "| not checkable:", entry["unchecked"])
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
