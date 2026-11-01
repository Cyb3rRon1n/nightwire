# Character Creator: Design

Date: 2026-11-01. Status: approved by the owner on 2026-11-01.

## Goal

A page in the AI Lab where players describe their Nightwire character, optionally add a photo of their own face as a reference, and redo the result until they're happy. The owner uses the same pages to create NPCs and the look of AI characters. Players can suggest NPCs and AI characters, and only the owner can accept them.

Not in this project: AI characters that take part in play (they need game engine work and get their own project), and using locked characters in the game (Phase 19c).

## Owner decisions

- Reached over Tailscale for now. No public access.
- Players get a review page with unlimited redos.
- The owner creates NPCs and AI characters. Players may suggest them, and the owner approves.

## Who can do what

| | Player | Owner |
|---|---|---|
| Create their own player character | Yes | Yes |
| Use a photo reference | Own character only | Own character only |
| Redo, edit answers, lock in, delete | Own character only | Any |
| Suggest an NPC or AI character (questionnaire, no photo) | Yes | n/a |
| Create NPCs and AI characters; accept or decline suggestions | No | Yes |

## Access

Tailscale controls who can reach the box but doesn't tell people apart, so links carry the permission:

- **Character link:** `/create/c/<token>`, 32 random characters from `secrets.token_urlsafe`. Anyone with the link can use that character, so players shouldn't share it.
- **Owner link:** `/create/owner/<token>`. The token is generated once and kept in a file on the GPU box. It isn't shown on the AI Lab dashboard, because everyone on the tailnet can open that.
- **Same-origin rule:** write requests must be JSON or a declared image type and have a matching Origin, like the existing services.

### Required before inviting players

Everything on the tailnet may currently be able to reach ComfyUI (`:8188`), whose output folder would hold likeness images, along with Open WebUI, Ollama and the home network route (`192.168.10.0/24`). The current Tailscale access rules haven't been checked.

**The owner needs to restrict player accounts to `100.67.87.32:8080` in the Tailscale admin console, or confirm that's already the case.** Photo uploads stay off until this is done. Forms without photos don't depend on it, but the same restriction is still recommended.

## Player flow

1. **Start.** The "Create a character" tile on AI Lab opens the form. Starting creates the private link, and the page tells the player to bookmark it.
2. **Answer.** The questions below, with choices where possible.
3. **Optional photo.** Consent screen, then upload and crop to the face (see Photos).
4. **Generate.** Four candidates, with a place in line shown.
5. **Review.** Each candidate has Pick, Favourite and "Like this one, but...", which makes variations of that image, subtle or strong, with an optional note. The player can also reroll for four new candidates, or edit answers and regenerate. No limit, and earlier rounds and favourites stay visible and can be picked.
6. **Lock in.** Saves the record and renders the turnaround, expressions and colour guide using the method from the cast. Each sheet can be redone on its own.
7. **Done.** The character stays on the private link, ready for 19c.

### Questions

The form has four steps with a progress indicator: Basics, Look, Nightwire details, Final touches. Only name and presentation are required, and choices are offered wherever they fit.

- **Basics:** character name; presentation (feminine, masculine, androgynous); apparent age (20s, 30s, 40s, 50+); role and lifepath from the game's lists; optional personality words.
- **Look:** hair colour and style; eye colour; skin tone; build and height; facial hair or makeup; what to keep from the photo, if there is one.
- **Nightwire details:** outfit style and main colours; tattoos, scars and piercings, with placement; chrome or implants, with side; a "never without" signature item. Tattoos, scars, piercings and chrome default to none.
- **Final touches:** must never include; anything else; one line of backstory.

Lifepath also adds a style tag to the outfit. Role and backstory are saved for the game and don't go into the image prompt. Personality words only set the default expression.

## From answers to prompt

- Choices map to fixed tags. Free text goes in as tags after cleaning: length limit, weight syntax such as `(x:1.4)` removed, and `refused_terms` from Image Studio applied.
- Hair, eyes, facial features, tattoos, scars and chrome go in `required`. Signature items go in `held`. "Never include" goes in `negative`.
- The person is always written as an adult using the existing adult tags and negatives.
- No language model writes the tags. It would have to share the GPU, and players see the result and can reword it.

Each character is a normal `Design`, so the sheets, the Review page and `tools/design_check` work on it unchanged.

## Photos

### Content rules

A character made from a photo stays clothed and non-suggestive for good:

- `from_photo = true` is saved on the design and stays after the photo is deleted, since the likeness remains in the art.
- These designs use the `safe` rating instead of `sensitive`, and don't get the revealing outfit tags or idol proportions from `docs/art-direction.md`, whatever the form says.
- Their negative prompt adds `cleavage, revealing clothes, lingerie, swimsuit, suggestive, seductive`. Answers using those words are refused with an explanation.
- 19c and Image Studio must honour `from_photo` wherever the design is used.

Designs without a photo follow the normal art direction, except that players choose their own build.

### Consent

Before uploading, the player confirms: this is my own face, I'm 18 or over, and I understand it's stored on the owner's server. A checkbox can't prove either claim, and nothing here estimates age from the photo. The owner can delete any character.

### Handling

- The browser crops and re-encodes to JPEG, which removes location and other metadata, and sends at most 1024 px. The server accepts JPEG only, checks the file signature and caps the size at 2 MB.
- Stored in the character's private folder and given to ComfyUI through a dedicated input subfolder. The service mounts that subfolder so it can delete the file.
- Deleted at lock-in, when the player asks, or 30 days after last use. Whichever comes first.
- Candidates are saved to the creator's folder and removed from ComfyUI's output folder after the service has fetched them. PNG metadata is stripped, since it holds the workflow, and the photo gets a random filename so the workflow doesn't identify anyone. Its ComfyUI history entry is deleted too.
- Excluded from the `homelab-ops` backup, and never added to git.

