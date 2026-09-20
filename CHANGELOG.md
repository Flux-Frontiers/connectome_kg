# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Answers in the 3-D viewer.** `connkg viz3d "path:LPLC2>DNp01"` opens on the
  answer rather than on a cell type, drawn hop-coloured; so does typing the
  same thing into the viewer's Show box, which means a question can be
  re-asked and re-seen without restarting. The forms are `path:FROM>TO`,
  `cone:SPEC`, `cone:SPEC>HOPS` downstream and `cone:SPEC<HOPS` upstream, the
  arrow pointing the way the signal travels. They follow the `label:` prefix
  the spec grammar already had, so anywhere a spec is taken an answer can be
  too.

  The new `connectomekg.answers` holds the grammar and the group-building, and
  `connkg path --render` and `connkg cone --render` now go through it as well
  rather than each building their own groups. An answer that reaches nothing,
  or that holds more neurons than one scene may draw, is refused with the
  reason and leaves the view as it was -- `cone:DNp01<1` is 663 neurons on
  FAFB v783 and says so.


### Changed

- **Every 3-D scene is lit by a three-point rig**, replacing PyVista's five
  default lights. The default's flaw is not that its lights follow the camera
  but that all five sit on the view axis, so every surface is lit head-on and
  a tube reads as a flat ribbon. Offsetting the key up and to the left models
  the form while still facing the subject. Measured on the LPLC2-DNp01 scene,
  the new rig is brighter and more saturated than the default it replaces
  (luminance 93.8 against 92.0, saturation 17.5 against 16.3). Fixing the
  lights in the brain's frame instead was tried and measured *worse* -- 86.0
  and 11.7, because a brain seen front-on turns its lit side away from a key
  placed in world coordinates -- and the numbers are recorded in the code so
  nobody repeats it.
