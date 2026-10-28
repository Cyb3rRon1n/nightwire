# Nightwire Narrator Reliability Design: Phase 18

Status: designed, not yet implemented. Brainstormed with the owner on 2026-10-28.

## The problem (live evidence, Phases 17a–17c on `qwen3:8b`)

- **State fields the model never volunteers:**
  - `humanity_delta` for human moments: 0/2 (17c), and weak in 17a;
  - `selfhood_loss` for machine acts: 0/1;
  - `repossess` when the player hands chrome or the shell over: 0/2 (17b, 17c), with a roll or the wrong field sent instead;
  - `installments_paid` was never exercised.
- **Difficulty:** Hard on every risky roll, 13/13 across 17a–17c, despite the prompt line "most risks are Moderate".
- **Narrating refused actions:** the engine refused a bodiless climb, but the narration already said the climb happened (17c).
- **Voicing the player:** the narrator sometimes writes the player character's dialogue or actions (17a).

Owner priority: immersion over everything. The fix must be **structural or engine-side, not more prompt text.**

## Owner decisions (2026-10-28)

- **Latency budget B:** engine fixes plus one small **referee** call per turn, about +10–20 s. Pure engine-only fixes (A) and a full decide-then-narrate split (C) were rejected.
- **Difficulty:** the model rates **stakes**; the engine maps them to difficulty and caps "high" use.
- **Refused actions:** **redo the turn** once, with the refusal stated as a fact.

## Research grounding

