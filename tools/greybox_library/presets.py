"""Mannequin poses and camera setups for the grey-box library. Pure data (no Blender).

Poses use the 11-bone LAYOUT in tools/shorts/greybox/blender_build.py (names read from it, not copied). The figure stands at
the origin facing +Y, 172 cm native height. Bone rotations are degrees in bone-local XYZ; for these vertical bones, local X
is world X: on thighs/upper arms/shins +X swings the limb forward (hip/shoulder flexion), on spine/head +X leans back,
and on L limbs -Z / R limbs +Z raises the arm out sideways.
  rot    {bone: (x, y, z)}      bones left out stay at rest
  euler  whole-rig rotation (deg); pos = rig offset (m, rig-local, scaled with the figure); focus = camera look-height multiplier
  blocks grey props in world metres: {name, size (x,y,z), at (centre x, centre y, bottom z)}
Cameras are world-fixed: yaw 0 = camera on the +Y side looking at the origin, 90 = on +X (the figure's left). A figure that faces
+Y is seen from the front at yaw 0; stand-back and stand-window-back turn the figure round instead. Numbers are for a 165 cm figure
and scale with --height. fg = generic grey foreground figure (facing away from the camera) placed forward/side metres from the camera (side + = camera-left),
dist = horizontal distance, height = camera z, look = target height, look_dx = target shift sideways (m)."""

import ast
import re
from pathlib import Path

BLENDER_BUILD = Path(__file__).parents[1] / "shorts" / "greybox" / "blender_build.py"
REF_HEIGHT_CM = 165
RIG_HEIGHT_CM = 172  # LAYOUT head top 1.72 m


def bone_names() -> tuple[str, ...]:
    for node in ast.parse(BLENDER_BUILD.read_text()).body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "LAYOUT":
            return tuple(b[0] for b in ast.literal_eval(node.value))
    raise RuntimeError("LAYOUT not found in blender_build.py")


def _blk(name, size, at):
    return {"name": name, "size": size, "at": at}


