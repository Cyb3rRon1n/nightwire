"""Inside Blender: blender -b -P blender_build.py -- scene.json outdir
Builds white room blocks, grey figures (capsule or 11-bone mannequin), one camera per shot on one timeline,
saves scene.blend, renders each shot's frames + start/middle/end previews, and an overhead floor plan."""

import json
import math
import shutil
import sys
from pathlib import Path

import bpy
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
scene_path, out = Path(args[0]), Path(args[1])
S = json.loads(scene_path.read_text())
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = "BLENDER_WORKBENCH"
sc.display.shading.light = "STUDIO"
sc.display.shading.color_type = "OBJECT"
sc.render.resolution_x, sc.render.resolution_y = S["res"]
sc.render.fps = S["fps"]
sc.frame_start, sc.frame_end = 0, max(S["frames"], 1)
sc.world = bpy.data.worlds.new("w")
sc.world.color = (0.05, 0.05, 0.06)

def box(name, size, at, rot=0.0, colour=(0.92, 0.92, 0.92, 1)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(at[0], at[1], at[2] + size[2] / 2))
    o = bpy.context.object
    o.name, o.scale, o.rotation_euler[2], o.color = name, size, math.radians(rot), colour
    return o

box("floor", (12, 12, 0.02), (0, 0, -0.02), colour=(0.18, 0.19, 0.21, 1))
for b in S["blocks"]:
    box(b["name"], b["size"], b["at"], b.get("rot", 0))

# Bone layout of the mannequin: (name, parent, head, tail) in metres, standing at origin facing +Y.
LAYOUT = [("hips", None, (0, 0, 0.95), (0, 0, 1.1)), ("spine", "hips", (0, 0, 1.1), (0, 0, 1.45)),
          ("head", "spine", (0, 0, 1.5), (0, 0, 1.72)),
          ("upper_arm.L", "spine", (0.2, 0, 1.42), (0.2, 0, 1.12)), ("forearm.L", "upper_arm.L", (0.2, 0, 1.12), (0.2, 0, 0.86)),
          ("upper_arm.R", "spine", (-0.2, 0, 1.42), (-0.2, 0, 1.12)), ("forearm.R", "upper_arm.R", (-0.2, 0, 1.12), (-0.2, 0, 0.86)),
          ("thigh.L", "hips", (0.1, 0, 0.95), (0.1, 0, 0.5)), ("shin.L", "thigh.L", (0.1, 0, 0.5), (0.1, 0, 0.05)),
          ("thigh.R", "hips", (-0.1, 0, 0.95), (-0.1, 0, 0.5)), ("shin.R", "thigh.R", (-0.1, 0, 0.5), (-0.1, 0, 0.05))]

def mannequin(fid, colour, rotations):
    """11-bone armature at the origin; one cylinder per bone, rigidly skinned with a vertex group + Armature modifier."""
    arm_data = bpy.data.armatures.new(fid)
    rig = bpy.data.objects.new(fid, arm_data)
    sc.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    for name, parent, head, tail in LAYOUT:
        b = arm_data.edit_bones.new(name)
        b.head, b.tail = head, tail
        if parent:
            b.parent = arm_data.edit_bones[parent]
    bpy.ops.object.mode_set(mode="OBJECT")
    for name, _parent, head, tail in LAYOUT:
        length = (Vector(tail) - Vector(head)).length
        radius = 0.11 if name == "head" else 0.07 if "arm" in name else 0.09
        bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=length, location=(Vector(head) + Vector(tail)) / 2)
        part = bpy.context.object
        part.name, part.color = f"{fid}.{name}", colour
        vg = part.vertex_groups.new(name=name)
        vg.add(range(len(part.data.vertices)), 1.0, "REPLACE")
        part.modifiers.new("rig", "ARMATURE").object = rig
        part.parent = rig  # rig sits at the origin with identity transform here, so world == local
    for name, (x, y, z) in rotations.items():
        pb = rig.pose.bones[name]
        pb.rotation_mode = "XYZ"
        pb.rotation_euler = (math.radians(x), math.radians(y), math.radians(z))
    return rig

