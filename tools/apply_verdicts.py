"""Copy the owner's Keep, Fix and Reject choices from the lab into the reference manifest.

    python -m tools.apply_verdicts [--images images.json] [--manifest design-data/references/manifest.json]

Fetches the choices from the lab unless --images is given. A manifest entry matches when its file name is the
image id without the gallery prefix (debt-, life-, wall-). Only Keep makes a file an approved reference.
"""

import argparse
import json
import urllib.request
from pathlib import Path

LAB = "http://192.168.10.19:8080/designs/api/images"
STATUS = {"keep": "approved", "fix": "needs-fix", "reject": "rejected"}
PREFIXES = ("debt-", "life-", "wall-", "day-", "room-")


def apply(entries: list[dict], verdicts: dict[str, dict]) -> tuple[int, list[str]]:
    """Updates entries in place. Returns how many changed and the ids that match nothing, so a missed pick is visible."""
    by_stem = {Path(e["path"]).stem: e for e in entries}
    changed, unmatched = 0, []
    for image, v in verdicts.items():
        stem = next((image[len(p):] for p in PREFIXES if image.startswith(p)), image)
        entry = by_stem.get(stem)
        if entry is None:
            unmatched.append(image)
            continue
        note = f"owner: {v['note']}" if v.get("note") else entry.get("note", "")
        if entry.get("status") != STATUS[v["verdict"]] or entry.get("note", "") != note:
            entry.update(status=STATUS[v["verdict"]], note=note)
            changed += 1
    return changed, unmatched


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--images", type=Path)
    parser.add_argument("--manifest", type=Path, default=Path("design-data/references/manifest.json"))
    args = parser.parse_args(argv)
    if args.images:
        verdicts = json.loads(args.images.read_text())
    else:
        with urllib.request.urlopen(LAB, timeout=10) as r:
            verdicts = json.load(r)
    entries = json.loads(args.manifest.read_text())
    changed, unmatched = apply(entries, verdicts)
    args.manifest.write_text(json.dumps(entries, indent=1, ensure_ascii=False))
    print(f"{changed} updated, {len(unmatched)} not in the manifest: {', '.join(unmatched) or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
