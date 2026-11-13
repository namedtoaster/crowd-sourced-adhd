"""Spike A: do Blender materials survive the trip?

Builds three materials of rising difficulty, renders them in Eevee, then
sends them through three paths and renders each result:

  usd-preview   USD export with UsdPreviewSurface, then USD import
  usd-materialx USD export with a MaterialX network, then USD import
  recipe        our JSON node recipe, rebuilt node by node

Each render is compared with the original. The original is rendered twice
first to measure Eevee's own noise, so a path counts as lossless when it is
no further from the original than the original is from itself.

Run:
  blender -b --factory-startup -P spike_materials.py -- <out dir>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy
import numpy as np

OUT = Path(sys.argv[sys.argv.index("--") + 1]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
RES = (480, 270)

# ---------------------------------------------------------------------------
# Scene


def reset() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x, scene.render.resolution_y = RES
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.eevee.taa_render_samples = 32
    scene.view_settings.view_transform = "Standard"
    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.05, 0.05, 0.06, 1)
    scene.world = world

    cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
    scene.collection.objects.link(cam)
    cam.location = (0, -8.5, 1)
    cam.rotation_euler = (1.5708, 0, 0)
    scene.camera = cam

    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    sun.data.energy = 3.5
    sun.rotation_euler = (0.9, 0.2, 0.6)
    scene.collection.objects.link(sun)


def add_spheres() -> list[bpy.types.Object]:
    out = []
    for i, x in enumerate((-2.2, 0, 2.2)):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, radius=1, location=(x, 0, 1))
        ob = bpy.context.active_object
        ob.name = f"Sphere{i}"
        bpy.ops.object.shade_smooth()
        out.append(ob)
    return out


# ---------------------------------------------------------------------------
# Three materials, rising difficulty


def mat_clay() -> bpy.types.Material:
    m = bpy.data.materials.new("clay")
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.75, 0.35, 0.2, 1)
    bsdf.inputs["Roughness"].default_value = 0.8
    return m


def mat_rust() -> bpy.types.Material:
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
    mid = ramp.color_ramp.elements.new(0.5)
    mid.color = (0.45, 0.2, 0.08, 1)
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


def mat_toon() -> bpy.types.Material:
    """An Eevee only look: shade, quantize with a constant ramp, emit."""
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

# ---------------------------------------------------------------------------
# The recipe: a JSON node graph. No code, only node types, values and links.

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


def to_recipe(mat: bpy.types.Material) -> dict:
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
    return {"schema": "adhd/material-recipe@0", "name": mat.name, "nodes": nodes, "links": links}


def from_recipe(recipe: dict, name: str) -> bpy.types.Material:
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    by_name = {}
    for e in recipe["nodes"]:
        n = nt.nodes.new(e["type"])
        n.name = e["name"]
        for k, v in e["props"].items():  # enums first can change which sockets exist
            try:
                setattr(n, k, v)
            except (AttributeError, TypeError, ValueError):
                pass
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
        n = by_name[e["name"]]
        for ident, v in e["inputs"].items():
            sock = next((s for s in n.inputs if s.identifier == ident), None)
            if sock is not None and hasattr(sock, "default_value"):
                sock.default_value = v
    for l in recipe["links"]:
        a, b = by_name[l["from"]], by_name[l["to"]]
        out = next(s for s in a.outputs if s.identifier == l["out"])
        inp = next(s for s in b.inputs if s.identifier == l["in"])
        nt.links.new(out, inp)
    return m


# ---------------------------------------------------------------------------
# Rendering and comparing


def render(tag: str) -> Path:
    path = OUT / f"{tag}.png"
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    return path


def pixels(path: Path) -> np.ndarray:
    img = bpy.data.images.load(str(path), check_existing=False)
    arr = np.array(img.pixels[:], dtype=np.float32).reshape(img.size[1], img.size[0], 4)[..., :3]
    bpy.data.images.remove(img)
    return arr


def diff(a: Path, b: Path) -> dict:
    pa, pb = pixels(a), pixels(b)
    d = np.abs(pa - pb)
    w = pa.shape[1] // 3
    per = [float(d[:, i * w:(i + 1) * w].mean() * 255) for i in range(3)]  # one third per sphere
    return {"mean_0_255": round(float(d.mean() * 255), 3),
            "per_material_0_255": dict(zip(("clay", "rust", "toon"), [round(x, 3) for x in per])),
            "pixels_off_by_more_than_8": round(float((d.max(axis=2) * 255 > 8).mean() * 100), 2)}


def original_scene() -> list[bpy.types.Object]:
    reset()
    spheres = add_spheres()
    for ob, build in zip(spheres, BUILDERS):
        ob.data.materials.append(build())
    return spheres


def usd_roundtrip(tag: str, materialx: bool) -> dict:
    spheres = original_scene()
    usd = OUT / f"{tag}.usda"
    bpy.ops.object.select_all(action="DESELECT")
    for ob in spheres:
        ob.select_set(True)
    bpy.ops.wm.usd_export(filepath=str(usd), selected_objects_only=True, export_materials=True,
                          generate_preview_surface=True, generate_materialx_network=materialx,
                          export_lights=False, export_cameras=False)
    for ob in spheres:
        bpy.data.objects.remove(ob)
    for m in list(bpy.data.materials):
        bpy.data.materials.remove(m)
    bpy.ops.wm.usd_import(filepath=str(usd), import_materials=True, import_lights=False, import_cameras=False)
    imported = sorted({m.name for m in bpy.data.materials})
    nodes = {m.name: sorted({n.bl_idname for n in m.node_tree.nodes}) for m in bpy.data.materials if m.node_tree}
    return {"render": render(tag), "materials_after_import": imported, "node_types_after_import": nodes,
            "usd_bytes": usd.stat().st_size}


def main() -> None:
    results: dict = {"blender": bpy.app.version_string}

    original_scene()
    a = render("original")
    b = render("original_again")
    results["noise_floor"] = diff(a, b)

    # Recipe path
    spheres = original_scene()
    recipes = [to_recipe(ob.data.materials[0]) for ob in spheres]
    (OUT / "recipes.json").write_text(json.dumps(recipes, indent=2))
    original_nodes = {r["name"]: sorted({n["type"] for n in r["nodes"]}) for r in recipes}
    for ob, r in zip(spheres, json.loads((OUT / "recipes.json").read_text())):
        ob.data.materials.clear()
        ob.data.materials.append(from_recipe(r, r["name"] + "_rebuilt"))
    results["recipe"] = {"diff": diff(a, render("recipe")),
                         "recipe_bytes": (OUT / "recipes.json").stat().st_size,
                         "node_types": original_nodes}

    for tag, mx in (("usd_preview", False), ("usd_materialx", True)):
        info = usd_roundtrip(tag, mx)
        results[tag] = {"diff": diff(a, info.pop("render")), **info}

    (OUT / "results.json").write_text(json.dumps(results, indent=2))
    print("RESULTS " + json.dumps(results))


main()
