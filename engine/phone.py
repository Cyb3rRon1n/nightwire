"""A player's phone: contacts with role + trust, threads, and the timing rules (docs/superpowers/specs/
2026-11-06-messenger-play-screen-design.md, "Phone"). Plain dicts so Session saves them as JSON. No model calls."""

from engine.session import Session

ROLE_BASE = {"partner": 0, "family": 1, "friend": 1, "crew": 1, "creditor": 1, "boss": 2, "fixer": 2,
             "informant": 2, "rival": 3, "enemy": 4, "stranger": 3}
START_TRUST = {"enemy": 0.0, "family": 3.0, "partner": 3.0}
UNPROMPTED_GAP = 4


def phone_of(session: Session, player_id: str) -> dict:
    return session.phone.setdefault(player_id, {"turn": 0, "last_unprompted": -99, "contacts": {}, "threads": {}})


def add_contact(session, player_id, name, role="stranger", *, pace=0, close=False) -> dict:
    p = phone_of(session, player_id)
    if name not in p["contacts"]:
        p["contacts"][name] = {"name": name, "role": role, "trust": START_TRUST.get(role, 2.0), "pace": pace,
                               "close": close, "knows": [], "cold_until": -1}
        p["threads"].setdefault(name, [])
    return p["contacts"][name]


def delay(contact: dict) -> int:
    raw = ROLE_BASE[contact["role"]] + (5 - int(contact["trust"])) + contact["pace"]
    return max(0, min(6, raw))


def tone(contact: dict, turn: int) -> str:
    if turn < contact["cold_until"]:
        return "guarded"
    return {5: "warm", 4: "warm", 3: "friendly", 2: "curt", 1: "guarded"}.get(int(contact["trust"]), "hostile")


def change_trust(contact: dict, delta: float) -> None:
    trust = contact["trust"] + delta
    if 0 < delta < 1 and trust > 3:
        trust = max(contact["trust"], 3.0)  # small gains don't climb past friendly
    contact["trust"] = max(0.0, min(5.0, trust))


def post(session, player_id, contact_name, sender, text, deliver_at) -> dict:
    p = phone_of(session, player_id)
    msg = {"sender": sender, "text": text, "turn": p["turn"], "deliver_at": deliver_at, "read": sender == "me"}
    p["threads"].setdefault(contact_name, []).append(msg)
    return msg


def advance(session, player_id) -> list[dict]:
    p = phone_of(session, player_id)
    p["turn"] += 1
    return [m for msgs in p["threads"].values() for m in msgs if m["deliver_at"] == p["turn"] and m["text"] is None]


def may_text_first(session, player_id) -> bool:
    p = phone_of(session, player_id)
    return p["turn"] - p["last_unprompted"] >= UNPROMPTED_GAP


def mark_unprompted(session, player_id) -> None:
    phone_of(session, player_id)["last_unprompted"] = phone_of(session, player_id)["turn"]


def unread(session, player_id) -> dict[str, int]:
    p = phone_of(session, player_id)
    counts = {name: sum(1 for m in msgs if not m["read"] and m["deliver_at"] <= p["turn"] and m["text"])
              for name, msgs in p["threads"].items()}
    return {k: v for k, v in counts.items() if v}
