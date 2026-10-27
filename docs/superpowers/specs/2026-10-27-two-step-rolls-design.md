# Nightwire Two-Step Player Rolls Design: Phase 16

Status: designed, not yet implemented. Brainstormed with the owner on 2026-10-27.

**Numbering.** The cyberware, humanity and debt spec (`2026-10-27-cyberware-humanity-design.md`) moves to Phase 17. The owner put this phase first because it closes the biggest immersion gap at the lowest cost.

## The actual gap

When an action needs a roll, the narrator's single response does two things at once: it narrates, and it calls `request_roll`. The code in `server/narration.py::handle_action` then runs in this order:
1. it logs and voices the narration;
2. *only after that*, it executes the roll;
3. it logs the result as a bracketed `[request_roll: {...}]` line.

The consequences:
- **The narrator never knows the outcome.** In the turn where the roll happens, the narration was written before the dice existed, so a failed roll can sit under prose that implied success.
- **The narrator never learns it later either.** Every bracketed line is filtered out of later prompts by `_build_messages`, the same filter that keeps tool annotations out of the story.
- The open gap noted in project memory since 2026-09-06 described it as "roll outcomes are bracket-filtered so the model never sees its own dice results (no feedback loop)", and it named "two-phase turn for rolls" as a top-3 fix.

Owner priority (2026-10-27): **immersion over everything**. Free typing stays the core of play.

## Owner decisions (2026-10-27)

- **The player rolls**, Baldur's Gate 3-style. The narrator sets up the moment, the player clicks **Roll** and sees the die land with their modifiers, then the narrator tells what happens. Party members see it too.
- **Approach A:** setup, then the player rolls, then a resolution call. There is one extra AI call, and only on roll turns. The click is a natural dramatic pause.
- The engine flow and the UI and testing sections were approved as presented.

## Research grounding

- **Tabletop practice.** Rules systems resolve before the GM describes the consequence: you declare an action, roll, then hear the outcome. Cyberpunk RED and The Sprawl, nightwire's own touchstones, work this way (general knowledge).
- **Baldur's Gate 3.** Nightwire already cites it as its CRPG precedent. The player-facing d20 roll in dialogue shows the DC and modifiers, the player clicks to roll, and the conversation branches on the result. This is the "player owns the moment" model the owner chose.
- **LLM game masters.** The Phase 15 research pass recorded two relevant designs [S]:
  - Grinmar "locks in the outcome before writing narrative";
  - RPG-MCP: "LLMs never directly mutate world state".
  
  Both support resolving first and narrating second.
- **Nightwire's own reliability history.** Mechanical triggers controlled by the player are more reliable than ones the model has to trigger itself; `start_combat` was removed from the narrator's tools for this reason. Here the model still *proposes* the roll (skill, attribute, difficulty, reason). The engine and the player own execution and timing.

## Design

### Turn flow

**1. The action turn** (`handle_action`, unchanged entry point).
- The narrator's normal call runs.
- If its response has `tool == "request_roll"`, the engine does **not** roll. Instead:
  - it validates the arguments exactly as today, forcing `player_id` to the actor;
  - it stores them in `session.pending_rolls[player_id]` as the request's argument dict;
  - it logs `[roll pending: {...}]`, which the UI uses to show the roll card.
- The setup narration is logged and voiced as usual.
- The rest of the turn runs unchanged: the image cooldown, compaction and saving.

**2. While a roll is pending.**
- An `action` from that player raises `ValueError("roll first")` through the existing error path.
- Other players act normally.
- Combat turn order is unaffected.

**3. The roll.** A new `{"type": "roll"}` message runs a new `handle_roll(session, narrator_client, store, image_backend, tts_backend, player_id)` in `server/narration.py`, routed in `server/app.py` next to `action`.
- It requires a pending roll for that player; otherwise it raises `ValueError("no roll pending")`. Only the owner can resolve their roll, because the message is keyed by the sender's `player_id`.
- It pops the pending request and runs the existing `execute_tool(session, "request_roll", args)`. The math is unchanged: `1d10 + attribute modifier + skill rank` vs DC (easy 8, moderate 12, hard 16, extreme 20); a natural 10 is always a clean success and a natural 1 is always a failure.
- It logs **a visible narrative line** with no brackets, so later prompts include it:
  - `"{name} rolls {Skill} ({Attribute}) vs {Difficulty}: {outcome text} ({die} + {attr_mod} + {skill_mod} = {total} vs {dc})."`
  - The outcome text is "a clean success", "success with a complication" or "a failure".
  - A natural 10 or 1 adds " — a natural 10" or " — a natural 1".
- It logs `[roll: {...result dict plus skill, attribute, difficulty, reason, name}]` for the UI's die display.

**4. The resolution call.** It runs the shared turn pipeline (below) with:
- **the input text** `"Roll result for {name}: {outcome text} on {reason}. Narrate what happens now, true to that result."`;
- **the actor line**: none, because the player didn't type anything, and the visible roll line already sits in the log.

