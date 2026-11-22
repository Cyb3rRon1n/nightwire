"""Word that spreads: whoever saw a deed tells one other person from the same district every 5 turns, weaker each
hop, sometimes exaggerated; old news fades; amends clear it (Ryan et al., AIIDE 2015 EXAG; Kreminski's Gossamer,
CoG 2023). No model calls. See docs/superpowers/specs/2026-11-22-places-gossip-design.md, part 3."""

import random
import re
import tomllib
from functools import cache
from pathlib import Path

from engine.session import Session
from narrator.cast import _player_turns
from narrator.world import _where, kuroshio

WITNESS, SPREAD_EVERY, FADE_EVERY, MAX_DEEDS, EXAGGERATE = 3, 5, 30, 20, 0.2
_BAD = {"punched", "hit", "kicked", "hurt", "robbed", "threatened", "shot", "stabbed", "beat", "cheated"}
_GOOD = {"helped", "saved", "paid", "fed", "gave", "protected", "healed", "freed"}


@cache
def rules() -> tuple[tuple[str, str], ...]:
    raw = tomllib.loads((Path(__file__).parent / "worlds" / "gossip.toml").read_text(encoding="utf-8"))
    return tuple((r["find"], r["replace"]) for r in raw["rule"])


def exaggerate(text: str) -> str:
    for find, replace in rules():
        if re.search(find, text):
            return re.sub(find, replace, text, count=1)
    return text


def _district(session: Session) -> str | None:
    d = _where(kuroshio(), session.location)[1]
    return d.name if d else None


def record(session: Session, what: str, good: bool) -> None:
    """Everyone here saw it (strength 3). Nobody here, nobody to tell."""
    now = _player_turns(session)
    if not session.present or any(d["what"] == what and now - d["turn"] < 10 for d in session.deeds):
        return
    session.deeds.append({"what": what, "good": good, "district": _district(session), "turn": _player_turns(session),
                          "knows": {n: {"s": WITNESS, "text": what, "seen": True} for n in session.present}})
    while len(session.deeds) > MAX_DEEDS:
        session.deeds.remove(min(session.deeds, key=lambda d: max(k["s"] for k in d["knows"].values())))


def classify(what: str) -> bool | None:
    words = set(re.findall(r"[a-z]+", what.lower()))
    return False if words & _BAD else True if words & _GOOD else None


def amends(session: Session, who: str) -> None:
    """Keeping your word to someone, or helping them at a cost, clears the bad things they've heard about you."""
    low = who.lower()
    for d in session.deeds:
        if not d["good"]:
            d["knows"] = {n: k for n, k in d["knows"].items() if n.lower() != low and low not in n.lower().split()}
    session.deeds = [d for d in session.deeds if d["knows"]]


def _locals(session: Session, district: str | None) -> list[str]:
    npcs = [n.name for n in kuroshio().npcs if n.home and n.home == district]
    return npcs + [n for n, p in session.people.items() if p["district"] == district]


def tick(session: Session) -> None:
    """Every 5 player turns each knower (strength 2+) tells one local who doesn't know; every 30, everything fades."""
    now = _player_turns(session)
    if now and now % SPREAD_EVERY == 0:
        for d in session.deeds:
            for teller, k in list(d["knows"].items()):
                fresh = [n for n in _locals(session, d["district"]) if n not in d["knows"]]
                if k["s"] >= 2 and fresh:
                    told = random.random() < EXAGGERATE
                    d["knows"][random.choice(fresh)] = {"s": k["s"] - 1, "seen": False,
                                                        "text": exaggerate(k["text"]) if told else k["text"],
                                                        "exaggerated": told or k.get("exaggerated", False)}
    if now and now % FADE_EVERY == 0:
        for d in session.deeds:
            d["knows"] = {n: {**k, "s": k["s"] - 1} for n, k in d["knows"].items() if k["s"] > 1}
        session.deeds = [d for d in session.deeds if d["knows"]]


def heard_lines(session: Session) -> str:
    """'Mama Sato has heard (second-hand, maybe exaggerated): ...' for present people who weren't there."""
    lines = []
    for name in session.present:
        heard = [d["knows"][name] for d in session.deeds if name in d["knows"] and not d["knows"][name]["seen"]]
        if heard:
            k = max(heard, key=lambda k: k["s"])
            how = "second-hand, maybe exaggerated" if k.get("exaggerated") else "second-hand"
            lines.append(f"{name} has heard ({how}): {k['text']}.")
    return "\n".join(lines[:3])


def street(session: Session) -> list[dict]:
    """Per district, the best and worst thing people there say about the player (the strongest telling)."""
    out = {}
    for d in session.deeds:
        best = max(d["knows"].values(), key=lambda k: k["s"])
        row = out.setdefault(d["district"] or "Around", {"district": d["district"] or "Around", "good": None,
                                                           "bad": None, "_s": {}})
        side = "good" if d["good"] else "bad"
        if best["s"] > row["_s"].get(side, 0):
            row[side], row["_s"][side] = best["text"], best["s"]
    return [{k: v for k, v in r.items() if k != "_s"} for r in out.values()]
