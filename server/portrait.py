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
) -> None:
    if player_id not in session.characters:
        raise ValueError(f"no joined character for player_id {player_id!r}")
    character = session.characters[player_id]

    description = _build_portrait_prompt(character)
    await narrator_client.unload()
    image_bytes = await image_backend.generate_portrait(description)

    relative_path = f"portraits/{session.session_id}/{player_id}.png"
    output_path = store.directory / relative_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(image_bytes)

    character.portrait_path = relative_path
