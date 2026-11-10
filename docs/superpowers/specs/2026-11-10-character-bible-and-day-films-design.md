# Character bible v2, look book and day films

Date: 2026-11-10. Status: design approved in chat by the owner. Builds on
`2026-11-10-shorts-production-package-design.md` (scene bible, plates, gates) and changes how character shots are made.

## Why

The owner wants near-wordless "day in the life" films per Nightwire character with the lonely feel of Blade Runner 2049,
planned like a whiteboard before anything is rendered. Two findings block that today:

- **The reference sheets contradict each other.** Saeko's turnaround (high-cut bodysuit, bare thighs, heels) disagrees
  with her portrait/expressions (jacket zipped to a high collar) and with the pilot's wardrobe text ("black trousers");
  her X cheek scar is on the portrait but in no tag; Rin's pink tips are missing on most expressions; portraits and
  expressions are lit strong blue, which video models copy into warm scenes. No workflow is more consistent than its
  references.
- **Local character keyframes fail.** Three rounds (lineart guide, then weighted prompts, then room-only guide) gave
  off-model or missing characters, wrong poses, faces instead of backs of heads, and Saeko's jacket rendered open
  despite the avoid list. The owner: drafts don't need characters; grey stand-ins are enough.

## Decisions (owner, 2026-11-10)

- Start with one character (Saeko): bible v2, then her day film end to end, then the next character.
- Saeko has two outfit states: **work** (approved jacket + bodysuit, zipped to the collar, dark tights/leggings, boots;
  covered and filter-safe) and **off-duty** (plain coat or oversized sweater).
- **No local character renders.** Drafts show grey stand-ins; identity comes only from the v2 sheets.

## 1. Character bible v2

Design TOML (`narrator/worlds/designs/<slug>.toml`) gains:

```toml
identity = ["X-shaped scar on the right cheek", "chrome right hand with an amber ring light on the wrist",
            "long straight black hair, blunt bangs", "brown eyes"]

[wardrobe.work]
text = "cropped navy jacket with red trim zipped to the high collar, black bodysuit, dark opaque tights, black boots"
tags = "cropped jacket, high collar, zipped jacket, black bodysuit, black pantyhose, black boots"

[wardrobe.offduty]
text = "long dark wool coat over a grey knit sweater, black trousers, flat boots"
tags = "long coat, sweater, trousers, boots"
```

Sheets per state: `design-data/<slug>/wardrobe/<state>/{turnaround,portrait,expressions,props}.png`, all on neutral grey
in neutral light (the approved E-on-grey turnaround look extended to portrait and expressions), made with the existing
sheet pipeline from the approved design + state tags + identity, with `fix_area` passes. Claude checks every sheet at full
size against the others of its set (identity marks present, same outfit, same hair) before it reaches the inbox; the
owner approves each set in the Review inbox (id `sheet--<slug>--<state>--<sha10>` over the set's files).

Shorts reference a state instead of free text: `[wardrobe] C1 = "work"`. The prompt builder then uses the state's `text`,
the design's `identity` (always sent), and the state's sheets as references. Free-text wardrobe stays allowed for designs
without states (old shorts). The `shorts/turnaround.png` closed-jacket copy is retired once `work` exists.

## 2. Look book

`docs/look-book.md` (owner-readable) plus `tools/shorts/lookbook.py` (data): preferred sizes WS/EWS/MS, moves
static/slow push-in/slow pan, faces small, away or in profile, silhouettes and reflections, long holds, ≤ one short line
per shot; light: one strong source, haze, sodium/amber against cold cyan, deep blacks. Pre-flight adds **warnings**
(not problems) for high-risk shots: a talking face at MCU or closer, more than one line, more than two people in frame,
a camera move plus character action in the same shot. The production sheet shows them so the owner sees the risk when
approving.

## 3. Drafts: grey stand-ins, no local character renders

Keyframe rendering of characters (Task 13's region/ControlNet route) is retired for characters. Instead:

- **Draft board** per shot (start, and end when needed): the approved plate warped to the shot's camera is not possible,
  so the board is the grey-box frame (`guide/<which>.png`) composited over a darkened copy of the shot's plate at
  partial opacity, with each figure's silhouette filled flat grey and labelled (C1/C2). Free, instant, never off-model;
  it shows framing, size, screen side and pose. Owner approves boards on the wall.
- **Character shots** go to fal **reference-to-video**: refs = the cast's v2 sheets for their state (turnaround,
  portrait, expressions, props), the approved plate (`place.png` role "this exact room"), and the draft board
  (`start_frame.png` role "match this composition and staging; grey figures are placeholders for the characters").
  The scene bible, identity and wardrobe text go in the prompt. Image limits: Seedance 2.0 takes 9 images; with two
  characters drop expressions first (identity is in the portrait), then props when the shot doesn't feature them.
- **Empty-room / environment shots** (no cast in frame): image-to-video from the plate itself (a free local plate
  render is the keyframe), so they stay pinned.
- Pre-flight: a character shot needs its draft board approved and every cast member's state sheets approved; an
  environment shot needs its plate approved.

The keyframe module stays for environment-only frames; its character-region path is removed.

## 4. Day films and the wall

A **film** groups ordered scenes; each scene is a short (its own place, bible, plates, shots), so every existing gate
applies. `narrator/worlds/films/<slug>.toml`:

```toml
title = "Saeko: one night"
character = "saeko-kirigaya"
logline = "..."
scenes = ["saeko-wake", "saeko-ring-line", "saeko-collection", "saeko-rin-izakaya", "saeko-rooftop", "saeko-home"]
```

The **wall** page (`/shorts/films/<slug>/`): columns = scenes in story order (time of day, place, wardrobe state,
mood line), cards = shots (draft board thumbnail, size, camera, light, one-line beat, look-book warnings, approval
state). Read-only; decisions in the Review inbox (new item kind `wall` for the film's story order + shot list,
id `film--<slug>--<sha10 of the film + scene shot lists>`). The dashboard's Productions group lists films first.

## 5. Order of work

1. Bible v2 data + sheet generation for Saeko (both states) → owner approves sets.
2. Look book + pre-flight warnings.
3. Draft boards; character shots via reference mode with board + plate + v2 sheets; retire character keyframes.
4. Films + wall page + inbox item.
5. Saeko's day: Claude drafts the film and scenes on paper (places, beats, shots in the look-book grammar) → owner
   approves the wall → plates and boards → owner approves → paid video per approved shot. The izakaya pilot becomes the
   "Mama Sato's" scene, re-planned in the new look.
6. Next character.

## 6. Out of scope

Music and sound design; editing films in the browser; automatic shot picking; other characters' bibles (one at a time).

## 7. Testing

Unit tests: design identity/wardrobe-state parsing; short wardrobe state resolution (text, identity, sheets as refs);
sheet-set review id changes with any file; look-book warnings; draft board compositing (silhouette fill, labels, size);
reference-mode ref list per shot (character vs environment, image-limit dropping order); pre-flight requirements for
both shot kinds; film loading and wall data; wall inbox id. Real verification: Saeko's two sheet sets approved by the
owner; one draft board per shot reviewed; one paid character shot whose outfit, scar, hand and room match.
