"""Inside Blender: blender -b -P blender_build.py -- scene.json outdir
Builds white room blocks, grey figures (capsule or 11-bone mannequin), one camera per shot on one timeline,
saves scene.blend, renders each shot's frames + start/middle/end previews, and an overhead floor plan."""

import json
import math
import shutil
import sys
import zlib
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
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
        obj.location = (x, y, -f.get("drop", 0.0))
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

KEY_W, KEY_H = 1216, 832  # keep in step with tools/shorts/guides.py


def screen_box(obj, cam):
    """0..1 image-fraction box of a figure (own box + all child parts, deformed by the pose), or None if off screen."""
    dg = bpy.context.evaluated_depsgraph_get()
    pts = []
    for o in (obj, *obj.children_recursive):
        ev = o.evaluated_get(dg)
        if ev.type in {"MESH", "CURVE"}:  # empties/armatures have no usable bound_box
            pts += [world_to_camera_view(sc, cam, ev.matrix_world @ Vector(c)) for c in ev.bound_box]
    xs = [min(max(p.x, 0), 1) for p in pts if p.z > 0]
    ys = [min(max(1 - p.y, 0), 1) for p in pts if p.z > 0]
    if not xs or max(xs) - min(xs) < 0.01 or max(ys) - min(ys) < 0.01:
        return None
    return [round(min(xs), 4), round(min(ys), 4), round(max(xs), 4), round(max(ys), 4)]


UP = Vector((0, 0, 1))
# OpenPose 18-point names in tools/reference_library._ORDER; left side is +x in the figure's own frame (it faces +Y).
CAPSULE_PTS = {"neck": (0, 0, 1.5), "rsho": (-.2, 0, 1.45), "lsho": (.2, 0, 1.45), "relb": (-.22, 0, 1.1), "lelb": (.22, 0, 1.1),
               "rwri": (-.22, 0, .85), "lwri": (.22, 0, .85), "rhip": (-.1, 0, .95), "lhip": (.1, 0, .95), "rkne": (-.1, 0, .5),
               "lkne": (.1, 0, .5), "rank": (-.1, 0, .05), "lank": (.1, 0, .05)}


def figure_pose(obj, cam):
    """{points: {openpose name: [x, y] image fractions or None}, back: bool} for one figure at the current frame."""
    ev = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mw = ev.matrix_world
    if ev.type == "ARMATURE":
        pb = ev.pose.bones
        w = lambda v: mw @ v  # noqa: E731
        pts = {"neck": w(pb["spine"].tail), "rsho": w(pb["upper_arm.R"].head), "lsho": w(pb["upper_arm.L"].head),
               "relb": w(pb["upper_arm.R"].tail), "lelb": w(pb["upper_arm.L"].tail),
               "rwri": w(pb["forearm.R"].tail), "lwri": w(pb["forearm.L"].tail),
               "rhip": w(pb["thigh.R"].head), "lhip": w(pb["thigh.L"].head), "rkne": w(pb["thigh.R"].tail), "lkne": w(pb["thigh.L"].tail),
               "rank": w(pb["shin.R"].tail), "lank": w(pb["shin.L"].tail)}
        hb = pb["head"]
        centre = w((hb.head + hb.tail) / 2)
        delta = (hb.matrix @ hb.bone.matrix_local.inverted()).to_3x3()  # the head's pose rotation, so a turned head turns the face
        face = (mw.to_3x3() @ (delta @ Vector((0, 1, 0)))).normalized()
    else:  # capsule: fixed offsets, facing from the object's rotation
        pts = {k: mw @ Vector(v) for k, v in CAPSULE_PTS.items()}
        centre = mw @ Vector((0, 0, 1.6))
        face = (mw.to_3x3() @ Vector((0, 1, 0))).normalized()
    right = UP.cross(face).normalized()
    pts.update(nose=centre + .11 * face, reye=centre + .09 * face + .03 * UP + .04 * right, leye=centre + .09 * face + .03 * UP - .04 * right,
               rear=centre + .1 * right, lear=centre - .1 * right)
    out = {}
    for k, p in pts.items():
        v = world_to_camera_view(sc, cam, p)
        out[k] = [round(v.x, 4), round(1 - v.y, 4)] if v.z > 0 and 0 <= v.x <= 1 and 0 <= v.y <= 1 else None
    return {"points": out, "back": face.dot(centre - cam.matrix_world.translation) > 0}


