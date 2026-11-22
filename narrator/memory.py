"""NPC memory that keeps what matters: facts ranked by recency + importance + relevance (Generative Agents, UIST '23,
with rules in place of model calls), only the people in the scene shown, late in the prompt (Lost in the Middle).
See docs/superpowers/specs/2026-11-22-npc-memory-design.md."""

import re

from engine.session import Session
from narrator.cast import _player_turns

MAX_NPCS, MAX_FACTS = 50, 12
SHOWN_NPCS, SHOWN_FACTS = 3, 3
DECAY = 0.9
ENGINE, NOTABLE, PLAIN = 3, 2, 1
_NOTABLE = {"owe", "owes", "owed", "promise", "promised", "lied", "lie", "saved", "betrayed", "paid", "killed",
            "helped", "family"}


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-zō']+", text.lower()))


def fact(item: str | dict) -> dict:
    """A stored fact; old saves kept plain strings."""
    return item if isinstance(item, dict) else {"text": item, "turn": 0, "last_used": 0, "weight": PLAIN}


def _score(f: dict, now: int, action_words: set[str]) -> float:
    relevant = any(len(w) >= 4 for w in _words(f["text"]) & action_words)
    return DECAY ** max(0, now - f["last_used"]) + f["weight"] / ENGINE + relevant


def remember(session: Session, name: str, text: str, weight: int | None = None) -> list[dict]:
    """Adds a fact (moving the NPC to the newest end); when full, the lowest-scored fact goes, not the oldest."""
    if weight is None:
        players = {w for c in session.characters.values() for w in _words(c.name)}
        weight = NOTABLE if _words(text) & (_NOTABLE | players) else PLAIN
    now = _player_turns(session)
    facts = [fact(f) for f in session.npc_memory.pop(name, [])]
    facts = [f for f in facts if f["text"] != text]
    facts.append({"text": text, "turn": now, "last_used": now, "weight": weight})
    while len(facts) > MAX_FACTS:
        facts.remove(min(facts, key=lambda f: (_score(f, now, set()), f["turn"])))
    session.npc_memory[name] = facts
    while len(session.npc_memory) > MAX_NPCS:
        del session.npc_memory[next(iter(session.npc_memory))]
    return facts


_TITLES = {"mama", "papa", "old", "the", "uncle", "auntie", "doc", "captain"}


def _mentioned(name: str, text: str) -> bool:
    """The full name, or a word of it that isn't a title ("Sato", not "Mama"), as whole words."""
    low = f" {' '.join(re.findall(r'[a-zō]+', text.lower()))} "
    full = " ".join(re.findall(r"[a-zō]+", name.lower()))
    return bool(full) and (f" {full} " in low or any(f" {w} " in low for w in full.split() if len(w) >= 3
                                                     and w not in _TITLES))


def recall_block(session: Session, action: str) -> str:
    """'What X remembers: ...' for up to 3 people in the scene or named in the action; showing a fact refreshes it."""
    now, words = _player_turns(session), _words(action)
    here = [n for n in session.npc_memory
            if any(_mentioned(n, p) for p in session.present) or _mentioned(n, action)]
    lines = []
    for name in here[-SHOWN_NPCS:]:
        facts = session.npc_memory[name] = [fact(f) for f in session.npc_memory[name]]
        top = sorted(facts, key=lambda f: _score(f, now, words), reverse=True)[:SHOWN_FACTS]
        for f in top:
            f["last_used"] = now
        lines.append(f"What {name} remembers: {'; '.join(f['text'] for f in top)}.")
    return "\n".join(lines)