def capsule(fid, colour):
    """Body cylinder plus a cone 'nose' showing facing; both parented to an empty at the origin."""
    root = bpy.data.objects.new(fid, None)
    sc.collection.objects.link(root)
    bpy.ops.mesh.primitive_cylinder_add(radius=0.22, depth=1.7, location=(0, 0, 0.85))
    body = bpy.context.object
    body.color, body.parent = colour, root
    bpy.ops.mesh.primitive_cone_add(radius1=0.08, depth=0.2, location=(0, 0.25, 1.5), rotation=(math.radians(-90), 0, 0))
    nose = bpy.context.object
    nose.color, nose.parent = colour, root
    return root

figures = {}
for f in S["figures"]:
    colour = (*f["tint"], 1)
    obj = mannequin(f["id"], colour, f["rotations"]) if f["tier"] in ("mannequin", "rigged") else capsule(f["id"], colour)
    for frame, x, y, facing in f["keys"]:
        obj.location = (x, y, 0)
        obj.rotation_euler = (0, 0, math.radians(facing - 90))
        obj.keyframe_insert("location", frame=frame)
        obj.keyframe_insert("rotation_euler", frame=frame)
    figures[f["id"]] = obj

def aim(cam, at, look):
    cam.location = at
    cam.rotation_euler = (Vector(look) - Vector(at)).to_track_quat("-Z", "Y").to_euler()

def render_still(path):
    sc.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)

for shot in S["shots"]:
    cam = bpy.data.objects.new(shot["id"], bpy.data.cameras.new(shot["id"]))
    sc.collection.objects.link(cam)
    cam.data.lens = shot["lens"]
    for frame, at, look in shot["camera"]:
        aim(cam, at, look)
        cam.keyframe_insert("location", frame=frame)
        cam.keyframe_insert("rotation_euler", frame=frame)
    sc.camera = cam
    start, end = shot["start_frame"], shot["end_frame"]
    frames = out / "shots" / shot["id"] / "frames"
    shutil.rmtree(frames, ignore_errors=True)
    # Exclusive end; frames are numbered from 0000 per shot so ffmpeg's %04d works for every shot.
    for frame in range(start, end):
        sc.frame_set(frame)
        render_still(frames / f"{frame - start:04d}.png")
    preview = out / "shots" / shot["id"] / "preview"
    preview.mkdir(parents=True, exist_ok=True)
    last = max(end - 1, start)
    for label, frame in (("start", start), ("middle", (start + last) // 2), ("end", last)):
        sc.frame_set(frame)
        render_still(preview / f"{label}.png")

# Overhead floor plan with C labels, figures at the first frame.
sc.frame_set(0)
top = bpy.data.objects.new("plan", bpy.data.cameras.new("plan"))
sc.collection.objects.link(top)
xs, ys = [], []
for b in S["blocks"]:
    r = math.radians(b.get("rot", 0))
    for dx in (-0.5, 0.5):
        for dy in (-0.5, 0.5):
            lx, ly = dx * b["size"][0], dy * b["size"][1]
            xs.append(b["at"][0] + lx * math.cos(r) - ly * math.sin(r))
            ys.append(b["at"][1] + lx * math.sin(r) + ly * math.cos(r))
for f in S["figures"]:
    for _t, x, y, _facing in f["keys"]:
        xs.append(x)
        ys.append(y)
cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
span = max(max(xs) - min(xs), max(ys) - min(ys), 2.0) + 2.0  # 1 m margin each side
top.data.type, top.data.ortho_scale = "ORTHO", span
top.location, top.rotation_euler = (cx, cy, 12), (0, 0, 0)
for fid, obj in figures.items():
    bpy.ops.object.text_add(location=(obj.location.x, obj.location.y + span * 0.09, 2.2))
    t = bpy.context.object
    t.data.body, t.data.size, t.data.align_x, t.data.align_y, t.color = fid, span * 0.07, "CENTER", "CENTER", (1.0, 0.9, 0.2, 1)
sc.camera = top
sc.render.resolution_x = sc.render.resolution_y = 1024
render_still(out / "floorplan.png")
bpy.ops.wm.save_as_mainfile(filepath=str(out / "scene.blend"))