- **`--floor` no longer unlights the scene.** It replaced the lighting with a
  single narrow spotlight, which threw a shadow and left everything the cone
  missed dark: the neuropil surfaces at 10 % opacity and the whole-brain cloud
  both disappeared, turning a circuit render into a lone neuron in the void.
  The shadow-casting light now sits on top of the three-point rig rather than
  replacing it, so a floored scene keeps its anatomy. The shadow itself is
  sharper and darker (cone 75 to 42 degrees, since a penumbra widens with the
  light's angular size), and the floor is no longer the exact colour of the
  background, which had left it with no horizon and no lit pool for a shadow
  to fall on.
- **The documentation images are drawn as tubes and stand on the ground.** A
  line has no surface, so no lighting can shade it and a line-drawn circuit
  reads flat however the scene is lit. `--tubes` stays opt-in on the CLI.

### Added

- **`connkg path --render` and `connkg cone --render` draw the answer.** The
  query already knows which neurons answer the question and in what order; the
  flag draws them. A path becomes its hops as traced skeletons, one colour per
  hop running dark to bright along the route and labelled with the synapses
  entering it; a cone becomes its shells, dark at the seed and bright outward.
  Tubes on a floor, written as a 4K still under `renders/stills/`. Needs the
  viz3d extra, and says so if it is missing.

  An answer render draws no neuropil surfaces and no whole-brain cloud, which
  is not about speed: the camera frames the scene's bounds, so leaving the
  brain in makes the brain the thing framed and the answer ends up a quarter
  of the frame wide. A cone over `MAX_SCENE_NEURONS` is refused with the count
  and the remedy, after its text answer has printed -- the query succeeded,
  only the drawing of it did not.

- **`connectomekg.scene.NeuronGroup`**, so a caller can say which neurons
  belong together and in what colour, rather than having cell type decide. The
  circuit view groups by type and colours by name, which is right for "show me
  LC4" and wrong for "show me the answer": a path's hops are an order, and the
  neurons in one hop rarely share a type. With `connectomekg.colors.hop_color`,
  a viridis-style ramp that rises monotonically in luminance so the order
  survives colour blindness, this is what `--render` draws with.


### Fixed

- **`connkg viz3d` could not open at all.** It died with `ZeroDivisionError:
  division by zero` before showing a window, on every invocation, and 0.4.0
  shipped that way. `BrainSceneWindow` aimed the camera during construction,
  but `quiltwright.frame_and_focus` divides by the render window's height to
  get the horizontal half-angle, and a `QtInteractor` reports `(0, 0)` until it
  is shown -- which `launch()` only did afterwards. The window now sizes its
  render window before composing, and `--width`/`--height` reach it rather than
  being applied after the fact. The viewer had one test, an import, which is
  why nothing caught this; it now has six that build the window offscreen, and
  five of them fail without the fix.

### Added

- **Effective connectivity: `connkg influence`, and an `influence` MCP tool.**
  How much one population drives another, hop by hop and signed, as a share of
  the receiving neuron's input synapses averaged over those neurons -- so 0.15
  reads as "the average target gets 15 % of its input from the source". A
  negative value is net inhibition, and two routes of opposite sign cancel,
  which is what this answers that counting paths does not. Without `--to` it
  ranks the cell types a population drives most.

  It follows the convention `connkg path` already uses, from
  connectome-interpreter, and is anchored to an identity that holds by
  construction: unsigned, at hop 1, the value *is* the source's share of the
  target's input synapses. On FAFB v783, LC4 onto DNp01 measures +0.1482 both
  ways. Signed, the same pair reads +0.1469, the difference being one LC4
  neuron of 104 whose transmitter is unresolved and which therefore carries
  nothing.

  Computed by propagating a sparse vector rather than raising the matrix to a
  power: the matrix is 139,255 square, so one dense power would be 1.5e10
  entries, while three hops over the 3.7 M edges take 0.02 s.

- **Picking in the 3-D viewer.** Point at a neuron in `connkg viz3d` and press
  P: a panel names it, gives the description the graph already stores for it,
  and lists its strongest partner types in each direction. Picking is bound to
  the key rather than to a left click, because a left click is where VTK begins
  a rotation and picking there would re-answer the question on every orbit.

  The toolbar's **Show** box takes the same specs the command does and redraws
  in place, so exploring no longer means restarting. It refuses a spec that
  matches nothing, or one over `MAX_SCENE_NEURONS`, and leaves the scene as it
  was -- including when only one spec of several is bad, since drawing the rest
  would look like a scene that contained them all.

  A whole cell type shares one actor, so VTK can report which type was hit but
  never which neuron -- and that is the question a click asks. The new
  `connectomekg.picking` carries identity beside the geometry instead: every
  drawn point with the neuron that owns it, resolved by nearest-point lookup
  (1.02 M points and 12.3 MB for a 212-neuron scene, 4.4 microseconds a pick).
  That makes it indifferent to `--tubes`, to the simplification stride, and to
  whether VTK propagates point data through `tube()` and `glyph()`. A pick more
  than 25 microns from any drawn neuron is reported as a miss rather than as
  whichever neuron happened to be nearest.


### Fixed

- **`docs/scripts/render_images.py` runs again.** It opened `ConnectomeKG(".")`,
  which has looked for `./.connectomekg/graph.sqlite` since 0.3.0 moved each
  dataset into `connectomes/<dataset>/`, so it failed on its first line and
  nothing had regenerated the documentation images since 2026-09-17. They
  therefore still showed the whole-brain cloud of marked points with no
  neuropil surfaces, two days after 0.4.0 added both.

### Added

- **A hero render, `docs/images/anatomy_lplc2_dnp01.png`**, on the README and
  the documentation site: the escape circuit, LPLC2 to DNp01, drawn inside the
  brain's neuropil surfaces with one dot per neuron at its cell body. The four
  existing images were regenerated and now show the surfaces and the somas too.


## [0.4.0] - 2026-09-19

### Added

- **A skeleton cache and a soma for every neuron.** `connkg skeletons
  --data-dir fafb_v783` reads the 31 GB SWC download once and writes two
  things. `.connectomekg/skeletons/` holds every neuron's skeleton simplified
  at `--step` (4 by default, the circuit view's own default) -- 212,351,918
  points in 2.5 GB on FAFB v783 -- and the circuit view now reads it in place
  of the download: 104 LC4 neurons render in 1.0 s rather than 1.7 s, with
  the same geometry, and no download needed at all. Each neuron node also
  gains `soma_x`, `soma_y`, `soma_z` and `has_soma`, so the graph answers for
  the cell body rather than only for FlyWire's marked point; `--no-somas`
  writes the cache without touching the graph. The new
  `connectomekg.skeleton_cache` holds both halves.
- **`connkg skeletons -j N` reads in parallel.** Parsing SWC is pure Python
  and holds the GIL, so the pass pegged one core and left the rest idle. `-j`
  splits the root ids into contiguous ranges, one worker and one Parquet
  shard each, after `proteusPy`'s `DisulfideExtractor_mp`. On FAFB v783 and
  an 18-core laptop: **19m 30s at `-j 1`, 2m 39s at `-j 12`, a 7.4x
  speed-up**, for a cache verified identical -- same point count, same
  134,675 somas, same SHA-256 over a sampled 199 neurons' coordinates,
  parents and labels, and a bit-identical soma back-fill across all 139,255
  neuron nodes. Shards hold disjoint root-id ranges, so a filtered read still
  skips the ones that cannot match, and `-j 1` starts no pool at all.
- **`coverage.soma` in the graph snapshot.** The soma back-fill writes
  metadata and never a node or an edge, so every metric a snapshot recorded
  was identical with or without it -- a 0.4 snapshot would have been
  indistinguishable from 0.3.2 on the one thing 0.4 adds. The new metric reads
  0.967 on FAFB v783 (134,675 of 139,255) and 0 on a graph that has not had
  `connkg skeletons` run over it.
- **A run report for `connkg skeletons`**, in `reports/skeletons_<timestamp>.md`,
  the same per-run provenance record `connkg build` has written all along:
  versions and git commit, options, host, the download read (file count and
  total size; it has no recorded checksums to verify against), the cache
  written, how many neuron nodes gained a soma, timings and peak memory. A
  failed or interrupted pass writes one too, marked FAILED. The pass earns one
  for a reason a build does not: it writes somas into an already-built
  `graph.sqlite`, so the report is the only record of which download they came
  from and at which step, and a snapshot taken before it no longer describes
  the graph.
- **A synapse-graph cache.** `connkg path` and `connkg cone` write the loaded
  neuron-level matrix to `.connectomekg/synapse_graph.npz` (14 MB on v783)
  and reuse it, turning an 8-second load of 3.7 M edges into under one:
  `connkg path --from LPLC2 --to DNp01` goes from 8.8 s to 1.8 s. The cache
  is keyed on the edge table's shape, the graph file and `min_syn`, so an
  edited or rebuilt graph is not answered from a stale one. Like the mesh and
  skeleton caches it is derived data, gitignored, and safe to delete.
- **Neuroglancer links.** `connkg link SPEC [SPEC...]` prints a URL that opens
  the specs' neurons as FlyWire meshes in the public Neuroglancer, with no
  login, each spec in its own Okabe-Ito colour inside a translucent brain
  outline. The same link comes from the MCP tool `neuroglancer_link` and from
  `ConnectomeKG.neuroglancer_link()`. The URL is the only thing on stdout,
  so `connkg link LC4 | pbcopy` works. A link selects root ids on the public
  flat v783 segmentation (`gs://flywire_v141_m783`); datasets without a
  public segmentation get an error that says so. Each spec shows up to
  `--limit` neurons (default 200, at most 500) and reports its full count.
- **Neuropil meshes in the 3-D views.** `connkg meshes` fetches the 78 FAFB
  v783 neuropil surfaces from FlyWire's public bucket (no sign-in, about
  1 MB, 11 seconds) into `.connectomekg/neuropil_meshes.npz` beside the
  graph. `connkg quilt`, `connkg viz3d` and its Cast button then draw them:
  pale neutral shells in the circuit view, region-tinted in the flow view.
  These are the volumes FlyWire assigned synapses to neuropils with, so they
  enclose what the graph's `IN_NEUROPIL` edges count. The source numbers its
  meshes without names; the new `connectomekg.neuropil_meshes` names them
  with a table matched vertex for vertex against fafbseg's named copy (78 of
  78). `UNASGD` has no mesh.
