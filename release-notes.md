# Release Notes -- v0.7.0

> Released: 2026-09-22

Traced neurons stop looking like heaps of blocks. The 3-D viewer opens on a circuit instead of refusing to start.

## What changed

**Neurons are drawn as continuous, tapering tubes.** The circuit view built its mesh from one line per traced edge, each carrying its own pair of points, so `--tubes` extruded a separate cylinder per edge: consecutive cylinders met at an angle with nothing joining them, and a neuron came out a heap of faceted stubs. It now walks the skeleton's parent links and draws each unbranched run between branch points as a single polyline, which tubes into one continuous surface with mitred joins. That costs *less*, because a run's interior points are shared rather than repeated once per edge -- 2.8 M cells against 3.4 M on `circuit:compass` -- and the saving pays for doubling the tube from 6 sides to 12.

A tube's radius is the radius FlyWire traced at that point, rather than one width for every neuron. It is clamped at both ends. The floor is the width skeletons were drawn at before, because FAFB's median traced radius is 222 nm, a thread at whole-brain framing: the old constant was doing visibility work, and keeping it as a floor means nothing draws thinner than it used to. The ceiling is the width of the sphere that marks a soma, so no neurite is drawn fatter than its own cell body -- without it the giant fiber, the thickest axon in the brain, ballooned to thirteen times the floor and swallowed the arbor around it.

**Turning the taper on needs one command.** The traced radius was being parsed and then thrown away, so the cache never held it. Cache format 2 stores it, and until a cache is rebuilt its radii read back as zeros and skeletons draw at the old constant width -- which is what they did before, so nothing breaks in the meantime:

```bash
connkg skeletons --data-dir fafb_v783 -j 12
```

That is about three minutes on twelve cores. It re-reads the SWC download once and rewrites the somas as well, so soma coverage is unaffected.

**`connkg viz3d` launches without a SPEC.** It used to refuse, with `--view circuit needs at least one SPEC` -- a guard shared with `connkg quilt`, where it is right, since quilt renders a file and exits and an empty circuit spends a 4K render on nothing. The viewer is interactive and has the Show box, so it now opens on `circuit:compass`: 151 neurons across five cell types, central in the brain and small enough to read as a circuit. Any SPEC replaces it. On a connectome whose cell types that circuit does not name, the default resolves to nothing and the viewer opens on the brain alone rather than captioning a scene it is not drawing.

## Upgrading

Nothing is required. A graph built by 0.6.0 works unchanged, and a skeleton cache written by it still loads.

To see the taper, re-run `connkg skeletons` as above; a format-1 cache draws exactly as it did before until you do. If you call `connectomekg.scene` from Python, `_segments_to_polydata` is gone -- `connectomekg.skeletons.polylines` replaces `segments` as the drawing path, and `segments` itself is unchanged for anything that measures rather than draws.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
