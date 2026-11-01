# Design Studio: Where We Are and How to Resume

Last updated 2026-11-01.

## State

- **All 22 designs are approved** (11 NPCs, 6 districts, 5 places). The owner made the picks through the gallery picker. Seeds and notes are in `narrator/worlds/designs/*.toml`.
- **Art direction is locked.** See `docs/art-direction.md`.
- **Full sheets:** `python -m tools.design_studio sheets --approved-missing` was started on 2026-10-29. It takes about 2 hours on the RTX 2080 and writes `design-data/<slug>/{turnaround,expressions,colorguide}.png` for characters and `{establishing,alternate,moodkeys,props}.png` for locations. The log is in the session's job tmp (`sheets.log`).
- **Owner's gallery and picker:** http://192.168.10.19:8080/designs/ (LAN or Tailscale; no login). The old claude.ai gallery is retired.
- **Eight new characters are waiting for picks** (added 2026-10-29 to 2026-11-01).

## Publishing and reading picks

- **Publish:** `python -m tools.design_studio gallery`, then `rsync -a design-data/gallery/ 192.168.10.19:anvil-deploy/stack/dashboard/designs/`. The picker is built into the page. Check it with a real click, since nothing else exercises the deployed page.
- **Read picks:** `curl -s http://192.168.10.19:8080/designs/api/picks` returns `{slug: {action: pick|reroll|skip, n, round, note, at}}`. They're stored in `~/anvil-deploy/stack/design-picks/state/picks.json` on the GPU box.
- **Apply:** `pick` becomes `approve <slug> <n>`, then `sheets --approved-missing`. `reroll` follows "Rerolls later" below.
- **Service:** `tools/design_picks.py`, copied to `~/anvil-deploy/stack/design-picks/`, runs as the `design-picks` compose service. After changing it, copy it over and `docker compose restart design-picks`.

## Resume

1. **Check the sheets.** Run `ls design-data/*/turnaround.png design-data/*/establishing.png | wc -l`, which should give 22. If any are missing, rerun `sheets --approved-missing`, which is idempotent.
2. **Commit the palettes.** Sheets write `palette` into the TOMLs: `git add narrator/worlds/designs && git commit`.
3. **Show the owner the sheets.** Publish the gallery as described above.
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
4. Publish the gallery as described above.
5. The owner picks. Then run `approve <slug> <n>`, which defaults to the round in `design-data/gallery/rounds.json`, then `sheets --approved-missing`. Re-approving clears the old sheets.

## Gotchas

- **Free the GPU first.** Unload Ollama before a batch (the CLI does this). Don't run two batches at once.
- **Don't match your own shell when waiting on a batch.** Use `ps -eo args | grep "[t]ools.design_studio"`, not `pgrep -f`.
- **CI runs plain `pytest` on an installed package.** New top-level packages must be listed in `[tool.setuptools.packages.find]`.
