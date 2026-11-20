"""Spike E: does work made in an older Blender come through on the pinned one?

Two modes, run with different Blenders:

  export   run in the contributor's Blender (4.2, 4.5, ...). Builds a prop,
           three material recipes and a skinned animation, exports them the
           way the add-on would, and records reference data next to them.
  import   run in the pinned Blender (5.2). Loads what an export run made and
           compares it with the reference, and with the same work made
           natively in the pinned Blender.

Run:
  blender -b --factory-startup -P spike_versions.py -- export <dir>
  blender -b --factory-startup -P spike_versions.py -- import <export dir> <out dir>

Pass bars (same as spikes A and B):
  prop       same vertex, face and UV counts; every vertex within 0.01 mm
  materials  every recipe rebuilds with no dropped values, links or nodes,
             and renders the same as recipes made natively (mean pixel
             error no worse than the native render's own noise)
  animation  every vertex within 0.1 mm on every frame, both as a full
             round trip and applied to a fresh library rig
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np

ARGS = sys.argv[sys.argv.index("--") + 1:]
MODE = ARGS[0]
FRAMES = range(1, 49)
ANIM_TOL_M = 1e-4
PROP_TOL_M = 1e-5
RES = (480, 270)

# ---------------------------------------------------------------------------
# Compatibility shims, by feature detection, never by version number


def eevee_id() -> str:
    items = {e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items}
    return "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in items else "BLENDER_EEVEE"


def op_kwargs(op, **kwargs) -> tuple[dict, list[str]]:
    """Drop keyword arguments this Blender's operator does not have."""
    have = {p.identifier for p in op.get_rna_type().properties}
    return {k: v for k, v in kwargs.items() if k in have}, sorted(k for k in kwargs if k not in have)


def action_curves(action) -> list:
    curves = list(getattr(action, "fcurves", []) or [])
    if not curves and getattr(action, "layers", None):
        for layer in action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    curves += list(bag.fcurves)
    return curves


def assign_action(ob, action) -> None:
    if any(c.data_path.endswith("rotation_quaternion") for c in action_curves(action)):
        for pb in ob.pose.bones:
            pb.rotation_mode = "QUATERNION"
    ob.animation_data_create()
    ob.animation_data.action = action
    slots = getattr(action, "slots", None)
    if slots and getattr(ob.animation_data, "action_slot", None) is None:
        ob.animation_data.action_slot = slots[0]


def environment() -> dict:
    env = {"blender": bpy.app.version_string, "python": sys.version.split()[0], "eevee_id": eevee_id()}
    try:
        from pxr import Usd  # noqa: PLC0415

        env["pxr"] = ".".join(str(x) for x in Usd.GetVersion())
    except Exception as e:  # noqa: BLE001
        env["pxr"] = f"not importable: {type(e).__name__}: {e}"
    return env


# ---------------------------------------------------------------------------
# The prop


def build_prop():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_monkey_add(location=(0.3, -0.2, 1.1), rotation=(0.2, 0, 0.4))
    ob = bpy.context.active_object
    ob.name = "Prop"
    mod = ob.modifiers.new("Sub", "SUBSURF")
    mod.levels = 1
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.ops.object.shade_smooth()
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    return ob


def prop_stats(ob) -> dict:
    me = ob.data
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    mw = np.array(ob.matrix_world)
    world = co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3]
    return {"verts": len(me.vertices), "faces": len(me.polygons), "loops": len(me.loops),
            "uv_layers": len(me.uv_layers), "positions": world.round(7).tolist()}


