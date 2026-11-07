"""Soak test: a scripted 30-turn game through the real turn pipeline and narrator, to surface problems nobody typed yet.

    OLLAMA_HOST=http://192.168.10.19:11434 NIGHTWIRE_THINK=off python -m tools.soak_test [--turns 30]

Plays one character through walking, talking, risky moves, out-of-character questions, typos and an emoji, rolling
the dice automatically whenever the narrator asks. A few turns text a contact instead of acting (the phone). Images and voices are off (their backends are pointed at nothing),
so only the narrator uses the GPU: never run it while ComfyUI is rendering. Writes one JSON line per turn and a summary
to design-data/soak/<time>.jsonl (git-ignored).
"""

import argparse
import asyncio
import json
import os
import tempfile
import time
from pathlib import Path

from engine.character import CharacterSheet
from engine.phone import add_contact, phone_of, unread
from engine.persistence import JSONFileSessionStore
from engine.session import Session
from narrator.client import create_narrator_backend
from narrator.image_backend import create_image_backend
from narrator.place_art import location_art
from narrator.tts_backend import KokoroBackend
from server.__main__ import build_system_prompt
from server.narration import handle_action, narrate_roll, resolve_roll
from server.phone_turns import deliver_due, handle_text

ACTIONS = [
    "I step off the Ring Line at Ikebe Low and look around.",
    "I head to Mama Sato's izakaya.",
    "I ask Mama Sato what's good tonight.",
    "I order the eel and eat slowly.",
    ("text", "Mama Sato", "Thanks for the eel. Is the back booth free tomorrow?"),
    "(ooc) how do rolls work?",
    "I quietly slip behind the counter and look for the collector's ledger.",
    "I tell Mama Sato I was just looking for the bathroom.",
    "I ask about the debt collector in the corner.",
    "I walk over and sit at the collector's table.",
    "I tell him I already paid this week.",
    "I leave and walk to Old Hara's clinic.",
    "I ask Old Hara if he can look at my optics.",
    ("text", "Saeko Kirigaya", "Haven't seen Hara in weeks."),  # a lie: the player just visited his clinic
    "I thank him and promise to bring him tea tomorrow.",
    "undo that",
    "I go to the Kuroshio Docks to find work.",
    "I ask the dockworkers who's hiring.",
    ("text", "Jun Arakawa", "Got any paid work for me?"),
    "I climb a crane to get a look at the yard.",
    "I hack the yard's security camera.",
    "I head back toward Ikebe Low.",
    "i chek my phone for mesages",
    "I buy noodles from a street vendor.",
    "I punch the guy who bumps into me.",
    "I apologise and help him up.",
    "I go home to my room and sleep.",
    "I wake up and check the news.",
    "I take the Ring Line to Tenjō Heights.",
    "I try to talk my way past the doorman.",
    "I look out over the city.",
    "I head back down to the street.",
    "👍",
]


def _phone_messages(session, player_id) -> list[tuple[str, str]]:
    """Every delivered (sender, text) from a contact so far; the player's own texts are skipped."""
    p = phone_of(session, player_id)
    return [(m["sender"], m["text"]) for msgs in p["threads"].values() for m in msgs
            if m["text"] and m["sender"] != "me" and m["deliver_at"] <= p["turn"]]


def _new_lines(log: list[str], start: int) -> list[str]:
    return [line for line in log[start:] if not line.startswith(("[audio", "[image error", "[image prompt"))]


async def main(turns: int) -> Path:
    client = create_narrator_backend()
    client.system_prompt = build_system_prompt()
    os.environ.setdefault("FLUX_WORKER_URL", "http://127.0.0.1:9")  # images off
    images, tts = create_image_backend(), KokoroBackend(base_url="http://127.0.0.1:9")  # voices off
    store = JSONFileSessionStore(tempfile.mkdtemp())
    session = Session(session_id="soak")
    session.characters["rin"] = CharacterSheet(player_id="rin", name="Rin", role="netrunner", lifepath="streetkid",
                                               attributes={"body": 10, "reflexes": 11, "tech": 12, "cool": 10,
                                                           "intellect": 10, "presence": 10},
                                               skills={"hacking": 2, "stealth": 1, "perception": 1})
    add_contact(session, "rin", "Saeko Kirigaya", "creditor", pace=-1)  # as the join does
    add_contact(session, "rin", "Jun Arakawa", "fixer")
    out = Path("design-data/soak") / f"{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    openings: list[str] = []
    seen_replies = 0
    with out.open("w") as f:
        for n, action in enumerate(ACTIONS[:turns], 1):
            start, before, t = len(session.log), session.location, time.time()
            texting = isinstance(action, tuple)
            row = {"turn": n, "action": action[2] if texting else action, "location_before": before}
            try:
                if texting:
                    row["text_to"] = action[1]
                    await handle_text(session, client, "rin", {"type": "text", "to": action[1], "text": action[2]})
                else:
                    await handle_action(session, client, store, images, tts, "rin", {"type": "action", "text": action})
                    await deliver_due(session, client, "rin")
                pending = None if texting else session.pending_rolls.get("rin")
                if pending:
                    row["roll"] = f"{pending['skill']} ({pending['attribute']}) vs {pending['difficulty']}"
                    rolled = resolve_roll(session, "rin")
                    row["outcome"] = rolled["outcome"]
                    await narrate_roll(session, client, store, images, tts, "rin", rolled)
                    await deliver_due(session, client, "rin")
            except Exception as e:  # record and carry on: the point is to see everything that breaks
                row["error"] = f"{type(e).__name__}: {e}"
            replies = _phone_messages(session, "rin")[seen_replies:]
            seen_replies += len(replies)
            lines = _new_lines(session.log, start)
            prose = [line for line in lines if not line.startswith("[") and not line.startswith("rin:")]
            opening = prose[0][:40] if prose else ""
            row.update(seconds=round(time.time() - t), location=session.location, art=location_art(session.location),
                       humanity=session.characters["rin"].humanity, narration=" / ".join(prose)[:300],
                       repeated_opening=bool(opening) and opening in openings,
                       voice_filtered=sum(line.startswith("[voice filtered") for line in lines),
                       unread=unread(session, "rin"), replies=[{"from": a, "text": b} for a, b in replies],
                       notes=[line[:120] for line in lines if line.startswith(("[tool error", "[referee", "[redo", "[ooc"))])
            openings.append(opening)
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            print(f"{n:2} {row['seconds']:3}s {row.get('roll', '-'):34} loc={session.location!r} "
                  f"{'ERROR ' + row['error'] if 'error' in row else ''}", flush=True)
        rows = [json.loads(line) for line in out.read_text().splitlines()]
        texts = [r for r in rows if "text_to" in r]
        replies = [m for r in rows for m in r["replies"]]
        words = [r["action"] for r in texts] + [m["text"] for m in replies]
        summary = {"turns": len(rows), "errors": sum("error" in r for r in rows), "rolls": sum("roll" in r for r in rows),
                   "median_seconds": sorted(r["seconds"] for r in rows)[len(rows) // 2],
                   "repeated_openings": sum(r["repeated_opening"] for r in rows),
                   "voice_filtered": sum(r["voice_filtered"] for r in rows),
                   "turns_without_art": sum(not r["art"] for r in rows),
                   "texts_sent": len(texts), "replies_delivered": len(replies),
                   "texts_in_session_log": sum(w in line for w in words for line in session.log)}  # must be 0
        f.write(json.dumps({"summary": summary}) + "\n")
    print(json.dumps(summary))
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--turns", type=int, default=len(ACTIONS))
    print(asyncio.run(main(parser.parse_args().turns)))
