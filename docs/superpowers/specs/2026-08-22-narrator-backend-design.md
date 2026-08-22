# Nightwire AI GM / Narrator Backend Design — Phase 3

Status: designed, not yet implemented. Builds on the ruleset (Phase 1) and core engine (Phase 2) specs. Every choice below is grounded in independent external research — no oracle-precedent citations.

## Default local model

**Qwen3, 7-8B class** — not a default carried over from any prior project's own testing. Real grounding:
- The Berkeley Function-Calling Leaderboard (BFCL, Gorilla project) is a real, current, AST-based tool-calling benchmark (2000+ question/function/answer pairs, serial/parallel/multi-turn) — the actual external evidence base for this choice, not an internal anecdote ([Gorilla leaderboard](https://gorilla.cs.berkeley.edu/leaderboard.html)).
- Qwen3 has a native tool-calling template with direct Ollama integration, and reasons meaningfully better than 2024-era Qwen2.5 finetunes — Qwen2.5-7B/14B are now explicitly characterized as "legacy budget picks" in current (2026) local-LLM guides, not the current best choice at this size ([InsiderLLM — best local LLMs for function calling](https://insiderllm.com/guides/function-calling-local-llms/)).
- Purpose-built tool-use fine-tunes (**Qwythos-9B**, **ToolACE-8B**) show real schema-adherence gains over generic instruct models at comparable size — worth evaluating as a secondary option once the engine exists to test against, not blocking the initial default.

**Hosted API remains a secondary option** (per the ruleset spec's backend policy) — for quality/speed flexibility, accepting the known content-refusal tradeoff already documented.

## Content policy: standard instruct model, not abliterated

Real, specific evidence against defaulting to an abliterated ("uncensored") model, despite the project's full-genre-grit content goal:

- **Abliteration** (activation-based surgical removal of refusal directions) is a different technique from genuine uncensored fine-tuning (Dolphin-style retraining on uncensored data) — they carry different risk profiles, not interchangeable "uncensored" options.
- **Documented tool-calling degradation**: abliterated Qwen variants show measurably weaker tool-call/MCP performance than their base models ([WebDecoy — abliterated models explained](https://webdecoy.com/blog/wtf-are-abliterated-models-uncensored-llms-explained/)). General capability loss is also measured, not just anecdotal — reduced coherence, lower benchmark scores, with structured/math reasoning the most sensitive category ([abliteration.ai — does abliteration ruin models](https://abliteration.ai/docs/does-abliteration-ruin-models); [arXiv 2512.13655](https://arxiv.org/pdf/2512.13655)).
- Community/practical consensus is that genuine fine-tuned uncensored models handle function calling more reliably than abliterated ones; abliteration suits pure creative-prose generation where fluency matters more than structured accuracy ([arXiv 2607.05842](https://arxiv.org/html/2607.05842)) — exactly the opposite of what Nightwire needs, since the narrator must reliably call tools *and* write mature prose in the same pass.

**Decision**: default to the standard Qwen3 instruct model with a permissive, non-hedging system prompt (open-weight local models are already far less restrictive on fictional mature content than hosted APIs, since there's no external safety layer in the loop at all). Reserve a genuine Dolphin-style fine-tune as a fallback **only if live play-testing shows the base model actually refuses reasonable mature-fiction content** — verified the same way every other reliability claim in this project gets verified: a real, repeatable test against a live model, not assumed upfront.

## Structured output over native tool-calling (local path)

Already established in the Phase 2 spec's narrator-backend section (local/open-weight models specifically, tied to training/quantization rather than raw size) — carried forward here as the resolution mechanism for the mechanical decision step (dice rolls, character/NPC state changes, world updates). Hosted-API backends may use native tool-calling instead, since the documented reliability risk is specific to the local/open-weight path.

## Tool surface

Derived directly from the ruleset (Phase 1) and engine (Phase 2) specs, not re-invented here:

- **`request_roll`**: dice notation implied by the ruleset's `1d10 + attribute + skill vs DC` mechanic — the narrator requests a roll before narrating an uncertain outcome, gets back a real result plus which of the three outcome bands it landed in, and narrates to match rather than deciding the outcome first.
- **`apply_character_update`**: Health/Armor changes, condition changes, cyberware install/removal, inventory changes — mirrors the "engine applies real state, DM narrates it" split the ruleset assumes throughout.
- **`update_world`**: location, scene mood, active objectives — narrative continuity state, same shape the engine's Session/world model already needs to track regardless of narrator backend.
- **`start_combat` / `end_combat`**: explicit, narrator-callable but ultimately player-triggered per the engine spec's turn-model section — the narrator doesn't unilaterally decide combat has started; a player action does, matching the engine design's own reasoning for why this can't be inferred from narration alone.

Exact schemas (field names, types) are implementation-detail work once real code exists to validate against — not blocking this design.

## Reliability measurement

A real, repeatable measurement harness from the first backend implementation, not retrofitted after informal testing — standard practice for this kind of system (deterministic seeded scripted-client testing is documented industry practice for multiplayer/game-server testing generally, per the Phase 2 spec's testing section). Concretely: fixed test scenarios run against the real local model, `--repeat N` style, scoring real tool-call correctness — before trusting any specific reliability claim (a specific model choice, a specific prompt wording, whether the base instruct model actually needs the Dolphin-fallback path) as more than a hypothesis.

## What's deliberately deferred

- Exact tool schemas (field-level detail) — implementation-phase work.
- The Dolphin-fallback decision itself — stays hypothetical until real play-testing either confirms or rules out a refusal problem with the base Qwen3 instruct model.
- Prompt engineering specifics (the actual system prompt wording for tone/content policy) — a real design pass once there's a model to test prompts against, not speculative text written in a vacuum.