def compare_prop(ref: dict, got: dict) -> dict:
    out = {k: [ref[k], got[k]] for k in ("verts", "faces", "loops", "uv_layers")}
    counts_ok = all(a == b for a, b in out.values())
    a, b = np.array(ref["positions"]), np.array(got["positions"])
    if a.shape != b.shape:
        return {"pass": False, "counts": out}
    in_order = float(np.linalg.norm(a - b, axis=1).max())
    srt = float(np.abs(np.sort(a, axis=0) - np.sort(b, axis=0)).max())
    err = min(in_order, srt)
    return {"pass": counts_ok and err <= PROP_TOL_M, "counts": out,
            "max_error_mm": round(err * 1000, 5), "vertex_order_kept": in_order <= PROP_TOL_M}


# ---------------------------------------------------------------------------
# Materials (same three as spike A)


def mat_clay():
    m = bpy.data.materials.new("clay")
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.75, 0.35, 0.2, 1)
    bsdf.inputs["Roughness"].default_value = 0.8
    return m


def mat_rust():
    m = bpy.data.materials.new("rust")
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 6.0
    noise.inputs["Detail"].default_value = 8.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = (0.12, 0.05, 0.02, 1)
    ramp.color_ramp.elements[1].position = 0.7
    ramp.color_ramp.elements[1].color = (0.8, 0.38, 0.1, 1)
    ramp.color_ramp.elements.new(0.5).color = (0.45, 0.2, 0.08, 1)
    rough = nt.nodes.new("ShaderNodeMapRange")
    rough.inputs["To Min"].default_value = 0.4
    rough.inputs["To Max"].default_value = 0.95
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.4
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(noise.outputs["Fac"], rough.inputs["Value"])
    nt.links.new(rough.outputs["Result"], bsdf.inputs["Roughness"])
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return m


def mat_toon():
    m = bpy.data.materials.new("toon")
    m.use_nodes = True
    nt = m.node_tree
    out = nt.nodes["Material Output"]
    nt.nodes.remove(nt.nodes["Principled BSDF"])
    diffuse = nt.nodes.new("ShaderNodeBsdfDiffuse")
    diffuse.inputs["Color"].default_value = (1, 1, 1, 1)
    to_rgb = nt.nodes.new("ShaderNodeShaderToRGB")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = "CONSTANT"
    ramp.color_ramp.elements[0].color = (0.05, 0.1, 0.25, 1)
    ramp.color_ramp.elements[1].position = 0.45
    ramp.color_ramp.elements[1].color = (0.3, 0.6, 0.9, 1)
    rim = nt.nodes.new("ShaderNodeLayerWeight")
    rim.inputs["Blend"].default_value = 0.25
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs["B"].default_value = (1, 0.9, 0.7, 1)
    emit = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(diffuse.outputs["BSDF"], to_rgb.inputs["Shader"])
    nt.links.new(to_rgb.outputs["Color"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], mix.inputs["A"])
    nt.links.new(rim.outputs["Facing"], mix.inputs["Factor"])
    nt.links.new(mix.outputs["Result"], emit.inputs["Color"])
    nt.links.new(emit.outputs["Emission"], out.inputs["Surface"])
    return m


BUILDERS = (mat_clay, mat_rust, mat_toon)
SKIP_PROPS = {"rna_type", "name", "label", "location", "width", "height", "dimensions",
              "select", "show_options", "show_preview", "hide", "mute", "show_texture",
              "use_custom_color", "color", "parent", "inputs", "outputs", "internal_links",
              "bl_idname", "bl_label", "bl_description", "bl_icon", "bl_static_type",
              "bl_width_default", "bl_width_min", "bl_width_max", "bl_height_default",
              "bl_height_min", "bl_height_max", "type", "is_active_output", "location_absolute",
              "warning_propagation", "color_tag"}


def _plain(v):
    if hasattr(v, "__len__") and not isinstance(v, str):
        return [_plain(x) for x in v]
    return v


