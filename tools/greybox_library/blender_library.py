"""Inside Blender: blender -b -P blender_library.py -- job.json outdir
Renders every job cell (pose x camera) of a mannequin on a neutral void: flat grey figure and props on a lighter grey floor with a
1 m grid. Per cell: board.png, depth.png (white = near), pose.json (18-point OpenPose + back flag), meta.json.

The mannequin, screen-box, pose-point and depth helpers are NOT copied: blender_build.py (shipped next to this file) runs a whole
scene on import, so only its LAYOUT / helper definitions are pulled out with ast and executed here."""

import ast
import json
import math
import sys
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

WANT_NAMES = {"LAYOUT", "UP", "CAPSULE_PTS"}
WANT_FUNCS = {"mannequin", "screen_box", "figure_pose", "render_depth", "render_still"}
GREY, FLOOR, SKY, GRID = (0.45, 0.45, 0.47, 1), (0.74, 0.74, 0.76, 1), (0.60, 0.60, 0.62), (0.52, 0.52, 0.55, 1)

args = sys.argv[sys.argv.index("--") + 1:]
job_path, out = Path(args[0]), Path(args[1])
J = json.loads(job_path.read_text())

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = "BLENDER_WORKBENCH"
sc.render.resolution_x, sc.render.resolution_y = J["res"]
sc.display.shading.light, sc.display.shading.color_type, sc.display.shading.show_object_outline = "STUDIO", "OBJECT", True
sc.view_settings.view_transform = "Standard"
sc.world = bpy.data.worlds.new("w")
sc.world.color = SKY

try:
    here = Path(__file__).resolve().parent
except NameError:
    here = Path(sys.argv[sys.argv.index("-P") + 1]).resolve().parent
tree = ast.parse((here / "blender_build.py").read_text())
keep = [n for n in tree.body if (isinstance(n, ast.FunctionDef) and n.name in WANT_FUNCS)
        or (isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") in WANT_NAMES)]
missing = (WANT_FUNCS | WANT_NAMES) - {n.name if isinstance(n, ast.FunctionDef) else n.targets[0].id for n in keep}
if missing:
    raise SystemExit(f"blender_build.py no longer defines: {sorted(missing)}")
exec(compile(ast.Module(body=keep, type_ignores=[]), "blender_build.py", "exec"), globals())  # noqa: S102


def quads(name, rects, colour, z):
    """One flat mesh from (x0, y0, x1, y1) rectangles at height z."""
    verts, faces = [], []
    for x0, y0, x1, y1 in rects:
        i = len(verts)
        verts += [(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)]
        faces.append((i, i + 1, i + 2, i + 3))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    obj = bpy.data.objects.new(name, mesh)
    obj.color = colour
    sc.collection.objects.link(obj)
    return obj


def box(name, size, at):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(at[0], at[1], at[2] + size[2] / 2))
    o = bpy.context.object
    o.name, o.scale, o.color = name, size, GREY
    return o


R = 30  # grid half-extent in metres
floor = quads("floor", [(-300, -300, 300, 300)], FLOOR, 0.0)
grid = quads("grid", [(i - 0.012, -R, i + 0.012, R) for i in range(-R, R + 1)] + [(-R, i - 0.012, R, i + 0.012) for i in range(-R, R + 1)],
             GRID, 0.002)


def delete(objs):
    for o in objs:
        bpy.data.objects.remove(o, do_unlink=True)


def horizon_y(cam):
    """Image fraction (0 = top) of the horizon: a point 1 km away at camera height, or None when the camera looks straight down."""
    fwd = cam.matrix_world.to_3x3() @ Vector((0, 0, -1))
    flat = Vector((fwd.x, fwd.y, 0))
    if flat.length < 1e-3:
        return None
    p = cam.matrix_world.translation + flat.normalized() * 1000
    v = world_to_camera_view(sc, cam, p)
    return round(1 - v.y, 4) if v.z > 0 else None


def feet(pose, box_):
    pts = [pose["points"][k] for k in ("lank", "rank") if pose["points"].get(k)]
    if not pts:
        return [round((box_[0] + box_[2]) / 2, 4), box_[3]] if box_ else None
    return [round(sum(p[0] for p in pts) / len(pts), 4), round(max(p[1] for p in pts), 4)]


current = None
rig, props = None, []
for cell in J["cells"]:
    if cell["pose"] != current:
        delete([o for o in (rig, *(rig.children_recursive if rig else ()), *props) if o])
        current = cell["pose"]
        r = cell["rig"]
        rig = mannequin("figure", GREY, {k: tuple(v) for k, v in r["rot"].items()})
        rig.scale, rig.location = (r["scale"],) * 3, r["pos"]
        rig.rotation_euler = tuple(math.radians(a) for a in r["euler"])
        props = [box(b["name"], b["size"], b["at"]) for b in cell["blocks"]]
        bpy.context.view_layer.update()
    c = cell["cam"]
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    sc.collection.objects.link(cam)
    cam.data.lens = c["lens"]
    cam.location = c["at"]
    cam.rotation_euler = (Vector(c["look"]) - Vector(c["at"])).to_track_quat("-Z", "Y").to_euler()
    sc.camera = cam
    bpy.context.view_layer.update()
    cell_dir = out / cell["dir"]
    cell_dir.mkdir(parents=True, exist_ok=True)
    render_still(cell_dir / "board.png")
    pose = figure_pose(rig, cam)
    box_ = screen_box(rig, cam)
    (cell_dir / "pose.json").write_text(json.dumps(pose, indent=1))
    # depth: no grid, far clip just behind the figure so the floor to the horizon doesn't crush the range
    grid.hide_render = True
    cam.data.clip_end = math.hypot(c["dist"], c["at"][2]) + 6
    render_depth(cell_dir / "depth.png", cam)
    grid.hide_render = False
    cam.data.clip_end = 1000
    meta = {"camera": {"height": round(c["at"][2], 3), "distance": round(c["dist"], 3), "lens": c["lens"],
                       "pitch_down_deg": round(90 - math.degrees(cam.rotation_euler.x), 2),
                       "yaw_deg": round(math.degrees(math.atan2(c["at"][0], c["at"][1])), 2)},
            "figure_box": box_, "feet": feet(pose, box_), "figure_height_px": round((box_[3] - box_[1]) * J["res"][1]) if box_ else 0,
            "horizon_y": horizon_y(cam), "back": pose["back"], "res": J["res"]}
    (cell_dir / "meta.json").write_text(json.dumps(meta, indent=1))
    delete([cam])
