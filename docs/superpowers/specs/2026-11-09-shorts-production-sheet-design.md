# Shorts production sheet: plan, approve, then pay

Date: 2026-11-09. Status: approved in chat by the owner (approach A + C, per-shot approval). Builds on
`2026-11-08-shorts-studio-design.md`.

## Why

Paid credits are now on the line (fal, about $13 left). The studio already stores the logline, beats, cast, floor
plan, grey-box, and per shot the camera path, lens, state, beats, acting and timed lines — but they are spread
over TOML files and the owner only ever sees finished takes. A film studio signs off a shot list, storyboard and
continuity plan before it shoots. This adds that layer: one readable **production sheet** per short, a
**pre-flight check**, and a **money gate** that refuses to spend on a shot the owner has not approved.

First user: the pilot re-shoot of `saeko-rin-izakaya` (all three shots) on `seedance-2.0-fast`; the owner picked
Seedance 2.0 because it stays with Saeko's character sheet (2.5 looks nicer but she did not look like herself).

## Research basis

Film/anime practice: script breakdown, beat sheet, shot list (size, angle, movement, lens, action, dialogue,
duration), floor plan with the 180-degree line, continuity notes (screen direction, which hand holds what,
wardrobe state), e-konte storyboard (cut, picture, action, dialogue, seconds). AI-video practice (third-party
Seedance guides; no official ByteDance prompt doc found): lock characters with the same reference set in every
shot, give each reference a role, keep one clear action per shot, match each shot's start to the previous end.
Numbers such as 2.5 spoken words per second are sensible defaults to tune, not documented rules.

