"""python -m tools.loop_still STILL [options]: one approved still in, a seamless loop out, in
design-data/loops/<still>/<preset>/ (master.mkv, loop.mp4, preview3x.mp4, poster.jpg, meta.json).
Exits 1 when a check fails, after writing everything. Masks: python -m tools.loop_still.regions."""

import argparse
import json
import sys
from pathlib import Path

from tools.loop_still.layers import RAIN
from tools.loop_still.render import Options, render


def parse(argv=None) -> Options:
    ap = argparse.ArgumentParser(prog="python -m tools.loop_still")
    ap.add_argument("still", type=Path)
    ap.add_argument("--seconds", type=float, default=20)
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--size", default="1920x1338")
    ap.add_argument("--rain", choices=list(RAIN), default="heavy")
    ap.add_argument("--no-near-rain", dest="near_rain", action="store_false", help="no rain in front of her")
    ap.add_argument("--lights", action=argparse.BooleanOptionalAction, default=True,
                    help="neon and windows breathe (tools/lights.py)")
    ap.add_argument("--strength", type=float, default=0.3, help="lights strength")
    ap.add_argument("--train"); ap.add_argument("--floor"); ap.add_argument("--passes", default="")
    ap.add_argument("--sweeps", default="")
    ap.add_argument("--sign-blink", help="polygon of a sign that blinks after each sweep (tools/lights.py --blink)")
    ap.add_argument("--fog", action="store_true")
    ap.add_argument("--ground", type=float, default=0.8, help="where the street starts, as a fraction of height")
    ap.add_argument("--splashes", type=int, default=40)
    ap.add_argument("--motion", default="hair,coat,breath", help="regions that move: hair, coat, breath")
    ap.add_argument("--still-character", action="store_true", help="she doesn't move at all")
    ap.add_argument("--blink", dest="blink", action="store_true", default=None)
    ap.add_argument("--no-blink", dest="blink", action="store_false")
    ap.add_argument("--edge-tint", action=argparse.BooleanOptionalAction, default=True,
                    help="the neon's light faintly on her edge")
    ap.add_argument("--plate", choices=["lama", "telea"], default="lama")
    ap.add_argument("--matte-model", type=Path)
    ap.add_argument("--redo-matte", action="store_true")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--preset")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--frames-only", type=int, default=0, help="write this many PNG frames for a quick look")
    return Options(**vars(ap.parse_args(argv)))


def main(argv=None) -> int:
    o = parse(argv)
    out = render(o)
    if o.frames_only:
        print(out)
        return 0
    checks = json.loads((out / "meta.json").read_text())["checks"]
    print(out)
    print(json.dumps(checks))
    return 0 if checks["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
