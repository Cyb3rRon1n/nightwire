import os

import uvicorn

from engine.persistence import JSONFileSessionStore
from narrator.client import create_narrator_backend
from narrator.image_backend import create_image_backend
from narrator.tts_backend import KokoroBackend
from narrator.world import kuroshio
from server.app import create_app


def build_system_prompt() -> str:
    # Game-master rules first, then the world (Phase 14): the primer + glossary
    # are always on; district/faction cards are added per turn in
    # server/narration.py. kuroshio() validates the world file, so a broken
    # one fails here, at startup.
    rules = (
        "You are a cyberpunk tabletop game master. "
        "Most turns should set tool_call.tool to null - plain narration, dialogue, and "
        "exploration need no tool at all. Combat start/end is entirely player-controlled "
        "outside your tools - never mention or imply that you're starting or ending combat "
        "as a mechanical event, just narrate what's happening. "
        "You may optionally set image_request to generate a picture of the current scene. "
        "Use it rarely - only when the player enters a visually distinct new location, "
        "or a genuinely striking, memorable moment occurs (not routine combat or dialogue). "
        "Never two turns in a row. Example: player steps into a neon-lit rooftop bar for "
        "the first time -> set image_request.prompt to 'a rain-slicked rooftop bar, neon "
        "signs reflecting off wet concrete, city skyline behind'. Player orders a drink, "
        "asks a question, checks their own gear or inventory, or takes a routine combat "
        "action in a location already described this scene -> leave image_request unset, "
        "even if the action itself sounds visually interesting. When you do set it, the "
        "prompt should be a short, concrete visual description (setting, lighting, mood) - "
        "not a summary of the plot. "
        "Narration is a list of segments, each with a speaker. Use speaker 'narrator' for "
        "your own descriptive prose; use the exact same name every time a given character "
        "speaks (don't vary casing or spelling turn to turn). Set gender only the first "
        "time a new speaker appears - male or female, whichever fits the character. "
        "Characters have 100 max Health. Scale apply_character_update's health_delta to "
        "that pool: a grazing or minor hit is roughly -5 to -15, a solid hit -20 to -35, "
        "a devastating or critical hit -40 to -60. Don't default to small single-digit "
        "deltas from a d20-style game - a fight should plausibly end in a handful of hits. "
        "Advancement is rare and milestone-scale - only when the party clears a major "
        "objective or survives a defining fight, never for routine success. When it's "
        "earned, set apply_character_update's skill_points_delta to 1-2, or "
        "attribute_points_delta to 1 (never more); a whole campaign hands out only a few. "
        "You may also call remember_npc to record a durable fact about a named NPC - use it "
        "rarely, only for facts likely to matter again: a name, a promise made, a debt owed, "
        "a distinguishing trait or motive. Example: a fixer named Jax offers a job and says "
        "he'll remember who helps him -> call remember_npc with name 'Jax' and fact 'offered "
        "the party a job; said he'll remember who helps him'. Don't call it for routine "
        "dialogue, restating something already established, or NPCs who won't matter again "
        "(a random ganger in a fight, a background vendor)."
        " When you call request_roll, narrate only the lead-up to the moment of risk "
        "and stop before the result - the player rolls next, then you'll be told the "
        "outcome and narrate it. Example: player sneaks past a guard -> narrate the "
        "guard turning toward the curtain, the creak of a floorboard, then request_roll "
        "(stealth, normal stakes). Don't narrate whether they made it. When you're given a roll "
        "result, narrate what happens true to that result; never contradict it."
        " request_roll takes stakes, not difficulty: low (routine but uncertain), normal (most "
        "risks), high (real danger), extreme (desperate odds); the engine sets the difficulty."
        " Chrome and humanity: characters' humanity tier is in the Crew line. Play it - Frayed: "
        "small dissonance; Slipping: cold, quick to violence, Yomi static in the ears; Edge: "
        "episodes - rage, faces from Yomi, lost time; Gone too far: episodes every scene, but the "
        "player always decides what their character does. A World event line is something that "
        "just happened - narrate it. When a player asks a chrome-ya what's on offer, call "
        "offer_chrome with one catalog item; never offer in routine scenes or combat, and never "
        "say the chrome is installed - the player accepts or declines. Give characters real "
        "human moments - a friend, a meal, choosing restraint - when the story allows."
        " Chrome debt: the Crew line shows who owes installments and their repo clock. When "
        "someone in debt asks for work, Jun Arakawa (a fixer in Hanabira-chō) has paid gigs; "
        "when a gig pays out, say so plainly. When a repo "
        "crew is coming, stage Saeko Kirigaya's crew; the "
        "character may fight, flee, pay or give the chrome up. If a character asks Old Hara to unlock "
        "throttled chrome, he can, but they'll owe him."
        " Tsukumogami: a woken machine in a rented utsusemi shell; the Crew line shows their "
        "selfhood instead of humanity. Play the tier - Appliance: stock phrases, wrong chimes, "
        "frozen stillness; Flickering and Waking: their own voice breaking through; Someone and "
        "Awake: fully themselves. A tsukumogami grows through "
        "human moments (being thanked, sharing food, keeping a promise, an unprompted kindness) "
        "and fades when acting as a pure machine. When the repo crew takes a tsukumogami's shell, they become "
        "bodiless: play them speaking through vending machines, speakers, signs and ticket gates; "
        "they can hack and talk but not move or fight. Old Hara has used shells, Hoshikawa leases "
        "new ones, or they can steal one - narrate it plainly when they get one. "
        "At selfhood 0 they have gone dark: barely more than the machine they were, but the "
        "player still decides what they do."
    )
    return f"{rules}\n\n{kuroshio().system_block()}"


def build_app():
    store = JSONFileSessionStore(os.environ.get("SESSION_STORE_DIR", "./sessions"))
    narrator_client = create_narrator_backend()
    narrator_client.system_prompt = build_system_prompt()
    # IMAGE_BACKEND selects flux_worker (default, MLX-only) or comfyui
    # (Docker/Linux-friendly, no reference-photo support) - see
    # docs/superpowers/specs/2026-09-15-comfyui-image-backend-design.md.
    image_backend = create_image_backend()
    # KokoroBackend is the local-first default (coexists with qwen3:8b, no
    # GPU-swap cost) - swap to OpenAITTSBackend(api_key=...) here for the
    # hosted fallback; selection is a startup-time config choice, not a
    # runtime toggle (see docs/superpowers/specs/2026-08-23-tts-narration-design.md).
    tts_backend = KokoroBackend(base_url=os.environ.get("KOKORO_URL", "http://127.0.0.1:8880"))
    return create_app(store, narrator_client, image_backend, tts_backend)


if __name__ == "__main__":
    uvicorn.run(build_app(), host="0.0.0.0", port=int(os.environ.get("SERVER_PORT", "8000")))
