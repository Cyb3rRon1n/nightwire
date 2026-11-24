"""Places that grow: heat (Blades in the Dark), warmth, and marks the player left, kept per place and told back to the
narrator in one line (Emily Short: say the cause back, players forget it). No model calls.
See docs/superpowers/specs/2026-11-22-places-gossip-design.md, part 2."""

from engine.session import Session
from narrator.cast import _player_turns
from narrator.movement import known_place
from narrator.world import _where, kuroshio

HEAT_MAX, LOCKDOWN_AFTER, HEAT_COOL_EVERY = 9, 5, 5
WARMTH_MAX, WARMTH_DRIFT_EVERY = 3, 30
MARKS_MAX, MARK_LIFE = 3, 30
FIGHT, COMBAT, HURT = 2, 4, 2
_FIGHT_SKILLS = {"melee", "ranged_combat"}
_HEAT_WORDS = ((9, "locked down"), (6, "tense"), (3, "wary"), (0, "calm"))
_WARMTH_WORDS = {-3: "hostile", -2: "hostile", -1: "cool", 0: "neutral", 1: "friendly", 2: "friendly", 3: "welcoming"}


def key(session: Session) -> str | None:
    """One key per place however the location is written (review 2026-11-22: "the izakaya" split Mama Sato's
    izakaya's state): a world place, else a known place ("the izakaya" -> Mama Sato's izakaya), else the district,
    else the location in plain lower case."""
    if not session.location:
        return None
    place, district = _where(kuroshio(), session.location)
    if place:
        return place.name
    known = known_place(session.location)
    if known:
        return known
    return district.name if district else " ".join(session.location.lower().split())


def _state(session: Session, k: str) -> dict:
    now = _player_turns(session)
    s = session.places.setdefault(k, {"heat": 0, "warmth": 0, "marks": []})
    for field in ("cooled", "drifted"):
        s.setdefault(field, now)
    s.setdefault("warmed", -1)
    return s


def arrive(session: Session) -> None:
    """Called each player turn. Every place cools 1 heat per 5 turns since its last heat and drifts 1 warmth toward 0
    per 30 turns since its last change, whether or not the player is there (review 2026-11-22). A mark the player is
    still with 5+ turns later, or comes back to, has been seen again and stays for good; others fade after 30."""
    now, here = _player_turns(session), key(session)
    for k, s in session.places.items():
        s = _state(session, k)
        if now - s["cooled"] >= HEAT_COOL_EVERY:
            steps = (now - s["cooled"]) // HEAT_COOL_EVERY
            s["heat"], s["cooled"] = max(0, s["heat"] - steps), s["cooled"] + steps * HEAT_COOL_EVERY
        if now - s["drifted"] >= WARMTH_DRIFT_EVERY:
            s["drifted"] = now
            s["warmth"] -= (s["warmth"] > 0) - (s["warmth"] < 0)
        for m in s["marks"]:
            if k == here and not m["permanent"] and 5 <= now - m["turn"] <= MARK_LIFE:
                m["permanent"] = True
        s["marks"] = [m for m in s["marks"] if m["permanent"] or now - m["turn"] <= MARK_LIFE]


def warm(session: Session, step: int) -> None:
    """One step of warmth per turn at the current place, up or down."""
    k = key(session)
    if not k or not step:
        return
    s, now = _state(session, k), _player_turns(session)
    if s["warmed"] == now:
        return
    s["warmed"] = s["drifted"] = now
    s["warmth"] = max(-WARMTH_MAX, min(WARMTH_MAX, s["warmth"] + (1 if step > 0 else -1)))


def mark(session: Session, text: str) -> None:
    k = key(session)
    if not k or not text:
        return
    s = _state(session, k)
    if any(m["text"].lower() == text.lower() for m in s["marks"]):
        return
    s["marks"].append({"text": text, "turn": _player_turns(session), "permanent": False})
    session.log.append(f"[mark: {text}]")  # the night recap scores the turn
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
    s["heat"], s["cooled"] = min(HEAT_MAX, s["heat"] + rise), _player_turns(session)
    warm(session, -1)
    return s["heat"] >= HEAT_MAX


def cool_after_lockdown(session: Session) -> None:
    s = _state(session, key(session))
    s["heat"] = LOCKDOWN_AFTER


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
