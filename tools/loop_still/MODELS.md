# Models used by tools/loop_still

All run on the CPU. Paths are the defaults the tool looks in; pass another with the matching flag.

| Use | Model | File | Licence | Source |
|---|---|---|---|---|
| Matte (default) | BiRefNet-general (ONNX, as rembg ships it) | `~/models/loop_still/birefnet-general.onnx` | MIT | github.com/ZhengPeng7/BiRefNet; ONNX from rembg's model release |
| Matte (A/B loser) | ToonOut (BiRefNet fine-tune for anime), ONNX export | `~/models/loop_still/toonout/birefnet-toonout.onnx` | MIT | huggingface.co/joelseytre/toonout; ONNX by huggingface.co/sprited/birefnet-toonout-onnx |
| Plate fill | LaMa (big-lama, ONNX) | `~/models/loop_still/lama/lama_fp32.onnx` | Apache-2.0 | see Task 7 notes below |
| Region masks | SAM 2.1 hiera-tiny | `~/models/loop_still/sam2/sam2.1_hiera_tiny.pt` | Apache-2.0 | github.com/facebookresearch/sam2 |

## Matte A/B (2026-11-26)

Three stills (rin-kageyama--alley, ayame-tsuda--city, yuki-shirasagi--city), 1024 px input, about 25 s each on the
CPU. Crops: `design-data/loops/_matte-ab/ab-sheet.jpg`. BiRefNet-general wins: ToonOut kept a cyan neon blob beside
Rin's ear and stray specks, and took Yuki's whole glowing window as foreground. Hair edges were as good or better
with BiRefNet on all three. ToonOut's paper numbers (95.3% → 99.5% pixel accuracy) are on its own test set, which
these neon night scenes are not like.

## Depth (2026-11-27)

| Use | Model | File | Licence | Source |
|---|---|---|---|---|
| Camera drift | Depth Anything V2 Small (transformers, 24.8M params, 94.6 MB) | `~/models/loop_still/depth-anything-v2-small/` | Apache-2.0 (Base/Large are CC-BY-NC-4.0, not used) | huggingface.co/depth-anything/Depth-Anything-V2-Small-hf |

About 1 s per 3648×2544 still on the CPU; the result is cached as `<still>.depth.png` (16-bit, 1 = nearest).
