"""The district map (spec 2026-11-24-district-map-design.md): Kuroshio's seven districts as a subway diagram, with
the engine state the player can use: where they are, how each district feels, its pressure clock, who they met there,
the places they know, and the travel line Go puts in the action box. Derived from session state; no model calls."""

from engine.session import Session
from narrator import clock, clocks, places
from narrator.movement import places_in
from narrator.place_art import location_art
from narrator.world import _where, kuroshio

ORDER = ("Tenjō Heights", "Hanabira-chō", "Ikebe Low", "Kuroshio Docks", "Ring Line", "The Loop", "Yomi Line")
_MOOD_RANK = ("calm", "wary", "tense", "locked down")
_LINES = {"Tenjō Heights": "I take a maglev pod up to Tenjō Heights.",
          "Yomi Line": "I look for a way down into the sealed Yomi Line.",
          "The Loop": "I ride up onto the Loop."}


def _district(text: str | None) -> str | None:
    d = _where(kuroshio(), text)[1]
    return d.name if d else None


def _go(name: str, trains: bool) -> str:
    if name in _LINES:
        return _LINES[name]
    return f"I take the Ring Line to {name}." if trains else f"I take a taxi to {name}."


def view(session: Session) -> dict:
    here, trains = _district(session.location), clock.stretch(session) not in clock.NO_TRAINS
    moods: dict[str, str] = {}
    for key, state in session.places.items():
        d, word = _district(key), places.mood(state).split(" and ")[0]
        if d and word in _MOOD_RANK and _MOOD_RANK.index(word) > _MOOD_RANK.index(moods.get(d, "calm")):
            moods[d] = word
    shown = {c["where"][0]: c for c in clocks.defs() if c.get("shown")}
    mentioned = places_in(" ".join([*session.active_objectives, *(j["text"] for j in session.journal)]))
    known = set(session.places) | mentioned
    districts = []
    for name in ORDER:
        c = shown.get(name)
        districts.append({
            "name": name, "here": name == here, "mood": moods.get(name, "calm"),
            "clock": {"filled": session.clocks.get(c["id"], {}).get("filled", 0), "size": c["size"]} if c else None,
            "people": [n for n, p in session.people.items() if p.get("district") == name],
            "places": sorted(k for k in known if k != name and _district(k) == name),
            "art": location_art(name), "go": None if name == here else _go(name, trains)})
    pressed = sum(bool(d["clock"] and d["clock"]["filled"]) for d in districts)
    caption = "Kuroshio." + (f" You are in {here}." if here else "")
    caption += f" {pressed} district{'s' if pressed != 1 else ''} under pressure." if pressed else ""
    return {"districts": districts, "trains": trains, "caption": caption}
