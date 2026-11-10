# Shorts production package: nothing left for the video model to guess

Date: 2026-11-10. Status: design approved in chat by the owner (approach A with B as fallback; owner signs off every
visual). Builds on `2026-11-09-shorts-production-sheet-design.md` (sheet, pre-flight, approval fingerprint, money gate),
which stays in force; this spec adds to it and changes how a shot is generated.

## Why

The pilot re-shoot on Seedance 2.0 fast (S01 t005, S02 t002, S03 t002) looked good per shot but did not hold together:

- **Room changed.** S01 had street windows the izakaya never had. The place has one interior image (toward the shelves);
  S02/S03 look the other way and the model invented that side.
- **Weather appeared.** Our own style line said "rain heard beyond the noren" and the place's design tags include
  "rain, wet street" (from the exterior). Nothing said what must not be visible.
- **Seating changed.** Side by side in S02, across the counter in S03. Blocking lived only in the grey-box video.
- **Wardrobe changed.** Jacket open in S01/S02, closed in S03 (the closed-jacket sheet came between them).
- **No pinned opening.** Every shot started from the model's own composition.

fal fact (API schema, checked 2026-11-10): Seedance 2.0 **reference-to-video** takes up to 9 `image_urls` and 3
`video_urls` cited as `@Image1`.. / `@Video1`.., but no first or last frame. **Image-to-video** takes `image_url` (start
frame) and optional `end_image_url`, but no extra references. Neither has a negative-prompt field. The two modes cannot be
combined. Practitioner workflows for consistent multi-shot work are keyframe-first: approve a still per shot, then animate
it (no controlled study found; this is the consensus of creator guides).

