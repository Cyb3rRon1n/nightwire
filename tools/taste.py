"""The owner's likes and dislikes from the World Gallery, with their notes. Read it before planning new Nightwire renders.

    python -m tools.taste
"""

import json
import urllib.request

LAB = "http://192.168.10.19:8080/designs/api"


def likes(taste: dict, images: dict) -> dict:
    """id -> (like, at). Keep counts as a like and Reject as a dislike; an explicit thumb wins."""
    out = {i: (r["verdict"] == "keep", r["at"]) for i, r in images.items() if r.get("verdict") in ("keep", "reject")}
    out.update({i: (r["like"], r["at"]) for i, r in taste.items()})
    return out


def summary(taste: dict, images: dict) -> str:
    """Liked and disliked image ids, newest first, each with the owner's note when there is one."""
    out, seen = [], likes(taste, images)
    for like, title in ((True, "Liked"), (False, "Disliked")):
        rows = sorted((at, i) for i, (l, at) in seen.items() if l is like)
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
