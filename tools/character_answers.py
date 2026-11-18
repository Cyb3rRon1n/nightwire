"""The character creator's questions, and how a player's answers become a normal Design.
No language model writes the tags: choices map to fixed tags and free text goes in after cleaning.
See docs/superpowers/specs/2026-11-01-character-creator-design.md."""

import re
import unicodedata

from narrator.design_sheets import CHARACTER_QUALITY
from narrator.designs import Design
from narrator.image_prompt import QUALITY
from ruleset.lifepaths import LIFEPATHS
from ruleset.roles import ROLES
from tools.image_studio import BadRequest, refused_terms

_PRESENTATIONS = ["feminine", "masculine", "androgynous"]
# "young" and "old" are both in the negatives every character gets, so neither can be an age tag.
_AGES = {"20s": "adult in their twenties", "30s": "adult in their thirties", "40s": "middle-aged", "50+": "older adult"}
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

# On top of Image Studio's refused_terms, which suits its short action text and drops digits. Best effort, like that list:
# the negatives below are always applied too. Matched against _screening_form, so spacing and punctuation don't matter.
_REFUSED = re.compile(
    r"\b(young|younger|youthful|youth|petite|childlike|childish|preteens?|pre teens?|tweens?|teenaged|adolescents?|juveniles?|"
    r"lolis|lolicon|shotas|shotacon|high ?school\w*|middle school\w*|elementary school\w*|junior high|school ?uniforms?|school ?kids?|"
    r"flat chest\w*|small breasts|aged down|under ?18|chibi|baby ?faced?|baby(?! blue| pink)|"
    r"unclothed|unclad|disrobed|(?:no|without) (?:clothes|clothing|garments?|shirt|top|pants|underwear|panties|bra)|wearing nothing|"
    r"see through|sheer clothes|transparent clothes|exposed (?:breasts?|chest|nipples?|genitals?|crotch|body|skin)|bare (?:breasts?|chest)|"
    r"fellatio|blowjobs?|handjobs?|paizuri|cunnilingus|testicles?|scrotum|anus|anal|clitoris|labia|cock|erections?|ejaculat\w*|semen|"
    r"creampie|masturbat\w*|oral sex|rape|gangbang|orgy|incest|futanari|bondage|bdsm|shibari|ecchi|lewd|erotic|xxx|r ?18|"
    r"questionable|rating)\b")
_TENS = "twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety"
_NUMBER_WORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
                 "thirteen", "fourteen", "fifteen", "sixteen", "seventeen")   # eighteen and up are adults
_NUMBER = rf"\d+|{'|'.join(_NUMBER_WORDS)}"
_AGE_AFTER = re.compile(rf"(?:\b({_TENS}) )?\b({_NUMBER}) ?(?:yo|y o|yrs? old|years? old|years? of age|years? young)\b")
_AGE_BEFORE = re.compile(rf"\b()(?:age|aged|ages)(?: of)? ({_NUMBER})\b")
# art-direction.md: elderly characters are never sexualised.
_REVEALING = re.compile(r"\b(cleavage|lingerie|swimsuits?|bikinis?|revealing|suggestive|seductive|sexy|skimpy|midriff|backless|"
                        r"miniskirts?|breasts?|busty|curvy)\b")
_WEIGHT = re.compile(r"\(([^():]*)(?::[\d.]+)?\)")
# Fixed text, never a player's: the sexual terms and the rating CHARACTER_NEGATIVE_EXTRA doesn't already name.
CREATOR_NEGATIVE = ("questionable, nudity, topless, bottomless, unclothed, see-through, exposed breasts, areolae, vagina, testicles, "
                    "fellatio, oral sex, intercourse, cum, bondage")
_OLDER_NEGATIVE = "sensitive, cleavage, revealing clothes, lingerie, swimsuit, suggestive, seductive"
# These two never reach a prompt, so other alphabets are fine there.
_ANY_ALPHABET = {"name", "backstory"}
_PROMPT_FIELDS = ("hair", "eyes", "skin", "build", "face_extras", "outfit", "colours", "marks", "chrome", "signature", "extra")


class BadAnswers(BadRequest):
    pass