POSES = {
    "stand": {"rot": {"upper_arm.L": (0, 0, -4), "upper_arm.R": (0, 0, 4), "forearm.L": (8, 0, 0), "forearm.R": (8, 0, 0)}},
    "walk": {"pos": (0, 0, -0.084),
             "rot": {"thigh.L": (25, 0, 0), "thigh.R": (-20, 0, 0), "shin.R": (-30, 0, 0),
                     "upper_arm.L": (-25, 0, 0), "upper_arm.R": (25, 0, 0), "forearm.R": (20, 0, 0), "spine": (-3, 0, 0)}},
    "sit-stool": {"pos": (0, 0, -0.26), "blocks": [_blk("stool", (0.35, 0.35, 0.65), (0, -0.1, 0))],
                  "focus": 0.8,
                  "rot": {"thigh.L": (60, 0, 0), "thigh.R": (60, 0, 0), "shin.L": (-60, 0, 0), "shin.R": (-60, 0, 0),
                          "upper_arm.L": (25, 0, 0), "upper_arm.R": (25, 0, 0), "forearm.L": (60, 0, 0), "forearm.R": (60, 0, 0),
                          "spine": (-8, 0, 0), "head": (8, 0, 0)}},
    "sit-ledge": {"pos": (0, 0, -0.33), "blocks": [_blk("ledge", (2.0, 0.6, 0.5), (0, -0.05, 0))],
                  "focus": 0.8,
                  "rot": {"thigh.L": (90, 0, 0), "thigh.R": (90, 0, 0), "shin.L": (-100, 0, 0), "shin.R": (-100, 0, 0),
                          "upper_arm.L": (15, 0, -4), "upper_arm.R": (15, 0, 4)}},
    # torso 20 deg forward, forearms along the rail top (rail 1.05 m, perpendicular to the facing), hands meeting in the middle.
    # Angles found by forward kinematics of LAYOUT for a 165 cm figure; the rail sits where the forearms land (y 0.28).
    "lean-rail": {"blocks": [_blk("rail", (2.4, 0.08, 0.08), (0, 0.28, 0.97)),
                             _blk("post.L", (0.08, 0.08, 1.05), (-1.2, 0.28, 0)), _blk("post.R", (0.08, 0.08, 1.05), (1.2, 0.28, 0))],
                  "rot": {"spine": (-20, 0, 0), "head": (15, 0, 0), "upper_arm.L": (55, 0, -20), "upper_arm.R": (55, 0, 20),
                          "forearm.L": (100, -70, 0), "forearm.R": (100, 70, 0)}},
    "stand-back": {"euler": (0, 0, 180), "rot": {"upper_arm.L": (0, 0, -4), "upper_arm.R": (0, 0, 4)}},
    # figure faces +Y, away from the ws-back camera (which sees its back, window beyond); frame 1.2 m wide x 1.6 m tall, sill at 0.9 m, 0.6 m in front of the face, centred
    "stand-window-back": {"euler": (0, 0, 0), "rot": {"upper_arm.L": (0, 0, -4), "upper_arm.R": (0, 0, 4)},
                          "blocks": [_blk("win.sill", (1.2, 0.1, 0.08), (0, 0.7, 0.9)), _blk("win.top", (1.2, 0.1, 0.08), (0, 0.7, 2.42)),
                                     _blk("win.L", (0.08, 0.1, 1.6), (-0.56, 0.7, 0.9)), _blk("win.R", (0.08, 0.1, 1.6), (0.56, 0.7, 0.9)),
                                     _blk("win.mullion", (0.04, 0.08, 1.5), (0, 0.7, 0.95))]},
    "crouch": {"pos": (0, -0.15, -0.555), "focus": 0.6,
               "rot": {"thigh.L": (100, 0, 0), "thigh.R": (100, 0, 0), "shin.L": (-120, 0, 0), "shin.R": (-120, 0, 0),
                       "spine": (-35, 0, 0), "head": (30, 0, 0),
                       "upper_arm.L": (60, 0, 0), "upper_arm.R": (60, 0, 0), "forearm.L": (20, 0, 0), "forearm.R": (20, 0, 0)}},
    # rig rolled 90 deg onto its left side (head toward +X, still facing +Y), torso axis ~0.26 m up so the lower arm rests on the floor;
    # the lower (left) arm is stretched overhead as a pillow for the head, knees slightly bent. Checked with forward kinematics.
    "lie-side": {"euler": (0, 90, 0), "pos": (-1.05, 0, 0.27), "focus": 0.2,
                 "rot": {"thigh.L": (35, 0, 0), "thigh.R": (45, 0, 0), "shin.L": (-50, 0, 0), "shin.R": (-60, 0, 0),
                         "upper_arm.L": (170, 0, 0), "forearm.L": (15, 0, 0), "upper_arm.R": (50, 0, 0), "forearm.R": (60, 0, 0),
                         "spine": (-5, 0, 0)}},
    "sit-floor": {"pos": (0, 0, -0.86), "focus": 0.55,
                  "rot": {"thigh.L": (120, 0, 0), "thigh.R": (120, 0, 0), "shin.L": (-66, 0, 0), "shin.R": (-66, 0, 0),
                          "upper_arm.L": (40, 0, 0), "upper_arm.R": (40, 0, 0), "forearm.L": (70, 0, 0), "forearm.R": (70, 0, 0),
                          "spine": (-6, 0, 0)}},
}

CAMERAS = {
    "ews-high": {"dist": 12.0, "height": 6.0, "yaw": 0, "lens": 28, "look": 0.5},
    "ws-front": {"dist": 4.5, "height": 1.5, "yaw": 0, "lens": 35, "look": 0.85},
    "ws-back": {"dist": 4.5, "height": 1.5, "yaw": 180, "lens": 35, "look": 0.85},
    "ws-profile": {"dist": 4.5, "height": 1.5, "yaw": 90, "lens": 35, "look": 0.85},
    "ms-front": {"dist": 2.4, "height": 1.35, "yaw": 0, "lens": 50, "look": 1.05},
    "ms-profile": {"dist": 2.4, "height": 1.35, "yaw": 90, "lens": 50, "look": 1.05},
    "mcu-front": {"dist": 1.3, "height": 1.4, "yaw": 0, "lens": 50, "look": 1.3},
    "ots-left": {"dist": 2.2, "height": 1.5, "yaw": -20, "lens": 50, "look": 1.2, "look_dx": -0.5, "fg": {"forward": 1.4, "side": 0.5}},
    "ots-right": {"dist": 2.2, "height": 1.5, "yaw": 20, "lens": 50, "look": 1.2, "look_dx": 0.5, "fg": {"forward": 1.4, "side": -0.5}},
    "low-hero": {"dist": 3.2, "height": 0.35, "yaw": 0, "lens": 28, "look": 1.0},
    "top-down": {"dist": 0.05, "height": 6.0, "yaw": 0, "lens": 35, "look": 0.0},
}

SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
