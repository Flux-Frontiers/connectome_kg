---
name: connkg
description: >
  ConnectomeKG: the connkg CLI, connectome_kg repo and connectomekg package, a
  knowledge graph of the FlyWire FAFB v783 Drosophila brain (neurons, cell
  types, synaptic pairs, neuropils, taxonomy, hemilineages, nerves, visual
  families and columns, connectivity tags, community labels, FBbt ontology
  terms). Use when the user asks about fly brain wiring or FlyWire data: a
  type's partner types, the strongest synaptic path between neurons or types
  (e.g. LPLC2 to DNp01), downstream or upstream cones, what innervates a
  neuropil or sits in a visual column, neurons in a nerve, a type's transmitter,
  sign, ontology term or labels. Also use for the connkg CLI (build, verify,
  files, fixture, stats, analyze, query, path, cone, snapshot), downloading and
  checking the Codex files, build reports, snapshots, SQL against
  .connectomekg/graph.sqlite, the synthetic fixture, or troubleshooting
  ConnectomeKG.
---

# ConnectomeKG (connkg)

> **Answer fly-connectome questions from the built graph first**, before the
> Codex website, web search, or loading the CSVs into pandas. The graph already
> holds the FlyWire FAFB v783 brain with its annotations joined, and a path or
> partner question is one command or one indexed SQL query.

ConnectomeKG is the connectome member of the KGRAG fleet (kgmodule-utils
`KGModule`). Every `SYNAPSES_TO` edge is a counted synapse pair seen in electron
microscopy; the semantic layer is the human vocabulary on top of it.

- Repo: `~/repos/connectome_kg` (branch `develop` for ongoing work)
- Store: `.connectomekg/graph.sqlite` (about 2.1 GB for FAFB v783)
- Download: `fafb_v783/` in the repo root, gitignored
- Download guide: `docs/DOWNLOAD.md`

## Running it

From the repo root, `poetry run connkg ...`. With nothing installed:
`PYTHONPATH=src python -m connectomekg ...`.

**`--root` goes before the command**: `connkg --root . path ...`, not
`connkg path --root .`. It names the directory that owns `.connectomekg/`.

Start by confirming a graph exists and which dataset it holds:

```bash
poetry run connkg --root . stats
```

`'neuron': 139255` in `node_counts` means the real brain. A few hundred to a
few thousand neurons means a synthetic fixture was built there instead.

## Answering questions

| question | use |
|---|---|
| strongest route from A to B | `connkg --root . path --from LC4 --to DNp01` |
| everything downstream or upstream | `connkg --root . cone LC4 --hops 2 --min-syn 10 --direction down` |
| a type's partner types, types in a neuropil, column, family or nerve, ontology terms, who labelled a neuron | SQL: read [references/sql-recipes.md](references/sql-recipes.md) |
| fuzzy concept ("giant fibre escape") | `connkg query`, only if the vector index exists; see below |
| overall counts, hubs, coverage | `connkg --root . stats`, `connkg --root . analyze` |

**Specs** (the `--from`, `--to` and `SPEC` arguments) accept a cell type name
(exact, case-sensitive: `LC4`, `KCg-m`, `DA1_lPN`), a root id
(`720575940622838154`), a neuron node id, or `label:<regex>` matched against
community label text. A type spec expands to all its neurons.

**Path strength** follows the connectome-interpreter convention: an edge's
weight is the fraction of the postsynaptic neuron's input synapses it carries,
and a path's strength is the product along it. The output lists each hop's
synapses, input fraction and transmitter sign, plus the net sign. It is the
strongest path by input fraction, not a signed or simulated result.

**Each `path` or `cone` call reloads all 3.7 M synapse edges into scipy.** For
more than a couple of queries, use one Python session instead:

```python
from connectomekg import ConnectomeKG

kg = ConnectomeKG(".")                      # repo root that owns .connectomekg/
res = kg.strongest_path("LPLC2", "DNp01")   # PathResult | None: .strength, .net_sign, .hops
reach = kg.cone("LC4", hops=2, min_syn=10)  # {neuron node id: hop}
kg.neurons_of("label:giant fib")            # resolve a spec to neuron ids
kg.describe("connectome:fafb783:t:LC4")     # node dict with decoded metadata
kg.close()
```