Research sources (third-party unless noted): fal API pages for
[reference-to-video](https://fal.ai/models/bytedance/seedance-2.0/reference-to-video/api) and
[image-to-video](https://fal.ai/models/bytedance/seedance-2.0/image-to-video/api) (official);
[Magic Hour reference guide](https://magichour.ai/blog/seedance-20-reference-guide) (modes exclusive, per-ref roles,
inline exclusions); [cutout.pro storyboard workflow](https://www.cutout.pro/learn/blog-seedance-2-0-storyboard-workflow-cutout-frames/)
(shot table: environment, plate, character per shot; fixed camera height); invideo FAQs on
[spatial consistency](https://invideo.io/faq/how-do-you-maintain-spatial-consistency-across-multiple/) and
[reverse angles](https://invideo.io/faq/how-do-you-generate-the-reverse-or-opposite-camera-angle/) (one plate per angle,
name the angle); [ai-flow storyboard → Seedance](https://www.ai-flow.net/templates/storyboard-to-cinematic-video-with-seedance-2.0)
and [renoise storyboard guide](https://renoise.ai/guides/ai-storyboard) (keyframe-first). Expect about 3 takes per usable
shot (reviewer reports).

## Decisions

- **A with B as fallback.** Plates and keyframes are rendered locally on the GPU box (free, our art style). A shot whose
  composition the local route cannot get after 3 rounds may use a fal image model with the sheets as references
  (cents per image; needs the owner's OK each time, logged in the ledger).
- **Owner signs off every visual:** each plate, the scene bible, every keyframe, then each shot as now.
- **Default generation mode: image-to-video** from approved keyframes. Reference-to-video stays available per shot
  (`mode = "reference"`) for shots where it is the better tool; both go through the same gates.

## 1. Data

### Short TOML: new tables

```toml
[scene]                       # sent word for word in every shot of the short
time = "late night, about 01:00"
weather = "indoors; no windows; no rain and no street visible"
set = "a narrow izakaya: one long wooden counter with guest stools on one side, bottle shelves behind it, the noren doorway in the left wall"
light = ["amber paper lanterns over the counter", "red neon sign on the back wall", "yellow strip light under the top shelf",
         "faint cool backlight from the kitchen pass"]
not_visible = ["windows", "street", "rain", "daylight", "other customers"]

[wardrobe]                    # per cast member: the outfit sentence for this short
C1 = "cropped navy jacket with red trim zipped to the high collar, black trousers, chrome right hand with amber wrist light"
C2 = "white hoodie, hood down after S01, white-silver cyberdeck on a strap across her chest"

[blocking]
seating = "C1 and C2 sit on guest stools side by side facing the counter; C2 on C1's left"
```

`style` keeps only the look (line, colour, cel shading, bloom); weather and sound words move out of it. `[locks]` stays
for identity details the sheets miss. Wardrobe and blocking changes inside a short must be declared per shot
(`wardrobe_change = ["C2"]`, `blocking_change = true`), like `prop_change` today.

### Shot TOML: new fields

| Field | Example | Required |
|---|---|---|
| `plate` | `"toward-door"` (a plate name of the short's place) | yes |
| `mode` | `"i2v"` (default) or `"reference"` | no |
| `motion` | one or two sentences: action + camera only, no description of the frame | yes for i2v |
| `end_frame` | `true` when someone enters/leaves or the composition must land somewhere specific | no (pre-flight requires it when the cast in `[at_start]` and `[at_end]` differs) |

Keyframes live in `design-data/shorts/<slug>/shots/Sxx/keyframe-start.png` and `keyframe-end.png`.

### Place plates

`design-data/<place>/plates/<name>.png` plus `narrator/worlds/designs/<place>.plates.toml`:

```toml
[[plate]]
name = "toward-shelves"
view = "from the guest stools toward the counter and bottle shelves"
source = "play.png"           # an existing approved image may be adopted as a plate
[[plate]]
name = "toward-door"
view = "from behind the counter toward the guest stools and the noren doorway in the left wall"
```

Plates are empty rooms (no people), night, the same light sources as the scene bible. A plate is approved like a design
sheet (review id `plate--<place>--<name>`), so later shorts at the same place reuse it.

## 2. Pipeline and gates

1. **Plates** — `python -m tools.shorts plates <slug>` renders every plate the short's shots name that does not exist yet,
   on the GPU box (one job at a time, ComfyUI VRAM freed after, taste check first). New angles are made from the approved
   plate's look: the place's interior tags + `[scene]` set/light + the plate's `view`, with the approved plate's palette;
   the owner reviews on the AI Lab designs review (verdict buttons), at full size.
2. **Scene bible** — shown at the top of the production sheet with its own approve button (`plan--<slug>--scene--<fp>`).
3. **Keyframes** — `python -m tools.shorts keyframes <slug> [shot]` renders start (and end) keyframes:
   the grey-box camera frame at that time as a **depth guide** (Blender renders a depth pass alongside the existing
   frames) so composition, seating and screen sides match the grey-box; the shot's plate as the background guide; each
   character's tags + locks + wardrobe in their own region; then `fix_area` passes for faces, hands and outfit against the
   turnarounds. Several seeds per keyframe; Claude picks the best 2-3 per keyframe, reviews each at full size beside the
   turnaround (house rule), and the owner approves one on the production sheet. Fallback B after 3 failed rounds:
   a fal image model given the character sheets + plate + grey-box frame, owner OK first.
   *To verify in the plan:* a depth ControlNet (or equivalent) that works with the house SDXL v-pred model on 8 GB; if a
   download is needed it goes to the owner for OK.
4. **Prompt** — i2v prompt = `motion` + the scene bible (time, weather, set, light) + wardrobe + seating +
   screen positions (`[frame]`, `line_rule`) + "not visible: …" as an inline exclusion sentence + style + timed lines.
   Locked-off camera sentence for `static`. Reference mode keeps the `@ImageN` role header (commit dfc4bc8) and adds the
   same bible text; its place image is the shot's plate, not always `play.png`.
5. **Pre-flight** — new checks (problems unless noted):
   - every shot has an approved plate and approved keyframes (start; end when required);
   - the scene bible is approved and unchanged;
   - no shot text (beats, acting, lines, motion, style) uses a `not_visible` word or a weather word that contradicts
     `[scene].weather` (e.g. "rain", "wet street") — warning for dialogue, problem elsewhere;
   - wardrobe and seating unchanged between shots unless declared;
   - an end keyframe exists when the cast in frame changes within the shot;
   - existing checks (pace, one action, continuity, refs, filter words, budget) stay.
6. **Approval fingerprint** now also covers the mode, the scene bible text and the keyframe file hashes.
7. **Submit** — unchanged gate order (pre-flight → approval → retry cap → budget → spend), new endpoints below.

## 3. fal backend and ledger

- Add `seedance-2.0-fast-i2v` and `seedance-2.0-i2v` (`bytedance/seedance-2.0[/fast]/image-to-video`, fields
  `image_url`, `end_image_url`, `prompt`, `duration`, `resolution`). Rates are checked on fal's pricing page in the plan
  and written into `RATES`; the sheet shows the estimate.
- A job that fails with fal's content block (422 on result fetch, `partner_validation_failed`) is recorded as
  `status = "blocked"` with the shot, mode and ref labels, and the message says "blocked by moderation" (not "network
  error").
- `python -m tools.shorts ledger-sync <slug> --balance 3.29` (owner reads the balance off fal's billing page; Claude
  never reads billing with the key) writes one adjustment row so the gate's remaining budget equals the real balance.

## 4. Proving it on the pilot

1. Fill `[scene]`, `[wardrobe]`, `[blocking]` for `saeko-rin-izakaya`; strip weather words from `style`; set each shot's
   `plate`, `motion`, `end_frame`.
2. Plates: adopt `play.png` as `toward-shelves`; render `toward-door` (S02/S03 reverse side) and `along-counter`
   (S01's view from the far end) → owner approves.
3. Keyframes for S01 (start without Rin, end with Rin), S02 (start), S03 (start, end with the data jack turned over)
   → owner approves.
4. Sync the ledger to the real balance; re-shoot what $3.29 allows, owner approving each shot first.

The GPU queue for this is long; Nightwire play tests can be slotted between keyframe batches on request.

## 5. Out of scope

Music and sound design; multi-location shorts (one place per short for now); editing plates or keyframes from the web
page (the owner comments, Claude edits); automatic take picking.

## 6. Testing

Unit tests for: scene/wardrobe/blocking parsing and validation; each new pre-flight check (pass and fail); i2v prompt
assembly (bible present, exclusions sentence, no frame description duplicated from the keyframe); fingerprint changes
when the bible text or a keyframe file changes; fal i2v request body (start, optional end, no extra refs) with the backend
faked; blocked-job ledger row; ledger-sync arithmetic. Real verification: plates and keyframes rendered on the GPU box and
approved by the owner; one paid i2v shot whose room, light, weather, wardrobe and seating match its keyframe.
