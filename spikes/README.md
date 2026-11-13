# Spikes

Short experiments that settle a design question before real code depends
on it. Each one runs headless in Blender and writes `results.json`.

```
blender -b --factory-startup -P spikes/<name>/spike_<name>.py -- <out dir>
```

Run on Blender 5.2.3 LTS (Python 3.13, OpenUSD 26.03 bundled), 13 Nov 2026.

## A. Materials: USD loses them, recipes keep them exactly

Three materials of rising difficulty, rendered in Eevee, sent through three
paths and rendered again. Eevee is deterministic here: the same scene
rendered twice differs by exactly 0.

| Path | Mean pixel error (0 to 255) | Clay | Rust | Toon | Pixels off by more than 8 |
|---|---|---|---|---|---|
| JSON recipe | **0.0** | 0.0 | 0.0 | 0.0 | 0% |
| USD, UsdPreviewSurface | 18.3 | 0.0 | 32.8 | 22.2 | 30% |
| USD, MaterialX | 18.3 | 0.0 | 32.8 | 22.2 | 30% |

![original](materials/results/original.png)

![after USD](materials/results/usd_preview.png)

Top: original. Bottom: after USD. Only the plain Principled material
survives. Through USD, every node graph collapses to a bare Principled
BSDF, so the rust and the toon sphere come back white. Blender writes
MaterialX on export but its importer ignores it, so MaterialX changes
nothing for a round trip.

The recipe is a JSON list of nodes (type, values, ramp stops) and links.
Three materials take 11 KB. Rebuilt node by node, the render is pixel
identical. It holds no code, so it is safe to accept from strangers, and
its node types are easy to check against an allowlist.

**Decision:** materials travel as recipes. USD carries geometry only.

## B. Animation: USD keeps it, including onto a library rig

A skinned three bone rig (3,744 vertices), animated over 48 frames with up
to 1.34 m of motion. Every vertex is compared on every frame.

| Path | Max error | Pass (0.1 mm) |
|---|---|---|
| USD round trip: mesh, skeleton and animation | 0.0011 mm | yes |
| Animation from USD onto a fresh copy of the rig | 0.0011 mm | yes |

The second row is the real case: contributors animate a library rig, only
the animation travels, and it is applied to the film's own copy of the rig.

What it took:

- USD brings rotations back as **quaternions**. A pose bone only reads the
  curves that match its rotation mode, so the receiving rig must be set to
  quaternion first. Without that the rig does not move at all.
- Bone names and the rest pose must match the library rig exactly. The
  add-on should check both before export.
- Blender samples every frame on export (48 keys per curve), so the
  original keyframe spacing is not kept. The motion is.

**Decision:** animation travels as USD skeletal animation on a library rig.

## Follow ups

- Export animation without the mesh. The test file is 900 KB because it
  carries the whole skinned mesh; the add-on should send only the skeleton
  animation.
- Lights and cameras: same question as materials, not tested yet.
