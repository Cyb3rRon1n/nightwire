"""Out-of-character messages: "(ooc) how do I check my inventory?", "undo that".

Dry run 2026-11-06: these went to the narrator, so Mama Sato answered a question about the screen in character and
"undo" was played as dialogue. They now skip the story and get a short, plain answer from a help desk that knows the
screen and the rules. Neither the question nor the answer reaches the narrator (both are bracketed log lines).
"""

import re

_MARKER = re.compile(r"^\s*(\(\s*ooc\b|\[\s*ooc\b|ooc\s*[:\-]|\(\(|//|undo\b)", re.IGNORECASE)

GUIDE = """Nightwire screen and rules, for answering players' out-of-character questions:
- Left: the Status panel holds the character sheet: attributes, skills (spend skill points with +), condition (health,
  armor), chrome and humanity (or selfhood for a tsukumogami), installments owed and the repo clock, inventory, and
  objectives. Ctrl+K (Cmd+K on a Mac) folds it away and back. On a phone it is the Status tab.
- Right: the World panel shows the scene and the party. Middle: the story and the action box.
- Do / Say / Think set how your line is phrased. Enter sends, Shift+Enter adds a line. While the narrator writes you
  can draft your next action; Send waits.
- Risky actions open a roll card: press Roll. Overclock buttons spend humanity for a bonus.
- Header: Scene art on/off, Gallery (the session's scene images), Immersive view, Reset layout, Leave (forget this
  session in this browser).
- Rolls: 1d10 + attribute modifier + skill vs a difficulty (easy 6, moderate 9, hard 12, extreme 15).
- There is no undo: what happened stays in the story. Describe what your character does next instead.
- Chrome costs humanity and is paid in installments; miss them and Hoshikawa's torite come for it."""

_FALLBACK = ("Out of character: your sheet, inventory and objectives are in the Status panel on the left (Ctrl+K). "
             "There is no undo; just describe what your character does next.")
SCHEMA = {"type": "object", "properties": {"answer": {"type": "string", "maxLength": 400}},
          "required": ["answer"], "additionalProperties": False}


def is_ooc(text: str) -> bool:
    return bool(_MARKER.match(text)) and not re.match(r"^\s*undo\s+the\b", text, re.IGNORECASE)


async def answer_ooc(client, text: str) -> str:
    system = (f"You are the help desk of a tabletop RPG app, answering a player's out-of-character question in one to "
              f"three plain sentences. Use only this guide; if it doesn't say, say you don't know.\n\n{GUIDE}")
    try:
        answer = await client.judge([{"role": "system", "content": system}, {"role": "user", "content": text}], SCHEMA)
        return " ".join(str(answer.get("answer", "")).split()) or _FALLBACK
    except Exception:  # the help desk must never break the game
        return _FALLBACK
