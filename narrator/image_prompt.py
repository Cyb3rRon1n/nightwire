"""Phase 19a: turn narrator image text into the owner-approved NoobAI-XL prompt.
The engine decides the subject; a small tag-writer call supplies content tags,
cleaned, with the original sentence as the fallback.
See docs/superpowers/specs/2026-10-28-image-look-19a-design.md."""

import re

from engine.character import is_tsukumogami

QUALITY = "masterpiece, best quality, very awa, newest, year 2024, absurdres, highres, safe"
STYLE = ("anime screenshot, anime coloring, cel shading, thick outlines, detailed background, neon lights, "
         "pink neon rim light, cyan backlight, yellow accents, high contrast, bloom, depth of field, "
         "chromatic aberration, cyberpunk, night")
NEGATIVE = ("nsfw, worst quality, old, early, low quality, lowres, signature, username, logo, bad hands, "
            "mutated hands, mammal, anthro, furry, ambiguous form, feral, semi-anthro, text, watermark, "
            "jpeg artifacts, blurry, worst aesthetic, flat color, simple background, blue skin, colored skin, "
            "monochrome, limited palette")
PORTRAIT_NEGATIVE = NEGATIVE + ", full body, feet, shoes, boots, legs, lower body"
TAGGER_PROMPT = ("Convert the image description into Danbooru-style tags for an anime image model. "
                 "Output 10-25 lowercase tags: setting, objects, people's clothing and features, lighting, "
                 "weather, mood. Concrete nouns only; no subject-count tags, no style or quality tags, "
                 "no artist names, no sentences.")
_SCHEMA = {"type": "object", "properties": {"tags": {"type": "array", "items": {"type": "string"}}},
           "required": ["tags"], "additionalProperties": False}
_PRESENTATION = {"feminine": "1girl", "masculine": "1boy", "androgynous": "1other"}
_COUNT_TAG = re.compile(r"^\d+\w*$|^\d+\s*\w+$")
_BANNED_WORDS = {"masterpiece", "quality", "best", "absurdres", "highres", "aesthetic", "style", "artist",
                 "anime", "detailed"}
_LOWER_BODY_WORDS = {"boots", "boot", "shoes", "shoe", "sneakers", "feet", "foot", "legs", "leg", "pants",
                     "trousers", "skirt", "shorts", "stockings", "thighhighs", "socks", "standing", "knees"}
_LOWER_BODY_PHRASE = re.compile(r"\b(full body|waist down)\b")
_MAX_TAGS = 25
_MIN_TAGS = 5


def subject_tags(kind: str, character=None) -> list[str]:
    if kind == "scene":
        return ["scenery", "no humans"]
    if character is not None and is_tsukumogami(character):
        return ["1other", "solo", "upper body", "portrait", "android", "robot joints"]
    presentation = getattr(character, "presentation", None)
    return [_PRESENTATION.get(presentation, "1other"), "solo", "upper body", "portrait", "looking at viewer"]


def clean_tags(raw: list[str]) -> list[str]:
    out: list[str] = []
    for tag in raw:
        t = str(tag).strip().lower().replace("_", " ")
        t = " ".join(t.split())
        if not t or _COUNT_TAG.match(t.replace(" ", "")) or any(w in _BANNED_WORDS for w in t.split()):
            continue
        if t not in out:
            out.append(t)
    return out[:_MAX_TAGS]


def _below_chest(tag: str) -> bool:
    return any(w in _LOWER_BODY_WORDS for w in tag.split()) or bool(_LOWER_BODY_PHRASE.search(tag))


def build_prompt(subject: list[str], content: list[str] | str) -> str:
    body = content if isinstance(content, str) else ", ".join(content)
    return ", ".join([QUALITY, *subject, STYLE, body])


async def tagify(client, text: str) -> list[str]:
    messages = [{"role": "system", "content": TAGGER_PROMPT}, {"role": "user", "content": text}]
    answer = await client.judge(messages, _SCHEMA)
    return clean_tags(answer.get("tags", []) if isinstance(answer, dict) else [])


async def resolve(client, kind: str, text: str, character=None) -> tuple[str, str, str]:
    subject = subject_tags(kind, character)
    try:
        tags = await tagify(client, text)
    except Exception:  # any tag-writer failure falls back to the narrator's own words
        tags = []
    negative = PORTRAIT_NEGATIVE if kind == "portrait" else NEGATIVE
    if kind == "portrait":  # framing is bust-up: content tags below the chest would pull it to full body
        tags = [t for t in tags if not _below_chest(t)]
    if len(tags) >= _MIN_TAGS:
        return build_prompt(subject, tags), negative, "tags"
    return build_prompt(subject, text), negative, "sentence"
