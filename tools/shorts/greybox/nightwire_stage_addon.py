"""Nightwire stage export, a Blender add-on (installed by `python -m tools.shorts stage`).
Sidebar tab "Nightwire" in the 3D view: Export start / Export end write the shot's board from the current stage:
board-<which>.owner.png (grey figures over the dimmed plate), .owner.pose.json (OpenPose points per figure) and
.owner.depth.png. `shorts boards` then uses them instead of building its own."""

bl_info = {"name": "Nightwire stage", "blender": (4, 2, 0), "category": "3D View", "version": (1, 0, 0)}

import ast
import json
import tempfile
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view  # noqa: F401  (used by the pulled helpers)
from mathutils import Vector  # noqa: F401

DIM = 0.55  # same dimming as tools/greybox_library/insert.py


HELPER_SRC = ""  # filled in by tools/shorts/stage.py install_addon: figure_pose / render_depth / render_still from blender_build.py


def _helpers():
    names = {"figure_pose", "render_depth", "render_still"}
    tree = ast.parse(HELPER_SRC)
    keep = [n for n in tree.body if (isinstance(n, ast.FunctionDef) and n.name in names)
            or (isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") in {"UP", "CAPSULE_PTS"})]
    g = dict(globals(), sc=bpy.context.scene)
    exec(compile(ast.Module(body=keep, type_ignores=[]), "blender_build.py", "exec"), g)  # noqa: S102
    return g


def export(which):
    import numpy as np
    sc = bpy.context.scene
    info = json.loads(sc["nightwire_stage"])
    g = _helpers()
    shot = Path(bpy.path.abspath(info["shot_dir"]))
    shot.mkdir(parents=True, exist_ok=True)
    cam = sc.camera
    figs = [o for o in sc.objects if o.type == "ARMATURE" and "nightwire_label" in o]
    with tempfile.TemporaryDirectory() as tmp:
        fig_png = Path(tmp) / "figures.png"
        g["render_still"](fig_png)
        top = bpy.data.images.load(str(fig_png))
        plate = bpy.data.images.load(bpy.path.abspath(info["plate"]))
        try:
            w, h = top.size
            if tuple(plate.size) != (w, h):
                plate.scale(w, h)
            a = np.array(top.pixels[:], dtype=np.float32).reshape(h, w, 4)
            b = np.array(plate.pixels[:], dtype=np.float32).reshape(h, w, 4)
            out = b[..., :3] * DIM * (1 - a[..., 3:]) + a[..., :3] * a[..., 3:]
            res = bpy.data.images.new("board", w, h, alpha=False)
            res.pixels = np.dstack([out, np.ones((h, w, 1), np.float32)]).ravel().tolist()
            res.filepath_raw, res.file_format = str(shot / f"board-{which}.owner.png"), "PNG"
            res.save()
            bpy.data.images.remove(res)
        finally:
            bpy.data.images.remove(top)
            bpy.data.images.remove(plate)
    poses = {o["nightwire_label"]: g["figure_pose"](o, cam) for o in figs}
    (shot / f"board-{which}.owner.pose.json").write_text(json.dumps(poses, indent=1))
    hidden = [o for o in sc.objects if o.hide_render is False and o.type == "MESH" and o.parent is None]
    for o in hidden:  # depth of the figures only
        o.hide_render = True
    try:
        g["render_depth"](shot / f"board-{which}.owner.depth.png", cam)
    finally:
        for o in hidden:
            o.hide_render = False
    return shot / f"board-{which}.owner.png"


class NIGHTWIRE_OT_export(bpy.types.Operator):
    bl_idname = "nightwire.export_board"
    bl_label = "Export board"
    which: bpy.props.EnumProperty(items=[("start", "start", ""), ("end", "end", "")])

    def execute(self, context):
        if "nightwire_stage" not in context.scene:
            self.report({"ERROR"}, "not a Nightwire stage file")
            return {"CANCELLED"}
        path = export(self.which)
        self.report({"INFO"}, f"wrote {path.name}; run: python -m tools.shorts boards <short>")
        return {"FINISHED"}


class NIGHTWIRE_PT_stage(bpy.types.Panel):
    bl_space_type, bl_region_type, bl_category, bl_label = "VIEW_3D", "UI", "Nightwire", "Stage"

    def draw(self, context):
        col = self.layout.column()
        if "nightwire_stage" not in context.scene:
            col.label(text="Open a shot's stage.blend")
            return
        col.operator("nightwire.export_board", text="Export start").which = "start"
        col.operator("nightwire.export_board", text="Export end").which = "end"


CLASSES = (NIGHTWIRE_OT_export, NIGHTWIRE_PT_stage)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
