<p align="center">
  <a href="https://github.com/Cyb3rRon1n/nightwire/actions/workflows/ci.yml"><img src="https://github.com/Cyb3rRon1n/nightwire/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT"></a>
  <img src="https://img.shields.io/badge/python-3.11%2B-blue.svg" alt="Python 3.11+">
</p>

<p align="center">
  <img src="docs/images/banner.svg"
       alt="Nightwire - A cyberpunk AI game master for real-time tabletop sessions"
       style="max-width: 100%; height: auto;">
</p>

<p align="center">
  📖 <a href="ROADMAP.md">Roadmap</a> · <a href="docs/superpowers/specs">Design specs</a>
</p>

A cyberpunk tabletop RPG with an AI game master — playable solo or with friends, in a browser. A homebrew ruleset (`1d10 + attribute + skill` vs. a difficulty class, four roles, six attributes) built specifically for a Cyberpunk-2077-flavored table, not borrowed from D&D.

Sibling project to [`oracle`](https://github.com/Cyb3rRon1n/oracle) (a D&D-flavored AI-DM) — built fresh rather than adapted, and researched independently at every design decision rather than leaning on oracle as precedent (see `ROADMAP.md`'s "Why a fresh project" section for the reasoning, and every spec under `docs/superpowers/specs/` for the citations behind each mechanic).

**Status**: Phases 1–10 built and live-verified — ruleset, engine, AI narrator, web frontend, image generation (two backends, MLX and ComfyUI), text-to-speech (character-distinct voices), a skill system, photo-reference portraits, and attribute point-buy all work end to end. See `ROADMAP.md`'s Phases section for the full build history.

## What makes it Nightwire

- **The server owns all truth.** Character sheets, turn order, combat state all live in the Python engine (`engine/`). The narrator model only narrates and calls tools — it never does its own arithmetic.
- **A tiered 1d10 resolution, not d20.** `1d10 + attribute + skill` vs. a difficulty class, deliberately the lowest-complexity class of cyberpunk system surveyed (Cyberpunk RED, CY_BORG), not Shadowrun-style dice pools.
- **Four roles, checked against Cyberpunk 2077 itself**: Solo, Netrunner, Techie, Fixer — CP2077's three official archetypes plus a Fixer for social/negotiation. Six attributes (Body, Reflexes, Tech, Cool, Intellect, Presence).
- **Structured output, not native tool-calling.** The narrator's tool choice and arguments are both constrained by a real JSON schema, after live testing found free-form tool-calling inventing plausible-but-wrong arguments on nearly every turn.
- **Character-consistent image generation.** A portrait generated at character approval becomes a reference image for later scene generation, so a character looks like themselves across turns instead of a new face each time — on the default `flux_worker` backend. The `comfyui` backend (Docker/Linux-friendly, see below) doesn't support this yet: no IPAdapter/InstantID on the verified target instance, so it's text-prompt-only.
- **You roll the dice, the narrator lives with them.** When an action is risky, the narrator sets up the moment and stops; you click **Roll**, watch the d10 land with your modifiers, then the narrator tells what happens — true to the result, which stays in the story so it's remembered later.
- **Chrome has a price.** Cyberware makes you better at the thing it's for — Kama blades, a Yomi jack, a Kagerou time-dilation rig — and costs humanity. Push an implant past its limits with ⚡ Overclock right on the roll card and it costs more. As humanity falls the narrator plays the slide; you never lose control of your character, and there's always a way back.
- **Chrome is on credit.** Miss enough installments and the street notices: a polite final notice, then Hoshikawa remote-throttles your newest implant, then Saeko Kirigaya's torite crew comes to take it back. Pay it down with Jun Arakawa's gigs, or have Old Hara unlock it off the books — for a favor.
- **Or play the machine.** Pick the Tsukumogami origin and you're an old vending machine or train announcer that woke up, walking the street in a rented utsusemi shell. You start as barely more than an appliance and earn your selfhood through human moments. Fall behind on the lease and Saeko's crew takes the shell, leaving you talking through vending machines and station speakers until someone finds you a new body.
- **Local-first AI** — Ollama-backed (`qwen3:8b`), same stance for the TTS backend.

## World

Nightwire's setting is **Kuroshio**, an original Japanese megacity in 2089 where everyone's chrome is on credit. It lives in `narrator/worlds/kuroshio.toml`:

- **`primer` + `[glossary]`**: always in the narrator's system prompt (max 1,900 chars together).
- **`[[district]]` / `[[faction]]` / `[[npc]]`**: `name`, `aliases`, `card` (max 400 chars); an NPC can also have a `home` district. Each turn, up to 4 cards are added: the district matching the current location first, then one NPC who lives there (unless a local NPC is already in the scene), then anything mentioned in the player's action or recent narration.

To add a place or faction, add an entry. Keep each card standalone (don't refer to "they" from another card), and make sure names and aliases are unique (matching ignores case and accents, so "Ōgane" already matches "Ogane"). The server checks the file at startup and refuses to start if it's invalid.

## Running it

Requirements: Python 3.11+, [Ollama](https://ollama.com) with `qwen3:8b` pulled, Node 22+ (frontend build).

```bash
# server
pip install -e ".[dev]"
python -m server                     # ws://localhost:8000

# web frontend (development)
cd frontend && npm ci && npm run dev # http://localhost:3000/nightwire
```

Image generation additionally needs a backend running — the default (`IMAGE_BACKEND=flux_worker`) is a running `ultra-fast-image-gen` worker (`open-dungeon`'s `image_server/`) on `http://127.0.0.1:7869`; set `IMAGE_BACKEND=comfyui` and `COMFYUI_URL` to use a ComfyUI instance instead (no MLX/Apple-Silicon requirement). Optional either way — without one, everything except scene/portrait images works normally.

The narrator itself is also swappable: the default (`NARRATOR_BACKEND=ollama`) is local Ollama; set `NARRATOR_BACKEND=anthropic` (needs `ANTHROPIC_API_KEY`; optionally `NARRATOR_ANTHROPIC_MODEL` to override the default model) or `NARRATOR_BACKEND=openai_compat` (needs `NARRATOR_OPENAI_COMPAT_BASE_URL` and `NARRATOR_OPENAI_COMPAT_MODEL`, e.g. for OpenRouter or a local vLLM/llama.cpp-server; optionally `NARRATOR_OPENAI_COMPAT_API_KEY` if the endpoint requires one) for a hosted alternative — same `NarratorResponse` schema either way, so behavior is directly comparable across backends.

With Ollama, set `NIGHTWIRE_THINK=off` to turn off qwen3's hidden thinking step: in live testing it cut the median turn from about 75 s to about 32 s with the same state accuracy (`on` forces it on; unset leaves Ollama's default). After each narration a small referee call decides state changes the narrator used to miss (human moments, repossession, gig pay), and the engine sets roll difficulty from the narrator's stakes.

### Run as a Docker stack

```bash
docker compose up -d --build          # server on :8000, web on :3000/nightwire

# local narrator instead of a hosted model:
docker compose --profile ollama up -d --build
docker compose exec ollama ollama pull qwen3:8b
#   ...and in .env:  OLLAMA_HOST=http://ollama:11434

# character-distinct TTS narration:
docker compose --profile voice up -d --build
#   ...and in .env:  KOKORO_URL=http://kokoro:8880   (compose default already points here)
```

Already run Anvil on this host? Point `OLLAMA_HOST` at Anvil's Ollama instead
of the `ollama` profile — one GPU can't usefully feed two.

**Image generation has two backends.** `image_backend.py`'s default
(`IMAGE_BACKEND=flux_worker`) talks to `open-dungeon`'s
`ultra-fast-image-gen` worker, which is MLX-based — Apple Silicon only,
can't run in a Linux container. Set `FLUX_WORKER_URL` if you run that
worker natively on a reachable Mac; there's no shared-volume wiring here
for its output image files, so generated images won't reach the
containerized web frontend without more plumbing. `IMAGE_BACKEND=comfyui`
has no such limitation — it's a plain HTTP client, so it works directly
from the Docker stack. Set `COMFYUI_URL` to a reachable ComfyUI instance.

### Homepage dashboard tile

Co-located Vulcan install with Homepage enabled? Add a click-through tile:

```bash
pip install --user pyyaml   # if not already present
python3 homepage_integrate.py --url http://192.168.1.x:3000/nightwire
```

Auto-detects a sibling `vulcan/stack`; pass `--vulcan-dir` otherwise. Safe to
re-run — only touches its own "Nightwire" group.

## Repository layout

```
├── ruleset/            # dice resolution, attributes, roles, lifepaths, difficulty
├── engine/             # authoritative session/character/turn state
│   ├── session.py      #   Session dataclass, log, combat state
│   ├── character.py    #   CharacterSheet
│   ├── turns.py        #   join / start_combat / advance_turn / end_combat
│   └── persistence.py  #   JSON session storage
├── narrator/            # the AI game master
│   ├── client.py       #   Ollama client, NarratorResponse schema
│   ├── tools.py         #   tool execution against engine state
│   ├── image_backend.py #   ImageBackend protocol + FluxWorkerBackend + create_image_backend()
│   └── comfyui_backend.py #   ComfyUIBackend — cross-platform, Docker-friendly, text-prompt-only
├── server/              # WebSocket server (FastAPI)
│   ├── app.py            #   app factory, connection lifecycle
│   ├── dispatch.py       #   incoming message routing
│   ├── narration.py      #   player action -> narrator -> tool/image execution
│   └── views.py          #   per-player state broadcast (redacted for other players)
├── frontend/            # Next.js web client (open-dungeon base, /nightwire route)
├── tests/               # pytest: ruleset, engine, narrator, server
└── docs/                # design specs, implementation plans, branding assets
```

## Screenshots

Real captures of the live frontend running its own "Neon Noir" theme — a cyberpunk visual identity independent of `open-dungeon`'s default fantasy-tabletop styling (see `ROADMAP.md`'s Phase 4 entry for the design reasoning).

<p align="center">
  <img src="docs/images/screenshots/session.png" alt="Nightwire combat turn with narration, an NPC dialogue bubble with its own avatar, and TTS audio" width="480"><br>
  <sub>Narration, dice-backed combat, and a speaker avatar next to each dialogue bubble</sub>
</p>
<p align="center">
  <img src="docs/images/screenshots/roll.png" alt="A Nightwire roll card: Stealth vs Hard 16, a d10 showing 6, the breakdown 6 +0 Cool +0 Stealth = 6 vs 16 and a red Failure badge, followed by the narrator's resolution" width="480"><br>
  <sub>A player roll: the narrator set up the moment, the player clicked Roll, and the resolution follows the real result</sub>
</p>
<p align="center">
  <img src="docs/images/screenshots/overclock.png" alt="A Nightwire roll card for Hacking vs Hard 12 with a Roll button and two overclock buttons: Yomi jack +3 and Kagerou +2 roll twice keep higher, each costing 1d6 humanity" width="480"><br>
  <sub>⚡ Overclock on the roll card: spend humanity for a better shot at the moment of risk</sub>
</p>
<p align="center">
  <img src="docs/images/screenshots/debt.png" alt="The Nightwire character sheet showing installments owed, a repo clock of six pips, Kagerou tagged Throttled and Repo crew coming, and torite notices in the log" width="480"><br>
  <sub>Chrome debt: the repo clock, a throttled implant and Saeko's crew on the way</sub>
</p>
<p align="center">
  <img src="docs/images/screenshots/tsukumogami.png" alt="A Nightwire character sheet for Hachi, a tsukumogami: the Shell and selfhood panel shows Selfhood 18, Appliance, and a Bodiless tag reading Living in a nearby machine, with installments owed and the repo clock" width="480"><br>
  <sub>Playing a tsukumogami: selfhood instead of humanity, and life without a shell</sub>
</p>
<p align="center">
  <img src="docs/images/screenshots/scene.jpg" alt="Nightwire generated scene art of a flooded underpass lit by a flickering vending machine" width="480"><br>
  <sub>A generated scene image for the current location and mood — real ComfyUI generation on a real GPU</sub>
</p>

## Contributing

Solo portfolio project — issues and ideas welcome.

## License

[MIT](LICENSE)
