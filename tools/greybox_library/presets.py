"""Mannequin poses and camera setups for the grey-box library. Pure data (no Blender).

Poses use the 11-bone LAYOUT in tools/shorts/greybox/blender_build.py (names read from it, not copied). The figure stands at
the origin facing +Y, 172 cm native height. Bone rotations are degrees in bone-local XYZ; for these vertical bones, local X
is world X: on thighs/upper arms/shins +X swings the limb forward (hip/shoulder flexion), on spine/head +X leans back,
and on L limbs -Z / R limbs +Z raises the arm out sideways.
  rot    {bone: (x, y, z)}      bones left out stay at rest
  euler  whole-rig rotation (deg); pos = rig offset (m, rig-local, scaled with the figure); focus = camera look-height multiplier
  blocks grey props in world metres: {name, size (x,y,z), at (centre x, centre y, bottom z), optional shape "cyl" = upright cylinder of diameter x, y and height z}
  group  browse/doc grouping: basic | cinematic | editorial | character;  for = the character a "character" pose was made for
Bone convention (found by forward kinematics, see test_new_poses_keep_feet_on_floor): euler is XYZ with X applied first, so on a limb "x" swings it forward
(hips/knees), a following "y" then turns that swung limb sideways about the vertical (spreads forward thighs, brings forearms together) and "z" tilts a hanging limb out.
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


def _group(group, poses):
    return {k: {**v, "group": group} for k, v in poses.items()}


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

for _p in POSES.values():
    _p["group"] = "basic"

# --- cinematic poses (FK-checked: feet/contacts on the floor and props, see docs/greybox-library.md)
POSES.update(_group('cinematic', {
    "doorway-silhouette": {"rot": {
            "upper_arm.L": (0, 0, -6),
            "upper_arm.R": (0, 0, 6),
            "forearm.L": (10, 0, 0),
            "forearm.R": (10, 0, 0),
            "head": (3, 0, 0)},
        "blocks": [
            {'name': 'door.L', 'size': (0.12, 0.2, 2.1), 'at': (-0.56, -0.25, 0)},
            {'name': 'door.R', 'size': (0.12, 0.2, 2.1), 'at': (0.56, -0.25, 0)},
            {'name': 'door.top', 'size': (1.24, 0.2, 0.12), 'at': (0, -0.25, 2.1)}]},
    "walk-away": {"rot": {
            "thigh.L": (25, 0, 0),
            "thigh.R": (-20, 0, 0),
            "shin.R": (-30, 0, 0),
            "upper_arm.L": (-25, 0, 0),
            "upper_arm.R": (25, 0, 0),
            "forearm.R": (20, 0, 0),
            "spine": (-3, 0, 0)},
        "pos": (0, 0, -0.084),
        "euler": (0, 0, 180)},
    "sit-bed-edge-head-down": {"rot": {
            "thigh.L": (90, 0, 0),
            "thigh.R": (90, 0, 0),
            "shin.L": (-90, 0, 0),
            "shin.R": (-90, 0, 0),
            "spine": (-38, 0, 0),
            "head": (-30, 0, 0),
            "upper_arm.L": (67, 0, 17),
            "forearm.L": (34, -32, 0),
            "upper_arm.R": (67, 0, -17),
            "forearm.R": (34, 32, 0)},
        "pos": (0, 0, -0.439),
        "focus": 0.8,
        "blocks": [
            {'name': 'bed', 'size': (2.0, 2.0, 0.4), 'at': (0, -0.75, 0)}]},
    "rail-overlook": {"rot": {
            "spine": (-12, 0, 0),
            "head": (14, 0, 0),
            "upper_arm.L": (31, 0, -26),
            "forearm.L": (97, -33, 0),
            "upper_arm.R": (31, 0, 26),
            "forearm.R": (97, 33, 0)},
        "blocks": [
            {'name': 'rail', 'size': (2.4, 0.08, 0.08), 'at': (0, 0.33, 0.97)},
            {'name': 'post.L', 'size': (0.08, 0.08, 1.05), 'at': (-1.2, 0.33, 0)},
            {'name': 'post.R', 'size': (0.08, 0.08, 1.05), 'at': (1.2, 0.33, 0)},
            {'name': 'parapet', 'size': (2.4, 0.1, 0.55), 'at': (0, 0.35, 0)}]},
    "look-up": {"rot": {
            "upper_arm.L": (0, 0, -4),
            "upper_arm.R": (0, 0, 4),
            "forearm.L": (8, 0, 0),
            "forearm.R": (8, 0, 0),
            "head": (35, 0, 0),
            "spine": (4, 0, 0)}},
    "sit-bench": {"rot": {
            "thigh.L": (90, 0, 0),
            "thigh.R": (90, 0, 0),
            "shin.L": (-90, 0, 0),
            "shin.R": (-90, 0, 0),
            "spine": (-5, 0, 0),
            "head": (5, 0, 0),
            "upper_arm.L": (14, 0, 16),
            "forearm.L": (75, -13, 0),
            "upper_arm.R": (14, 0, -16),
            "forearm.R": (75, 13, 0)},
        "pos": (0, 0, -0.439),
        "focus": 0.8,
        "blocks": [
            {'name': 'bench', 'size': (1.6, 0.45, 0.4), 'at': (0, 0, 0)}]},
    "stand-umbrella": {"rot": {
            "upper_arm.L": (0, 0, -4),
            "upper_arm.R": (32, 0, 23),
            "forearm.L": (8, 0, 0),
            "forearm.R": (117, -23, 0),
            "spine": (0, 0, 0)},
        "blocks": [
            {'name': 'umbrella.pole', 'size': (0.03, 0.03, 1.0), 'at': (-0.29, 0.27, 1.2), 'shape': 'cyl'},
            {'name': 'umbrella.canopy', 'size': (1.2, 1.2, 0.05), 'at': (-0.29, 0.27, 2.17), 'shape': 'cyl'}]},
    "lie-floor-up": {"rot": {
            "upper_arm.L": (0, 0, -25),
            "upper_arm.R": (0, 0, 25),
            "forearm.L": (4, 0, 0),
            "forearm.R": (4, 0, 0),
            "thigh.L": (0, 0, -6),
            "thigh.R": (0, 0, 6),
            "head": (-8, 0, 0)},
        "pos": (-0.86, 0, 0.1),
        "euler": (90, 0, 90),
        "focus": 0.2},
    "sit-window-sill": {"rot": {
            "thigh.L": (118, 0, 0),
            "thigh.R": (118, 0, 0),
            "shin.L": (-165, 0, 0),
            "shin.R": (-165, 0, 0),
            "spine": (4, 0, 0),
            "upper_arm.L": (22, 0, 0),
            "forearm.L": (91, -9, 0),
            "upper_arm.R": (22, 0, 0),
            "forearm.R": (91, 9, 0)},
        "pos": (0, 0, -0.074),
        "focus": 0.8,
        "blocks": [
            {'name': 'sill', 'size': (1.4, 0.6, 0.75), 'at': (0, 0, 0)},
            {'name': 'win.L', 'size': (0.08, 0.1, 1.7), 'at': (-0.7, -0.3, 0.75)},
            {'name': 'win.R', 'size': (0.08, 0.1, 1.7), 'at': (0.7, -0.3, 0.75)},
            {'name': 'win.top', 'size': (1.48, 0.1, 0.08), 'at': (0, -0.3, 2.45)}]},
}))

# --- editorial poses (FK-checked: feet/contacts on the floor and props, see docs/greybox-library.md)
POSES.update(_group('editorial', {
    "contrapposto": {"rot": {
            "hips": (0, 0, -7),
            "thigh.R": (0, 0, -9),
            "thigh.L": (12, 0, -16),
            "shin.L": (2, 0, 0),
            "spine": (0, 0, 5),
            "head": (0, 0, 2),
            "upper_arm.L": (0, 0, -8),
            "upper_arm.R": (0, 0, 6),
            "forearm.L": (14, 0, 0),
            "forearm.R": (10, 0, 0)}},
    "hand-on-hip": {"rot": {
            "hips": (0, 0, -7),
            "thigh.R": (0, 0, -9),
            "thigh.L": (12, 0, -16),
            "shin.L": (2, 0, 0),
            "spine": (0, 0, 5),
            "head": (0, 0, 2),
            "upper_arm.L": (0, 0, -8),
            "forearm.L": (14, 0, 0),
            "upper_arm.R": (-15, 0, 27),
            "forearm.R": (80, 40, 0)}},
    "over-shoulder-glance": {"rot": {
            "hips": (0, 0, -7),
            "thigh.R": (0, 0, -9),
            "thigh.L": (12, 0, -16),
            "shin.L": (2, 0, 0),
            "spine": (0, -35, 5),
            "head": (0, -85, 2),
            "upper_arm.L": (0, 0, -8),
            "upper_arm.R": (0, 0, 6),
            "forearm.L": (14, 0, 0),
            "forearm.R": (45, 0, 0)},
        "euler": (0, 0, 180)},
    "hands-in-pockets": {"rot": {
            "hips": (0, 0, -3),
            "thigh.R": (0, 0, -9),
            "thigh.L": (12, 0, -16),
            "shin.L": (2, 0, 0),
            "spine": (-4, 0, 2),
            "head": (5, 0, 1),
            "upper_arm.L": (-3, 0, 4),
            "forearm.L": (30, 17, 0),
            "upper_arm.R": (-3, 0, -3),
            "forearm.R": (28, -17, 0)}},
    "arms-crossed": {"rot": {
            "hips": (0, 0, -3),
            "thigh.R": (0, 0, -9),
            "thigh.L": (12, 0, -16),
            "shin.L": (2, 0, 0),
            "spine": (-3, 0, 1),
            "head": (0, 0, 2),
            "upper_arm.L": (2, 0, 29),
            "forearm.L": (80, -38, 0),
            "upper_arm.R": (20, 0, -28),
            "forearm.R": (98, 51, 0)}},
    "lean-wall": {"rot": {
            "hips": (0, 0, 7),
            "thigh.R": (0, 0, 14),
            "spine": (0, 0, 5),
            "head": (0, 0, -6),
            "upper_arm.R": (0, 0, 4),
            "thigh.L": (17, 0, 15),
            "shin.L": (-3, 0, 0),
            "forearm.R": (10, 0, 0),
            "upper_arm.L": (-2, 0, 6),
            "forearm.L": (29, 17, 0)},
        "blocks": [
            {'name': 'wall', 'size': (0.3, 3.0, 2.6), 'at': (-0.49, 0.0, 0)}]},
    "chair-backward": {"rot": {
            "spine": (-10, 0, 0),
            "head": (8, 0, 0),
            "thigh.L": (85, 47, 0),
            "thigh.R": (85, -47, 0),
            "shin.L": (-85, 0, 0),
            "shin.R": (-85, 0, 0),
            "upper_arm.L": (61, 0, -27),
            "forearm.L": (129, -11, 0),
            "upper_arm.R": (61, 0, 27),
            "forearm.R": (129, 11, 0)},
        "pos": (0, 0, -0.387),
        "focus": 0.8,
        "blocks": [
            {'name': 'chair.seat', 'size': (0.42, 0.42, 0.45), 'at': (0, 0, 0)},
            {'name': 'chair.back', 'size': (0.42, 0.04, 0.5), 'at': (0, 0.21, 0.45)}]},
    "seated-legs-crossed": {"rot": {
            "thigh.R": (60, 0, 0),
            "shin.R": (-60, 0, 0),
            "thigh.L": (93, -28, 0),
            "shin.L": (-70, 10, 4),
            "spine": (-6, 0, 0),
            "head": (6, 0, 0),
            "upper_arm.L": (-8, 0, -1),
            "upper_arm.R": (26, 0, -10),
            "forearm.L": (88, 1, 0),
            "forearm.R": (24, 2, 0)},
        "pos": (0, 0, -0.26),
        "focus": 0.8,
        "blocks": [
            {'name': 'stool', 'size': (0.35, 0.35, 0.65), 'at': (0, -0.1, 0)}]},
    "chin-on-hand": {"rot": {
            "thigh.L": (90, 0, 0),
            "thigh.R": (90, 0, 0),
            "shin.L": (-90, 0, 0),
            "shin.R": (-90, 0, 0),
            "spine": (-14, 0, 0),
            "head": (-4, 0, 0),
            "upper_arm.R": (85, 0, 39),
            "forearm.R": (131, 9, 0),
            "upper_arm.L": (85, 0, -16),
            "forearm.L": (23, 15, 0)},
        "pos": (0, 0, -0.439),
        "focus": 0.8,
        "blocks": [
            {'name': 'chair.seat', 'size': (0.45, 0.45, 0.4), 'at': (0, -0.05, 0)},
            {'name': 'table.top', 'size': (1.2, 0.7, 0.05), 'at': (0, 0.66, 0.72)},
            {'name': 'table.leg.a', 'size': (0.06, 0.06, 0.72), 'at': (-0.54, 0.38, 0)},
            {'name': 'table.leg.b', 'size': (0.06, 0.06, 0.72), 'at': (0.54, 0.38, 0)},
            {'name': 'table.leg.c', 'size': (0.06, 0.06, 0.72), 'at': (-0.54, 0.94, 0)},
            {'name': 'table.leg.d', 'size': (0.06, 0.06, 0.72), 'at': (0.54, 0.94, 0)}]},
    "crouch-street": {"rot": {
            "thigh.L": (100, 0, 0),
            "thigh.R": (100, 0, 0),
            "shin.L": (-120, 0, 0),
            "shin.R": (-120, 0, 0),
            "spine": (-35, 0, 0),
            "head": (30, 0, 0),
            "upper_arm.L": (79, 0, -26),
            "forearm.L": (50, -23, 0),
            "upper_arm.R": (79, 0, 26),
            "forearm.R": (50, 23, 0)},
        "pos": (0, -0.15, -0.555),
        "focus": 0.6},
    "kneel-one-knee": {"rot": {
            "thigh.R": (80, 0, 0),
            "shin.R": (-80, 0, 0),
            "thigh.L": (-5, 0, 0),
            "shin.L": (-85, 0, 0),
            "spine": (-32, 0, 0),
            "head": (22, 0, 0),
            "upper_arm.R": (57, 0, -22),
            "forearm.R": (20, -8, 0),
            "upper_arm.L": (5, 0, 13),
            "forearm.L": (45, 13, 0)},
        "pos": (0, 0, -0.379),
        "focus": 0.7},
    "recline-elbow": {"rot": {
            "thigh.L": (90, 0, 0),
            "shin.L": (0, 0, 0),
            "thigh.R": (146, -6, 0),
            "shin.R": (-121, 0, 0),
            "spine": (44, 0, -45),
            "head": (-12, 0, 0),
            "upper_arm.L": (-2, 0, -5),
            "forearm.L": (38, -15, 0)},
        "pos": (0, 0, -0.856),
        "focus": 0.4},
}))

# --- character poses (FK-checked: feet/contacts on the floor and props, see docs/greybox-library.md)
POSES.update(_group('character', {
    "inspect-hand": {"rot": {
            "upper_arm.L": (0, 0, -4),
            "forearm.L": (8, 0, 0),
            "spine": (-5, 0, 0),
            "head": (-18, 0, 0),
            "upper_arm.R": (50, 0, 5),
            "forearm.R": (107, 28, 0)},
        "for": 'Saeko'},
    "cross-legged-deck": {"rot": {
            "thigh.L": (90, 36, 0),
            "thigh.R": (90, -37, 0),
            "shin.L": (-173, 0, -41),
            "shin.R": (-180, 0, 45),
            "spine": (-14, 0, 0),
            "head": (-22, 0, 0),
            "upper_arm.L": (33, 0, 6),
            "forearm.L": (85, -10, 0),
            "upper_arm.R": (33, 0, -6),
            "forearm.R": (85, 10, 0)},
        "pos": (0, 0, -0.846),
        "focus": 0.55,
        "blocks": [
            {'name': 'deck', 'size': (0.42, 0.3, 0.04), 'at': (0, 0.3, 0.26)}],
        "for": 'Rin'},
    "behind-counter": {"rot": {
            "spine": (-6, 0, 0),
            "head": (4, 0, 0),
            "upper_arm.L": (33, 0, 1),
            "forearm.L": (57, 6, 0),
            "upper_arm.R": (33, 0, -1),
            "forearm.R": (57, -6, 0)},
        "blocks": [
            {'name': 'counter', 'size': (1.6, 0.5, 1.0), 'at': (0, 0.62, 0)}],
        "for": 'Mama Sato'},
    "lean-cane": {"rot": {
            "spine": (-9, 0, 0),
            "head": (9, 0, 0),
            "upper_arm.L": (-8, 0, -5),
            "forearm.L": (10, 0, 0),
            "upper_arm.R": (8, 0, 1),
            "forearm.R": (50, -17, 0)},
        "blocks": [
            {'name': 'cane', 'size': (0.035, 0.035, 0.89), 'at': (-0.26, 0.22, 0), 'shape': 'cyl'}],
        "for": 'Tadamori'},
    "adjust-visor": {"rot": {
            "spine": (0, 0, 0),
            "head": (-4, 0, 0),
            "upper_arm.L": (0, 0, -4),
            "forearm.L": (8, 0, 0),
            "upper_arm.R": (92, 0, 26),
            "forearm.R": (136, -8, 0)},
        "for": 'Yuki'},
}))


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
    # cinema cameras: small figure in a big space, backs, profiles, a far overhead and a look through a doorway
    "ews-low": {"dist": 20.0, "height": 0.4, "yaw": 0, "lens": 70, "look": 0.7},
    "ws-low-back": {"dist": 4.0, "height": 0.3, "yaw": 180, "lens": 35, "look": 0.9},
    "profile-close": {"dist": 4.1, "height": 1.35, "yaw": 90, "lens": 85, "look": 1.05},
    "high-wide": {"dist": 8.0, "height": 8.0, "yaw": 0, "lens": 35, "look": 0.5},
    "doorway-frame": {"dist": 3.2, "height": 1.25, "yaw": 15, "lens": 28, "look": 1.0},
}

SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
