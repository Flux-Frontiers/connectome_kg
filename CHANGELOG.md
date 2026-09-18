# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
