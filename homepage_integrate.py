#!/usr/bin/env python3
"""
Add a "Nightwire" tile to a co-located Vulcan install's Homepage dashboard.
Optional, one-shot — run it after `docker compose up`, and again any time
the URL changes.

Mirrors anvil/installer/vulcan_integration.py's merge_into_vulcan_homepage()
exactly: same tile shape ({name: {href, icon, description}}), same
write-once respect for Vulcan's own groups (only this script's own named
group is ever touched), same insert-before-"Guides" placement.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

GROUP_NAME = "Nightwire"
ICON_URL = "https://raw.githubusercontent.com/Cyb3rRon1n/nightwire/main/docs/images/logo.svg"


def find_vulcan_stack(search_paths: list[Path] | None = None) -> Path | None:
    if search_paths is None:
        cwd = Path.cwd().resolve()
        search_paths = [cwd.parent / "vulcan" / "stack", cwd / "vulcan" / "stack"]
    for path in search_paths:
        if (path / ".vulcan-state.json").exists():
            return path
    return None


def merge_tile(services_yaml_path: Path, url: str) -> None:
    groups = yaml.safe_load(services_yaml_path.read_text()) or []
    groups = [g for g in groups if GROUP_NAME not in g]

    tile = {GROUP_NAME: {"href": url, "icon": ICON_URL, "description": "Cyberpunk AI game master, playable in a browser"}}
    insert_at = next((i for i, g in enumerate(groups) if "Guides" in g), len(groups))
    groups.insert(insert_at, {GROUP_NAME: [tile]})

    services_yaml_path.write_text(yaml.safe_dump(groups, sort_keys=False))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:3000/nightwire", help="frontend URL (default: http://localhost:3000/nightwire)")
    parser.add_argument("--vulcan-dir", type=Path, help="path to Vulcan's stack/ dir (auto-detected if omitted)")
    args = parser.parse_args()

    vulcan_dir = args.vulcan_dir or find_vulcan_stack()
    if vulcan_dir is None:
        print("[nightwire] no co-located Vulcan stack found (looked for a sibling vulcan/stack "
              "with .vulcan-state.json) — pass --vulcan-dir, or add the tile to your dashboard by hand.",
              file=sys.stderr)
        return 1

    services_yaml_path = vulcan_dir / "config" / "homepage" / "services.yaml"
    if not services_yaml_path.exists():
        print(f"[nightwire] Vulcan found at {vulcan_dir} but Homepage isn't enabled there "
              f"({services_yaml_path} doesn't exist) — enable it in Vulcan first.", file=sys.stderr)
        return 1

    merge_tile(services_yaml_path, args.url)
    print(f"[nightwire] added '{GROUP_NAME}' -> {args.url} to {services_yaml_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
