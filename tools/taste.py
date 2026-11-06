"""The owner's likes and dislikes from the World Gallery, with their notes. Read it before planning new Nightwire renders.

    python -m tools.taste
"""

import json
import urllib.request

LAB = "http://192.168.10.19:8080/designs/api"


def summary(taste: dict, images: dict) -> str:
    """Liked and disliked image ids, newest first, each with the owner's note when there is one."""
    out = []
    for like, title in ((True, "Liked"), (False, "Disliked")):
        rows = sorted((r["at"], i) for i, r in taste.items() if r["like"] is like)
        out.append(f"{title} ({len(rows)}):")
        for _, i in reversed(rows):
            note = images.get(i, {}).get("note")
            out.append(f"  {i}" + (f": {note}" if note else ""))
    return "\n".join(out)


def main() -> int:
    get = lambda p: json.load(urllib.request.urlopen(f"{LAB}/{p}", timeout=10))
    print(summary(get("taste"), get("images")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
