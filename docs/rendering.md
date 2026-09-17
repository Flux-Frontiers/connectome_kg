# Rendering the connectome in 3-D

`connkg quilt` and `connkg viz3d` draw a connectome where it is: every neuron
at its real position in the brain. Other 3-D views in the KGRAG fleet grow
an invented tree layout. A connectome does not need one, because the
microscope already put every neuron somewhere.

Two views are available:

- **Circuit** (`--view circuit`, the default) draws the traced skeletons of
  the neurons that one or more SPECs resolve to.
- **Flow** (`--view flow`) draws neuropils as spheres, linked by tubes
  weighted by how much signal the brain's neurons carry between them.

Both views draw the whole brain as a context cloud behind the subject, and
both render either as a Looking Glass quilt or in an interactive viewer.

![The two DNp01 descending neurons inside the whole-brain context cloud](images/circuit_dnp01.png)

*Circuit view: the two DNp01 giant fiber neurons, drawn from their traced
skeletons, inside the FAFB v783 context cloud.*

![Neuropil flow across the whole brain, strongest 100 pairs](images/flow_all.png)

*Flow view: the strongest 100 of 5,786 directed neuropil pairs.*

## Quilts and Looking Glass displays

A Looking Glass display shows a 3-D scene without glasses. Lenticular optics
send a slightly different image toward each viewing angle, so each eye sees
the scene from its own position. The display plays a *quilt*: a single PNG
that tiles many renders of the same scene in a grid, one per camera
position.