- `--neuropils/--no-neuropils` and `--cloud/--no-cloud` on `connkg quilt` and
  `connkg viz3d`, and matching `neuropils=` and `cloud=` arguments on
  `build_brain_scene`.

### Changed

- **An interrupted `connkg skeletons` pass removes its own partial cache.** It
  builds in `skeletons.part/` and moves it into place at the end; a Ctrl-C part
  way through a long read used to strand hundreds of megabytes there, and a
  failure moving it into place did too. Both now clean up, the pool is
  terminated rather than joined so an interrupt actually interrupts, and
  `*.part` under `.connectomekg/` is gitignored for the case a process is
  killed outright.
- **A run report's peak memory counts the worker processes**, not just the
  parent. A parallel pass reported 230 MB for a run whose real footprint was
  several gigabytes.
- **The context cloud draws somas where the graph has them.** Each dot sits
  at the neuron's `soma_x`/`soma_y`/`soma_z` once `connkg skeletons` has
  back-filled one, and at its marked point otherwise, so a graph without the
  back-fill draws exactly the cloud it always did. The scene title says which
  (`somas=N` against `context=N`), and `build_brain_scene` reports it as
  `SceneInfo.n_context_somas`. `connectomekg.scene.context_points` returns
  that count as a fourth value, which is a breaking change to that function.
