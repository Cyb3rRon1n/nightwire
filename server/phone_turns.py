"""Sending a text and delivering replies on the contact's schedule. The words of a text never reach session.log."""

import re

from engine import phone
from narrator.phone_reply import write_reply

MAX_TEXT = 500


async def _fill(session, client, player_id, msg, contact_name) -> None:
    p = phone.phone_of(session, player_id)
    contact = p["contacts"][contact_name]
    msg["text"] = await write_reply(client, contact, phone.tone(contact, p["turn"]), p["threads"][contact_name],
                                    session.characters[player_id].name)


async def deliver_due(session, client, player_id) -> None:
    phone.advance(session, player_id)
    p = phone.phone_of(session, player_id)
    for name, msgs in p["threads"].items():
        for m in msgs:
            if m["text"] is None and m["deliver_at"] <= p["turn"]:
                await _fill(session, client, player_id, m, name)
    if phone.may_text_first(session, player_id):
        for name, c in p["contacts"].items():
            msgs = p["threads"].get(name, [])
            last = msgs[-1]["turn"] if msgs else 0
            if c["role"] in ("family", "partner") and c["trust"] >= 3 and last <= p["turn"] - 8:
                text = await write_reply(client, c, phone.tone(c, p["turn"]), [], session.characters[player_id].name)
                phone.post(session, player_id, name, name, text, p["turn"])
                phone.mark_unprompted(session, player_id)
                break


_WORK = re.compile(r"\b(work|job|jobs|gig|gigs|cash|money|pay|paid|eddies|yen)\b", re.I)


async def handle_text(session, client, player_id, message) -> None:
    p = phone.phone_of(session, player_id)
    contact = p["contacts"].get(message.get("to"))
    if contact is None:
        raise ValueError("not in your contacts")
    text = (message.get("text") or "").strip()
    if not text or len(text) > MAX_TEXT:
        raise ValueError(f"text must be 1-{MAX_TEXT} characters")
    name = contact["name"]
    phone.post(session, player_id, name, "me", text, p["turn"])
    contact["knows"] = (contact["knows"] + [text])[-20:]
    session.pending_world_events.append(f"{session.characters[player_id].name} quietly texts someone on their phone.")
    await deliver_due(session, client, player_id)
    if contact["role"] == "enemy" and contact["trust"] < 1:
        return
    d = phone.delay(contact)
    if contact["role"] == "fixer" and _WORK.search(text):
        d = min(d, 1)  # a fixer asked for work answers next turn (playthrough 2026-11-07: Jun took 6)
    msg = phone.post(session, player_id, name, name, None, p["turn"] + d)
    if d == 0:
        await _fill(session, client, player_id, msg, name)