Sources (third-party, checked 2026-11-09): [Scenario — Seedance 2.0 guide](https://help.scenario.com/articles/7140699840-seedance-2-0-the-complete-guide)
(reference limits, role per reference); [Magic Hour — Seedance 2.0 reference guide](https://magichour.ai/blog/seedance-20-reference-guide)
(reference tagging); [Aireiter — reference-first character consistency](https://aireiter.com/blog/seedance-2-0-reference-first-architecture-character-consistency)
(same refs every shot, drift around shot 4-5); [MindStudio — AI animated short workflow](https://www.mindstudio.ai/blog/ai-animated-short-film-seedance-2-0-workflow-cost)
(subject + action + camera + light + style + negatives); [seedance2.0 prompt skill](https://skillselion.com/skills/mapleshaw/seedance2.0-prompt-skill/seedance)
and [seedance-director](https://smithery.ai/skills/ant68451271/seedance-director) (Chinese pre-production chain:
character cards → storyboard script → storyboard images → shot-by-shot generation). Our own pilot evidence: the
S02 content-filter false positive and the 2.0-vs-2.5 likeness result (2026-11-08/09). Film/anime document fields
(breakdown, shot list, continuity, e-konte) are standard practice.

## Approach

**A — one source of truth, rendered as a sheet** (chosen), then **C — storyboard stills**. The short's TOML stays
the only copy; the sheet, the prompt and the checks are all derived from it, so nothing drifts. A hand-written
bible (rejected) would be a second copy.

## 1. Data: new fields

Shot TOML (`narrator/worlds/shorts/<slug>/shots/Sxx.toml`), all strings unless noted:

| Field | Example | Required |
|---|---|---|
| `size` | `"MCU"` (one of ECU, CU, MCU, MS, MWS, WS, EWS) | yes |
| `angle` | `"eye level, over C1's shoulder"` | yes |
| `move` | `"static"` or one move (`"slow push-in"`) | yes |
| `action` | one sentence: the one main thing that happens | yes |
| `[frame]` | `C2 = "screen-left, facing camera"`, `C1 = "foreground screen-right, back of head"` | yes |
| `[at_start]` / `[at_end]` | per character: pose, gaze, what is in which hand | yes |
| `[props]` | `C1 = "sake cup in chrome right hand"` | when anyone holds something |

Existing `summary` stays (it feeds L1). Short TOML gains `line_rule` (screen direction in words, e.g.
`"C1 is screen-right of C2 in every shot"`) and `model` (default model for the short, here `seedance-2.0-fast`).
Character locks are not typed again: they come from each design's `required` tags plus a short `lock` line per cast
member in `short.toml` `[locks]` for things the tags miss (e.g. `C1 = "chrome right hand, amber wrist light, red trim"`).

Missing new fields are reported by pre-flight; `validate_short` only checks values that are present (size in the list, cast ids), so old shorts still pass `check`.

## 2. The production sheet page

Built by `python -m tools.shorts sheet <slug>` into `design-data/shorts/_site/<slug>/sheet/index.html` and published
with the existing rsync. Sections, top to bottom:

1. **Header** — title, logline, runtime, model, cost estimate vs remaining budget, approval status per shot.
2. **Cast lock** — per character: turnaround, portrait, expressions, props side by side, and the lock line
   (required tags + `[locks]`).
3. **Location and look** — place image, floor plan, `line_rule`, style text (sent on every shot).
4. **Story beats** — the short's beats, each tagged with its shot.
5. **Shot list** — one row per shot: storyboard still (section 5) or grey-box frame, size/angle/lens/move, action,
   frame, start/end, props, timed lines, refs attached (after the model's skip list), estimated cost, pre-flight
   result, and **Approve / Change / Reject** buttons with a note box.
6. **Dialogue timeline** — all lines on one strip across the whole short.
7. **Continuity strip** — shot N `[end]` beside shot N+1 `[start]`, mismatch flags from pre-flight.
8. **Prompt** — collapsible: the exact text and reference list that will be sent, so what is approved is what is paid for.

## 3. Pre-flight checks

`python -m tools.shorts preflight <slug> [shot]` — pure functions, each returns problems as strings:

- required fields present (section 1);
- dialogue pace: words in the shot's lines ÷ (shot seconds − 1.0 s of air) ≤ 2.5 words/s;
- one action: `action` is one sentence and `move` names at most one move;
- continuity: each character in both shots keeps the same hand/prop in `end`→`start` (prop names compared), and
  `frame` sides agree with `line_rule` (a character listed screen-left/right must not swap without `cross_ok = true`);
- refs: every file exists, and the count after the model's `skip` fits the model's image limit;
- content filter: none of a project word list that tripped ByteDance's filter (starts with the S02 false positives:
  "plug it in", "open it", "stuck" next to a body part) — warn, not fail;
- position words outside L5 (existing `position_problems`);
- budget: estimate fits `budget_usd − spent`.

## 4. Approval and the money gate

- The sheet's buttons call the existing review API (`PUT /designs/api/images/<id>`) with id
  `plan--<slug>--<shot>--<fp>`, where `fp` = first 10 hex of SHA-256 over the exact prompt text plus each reference's
  label and file hash. Verdicts: `keep` = approved, `fix` = change (note goes to Claude like image notes), `reject`.
- `tools.shorts verdicts` (existing) also syncs plan verdicts into `design-data/shorts/<slug>/approvals.json`.
- Editing a shot changes `fp`, so the old approval no longer matches; the sheet shows "changed since approval".
- `submit` order: pre-flight (any failure stops) → approved with current `fp` → budget → retry cap (2 extra takes per
  shot beyond the first; `retry_cap` in short.toml raises it) → spend. `--override "<reason>"` skips the approval
  check only; the reason is written to the ledger row and shown on the sheet. Budget and pre-flight cannot be skipped.

## 5. Storyboard stills (C)

`python -m tools.shorts stills <slug>` renders one opening-frame still per shot on the GPU box (free, one job at a
time, ComfyUI VRAM freed after): the existing scene-image path (`tools.imagegen --kind subject` / scene workflow)
with the characters' tags + locks, the place, and the shot's size/angle/frame wording, at the model's aspect. Taste
check (`python -m tools.taste`) first, as for every render batch. Stills land in `design-data/shorts/<slug>/shots/
Sxx/still.png`, show on the sheet, and are approved with the shot (the still's hash is part of `fp`).

Sending the still to the model: Seedance 2.0 takes 9 images; the pilot already sends 8 character sheets + place.
The approved still **replaces `place.png`** (it contains the place) and is labelled `start_frame.png`, with L1
saying "match start_frame.png as the opening frame". Without a still, nothing changes.

## 6. Out of scope

Music/sound plan, colour-script swatches, wardrobe-change tracking across scenes, multi-scene films, editing the
plan from the web page (the owner comments; Claude edits TOML).

## 7. Testing

Unit tests per check (pass and fail cases), fingerprint stability (same inputs same `fp`; any prompt or ref change
new `fp`), submit gate order (unapproved, stale approval, over budget, over retry cap, override logged) with the
fal backend faked, sheet build smoke test on the pilot. CI must stay green. Real verification: build the pilot's
sheet, publish, owner approves on the page, `submit` refuses before and passes after.

## 8. Order of work

1. Fields + validation, pilot TOML filled in. 2. Pre-flight. 3. Fingerprint + approvals + submit gate.
4. Sheet page. 5. Stills. Then the owner reviews the pilot sheet, approves shots, and the re-shoot on
`seedance-2.0-fast` (~21 s, about $5 of the ~$13 left) runs only on approved shots.