- **Drawing the neuropil surfaces turns the context cloud off**, since the
  surfaces show the brain's outline more plainly than 139,255 dots; `--cloud`
  (or `cloud=True`) draws both. A graph with no mesh cache is unaffected, so
  this changes nothing until `connkg meshes` has run.
- **The documented FAFB v783 build now includes the vector index.** The
  README and `docs/DOWNLOAD.md` drop `--no-index` from the reference build,
  so a new install has `connkg query` and the `query_connectome` and
  `pack_connectome` MCP tools. Measured on v783: 16,861 vectors in 25
  seconds and 29 MB (Apple M5 Max), not the "few minutes" the docs said.
- `connkg build` without `--no-index` checks for the `semantic` extra before
  it starts and stops with a usage error naming the missing modules, instead
  of failing at the index step after the graph write.
- `connkg build --no-index` warns when it leaves a vector index from an
  earlier build in place, since that index was not rebuilt and may not match
  the new graph. The warning is recorded in the build report.

 `connkg link SPEC [SPEC...]` prints a URL that opens
  the specs' neurons as FlyWire meshes in the public Neuroglancer, with no
  login, each spec in its own Okabe-Ito colour inside a translucent brain
  outline. The same link comes from the MCP tool `neuroglancer_link` and from
  `ConnectomeKG.neuroglancer_link()`. The URL is the only thing on stdout,
  so `connkg link LC4 | pbcopy` works. A link selects root ids on the public
  flat v783 segmentation (`gs://flywire_v141_m783`); datasets without a
  public segmentation get an error that says so. Each spec shows up to
  `--limit` neurons (default 200, at most 500) and reports its full count.

## [0.3.2] - 2026-09-19

### Changed

- Raised the `mcp` floor from 1.0.0 to 1.3.0, the first release whose
  `FastMCP` accepts the `lifespan=` and `instructions=` arguments
  `connkg-mcp` passes. Earlier versions have no `mcp.server.fastmcp` at all.
- Raised the `numpy` floor from 1.24.0 to 1.26.0, the first release that
  installs on Python 3.12.
- Relocked `pycode-kg` to 0.27.1 (maintainer `kg` group; floor unchanged).
- README status line: the KGRAG adapter shipped in kg-rag 0.16.0
  (`pip install "kg-rag[connectome]"`), no longer "its next release".

## [0.3.1] - 2026-09-18

### Added

- **Published to PyPI** as `connectome-kg`: `pip install "connectome-kg[semantic]"`.
  The release workflow gains a `publish` job that uploads the wheel and sdist
  the release job built, byte for byte, using trusted publishing (OIDC) under
  the `pypi` environment, so no API token is stored. kg-rag's connectome
  adapter needs a versioned dependency, which is why this is happening now.
- `Documentation`, `Issues` and `Changelog` project URLs.

### Fixed

- **README links work on PyPI.** The seven relative links (to
  `docs/DOWNLOAD.md`, `docs/rendering.md`, `CHANGELOG.md` and `LICENSE`)
  now point at GitHub, since PyPI serves the README without the files beside it.

## [0.3.0] - 2026-09-18

### Changed

- **One graph per connectome.** Each dataset now lives in its own directory,
  `<root>/connectomes/<dataset_id>/.connectomekg/`, holding its own graph,
  vector index and snapshot history. This follows GutenbergKG's
  one-graph-per-book layout. A second release (another FAFB version, MANC,
  hemibrain) no longer overwrites the first, and KGRAG's registry scan finds
  each dataset as a separate KG. New module `connectomekg.datasets`
  (`scan_datasets`, `resolve_dataset`, `dataset_dir`).
- **`--dataset ID` replaces `--dataset-id`**, and moves from individual
  commands to the group: `connkg --root . --dataset fafb783 build ...`.
  `connkg build` without it writes to `fafb783`, or to `synthetic` with
  `--source synthetic`. Every other command uses the only built dataset, and
  stops with a list when there are several. Ids are restricted to lowercase
  letters, digits, `_`, `.` and `-`, so an id can never name a path outside
  `connectomes/`.
- **`connkg-mcp --dataset ID`** picks the dataset the server serves, with the
  same default. Serve two datasets as two server entries.
