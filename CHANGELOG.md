# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **BANC v888 and MCNS v1.0 build alongside FAFB v783.** Codex exports both
  as one consolidated neuron-attributes table, and `read_codex` now
  recognizes that layout by its header (`is_attribute_export`) and maps its
  display-name columns; no classification file is needed. New dataset
  records `BANC_888` (`banc888`) and `MCNS_1` (`mcns1`), both CC-BY-4.0, and
  `connkg verify` checks the two-file export against its own manifest.
  Super classes are mapped to FAFB's spelling (`ol_intrinsic` and
  `optic_lobe_intrinsic` to `optic`, the nerve cord's to
  `ventral_nerve_cord`); community labels become one label each, less MCNS's
  `statusLabel` and `mancBodyid`. See `docs/DOWNLOAD.md`.
- **Soma positions for BANC and MCNS, so their 3-D views draw something.**
  Codex exports no coordinates for either release, which left every neuron at
  a null position: no cell-body cloud, no circuit view, and no flow view
  either, since neuropil centres are weighted over the positions of the
  neurons in them. Both projects publish the positions outside Codex, and the
  reader now picks up one Feather table per release directory, matched on its
  columns rather than its name (`SOMA_POSITION_SOURCES`, and
  `soma_position_table` for callers that only want the path). BANC's
  `root_position_nm` is already in nanometres, keyed on `root_888`; MCNS's
  `somaLocation` is an `[x y z]` array in 8 nm EM voxels, scaled on read.
  Coverage is 88.7% of BANC's neurons and 83.8% of MCNS's, against FAFB's
  96.7%. Both files are CC BY 4.0 and neither is required: without one the
  build is exactly as it was. `connkg verify` now names the table it found,
  or reports that it found none. See `docs/DOWNLOAD.md`.

- **`DatasetInfo.min_pair_syn`**: pairs whose synapses, summed over
  neuropils, fall below it are dropped at read time. BANC keeps pairs of 3
  or more, so BANC and MCNS set 5 to compare with FAFB's filtered table;
  FAFB stays at 1 so an unthresholded table chosen with `--connections-file`
  is kept whole. This is per pair; `--min-syn` still filters per neuropil
  row.
- **Nerve-cord neuropils** (`neuropils.py`): names and regions for the
  ventral nerve cord, its nerves, the cervical connective and the
  per-region unassigned buckets, in both releases' spellings, with new
  regions `VNC`, `NERVE` and `CV`. BANC's `Xnerve` (54 synapses) is left
  unnamed.

- **Dataset and View boxes in `connkg viz3d`.** The control rail switches
  between every dataset built under `--root`, and between the circuit and flow
  views, without restarting. A switch keeps the Show box's specs where they
  resolve in the new graph and falls back to the opening scene where they do
  not. The window now owns the open graph and closes each one it replaces.
- **Scene background: `--background` on `quilt` and `viz3d`, and a Background
  box in the viewer's Display tab.** `gray` (the default), `charcoal`, `light`,
  or any `#RRGGBB`; Custom in the viewer opens a color dialog. The context
  cloud mutes toward the chosen background, the floor shades from it, and
  saved images, quilts and casts use it. Region colors are unchanged.
- **Marker sizes scale with the dataset.** Neuropil spheres, flow tubes and
  soma spheres were sized in world units for FAFB v783, so on BANC, whose
  brain and nerve cord stand 2.3 times as tall, the camera zoomed out and
  they drew at under half the size. `world_frame` now measures each
  dataset's framed extent against FAFB's and scales them by the ratio
  (`WorldFrame.marker_scale`): 1.0 on FAFB, so its renders are unchanged,
  2.32 on BANC and 1.12 on MCNS. The context cloud keeps FAFB's size.

### Changed

- **Histamine is inhibitory** (`HIST`, sign -1). FAFB's predictions have no
  histamine class; BANC's and MCNS's do. Tyramine stays unresolved (0).
- **A connection row with no transmitter takes its presynaptic neuron's.**
  BANC and MCNS leave the column empty; FAFB fills every row, so FAFB builds
  are unchanged.
- **Lock: `quiltwright` 0.15.0 -> 0.15.1**, the fleet's current release. The
  floor stays `>=0.15.0`.

