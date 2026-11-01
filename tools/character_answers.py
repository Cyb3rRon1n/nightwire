"""The character creator's questions, and how a player's answers become a normal Design.
No language model writes the tags: choices map to fixed tags and free text goes in after cleaning.
See docs/superpowers/specs/2026-11-01-character-creator-design.md."""

import re

from narrator.designs import Design
from ruleset.lifepaths import LIFEPATHS
from ruleset.roles import ROLES
from tools.image_studio import BadRequest, refused_terms

_PRESENTATIONS = ["feminine", "masculine", "androgynous"]
_AGES = {"20s": "young adult", "30s": "mature", "40s": "middle-aged", "50+": "old"}  # never "young" alone: it's a negative
_LIFEPATH_TAGS = {"corpo": "corporate attire", "streetkid": "street fashion", "nomad": "nomad gear", "tsukumogami": "android"}
_NOTE_MAX = 200
# Everything a player can put in a negative prompt: free text there could negate clothes or the adult tags.
NEVER_CHOICES = ["glasses", "facial hair", "tattoos", "scars", "piercings", "chrome", "makeup", "jewellery", "hats", "hoods", "masks"]


def _q(qid, label, step, kind="text", **extra):
    return {"id": qid, "label": label, "kind": kind, "step": step, "required": False, **extra}


QUESTIONS: list[dict] = [
    {**_q("name", "Character name", "basics", max=60), "required": True},
    {**_q("presentation", "Presentation", "basics", kind="choice", choices=_PRESENTATIONS), "required": True},
    _q("age", "Apparent age", "basics", kind="choice", choices=list(_AGES)),
    _q("role", "Role", "basics", kind="choice", choices=list(ROLES)),
    _q("lifepath", "Lifepath", "basics", kind="choice", choices=list(LIFEPATHS)),
    _q("personality", "Personality words", "basics"),
    _q("world_role", "Role in the world", "basics", world_only=True),
    _q("home", "Home location", "basics", world_only=True),
    _q("hair", "Hair colour and style", "look"),
    _q("eyes", "Eye colour", "look"),
    _q("skin", "Skin tone", "look"),
    _q("build", "Build and height", "look"),
    _q("face_extras", "Facial hair or makeup", "look"),
    _q("outfit", "Outfit style", "nightwire"),
    _q("colours", "Main colours", "nightwire"),
    _q("marks", "Tattoos, scars and piercings, with placement", "nightwire", hint="Optional. Leave blank for none."),
    _q("chrome", "Chrome or implants, with side", "nightwire", hint="Optional. Leave blank for none."),
    _q("signature", "Never without (a signature item)", "nightwire"),
    _q("never", "Must never include", "final", kind="multi", choices=NEVER_CHOICES),
    _q("extra", "Anything else", "final", max=_NOTE_MAX),
    _q("backstory", "One line of backstory", "final", max=_NOTE_MAX),
]

# refused_terms drops digits and knows "young girl" but not "young", which is a negative on every render anyway.
_NOT_ADULT = re.compile(r"\b(young|younger|youthful|petite|1?\d\s*(?:yo|y/?o|years?[ -]?old))\b", re.I)
_WEIGHT = re.compile(r"\(([^():]*)(?::[\d.]+)?\)")


class BadAnswers(BadRequest):
    pass


def clean_text(value, label: str, limit: int = 120) -> str:
    """One free-text value made safe for a prompt, or BadAnswers naming the words and why."""
    if not isinstance(value, str):
        raise BadAnswers(f"{label} must be text")
    text = re.sub(r"<[^>]*>", "", value)
    while (unwrapped := _WEIGHT.sub(r"\1", text)) != text:   # ((x:1.4)) takes two passes
        text = unwrapped
    text = re.sub(r"[()<>\[\]{}]", "", text)   # whatever brackets were left unbalanced
    text = " ".join(text.split()).strip(", ")[:limit].rstrip(", ")
    bad = sorted({*refused_terms(text), *(m.group(0).lower() for m in _NOT_ADULT.finditer(text))})
    if bad:
        raise BadAnswers(f"{label} can't use: {', '.join(bad)}. Everyone here stays an adult and clothed, so please reword it.")
    return text


def clean_answers(raw) -> dict[str, str | list[str]]:
    if not isinstance(raw, dict):
        raise BadAnswers("expected an object")
    answers = {}
    for q in QUESTIONS:
        value = raw.get(q["id"])
        if q["kind"] == "text" and value not in (None, ""):
            label = q["label"].lower()
            answers[q["id"]] = clean_text(value, label, q.get("max", 120))
    for q in QUESTIONS:
        value = raw.get(q["id"])
        if q["kind"] == "choice" and value not in (None, ""):
            if value not in q["choices"]:
                raise BadAnswers(f"{q['label'].lower()} must be one of: {', '.join(q['choices'])}")
            answers[q["id"]] = value
        if q["kind"] == "multi" and value not in (None, "", []):
            if not isinstance(value, list) or any(v not in q["choices"] for v in value):
                raise BadAnswers(f"{q['label'].lower()} must be chosen from: {', '.join(q['choices'])}")
            answers[q["id"]] = [c for c in q["choices"] if c in value]
    for q in QUESTIONS:
        if q["required"] and not answers.get(q["id"]):
            raise BadAnswers(f"{q['label'].lower()} is required")
    return {k: v for k, v in answers.items() if v}


def _split(*values: str) -> list[str]:
    return [part.strip() for v in values for part in v.split(",") if part.strip()]


def to_design(answers: dict, kind: str, seed: int, close_up: bool = False) -> Design:
    """`kind` is the creator's player, npc or ai. Every one of them is a "character" Design, so the sheets work unchanged.

    No player text goes in `negative` or `held`: `held` reaches the expression negative, so the signature item is only ever
    a tag, and `close_up` leaves it out for the expression panels so it can't float beside a head."""
    def a(qid: str) -> str:
        return answers.get(qid, "")

    never = answers.get("never")
    tags = dict.fromkeys(_split("mature, adult", _AGES.get(a("age"), ""), a("skin"), a("build"), a("outfit"), a("colours"),
                                _LIFEPATH_TAGS.get(a("lifepath"), ""), "" if close_up else a("signature"), a("extra")))
    return Design(
        name=answers["name"], kind="character", source=f"creator:{kind}", tags=", ".join(tags),
        presentation=answers["presentation"],
        negative=", ".join(c for c in NEVER_CHOICES if isinstance(never, list) and c in never),
        required=_split(a("hair"), a("eyes"), a("face_extras"), a("marks"), a("chrome")),
        seed=seed, notes=[f"personality: {a('personality')}"] if a("personality") else [],
    )