- The tracked FAFB v783 snapshots moved to
  `connectomes/fafb783/.connectomekg/snapshots/`.

### Added

- **`connkg datasets`** lists the datasets built under `--root`, with each
  graph's size and dataset name.

### Migration

A graph built before this change is in `<root>/.connectomekg/`. Commands
that find it say so and print the move:

```bash
mkdir -p connectomes/fafb783/.connectomekg
mv .connectomekg/*.sqlite* connectomes/fafb783/.connectomekg/
```

A KGRAG registry entry that points at the old path needs registering again.

### Fixed

- **A built store can be queried without its source data.** `connkg query`,
  and anything else that opens an existing graph -- kg-rag's federation
  adapter among them -- failed with `source='codex' needs data_dir` unless
  the 34 GB Codex release was on hand. `KGModule.index` builds an extractor
  only to ask which node kinds are embedded, and `ConnectomeExtractor` loaded
  its tables eagerly to do it, so every semantic query read the whole release
  first, or failed without it. The extractor now loads its tables on first
  use, and `make_extractor()` passes the loader rather than calling it. The
  existing semantic-query test never saw this, because its module is built
  from in-memory tables; the new regression test reopens a built store the
  way a user does.

## [0.2.1] - 2026-09-17

### Changed

- **`kgmodule-utils` floor raised to `>=0.22.0`** (was `>=0.21.0`), across the
  base dependency and the `semantic`, `viz` and `viz3d` extras. 0.22.0 makes
  the Cast button sweep quiltwright's standard 35-degree view cone instead of
  the preset's full cone, which for the 16" landscape is 50 -- wider than
  reliably fuses, so hard edges ghosted where a quilt rendered by `connkg`
  itself held. Nothing in this repo changes; the fix arrives through
  `kg_utils.viz3d.qt.cast_scene_to_looking_glass`, which `connectomekg.viz3d`
  calls.

  The `viz3d` extra already declared `quiltwright>=0.14.1`, which is what
  0.22.0 requires transitively, so no pin moves here.

## [0.2.0] - 2026-09-17

### Added

- **A key for the rendered images, and a script that regenerates them.**
  `docs/rendering.md` gains "Reading the images": swatches for the
  background, the context cloud's super classes and signs, what each shape,
  size, thickness and curve means in the circuit and flow views, a region
  colour table, and a collapsible table of every labelled neuropil. The
  swatches are generated from `connectomekg.colors` and show the colours as
  drawn. `docs/scripts/render_images.py` redraws the four doc images through
  the same steps as `connkg quilt --still` and labels neuropils in the flow
  images. `connectomekg.neuropils` gains `REGION_NAMES`, `NEUROPIL_REGION`
  and `neuropil_region`, grouping every neuropil into the 13 regions of the
  nomenclature FlyWire follows (Ito et al. 2014).

- **`--floor`, `--elevation` and `--still` for the 3-D views.** `--floor`
  (on `connkg quilt` and `connkg viz3d`) stands the scene over a floor in
  the background grey, lit by a shadow-casting spotlight from above, with an
  8192 px shadow map. The new `scene.add_floor` does it after framing, so the
  floor never decides the framing, and the viewer's Cast rebuilds it.
  `--elevation` tilts the camera to look down (default 25 degrees with a
  floor, which is invisible from level). `connkg quilt --still` renders the
  quilt's centre view as one flat image at the preset's aspect, 3840 x 2160
  for `16-landscape`, into `renders/stills/`. The rendering guide gains
  "Camera and framing" and "Floor and shadows" sections.

- **Documentation site and a rendering guide.** `mkdocs.yml`, a `docs`
  Poetry group (mkdocs-material, mkdocstrings) and a Pages workflow, set up
  the same way as quiltwright's. `docs/rendering.md` explains both 3-D views:
  the world frame, the context cloud, skeleton simplification, how flow is
  defined, with a worked example and the FAFB v783 numbers, every tuning
  constant, and the known limits. The API reference for `connectomekg.scene`
  and `connectomekg.skeletons` is generated from their docstrings.
  `poetry run mkdocs build --strict` builds it.