def render_depth(path, cam):
    """White = near, black = far, normalised over the visible range. The Z pass goes through a compositor File Output node as a float
    OpenEXR (the Viewer node image is empty in background mode), is read back with numpy at the scene resolution and saved as an
    8-bit PNG. Compositor state is restored."""
    import tempfile
    import numpy as np
    vl, old_nodes, old_z = bpy.context.view_layer, sc.use_nodes, bpy.context.view_layer.use_pass_z
    old_comp, old_pct = sc.render.use_compositing, sc.render.resolution_percentage
    vl.use_pass_z, sc.use_nodes, sc.render.use_compositing, sc.render.resolution_percentage = True, True, True, 100
    tree = sc.node_tree
    tmp = path.with_name(".tmp-" + path.name)
    img = None
    with tempfile.TemporaryDirectory() as zdir:
        try:
            for n in list(tree.nodes):
                tree.nodes.remove(n)
            rl, comp, fo = tree.nodes.new("CompositorNodeRLayers"), tree.nodes.new("CompositorNodeComposite"), tree.nodes.new("CompositorNodeOutputFile")
            fo.base_path = zdir
            fo.format.file_format, fo.format.color_depth, fo.format.color_mode = "OPEN_EXR", "32", "BW"
            if hasattr(fo, "file_slots"):
                fo.file_slots[0].path = "z_"
            else:  # newer Blender: output items
                fo.file_output_items.clear()
                fo.file_output_items.new("FLOAT", "z_")
            tree.links.new(rl.outputs["Depth"], fo.inputs[0])
            tree.links.new(rl.outputs["Image"], comp.inputs["Image"])
            render_still(tmp)
            exr = sorted(Path(zdir).glob("z_*.exr"))
            if not exr:
                raise RuntimeError("depth: compositor wrote no EXR (files: %s)" % [p.name for p in Path(zdir).iterdir()])
            img = bpy.data.images.load(str(exr[0]))
            img.colorspace_settings.name = "Non-Color"
            w, h = img.size
            z = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, -1)[..., 0]
            if (w, h) != (sc.render.resolution_x, sc.render.resolution_y):
                raise RuntimeError(f"depth: got {w}x{h}, expected {sc.render.resolution_x}x{sc.render.resolution_y}")
            seen = z < 1e4  # background is ~1e10
            out_z = np.zeros_like(z)
            if seen.any():
                lo, hi = float(z[seen].min()), float(z[seen].max())
                out_z[seen] = 0.08 + 0.92 * (1 - (z[seen] - lo) / max(hi - lo, 1e-6))  # nearest = 1.0, farthest visible stays above black
            res = bpy.data.images.new("depth_out", w, h, alpha=False, float_buffer=False)
            res.colorspace_settings.name = "Non-Color"
            res.pixels = np.dstack([out_z, out_z, out_z, np.ones_like(out_z)]).ravel().tolist()
            res.filepath_raw, res.file_format = str(path), "PNG"
            res.save()
            bpy.data.images.remove(res)
        finally:
            for n in list(tree.nodes):
                tree.nodes.remove(n)
            sc.use_nodes, vl.use_pass_z, sc.render.use_compositing, sc.render.resolution_percentage = old_nodes, old_z, old_comp, old_pct
            if img is not None:
                bpy.data.images.remove(img)
            tmp.unlink(missing_ok=True)


def render_guides(shot, cam, start, last):
    """Flat white-on-black renders at keyframe size (with and without figures) plus figure screen regions; restores all state."""
    guide = out / "shots" / shot["id"] / "guide"
    guide.mkdir(parents=True, exist_ok=True)
    sh, res, world = sc.display.shading, (sc.render.resolution_x, sc.render.resolution_y), tuple(sc.world.color)
    saved = (sh.light, sh.color_type, sh.show_object_outline)
    old_colours = {o.name: tuple(o.color) for o in bpy.data.objects}
    old_hide = {o.name: o.hide_render for o in bpy.data.objects}
    boxes = {}

    def unhide():
        for o in bpy.data.objects:
            o.hide_render = old_hide[o.name]

    try:
        fig_shade = {c.name: 0.9 + 0.05 * (i % 3) for i, o in enumerate(figures.values()) for c in (o, *o.children_recursive)}
        for o in bpy.data.objects:  # one stable shade per room object (0.25..0.85), one near-white shade per figure
            g = fig_shade[o.name] if o.name in fig_shade else 0.25 + 0.6 * (zlib.crc32(o.name.encode()) % 1000) / 999
            o.color = (g, g, g, 1)
        sc.render.resolution_x, sc.render.resolution_y = KEY_W, KEY_H
        sh.light, sh.color_type, sh.show_object_outline = "FLAT", "OBJECT", True
        sc.world.color = (0, 0, 0)
        for label, frame in (("start", start), ("end", last)):
            sc.frame_set(frame)
            bpy.context.view_layer.update()
            render_still(guide / f"{label}.png")
            render_depth(guide / f"{label}-depth.png", cam)
            boxes[label] = {fid: b for fid, o in figures.items() if (b := screen_box(o, cam))}
            (guide / f"{label}-pose.json").write_text(json.dumps({fid: figure_pose(figures[fid], cam) for fid in boxes[label]}, indent=1))
            for o in figures.values():
                o.hide_render = True
                for c in o.children_recursive:
                    c.hide_render = True
            render_still(guide / f"{label}-room.png")
            unhide()
        (guide / "regions.json").write_text(json.dumps(boxes, indent=1))
    finally:
        unhide()
        sc.render.resolution_x, sc.render.resolution_y = res
        sh.light, sh.color_type, sh.show_object_outline = saved
        for o in bpy.data.objects:
            o.color = old_colours[o.name]
        sc.world.color = world


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
    render_guides(shot, cam, start, last)

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
