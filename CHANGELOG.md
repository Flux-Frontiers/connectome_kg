# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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

- Initial import from the `kgrag_priv/connectome_kg` prototype: normalised
  connectome tables, the FlyWire FAFB v783 release manifest with checksums,
  the Codex reader, a seeded synthetic connectome with planted feeding,
  escape and grooming circuits, the extractor emitting neurons, cell types,
  neuropils, hemilineages, labels and taxa with signed synapse edges,
  `ConnectomeKG(KGModule)` with strongest-path and cone queries and a
  Markdown analysis, and the `connectome-kg` CLI.