- **`--view flow` on `connkg quilt` and `connkg viz3d`: neuropil flow in 3-D.**
  Neuropils are drawn as spheres at the synapse-weighted centroid of their
  neurons' marked points, sized by synapse count. The `--top` strongest
  directed pairs (default 100, capped at `MAX_FLOW_PAIRS` = 500) are drawn
  as tubes, coloured by source neuropil and bowed to one side so A -> B and
  B -> A stay apart. Flow is carried by neurons, not synapses. Flow A -> B is
  each neuron's output synapses in B, split by the share of its input
  synapses in A, summed over neurons, with A = B left out. The new
  `connectomekg.scene.neuropil_flow` computes it from `IN_NEUROPIL` evidence
  alone, about 1.5 s for all of FAFB v783 (5,786 pairs across 79 neuropils),
  so nothing new is stored at build time. SPEC(s) become optional in this
  view and limit the sum to their neurons. The context cloud is thinned to
  every 10th neuron so it does not hide the neuropils.

- **`connkg quilt` and `connkg viz3d`, real-geometry 3-D views of a connectome**
  (the new `viz3d` extra). Unlike the fleet's other viz3d consumers, this
  graph already has space: view A is every neuron's marked point as a dim
  whole-brain context cloud, coloured by super class or transmitter sign; view
  B is a spec's circuit -- neurons resolved via `ConnectomeKG.neurons_of`,
  drawn from their traced skeletons (read from `fafb_v783/sk_lod1_783_healed/`
  by the new `connectomekg.skeletons`, NumPy only) at full brightness, one
  line mesh per cell type plus a soma sphere; a neuron with no skeleton file
  falls back to a larger sphere at its marked point, counted separately.
  `connectomekg.scene.build_brain_scene` composes both views into a
  caller-supplied `pv.Plotter`, framed with `kg_utils.viz3d.frame_tree` and
  coloured deterministically per cell type via `seed_from_key`; it is Qt-free,
  so `connkg quilt` (headless, `quiltwright.render_quilt`/`save_quilt`,
  printing `depth_report` every run, optional `--cast`) and `connkg viz3d`
  (an interactive PyQt5/pyvistaqt viewer with one Cast-to-Looking-Glass
  toolbar action) are two callers of one function. A circuit is capped at
  `MAX_SCENE_NEURONS` (500) neurons; `--skeleton-step` simplifies a skeleton's
  point count while preserving its branch topology, bounded by
  `MAX_SKELETON_STEP` (50). `renders/` follows quiltwright's own layout
  (`stills/`, `quilts/`, `views/`, `reports/`) rather than a flat directory.

- **`connkg viz`, 2-D views of a cell type's local circuit** (the new `viz`
  extra). `--view network` draws the type with its strongest input and output
  partner types through the shared `kg_utils.viz` renderer: nodes coloured by
  super class, edges labelled with synapse count and transmitter
  (`28,530 ACH`) and coloured by sign, and partner-to-partner edges drawn only
  when at least as strong as the weakest edge to the centre. `--view partners`
  draws the same partners as a plotly diverging bar chart. Both write one
  self-contained HTML file. `ConnectomeKG.cell_type_node` resolves a type by
  exact name and, when there is none, names the types containing it.

- **`connkg-mcp`, an MCP server for the graph.** Fourteen tools over stdio or
  SSE: `graph_stats`, `find_nodes`, `get_node`, `node_edges`, `neurons_of`,
  `type_partners`, `strongest_path`, `cone`, `query_connectome`,
  `pack_connectome`, `analyze_connectome` and `snapshot_list/show/diff`. It
  follows the fleet MCP standards as genealogy_kg and swift_kg implement them:
  a `FastMCP` `lifespan` hook closes the graph on shutdown, and every argument
  is validated in `ConnectomeKG` itself (new `validation.py`), so the CLI, the
  server and the Python API share one set of bounds. Out-of-range values are
  rejected with a message naming the range, never clamped; a `label:` spec's
  regex is length-capped and must compile before it runs over the labels; and
  specs are resolved before the synapse graph loads, so a bad argument costs
  nothing. `query`/`pack` without a vector index now say so instead of failing
  inside the SDK. Tests drive the real server through `mcp.shared.memory`.
  `mcp>=1.0.0,<2` is a direct dependency.

- **A provenance report for every build.** `connkg build` writes
  `reports/build_<timestamp>.md`, following gutenberg_kg's ingest reports:
  package versions and git commit, host and Python, the options, every input
  file's SHA-256 against the manifest, time per extraction stage, the counts
  written, database size and peak resident memory. A failed build still
  writes one, marked FAILED. Reports are gitignored; `git add -f` the ones
  worth keeping.