- **Engine decides, LLM narrates.** In the Program-First Architecture pattern, code validates actions, rolls dice and updates state, and the model only narrates ([pattern](https://valaery.github.io/llm-world-engine/patterns/architectural/program-first-architecture)). No small-model benchmark exists for it.
- **Function-calling GM failure modes** match ours. With every tool available, the GM rolled repeatedly instead of updating state, and state-only functions scored best (GPT-4; [Song et al., arXiv 2409.06949](https://arxiv.org/abs/2409.06949)).
- **Strict format hurts reasoning but helps classification** ([Tam et al., arXiv 2408.02442](https://arxiv.org/abs/2408.02442)). That supports narrating freely first, then making a separate small classification call.
- **Optional fields are skippable.** Under constrained decoding the cheapest continuation is to close the object, which is consistent with our 0/n rates. The referee's fields are all required.
- **qwen3 thinking and `format` on Ollama** interact unreliably ([ollama#14645](https://github.com/ollama/ollama/issues/14645), [ollama#10809](https://github.com/ollama/ollama/issues/10809)). Nightwire never sets `think`, so it is measured in this phase, not assumed.
- Nightwire's own history points the same way: removing `start_combat` from the model (Phase 3) and two-step rolls (Phase 16) both moved decisions from the model to the engine.

## Design

### 1. The referee (`narrator/referee.py`)

**When it runs.** After the narrator call on:
- an action turn that did **not** create a pending roll;
- every roll-resolution turn (`narrate_roll`).

It is skipped on the setup turn that opens a pending roll, because the outcome is not known yet.

**Questions** (`build_questions(session, player_id) -> dict[str, list|type]`). Only the questions that apply to the actor's state right now:

| Field | Type | Asked when | Engine applies |
|---|---|---|---|
| `human_moment` | `none \| small \| big` | always | `change_humanity(+2 / +4)`; logs `[selfhood: ±N]` for a tsukumogami, as now |
| `acted_as_machine` | `none \| small \| big` | the actor is a tsukumogami | `change_humanity(−2 / −4)` |
| `gave_up_repo_item` | bool | `pending_repo` is set | `repossess` + the existing torite log line |
| `gig_paid_out` | bool | `installments_owed > 0` and not bodiless | `pay_installment(1)` |
| `got_new_shell` | bool | bodiless | `new_shell` + the existing utsusemi log line |
| `hara_unlocked_chrome` | bool | `throttled` is set | `unthrottle` + the "Owe Old Hara a favor" objective |

**The call.** A JSON schema is built from the questions, every field required (`additionalProperties: false`). The prompt is short and fixed:
- the player's action text (or the roll-resolution text);
- the narration just produced;
- one state line (e.g. `Hachi: tsukumogami, owes 4, repo pending: Kagerou`);
- one plain-language line per question (e.g. `gave_up_repo_item: did they hand over or lose the Kagerou to the repo crew in this narration?`).

Options: `think: false`, `temperature: 0`, `num_predict: 80`.

**Applying answers.** `apply_verdict(session, player_id, verdict) -> None` calls the existing engine functions in the 17b order: repossess and unthrottle before payment. World events are queued exactly as the tool path queues them.

**Failure.** Any exception, an invalid JSON response or a timeout logs `[referee error: …]`. The turn stands and nothing is applied.

**Backends.** `NarratorBackend` gains `async def judge(self, messages: list[dict], schema: dict) -> dict`:
- `NarratorClient` (Ollama) passes `format=schema`, `think=False` and the options above;
- the Anthropic and OpenAI-compatible backends implement it with their own structured output;
- fake test clients accept an injected `judge_fn`.

### 2. The narrator gives up the referee's fields

`ApplyCharacterUpdate` drops `humanity_delta`, `selfhood_loss`, `repossess`, `installments_paid`, `new_shell` and `unthrottle`. It keeps health, armor, conditions, inventory, skill points and attribute points.

The system prompt loses the sentences that told the narrator to set those fields. It keeps the guidance on how to *stage* those scenes: Arakawa's gigs, Saeko's crew, Old Hara, bodiless play and the tiers.

### 3. Stakes instead of difficulty

- `RequestRoll.difficulty` is replaced by `stakes: Literal["low", "normal", "high", "extreme"]`.
- The engine (`ruleset/difficulty.py`, `difficulty_for(stakes, recent) -> Difficulty`) maps them low → EASY, normal → MODERATE, high → HARD, extreme → EXTREME.
- **Cap.** `Session.recent_stakes: list[str]` holds the last 6 *effective* stakes. If 2 or more of them are high or extreme, a new `high` becomes `normal` and a new `extreme` becomes `high`. The effective stakes are appended after mapping.
- The pending-roll dict still carries `difficulty` (the effective one) and `dc`, so `resolve_roll`, the roll card and older saved pending rolls keep working. It also records `stakes` as the model gave them.
- The system prompt's roll sentence names stakes, with one example each.

### 4. Redoing refused turns

- In `_run_turn`, a refusal is a tool error from the narrator's own tool call on an **action** turn: a `_hold_roll` refusal or an `execute_tool` ValueError/TypeError.
- On a refusal the engine:
  - removes every log line that turn appended after the actor line (narration, audio and the tool error);
  - deletes the turn's audio files;
  - logs `[redo: {error}]`;
  - calls the narrator once more, appending `Engine: {error}. That does not happen - narrate the attempt failing or not being possible.` to the action prompt.
- The redo's own tool call is handled normally, but a refusal during a redo is only logged. There is no second redo.
- Roll-resolution turns don't redo; their roll-request refusal stays the existing "no new rolls" log line.

### 5. The player's voice

After every narrator response (action, redo and resolution), drop any segment whose `speaker`, case-insensitive and trimmed, equals a session character's `name` or `player_id`. Log `[voice filtered: {speaker}]`. Narrator segments that describe the player are untouched.

### 6. Thinking mode

`NarratorClient` gains `think: bool | None = None`, read from the env `NIGHTWIRE_THINK` (`on` / `off`; unset keeps Ollama's default). The value is passed to `chat`. The live probe measures the narrator with it on and off; the ROADMAP records the winner and the default is set to match.

## Testing

**Unit tests** (scripted `chat_fn` / `judge_fn`, no GPU):
- **Questions:** each conditional question appears only in its state; `acted_as_machine` only for a tsukumogami.
- **Verdicts:** each answer applies the right engine call and log line; none/false changes nothing; repossess and unthrottle run before payment.
- **Referee runs:** skipped on a turn that opened a pending roll; runs on action turns without a roll and on resolutions; failure logs and leaves state unchanged.
- **Schema:** the narrator's `ApplyCharacterUpdate` rejects the removed fields; old saves load.
- **Stakes:** each value maps correctly; the cap downgrades the third high in a window of 6 and turns extreme into high; the pending roll carries `difficulty`, `dc` and `stakes`; `resolve_roll` works with an old pending roll that has only `difficulty`.
- **Redo:** a refused roll triggers exactly one redo, with the engine fact in the prompt and the first narration and audio gone; a second refusal doesn't loop; resolutions never redo.
- **Voice:** a segment spoken as the player character is dropped and logged; an NPC segment is kept.
- **Think:** the `think` value reaches the chat call; the referee always sends `think: false`.

**Live A/B** on `qwen3:8b` (GPU box, 300 s client timeout), re-running the failure cases from 17a–17c:

| Case | Before | Target |
|---|---|---|
| Human moment → gain | 0/2 | ≥ 1/2 |
| Cold machine act → selfhood loss | 0/1 | hit |
| Chrome handed to the repo crew → `repossess` | 0/2 | hit |
| Gig pays out → `installments_paid` | not exercised | hit when paid |
| Share of rolls at Hard or above | 13/13 | < 50 % |
| Refused action narrated as success | 1/1 | 0 |
| Narrator voicing the player | seen | 0 |

Also record: referee latency per turn, narrator time and JSON-error rate with `think` on vs off, n and errors. Results go in the ROADMAP whatever they are.

**Browser:** none needed beyond a smoke check that the roll card still shows the difficulty and DC.

## Not in this phase

- The image upgrade (NoobAI-XL / SDXL anime workflow, research recorded 2026-10-28), which is its own phase and starts with a hardware spike.
- Changing models or sizes.
- Streaming narration.
- Making the referee judge NPC memory or world updates.
