import base64
from pathlib import Path

from engine.character import CharacterSheet
from engine.persistence import JSONFileSessionStore
from engine.session import Session
from narrator.client import NarratorClient
from narrator.image_backend import ImageBackend

# Visual (not mechanical) descriptors for portrait prompts. ROLES/LIFEPATHS
# in ruleset/ describe game mechanics, not appearance, so this is genuinely
# new content, not a duplicate of something already in the codebase.
_ROLE_VISUALS: dict[str, str] = {
    "solo": "battle-scarred, tactical armor plating, holstered sidearm, alert combat stance",
    "netrunner": "sleek matte-black jacket, temple-jack cyberware behind the ear, faint neon glow from a wrist deck",
    "techie": "grease-stained coveralls, tool harness, magnifying optic goggles pushed up on the forehead",
    "fixer": "sharp tailored coat, understated jewelry, calm and calculating expression",
}

_LIFEPATH_VISUALS: dict[str, str] = {
    "corpo": "crisp corporate-cut clothing softened by street wear, faint megacorp branding",
    "streetkid": "layered street fashion, hand-me-down cyberware, scuffed boots",
    "nomad": "weathered leather and denim, dust-scoured gear, a clan tattoo or patch",
}


_MAX_REFERENCE_PHOTOS = 2
_MAX_REFERENCE_PHOTO_BYTES = 4 * 1024 * 1024
_ALLOWED_REFERENCE_PHOTO_TYPES = ("image/png", "image/jpeg", "image/webp")


def _validate_reference_photos(raw: object) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"reference_photos must be a list, got {type(raw).__name__}")
    if len(raw) > _MAX_REFERENCE_PHOTOS:
        raise ValueError(f"reference_photos: at most {_MAX_REFERENCE_PHOTOS} photos allowed, got {len(raw)}")
    for photo in raw:
        if not isinstance(photo, str):
            raise ValueError(f"reference_photos: each entry must be a string, got {type(photo).__name__}")
        header, sep, encoded = photo.partition(",")
        if not sep or not header.startswith("data:") or ";base64" not in header:
            raise ValueError("reference_photos: each entry must be a base64 data URL (data:image/...;base64,...)")
        media_type = header[len("data:"):header.index(";")]
        if media_type not in _ALLOWED_REFERENCE_PHOTO_TYPES:
            raise ValueError(f"reference_photos: unsupported image type {media_type!r}")
        # Reject on encoded length before decoding, so a huge data URL isn't
        # fully materialized in memory just to be rejected. base64 inflates
        # ~4/3, so this is a loose upper bound; the exact check on the
        # decoded bytes below still applies.
        if len(encoded) > _MAX_REFERENCE_PHOTO_BYTES * 4 // 3 + 4:
            raise ValueError(
                f"reference_photos: encoded image exceeds the {_MAX_REFERENCE_PHOTO_BYTES} byte limit"
            )
        try:
            decoded = base64.b64decode(encoded, validate=True)
        except ValueError as e:
            raise ValueError(f"reference_photos: invalid base64 data: {e}") from e
        if not decoded:
            raise ValueError("reference_photos: image data is empty")
        if len(decoded) > _MAX_REFERENCE_PHOTO_BYTES:
            raise ValueError(
                f"reference_photos: image is {len(decoded)} bytes, exceeds {_MAX_REFERENCE_PHOTO_BYTES} byte limit"
            )
    return raw


def _build_portrait_prompt(character: CharacterSheet) -> str:
    role_visual = _ROLE_VISUALS.get(character.role.lower())
    lifepath_visual = _LIFEPATH_VISUALS.get(character.lifepath.lower())
    visual_tags = ", ".join(tag for tag in (lifepath_visual, role_visual) if tag)

    base = f"{character.name}, a {character.lifepath} {character.role}"
    style = "moody neon lighting, rain-slicked cyberpunk city backdrop, highly detailed digital painting"
    if visual_tags:
        return f"{base} — {visual_tags}, {style}"
    return f"{base} — {style}"


async def handle_approve_character(
    session: Session,
    store: JSONFileSessionStore,
    narrator_client: NarratorClient,
    image_backend: ImageBackend,
    player_id: str,
    message: dict,
) -> None:
    if player_id not in session.characters:
        raise ValueError(f"no joined character for player_id {player_id!r}")
    character = session.characters[player_id]
    reference_photos = _validate_reference_photos(message.get("reference_photos"))

    description = _build_portrait_prompt(character)
    await narrator_client.unload()
    image_bytes = await image_backend.generate_portrait(description, reference_photos=reference_photos)

    relative_path = f"portraits/{session.session_id}/{player_id}.png"
    output_path = store.directory / relative_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(image_bytes)

    character.portrait_path = relative_path
