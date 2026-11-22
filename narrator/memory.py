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


_LETTERS = r"[a-z0-9āēīōū]+"
_STOP = {"them", "they", "their", "that", "this", "with", "what", "from", "have", "about", "into", "your", "when"}
# Words that don't tell two people apart: honorifics and descriptions ("Old Man Hara", "Mama Sato").
_TITLES = {"mama", "papa", "old", "the", "uncle", "auntie", "doc", "captain", "man", "woman", "boss", "big", "little",
           "young", "san", "chan", "kun", "sama"}


def _words(text: str) -> set[str]:
    return set(re.findall(_LETTERS, text.lower()))


def _names(name: str) -> set[str]:
    return {w for w in _words(name) if len(w) >= 3 and w not in _TITLES}


def canonical(session: Session, name: str) -> str:
    """One key per person: an existing NPC, a world NPC or a phone contact whose name this is, or the only one it is
    a word of ("Sato" -> "Mama Sato"; "Mama" -> "Mama Sato" only if no other Mama is known). Else the name as given."""
    from narrator.world import kuroshio  # lazy: world loads TOML
    pool = {*session.npc_memory, *(n.name for n in kuroshio().npcs),
            *(c["name"] for p in session.phone.values() for c in p.get("contacts", {}).values())}
    low = " ".join(_words(name))
    exact = [c for c in pool if " ".join(_words(c)) == low]
    if exact:
        return exact[0]
    words = _names(name) or _words(name)
    if not words:
        return name
    hits = [c for c in pool if words <= _words(c)]
    return hits[0] if len(hits) == 1 else name


def fact(item: str | dict) -> dict:
    """A stored fact; old saves kept plain strings."""
    return item if isinstance(item, dict) else {"text": item, "turn": 0, "last_used": 0, "weight": PLAIN}


def _score(f: dict, now: int, action_words: set[str]) -> float:
    relevant = any(len(w) >= 4 and w not in _STOP for w in _words(f["text"]) & action_words)
    return DECAY ** max(0, now - f["last_used"]) + f["weight"] / ENGINE + relevant


def remember(session: Session, name: str, text: str, weight: int | None = None) -> list[dict]:
    """Adds a fact (moving the NPC to the newest end); when full, the lowest-scored fact goes, not the oldest."""
    if weight is None:
        players = {w for c in session.characters.values() for w in _words(c.name)}
        weight = NOTABLE if _words(text) & (_NOTABLE | players) else PLAIN
    now, name = _player_turns(session), canonical(session, name)
    facts = [fact(f) for f in session.npc_memory.pop(name, [])]
    facts = [f for f in facts if f["text"] != text]
    facts.append({"text": text, "turn": now, "last_used": now, "weight": weight})
    while len(facts) > MAX_FACTS:
        facts.remove(min(facts, key=lambda f: (_score(f, now, set()), f["turn"])))
    session.npc_memory[name] = facts
    while len(session.npc_memory) > MAX_NPCS:
        del session.npc_memory[next(iter(session.npc_memory))]
    return facts


def _mentioned(name: str, text: str, others: list[str]) -> bool:
    """The full name, or a word of it no other known person shares ("Sato", never "Mama"), as whole words."""
    low = f" {' '.join(re.findall(_LETTERS, text.lower()))} "
    full = " ".join(re.findall(_LETTERS, name.lower()))
    if not full:
        return False
    shared = {w for o in others if o != name for w in _names(o)}
    return f" {full} " in low or any(f" {w} " in low for w in _names(name) - shared)


def recall_block(session: Session, action: str) -> str:
    """'What X remembers: ...' for up to 3 people in the scene or named in the action; showing a fact refreshes it."""
    now, words = _player_turns(session), _words(action)
    keys = list(session.npc_memory)
    here = [n for n in keys
            if any(_mentioned(n, p, keys) for p in session.present) or _mentioned(n, action, keys)]
    lines = []
    for name in here[-SHOWN_NPCS:]:
        facts = session.npc_memory[name] = [fact(f) for f in session.npc_memory[name]]
        top = sorted(facts, key=lambda f: _score(f, now, words), reverse=True)[:SHOWN_FACTS]
        for f in top:
            f["last_used"] = now
        lines.append(f"What {name} remembers: {'; '.join(f['text'] for f in top)}.")
    return "\n".join(lines)