def _screening_form(text: str) -> str:
    """Lower case letters and digits with single spaces, so n.u.d.e, n-u-d-e and n_u_d_e all read as nude."""
    text = re.sub(r"(?<![a-z])(?:[a-z]\.)+[a-z]?(?![a-z])", lambda m: m.group(0).replace(".", ""), text.lower())
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    return re.sub(r"(?<![a-z0-9])[a-z](?: [a-z]){2,}(?![a-z0-9])", lambda m: m.group(0).replace(" ", ""), text)


def _refused(text: str) -> list[str]:
    plain = _screening_form(text)
    bad = {*refused_terms(plain), *(m.group(0) for m in _REFUSED.finditer(plain))}
    for pattern in (_AGE_AFTER, _AGE_BEFORE):
        for m in pattern.finditer(plain):
            number = int(m.group(2)) if m.group(2).isdigit() else _NUMBER_WORDS.index(m.group(2))
            if not m.group(1) and number < 18:
                bad.add(m.group(0))
    return sorted(bad)


def clean_text(value, label: str, limit: int = 120, tag: bool = True) -> str:
    """One free-text value made safe for a prompt, or BadAnswers naming the words and why. `tag` is for text that
    reaches a prompt: it's stored normalised and limited to English letters. All text gets the same screening."""
    if not isinstance(value, str):
        raise BadAnswers(f"{label} must be text")
    text = "".join(c for c in unicodedata.normalize("NFKC", value) if unicodedata.category(c) != "Cf")
    text = re.sub(r"<[^>]*>", "", text)
    while (unwrapped := _WEIGHT.sub(r"\1", text)) != text:   # ((x:1.4)) takes two passes
        text = unwrapped
    text = re.sub(r"[()<>\[\]{}]", "", text)   # whatever brackets were left unbalanced
    text = re.sub(r"embedding\s*:\s*[^\s,]*", "", text, flags=re.I)
    if tag:
        text = re.sub(r"[_-]", " ", text)
    text = " ".join(text.split()).strip(", ")[:limit].rstrip(", ")
    bad = _refused(text)
    if bad:
        raise BadAnswers(f"{label} can't use: {', '.join(bad)}. Everyone here stays an adult and clothed, so please reword it.")
    if tag and any(ord(c) > 127 and unicodedata.category(c)[0] in "LM" for c in text):
        raise BadAnswers(f"{label} can only use English letters, because the image generator reads this as tags.")
    return text


def _check_revealing(text: str, label: str) -> None:
    bad = sorted({m.group(0) for m in _REVEALING.finditer(_screening_form(text))})
    if bad:
        raise BadAnswers(f"{label} can't use: {', '.join(bad)}. Characters who are 50+ are never drawn in a revealing way.")


def clean_note(note, answers: dict) -> str:
    """A note on a reroll or variation, which reaches the prompt like any other tag field."""
    note = clean_text(note or "", "the note", _NOTE_MAX)
    if answers.get("age") == "50+":
        _check_revealing(note, "the note")
    return note


def rated(positive: str, answers: dict) -> str:
    """The design sheets' character rating allows suggestive; 50+ gets the plain safe rating instead."""
    return positive.replace(CHARACTER_QUALITY, QUALITY) if answers.get("age") == "50+" else positive


def clean_answers(raw) -> dict[str, str | list[str]]:
    if not isinstance(raw, dict):
        raise BadAnswers("expected an object")
    answers = {}
    for q in QUESTIONS:
        value = raw.get(q["id"])
        if q["kind"] == "text" and value not in (None, ""):
            label = q["label"].lower()
            answers[q["id"]] = clean_text(value, label, q.get("max", 120), tag=q["id"] not in _ANY_ALPHABET)
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
    if answers.get("age") == "50+":
        for qid in _PROMPT_FIELDS:
            _check_revealing(answers.get(qid, ""), qid.replace("_", " "))
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
        negative=", ".join((CREATOR_NEGATIVE, *([_OLDER_NEGATIVE] if a("age") == "50+" else []),
                            *(c for c in NEVER_CHOICES if isinstance(never, list) and c in never))),
        required=_split(a("hair"), a("eyes"), a("face_extras"), a("marks"), a("chrome")),
        seed=seed, notes=[f"personality: {a('personality')}"] if a("personality") else [],
    )