- **`kgmodule-utils` floor raised to `>=0.24.0`** in the core dependency and
  all three extras. 0.24.0 drops the vector index when the graph is wiped
  (`KGModule.drop_index()`), so `build --no-index --wipe` now removes a stale
  index instead of keeping it and warning. An unwiped `build --no-index`
  still keeps an existing index and warns, as before: an unchanged graph
  still matches it.

## [0.7.1] - 2026-09-22

### Fixed

- **Line skeletons no longer draw a stray point at every traced point.**
  0.7.0 built the skeleton mesh with `pv.PolyData(points)`, whose
  constructor adds a vertex cell per point; the lines were then set on top,
  so every skeleton rendered its points as well. Points carry no normals,
  so with `--floor` the shadow pass failed to compile their shader and VTK
  logged `Could not set shader program` on the first floored render -- the
  same unlit-branch failure `_shade_skeleton_lines` exists to prevent,
  which it could not fix here because it turns *lines* into tubes, not
  points. The mesh is built empty and filled, as it was before 0.7.0.

## [0.7.0] - 2026-09-22

### Changed

- **`connkg viz3d` launches without a SPEC, on `circuit:compass`.** It
  refused with `--view circuit needs at least one SPEC`, a guard it shared
  with `connkg quilt`. The guard is right for `quilt`, which renders a file
  and exits, so an empty circuit spends a 4K render on nothing; the viewer
  is interactive and has the Show box. Opening on the brain alone was the
  first try and it draws the neuropil surfaces and no neurons at all, since
  the automatic cloud stays off whenever surfaces are drawn -- a shell with
  nothing in it. So a bare `connkg viz3d` opens on the compass circuit
  instead: 151 neurons across five cell types, central and small enough to
  read. Any SPEC replaces it. The default is applied only when it resolves,
  because the shipped circuits name FAFB cell types and a window captioned
  `circuit:compass` drawing nothing is worse than one that opens on the
  brain; on the synthetic fixture it falls back that way. `quilt` is
  unchanged.
- **Traced neurons are drawn as continuous tubes, and they taper.** The
  circuit view built its mesh from `segments()`, one line per traced edge
  with its own two points, so `--tubes` extruded a separate cylinder per
  edge: consecutive cylinders met at an angle with nothing joining them,
  and a neuron came out a heap of faceted stubs. `skeletons.polylines()`
  walks the parent links instead and returns each unbranched run between
  branch points, which tubes into one continuous surface with mitred
  joins. It carries exactly the edges `segments()` does -- tested against
  it on random trees at four strides -- and costs less, because a run's
  interior points are shared rather than repeated per edge: 2.8 M cells
  against 3.4 M on `circuit:compass`, while the tube goes from 6 sides to
  12.
- **The skeleton cache stores the traced radius, and tubes use it.** A
  neuron was piped at one width because the radius was parsed, then
  written to the cache as zeros. Cache format 2 keeps it, and a tube's
  radius is now the traced radius floored at the old constant. FAFB's
  median traced radius is 222 nm, a thread at whole-brain framing, so that
  constant was doing visibility work: flooring rather than replacing it
  means nothing draws thinner than before and only the thick structures --
  major axons, the soma -- widen. A format-1 cache still loads, reads back
  zeros and draws at the constant width, so nothing breaks; re-running
  `connkg skeletons` is what turns the taper on.
- **A tapered tube is capped at the soma's width.** Tapering floored the
  traced radius but never capped it, so the giant fiber -- the thickest
  axon in the brain -- drew at 13x the floor and 2.6x the sphere that
  marks its own cell body, a sausage that swallowed the arbor around it.
  DNp01 was the one scene this broke; `circuit:compass` and the like never
  exceed 3.4x and are unchanged. The radius is now clamped to the soma
  marker's width at the top, so no neurite draws fatter than its own cell
  body, which costs 0.6% of DNp01's points and leaves the taper doing its
  work everywhere else.

## [0.6.0] - 2026-09-21

### Added

- **Save scene, in the 3-D viewer.** A button above Cast writes what is on
  screen without a Looking Glass in the loop: **Image** renders one 4K still
  the way `connkg quilt --still` does, floor and shadows included, and
  **Quilt** writes the quilt Cast would send. Both re-compose the scene
  off-screen from the current specs, settings and camera, sharing the
  cast's scene builder, so the file matches the viewport rather than being
  a screen grab of it. The dialog opens in `renders/stills/` or
  `renders/quilts/`, the chosen name is the stem, and quiltwright appends
  its spec suffix, so the naming matches the CLI's. A failed render is
  reported in the status bar and a dialog and leaves the viewer usable.
