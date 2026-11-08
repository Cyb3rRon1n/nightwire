"""Hand-off for Dreamina / LibTV: a folder to paste from, and an inbox to file results from."""

import shutil
from pathlib import Path

from tools.shorts.takes import Ledger, file_take


def write_bundle(shot_dir: Path, prompt: str, refs: list[tuple[str, Path]]) -> Path:
    out = shot_dir / "bundle"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    (out / "prompt.txt").write_text(prompt)
    for label, path in refs:
        shutil.copyfile(path, out / label)
    return out


def import_inbox(short_dir: Path, shot_id: str, cost: float, model: str, ledger: Ledger) -> list[str]:
    inbox, done = short_dir / "inbox", short_dir / "inbox" / "done"
    done.mkdir(parents=True, exist_ok=True)
    ids = []
    for video in sorted(inbox.glob("*.mp4")):
        # Move first: a file that is no longer in inbox/ can never be filed or charged twice.
        moved = done / video.name
        shutil.move(video, moved)
        tid = file_take(short_dir / "shots" / shot_id, moved,
                        {"model": model, "cost": cost, "backend": "manual", "source": video.name})
        ledger.add(shot_id, tid, model, cost)
        ids.append(tid)
    return ids
