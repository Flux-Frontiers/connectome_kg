# Release Notes -- v0.6.0

> Released: 2026-09-21

The 3-D viewer becomes a workspace that can save what it shows, `connkg stats` describes a connectome instead of a code graph, eight commands stop advertising options they never used, and every command finally has a reference page.

## What changed

**The viewer is a workspace.** The toolbar and two docks are gone. A control rail down the left holds the Show box, an Explore tab that lists every documented spec, answer and named circuit as a button, and a Display tab for the overlays and detail settings; the scene sits beside it with a collapsible neuron inspector below. Two lines above the scene say what is drawn and what it cost: circuit and context neurons, surfaces and skeletons, then visible meshes, points and cells after glyph and tube expansion, and the seconds the composition took. That last number is the one to watch when a scene turns sluggish, and it was invisible before. The Show box now takes quotes, so `"label:giant fib" LC4` draws both and a regex keeps its backslashes; the cloud toggle has an automatic third state that survives other edits; Reset view reframes without the floor fooling it; and the slow steps show a wait cursor and report progress in the status bar instead of freezing silently.

**Save scene.** A button above Cast writes the current view to disk without a Looking Glass in the loop: a 4K still framed and lit the way `connkg quilt --still` renders, or the quilt Cast would have sent. Both re-compose the scene off-screen from the live specs, settings and camera, so the file matches the viewport rather than being a screen grab. Names follow the CLI's convention, with quiltwright's spec suffix appended to the stem you choose.

**Named circuits.** `circuit:compass`, `circuit:optic-flow`, `circuit:mushroom-body` and `circuit:clock` expand to the cell types worth drawing together, and go anywhere a spec goes: `quilt`, `viz3d`, `path`, `cone`, `influence`, `link`.

**Rendering fixes.** `--floor` no longer corrupts skeletons drawn as lines, neuropil surfaces no longer vanish under the floor, rebuilding a floored scene no longer shades the new skeletons through the previous shadow pass, a cast is framed at the viewport's view angle rather than VTK's default, and the viewer can no longer start a second composition on top of one in progress. With a floor the context cloud is now on by default, since it is what throws the brain's shadow.

**`stats` describes a connectome.** `connkg stats`, the `graph_stats` MCP tool and `snapshot save` used to report `module_count`, `class_count`, `function_count`, `method_count` and `docstring_coverage`, all zero on a brain. They now lead with the dataset and its figures: `dataset_id`, `dataset_version`, `n_neurons`, `n_cell_types`, `n_neuropils`, `n_pairs` and `n_synapses`, followed by the SDK's totals and the counts by kind and relation. The names are the ones snapshots already used, so a snapshot keeps one copy of each figure.

**A tidier CLI.** The options that tell `build` what to extract had been attached to every command that opens a graph, so `connkg stats --help` offered `--seed` and `--source` and accepted them silently. Only `build` takes them now. `cone` keeps `--min-syn` as its own threshold, and `path --render` and `cone --render` take the same `--data-dir` as `quilt` and `viz3d`, so a rendered answer falls back to the skeleton download for neurons the cache lacks.

**Documentation.** A command reference covers every `connkg` command and `connkg-mcp` with options, defaults and an example each; a querying page explains the spec grammar, the answer forms and each query command; the viewer section on the rendering page matches the new layout, with screenshots. A test now fails when a command's name appears nowhere in the docs or a page is missing from the nav, which is how 0.5.0 shipped three features documented only in the README.

**Housekeeping.** The dependency floors follow the fleet's 2026-09-20 releases: `kgmodule-utils>=0.23.0`, `quiltwright>=0.15.0`, `ruff>=0.15`. The `kg` Poetry group of never-imported tools is gone. Spellings are American throughout, which renames `Dataset.licence` to `Dataset.license`. The `__enter__` override that worked around an SDK typing gap is removed now that the SDK returns `Self`.

## Upgrading

No rebuild is needed; a graph built by 0.5.0 works as it is. The one thing a build gains is the `license` key on the dataset node, and the analysis reads the old `licence` key too, so it reports the same either way.

If you scripted against `connkg stats` or the `graph_stats` tool, the code-graph keys are gone and the new keys arrive; `total_nodes`, `total_edges`, `node_counts` and `edge_counts` are unchanged. If you passed `--source`, `--data-dir`, `--seed` or the other extraction flags to a read command, drop them; `cone --min-syn` still works, and `path`/`cone` now take `--data-dir` only for `--render`. Python callers reading `Dataset.licence` should read `Dataset.license`. With `--floor`, pass `--no-cloud` if you relied on the cloud being off.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
