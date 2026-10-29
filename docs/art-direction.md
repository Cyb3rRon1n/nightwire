# Nightwire Art Direction

Owner-approved over the Phase 19a/19b review rounds (2026-10-28/29). Use this for every new image: new NPC designs, player portraits, scene art and future studio-track sheets.

## The look

- **Model:** NoobAI-XL v-pred 1.0, Smooth Booster v3 at 0.6, Euler, CFG 4.5, 28 steps, RescaleCFG 0.6, clip skip 2 (`COMFYUI_PROFILE=noobai`).
- **Style:** anime screenshot coloring, cel shading, thick outlines, neon lights with pink rim light and cyan backlight, high contrast, bloom, night. Prompt strings live in `narrator/image_prompt.py` (scenes and portraits) and `narrator/design_sheets.py` (model sheets).
- **Locations:** the in-game neon style as rendered. The owner loves all of round 1, including the candidates not picked; keep them in `design-data/<slug>/candidates/` as alternates.

## Characters

- **Tone:** mature, adult, serious, gritty dark cyberpunk society. Techwear, LED trim, tattoos, scars, piercings, dark makeup.
- **Model sheets:** dark grey backdrop with pink and cyan neon rim light (`CHARACTER_SHEET_STYLE`). Turnaround, expression sheet and colour guide.
- **Rating:** `sensitive`, so suggestive is allowed. Every character prompt negates `nude, nipples, pussy, penis, sex, explicit, loli, shota, child, petite, flat chest, young, teenage, aged down, chibi, kawaii, moe, cute, big eyes, deformed`. **No nudity.**
- **Women,** including female-presenting androids:
  - **Proportions:** idol proportions, like a K-pop idol or Chun-Li: `mature female, slender, narrow waist, large breasts, long legs, toned, beautiful face, idol`.
  - **Negatives:** `wide hips, thick thighs, plump, chubby, gigantic breasts, huge breasts, curvy`.
  - **Clothes:** sexy, revealing cyberpunk fashion, such as plunging necklines, bodysuits, slits, midriff, fishnets and thigh boots.
- **Men:** adult, rugged, muscular where it fits the role (`muscular male, broad shoulders`, stubble, scars).
- **Always clearly adult.** Elderly characters, and anyone written as 18–19, are styled gritty and are never sexualized.
- **Tag order:** hair → face and eyes → build and proportions → outfit → signature chrome last. Chrome names its side ("mechanical right arm, human left hand"), with a matching negative ("two mechanical arms").

## New character portraits (in game, and new NPCs)

- **In-game portraits** (`server/portrait.py` through `narrator/image_prompt.py`) use bust framing. Lower-body tags are dropped and the portrait negative blocks full body. Player `presentation` gives 1girl, 1boy or 1other; a tsukumogami is an android.
- **New portraits must follow this guide.** Apply the same mature tone and, for women, the idol proportions above. Phase 19c will make portraits and scenes reuse each character's approved design record (`narrator/worlds/designs/<slug>.toml`: tags and seed) so a character looks the same everywhere.
- **For a new NPC:**
  1. Write `narrator/worlds/designs/<slug>.toml` from their world card, following the rules above.
  2. Run `python -m tools.design_studio candidates <slug>`, then `gallery`, and republish the gallery with its picker (see `docs/design-studio-resume.md`).
  3. The owner picks; then run `approve` and `sheets`.
