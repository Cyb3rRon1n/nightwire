# Photo-first test scripts

The owner's photo-first method: paint a realistic person into the background plate first, then repaint the photo in the anime style.

- `v1_whole_plate.py` - photo by img2img over the whole plate (RealVisXL, denoise 0.75), then a plain NoobAI anime pass with a depth ControlNet at denoise 0.55 or 0.70. **The owner's favourite results came from this version** (2026-11-16); which denoise is being confirmed in the review inbox ("Which one was your favourite?").
- `v2_house_look.py` - same photo, finished with the locked "medium dark" house recipe (kept).
- `v3_masked.py` - photo painted only inside a soft mask so the room stays exactly the plate (rejected 2026-11-17: see-through people where bright lights sit under the soft mask edge).
- `v4_new_shots.py` - 12 new character/location shots on the v3 photo step plus the house anime pass and a hands pass.
- `gentle.py` - wrapper that keeps the laptop GPU cool: pause at 74°C until 62°C, rest 45 s after every job.

Run from the repo root: `.venv/bin/python tools/photo_first/gentle.py tools/photo_first/v1_whole_plate.py stage1 desk`. Outputs go to `tools/photo_first/out/` (git-ignored). `URL` points at the old laptop GPU box; change it when the 4U box is up.
