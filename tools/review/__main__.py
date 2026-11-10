"""python -m tools.review build [--world-ids PATH] | migrate"""

import argparse
import os
import sys
from pathlib import Path

from narrator.designs import load_designs
from tools.shorts import SHORTS_DIR
from tools.shorts.plates import PLATES_ROOT
from tools.review import migrate, producers
from tools.review.registry import build_items, write_items

PAGE = Path(__file__).with_name("inbox.html")
REMOTE = "192.168.10.19:anvil-deploy/stack/dashboard/review/"


def design_dir() -> Path:
    return Path(os.environ.get("NIGHTWIRE_DESIGN_DIR", "design-data"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.review")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--world-ids", type=Path, help="world-page/ids.json (default: the lab archive's, when present)")
    sub.add_parser("migrate")
    a = ap.parse_args(argv)
    if a.cmd == "migrate":
        return migrate.run()
    dd = design_dir()
    site = dd / "review" / "_site"
    archives = sorted(dd.glob("lab-archive/*/world-page/ids.json"))  # dated names: last is newest
    world_ids = a.world_ids or (archives[-1] if archives else None)
    ctx = {"design_dir": dd, "site": site, "world_ids": world_ids, "shorts_site": dd / "shorts" / "_site",
           "designs": load_designs(),
           "shorts_dir": Path(os.environ.get("NIGHTWIRE_SHORTS_DIR", SHORTS_DIR)),
           "plates_root": Path(os.environ.get("NIGHTWIRE_PLATES_DIR", PLATES_ROOT))}
    items, errors = build_items(producers.ALL, ctx)
    write_items(items, site)
    (site / "index.html").write_text(PAGE.read_text())
    for e in errors:
        print(f"warning: {e}", file=sys.stderr)
    print(f"{len(items)} item(s); publish with:\nrsync -a {site}/ {REMOTE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
