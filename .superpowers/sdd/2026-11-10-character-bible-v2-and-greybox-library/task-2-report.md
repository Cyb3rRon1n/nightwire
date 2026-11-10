# Task 2 report

Commit: "design studio: v2 sheet sets per wardrobe state in neutral light". Full suite: 1130 passed, 1 skipped (1124 + 6 new tests). RED seen first (6 failures), then GREEN.

## Replacement rule
With `state`: `d.tags` (outfit and body mixed, no reliable split) is dropped whole. Prompt = required + state tags + identity. `required` was already the identity-ish split; body/hair marks that must persist across states must live in `required` or `identity`. Unknown state raises ValueError. Portrait/expressions run state tags through the existing `_face_tags` filter (held, below-chest, expression words dropped), so the portrait loses the skirt. Without `state`, behaviour is unchanged.

## Other behaviour
- `NEUTRAL_LIGHT`/`NEUTRAL_NEGATIVE` constants; portrait/expressions swap STYLE for "anime screenshot... thick outlines" + NEUTRAL_LIGHT and add the negative extras.
- New `state_props_prompt(d, state)`: no props generator existed for characters (props.png was hand-made), so new: state props else the state's tags, close-up on grey, identity appended.
- CLI: `sheets <slug> --state <name|all> [--redo] [--only]` writes wardrobe/<state>/{turnaround,expressions,portrait,props,colorguide}.png; skips existing unless --redo; sequential; never writes top-level files (tested). Seed = design seed (or --seed). `--only` now also accepts "props".

## Concerns
- Real TOMLs have no identity/wardrobe yet, so --state raises until they do.
- Hair/build tags in `tags` are lost under a state unless copied to required/identity.
- Turnaround keeps the existing CHARACTER_SHEET_STYLE (already grey/even light); it has no NEUTRAL_LIGHT string.
- Palette in the TOML is not updated by the state path.

## Sample prompts (saeko-kirigaya, identity set to scar on right cheek / mechanical right arm / human left hand, state work = white dress shirt, black pencil skirt, black blazer, flats)
### PORTRAIT
Positive:
```
masterpiece, best quality, very awa, newest, year 2024, absurdres, highres, sensitive, anime screenshot, anime coloring, cel shading, thick outlines, plain grey background, soft even studio light, neutral colors, no neon, mature, adult, solo, portrait, close-up, face focus, looking at viewer, 1girl, expressionless, closed mouth, long hair, straight hair, black hair, blunt bangs, brown eyes, white dress shirt, black blazer, flats, scar on right cheek, mechanical right arm, human left hand
```
Negative:
```
nsfw, worst quality, old, early, low quality, lowres, signature, username, logo, bad hands, mutated hands, mammal, anthro, furry, ambiguous form, feral, semi-anthro, watermark, jpeg artifacts, blurry, worst aesthetic, blue skin, colored skin, monochrome, limited palette, inconsistent outfit, different clothes, different hairstyle, floating object, mismatched footwear, extra arms, extra legs, nude, nipples, pussy, penis, sex, explicit, loli, shota, child, petite, flat chest, young, teenage, aged down, chibi, kawaii, moe, cute, big eyes, deformed, wavy hair, curly hair, two mechanical arms, wide hips, thick thighs, plump, chubby, gigantic breasts, huge breasts, curvy, realistic, photorealistic, photo (medium), 3d, semi-realistic, painterly, oil painting, skin texture, pores, airbrushed, (blue skin:1.3), (colored skin:1.3), (grey skin:1.3), (shadow over face:1.2), multiple views, character sheet, expression chart, turnaround, split screen, full body, child face, baby face, round face, youthful face, cowboy shot, breast focus, cleavage, hand up, hands, hand on own face, hand on own chin, fingers, holding, cigarette, smoking, floating object, extra hands, sharp teeth, vampire, monster, pink skin, red skin, blue skin, purple skin, colored skin, monochrome, red theme, pink theme, neon lights, backlighting, fang, fangs, neon, blue light, cyan tint, colored light, rim light
```