- **A command reference, `docs/cli.md`.** Every `connkg` command and
  `connkg-mcp` on one page: options with defaults and ranges, one example
  each with output from the built FAFB v783 graph, and a link to the page
  that explains the command at length where one exists. Until now the only
  complete list was the README's task table, which names each command once
  and documents none of its options; `connkg viz` and three of the five
  `snapshot` subcommands were not in the docs at all.
- **A workspace layout for the 3-D viewer, and what the scene costs.** The
  viewer's toolbar and two docks became the control rail `gutenberg_kg` and
  `pycode_kg` use: the Show box, an Explore tab of example buttons and a
  Display tab of settings down the left, the scene beside them, and the neuron
  inspector below it where **Neuron details** can collapse it. Two lines above
  the scene say what is in it -- circuit and context neurons, neuropil
  surfaces, skeletons or flow arcs -- and what it cost: visible meshes, points
  and cells after glyphs and tubes expand, broken down per group in the
  tooltip, plus the time the composition took. That is the number to watch
  when a scene turns sluggish, and it was previously invisible.
- **Quoting in the Show box, so a label spec can join a union.** Specs are
  split with `shlex` rather than `str.split`, so `"label:giant fib" LC4` draws
  both, and a regex keeps its backslashes. A bare leading `label:` still takes
  the whole box, as before, and an unclosed quote is refused like any other bad
  spec rather than raising.
- **The cloud toggle is tri-state, and stride applies once.** Partially
  checked is automatic -- draw the cloud only when no neuropil surfaces are
  available -- and it stays automatic when some other display setting changes,
  instead of collapsing to on. The skeleton stride applies when it has actually
  been edited, so leaving the field no longer rebuilds the scene for nothing.
- **Reset view, and a wait cursor on the slow steps.** Reset view takes the
  floor off before reframing and puts it back after: `aim_camera` measures
  `plotter.bounds`, and framing a 120-unit floor plane around an 8-unit brain
  fits the floor and shrinks the subject to a speck. The viewer gained a
  toolbar action that frames the current scene again, undoing an orbit or a
  zoom, matching what `gutenberg_kg` and `pycode_kg` already offer. Composing
  a scene and casting both run seconds long on the GUI thread; both now show
  a wait cursor and say what they are doing in the status bar, and the cast
  reports its four stages through the progress sink the SDK already took and
  the viewer was not passing.
- **`circuit:<name>`, a spec form for a named circuit.** Some circuits are
  worth drawing together and nobody remembers them as a list of cell types.
  `circuit:compass` expands to the union of the central complex's five
  head-direction types, and goes anywhere a SPEC goes -- `quilt`, `viz3d`,
  `path`, `cone`, `influence`, `link` -- because it resolves inside
  `ConnectomeKG.neurons_of`. Four ship: `compass` (151 neurons),
  `optic-flow` (24), `mushroom-body` (99) and `clock` (48). The union is
  flat, and the circuit view still colors by each neuron's own cell type, so
  a circuit draws one color per type it contains. Names fold case and `_` to
  `-`; an unknown one is refused by name, listing the circuits there are.
- **The 3-D viewer draws an example when you click it.** The controls dock
  listed the spec grammar as text to be retyped into the Show box; every
  documented spec, answer and circuit is now a button that fills the box and
  applies it, taking the same path a typed spec does, refusals included. The
  meaning moved to the tooltip.
- **A documentation page for querying**, `docs/queries.md`: the SPEC grammar,
  the answer forms, and `connkg path`, `cone`, `influence`, `query`, `link`,
  `stats`, `analyze` and `datasets`. 0.5.0 shipped `influence`, `specs` and
  the whole answer grammar documented in the README and nowhere on the site,
  which was noticed only after the tag was pushed.
- **A viewer section in `docs/rendering.md`**: picking with P, the Show box,
  the control panel, and why a toggle keeps the camera while a new spec does
  not.
- **`tests/test_docs_coverage.py`**, so this cannot happen quietly again. It
  fails when a `connkg` command's name appears nowhere under `docs/`, or when
  a page is missing from `mkdocs.yml`'s nav. `mkdocs build --strict` could not
  catch either: a command with no page is not a broken link. It caught
  `connkg fixture`, which is now covered in `docs/DOWNLOAD.md` as the way to
  skip the download entirely.

### Changed

