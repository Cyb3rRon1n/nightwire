# Nightwire — instructions for AI sessions

Read `ROADMAP.md` first — it's the durable source of truth for what's decided, what's built, and why.

## The standing rule: independent research, never oracle-precedent

This project was designed by researching real, external prior art for every non-trivial decision — never by copying `oracle` (the owner's sibling D&D-flavored AI-DM project) just because oracle already does it that way. This rule was established explicitly and firmly partway through the design process, after several early decisions leaned on oracle as justification and had to be re-researched and rewritten from scratch. Keep following it:

- **Ground every design decision in real, external sources** — comparable projects (open-dungeon, dungeon-ultimate, skeinkeeper, dungeon-master-ai), real tabletop RPG systems (Cyberpunk RED, Shadowrun, The Sprawl, CY_BORG, Neon City Overdrive), real CRPG precedent (**Baldur's Gate 3**, Solasta: Crown of the Magister, Divinity: Original Sin 2, Fallout's VATS), and **Cyberpunk 2077** specifically — it's this project's own stated aesthetic touchstone and has already overruled tabletop-only research more than once (see the Roles section of the ruleset spec for a concrete example: a tabletop-focused pass argued for 6 player roles, but checking CP2077 itself — which runs on just 3 official archetypes with no dedicated medic build — pulled the roster back down).
- **Where oracle happens to reach the same conclusion, that's coincidence confirmed by independent research, not the reasoning.** Every spec in `docs/superpowers/specs/` documents real citations for its choices — if you're about to write "because oracle does this," stop and research the actual question instead.
- **The one explicit exception**: `ROADMAP.md`'s "Why a fresh project" section names a short list of *lessons* (not code, not architecture) knowingly carried over from oracle's own hard-won reliability testing — e.g., structured JSON output beating native tool-calling on local models. That's a disclosed, deliberate carry-over, not a precedent to extend elsewhere.

When picking up new design work (Phase 3's narrator prompt tuning, Phase 4's frontend components, later phases), the pattern that's worked well this whole project: research first (real external sources, not memory/assumption), present findings with citations, then decide — the same way every existing spec in `docs/superpowers/specs/` was built.

## Process

This project uses the `superpowers` skill set for design and implementation:
- New design work → `superpowers:brainstorming` (research → questions → approaches → design → spec)
- Turning a spec into buildable steps → `superpowers:writing-plans`
- Executing a plan → `superpowers:subagent-driven-development` (the pattern used for both Phase 1 and Phase 2a so far — fresh subagent per task, review after each, one final whole-branch review, fix real findings before merging)

Every phase so far has an implementation plan at `docs/superpowers/plans/` and a design spec at `docs/superpowers/specs/` — read both before touching a phase's code.