**Semantic search** (`connkg query`, `kg.query`, `kg.pack`) needs
`.connectomekg/vectors.sqlite`, which exists only after a build without
`--no-index`, with the `semantic` extra installed. The reference build uses
`--no-index`, so check for the file first. Without it, search docstrings and
labels in SQL (`lower(docstring) LIKE '%giant fib%'` on `cell_type` and `label`
nodes finds DNp01). Community labels are the only free text in the graph:
a concept nobody wrote into a label, such as "looming" on FAFB, is found by
neither route, so fall back to known type names.

**Names differ between the fixture and the real brain.** `MN9`, `aDN1`,
`GRN_sugar`, `SEZ_IN1` and `JO-CE` are planted synthetic circuits. On FAFB, use
real Codex names (`LC4` 104 neurons, `LPLC2` 210, `DNp01` 2, `KCg-m`, `PAM01`,
`T4a`, `Mi1`). When unsure, look the name up:
`SELECT name FROM nodes WHERE kind='cell_type' AND name LIKE 'DNp%';`

Open the store with plain `sqlite3 .connectomekg/graph.sqlite` and only run
SELECTs, never during a build. `sqlite3 -readonly` fails with "unable to open
database file" whenever no other connection is open: the store is in WAL mode
and a read-only open cannot create the `-shm` file.

For node ids, metadata fields, relations, edge evidence, the sign convention
and the expected v783 counts, read
[references/graph-model.md](references/graph-model.md).

## Getting and checking the data

The Codex portal needs a Google sign-in, so downloading is manual. Follow
`docs/DOWNLOAD.md`. `connkg files` maps the portal's display labels to file
names; `connkg verify --data-dir fafb_v783` checks the directory.

- **Safari saves gzip under `.csv` or `.csv.csv` names without
  decompressing.** Confirm with `file`, then rename to `<name>.csv.gz`. Never
  gunzip: the reader reads `.csv.gz` directly, and decompressing loses the
  bytes the manifest checksums.
- **The portal is live.** `verify` reports checksum drift and still says
  "ready to build". Judge a download by the counts (139,255 neurons, 3,732,460
  pairs), not by digests.
- Required: `neurons`, `classification`, `connections_princeton`. Optional
  but wanted: `consolidated_cell_types` (the only source of cell types on
  current exports), `coordinates`, `labels`, `cell_stats`,
  `visual_neuron_types`, `column_assignment`, `connectivity_tags`,
  `processed_labels`.

## Building

```bash
poetry run connkg --root . build --data-dir fafb_v783 --dataset-id fafb783 --no-index --wipe
```

- **Do not start a real FAFB build yourself.** It takes about 4 minutes and
  2.1 GB (keep 4 GB free for the write-ahead log). Give the maintainer the
  command and let them run and watch it; read the output they paste back.
  Fixture builds and the test suite are fine to run.
- Progress goes to stderr: each extraction stage, then a count every 250,000
  pairs, then "writing to SQLite", after which the write is silent.
- Use `--wipe` after an interrupted build, or the new graph lands on the
  partial one.
- For tests and experiments without the download:
  `connkg fixture --out /tmp/synth --n 1000 --seed 1`, then build with
  `--data-dir /tmp/synth --dataset-id synthetic` into a scratch `--root`.

## Provenance

- **Build reports.** Every build, including a failed one, writes
  `reports/build_<UTC timestamp>.md`: versions and git commit, options, each
  input's SHA-256 against the manifest, time per stage, counts, database size,
  peak resident memory. Reports are gitignored; `git add -f` one worth keeping.
  Read the newest report before guessing why a build was slow or wrong.
- **Snapshots** follow the fleet contract. `connkg snapshot save [OPTIONS]
  VERSION` keys on VERSION, or on a UTC timestamp when omitted, and never on
  the git tree hash, which is recorded only as provenance. The subject is
  `corpus:fafb783` (the graph measures a connectome release, not this
  package's code). At release, reinstall first and pass `--force`, as the
  repo's `.claude/skills/release/SKILL.md` describes.
  `.connectomekg/snapshots/` is tracked in git.

## Not available yet

Do not claim or try these; they are planned, not built:

- an MCP server (no `connkg-mcp`, no MCP tools)
- KGRAG registration or federated queries across KGs
- other datasets (hemibrain, MANC, BANC) or a neuPrint reader
- activity simulation, and soma positions or morphology from the skeletons
  (neuron `x`/`y`/`z` is a marked point, not necessarily the soma)