- **`stats` describes a connectome, not a code graph.** `connkg stats`, the
  `graph_stats` MCP tool and `snapshot save` all read the SDK's generic
  `GraphStore.stats()`, which reports `module_count`, `class_count`,
  `function_count`, `method_count`, `docstring_coverage` and
  `meaningful_nodes`; on a brain every one of them was zero and printed
  anyway. `ConnectomeKG.stats()` now overrides the module method the way the
  rest of the fleet does: the SDK's totals, `node_counts` and `edge_counts`
  stay, the code-graph fields go, and in their place the graph is described
  in its own terms -- `dataset_id`, `dataset_version`, `n_neurons`,
  `n_cell_types`, `n_neuropils`, `n_pairs` and `n_synapses`. Those are the
  names the dataset node and the snapshots already used, so a snapshot's
  metrics keep one copy of each figure. A snapshot saved after this change
  records `n_cell_types`, `n_neuropils` and `vector_backend` and omits the
  six dropped keys; `snapshot diff` against an older one shows every count
  unchanged, verified on the v783 graph. The MCP tool returns the new keys
  too.
- **`--floor` defaults the context cloud on.** The brain's shadow on the
  floor is thrown by the cloud's opaque somas and by nothing else, since the
  translucent surfaces cast none; a floor without a cloud showed the circuit's
  shadow alone. `--no-cloud` still turns it off.
- **Fleet dependency floors raised and relocked** (`kgrag_priv` sweep item 46):
  `kgmodule-utils` to `>=0.23.0`. The three packages released on 2026-09-20 and put
  every consumer's lock behind them within hours; this is the routine
  currency bump that follows.

- **The `kg` Poetry group is gone** (`kgrag_priv` sweep item 50, phase 1).
  It held `doc-kg` and `pycode-kg`, tools this repo runs but never imports. Under the fleet's
  "tools are global" rule a tool is installed once with `uv tool` and is
  never a dependency of the repo; 20 of 22 clones were carrying their own
  copy, and every copy was a lock entry that drifted on each release.

- **American spellings throughout**: `color`, `license`, `gray`, `fiber`,
  `center`, `labeled`. `Dataset.licence` is `Dataset.license` now, and the
  extractor writes a `license` key into the dataset node's metadata; the
  analysis reads either, so a graph built before this keeps reporting its
  license rather than `?` until it is rebuilt. FlyWire's own label text is
  left as it is -- the v783 community label reads `giant fiber/giant
  fibre/GF/GFN` and carries both spellings itself.
- **`quiltwright` floor raised to `>=0.15.0`** (was `>=0.14.1`) and the `ruff`
  floor from `>=0.6` to `>=0.15`, inside the existing `<0.16` cap
  (`kgrag_priv` sweep item 49, tier 1). Nothing here depends on 0.15.0's
  toe-in geometry specifically; this is a currency bump.

### Removed

- **The `__enter__` override is gone** (`kgrag_priv` sweep item 5).
  It existed only to narrow `KGModule.__enter__`, which was typed to
  return the base class, so `with ConnectomeKG(...) as kg:` lost the subclass
  surface under `ty`. kgmodule-utils 0.23.0 returns `Self`, so the
  workaround is redundant; `ty` is clean without it.

### Fixed

- **Read-only commands no longer advertise build options.** `stats`,
  `analyze`, `query`, `path`, `cone`, `influence`, `link` and `viz` all listed
  `--data-dir`, `--source`, `--n`, `--seed`, `--min-syn`, `--connections-file`
  and `--embed-neurons` in their `--help`, because the decorator that gives
  `build` its extraction options had been applied to every command that opens
  a graph. On a built graph the options did nothing, and `connkg stats --seed
  7` was accepted silently. Only `build` takes them now. `cone` keeps
  `--min-syn` as its own option, since that one is a real query threshold,
  and `path --render` and `cone --render` take the same `--data-dir` as
  `quilt` and `viz3d` do, meaning the skeleton download root for neurons the
  cache lacks, with the same `fafb_v783` default.
- **Rebuilding a floored scene no longer shades the new skeletons through the
  old shadow pass.** `clear_actors` keeps render passes, so the second scene's
  line skeletons compiled their shaders against the previous floor's
  `vtkShadowMapPass` before tube shading was enabled -- VTK logged
  "Could not set shader program" and the lines came out unlit. The floor's
  passes are now torn back down to a plain `vtkRenderStepsPass` before a
  rebuild, releasing the old shadow maps while their render window still
  exists, and `add_floor` shades the skeleton lines before enabling shadows
  rather than after. Switching examples in the viewer with the floor on is the
  way to hit this.