- **`connkg snapshot save/list/show/diff/prune`.** Snapshots of the built
  graph on the shared `kg_utils` manager, following the fleet snapshot
  standard: the subclass sets `package_name` and adds the dataset figures,
  per-layer neuron coverage and hub neurons, and overrides nothing else.
  `snapshot save [OPTIONS] VERSION` keys on the release tag, or on a UTC
  timestamp when it is omitted, never on the git tree hash, which is recorded
  only as provenance. The subject is `corpus:<dataset id>` (`corpus:fafb783`),
  since the graph measures a connectome release rather than this package's
  code; the repo's release skill spells that out for the release snapshot.
  They live in `.connectomekg/snapshots/`, now tracked while the rest of
  `.connectomekg/` stays ignored.

- **Annotation layers from the optional Codex files.** The reader now joins
  `cell_stats`, `visual_neuron_types`, `column_assignment`,
  `connectivity_tags` and `processed_labels` when present, and keeps the
  per-transmitter prediction scores it used to discard. The graph gains
  sub-class taxa, `nerve` nodes (`VIA_NERVE`), visual subsystem and family
  taxa that contain their cell types, retinotopic `column` nodes keyed by
  hemisphere and id (`IN_COLUMN`), `connectivity_tag` nodes for the four
  selective tags (`TAGGED`), and Fly Anatomy Ontology `ontology_term` nodes
  mapped from cell types (`MAPS_TO`), with the `Fbbt_`/`FBbt_` spelling
  normalised. A type maps to a term only when at least half as many of its
  neurons carry it as carry its best-supported term: on v783 that drops 247
  of 552 raw mappings, such as T4b to the T4a, T4c and T4d terms on 40, 6
  and 6 stray labels against 1,426 for its own. Neurons carry flow, nerve, transmitter scores, cable length,
  area, volume, column, tags and refined labels in metadata; cell type
  docstrings mention flow, visual family and ontology ids. `analyze` reports
  coverage for each layer. The synthetic fixture writes every new file.

- **CI and release workflows from doc_kg.** CI adds a blocking `ty` type
  check and an installed-wheel job that loads the `connkg` entry point, builds
  and path-queries a synthetic connectome, and imports every packaged
  submodule, all from a clean core-only install. A `v*` tag builds the
  package, creates the GitHub Release (which Zenodo archives) and publishes
  to PyPI through trusted publishing.

- **`connkg build` reports progress.** A real FAFB v783 build ran for three
  minutes with no output at all, which reads as a hang. The extractor takes an
  optional `progress` callback, reports each stage and a count every 250,000
  synaptic pairs, and says when it hands over to the SQLite write. The CLI
  prints these on stderr; library use stays silent by default.

- **`python -m connectomekg`** runs the CLI from a clone with nothing
  installed. The `connectome-kg` script only exists after an install, so the
  first thing anyone tries returned "command not found".
- **`connectome-kg files`**, and the portal labels in the manifest. The Codex
  download page lists display names, not file names: `neurons.csv.gz` appears
  as "Neurotransmitter Type Predictions" and `connections_princeton.csv.gz` as
  "Connections (Filtered)", which makes a download impossible to match against
  a manifest by eye. Every manifest entry now carries the portal's own label
  and size, `verify` prints the mapping when a required file is missing, and
  `FAFB_783_UNUSED` records the assets the build deliberately skips with the
  reason for each.

### Changed

- **Tagged releases no longer publish to PyPI.** The Release workflow builds
  the wheel and sdist and attaches them to the GitHub Release, which is what
  Zenodo archives; its PyPI publish job is removed until the KGRAG adapter
  gives the package a consumer that needs it on an index.

- **`quiltwright>=0.14.1` in the `viz3d` extra** (was `>=0.10.0`).
  `scene.aim_camera` takes `spec=` and passes it to quiltwright's
  `frame_and_focus`, which from 0.14.1 sizes the window to the aspect
  `render_quilt` captures views at. That replaces the manual window sizing in
  `connkg quilt` and `docs/scripts/render_images.py`; framing is unchanged,
  and the doc images re-render byte-identical.

- **Colour-blind-safe colours in the 3-D views, with no pastels.** Neuropil
  spheres and flow tubes are coloured by brain region (`scene.region_color`)
  instead of a 15-colour hash of the neuropil name, which had given unrelated
  neuropils the same colour. The regions use the 8 saturated Okabe-Ito colours
  (`colors.REGION_COLOR`); neighbouring regions share a colour where 13 do not
  fit. Cell-type colours are the 7 non-black Okabe-Ito colours. The flow
  view's context cloud is one neutral grey, so colour there means only region,
  and `--color-by` applies to the circuit view alone. The context cloud is
  muted toward the grey background instead of lightened toward white, so a
  skeleton that shares a hue with the dots around it still stands out.
  Neuropil spheres and tubes are lit more evenly (`_FLOW_AMBIENT`), because
  shading turned the yellow region colour orange.

