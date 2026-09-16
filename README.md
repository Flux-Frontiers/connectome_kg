# connectome-kg

Connectomes as KGModule knowledge graphs. First corpus: FlyWire FAFB v783.

A KGModule for connectomes, built on
[kgmodule-utils](https://github.com/Flux-Frontiers/KG_utils). Every edge is a
counted synapse seen in an electron microscope; the semantic layer is the
small human vocabulary on top (cell types, neuropils, community labels).
Getting the data: [`docs/DOWNLOAD.md`](docs/DOWNLOAD.md). The design plan
lives in the private `kgrag_priv` repo as `docs/CONNECTOME_KG_PLAN.md`.

## What works (2026-09-16)

- `schema.py`: the normalised tables every reader produces (neurons,
  connections, labels, dataset provenance) with validation and the Shiu
  sign convention.
- `manifest.py`: the v783 Codex file list with expected SHA-256 values and
  `verify_dir()`.
- `readers/codex.py`: a Codex release directory to tables.
- `readers/synthetic.py`: a seeded synthetic connectome shaped like v783
  (population shares, degree tail, synapse histogram, transmitter shares,
  reciprocity) with planted feeding, escape and grooming circuits, and a
  writer that emits it in Codex format so the reader is tested end to end.
  At least 361 neurons, so every planted circuit fits its super class;
  `min_neurons()` derives that floor and a smaller size is refused.
- `extractor.py`: the plan's section 4 graph. Node kinds dataset, taxon,
  hemilineage, neuropil, cell_type, neuron, label. Edge kinds CONTAINS,
  MEMBER_OF, INNERVATES, INSTANCE_OF, IN_NEUROPIL, LABELED, SYNAPSES_TO,
  TYPE_SYNAPSES_TO, MIRROR_OF, IN_DATASET. Neurons are not embedded by
  default.
- `module.py`: `ConnectomeKG(KGModule)` with `neurons_of()` (type name,
  root id, node id, or `label:<regex>`), `strongest_path()`, `cone()` and a
  Markdown `analyze()`.
- `paths.py`: strongest signed path (Dijkstra on minus log input fraction)
  and up/down cones over the neuron-level wiring.
- `cli.py`: `fixture`, `verify`, `build`, `stats`, `analyze`, `query`,
  `path`, `cone`.

Not done: a real v783 build (needs the download), snapshots, the neuprint
reader, the LIF what-if, fleet wiring.

## Try it

```bash
poetry install --with dev          # or: pip install -e . pytest
pytest                             # 20 pass with the semantic extra installed;
                                   # the semantic query test skips without it

connectome-kg fixture --out /tmp/synth1k --n 1000 --seed 1
connectome-kg --root /tmp/kg build --data-dir /tmp/synth1k \
    --dataset-id synthetic1k --no-index --wipe
connectome-kg --root /tmp/kg path --dataset-id synthetic1k --from GRN_sugar --to MN9
connectome-kg --root /tmp/kg cone --dataset-id synthetic1k LC4 --min-syn 5
connectome-kg --root /tmp/kg analyze --dataset-id synthetic1k
```

Against a real download, after fetching the v783 files from
https://codex.flywire.ai/api/download:

```bash
connectome-kg verify --data-dir /path/to/fafb_v783
connectome-kg --root . build --data-dir /path/to/fafb_v783 --dataset-id fafb783
```

The full build has not been run yet; see the plan's section 8 for the edge
volume risks it will hit first.