- **The viewer cannot start a second composition on top of the first.**
  Composing pumps the Qt event loop to keep the window responsive, which also
  delivers clicks, so a click on Show scene or Cast during a slow scene queued
  work against a half-built one. The rail, Reset view and the scene are
  disabled for the duration and restored afterwards, including when the
  composition raises.
- **A cast from the 3-D viewer is framed like the viewport.** PyVista's
  `camera_position` is (position, focal point, view up) and carries no view
  angle, so the cast helper's fresh off-screen plotter kept VTK's default 30
  degrees while the viewport sat at the 14 that `aim_camera` framed with. The
  subject landed tan(15)/tan(7) = 2.2x too small on the panel, about eight
  scroll-wheel steps to undo by hand. The viewer now carries its view angle
  across. Note the viewport's aspect still differs from the quilt tile's
  (1.56 against 1.78), which adds margin left and right but does not change
  the size of what is cast.
- **`--floor` no longer corrupts skeletons drawn as lines.** VTK's shadow-map
  pass splices `calcShadow(vertexVC, ...)` into every actor's fragment shader
  but declares `vertexVC` only for lit geometry; a line has no normals, so
  its shader failed to compile and the render carried on regardless, drawing
  the skeletons as stray red strokes or not at all. Every documented floor
  render happened to pair `--floor` with `--tubes` or the flow view, which is
  why it went unseen. `add_floor` now renders line skeletons as GPU tubes.
- **Neuropil surfaces show under the floor.** PyVista appends the shadow pass
  after the stock render-steps pass, so each frame drew the opaque geometry a
  second time, shadowed, over any translucent surface in front of the floor.
  `add_floor` re-sequences the passes the way VTK intends: shadowed opaque
  geometry first, translucency after.

## [0.5.0] - 2026-09-20

### Added

- **The source papers as a searchable corpus**, in `papers/`. The graph says
  LC4 makes 1,401 synapses onto DNp01; it does not say how the synapses were
  detected or what a neurotransmitter prediction is worth. DocKG indexes
  Dorkenwald et al. 2024 and Schlegel et al. 2024 beside the connectome, so
  the same session can ask the graph a wiring question and the papers a
  provenance one. `papers/extract.py` and `papers/README.md` are tracked; the
  PDFs and the text derived from them are not, since the publishers' files are
  theirs to distribute.

  Eight papers, about a million characters: the two FlyWire papers, Eckstein
  on neurotransmitter classification, Matsliah on the optic lobe, Namiki on
  descending neurons, Morimoto on looming, Scheffer on hemibrain and Shiu on
  the brain model.

  The extraction undoes the hard wrapping of a two-column PDF, without which
  chunk boundaries fall mid-clause, and cuts the reference lists, which are
  a third to a half of each paper and which retrieve -- before cutting them a
  query for looming visual projection neurons returned a bibliography entry
  rather than any prose. Journals differ enough that this is three rules:
  Nature prints no "References" heading in its extracted text, so its first
  numbered citation is the anchor; eLife and Cell print one, in their own
  case; and a heading only counts when citations crowd in behind it, since
  "References" occurs in prose too. Cell prints 90,000 characters of methods
  *after* its references, so the list is cut as a span rather than a tail.
  eLife's per-figure DOIs are stripped as well -- one paper carried 105 of
  them inline.

  Asked what the giant fiber does in the escape response, the corpus returns a
  passage naming DNp01, the looming stimulus and the fast mode of takeoff: the
  same DNp01 the graph holds as a node, which is what this was for. With only
  the first two papers that query returned nothing useful, since `DNp01`,
  `LC4` and `LPLC2` appeared zero times in either.

- **`connkg specs`** prints every form a SPEC takes, with examples, and the
  answer forms beside them. One list in `connectomekg.answers` feeds the
  command, the README and the 3-D viewer's own panel, and a test asserts every
  example parses -- three were wrong when first written (two synthetic
  fixture names that do not exist on v783, and two cones that blow the scene
  cap) and were caught by running them against the real graph.