- **`connkg quilt` frames with quiltwright's `frame_and_focus` and sweeps a
  35-degree view cone by default.** The new `scene.aim_camera` points the
  camera with `frame_tree`, applies `--elevation`, then fits the scene at
  that final view with the focal plane at the harmonic mean of near and far
  depth; `depth_report` and `render_quilt` both take `fov=None` after it,
  so neither re-frames. The render window now matches the aspect quiltwright
  captures views at (16:9) rather than the 4:3 quilt tile, which had put the
  focal plane at 30.5 units instead of 23.4. The view cone was the preset's
  full 50 degrees; `--view-cone` (default 35) matches quiltwright's own CLI.
  A cast now goes through `save_and_cast_quilt`, so a missing Bridge never
  loses the quilt.

- **3-D scenes render on a muted grey background, and the context cloud is
  drawn as sphere glyphs sized in world units.** The cloud used to be
  pixel-sized points on white. It disappeared in a HiDPI viewer window and
  in quilt tiles. Its colours are now lightened 35% toward white instead of
  darkened.

- **The CLI is Click, and the command is `connkg`.** `connectome-kg` was long
  to type and argparse was the odd one out in the fleet. The commands and
  their options are unchanged, `--root` still comes before the command, and
  numeric options are now range-checked at parse time (`--k` 1-100, `--hop`
  and `--hops` 0-5). Commands close the graph through `open_kg()` and a `with`
  block instead of leaving the SQLite handle to process exit.

- **Checksum differences are reported as drift, not failure.** Codex states
  that its downloads are synchronised with the live database and may differ
  from the October 2024 published snapshot, so a digest that does not match
  the August 2026 download this manifest fingerprints is expected rather than
  corrupt. `ManifestReport.ok` now depends only on the required files being
  present, drift is listed separately with the counts to check instead, and
  `STATIC_ARCHIVES` records the no-login Zenodo and GitHub snapshots to use
  when a build has to be reproducible.

- **The Codex reader no longer hard-codes the connections file name.** Codex
  has shipped that table as both `connections_princeton.csv.gz` and
  `connections.csv.gz`, so a hard-coded name made a perfectly good download
  unreadable. `find_connections_file()` picks whichever variant is present,
  preferring the thresholded Princeton table, `--connections-file` overrides
  it, and the reader resolves column aliases (`pre_root_id` / `pre_pt_root_id`
  / `pre`, `syn_count` / `weight`, and so on) reporting exactly which column
  it could not find. `verify` accepts any connections variant and names the
  one it found.

### Fixed

- **Importing `connectomekg.cli.__main__` ran the CLI.** It called `cli()`
  with no `__main__` guard, so anything that walked the package, like the new
  wheel job, printed help and exited. `python -m connectomekg.cli` still works.

- **`ty check src/` reported 17 errors.** pandas types `groupby` keys as
  `Hashable`; the extractor and synthetic reader now convert them with `str()`,
  which they already were at runtime.

- **Current Codex exports failed to load.** `classification.csv.gz` no longer
  carries a `cell_type` column, and the reader demanded it, so every build
  from a fresh download stopped with "Usecols do not match columns". The
  reader now reads the columns a download has and takes cell types from
  `consolidated_cell_types.csv.gz`. The synthetic fixture wrote the old
  schema, which is why the suite never noticed; it now writes the current one.

- **The synthetic fixture crashed below 361 neurons.** The planted circuits
  claim a fixed number of neurons from each super class, so a small
  `n_neurons` ran the visual projection population out and pandas raised an
  opaque length error. `synthetic_tables()` now refuses a too-small size and
  names the minimum, which `min_neurons()` derives from the plant table
  rather than hard-coding.

## [0.1.0] - 2026-09-16

### Added

- Initial import from the private KGRAG fleet prototype: normalised
  connectome tables, the FlyWire FAFB v783 release manifest with checksums,
  the Codex reader, a seeded synthetic connectome with planted feeding,
  escape and grooming circuits, the extractor emitting neurons, cell types,
  neuropils, hemilineages, labels and taxa with signed synapse edges,
  `ConnectomeKG(KGModule)` with strongest-path and cone queries and a
  Markdown analysis, and the `connectome-kg` CLI.
