"""Spike B: does animation survive USD?

Builds a skinned three bone rig, animates it over 48 frames and records
where every vertex of the skinned mesh is on every frame. Then:

  usd-roundtrip   export mesh + armature + animation to USD, import, compare
  library-rig     take only the animation from the imported USD and put it
                  on a fresh copy of the original rig (the "library rig"
                  case: contributors animate, the rig itself never travels)

A path passes when every vertex lands within 0.1 mm of where it was, on
every frame. The rig is 3 m tall.

Run:
  blender -b --factory-startup -P spike_animation.py -- <out dir>
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np

OUT = Path(sys.argv[sys.argv.index("--") + 1]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
FRAMES = range(1, 49)
TOLERANCE_M = 1e-4

POSES = {  # frame: per bone XYZ euler in degrees
    1: [(0, 0, 0), (0, 0, 0), (0, 0, 0)],
    12: [(25, 0, 10), (-35, 15, 0), (40, 0, -20)],
    24: [(-15, 30, 0), (50, 0, 25), (-30, 20, 0)],
    36: [(10, -20, -30), (-20, -10, 40), (60, -15, 10)],
    48: [(0, 0, 0), (0, 0, 0), (0, 0, 0)],
}


def build_rig(animate: bool = True) -> tuple[bpy.types.Object, bpy.types.Object]:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.frame_start, scene.frame_end = FRAMES.start, FRAMES.stop - 1

    arm_data = bpy.data.armatures.new("Rig")
    rig = bpy.data.objects.new("Rig", arm_data)
    scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    parent = None
    for i in range(3):
        b = arm_data.edit_bones.new(f"bone{i}")
        b.head, b.tail = (0, 0, i), (0, 0, i + 1)
        if parent:
            b.parent, b.use_connect = parent, True
        parent = b
    bpy.ops.object.mode_set(mode="OBJECT")

    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.3, depth=3, location=(0, 0, 1.5))
    body = bpy.context.active_object
    body.name = "Body"
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.subdivide(number_cuts=11)
    bpy.ops.object.mode_set(mode="OBJECT")

    bpy.ops.object.select_all(action="DESELECT")
    body.select_set(True)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")

    if animate:
        for frame, rots in POSES.items():
            for pb, rot in zip(rig.pose.bones, rots):
                pb.rotation_mode = "XYZ"
                pb.rotation_euler = [math.radians(a) for a in rot]
                pb.keyframe_insert("rotation_euler", frame=frame)
    else:
        for pb in rig.pose.bones:
            pb.rotation_mode = "XYZ"
    return rig, body


def sample(mesh_ob: bpy.types.Object) -> np.ndarray:
    """World position of every vertex on every frame: frames x verts x 3."""
    scene = bpy.context.scene
    out = []
    for f in FRAMES:
        scene.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        ev = mesh_ob.evaluated_get(dg)
        me = ev.to_mesh()
        co = np.empty(len(me.vertices) * 3, dtype=np.float64)
        me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        mw = np.array(ev.matrix_world)
        out.append(co @ mw[:3, :3].T + mw[:3, 3])
        ev.to_mesh_clear()
    return np.stack(out)


def compare(a: np.ndarray, b: np.ndarray) -> dict:
    if a.shape != b.shape:
        return {"pass": False, "reason": f"vertex count differs: {a.shape} vs {b.shape}"}
    err = np.linalg.norm(a - b, axis=2)
    worst = np.unravel_index(err.argmax(), err.shape)
    return {"pass": bool(err.max() <= TOLERANCE_M),
            "max_error_mm": round(float(err.max() * 1000), 4),
            "mean_error_mm": round(float(err.mean() * 1000), 5),
            "worst_frame": int(FRAMES[worst[0]])}


def action_curves(action: bpy.types.Action) -> list:
    curves = list(getattr(action, "fcurves", []) or [])
    if not curves and getattr(action, "layers", None):  # layered actions keep curves in channelbags
        for layer in action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    curves += list(bag.fcurves)
    return curves


def assign_action(ob: bpy.types.Object, action: bpy.types.Action) -> None:
    # USD brings rotations back as quaternions. Pose bones only read the
    # curves that match their rotation mode, so match the rig to the action.
    if any(c.data_path.endswith("rotation_quaternion") for c in action_curves(action)):
        for pb in ob.pose.bones:
            pb.rotation_mode = "QUATERNION"
    ob.animation_data_create()
    ob.animation_data.action = action
    slots = getattr(action, "slots", None)  # layered actions (Blender 4.4+)
    if slots and getattr(ob.animation_data, "action_slot", None) is None:
        ob.animation_data.action_slot = slots[0]


def main() -> None:
    results: dict = {"blender": bpy.app.version_string, "frames": len(FRAMES), "tolerance_mm": TOLERANCE_M * 1000}

    rig, body = build_rig()
    reference = sample(body)
    results["vertices"] = int(reference.shape[1])
    results["max_motion_m"] = round(float(np.linalg.norm(reference - reference[0], axis=2).max()), 3)

    usd = OUT / "anim.usda"
    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True)
    body.select_set(True)
    bpy.ops.wm.usd_export(filepath=str(usd), selected_objects_only=True, export_animation=True,
                          export_armatures=True, export_materials=False)
    results["usd_bytes"] = usd.stat().st_size

    # Path 1: full round trip
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.frame_start, bpy.context.scene.frame_end = FRAMES.start, FRAMES.stop - 1
    bpy.ops.wm.usd_import(filepath=str(usd), import_skeletons=True, set_frame_range=False)
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    arms = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    info = {"meshes": len(meshes), "armatures": len(arms)}
    if arms:
        a = arms[0]
        info["bones"] = [b.name for b in a.data.bones]
        act = a.animation_data.action if a.animation_data else None
        info["action"] = act.name if act else None
        if act is not None:
            curves = action_curves(act)
            info["fcurves"] = len(curves)
            info["keys_per_curve"] = max((len(c.keyframe_points) for c in curves), default=0)
            info["fcurve_paths_sample"] = sorted({c.data_path for c in curves})[:4]
    results["usd_roundtrip"] = {**info, **(compare(reference, sample(meshes[0])) if meshes else {"pass": False})}

    # Path 2: animation from USD onto a fresh library rig
    imported_action = arms[0].animation_data.action if arms and arms[0].animation_data else None
    if imported_action is None:
        results["library_rig"] = {"pass": False, "reason": "no action on the imported armature"}
    else:
        imported_action.use_fake_user = True
        keep = imported_action.name
        tmp = OUT / "action_carrier.blend"
        bpy.data.libraries.write(str(tmp), {imported_action})
        rig2, body2 = build_rig(animate=False)
        with bpy.data.libraries.load(str(tmp)) as (src, dst):
            dst.actions = [keep]
        assign_action(rig2, dst.actions[0])
        bone_names = {b.name for b in rig2.data.bones}
        results["library_rig"] = {"bones_match": sorted(bone_names) == sorted(info.get("bones", [])),
                                  **compare(reference, sample(body2))}

    (OUT / "results.json").write_text(json.dumps(results, indent=2))
    print("RESULTS " + json.dumps(results))


main()