- **A control panel in the 3-D viewer.** Toggles for the whole-brain cloud,
  the neuropil surfaces, the floor and tubes; a stride spinner where 0 means
  automatic; a minimum-synapse spinner that brings an over-cap cone back under
  it; and the spec examples listed beside them. The fleet's other viewers
  (`gutenberg_kg`, `pycode_kg`, `Metabo_kg`) all have a panel like this;
  only `genealogy_kg`, which this viewer was modeled on, does not.

- **Answers in the 3-D viewer.** `connkg viz3d "path:LPLC2>DNp01"` opens on the
  answer rather than on a cell type, drawn hop-colored; so does typing the
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

- **`connkg path --render` and `connkg cone --render` draw the answer.** The
  query already knows which neurons answer the question and in what order; the
  flag draws them. A path becomes its hops as traced skeletons, one color per
  hop running dark to bright along the route and labeled with the synapses
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
  belong together and in what color, rather than having cell type decide. The
  circuit view groups by type and colors by name, which is right for "show me
  LC4" and wrong for "show me the answer": a path's hops are an order, and the
  neurons in one hop rarely share a type. With `connectomekg.colors.hop_color`,
  a viridis-style ramp that rises monotonically in luminance so the order
  survives color blindness, this is what `--render` draws with.

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

- **A hero render, `docs/images/anatomy_lplc2_dnp01.png`**, on the README and
  the documentation site: the escape circuit, LPLC2 to DNp01, drawn inside the
  brain's neuropil surfaces with one dot per neuron at its cell body. The four
  existing images were regenerated and now show the surfaces and the somas too.

### Changed

- **A new hero image**, on the README and the documentation site: the
  whole-brain flow map over a floor, `docs/images/flow_all_floor.png`. The
  previous hero was a circuit drawn flat, and the shadow is what it was
  missing. Passing `cloud=True` explicitly is load-bearing here -- drawing
  the neuropil surfaces turns the cloud off by default, and it is the brain's
  outline in cell bodies that the flow map hangs in.

  A note in `render_images.py` had claimed the flow view was seen too nearly
  front-on for a floor to read. With the camera tilted by `FLOOR_ELEVATION`,
  which `add_floor` is designed to pair with, that is not so.

- **`MAX_SCENE_NEURONS` is 5,000, up from 500**, and the skeleton stride now
  defaults to one chosen by neuron count rather than a fixed 4. The old cap
  was set when drawing 500 neurons meant 500 SWC parses out of a 31 GB
  download; the skeleton cache made that a filtered read of one Parquet
  directory. Measured on FAFB v783: 4,000 neurons compose in 4.5 s and render
  in 0.4 s, and the automatic stride holds the point count near
  `SCENE_POINT_BUDGET` so the cost stops tracking the neuron count. `cone:LC4`
  is 489 neurons and `cone:DNp01<1` is 663 -- both refused before, both drawn
  now.

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
  light's angular size), and the floor is no longer the exact color of the
  background, which had left it with no horizon and no lit pool for a shadow
  to fall on.
- **The documentation images are drawn as tubes and stand on the ground.** A
  line has no surface, so no lighting can shade it and a line-drawn circuit
  reads flat however the scene is lit. `--tubes` stays opt-in on the CLI.

### Fixed

- **The 3-D viewer no longer refuses to build when there is no interactor.**
  Picking is an interactor event, and a `QtInteractor` created while
  `pyvista.OFF_SCREEN` is set has no interactor at all, so
  `enable_point_picking` raised `AttributeError` in `BrainSceneWindow`'s
  constructor and the window could not be built. It is skipped in that state
  now -- an off-screen window is one nobody can point at. This is what CI runs
  in, since pyvista's headless-display action exports `PYVISTA_OFF_SCREEN` and
  a developer's machine does not: 21 viewer tests passed locally and failed
  there. A test sets the flag itself, so the developer run catches it too.

- **A toggle in the 3-D viewer no longer throws away the rotation.** Every
  overlay toggle recomposed the scene and re-aimed the camera, so turning the
  floor on after orbiting put the view back where it started. A toggle changes
  what is drawn, not what is being looked at, so the camera is kept; a new
  spec or answer still re-frames, since the old camera may not contain it.
- **The floor no longer blocks the scene from below.** It was an opaque
  120-unit plane visible from both sides, so orbiting under the subject put it
  between the camera and the brain -- nothing was visible at all. It is culled
  from behind now: a floor is a surface to stand on, not a wall. (Viewed from
  underneath the subject is still dark, which is the shadow rather than the
  floor: the only shadow-casting light is above it.)

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