def to_recipe(mat) -> dict:
    nodes = []
    for n in mat.node_tree.nodes:
        props = {}
        for p in n.bl_rna.properties:
            if p.identifier in SKIP_PROPS or p.is_readonly or p.type in {"POINTER", "COLLECTION"}:
                continue
            props[p.identifier] = _plain(getattr(n, p.identifier))
        entry = {"type": n.bl_idname, "name": n.name, "props": props, "inputs": {}}
        for s in n.inputs:
            if not s.is_linked and hasattr(s, "default_value") and s.enabled:
                entry["inputs"][s.identifier] = _plain(s.default_value)
        if n.bl_idname == "ShaderNodeValToRGB":
            r = n.color_ramp
            entry["ramp"] = {"interpolation": r.interpolation, "color_mode": r.color_mode,
                             "elements": [[e.position, list(e.color)] for e in r.elements]}
        nodes.append(entry)
    links = [{"from": l.from_node.name, "out": l.from_socket.identifier,
              "to": l.to_node.name, "in": l.to_socket.identifier} for l in mat.node_tree.links]
    return {"schema": "adhd/material-recipe@0", "blender": bpy.app.version_string,
            "name": mat.name, "nodes": nodes, "links": links}


def from_recipe(recipe: dict, name: str, problems: list) -> object:
    """Rebuild a recipe, recording anything that does not land."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    by_name = {}
    for e in recipe["nodes"]:
        try:
            n = nt.nodes.new(e["type"])
        except RuntimeError as err:
            problems.append(f"{recipe['name']}: node type {e['type']} missing ({err})")
            continue
        n.name = e["name"]
        for k, v in e["props"].items():
            if not hasattr(n, k):
                problems.append(f"{recipe['name']}: {e['type']}.{k} no longer exists")
                continue
            try:
                setattr(n, k, v)
            except (AttributeError, TypeError, ValueError) as err:
                problems.append(f"{recipe['name']}: {e['type']}.{k} = {v!r} rejected ({err})")
        if "ramp" in e:
            r = n.color_ramp
            r.interpolation = e["ramp"]["interpolation"]
            r.color_mode = e["ramp"]["color_mode"]
            els = e["ramp"]["elements"]
            while len(r.elements) < len(els):
                r.elements.new(0.5)
            while len(r.elements) > len(els):
                r.elements.remove(r.elements[-1])
            for el, (pos, col) in zip(r.elements, els):
                el.position, el.color = pos, col
        by_name[n.name] = n
    for e in recipe["nodes"]:
        n = by_name.get(e["name"])
        if n is None:
            continue
        for ident, v in e["inputs"].items():
            sock = next((s for s in n.inputs if s.identifier == ident), None)
            if sock is None or not hasattr(sock, "default_value"):
                problems.append(f"{recipe['name']}: {e['type']} input {ident} missing")
                continue
            try:
                sock.default_value = v
            except (TypeError, ValueError) as err:
                problems.append(f"{recipe['name']}: {e['type']} input {ident} rejected ({err})")
    for l in recipe["links"]:
        a, b = by_name.get(l["from"]), by_name.get(l["to"])
        out = next((s for s in a.outputs if s.identifier == l["out"]), None) if a else None
        inp = next((s for s in b.inputs if s.identifier == l["in"]), None) if b else None
        if out is None or inp is None:
            problems.append(f"{recipe['name']}: link {l['from']}.{l['out']} -> {l['to']}.{l['in']} dropped")
            continue
        nt.links.new(out, inp)
    return m


def render_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = eevee_id()
    scene.render.resolution_x, scene.render.resolution_y = RES
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.eevee.taa_render_samples = 32
    scene.view_settings.view_transform = "Standard"
    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.05, 0.05, 0.06, 1)
    scene.world = world
    cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
    scene.collection.objects.link(cam)
    cam.location, cam.rotation_euler = (0, -8.5, 1), (1.5708, 0, 0)
    scene.camera = cam
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    sun.data.energy = 3.5
    sun.rotation_euler = (0.9, 0.2, 0.6)
    scene.collection.objects.link(sun)
    spheres = []
    for i, x in enumerate((-2.2, 0, 2.2)):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, radius=1, location=(x, 0, 1))
        ob = bpy.context.active_object
        ob.name = f"Sphere{i}"
        bpy.ops.object.shade_smooth()
        spheres.append(ob)
    return spheres


def render(path: Path) -> np.ndarray:
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(str(path), check_existing=False)
    arr = np.array(img.pixels[:], dtype=np.float32).reshape(img.size[1], img.size[0], 4)[..., :3]
    bpy.data.images.remove(img)
    return arr


def pixel_diff(a: np.ndarray, b: np.ndarray) -> dict:
    d = np.abs(a - b)
    w = a.shape[1] // 3
    per = [round(float(d[:, i * w:(i + 1) * w].mean() * 255), 3) for i in range(3)]
    return {"mean_0_255": round(float(d.mean() * 255), 3),
            "per_material_0_255": dict(zip(("clay", "rust", "toon"), per)),
            "pixels_off_by_more_than_8": round(float((d.max(axis=2) * 255 > 8).mean() * 100), 2)}


# ---------------------------------------------------------------------------
# Animation (same rig as spike B)

POSES = {
    1: [(0, 0, 0), (0, 0, 0), (0, 0, 0)],
    12: [(25, 0, 10), (-35, 15, 0), (40, 0, -20)],
    24: [(-15, 30, 0), (50, 0, 25), (-30, 20, 0)],
    36: [(10, -20, -30), (-20, -10, 40), (60, -15, 10)],
    48: [(0, 0, 0), (0, 0, 0), (0, 0, 0)],
}


def build_rig(animate: bool = True):
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
    for pb in rig.pose.bones:
        pb.rotation_mode = "XYZ"
    if animate:
        for frame, rots in POSES.items():
            for pb, rot in zip(rig.pose.bones, rots):
                pb.rotation_euler = [math.radians(a) for a in rot]
                pb.keyframe_insert("rotation_euler", frame=frame)
    return rig, body


def sample(mesh_ob) -> np.ndarray:
    scene = bpy.context.scene
    out = []
    for f in FRAMES:
        scene.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        ev = mesh_ob.evaluated_get(dg)
        me = ev.to_mesh()
        co = np.empty(len(me.vertices) * 3, dtype=np.float64)
        me.vertices.foreach_get("co", co)
        mw = np.array(ev.matrix_world)
        out.append(co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3])
        ev.to_mesh_clear()
    return np.stack(out)


def compare_anim(a: np.ndarray, b: np.ndarray) -> dict:
    if a.shape != b.shape:
        return {"pass": False, "reason": f"vertex count differs: {a.shape} vs {b.shape}"}
    err = np.linalg.norm(a - b, axis=2)
    return {"pass": bool(err.max() <= ANIM_TOL_M), "max_error_mm": round(float(err.max() * 1000), 4),
            "worst_frame": int(FRAMES[np.unravel_index(err.argmax(), err.shape)[0]])}


# ---------------------------------------------------------------------------
# Modes


def export(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    res: dict = {"env": environment(), "dropped_export_options": {}}

    ob = build_prop()
    (out / "prop_reference.json").write_text(json.dumps(prop_stats(ob)))
    kw, dropped = op_kwargs(bpy.ops.wm.usd_export, filepath=str(out / "prop.usda"), selected_objects_only=True,
                            export_materials=False, export_uvmaps=True, export_normals=True,
                            export_animation=False)
    ob.select_set(True)
    bpy.ops.wm.usd_export(**kw)
    res["dropped_export_options"]["prop"] = dropped

    render_scene()
    recipes = [to_recipe(build()) for build in BUILDERS]
    (out / "recipes.json").write_text(json.dumps(recipes, indent=2))
    res["recipe_node_types"] = {r["name"]: sorted({n["type"] for n in r["nodes"]}) for r in recipes}

    rig, body = build_rig()
    np.save(out / "anim_reference.npy", sample(body))
    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True)
    body.select_set(True)
    kw, dropped = op_kwargs(bpy.ops.wm.usd_export, filepath=str(out / "anim.usda"), selected_objects_only=True,
                            export_animation=True, export_armatures=True, export_materials=False)
    bpy.ops.wm.usd_export(**kw)
    res["dropped_export_options"]["anim"] = dropped
    res["action_api"] = "layered" if getattr(rig.animation_data.action, "layers", None) else "legacy"

    (out / "export.json").write_text(json.dumps(res, indent=2))
    print("EXPORT " + json.dumps(res))


def import_(src: Path, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    exp = json.loads((src / "export.json").read_text())
    res: dict = {"pinned": environment(), "made_in": exp["env"]}

    # Prop
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.wm.usd_import(filepath=str(src / "prop.usda"))
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    ref = json.loads((src / "prop_reference.json").read_text())
    res["prop"] = compare_prop(ref, prop_stats(meshes[0])) if meshes else {"pass": False, "reason": "no mesh"}

    # Materials: the old recipes against recipes made natively here
    spheres = render_scene()
    for ob, build in zip(spheres, BUILDERS):
        ob.data.materials.append(build())
    native = render(out / "native.png")
    native_again = render(out / "native_again.png")
    spheres = render_scene()
    problems: list = []
    for ob, r in zip(spheres, json.loads((src / "recipes.json").read_text())):
        ob.data.materials.append(from_recipe(r, r["name"] + "_old", problems))
    rebuilt = render(out / "rebuilt.png")
    noise = pixel_diff(native, native_again)
    d = pixel_diff(native, rebuilt)
    res["materials"] = {"pass": not problems and d["mean_0_255"] <= noise["mean_0_255"] + 0.01,
                        "problems": problems, "diff": d, "noise_floor": noise}

    # Animation: full round trip, then onto a fresh library rig made here
    reference = np.load(src / "anim_reference.npy")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.frame_start, scene.frame_end = FRAMES.start, FRAMES.stop - 1
    bpy.ops.wm.usd_import(**op_kwargs(bpy.ops.wm.usd_import, filepath=str(src / "anim.usda"),
                                      import_skeletons=True, set_frame_range=False)[0])
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    arms = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    res["animation_roundtrip"] = compare_anim(reference, sample(meshes[0])) if meshes else {"pass": False}
    act = arms[0].animation_data.action if arms and arms[0].animation_data else None
    if act is None:
        res["animation_library_rig"] = {"pass": False, "reason": "no action on the imported armature"}
    else:
        act.use_fake_user = True
        keep = act.name
        carrier = out / "action_carrier.blend"
        bpy.data.libraries.write(str(carrier), {act})
        rig2, body2 = build_rig(animate=False)
        with bpy.data.libraries.load(str(carrier)) as (_, dst):
            dst.actions = [keep]
        assign_action(rig2, dst.actions[0])
        res["animation_library_rig"] = compare_anim(reference, sample(body2))

    res["pass"] = all(res[k]["pass"] for k in ("prop", "materials", "animation_roundtrip", "animation_library_rig"))
    (out / "results.json").write_text(json.dumps(res, indent=2))
    print("IMPORT " + json.dumps(res))


def render_native(out: Path) -> None:
    """Render the three materials as made in this Blender, for a same look check."""
    out.mkdir(parents=True, exist_ok=True)
    spheres = render_scene()
    for ob, build in zip(spheres, BUILDERS):
        ob.data.materials.append(build())
    render(out / "native.png")


if MODE == "export":
    export(Path(ARGS[1]).resolve())
elif MODE == "import":
    import_(Path(ARGS[1]).resolve(), Path(ARGS[2]).resolve())
elif MODE == "render":
    render_native(Path(ARGS[1]).resolve())
else:
    raise SystemExit(f"unknown mode {MODE!r}")