ConnectomeKG does not build quilts itself. It composes a PyVista scene, and
[quiltwright](https://flux-frontiers.github.io/quiltwright/) renders that scene into a quilt, reports its depth
budget, and sends it to the display. For each view, quiltwright:

1. Starts from the scene's camera. The camera's focal point becomes the
   plane of the physical glass. ConnectomeKG places the focal plane inside
   the brain (see [Camera and framing](#camera-and-framing)), so nearer
   structures stand in front of the glass and farther ones sit behind it.
2. Slides the camera sideways across the display's view cone without
   turning it.
3. Renders with an off-axis (asymmetric-frustum) projection, which keeps the
   glass plane identical in every view. The display can only fuse views that
   share that plane. Turning each camera toward the subject ("toe-in")
   produces ghosting instead of depth.

The default preset, `16-landscape`, targets the 16-inch landscape display:
48 views in 8 columns and 6 rows, and a 7680 x 4320 quilt. The display
accepts a 50-degree view cone, but `connkg quilt` sweeps 35 degrees by
default (`--view-cone`), the same cap quiltwright's own CLI applies. View 0, the leftmost camera, is the bottom-left tile. The filename
suffix, for example `_qs8x6a1.77778`, records the columns, rows and aspect
ratio, so Looking Glass Bridge configures playback from the name.

A scene that is too deep for the display looks blurred at its front and
back. The *depth budget* is how far in front of and behind the glass plane a
scene can extend before that happens. `connkg quilt` checks it on every run
(see [World coordinates](#world-coordinates)).

For the full method, the other rendering backends, and Bridge setup, see the
[quiltwright documentation](https://flux-frontiers.github.io/quiltwright/), in particular
[the PyVista backend](https://flux-frontiers.github.io/quiltwright/lfd/).

## Before you begin

You need the following:

- The `viz3d` extra, which installs PyVista, PyQt5, pyvistaqt and
  [quiltwright](https://flux-frontiers.github.io/quiltwright/):

    ```bash
    pip install -e ".[viz3d]"      # or: poetry install --extras viz3d
    ```

- A built graph in `.connectomekg/graph.sqlite`. See the README for
  `connkg build`.
- For the circuit view, the skeleton download in
  `fafb_v783/sk_lod1_783_healed/`, which holds one `.swc` file per neuron
  (about 31 GB). Without it, each circuit neuron is drawn as a sphere at its
  marked point. The flow view does not read skeletons.

## Render a view

A SPEC is a cell type name (`LC4`), a root id, a neuron node id, or
`label:<regex>` over community labels. Specs are case-sensitive.

To open a view in the interactive viewer, run `connkg viz3d`:

```bash
connkg --root . viz3d LC4 DNp01                 # circuit: two cell types
connkg --root . viz3d --view flow               # flow: whole brain
connkg --root . viz3d --view flow LC4           # flow carried by LC4 only
```

Drag to orbit, scroll to zoom, and shift-drag to pan. To send the current
camera view to a Looking Glass display as a quilt, click **Cast to Looking
Glass**. Looking Glass Bridge must be running; see
[Set up Bridge and the display](https://flux-frontiers.github.io/quiltwright/lfd/#1-set-up-bridge-and-the-display).

To render a quilt without a window, run `connkg quilt`:

```bash
connkg --root . quilt DNp01 --preview dnp01.png
connkg --root . quilt --view flow --top 60 --floor --cast
```

To render one flat image instead of a quilt, add `--still`. The still is the
quilt's centre view at the preset's aspect, 3840 x 2160 for `16-landscape`:

```bash
connkg --root . quilt LPLC2 DNp01 --tubes --floor --still
```

`connkg quilt` prints what it drew and, for a quilt, a depth report. It then
writes files under `renders/`:

| path | contents |
|---|---|
| `renders/stills/` | a `--still` image, and the `--preview` PNG when the value is a bare filename |
| `renders/quilts/` | the quilt, named after the specs (`flow_LC4_qs8x6a1.77778.png` for a flow) |

Quilts are never committed.

### Options

| option | views | default | effect |
|---|---|---|---|
| `--view` | both | `circuit` | `circuit` or `flow` |
| `--color-by` | both | `super_class` | context cloud colour: `super_class` or `sign` |
| `--data-dir` | circuit | `fafb_v783` | skeleton download root |
| `--skeleton-step` | circuit | `4` | keep every Nth skeleton point, 1 to 50 |
| `--tubes` | circuit | off | draw skeletons as tubes instead of lines |
| `--top` | flow | `100` | strongest neuropil pairs drawn, 1 to 500 |
| `--floor` | both | off | stand the scene over a floor lit from above, with shadows |
| `--elevation` | both | `25` with `--floor`, else `0` | degrees to tilt the camera up so it looks down, -80 to 80 |
| `--preset` | both | `16-landscape` | quiltwright quilt preset (8 x 6 views) |
| `--view-cone` | quilt | `35` | degrees the quilt cameras sweep |
| `--fov`, `--zoom` | quilt | `14.0`, `1.0` | per-view field of view in degrees, and camera dolly |
| `--still` | quilt | off | render one flat centre view instead of a quilt |
| `--cast` | quilt | off | send the finished quilt to Looking Glass Bridge; not with `--still` |

The circuit view needs at least one SPEC. In the flow view, SPECs are
optional.

## How a scene is built

Every render path calls one function,
`connectomekg.scene.build_brain_scene`. It composes the scene into a PyVista
plotter that the caller supplies. `connkg quilt` passes an off-screen
plotter, the viewer passes its Qt widget, and **Cast to Looking Glass**
rebuilds the scene in a fresh off-screen plotter. All three therefore draw
the same thing.

The function works in four steps:

1. Set the background to a muted grey (`scene.BACKGROUND`, `#5A5D62`).
2. Compute the world frame from the neuron positions.
3. Draw the context cloud.
4. Draw the circuit or the flow.

The module is split so most of it runs without PyVista. `world_frame`,
`context_points`, `circuit_neurons`, `neuropil_flow` and `flow_arc` are
NumPy and SQL only. The tests exercise them without the `viz3d` extra.

### Data each view reads

| data | source | read by |
|---|---|---|
| neuron positions | `x`, `y`, `z` in each neuron node's metadata (the Codex marked point, in nm) | world frame, context cloud, flow centroids |
| super class and sign | neuron node metadata | context cloud colour |
| skeletons | `fafb_v783/sk_lod1_783_healed/<root_id>.swc` | circuit |
| per-neuron neuropil synapse counts | `IN_NEUROPIL` edge evidence, `{"pre": n, "post": m}` | flow |
| neuropil synapse totals | neuropil node metadata, `n_synapses` | flow sphere size |

## World coordinates

FAFB coordinates are image coordinates in nanometres: `x` runs across the
brain, `y` increases ventrally, and `z` runs through the section stack. The
3-D stack expects `+z` up.

`build_brain_scene` centres the scene on the median neuron position and
scales it to 1 world unit per 100,000 nm. It maps each point as follows:

```
world = ((x - cx) / S,  (z - cz) / S,  -(y - cy) / S)       S = 100,000 nm
```

Negating `y` puts dorsal up. At this scale the brain is about 8 x 4 x 3 world
units, which fits inside the depth budget of a Looking Glass quilt.

## Camera and framing

`connectomekg.scene.aim_camera` sets the camera in three steps:

1. `kg_utils.viz3d.frame_tree` points the camera along world `+y`, so you
   see the brain from the front with dorsal up.
2. With a non-zero `--elevation`, the camera tilts up by that many degrees
   and looks down on the brain.
3. `quiltwright.frame_and_focus` fits the scene tightly at that final
   direction and puts the focal plane at the harmonic mean of the scene's
   near and far depths. A tilted view framed by `reset_camera()` instead
   leaves the brain small in frame.

`frame_and_focus` fits to the window's shape, so `connkg quilt` sizes its
window to the aspect quiltwright captures each view at (16:9 for
`16-landscape`), not to the quilt tile (4:3). After framing, the camera is
fixed: the depth report and the render both take `fov=None`, so neither
re-frames it.

For a quilt, `connkg quilt` prints `quiltwright.depth_report` for that
camera and `--zoom`. The report lists how many pixels the nearest and
farthest geometry shift between neighbouring views. Around 4 to 5 px is the
practical ceiling, and rows above 5.5 px are flagged as soft. The flow view
with a floor comes to about 3.4 px at `--zoom 1.0` and about 3.7 px at
`--zoom 1.1`. Above about 1.15 the camera crops the optic lobes, because the
brain already spans the width of the frame.

## The context cloud

The context cloud draws each neuron as a small sphere at its marked point.
The cloud shows the outline of the brain: optic lobes, central brain and
the gaps between regions.

Three choices keep it visible without covering the subject:

- **Spheres sized in world units, not pixels.** A 2-pixel point disappears
  in a Retina window and in a quilt tile. A world-sized sphere scales with
  the camera like the rest of the scene. Each sphere is a low-poly glyph (6 x
  4 facets), so the full 139,255-neuron cloud is about 3.3 million triangles
  and composes in under a second.
- **Lightened colours, not transparency.** Each colour moves 35% toward
  white so that it stands out from the grey background. Transparency is
  avoided because alpha blending ghosts between views in a light-field
  render.
- **Thinner in the flow view.** The flow view draws every 10th neuron with
  larger spheres (radius 0.014 world units, against 0.005 in the circuit
  view). At full density, the cloud hides the neuropil spheres inside it.

With `--color-by super_class`, the colours follow `connectomekg.colors`:
central neurons blue, optic neurons green, sensory neurons orange, and so on.
With `--color-by sign`, excitatory neurons are warm, inhibitory neurons cool,
and unknown neurons grey.

A marked point is not a cell body. It can be tens of microns from the
soma. The cloud shows where neurons are, not where their
cell bodies are.

## The circuit view

The circuit view draws the neurons that the SPECs resolve to, at full
brightness:

1. **Resolve.** Each SPEC goes through `ConnectomeKG.neurons_of`, and the
   results are merged without duplicates. A scene holds at most
   `MAX_SCENE_NEURONS` (500) neurons. Above that, the render stops with an
   error that names the count, because a silently sampled circuit looks
   complete when it is not. Narrow the spec instead.
2. **Load skeletons.** `connectomekg.skeletons.read_swc` parses each
   neuron's SWC file. SWC coordinates share the graph's nanometre frame, so
   skeletons and the cloud line up without a transform.
3. **Simplify.** `--skeleton-step N` keeps every Nth point along each
   unbranched run. Roots, the soma, and every branch point and tip are always
   kept, so the branching shape stays intact at any step. Branch points and
   tips come from the parent links, not from the SWC labels, which real
   skeletons do not apply consistently.
4. **Draw.** All the neurons of one cell type share a single line mesh
   (`skeleton:<type>`), so a 100-neuron type costs one draw call. A sphere
   marks each soma (`soma:<type>`).

Each cell type's colour comes from a fixed palette, indexed by
`seed_from_key(type name)`. The same type has the same colour in every
render and every session. The colour identifies the type; it does not
encode a category.

Two fallbacks keep a neuron visible when data is missing, and the command
output counts both:

- **Missing skeletons:** a neuron with no SWC file is drawn as a larger
  sphere at its marked point (`fallback:<type>`). The larger size marks it
  as a stand-in, not a measured soma.
- **Soma fallbacks:** in about 6% of skeletons, no row is labelled soma, so
  the soma sphere sits at the skeleton's root point instead.

## The flow view

The flow view shows how signal moves between brain regions, summed over
neurons.

![Neuropil flow carried by the 104 LC4 neurons](images/flow_lc4.png)

*Flow carried by LC4 only. About 90% of it runs from the lobula (LO) to the
posterior ventrolateral protocerebrum (PVLP) on each side.*

### What flow measures

Each synapse lies in one neuropil. The neuropil breakdown on a synapse edge
records where two neurons meet, not how signal moves from one region to
another. Signal crosses from neuropil A to neuropil B inside a single neuron
that takes input in A and makes output in B.

For each neuron `n`, the `IN_NEUROPIL` edges give `post_n(A)`, the input
synapses `n` receives in A, and `pre_n(B)`, the output synapses `n` makes in
B. The flow from A to B is:

```
F(A -> B) = sum over neurons n of   pre_n(B) * post_n(A) / post_n(total)      A != B
```

In words, each neuron's output synapses in B are split across neuropils in
proportion to where that neuron takes its input, and the result is summed
over all neurons. The unit is output synapses.

For example, suppose a neuron takes 30 input synapses in A and 10 in B, and
makes 20 output synapses in B and 40 in C. Three quarters of its input is in
A and one quarter is in B, so it contributes:

| pair | contribution |
|---|---|
| A -> B | 20 x 0.75 = 15 |
| A -> C | 40 x 0.75 = 30 |
| B -> C | 40 x 0.25 = 10 |

Flow within one neuropil (A -> A) is left out. A neuron with no input
synapses contributes nothing, because its output cannot be attributed to a
source.

Keep three limits in mind when you read a flow picture:

- Flow counts synapses, not activity. A strong tube means many synapses sit
  on that route, not that the route is active.
- Transmitter sign is ignored. Excitatory and inhibitory synapses add
  together.
- The split assumes that a neuron's output draws evenly on all of its
  input. That approximation fits a compact neuron better than a neuron with
  separate input and output compartments.

### What is drawn

- **Neuropil spheres** sit at the synapse-weighted centroid of the marked
  points of every neuron in that neuropil. The centroids always use every
  neuron, even when SPECs restrict the flow, so a neuropil sits in the same
  place in every flow render. A sphere's radius scales with the cube root of
  the neuropil's synapse count, up to 0.22 world units. A centroid is a
  position, not the neuropil's shape: the Codex download has no neuropil
  meshes.
- **Colour** comes from the neuropil name without its side, so `LO_L` and
  `LO_R` match.
- **Tubes** follow the `--top` strongest pairs. A tube's radius scales with
  the square root of its flow relative to the strongest drawn pair, and its
  colour is the source neuropil's colour.
- **Direction** shows in the curve. Each tube bows to one side of the line
  between its endpoints, along the cross product of that line and world up,
  so A -> B and B -> A curve to opposite sides instead of overlapping.
- **Idle neuropils**, those with no drawn tube, are drawn at half size and
  darker.

### Restrict flow to a population

When you pass SPECs with `--view flow`, only those neurons count toward the
flow. For example, `connkg viz3d --view flow LC4` shows where the 104 LC4
neurons carry signal. The flow view has no neuron limit, because it draws
only neuropils and tubes, never individual neurons.

### Scale and cost on FAFB v783

`neuropil_flow` reads 421,132 `IN_NEUROPIL` edges and 139,255 neuron
positions. It aggregates 138,584 neurons into 5,786 directed pairs across
79 neuropils in about 1.5 seconds, so the flow is computed at render time
and nothing extra is stored in the graph.

The strongest pairs follow the visual pathway:

| pair | flow (output synapses) |
|---|---|
| ME_R -> LO_R | 1,413,667 |
| ME_L -> LO_L | 1,412,266 |
| LA_R -> ME_R | 886,045 |
| LA_L -> ME_L | 527,637 |
| LO_R -> LOP_R | 420,874 |
| ME_R -> LOP_R | 411,959 |
| LO_L -> PVLP_L | 351,335 |

The top 50 pairs carry 46% of all flow, and the top 200 carry 66%, so the
default of 100 shows most of the picture. The difference between LA_R ->
ME_R and LA_L -> ME_L is present in the `IN_NEUROPIL` counts themselves. The
aggregation does not introduce it.

## Floor and shadows

`--floor` stands the scene over a floor and lights it from above so that it
casts shadows. The shadow shows where structures sit in depth, which helps
most in a still and on the panel.

![LPLC2 and DNp01 over a floor, with shadows](images/floor_lplc2_dnp01.png)

*`connkg quilt LPLC2 DNp01 --tubes --floor --still`: the 210 LPLC2 neurons
and the two DNp01 neurons, drawn as tubes, over the floor.*

`connectomekg.scene.add_floor` adds three things:

- **A floor plane** in the background grey, a little below the scene and
  far larger than the frame, so it fills the view behind the brain. The
  floor is only visible from a camera that looks down on it, which is why
  `--floor` defaults `--elevation` to 25 degrees.
- **A key light**: a spotlight high above the brain with a 75-degree cone
  that casts the shadows, plus a weak headlight so that shadowed surfaces
  stay readable.
- **Shadow mapping** at 8192 x 8192 pixels. At VTK's default of 1024, the
  shadows are visibly blocky at 4K, and a wide cone spreads the map over
  more floor. A narrower cone gives sharper shadows but shows its circular
  edge on the floor.

The floor is added after the camera is framed and after the depth report,
because it reaches past the camera and would otherwise decide both. In the
viewer, **Cast to Looking Glass** rebuilds the floor with the scene.

Skeletons drawn as lines cast almost no shadow. Add `--tubes` to a floored
circuit view.

Shadow mapping adds a render pass for each frame, so the interactive viewer
can respond more slowly with `--floor`. The stills and quilts are not
affected in practice: a floored 4K still takes about 4 to 6 seconds.

## Tuning constants

The visual constants live at the top of `src/connectomekg/scene.py`. Sizes
are in world units, where the brain is about 8 units wide.

| constant | value | controls |
|---|---|---|
| `BACKGROUND` | `#5A5D62` | scene background |
| `_CONTEXT_RADIUS` | 0.005 | context sphere radius, circuit view |
| `_FLOW_CONTEXT_RADIUS` | 0.014 | context sphere radius, flow view |
| `_FLOW_CONTEXT_STRIDE` | 10 | flow view draws every Nth neuron |
| `_CONTEXT_LIGHTEN` | 0.35 | how far context colours move toward white |
| `_SOMA_RADIUS`, `_FALLBACK_RADIUS` | 0.05, 0.09 | soma and missing-skeleton spheres |
| `_TUBE_RADIUS` | 0.01 | skeleton tube radius with `--tubes` |
| `_NEUROPIL_MAX_RADIUS` | 0.22 | largest neuropil sphere |
| `_FLOW_MAX_RADIUS`, `_FLOW_MIN_RADIUS` | 0.08, 0.004 | flow tube radius range |
| `_FLOW_BOW` | 0.15 | tube bow, as a fraction of the distance between endpoints |
| `_CONTEXT_DIM` | 0.85 | darkening of idle neuropil spheres |
| `FLOOR_ELEVATION` | 25 | default `--elevation` with `--floor`, degrees |
| `_FLOOR_DROP`, `_FLOOR_SIZE` | 0.15, 120 | floor distance below the scene, and its side length |
| `_KEY_LIGHT_HEIGHT`, `_KEY_LIGHT_CONE` | 20, 75 | key light height above the scene, and its cone in degrees |
| `_KEY_LIGHT_INTENSITY`, `_FILL_LIGHT_INTENSITY` | 0.9, 0.35 | key light and headlight intensity |
| `_SHADOW_MAP_RESOLUTION` | 8192 | shadow map size, pixels per side |

Bounds on user input live in `connectomekg.validation` and apply equally to
the CLI and the Python API:

| bound | value |
|---|---|
| `MAX_SCENE_NEURONS` | 500 neurons in a circuit |
| `MAX_SKELETON_STEP` | 50 |
| `MAX_FLOW_PAIRS` | 500 tubes in a flow |

## Known limits

- **No neuropil geometry.** Regions show only as the density of the context
  cloud and as flow centroids. Drawing neuropil surfaces needs a mesh source
  that the Codex download does not include.
- **Marked points are not somas.** The cloud and the flow centroids use
  marked points. Only the circuit view reads real somas, from skeletons.
- **Large circuits are refused, not sampled.** Narrow a SPEC that resolves
  to more than 500 neurons.

## Use the scene from Python

`build_brain_scene`, `aim_camera` and `add_floor` are the steps
`connkg quilt` runs, in the same order:

```python
import pyvista as pv
from quiltwright import QUILT_PRESETS, render_quilt, save_quilt

from connectomekg import ConnectomeKG
from connectomekg.scene import FLOOR_ELEVATION, add_floor, aim_camera, build_brain_scene

spec = QUILT_PRESETS["16-landscape"].still(height=2160)
kg = ConnectomeKG(".")  # the directory that holds .connectomekg/
plotter = pv.Plotter(
    off_screen=True, window_size=(round(spec.tile_height * spec.aspect), spec.tile_height)
)
info = build_brain_scene(plotter, kg, view="flow", specs=["LC4"], progress=print)
print(info.title, info.n_flow_pairs, info.n_flow_total)

aim_camera(plotter, info.points, fov=14.0, elevation=FLOOR_ELEVATION)
add_floor(plotter)
save_quilt(render_quilt(plotter, spec, fov=None), "renders/stills/flow_lc4", spec)
plotter.close()
kg.close()
```

To compute flow numbers without drawing anything, call
`connectomekg.scene.neuropil_flow(kg.store)`. See the
[scene API reference](api/scene.md).
