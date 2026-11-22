"""Unfinished business: promises, debts and favours that come back, and the player's journal of what is over.
See docs/superpowers/specs/2026-11-22-unfinished-business-design.md."""

from engine.session import Session
from narrator import memory
from narrator.cast import _player_turns

MAX_OPEN = 6
JOURNAL_MAX = 30
REMIND_AFTER = 8
CALL_IN_AFTER = 16
_SHOWN = 2
_WHO_MAX, _WHAT_MAX = 30, 80


def _key(text: str) -> str:
    return " ".join("".join(ch if ch.isalnum() or ch.isspace() else " " for ch in text.lower()).split())


def note(session: Session, text: str, kind: str) -> None:
    session.journal = [*session.journal, {"text": text, "kind": kind, "turn": _player_turns(session)}][-JOURNAL_MAX:]


def _cap(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0]


def split(answer: str) -> tuple[str, str] | None:
    """ "Mama Sato: bring back her nephew Kenta" -> ("Mama Sato", "bring back her nephew Kenta")."""
    who, sep, what = answer.partition(":")
    who, what = _cap(" ".join(who.split()), _WHO_MAX), _cap(" ".join(what.split()), _WHAT_MAX)
    return (who, what) if sep and who and what else None


MAX_OBJECTIVES = 5


def add_lead(session: Session, lead: str) -> None:
    """A new objective; the oldest past 5 are journaled as set aside (referee leads and director events)."""
    if lead in session.active_objectives:
        return
    grown = [*session.active_objectives, lead]
    for dropped in grown[:-MAX_OBJECTIVES]:
        note(session, dropped, "set aside")
    session.active_objectives = grown[-MAX_OBJECTIVES:]


def record(session: Session, who: str, what: str) -> None:
    if any(_key(p["who"]) == _key(who) and _key(p["what"]) == _key(what) for p in session.promises):
        return
    grown = [*session.promises, {"who": who, "what": what, "turn": _player_turns(session), "called_in": False}]
    for dropped in grown[:-MAX_OPEN]:
        note(session, f"{dropped['who']}: {dropped['what']}", "set aside")
    session.promises = grown[-MAX_OPEN:]
    session.log.append(f"[promise: {who}: {what}]")


def _is(written: str, who: str) -> bool:
    a, b = _key(written), _key(who)
    return bool(a and b) and (a == b or a in b.split() or b in a.split())


def _find(session: Session, written: str) -> dict | None:
    """The full name, or one word that belongs to exactly one person owed (review 2026-11-22: "Mama" closed Sato's
    promise when Mama Kobayashi was owed too)."""
    exact = [p for p in session.promises if _key(p["who"]) == _key(written)]
    hits = exact or [p for p in session.promises if _is(written, p["who"])]
    return hits[0] if len({_key(p["who"]) for p in hits}) == 1 else None


def close(session: Session, written: str, kept: bool, name: str) -> None:
    """Closes the oldest open promise to that person; a broken one is heard about once."""
    p = _find(session, written)
    if p is None:
        return
    session.promises = [q for q in session.promises if q is not p]
    kind = "kept" if kept else "broken"
    session.log.append(f"[promise {kind}: {p['who']}: {p['what']}]")
    note(session, f"{p['who']}: {p['what']}", kind)
    memory.remember(session, p["who"], f"{name} {'kept' if kept else 'broke'} their word: {p['what']}", memory.ENGINE)
    if not kept:
        session.pending_world_events.append(f"{p['who']} remembers {name} broke their word: {p['what']}.")


def call_in(session: Session) -> None:
    """A promise open too long comes back once, as a world event (Blades in the Dark's entanglements)."""
    now = _player_turns(session)
    for p in session.promises:
        if not p["called_in"] and now - p["turn"] >= CALL_IN_AFTER:
            p["called_in"] = True
            session.pending_world_events.append(f"{p['who']} hasn't forgotten: {p['what']}.")
            note(session, f"{p['who']}: {p['what']}", "called in")


def business_line(session: Session) -> str:
    now = _player_turns(session)
    here = [p for p in session.promises if any(_is(n, p["who"]) for n in session.present)]
    if not here and session.promises and now - session.promises[0]["turn"] >= REMIND_AFTER:
        here = session.promises[:1]
    if not here:
        return ""
    entries = [f"{p['who']}: {p['what']} ({now - p['turn']} turns ago)" for p in here[-_SHOWN:]]
    return "Unfinished business: " + "; ".join(entries) + "."
