"""Owner sign-off per shot. An approval belongs to one exact prompt + reference set (its fingerprint), so any edit
after approval needs a new approval. Verdicts travel through the existing /designs/api/images review API under the
id plan--<slug>--<shot>--<fp> (keep = approved, fix = change with a note, reject)."""

import hashlib
import json
from pathlib import Path

from tools.shorts.takes import SLUG


def fingerprint(model: str, prompt: str, refs: list[tuple[str, Path]]) -> str:
    h = hashlib.sha256(model.encode() + b"\0" + prompt.encode())
    for label, path in refs:
        h.update(b"\0" + label.encode() + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return h.hexdigest()[:10]


def plan_image_id(slug: str, shot_id: str, fp: str) -> str:
    if "--" in slug or not SLUG.fullmatch(slug):
        raise ValueError(f"slug {slug!r} must match [a-z0-9][a-z0-9-]* and must not contain '--'")
    return f"plan--{slug}--{shot_id.lower()}--{fp}"


def apply_approvals(short_dir: Path, slug: str, api: dict) -> dict[str, dict]:
    prefix = f"plan--{slug}--"
    mine, per_shot = {}, {}
    for key, v in api.items():
        if not key.startswith(prefix):
            continue
        parts = key[len(prefix):].split("--")
        if len(parts) != 2:
            continue  # malformed id from the shared API; skip it
        mine[key] = v
        per_shot.setdefault(parts[0].upper(), {})[parts[1]] = {k: v[k] for k in ("verdict", "note") if k in v}
    short_dir.mkdir(parents=True, exist_ok=True)
    (short_dir / "approvals.json").write_text(json.dumps(per_shot, indent=1, sort_keys=True))
    return mine


def approval(short_dir: Path, shot_id: str, fp: str) -> dict | None:
    path = short_dir / "approvals.json"
    data = json.loads(path.read_text()) if path.exists() else {}
    return data.get(shot_id, {}).get(fp)


def attempts(short_dir: Path, shot_id: str, fp: str) -> int:
    """Paid attempts for this approval, from the ledger (a take that failed after the POST still cost money)."""
    path = short_dir / "costs.json"
    rows = json.loads(path.read_text()) if path.exists() else []
    return sum(1 for r in rows if r.get("shot") == shot_id and r.get("fp") == fp)
