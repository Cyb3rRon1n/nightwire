# Design Studio: Where We Are and How to Resume

Last updated 2026-10-29.

## State

- **All 22 designs are approved** (11 NPCs, 6 districts, 5 places). The owner made the picks through the gallery picker. Seeds and notes are in `narrator/worlds/designs/*.toml`.
- **Art direction is locked.** See `docs/art-direction.md`.
- **Full sheets:** `python -m tools.design_studio sheets --approved-missing` was started on 2026-10-29. It takes about 2 hours on the RTX 2080 and writes `design-data/<slug>/{turnaround,expressions,colorguide}.png` for characters and `{establishing,alternate,moodkeys,props}.png` for locations. The log is in the session's job tmp (`sheets.log`).
- **Owner's gallery** (private, with the picker): https://claude.ai/artifact/KfQA8VGkHgX58bNfe1rhj3. Picks are in its database collection `picks` (doc id = slug; fields `action` pick|reroll|skip, `n`, `round`, `note`).

## Resume

1. **Check the sheets.** Run `ls design-data/*/turnaround.png design-data/*/establishing.png | wc -l`, which should give 22. If any are missing, rerun `sheets --approved-missing`, which is idempotent.
2. **Commit the palettes.** Sheets write `palette` into the TOMLs: `git add narrator/worlds/designs && git commit`.
3. **Show the owner the sheets.** Run `python -m tools.design_studio gallery`, then append `.superpowers/imagebench/picker.html` to `design-data/gallery/index.html`. The CLI's gallery doesn't include the picker yet. Then republish to the same artifact URL, passing `files` with only the new `img/...` paths and `capabilities: {"db": {}}`.
4. **Export.** `python -m tools.design_studio export` writes a zip to `design-data/exports/`.
5. **ROADMAP:** add a 19b line saying the sheets are complete.
6. **Next phase, 19c (designs in play):**
   - players design their look at creation (preview, regenerate, lock);
   - scenes and portraits reuse a character's or location's approved tags and seed when they are present.

   Read the ROADMAP studio track first.

## Rerolls later

1. Edit the design's `tags` in its TOML by hand.
2. Run `python -m tools.design_studio reroll <slug> "<note>"`.
3. Run `candidates --rerolls`.
4. Run `gallery`, add the picker, and republish.
5. The owner picks. Then run `approve <slug> <n>`, which defaults to the round in `design-data/gallery/rounds.json`, then `sheets --approved-missing`. Re-approving clears the old sheets.

## Gotchas

- **Free the GPU first.** Unload Ollama before a batch (the CLI does this). Don't run two batches at once.
- **Don't match your own shell when waiting on a batch.** Use `ps -eo args | grep "[t]ools.design_studio"`, not `pgrep -f`.
- **CI runs plain `pytest` on an installed package.** New top-level packages must be listed in `[tool.setuptools.packages.find]`.
