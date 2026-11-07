"""Phone replies: one structured judge call writes an NPC's text message."""
import re

_SCHEMA = {"type": "object", "properties": {"reply": {"type": "string", "maxLength": 240}},
           "required": ["reply"], "additionalProperties": False}
_FALLBACK = {"creditor": "Payment's due.", "fixer": "Busy. Later."}


async def write_reply(client, contact: dict, tone: str, thread: list[dict], character_name: str) -> str:
    name = contact["name"]
    system = (f"You write one text message from {name} to {character_name} in a cyberpunk RPG. "
              f"Role: {contact['role']}. Tone: {tone}. Under 2 sentences, no emoji spam, "
              f"never act for {character_name}. You know only: {contact['knows'][-6:]}.")
    lines = [f"{character_name if m['sender'] == 'me' else m['sender']}: {m['text']}"
             for m in thread if m.get("text")][-6:]
    user = "\n".join(lines) or f"Write the first text of a new conversation with {character_name}."
    try:
        out = await client.judge([{"role": "system", "content": system},
                                  {"role": "user", "content": user}], _SCHEMA)
        reply = out["reply"].strip()
        for prefix in (name, name.split()[0]):  # qwen sometimes echoes "Saeko Kirigaya: ..."
            m = re.match(rf"{re.escape(prefix)}\s*:\s*", reply, re.I)
            if m:
                reply = reply[m.end():].strip()
                break
    except Exception:  # a failed reply must never break the game
        reply = ""
    return reply or _FALLBACK.get(contact["role"], "Can't talk now.")
