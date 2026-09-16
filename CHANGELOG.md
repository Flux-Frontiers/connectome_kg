# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

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
