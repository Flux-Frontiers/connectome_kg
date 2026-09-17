# Release Notes -- v0.2.0

> Released: 2026-09-17

ConnectomeKG 0.2.0 is the first tagged release, and the first since the
repository became public. It makes the FlyWire FAFB v783 brain something you
can look at as well as query: real-geometry 3-D views of circuits and of
signal flow between brain regions, rendered in an interactive viewer, as flat
4K images, or as Looking Glass holograms. Alongside the views come an MCP
server for agents, 2-D circuit charts, a provenance report for every build,
and a documentation site.

## What changed

**3-D views of the brain.** `connkg viz3d` opens an interactive viewer and
`connkg quilt` renders the same scene headless. The circuit view draws the
traced skeletons of any cell types, neurons or community labels inside a
context cloud of all 139,255 neurons, each at its real position. The flow
view draws the neuropils linked by the signal their neurons carry from one
region to another, for the whole brain or for one population. `--floor` adds
a floor lit from above with shadows, `--elevation` tilts the camera, and
`--still` writes a single 3840 x 2160 image instead of a light-field quilt.
Quilts follow quiltwright's framing and depth budget, and cast straight to a
Looking Glass panel.

**Colours you can read.** Neuropils are coloured by brain region, grouped by
the nomenclature FlyWire follows, and every colour that carries meaning comes
from the colour-blind-safe Okabe-Ito palette. There are no pastels. The
context cloud is muted toward the background so the subject of each view
stands out, and the documentation includes a key for every colour, shape,
size and curve in the images.

**An MCP server.** `connkg-mcp` serves fourteen tools over stdio or SSE:
graph statistics, node lookup, partner types, the strongest synaptic path
between two populations, downstream and upstream cones, snapshots and more.
The CLI, the server and the Python API share one set of argument bounds, and
out-of-range values are rejected with a message rather than silently clamped.

**2-D circuit charts.** `connkg viz` draws a cell type's strongest input and
output partners as a network or as a partner bar chart, each written to one
self-contained HTML file.

**Provenance.** Every `connkg build` writes a report of package versions, the
input files and their checksums, stage timings and peak memory. Graph
snapshots record the connectome's metrics over time, and this release carries
one keyed to 0.2.0.

**Documentation.** The docs site at
https://flux-frontiers.github.io/connectome_kg/ covers downloading the data,
rendering in 3-D, how flow between neuropils is defined and measured, and an
API reference generated from the code. Renders of FlyWire data in the docs
are credited and shared under CC BY-NC-SA 4.0, separately from the software's
Elastic License 2.0.

## Upgrading

Rebuild the graph with `connkg build` so that it carries the annotation
layers and a build report. Install the `viz3d` extra for the 3-D views; it now
requires quiltwright 0.14.1 or later. `--color-by` applies to the circuit view
only, since the flow view's context cloud is always neutral grey. Renders made
before this release will look different, because both neuropil and cell-type
colours changed.

ConnectomeKG is still not published to PyPI. Install it from a clone or with
`pip install git+https://github.com/Flux-Frontiers/connectome_kg`. The wheel
and sdist for this version are attached to the GitHub Release.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