### Likeness

Reference is done with IPAdapter using the installed `ip-adapter-plus_sdxl_vit-h` and CLIP ViT-H. Expect "inspired by", not a portrait. Photo features remain off until a trial on a stock or owner-supplied face shows it's useful and fits 8 GB of VRAM. If it's too weak, IPAdapter Plus Face is the next candidate and is a separate download decision for the owner. InstantID, FaceID and PuLID are out for now: they need InsightFace, whose model weights are for non-commercial research only, and one published test put InstantID near 20 GB of VRAM.

## NPCs and AI characters

- **Owner creation:** same form and review page, plus a kind (NPC or AI character), world role and home location. No photo option.
- **Suggestions:** players go through the same questionnaire as a player character, plus the kind, world role and home location, with no photo. Nothing renders until the owner accepts, so a suggestion costs no GPU time and nothing joins the world unreviewed. The owner sees pending suggestions on the owner page with all the answers and can accept, edit or decline with a note, and the player sees the outcome on their link.
- **Into the world:** on approval, `python -m tools.character_creator export` writes a normal `narrator/worlds/designs/<slug>.toml` into the repo along with its images. World records stay in git and owner-controlled.

## Service

Same pattern as Image Studio:

- **`tools/character_creator.py`:** standard library only, in a `python:3.12-alpine` container, read-only, no capabilities, loopback only, behind nginx at `/create/` and `/create/api/`.
- **`tools/character_creator.html`:** one page for form, review and owner modes.
- **Variations:** image-to-image from the chosen candidate with the same answers. Subtle and strong are two denoise values, set by testing.
- **Reuse:** `image_studio.Comfy`, `refused_terms`, `write_json_atomic`, `design_sheets` prompts and workflows.
- **State:** `state/characters/<token>/` with `character.json`, `photo.jpg`, `candidates/` and `sheets/`, written atomically. Player characters aren't stored in the repo.
- **Queue:** one worker renders one job at a time, across players in order, with one batch per character. It only submits when ComfyUI's queue is empty, so the owner's batches aren't starved or interleaved mid-render.
- **Limits:** at most 12 waiting batches overall, with a clear message when full. Upload limits as above.

## Errors

- **ComfyUI down or busy:** the job stays queued and the page says it's waiting.
- **A failed render:** the batch is marked failed with a Retry button, and earlier rounds are untouched.
- **Service restart:** queued jobs resume from state, and jobs that were rendering are re-queued.
- **Refused words:** the form says which words and why, and keeps the player's answers.
- **Lost link:** there's no recovery without the owner, who can look up characters by name on the owner page and resend it.

## Testing

- **Unit:** answer-to-tag mapping; refused and cleaned text; `from_photo` always yielding the safe rating and added negatives; token and owner-link checks; JPEG signature and size checks; photo deletion on each of its three triggers; suggestions rendering nothing until accepted; queue order and restart recovery.
- **Browser:** the full flow with real renders, redo, going back to an earlier round, lock-in, phone width, one player's link not revealing another's, and the owner link being refused without its token.
- **Real infrastructure:** deployed on the GPU box and reached over the Tailscale address, per the project's verification rule.
- **Photo trial:** run separately on a stock or owner-supplied face before photos are enabled.

## Research basis

Evidence is uneven, and secondary sources were used for most of it.

- **Fields:** Cyberpunk 2077 starts with a [permanent lifepath](https://www.pcgamesn.com/cyberpunk-2077/character-creator), and its scars, tattoos and cyberware [have off options](https://cyberpunk.fandom.com/wiki/Cyberpunk_2077_Character_Customization). Cyberpunk RED's [lifepath](https://rtalsoriangames.com/2020/10/16/cyberpunk-red-alert-lifepath/) uses personality, clothing style, hairstyle and an affectation "you are never without". These shaped the defaults and the signature item.
- **Form length:** there's no good evidence for a creative setup. [Vendor figures on marketing forms](https://www.crazyegg.com/blog/form-statistics/) are weak, so the four steps and optional fields are an informed guess to test with players.
- **Variations:** [Midjourney's Vary (Subtle) and Vary (Strong)](https://docs.midjourney.com/docs/variations) are the precedent. Keeping history and favourites is our own decision, as no source covered it.
- **Likeness:** no head-to-head anime comparison was found, which is why this design runs its own trial. The InsightFace limit is from its [README](https://github.com/deepinsight/insightface); the InstantID VRAM figure is [one user's test](https://stable-diffusion-art.com/instantid/).
- **Photos:** GDPR [Recital 51](https://gdpr-info.eu/recitals/no-51/) says photos are biometric data only when technically processed to identify someone. Illinois's BIPA [excludes photographs, though courts have allowed claims over faceprints made from them](https://lockelord.com/newsandevents/publications/2022/07/bipas-scope-shaped-by-courts). No source addresses a CLIP-based reference like this one, and this isn't legal advice. Avoiding face-recognition templates and deleting promptly are the practical response. [Lensa's problems](https://jezebel.com/trendy-portrait-app-lensa-is-accused-of-creating-noncon-1849870304) with nudes of other people support the own-face confirmation and the clothed rule.

## Build order

Each step is usable on its own:

1. Player form, candidates and review page, without photos.
2. Sheets on lock-in, and the AI Lab tile.
3. Owner page: NPC and AI character creation, suggestions and export.
4. Likeness trial, then photo upload once the trial and the Tailscale restriction are both done.
5. Phase 19c connects locked characters to the game.
