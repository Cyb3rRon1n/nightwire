"""Inside Blender: blender -b -P blender_stage.py -- job.json out.blend
Builds a shot's stage for the owner: a camera matched to the plate (height, pitch from the horizon, lens), the plate behind it,
an invisible floor to snap to, and one posable grey mannequin per board figure standing where the board put its feet.
The Nightwire add-on (nightwire_stage_addon.py) reads scene["nightwire_stage"] to export boards back into the shot folder.

The mannequin helper is not copied: it is pulled out of blender_build.py (next to this file) with ast, like blender_library.py."""

import ast
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

args = sys.argv[sys.argv.index("--") + 1:]
J = json.loads(Path(args[0]).read_text())
OUT = Path(args[1])
GREY = (0.45, 0.45, 0.47, 1)

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
here = Path(J["helpers"])
tree = ast.parse(here.read_text())
keep = [n for n in tree.body if (isinstance(n, ast.FunctionDef) and n.name == "mannequin")
        or (isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") in {"LAYOUT", "MANNEQUIN_BUILD"})]
exec(compile(ast.Module(body=keep, type_ignores=[]), "blender_build.py", "exec"), globals())  # noqa: S102

W, H = J["res"]
sc.render.resolution_x, sc.render.resolution_y = W, H
sc.render.engine = "BLENDER_WORKBENCH"
sc.display.shading.light, sc.display.shading.color_type, sc.display.shading.show_object_outline = "STUDIO", "OBJECT", True
sc.view_settings.view_transform = "Standard"
sc.render.film_transparent = True
sc.world = bpy.data.worlds.new("w")

# camera: at (0, 0, height) looking along +Y, pitched so the plate's horizon lands on the same row
cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
sc.collection.objects.link(cam)
cam.data.lens, cam.data.sensor_fit, cam.data.sensor_width = J["lens"], "HORIZONTAL", 36.0
cam.data.clip_start, cam.data.clip_end = 0.05, 500
tan_h = 18.0 / J["lens"]
tan_v = tan_h * H / W
pitch_down = math.atan((0.5 - J["horizon_y"]) * 2 * tan_v)
cam.location = (0, 0, J["cam_height_m"])
cam.rotation_euler = (math.pi / 2 - pitch_down, 0, 0)
cam.lock_location = cam.lock_rotation = (True, True, True)  # the plate is a fixed photo: moving the camera breaks the match
sc.camera = cam
bg = cam.data.background_images.new()
bg.image = bpy.data.images.load(J["plate"])
bg.display_depth, bg.alpha, bg.frame_method = "BACK", 1.0, "FIT"
cam.data.show_background_images = True
bpy.context.view_layer.update()

# invisible floor to snap feet to
bpy.ops.mesh.primitive_plane_add(size=80, location=(0, 40, 0))
floor = bpy.context.object
floor.name, floor.display_type, floor.hide_render = "Floor (snap here)", "WIRE", True


def ground(fx, fy):
    """World point on the floor under frame position (fx, fy) 0..1, or None above the horizon."""
    d = cam.matrix_world.to_3x3() @ Vector(((fx - 0.5) * 2 * tan_h, (0.5 - fy) * 2 * tan_v, -1))
    if d.z >= -1e-6:
        return None
    return cam.matrix_world.translation + d * (-cam.matrix_world.translation.z / d.z)


for f in J["figures"]:
    p = ground(*f["feet"])
    if p is None:
        print(f"skip {f['label']}: feet above the horizon")
        continue
    to_cam = cam.matrix_world.translation - p
    to_cam.z = 0
    face = Matrix.Rotation(math.radians(f["yaw"]), 3, "Z") @ to_cam.normalized()  # the library camera's yaw, kept as the view of the figure
    rz = math.atan2(-face.x, face.y)
    r = f["rig"]
    rig = mannequin(f["label"], GREY, {k: tuple(v) for k, v in r["rot"].items()})
    rig.scale = (r["scale"],) * 3
    rig.rotation_euler = (math.radians(r["euler"][0]), math.radians(r["euler"][1]), rz + math.radians(r["euler"][2]))
    rig.location = p + Matrix.Rotation(rz, 3, "Z") @ Vector(r["pos"])
    rig["nightwire_label"] = f["label"]

sc["nightwire_stage"] = json.dumps({"shot_dir": "//", "plate": "//stage-plate.png"})  # relative: works on any machine
for area_hint in ("Use the Nightwire tab in the 3D view sidebar (N): Export start / Export end.",):
    t = bpy.data.texts.new("README")
    t.write("Nightwire stage for " + J["title"] + "\n\n"
            "- Numpad 0: look through the camera (the plate is behind it). The camera is locked to the plate.\n"
            "- Select a figure, Ctrl+Tab: pose mode; R to rotate bones. G to move a figure along the floor (snap to 'Floor').\n"
            "- " + area_hint + "\n"
            "- An exported board is used by the pipeline and is never overwritten by 'shorts boards'.\n")
bpy.ops.wm.save_as_mainfile(filepath=str(OUT))
bpy.ops.file.make_paths_relative()
bpy.ops.wm.save_mainfile()
print("stage saved", OUT)
