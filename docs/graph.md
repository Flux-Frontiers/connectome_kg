# What is in the graph

`connkg build` reads one connectome release and writes a typed graph to
SQLite. Every neuron is a node, and every connected pair of neurons is one
`SYNAPSES_TO` edge carrying its synapse count and a transmitter sign. Cell
types, taxonomy, neuropils and annotations sit on top.

The synapse counts come from the electron microscope, and the labels on top
are a thin semantic layer. A vector index over the labels (cell type names,
neuropils, community labels, taxa) lets `connkg query` find a place to start;
the graph answers everything after that. Neurons are not embedded by default,
because there are 139,255 of them in FAFB v783 and their names carry little
meaning. `connkg build --embed-neurons` embeds them anyway.

## Node kinds

| node kind | what it is |
|---|---|
| `dataset` | One connectome release, with its provenance |
| `taxon` | Super class, class and sub class, and the visual subsystems and families |
| `hemilineage` | The developmental lineage a cell type belongs to |
| `nerve` | A nerve that neurons enter or leave the brain by |
| `neuropil` | A brain region, split by side |
| `column` | A visual column in one optic lobe |
| `connectivity_tag` | A Codex connectivity tag selective enough to say something about a neuron: `broadcaster`, `highly_reciprocal_neuron`, `integrator`, `nsrn` |
| `ontology_term` | A Drosophila Anatomy Ontology (FBbt) term |
| `cell_type` | A named type, with its transmitter and sign |
| `neuron` | One reconstructed cell, keyed by root id, with position and synapse totals |
| `label` | A community annotation, with attribution |

The other Codex connectivity tags (`feedforward_loop_participant`,
`reciprocal`, `3_cycle_participant`, `rich_club`) are on 44% to 95% of v783
neurons, so they stay in neuron metadata and get no node.

## Edge kinds

| edge kind | from | to | meaning |
|---|---|---|---|
| `SYNAPSES_TO` | neuron | neuron | Synapse count, transmitter and sign, and the per-neuropil breakdown |
| `TYPE_SYNAPSES_TO` | cell type | cell type | The same wiring summed over the two types |
| `INSTANCE_OF` | neuron | cell type | The neuron's type |
| `MEMBER_OF` | cell type | hemilineage | The type's lineage |
| `CONTAINS` | taxon | taxon or cell type | Super class to class to sub class, visual subsystem to family, and taxon to cell type |
| `IN_NEUROPIL` | neuron | neuropil | Pre- and postsynaptic counts in that neuropil |
| `INNERVATES` | cell type | neuropil | The type's main neuropils, by synapse count |
| `LABELED` | neuron | label | Who labeled it and when |
| `MIRROR_OF` | neuron | neuron | Left to right, for types with exactly one neuron per side |
| `VIA_NERVE` | neuron | nerve | The nerve the neuron runs through |
| `IN_COLUMN` | neuron | column | The visual column the neuron sits in |
| `TAGGED` | neuron | connectivity tag | A selective connectivity tag |
| `MAPS_TO` | cell type | ontology term | An FBbt term on at least half as many of the type's neurons as its best-supported term |
| `IN_DATASET` | top-level node | dataset | Super classes, cell types, neuropils, hemilineages and annotation nodes to their release |

`connkg stats` prints the count of each kind for a built graph.

## Transmitter signs

Signs follow Shiu et al. (2024):

- Acetylcholine, dopamine, octopamine and serotonin are +1.
- GABA and glutamate are -1. Glutamate is inhibitory in *Drosophila* through
  GluCl-alpha.
- Histamine is -1 in BANC and MCNS. FAFB's predictions have no histamine
  class.
- An unresolved transmitter is 0, and so is tyramine (209 BANC neurons),
  which has no settled sign.

A path's net sign is the product of its hop signs, so two inhibitory hops make
an excitatory route. See [Asking the graph a question](queries.md) for how
paths and influence use the signs.

## One graph per connectome

Each release is built into its own directory under `--root`:

```text
<root>/connectomes/
  fafb783/.connectomekg/     graph.sqlite, vectors.sqlite, snapshots/
  banc888/.connectomekg/
  mcns1/.connectomekg/
```

Releases never share a graph, a vector index or a snapshot history.
`--dataset ID` picks one, and it is a global option, so it goes before the
command:

```bash
connkg --root . --dataset banc888 stats
```

Without `--dataset`, `connkg build` writes to `fafb783` (`synthetic` with
`--source synthetic`), and every other command uses the only built dataset.
When a root holds several, the command stops and lists them. `connkg datasets`
lists them too. Dataset ids are 1 to 64 lowercase letters, digits, `_`, `.` or
`-`.

### Move a graph from the old layout

A graph built before this layout sits in `<root>/.connectomekg/`. To move it
into place as `fafb783`, run this from `<root>`:

```bash
mkdir -p connectomes/fafb783/.connectomekg
mv .connectomekg/*.sqlite* connectomes/fafb783/.connectomekg/
```

## Query the SQLite directly

The graph is an ordinary SQLite file with `nodes` and `edges` tables. Edge
details such as `syn_count` are JSON in `edges.evidence`:

```bash
sqlite3 connectomes/fafb783/.connectomekg/graph.sqlite \
  "SELECT rel, count(*) FROM edges GROUP BY rel"
```
