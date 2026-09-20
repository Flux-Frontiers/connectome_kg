[![Python](https://img.shields.io/badge/python-3.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![License: Elastic-2.0](https://img.shields.io/badge/License-Elastic%202.0-blue.svg)](https://www.elastic.co/licensing/elastic-license)
[![Version](https://img.shields.io/badge/version-0.5.0-blue.svg)](https://github.com/Flux-Frontiers/connectome_kg/releases)
[![CI](https://github.com/Flux-Frontiers/connectome_kg/actions/workflows/ci.yml/badge.svg)](https://github.com/Flux-Frontiers/connectome_kg/actions/workflows/ci.yml)
[![Poetry](https://img.shields.io/endpoint?url=https://python-poetry.org/badge/v0.json)](https://python-poetry.org/)
[![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.22817369-blue.svg)](https://doi.org/10.5281/zenodo.22817369)
[![Data: FlyWire FAFB v783](https://img.shields.io/badge/data-FlyWire%20FAFB%20v783-orange.svg)](https://github.com/Flux-Frontiers/connectome_kg/blob/main/docs/DOWNLOAD.md)

# ConnectomeKG -- Connectomes as Knowledge Graphs

**ConnectomeKG turns an electron-microscopy connectome into a queryable knowledge graph: every neuron a node, every edge a counted synapse, with the cell types, neuropils and community labels layered on top.**

<!-- An absolute raw URL, not a repo-relative path: PyPI re-hosts this README
     and repo-relative images do not resolve there. Pinned to main rather than
     to a tag on purpose -- a tag-pinned hero has to be bumped every release
     and fails silently when it is not, serving the previous release's image
     at 200 OK. -->
![The FlyWire FAFB v783 fly brain seen from the front and slightly above, standing on a floor with its shadow below. Colored spheres mark the 79 neuropils, linked by curved tubes showing where signal flows between them, inside a haze of gray dots, one for each of the 139,255 neurons' cell bodies.](https://raw.githubusercontent.com/Flux-Frontiers/connectome_kg/main/docs/images/flow_all_floor.png)

**The whole fly brain, and where its signal goes.** Each sphere is one of the 79 neuropils, placed at the synapse-weighted center of its neurons and colored by brain region -- orange for the optic lobes down each side, yellow for the superior neuropils and lateral horn across the top, green for the antennal lobe and the neuropils around the esophagus below, blue and light blue for the inferior, ventromedial and ventrolateral neuropils between them. A sphere's width grows with the cube root of its synapse count, so one twice as wide holds about eight times as many.

The tubes are the strongest 100 of 5,786 directed neuropil pairs. Thickness grows with the square root of the flow, and each tube bows to the right of its direction of travel, so a tube bulging toward you runs left to right. Flow is carried by neurons rather than counted from synapses: each neuron's output synapses in B, apportioned by the share of its input lying in A, summed over every neuron.

Behind them, one gray dot per neuron at its cell body -- all 139,255 of them, which is what gives the brain its outline. The floor and shadow carry no data; they are there for depth. One command draws it: `connkg quilt --view flow --floor --cloud --still`.

*Render of the [FlyWire](https://flywire.ai) FAFB v783 connectome ([Dorkenwald et al. 2024](https://doi.org/10.1038/s41586-024-07558-y); [Schlegel et al. 2024](https://doi.org/10.1038/s41586-024-07686-5)), [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). The image is an adaptation shared under the same license, not under the software's Elastic License 2.0.*

The first corpus is the FlyWire FAFB v783 adult *Drosophila* brain: 139,255 neurons and 3,732,460 connected neuron pairs. ConnectomeKG reads the Codex export, normalizes it into dataset-neutral tables, and writes a typed graph to SQLite. Neurons are instances of cell types, cell types sit under a super class and class taxonomy and belong to hemilineages, and both neurons and types connect to the neuropils they innervate. Each synapse edge carries its count and a transmitter sign. A vector index over the small human vocabulary (cell type names, neuropils, labels, taxa) lets a query like *"sugar sensing gustatory neurons"* find the right place to start.

From there you can ask wiring questions directly: the strongest signed path from a sensory neuron to a motor neuron, the downstream cone of a visual projection type, the hub neurons and strongest type-to-type connections. Because it is a `KGModule` built on [kgmodule-utils](https://github.com/Flux-Frontiers/KG_utils), the same graph also federates with the rest of the KGRAG fleet.

The design follows its siblings: **structure is ground truth; embeddings are an acceleration layer**. In a connectome this is literal. The synapse counts come from the microscope and the semantic layer is a thin set of labels on top. Neurons are not embedded by default; there are 139k of them and their names carry little meaning. Search finds a type or a neuropil, then the graph does the rest.

Everything runs on your laptop. A full v783 build without the vector index takes about three minutes.

*Author: Eric G. Suchanek, PhD -- Flux-Frontiers, Liberty TWP, OH*

> **Status: pre-alpha (0.5.0).** The Codex reader, the synthetic fixture, the extractor, path, cone and influence queries, the Markdown analysis, snapshots, the `connkg` CLI, the `connkg-mcp` server, and the 2-D and 3-D views work end to end, and a real FAFB v783 build has been run and measured. Not done yet: the neuPrint reader (hemibrain, MaleCNS) and the LIF what-if simulation. The KGRAG adapter ships in kg-rag 0.16.0: `pip install "kg-rag[connectome]"`.

---

## Sister projects

ConnectomeKG is part of the **KGRAG** family, a suite of knowledge-graph systems that share the same hybrid semantic-plus-structural design, each for a different kind of corpus:

- **[PyCodeKG](https://github.com/Flux-Frontiers/pycode_kg)** -- Python source code: modules, classes, functions and their typed relationships.
- **[DocKG](https://github.com/Flux-Frontiers/doc_kg)** -- document corpora (`.md`, `.txt`, `.rst`, `.pdf`) with source-grounded passage packs.
- **[MetaboKG](https://github.com/Flux-Frontiers/metabo_kg)** -- metabolic pathways (KEGG, SBML, BioPAX) with FBA and ODE simulation on top of the graph.
- **[GenealogyKG](https://github.com/Flux-Frontiers/genealogy_kg)** -- GEDCOM family-history files: people, families, events, places and lineage.
- **[DiaryKG](https://github.com/Flux-Frontiers/diary_kg)** -- personal journals and diary corpora.
- **[AgentKG](https://github.com/Flux-Frontiers/agent_kg)** -- conversational memory as a knowledge graph.

All of them build on **[kgmodule-utils](https://github.com/Flux-Frontiers/KG_utils)**, the shared SDK for storage, indexing, query and snapshots.

---

## Get started

**Requirements:** Python >= 3.12, < 3.14

```bash
pip install "connectome-kg[semantic]"
```

To work on it, install from a clone instead:

```bash
git clone https://github.com/Flux-Frontiers/connectome_kg.git
cd connectome_kg
pip install -e ".[semantic]"      # or: poetry install --with dev --extras semantic
```

The `semantic` extra adds the embedding model for `connkg query`. Without it, everything except semantic search works; pass `--no-index` to `build`.

The `viz3d` extra (`pip install "connectome-kg[viz3d]"`) adds PyVista, PyQt5, pyvistaqt
and [quiltwright](https://flux-frontiers.github.io/quiltwright/) for `connkg quilt` and `connkg viz3d`: real-geometry 3-D
views of the whole brain plus a circuit's traced skeletons or the signal flow
between neuropils, rendered to a Looking Glass quilt or opened in an
interactive viewer. [docs/rendering.md](https://github.com/Flux-Frontiers/connectome_kg/blob/main/docs/rendering.md) explains both views
and how each is drawn.

No install at all also works from the clone root: `PYTHONPATH=src python -m connectomekg <arguments>`. With Poetry, prefix commands with `poetry run`.

### Try it on a synthetic connectome

No download needed. The fixture is a seeded connectome shaped like v783 (population shares, degree tail, synapse histogram, transmitter shares, reciprocity) with planted feeding, escape and grooming circuits, written in Codex format so it goes through the real reader:

```bash
connkg fixture --out /tmp/synth1k --n 1000 --seed 1
connkg --root /tmp/kg --dataset synthetic1k build --data-dir /tmp/synth1k --no-index --wipe
connkg --root /tmp/kg path --from GRN_sugar --to MN9
connkg --root /tmp/kg cone LC4 --min-syn 5
connkg --root /tmp/kg analyze
```

### Build the real FlyWire brain

The Codex portal needs a Google sign-in and lists display labels instead of file names, so the download is a manual step. [docs/DOWNLOAD.md](https://github.com/Flux-Frontiers/connectome_kg/blob/main/docs/DOWNLOAD.md) walks through it, including which three files are required (about 71 MB) and the Safari `.gz` trap.

```bash
connkg files                                   # portal label -> file name
connkg verify --data-dir /path/to/fafb_v783    # check the download
connkg --root . --dataset fafb783 build --data-dir /path/to/fafb_v783
connkg --root . analyze
```

For the 3-D views, two more one-time passes fill in the anatomy:

```bash
connkg --root . --dataset fafb783 meshes                                  # 78 neuropil surfaces, ~1 MB
connkg --root . --dataset fafb783 skeletons --data-dir /path/to/fafb_v783 -j 12
```

`skeletons` needs the 31 GB skeleton download, and is the only thing that
does: it caches every neuron's simplified skeleton (2.5 GB) and writes each
neuron's real soma into the graph. `-j` is the worker count and defaults to 1,
so pass your core count -- 2m 39s across twelve on FAFB v783, against 19m 30s
on one.

Measured on Apple silicon for the 0.2.0 release, September 2026: 3 minutes 2 seconds, 7.2 GB peak memory, and 2.3 GB of SQLite for 157,698 nodes and 5,072,285 edges. Keep about 4 GB free; the write-ahead log and the database both exist during the final checkpoint. The vector index for `connkg query` adds 25 seconds (16,861 vectors, 29 MB; Apple M5 Max, September 2026); `--no-index` skips it.

---

## What is in the graph

| Node kind | What it is |
|---|---|
| `dataset` | One connectome release, with its provenance |
| `taxon` | Super class and class from the FlyWire hierarchy |
| `hemilineage` | Developmental lineage a cell type belongs to |
| `neuropil` | Brain region, split by side |
| `cell_type` | Named type, with its transmitter and sign |
| `neuron` | One reconstructed cell, keyed by root id, with position and synapse totals |
| `label` | Community annotation, with attribution |

| Edge kind | Meaning |
|---|---|
| `SYNAPSES_TO` | Neuron to neuron, with synapse count and transmitter sign |
| `TYPE_SYNAPSES_TO` | The same wiring aggregated to cell types |
| `INSTANCE_OF` | Neuron to its cell type |
| `MEMBER_OF` | Cell type to its hemilineage |
| `CONTAINS` | Super class to class, and taxon to cell type |
| `IN_NEUROPIL` | Neuron to neuropil, with pre- and postsynaptic counts |
| `INNERVATES` | Cell type to its main neuropils |
| `LABELED` | Neuron to a community label, with who labeled it and when |
| `MIRROR_OF` | Left neuron to right neuron, for types with exactly one per side |
| `IN_DATASET` | Neuron to its release |

Transmitter signs follow Shiu et al. (2024): acetylcholine, dopamine, octopamine and serotonin are +1; GABA and glutamate (inhibitory in *Drosophila* via GluCl-alpha) are -1; an unresolved transmitter is 0.

---

## How path queries work

`connkg path` and `connkg cone` load the `SYNAPSES_TO` edges once into a sparse matrix and answer with SciPy.

An edge's weight is the **fraction of the postsynaptic neuron's input synapses** it carries. A path's strength is the product of those fractions, so the strongest path is the Dijkstra shortest path on `-log(fraction)`. This is the connectome-interpreter convention: a 40-synapse input that is half of a small neuron's drive counts for more than a 40-synapse input that is 1% of a large one. Each result reports per-hop synapse counts, fractions and signs, and a net sign for the whole path.

A **spec** names a starting set of neurons in any of four ways:

| Spec | Resolves to |
|---|---|
| `LC4` | Every neuron of that cell type |
| `720575940612345678` | One neuron by FlyWire root id |
| `connectome:...:n:...` | One neuron by graph node id |
| `label:<regex>` | Every neuron whose community label matches |

---

## What you can do with it

| If you want to... | Reach for |
|---|---|
| **See which portal files to download** | `connkg files` |
| **Check a download before building** | `connkg verify --data-dir DIR` |
| **Make a test connectome** | `connkg fixture --out DIR` |
| **Build the graph** | `connkg build` |
| **List the connectomes built under a root** | `connkg datasets` |
| **List every SPEC and answer form, with examples** | `connkg specs` |
| **Count nodes and edges** | `connkg stats` |
| **Get a Markdown report: hubs, top type-to-type links, neuropils, coverage** | `connkg analyze` |
| **Search types, neuropils and labels** | `connkg query "..."` |
| **Find the strongest path between two specs** | `connkg path --from A --to B` |
| **Walk downstream or upstream** | `connkg cone SPEC --hops N --direction down\|up` |
| **Measure how much one population drives another, signed** | `connkg influence --from A --to B --hops N` |
| **Draw the answer: a path's hops or a cone's shells, hop-colored** | `connkg path --from A --to B --render`, `connkg cone SPEC --render` (the `viz3d` extra) |
| **Open neurons as FlyWire meshes in the browser, no login** | `connkg link SPEC [SPEC...]` (FAFB v783) |
| **Draw a cell type's partner network or partner chart** | `connkg viz TYPE --view network\|partners` (the `viz` extra) |
| **Render a circuit inside the whole brain as a Looking Glass quilt** | `connkg quilt SPEC [SPEC...]` (the `viz3d` extra) |
| **Open a circuit inside the whole brain in an interactive 3-D viewer** | `connkg viz3d SPEC [SPEC...]` (the `viz3d` extra) |
| **Draw the signal flow between neuropils in 3-D, for the whole brain or one population** | `connkg quilt --view flow [SPEC...]`, `connkg viz3d --view flow [SPEC...]` (the `viz3d` extra) |
| **Draw the brain's 78 neuropil surfaces in the 3-D views** | `connkg meshes` once, then any `quilt` or `viz3d` (FAFB v783) |
| **Cache simplified skeletons and give every neuron a soma** | `connkg skeletons --data-dir fafb_v783 -j 12` once (2m 39s on v783); the circuit view then renders without the 31 GB download, and the whole-brain cloud shows cell bodies |
| **Render a view as one 4K image, over a floor with shadows** | `connkg quilt SPEC --still --floor` (the `viz3d` extra) |
| **Record the graph's metrics** | `connkg snapshot save [VERSION]` |
| **Give an AI agent the graph** | `connkg-mcp --root DIR [--dataset ID]` |

### What a SPEC can be

Every command that takes neurons takes the same grammar, and `connkg specs` prints it.

| spec | means |
|---|---|
| `LC4` | every neuron of a cell type, by exact name (case-sensitive) |
| `DNp01` | the two giant fiber descending neurons |
| `720575940622838154` | one neuron, by FlyWire root id |
| `connectome:fafb783:n:720575940622838154` | the same neuron, by node id |
| `label:giant fib` | every neuron a community label matches, as a regex |
| `label:^LPLC2_` | anchored, so it matches the label's start |

An **answer** goes anywhere a spec does, and draws the query rather than naming it:

| answer | means |
|---|---|
| `path:LPLC2>DNp01` | the strongest signed path, hop by hop |
| `path:LC4>DNp01` | looming detectors to the giant fiber: the escape circuit |
| `path:label:giant fib>DNp04` | a path may start from a label |
| `cone:LC4` | everything one hop downstream: 489 neurons |
| `cone:DNp01<1` | one hop upstream -- the arrow follows the signal: 663 |
| `cone:label:giant fib<1` | a spec may itself carry a prefix |

The arrow follows the signal, which is why upstream is `<`. Specs are case-sensitive, and a `label:` pattern is a regular expression. An answer that will not fit in one scene is refused; narrow it with `--min-syn`.

`--root` and `--dataset` come before the command. Run `connkg <command> --help` for every option.

### One graph per connectome

Each connectome release is built into its own directory, the way GutenbergKG keeps one graph per book:

```text
<root>/connectomes/
  fafb783/.connectomekg/     graph.sqlite, vectors.sqlite, snapshots/
  synthetic/.connectomekg/
```

Releases never share a graph, a vector index or a snapshot history. `--dataset ID` picks one. Without it, `connkg build` writes to `fafb783` (`synthetic` with `--source synthetic`), and every other command uses the only built dataset, or stops and lists them when there are several. Dataset ids are 1-64 lowercase letters, digits, `_`, `.` or `-`.

A graph built before this layout sat in `<root>/.connectomekg/`. Move it with:

```bash
mkdir -p connectomes/fafb783/.connectomekg
mv .connectomekg/*.sqlite* connectomes/fafb783/.connectomekg/
```

### From Python

```python
from connectomekg import ConnectomeKG

with ConnectomeKG("/tmp/kg", source="synthetic", n_neurons=1000, seed=1) as kg:
    kg.build_graph(wipe=True)       # graph only; build() also embeds (semantic extra)
    path = kg.strongest_path("GRN_sugar", "MN9")
    print(path.strength, path.net_sign, [h.node_id for h in path.hops])
    print(kg.analyze())
```

### As an MCP server

`connkg-mcp` serves the graph to MCP clients (Claude Code, Claude Desktop,
Cursor) over stdio, or SSE with `--transport sse`. Point `--root` at the
directory holding `connectomes/`, and add `--dataset ID` when more than one
dataset is built. Serve two datasets as two entries. In a project's
`.mcp.json`, which holds absolute paths and is gitignored:

```json
{
  "mcpServers": {
    "connkg": {
      "command": "/path/to/connectome_kg/.venv/bin/connkg-mcp",
      "args": ["--root", "/path/to/connectome_kg", "--dataset", "fafb783"]
    }
  }
}
```

| Tool | Answers |
|---|---|
| `graph_stats`, `analyze_connectome` | counts; the Markdown report |
| `find_nodes`, `get_node`, `node_edges` | find a node by name; its metadata; its edges (neuropils, columns, nerves, ontology terms) |
| `neurons_of`, `type_partners` | resolve a spec to neurons; a type's partner types by synapses |
| `strongest_path`, `cone` | the strongest synaptic route; everything within N hops |
| `influence` | effective connectivity: the share of a target's input the source drives, per hop, signed |
| `neuroglancer_link` | a Neuroglancer URL showing up to seven specs as meshes, one color each |
| `query_connectome`, `pack_connectome` | semantic search (needs a build with the vector index) |
| `snapshot_list`, `snapshot_show`, `snapshot_diff` | saved metric snapshots |

Every argument is bounded and checked inside `ConnectomeKG`, so the CLI and the
server reject the same bad input with the same message: `k` 1-100, `hop` and
`hops` 0-5, `limit` and `max_nodes` 1-500, `min_syn` 1-10000, queries and ids at
most 500 characters, and a `label:` regex at most 100 characters that must
compile. The first `strongest_path` or `cone` call on FAFB v783 loads all 3.7 M
synapse edges; later calls reuse them.

---

## Documentation map

| Doc | What it covers |
|---|---|
| [docs/DOWNLOAD.md](https://github.com/Flux-Frontiers/connectome_kg/blob/main/docs/DOWNLOAD.md) | Getting FAFB v783 from Codex, file names, checksum drift, reproducible snapshots, build footprint |
| [CHANGELOG.md](https://github.com/Flux-Frontiers/connectome_kg/blob/main/CHANGELOG.md) | Release history |

---

## Data and licensing

The FlyWire data is free for non-commercial use under **CC BY-NC-SA 4.0**. A graph built from it is a derived work under the same license. Keep the download and the built graphs (`connectomes/*/.connectomekg/*.sqlite`) out of the repository (`.gitignore` already does) and out of anything commercial.

The Codex portal is synchronised with the live FlyWire database, so its files drift from the October 2024 published release. For a build that has to be reproducible, use the static no-login snapshots listed in [docs/DOWNLOAD.md](https://github.com/Flux-Frontiers/connectome_kg/blob/main/docs/DOWNLOAD.md) and record which one you used.

If you use FlyWire data, cite the data papers:

- Dorkenwald, S. et al. (2024). Neuronal wiring diagram of an adult brain. *Nature* 634, 124-138.
- Schlegel, P. et al. (2024). Whole-brain annotation and multi-connectome cell typing of *Drosophila*. *Nature* 634, 139-152.
- Eckstein, N. et al. (2024). Neurotransmitter classification from electron microscopy images at synaptic sites in *Drosophila melanogaster*. *Cell* 187, 2574-2594.

---

## Citation

If you use ConnectomeKG in research or a project, please cite it. The software is archived on Zenodo with each GitHub release. The DOI below, [10.5281/zenodo.22817369](https://doi.org/10.5281/zenodo.22817369), always resolves to the newest version.

**APA**

> Suchanek, E. G. (2026). *ConnectomeKG: Connectomes as Knowledge Graphs* (Version 0.5.0) [Software]. Flux-Frontiers. https://doi.org/10.5281/zenodo.22817369

**BibTeX**

```bibtex
@software{suchanek_connectome_kg,
  author    = {Suchanek, Eric G.},
  title     = {{ConnectomeKG}: Connectomes as Knowledge Graphs},
  version   = {0.5.0},
  year      = {2026},
  publisher = {Flux-Frontiers},
  doi       = {10.5281/zenodo.22817369},
  url       = {https://github.com/Flux-Frontiers/connectome_kg},
}
```

---

## License

[Elastic License 2.0](https://github.com/Flux-Frontiers/connectome_kg/blob/main/LICENSE) -- free for non-commercial and internal use; commercial redistribution or hosting requires a license from Flux-Frontiers. This covers the software only. The connectome data keeps its own license (see above).

---

## Support

- **Issues** -- [GitHub Issues](https://github.com/Flux-Frontiers/connectome_kg/issues)
- Sister projects: [PyCodeKG](https://github.com/Flux-Frontiers/pycode_kg), [DocKG](https://github.com/Flux-Frontiers/doc_kg), [MetaboKG](https://github.com/Flux-Frontiers/metabo_kg)
- Built on: kgmodule-utils, SQLite, sqlite-vec, pandas, SciPy and Click

---

*Built for neuroscientists, and the AI agents that work alongside them -- egs*
