# Plate-aware staging: perspective, scale, depth, and Blender stages the owner can use

Owner asks (2026-11-11):
- Grey figures "do not understand the images" they stand in: perspective, and character height against the background.
- An AI Lab tile where the owner can stage shots in Blender themselves ("I want to master this").

Owner answers:
- Scars removed (done, 5e96dc7).
- Blender: both desktop stage files and a browser tile.
- Depth model: yes.
- Old renders: hidden (done, 209412b).

## What is wrong today (seen on 4 boards)
1. **Heights are typed by hand** (`height` in shot TOML). In Rin's room the figure is shorter than the desk.
2. **The figure's camera is always eye level**, even when the plate is shot from above.
3. **Library cells bring their own props** (stool block, rail), and these land on top of the plate's real stool or rail.
4. **`hidden_below` is set by hand** for counters.

## 1. Plate camera (`tools/shorts/plate_camera.py`)
Per chosen plate, saved as `<place>/plates/<name>.camera.json`:
- `horizon_y`: 0..1, may be <0 or >1.
- `cam_height_m`: default 1.5.
- `fov_deg`
- `floor`: a mask PNG.
- `source`: "auto" | "owner" | "claude".

How the values are filled:
- **Horizon:** a line-segment vanishing-point vote (spike: correct on 3 of 4 plates; Rin's dark high-angle room failed). Where lines are weak, the fallback is the depth-gradient horizon.
- **Floor mask and depth:** Depth Anything V2 Small, already downloaded (Apache-2.0, CPU, ~1 s per plate). The floor is depth pixels whose depth rises smoothly toward the frame bottom, connected to the bottom edge.
- **Check image:** `plate-check.png` shows the horizon line, the floor tint, and a 1.6 m ruler drawn at three floor points. It goes to the inbox as part of the plate item, and a wrong horizon gets fixed with `shorts plates <slug> --horizon NAME Y`.

## 2. Boards use the camera
- **Height:** figure height in frame = (feet_y - horizon_y) × (character_height_m / cam_height_m). Character height comes from a new optional bible field `height_m` (default 1.65). The field is outside `_bible_data`, so it does not void keeps. A shot's `height` stays as a manual override and draws a warning.
- **Feet must land on the floor mask.** The board build fails otherwise, with the nearest valid point suggested.
- **Occlusion:** plate depth nearer than the figure's floor depth hides figure pixels. This replaces hand-set `hidden_below`, which stays as an override.
- **Library camera chosen by pitch:** horizon above the frame means a high-angle cell, below the frame a low-angle cell, otherwise eye level.
- **Library props:** cells insert only the figure layer, unless the shot says `keep_props = true`.

## 3. Blender stages, desktop (owner's PC)
- **Build:** `python -m tools.shorts stage <short> <shot>` writes `shots/<id>/stage.blend`:
  - the camera from the plate's camera.json (horizon to pitch, fov, height);
  - the plate as the camera background;
  - a ground plane, invisible but used for snapping and shadows, placed from the floor mask;
  - one mannequin per figure at its true height, rigged with Blender's built-in Rigify human metarig (no download), on the board's feet positions;
  - a pose library of the existing grey-box presets.
- **Export button:** an add-on panel "Nightwire > Export board" renders `board-start.png`/`board-end.png` and the depth, pose and normal passes the existing pipeline reads, into the same shot folder. Boards made this way carry `source = owner` and are never overwritten by `shorts boards`.
- **Optional camera match:** fSpy can be added later for exact camera matching by hand, if its importer works on Blender 4.5.
- **Sync:** design-data is local on this PC, so the files are opened in place. No upload server.

## 4. Blender in the browser (GPU box tile)
- The `linuxserver/blender` container (KasmVNC web UI) on 192.168.10.19 mounts the same stage folders (synced design-data/shorts), and an AI Lab tile opens it.
- **GPU sharing:** it uses the GPU only while open. ComfyUI jobs pause while a stage session is open (one job at a time). A stage tile page lists each shot with "open stage" and the last exported board.
- The image download is about 2 GB, and goes ahead only when part 4 starts.

## 5. Re-render order after this lands
1. Keep the 5 scar-free bibles.
2. Re-render the sheet sets.
3. Rebuild the plate camera files.
4. Rebuild the boards and walls (new ids, back in the inbox).
5. Render the world images and keyframes with the v2 sheets.

## Tests
- Height formula against a synthetic plate with a known horizon.
- A floor-mask hit or miss rejects feet off the floor.
- The occlusion mask from a synthetic depth step.
- The library-cell pitch choice.
- A stage.blend build smoke test, run headless on the GPU box (real Blender, per the project's real-verification rule).
- An export round trip: export, then the board is picked up and not overwritten.