### TURNAROUND
Positive:
```
masterpiece, best quality, very awa, newest, year 2024, absurdres, highres, sensitive, anime screenshot, anime coloring, cel shading, thick outlines, simple background, (grey background:1.3), even lighting, front lighting, cyberpunk, mature, adult, serious, cyberpunk, techwear, character sheet, reference sheet, turnaround, multiple views, front view, from side, from behind, full body, standing, 1girl, long hair, straight hair, black hair, blunt bangs, brown eyes, white dress shirt, black pencil skirt, black blazer, flats, scar on right cheek, mechanical right arm, human left hand
```
Negative:
```
nsfw, worst quality, old, early, low quality, lowres, signature, username, logo, bad hands, mutated hands, mammal, anthro, furry, ambiguous form, feral, semi-anthro, watermark, jpeg artifacts, blurry, worst aesthetic, blue skin, colored skin, monochrome, limited palette, scenery, background clutter, inconsistent outfit, different clothes, different hairstyle, floating object, mismatched footwear, extra arms, extra legs, nude, nipples, pussy, penis, sex, explicit, loli, shota, child, petite, flat chest, young, teenage, aged down, chibi, kawaii, moe, cute, big eyes, deformed, wavy hair, curly hair, two mechanical arms, wide hips, thick thighs, plump, chubby, gigantic breasts, huge breasts, curvy, (realistic:1.4), (photorealistic:1.4), (photo (medium):1.3), (3d:1.3), (semi-realistic:1.3), painterly, oil painting, (skin texture:1.3), pores, airbrushed, detailed skin, hairy, (shadow over face:1.2), (dark face:1.2), low key, underexposed, silhouette, black background, multiple heads, extra heads, disembodied head, (white background:1.4), (light background:1.2)
```


## Fix round 1
Added `Design.appearance` (saved after identity, skipped when empty; validator requires it with wardrobe states and for characters only). Under a state the positive = appearance + state tags + identity; `required` and `tags` are not used (tested with a "white hoodie" in required). State props prompt has no identity; "no neon" removed from NEUTRAL_LIGHT; state turnaround drops "techwear" and the duplicate "cyberpunk"; a failing state is reported, the others continue, exit code 1. Suite 1131 passed, 1 skipped.
Sample for saeko (sample appearance "long hair, straight hair, black hair, blunt bangs, brown eyes, slender, narrow waist, large breasts, long legs"; identity scar on right cheek / mechanical right arm / human left hand; work = white dress shirt, black pencil skirt, black blazer, flats). Negatives are unchanged except the portrait gains the NEUTRAL_NEGATIVE tail.

### Portrait
Positive:
```
masterpiece, best quality, very awa, newest, year 2024, absurdres, highres, sensitive, anime screenshot, anime coloring, cel shading, thick outlines, plain grey background, soft even studio light, neutral colors, mature, adult, solo, portrait, close-up, face focus, looking at viewer, 1girl, expressionless, closed mouth, long hair, straight hair, black hair, blunt bangs, brown eyes, white dress shirt, black blazer, flats, scar on right cheek, mechanical right arm, human left hand
```

### Turnaround
Positive:
```
masterpiece, best quality, very awa, newest, year 2024, absurdres, highres, sensitive, anime screenshot, anime coloring, cel shading, thick outlines, simple background, (grey background:1.3), even lighting, front lighting, mature, adult, serious, character sheet, reference sheet, turnaround, multiple views, front view, from side, from behind, full body, standing, 1girl, long hair, straight hair, black hair, blunt bangs, brown eyes, slender, narrow waist, large breasts, long legs, white dress shirt, black pencil skirt, black blazer, flats, scar on right cheek, mechanical right arm, human left hand
```

### Props
Positive:
```
masterpiece, best quality, very awa, newest, year 2024, absurdres, highres, sensitive, anime screenshot, anime coloring, cel shading, thick outlines, hands and props close-up, product sheet, still life, object focus, multiple views, grey background, soft even studio light, neutral colors, tablet, pen
```
Negative:
```
nsfw, worst quality, old, early, low quality, lowres, signature, username, logo, bad hands, mutated hands, mammal, anthro, furry, ambiguous form, feral, semi-anthro, watermark, jpeg artifacts, blurry, worst aesthetic, blue skin, colored skin, monochrome, limited palette, scenery, background clutter, inconsistent outfit, different clothes, different hairstyle, floating object, mismatched footwear, extra arms, extra legs, nude, nipples, pussy, penis, sex, explicit, loli, shota, child, petite, flat chest, young, teenage, aged down, chibi, kawaii, moe, cute, big eyes, deformed, wavy hair, curly hair, two mechanical arms, wide hips, thick thighs, plump, chubby, gigantic breasts, huge breasts, curvy, neon, blue light, cyan tint, colored light, rim light, white background, 1girl, 1boy, face
```
