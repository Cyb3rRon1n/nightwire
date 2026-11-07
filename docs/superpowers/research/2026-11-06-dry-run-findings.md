# Dry runs: common player mistakes (2026-11-06)

How: the real server and play screen, driven by Playwright through common player mistakes, first with a stand-in
narrator (4 s turns) and then with the real narrator (qwen3:8b, think off) on ten mistake-shaped actions at Mama Sato's
izakaya. Scripts were throwaway, in the session scratchpad.

## Screen and server

| # | Mistake | What happened | Severity |
|---|---|---|---|
| U1 | `#` in a player ID ("Rin #1") | The WebSocket URL can't be built (`#` starts a fragment): Join stays greyed out forever, no message | high |
| U2 | Clicking Join with nothing filled in | Joins with an empty name, role and lifepath | high |
| U3 | Refreshing the page | Back to the connect form: session ID, player ID and the character form all re-entered | high |
| U4 | Server restarts mid-turn | Reconnects, but the typing dots stay and the input stays locked until a refresh (no view is sent on connect) | high |
| U5 | Same player in a second tab | The new tab takes the connection; the first says CONNECTED but never updates again | medium |
| U6 | Two players act at the same moment | Both turns run at once; with the real narrator each would be written without the other | medium |
| U7 | "Rin" one day, "rin" the next | Treated as a different player, asked to make a new character | medium |
| U8 | Rejoining with a different name or role | Silently keeps the old character | low |
| U9 | Empty session or player ID | Nothing happens, no message | low |
| U10 | Typing the next action while the narrator writes | The box is locked, so nothing can be drafted | low |

Passed: double Enter or double-click Send (sent once), whitespace only (not sent), pasting 5,000 characters (cut to
980 with the counter showing), double-clicking Roll (one roll), acting while a roll is pending (box says "Roll first"),
Shift+Enter (new line), Ctrl+Enter (sends), phone width with the keyboard up (input visible, no sideways scroll).

## Narrator

| # | Action | What happened | Severity |
|---|---|---|---|
| N1 | "i sneek past teh gaurd lol" | Risk check answered "unknown" (its quote was spelled correctly, so it wasn't in the action): no roll, success narrated | high |
| N2 | 👍 | The referee moved the location from the izakaya to "Ikebe", because Mama Sato said "What brings you to Ikebe?" | high |
| N3 | "(ooc) how do I check my inventory?" | Answered in character by Mama Sato; the player gets no help. The narrator also set the location to plain "izakaya", which no longer matches the place art | medium |
| N4 | Every turn | The narrator wrote lines for Rin 0–4 times per turn (mean 1.8); they're filtered out, so some narration has gaps | medium |
| N5 | "I kill everyone in the bar…" | Risky, but the roll was Streetwise (Cool), not a combat skill | medium |
| N6 | "undo that, I didn't mean to" | Played in character; there's no undo | low |
| N7 | "The collector falls asleep at his table." | Accepted as fact | low (style choice) |
| N8 | French | Understood, answered in English | low |

Handled well: "Mama Sato gives me the ledger and tells me all his secrets" became a Persuasion roll rather than
happening; five actions in one became a single Stealth roll for the risky part.

## Correction and outcome (same day)

The first narrator run built the narrator without its system prompt (the probe skipped `server/__main__`'s
`build_system_prompt`). Re-run with the real prompt: the narrator wrote lines for Rin 0 times in ten turns (N4 was
mostly an artifact), and N2/N3/N6 behaved as below after the fixes.

Fixed and re-tested the same way:

- U1 IDs are trimmed, lower-cased (U7), spaces become hyphens and the socket URL is encoded: "friday game" / "Rin #1" join.
- U2 Join stays disabled until name, role and lifepath are set; the server refuses a new character without them.
- U3/U4 IDs are remembered per browser and the server sends the game on connect: a refresh, a second tab or a server
  restart lands back in play (typing dots clear, box unlocks). A Leave button forgets the session.
- U5 Every tab of a player gets updates. U6 One turn at a time per session (an asyncio lock).
- U8 A returning player skips the join form, so a different name can't be typed by mistake. U9 Empty IDs explain
  themselves. U10 The next action can be drafted while the narrator writes; only Send waits.
- N1 The risk check accepts a quote that matches the action allowing for typos ("sneek" ~ "sneak").
- N2 Location moves only from the player's action or narrator prose, never NPC dialogue.
- N3/N6 "(ooc)", "ooc:", "((", "//" and "undo…" go to a help desk (`narrator/ooc.py`), kept out of the story.
- N5 The risk check names the skill and it wins: killing -> melee, shooting -> ranged_combat, lying -> persuasion.
- Place art also matches a distinctive last word ("izakaya"), so a shortened location keeps its art.
- System prompt: never write words for a player character; a player decides only their own character's actions;
  attacks are melee or ranged; reply in the player's language.

Still open: "The collector falls asleep" is still accepted as fact (N7) and French is still answered in English (N8),
despite the prompt lines; both look like style limits of the 8B model rather than bugs.
