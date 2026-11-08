"""Short -> scene.json, the only input the Blender script reads. No bpy here, so it is unit-tested."""

from tools.shorts.model import Short

FPS = 24
RES = (1280, 720)
BONES = ("hips", "spine", "head", "upper_arm.L", "forearm.L", "upper_arm.R", "forearm.R",
         "thigh.L", "shin.L", "thigh.R", "shin.R")
# Rotations are about each bone's local X. Bones hang along -Z (arms, legs), so a positive angle swings them
# forward (+Y at rest); the spine points up, so a negative angle leans it forward.
POSES = {
    "stand": {},
    "sit": {"thigh.L": (90, 0, 0), "thigh.R": (90, 0, 0), "shin.L": (-90, 0, 0), "shin.R": (-90, 0, 0)},
    "lean_counter": {"spine": (-25, 0, 0), "upper_arm.L": (60, 0, 10), "upper_arm.R": (60, 0, -10),
                     "forearm.L": (30, 0, 0), "forearm.R": (30, 0, 0)},
    "kneel": {"thigh.L": (90, 0, 0), "shin.L": (-90, 0, 0), "thigh.R": (0, 0, 0), "shin.R": (-90, 0, 0)},
    "arm_raised": {"upper_arm.R": (170, 0, 0)},
}
GREY = 0.6


def tint(colorguide_hex: str | None) -> list[float]:
    if not colorguide_hex:
        return [GREY] * 3
    h = colorguide_hex.lstrip("#")
    rgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return [round(GREY * 0.85 + c * 0.15, 4) for c in rgb]


def _f(seconds: float) -> int:
    return round(seconds * FPS)


def scene_json(short: Short, palettes: dict[str, str] | None = None) -> dict:
    palettes = palettes or {}
    return {
        "fps": FPS, "res": list(RES),
        "frames": max((_f(s.end) for s in short.shots), default=0),
        "blocks": [{"name": b.name, "size": list(b.size), "at": list(b.at), "rot": b.rot} for b in short.blocks],
        "figures": [{"id": f.id, "tier": f.tier, "pose": f.pose, "rotations": POSES.get(f.pose, {}),
                     "tint": tint(palettes.get(f.id)),
                     "keys": [[_f(t), x, y, facing] for t, x, y, facing in f.keys]} for f in short.figures.values()],
        "shots": [{"id": s.id, "start_frame": _f(s.start), "end_frame": _f(s.end), "lens": s.lens,
                   "camera": [[_f(s.start + k.t), list(k.at), list(k.look)] for k in s.camera]} for s in short.shots],
    }