- **`docs/scripts/render_images.py` runs again.** It opened `ConnectomeKG(".")`,
  which has looked for `./.connectomekg/graph.sqlite` since 0.3.0 moved each
  dataset into `connectomes/<dataset>/`, so it failed on its first line and
  nothing had regenerated the documentation images since 2026-09-17. They
  therefore still showed the whole-brain cloud of marked points with no
  neuropil surfaces, two days after 0.4.0 added both.

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
  login, each spec in its own Okabe-Ito color inside a translucent brain
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
  login, each spec in its own Okabe-Ito color inside a translucent brain
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
  color table, and a collapsible table of every labeled neuropil. The
  swatches are generated from `connectomekg.colors` and show the colors as
  drawn. `docs/scripts/render_images.py` redraws the four doc images through
  the same steps as `connkg quilt --still` and labels neuropils in the flow
  images. `connectomekg.neuropils` gains `REGION_NAMES`, `NEUROPIL_REGION`
  and `neuropil_region`, grouping every neuropil into the 13 regions of the
  nomenclature FlyWire follows (Ito et al. 2014).

- **`--floor`, `--elevation` and `--still` for the 3-D views.** `--floor`
  (on `connkg quilt` and `connkg viz3d`) stands the scene over a floor in
  the background gray, lit by a shadow-casting spotlight from above, with an
  8192 px shadow map. The new `scene.add_floor` does it after framing, so the
  floor never decides the framing, and the viewer's Cast rebuilds it.
  `--elevation` tilts the camera to look down (default 25 degrees with a
  floor, which is invisible from level). `connkg quilt --still` renders the
  quilt's center view as one flat image at the preset's aspect, 3840 x 2160
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
  as tubes, colored by source neuropil and bowed to one side so A -> B and
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
  whole-brain context cloud, colored by super class or transmitter sign; view
  B is a spec's circuit -- neurons resolved via `ConnectomeKG.neurons_of`,
  drawn from their traced skeletons (read from `fafb_v783/sk_lod1_783_healed/`
  by the new `connectomekg.skeletons`, NumPy only) at full brightness, one
  line mesh per cell type plus a soma sphere; a neuron with no skeleton file
  falls back to a larger sphere at its marked point, counted separately.
  `connectomekg.scene.build_brain_scene` composes both views into a
  caller-supplied `pv.Plotter`, framed with `kg_utils.viz3d.frame_tree` and
  colored deterministically per cell type via `seed_from_key`; it is Qt-free,
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
  partner types through the shared `kg_utils.viz` renderer: nodes colored by
  super class, edges labeled with synapse count and transmitter
  (`28,530 ACH`) and colored by sign, and partner-to-partner edges drawn only
  when at least as strong as the weakest edge to the center. `--view partners`
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
  normalized. A type maps to a term only when at least half as many of its
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

- **Color-blind-safe colors in the 3-D views, with no pastels.** Neuropil
  spheres and flow tubes are colored by brain region (`scene.region_color`)
  instead of a 15-color hash of the neuropil name, which had given unrelated
  neuropils the same color. The regions use the 8 saturated Okabe-Ito colors
  (`colors.REGION_COLOR`); neighbouring regions share a color where 13 do not
  fit. Cell-type colors are the 7 non-black Okabe-Ito colors. The flow
  view's context cloud is one neutral gray, so color there means only region,
  and `--color-by` applies to the circuit view alone. The context cloud is
  muted toward the gray background instead of lightened toward white, so a
  skeleton that shares a hue with the dots around it still stands out.
  Neuropil spheres and tubes are lit more evenly (`_FLOW_AMBIENT`), because
  shading turned the yellow region color orange.

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

- **3-D scenes render on a muted gray background, and the context cloud is
  drawn as sphere glyphs sized in world units.** The cloud used to be
  pixel-sized points on white. It disappeared in a HiDPI viewer window and
  in quilt tiles. Its colors are now lightened 35% toward white instead of
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

- Initial import from the private KGRAG fleet prototype: normalized
  connectome tables, the FlyWire FAFB v783 release manifest with checksums,
  the Codex reader, a seeded synthetic connectome with planted feeding,
  escape and grooming circuits, the extractor emitting neurons, cell types,
  neuropils, hemilineages, labels and taxa with signed synapse edges,
  `ConnectomeKG(KGModule)` with strongest-path and cone queries and a
  Markdown analysis, and the `connectome-kg` CLI.