If the resolution response contains `request_roll`, it is **ignored**, and `[tool error: no new rolls during a roll resolution]` is logged. All other tools work normally: `apply_character_update` for damage, `update_world`, `remember_npc` and `image_request`.

### Shared turn pipeline (refactor)

The body of `handle_action` after its input validation moves into one helper:

```
_run_turn(session, narrator_client, store, image_backend, tts_backend,
          player_id, prompt_text, actor_line: str | None, allow_roll: bool)
```

The helper does the following, in order:
1. build messages from `prompt_text`;
2. call the narrator;
3. append `actor_line` if given;
4. log and voice the segments;
5. run the tool, branching on `request_roll` versus `allow_roll`;
6. run the image cooldown and generation;
7. run compaction.

Callers:
- `handle_action` calls it with `actor_line=f"{player_id}: {action_text}"` and `allow_roll=True`.
- `handle_roll` calls it with `actor_line=None` and `allow_roll=False`.

There is no behavior change for non-roll turns. Every existing `handle_action` test must pass unchanged.

### Data model

- `Session.pending_rolls: dict[str, dict] = {}`, persisted through the existing JSON round-trip. A session saved before this change loads with `{}`.
- `StateView` / `build_view` exposes `pending_rolls`. It is per-player public data: skill, attribute, difficulty, DC and reason are visible to the whole party, which matches "party members see it too". Each pending roll includes its DC (`Difficulty[...]`) so the card can show the number.

### Narrator guidance (system prompt)

`server/__main__.py::build_system_prompt` gains one rule plus a good and a bad example:

> When you call request_roll, narrate only the lead-up to the moment of risk and stop before the result — the player rolls next, then you'll be told the outcome and narrate it. Example: player sneaks past a guard → narrate the guard turning toward the curtain, the creak of a floorboard, then request_roll (stealth, hard). Don't narrate whether they made it. When you're given a roll result, narrate what happens true to that result; never contradict it.

### UI (`frontend/src/app/nightwire/page.tsx` and a new `RollCard.tsx`)

**Roll card.** It renders from `pending_rolls` and the `[roll pending: …]` / `[roll: …]` log lines.
- **Pending:** the reason; `Skill (Attribute) · Difficulty DC`, for example *Stealth (Reflexes) · Hard 16*.
  - The roller sees a large **Roll** button.
  - Everyone else sees *"Waiting for {name} to roll…"*.
  - The roller's composer is disabled with the hint "Roll first".
- **Rolled:**
  - a short CSS-only d10 tumble (no new dependency) that lands on the die value;
  - then the breakdown `7 + Reflexes 2 + Stealth 1 = 10 vs 16`;
  - and an outcome badge: **Clean success** (green), **Complication** (amber) or **Failure** (red);
  - a natural 10 or 1 gets a brief flash;
  - the resolution narration follows as a normal turn.
- **Visible roll line:** the non-bracket narrative line renders as a regular story line, so the card and the story stay consistent.
- **Accessibility:** the outcome is also written as text (not color alone), the Roll button is keyboard-focusable, and the animation respects `prefers-reduced-motion`.

## Testing

**Unit tests (pytest):**
- `request_roll` in an action turn stores a pending roll, doesn't roll, logs `[roll pending: …]`, and still logs and voices the setup narration;
- a second action from the same player while pending raises "roll first";
- another player's action still works while one roll is pending;
- `roll` with nothing pending raises "no roll pending";
- `roll` resolves with the correct math (patch `random.randint`) and writes the exact visible line, including natural 10 and natural 1 suffixes;
- `roll` writes the `[roll: …]` line and clears the pending roll;
- the resolution call's prompt contains the result text;
- a `request_roll` in a resolution response is ignored with the tool-error line;
- tools in a resolution (damage) apply;
- `pending_rolls` survives a persistence round-trip, and an old session file loads with `{}`;
- the view exposes `pending_rolls` with the DC;
- every existing `handle_action` and narration test passes unchanged (the refactor guard);
- the system prompt contains the new rule.

**Live verification** on real `qwen3:8b` (GPU box `192.168.10.19`, 300s client timeout; the dev box has no GPU):
- an 8-action probe of risky actions (stealth, combat, persuasion, hacking, athletics), with the probe acting as the player and sending `roll` whenever a roll is pending;
- **Report:**
  - how often a roll is requested;
  - **outcome leakage**: setup narration that already states success or failure, judged per turn by reading it and listed with the evidence;
  - **result fidelity**: the resolution matches the real outcome, with no "you slip past" after a failure;
  - whether consequences apply (damage on failure);
  - the extra latency on roll turns;
  - schema and tool errors;
  - n.
- **UI:** checked in a real browser: the card, the Roll button, the tumble, the badge, the waiting state for a second client, and the disabled composer.

## Not in this phase

- **Rerolls, luck points, advantage or disadvantage, and group or opposed rolls.** Cyberware's Kagerou overclock in Phase 17 will add "roll 2d10, keep the higher" through the same roll path.
- **A separate decide-first call** (approach B, rejected).
- **Timeouts or auto-roll** for an idle roller.
- **GM-hidden rolls.**
- **Streaming narration.**
