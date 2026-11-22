"""Turns liked-turn ratings (design-data/turn-ratings.jsonl) into a KTO training set for the 4U box: TRL KTOTrainer's
unpaired format {prompt, completion, label} (huggingface.co/docs/trl/kto_trainer). TRL truncates from the right,
which would cut the reply being trained on, so long prompts lose their oldest "Recent events" lines here instead.
Also prints the desirable/undesirable weights that put the weighted ratio in TRL's advised 1:1 to 4:3.

    python -m tools.ratings_export out.jsonl [--max-tokens 6000]
"""

import argparse
import json
from pathlib import Path

from narrator import ratings

CHARS_PER_TOKEN = 4  # the same rough estimate server/narration.py budgets with


def trim(user: str, budget_chars: int) -> str:
    """Drops the oldest lines of the "Recent events:" block until the prompt fits; never touches the rest."""
    lines = user.split("\n")
    if "Recent events:" not in lines:
        return user
    start = lines.index("Recent events:") + 1
    end = start
    while end < len(lines) and lines[end] and not lines[end].endswith(":"):
        end += 1
    while len("\n".join(lines)) > budget_chars and end > start + 1:
        del lines[start]
        end -= 1
    return "\n".join(lines)


def weights(likes: int, dislikes: int) -> tuple[float, float]:
    """(desirable_weight, undesirable_weight) so likes*dw : dislikes*uw lands in 1:1 to 4:3."""
    if not likes or not dislikes:
        return 1.0, 1.0
    if likes > dislikes * 4 / 3:
        return round(dislikes * 4 / 3 / likes, 3), 1.0
    if likes < dislikes:
        return 1.0, round(likes / dislikes, 3)
    return 1.0, 1.0


def export(rows: list[dict], system: str, max_tokens: int) -> list[dict]:
    out = []
    for r in rows:
        if not r.get("prompt") or not r.get("narration"):
            continue
        budget = max_tokens * CHARS_PER_TOKEN - len(system) - len(r["narration"])
        out.append({"prompt": [{"role": "system", "content": system},
                               {"role": "user", "content": trim(r["prompt"], max(budget, 0))}],
                    "completion": [{"role": "assistant", "content": r["narration"]}],
                    "label": bool(r["like"])})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--max-tokens", type=int, default=6000)
    args = ap.parse_args()
    from server.__main__ import build_system_prompt
    rows = export(ratings._read(), build_system_prompt(), args.max_tokens)
    Path(args.out).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    likes = sum(r["label"] for r in rows)
    dw, uw = weights(likes, len(rows) - likes)
    print(f"{len(rows)} rows: {likes} liked, {len(rows) - likes} disliked -> desirable_weight={dw} undesirable_weight={uw}")


if __name__ == "__main__":
    main()
