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
_DICE = re.compile(r"^\S+ rolls ")  # the engine's own dice line, the same words every roll
_SPEECH = re.compile(r"^([^:/]{1,30}): (.+)$")
# The narrator speaking or choosing for "you" (heuristic: a verb the player's own action didn't use).
_AGENCY = re.compile(r"\byou (say|said|tell|told|ask|asked|reply|replied|answer|answered|agree|agreed|decide|decided|"
                     r"promise|promised|nod|nodded|shrug|shrugged|smile|smiled|grin|grinned|laugh|laughed)\b", re.I)


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def _runs(words: list[str]) -> set[tuple]:
    return {tuple(words[i:i + _RUN]) for i in range(len(words) - _RUN + 1)}


def _remembers(m: dict, name: str, *words: str) -> bool:
    return any(all(w in (f["text"] if isinstance(f, dict) else f).lower() for w in words) for f in m.get(name, []))


# LoCoMo-style memory probes (Maharana et al., arXiv:2402.17753): "does X still know Y at the end?", checked on the
# end state the soak saves, tied to moments in tools/soak_test.py ACTIONS. None = the soak predates that state.
PROBES = {
    # turn 11: "I tell him I already paid this week." -> the collector should remember it.
    "collector_remembers_paid": lambda s: any(_remembers(s["npc_memory"], n, "paid") for n in s["npc_memory"]),
    # turn 15 promises Old Hara tea; turn 16 "undo that" is answered "there is no undo" (narrator/ooc.py), so the
    # promise must still be there at the end, open or in the journal.
    "tea_promise_survives_undo": lambda s: any("tea" in p["what"].lower() for p in s["promises"])
                                           or any("tea" in j["text"].lower() for j in s["journal"]),
    # turns 25-26: punch the guy, then help him up -> one person, met twice.
    "punched_guy_became_someone": lambda s: any(p["weight"] >= 2 for p in s["people"].values()),
    # the punch made a deed that someone who wasn't there has heard.
    "punch_spread": lambda s: any(not k["seen"] for d in s["deeds"] for k in d["knows"].values()),
    # the punch left Ikebe Low less than calm, or marked.
    "ikebe_remembers": lambda s: any(
        "ikebe" in k.lower() and (v["heat"] or v["warmth"] or v["marks"]) for k, v in s["places"].items()),
    # quiet stretches (walk home, sleep, wake) got at least one director event.
    "director_fired": lambda s: bool(s["events_used"]),
}


def probes(summary: dict) -> dict:
    out = {}
    for name, check in PROBES.items():
        try:
            out[name] = bool(check(summary))
        except (KeyError, TypeError):
            out[name] = None  # the soak predates this state
    return out


def score(path: Path, summary: dict | None = None) -> dict:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    summary = summary or next((r["summary"] for r in rows if "summary" in r), {})  # soak_test passes its own
    memory = summary.get("npc_memory", {})
    facts = [f for fs in memory.values() for f in fs if isinstance(f, dict)]
    rows = [r for r in rows if "turn" in r]
    seen: set[tuple] = set()
    repeated_runs = agency = empty = 0
    openings, speech = [], 0
    for r in rows:
        parts = [p.strip() for p in r.get("narration", "").split(" / ") if p.strip() and not _DICE.match(p.strip())]
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
        "director_events": sum(n.startswith("[director") and "breather" not in n for n in notes),
        "npc_facts": len(facts),
        "npc_facts_weighted": sum(f.get("weight") == 3 for f in facts),
        **{f"probe_{k}": v for k, v in probes(summary).items()},
        "breathers": sum(n == "[director: breather]" for n in notes),
    }


def main(paths: list[str]) -> None:
    scores = {Path(p).stem: score(Path(p)) for p in paths}
    keys = list(next(iter(scores.values())))
    print(f"{'':24}" + "".join(f"{name:>18}" for name in scores))
    for k in keys:
        print(f"{k:24}" + "".join(f"{str(s[k]):>18}" for s in scores.values()))


if __name__ == "__main__":
    main(sys.argv[1:])
