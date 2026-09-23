# Release Notes -- v0.7.1

> Released: 2026-09-22

A visual bug in the 3-D views, shipped in 0.7.0 and fixed the same day: a floored render of a circuit drawn as lines could fail to compile a shader and log a VTK error.

## What changed

**Line skeletons no longer draw a stray point at every traced point.** 0.7.0's rewrite of the skeleton mesh built it with `pv.PolyData(points)`, whose constructor adds a vertex cell for every point passed to it. The lines were then set on top, so every skeleton rendered its points as well as its lines. Points carry no normals, so with `--floor` the shadow pass took the unlit branch and failed to compile the shader for them -- VTK logged `Could not set shader program` on the first floored render of a scene. The mesh is built empty and its points and lines assigned separately again, which is how it worked before 0.7.0 and adds no vertex cells.

Only line-drawn skeletons were affected. `--tubes` renders a surface with no line or vertex cells, so every quilt in the docs and any render that pairs `--floor` with `--tubes` was never wrong.

## Upgrading

Nothing to do. No cache format change, no new command, no new option. If you built or rebuilt against 0.7.0, this replaces the affected code path; no rebuild of the skeleton cache is needed.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
