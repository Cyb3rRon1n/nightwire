"""One-off: copy the old per-character sheet reviews (/designs/api/reviews) into the shared verdict store as
sheet--<slug>--<version>, so the inbox shows them as already reviewed. Safe to re-run: existing ids are left alone."""

import json
import urllib.request

from tools.review.producers import sheet_id
from tools.review.registry import valid_id

MAP = {"ok": "keep", "fix": "fix"}


def plan_migration(reviews: dict, images: dict) -> dict[str, dict]:
    out = {}
    for slug, r in reviews.items():
        v, verdict = str(r.get("v", "")), MAP.get(r.get("verdict", ""))
        new = sheet_id(slug, v)
        if not v or not verdict or not valid_id(new) or new in images:
            continue
        out[new] = {"verdict": verdict, **({"note": r["note"]} if verdict == "fix" and r.get("note") else {})}
    return out


def _get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.loads(r.read())


def run(api_base: str = "http://192.168.10.19:8080/designs/api") -> int:
    todo = plan_migration(_get(f"{api_base}/reviews"), _get(f"{api_base}/images"))
    for new, body in todo.items():
        req = urllib.request.Request(f"{api_base}/images/{new}", data=json.dumps(body).encode(), method="PUT",
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=20).read()
    print(f"migrated {len(todo)} sheet review(s)")
    return 0
