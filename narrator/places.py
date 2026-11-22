"""Places that grow: heat (Blades in the Dark), warmth, and marks the player left, kept per place and told back to the
narrator in one line (Emily Short: say the cause back, players forget it). No model calls.
See docs/superpowers/specs/2026-11-22-places-gossip-design.md, part 2."""

from engine.session import Session
from narrator.cast import _player_turns
from narrator.world import _where, kuroshio

HEAT_MAX, LOCKDOWN_AFTER, HEAT_COOL_EVERY = 9, 5, 5
WARMTH_MAX, WARMTH_DRIFT_EVERY = 3, 30
MARKS_MAX, MARK_LIFE = 3, 30
FIGHT, COMBAT, HURT = 2, 4, 2
_FIGHT_SKILLS = {"melee", "ranged_combat"}
_HEAT_WORDS = ((9, "locked down"), (6, "tense"), (3, "wary"), (0, "calm"))
_WARMTH_WORDS = {-3: "hostile", -2: "hostile", -1: "cool", 0: "neutral", 1: "friendly", 2: "friendly", 3: "welcoming"}


def key(session: Session) -> str | None:
    """The place the player is at: its own name, else the district, else the location as written."""
    place, district = _where(kuroshio(), session.location)
    return place.name if place else (session.location or (district.name if district else None))


def _state(session: Session, k: str) -> dict:
    return session.places.setdefault(k, {"heat": 0, "warmth": 0, "marks": [], "last_visit": _player_turns(session),
                                         "warmed": -1})


def arrive(session: Session) -> None:
    """Called each turn: cooling and drift for the time away, and a mark seen again stays for good."""
    k = key(session)
    if not k:
        return
    now, s = _player_turns(session), _state(session, k)
    away = now - s["last_visit"]
    if away > 1:
        s["heat"] = max(0, s["heat"] - away // HEAT_COOL_EVERY)
        drift = min(abs(s["warmth"]), away // WARMTH_DRIFT_EVERY)
        s["warmth"] -= drift if s["warmth"] > 0 else -drift
        for m in s["marks"]:
            if not m["permanent"] and now - m["turn"] <= MARK_LIFE:
                m["permanent"] = True  # came back while it was still there
    s["marks"] = [m for m in s["marks"] if m["permanent"] or now - m["turn"] <= MARK_LIFE]
    s["last_visit"] = now


def warm(session: Session, step: int) -> None:
    """One step of warmth per turn at the current place, up or down."""
    k = key(session)
    if not k or not step:
        return
    s, now = _state(session, k), _player_turns(session)
    if s["warmed"] == now:
        return
    s["warmed"] = now
    s["warmth"] = max(-WARMTH_MAX, min(WARMTH_MAX, s["warmth"] + (1 if step > 0 else -1)))


def mark(session: Session, text: str) -> None:
    k = key(session)
    if not k or not text:
        return
    s = _state(session, k)
    if any(m["text"].lower() == text.lower() for m in s["marks"]):
        return
    s["marks"].append({"text": text, "turn": _player_turns(session), "permanent": False})
    while len(s["marks"]) > MARKS_MAX:
        temp = [m for m in s["marks"] if not m["permanent"]]
        s["marks"].remove((temp or s["marks"])[0])


def heat(session: Session, rolls: list[dict], hurt: bool) -> bool:
    """Raises the current place's heat for violence this turn; True when it locks down (then cools to 5)."""
    k = key(session)
    if not k:
        return False
    fight = any(r.get("skill") in _FIGHT_SKILLS for r in rolls)
    rise = (COMBAT if session.in_combat else FIGHT if fight else 0) + (HURT if hurt and (fight or session.in_combat)
                                                                          else 0)
    if not rise:
        return False
    s = _state(session, k)
    s["heat"] = min(HEAT_MAX, s["heat"] + rise)
    warm(session, -1)
    if s["heat"] >= HEAT_MAX:
        s["heat"] = LOCKDOWN_AFTER
        return True
    return False


def mood(s: dict) -> str:
    heat_word = next(w for floor, w in _HEAT_WORDS if s["heat"] >= floor)
    warmth_word = _WARMTH_WORDS[s["warmth"]]
    parts = [heat_word] if heat_word != "calm" else []
    if warmth_word != "neutral":
        parts.append(warmth_word)
    return " and ".join(parts) or "calm"


def line(session: Session, player_name: str) -> str:
    """"This place: the window is still boarded (Rin left it 12 turns ago); people here are wary." or ""."""
    k = key(session)
    s = session.places.get(k or "")
    if not s or (not s["marks"] and not s["heat"] and not s["warmth"]):
        return ""
    now = _player_turns(session)
    bits = [f"{m['text']} ({player_name}, {now - m['turn']} turns ago)" for m in s["marks"]]
    return f"This place: {'; '.join([*bits, f'people here are {mood(s)}'])}."


def view(session: Session) -> dict | None:
    k = key(session)
    s = session.places.get(k or "")
    if not s:
        return None
    return {"place": k, "mood": mood(s), "mark": s["marks"][-1]["text"] if s["marks"] else None}
