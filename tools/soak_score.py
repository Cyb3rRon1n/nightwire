"""Narrator scorecard: scores soak files (design-data/soak/*.jsonl) with no model calls, so every change and the
bigger model on the 4U box are measured, not guessed. Research pass 2 (2026-11-22): repetition, the narrator deciding
for the player, state, forgetting (D&D dialog challenge, arXiv:2210.07109; LoCoMo, arXiv:2402.17753).

    python -m tools.soak_score design-data/soak/A.jsonl design-data/soak/B.jsonl
"""

import json
import re
import sys
from pathlib import Path

_RUN = 8
_SPEECH = re.compile(r"^([^:/]{1,30}): (.+)$")
# The narrator speaking or choosing for "you" (heuristic: a verb the player's own action didn't use).
_AGENCY = re.compile(r"\byou (say|said|tell|told|ask|asked|reply|replied|answer|answered|agree|agreed|decide|decided|"
                     r"promise|promised|nod|nodded|shrug|shrugged|smile|smiled|grin|grinned|laugh|laughed)\b", re.I)


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def _runs(words: list[str]) -> set[tuple]:
    return {tuple(words[i:i + _RUN]) for i in range(len(words) - _RUN + 1)}


def score(path: Path) -> dict:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    rows = [r for r in rows if "turn" in r]
    seen: set[tuple] = set()
    repeated_runs = agency = empty = 0
    openings, speech = [], 0
    for r in rows:
        parts = [p.strip() for p in r.get("narration", "").split(" / ") if p.strip()]
        ooc = any(n.startswith("[ooc") for n in r.get("notes", []))  # "undo that" is answered out of character
        if not parts and "text_to" not in r and not ooc:
            empty += 1
        runs = set().union(*(_runs(_words(p)) for p in parts)) if parts else set()
        repeated_runs += len(runs & seen)
        seen |= runs
        action_verbs = set(_words(r["action"]))
        for p in parts:
            m = _SPEECH.match(p)
            if m:
                speech += 1
                openings.append(" ".join(_words(m.group(2))[:3]))
            else:
                agency += sum(v.lower() not in action_verbs for v in _AGENCY.findall(p))
    notes = [n for r in rows for n in r.get("notes", [])]
    return {
        "turns": len(rows),
        "errors": sum("error" in r for r in rows),
        "empty_turns": empty,
        "median_seconds": sorted(r.get("seconds", 0) for r in rows)[len(rows) // 2] if rows else 0,
        "repeated_8word_runs": repeated_runs,  # what got past the repeat cut, across turns
        "repeated_openings": sum(bool(r.get("repeated_opening")) for r in rows),
        "npc_lines": speech,
        "npc_distinct_openings": round(len(set(openings)) / len(openings), 2) if openings else None,
        "acted_for_player": agency,
        "sample_lines_cut": sum(n.startswith("[sample line cut") for n in notes),
        "referee_ignored": sum(n.startswith("[referee") and "ignored" in n for n in notes),
        "promises": sum(n.startswith("[promise") for n in notes),
    }


def main(paths: list[str]) -> None:
    scores = {Path(p).stem: score(Path(p)) for p in paths}
    keys = list(next(iter(scores.values())))
    print(f"{'':24}" + "".join(f"{name:>18}" for name in scores))
    for k in keys:
        print(f"{k:24}" + "".join(f"{str(s[k]):>18}" for s in scores.values()))


if __name__ == "__main__":
    main(sys.argv[1:])
