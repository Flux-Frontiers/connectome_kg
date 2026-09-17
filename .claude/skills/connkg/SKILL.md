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
  .connectomekg/graph.sqlite, the connkg-mcp server and its tools, the synthetic
  fixture, or troubleshooting ConnectomeKG.
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
| a picture of a type's local circuit | `connkg --root . viz LC4 --view network\|partners -o out.html` (needs the `viz` extra; about a second on FAFB) |
| a real-geometry 3-D view of a circuit inside the whole brain | `connkg --root . quilt SPEC [SPEC...]` (Looking Glass quilt) or `connkg --root . viz3d SPEC [SPEC...]` (interactive viewer); needs the `viz3d` extra and reads skeletons from `fafb_v783/sk_lod1_783_healed/` -- see below |

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

## 3-D views

`connkg quilt SPEC [SPEC...]` and `connkg viz3d SPEC [SPEC...]` need the
`viz3d` extra (`pip install "connectome-kg[viz3d]"`) and draw two things at
once: every neuron's marked point as a dim whole-brain context cloud, plus
the given spec(s)' circuit at full brightness, drawn from **real traced
skeletons** read from `fafb_v783/sk_lod1_783_healed/<root_id>.swc`. Without
`--data-dir` (default `fafb_v783`) or a missing skeleton file, a neuron falls
back to a larger sphere at its marked point instead of a traced shape.

- **Do not start a real quilt render, cast, or the viewer yourself.** These
  are the maintainer's to run and watch, like a real build. Give the command;
  do not run `connkg quilt`, `connkg viz3d`, or anything with `--cast`.
- A circuit is capped at `MAX_SCENE_NEURONS` (500) neurons -- a hop-2 cone of
  a large type can resolve to thousands, so narrow the spec(s) rather than
  expecting the cap to be raised.
- `--skeleton-step` (default 4, capped at `MAX_SKELETON_STEP` = 50)
  simplifies a skeleton's point count for rendering; step 1 draws every
  traced point.
- Output lands under `renders/` (`stills/` for a `--preview` PNG, `quilts/`
  for the quilt itself), none of it committed.
- `--view flow` draws neuropil flow instead of a circuit: neuropils as spheres
  at the synapse-weighted centroid of their neurons, linked by arcs for the
  `--top` strongest directed pairs (default 100, capped at `MAX_FLOW_PAIRS` =
  500). Flow A -> B is summed over neurons: a neuron's output synapses in B,
  split by the share of its input synapses in A. SPEC(s) are optional and
  restrict the sum to their neurons, with no neuron cap. The largest v783
  flows are ME -> LO, LA -> ME, LO -> LOP and LO -> PVLP. Each arc bows to one
  side, so A -> B and B -> A do not overlap. The context cloud is thinned to
  every 10th neuron in this view, in one neutral grey.
- Colours are colour-blind safe, with no pastels. Neuropils and flow tubes
  take their brain region's colour (13 regions from
  `connectomekg.neuropils.NEUROPIL_REGION` over 8 Okabe-Ito colours, so
  neighbouring regions share one); cell types use the 7 non-black Okabe-Ito
  colours; the circuit view's cloud is its super-class colours muted toward
  the background. The key is "Reading the images" in `docs/rendering.md`;
  regenerate the doc images with `docs/scripts/render_images.py`.
- `--floor` stands the scene over a floor lit from above, with shadows, and
  defaults `--elevation` to 25 degrees (the floor is invisible from level).
  Pair it with `--tubes` in the circuit view: line skeletons cast almost no
  shadow. `connkg quilt --still` renders one flat 3840 x 2160 centre view to
  `renders/stills/` instead of a quilt; it cannot be combined with `--cast`.
- A quilt sweeps `--view-cone` 35 degrees by default and prints
  `depth_report` before rendering. The flow view with a floor measures about
  3.4 px of adjacent-view disparity at `--zoom 1.0`; above about 1.15 zoom
  crops the optic lobes. A quick flat still is fine to render yourself to
  check framing; full quilts and casts stay the maintainer's.

```bash
poetry run connkg --root . quilt DNp01 --preview renders/stills/dnp01.png
poetry run connkg --root . viz3d LC4 DNp01
poetry run connkg --root . quilt --view flow --top 60 --preview flow.png
poetry run connkg --root . quilt LPLC2 DNp01 --tubes --floor --still
poetry run connkg --root . quilt --view flow --floor --cast
poetry run connkg --root . viz3d --view flow LC4
```

## MCP server

`connkg-mcp --root <dir>` serves the graph over stdio (`--transport sse` for
SSE). When its tools are connected, prefer them to shelling out to the CLI:

| tool | use for |
|---|---|
| `graph_stats`, `analyze_connectome` | orientation, the Markdown report |
| `find_nodes(name, kind, limit)` | a node whose exact name or id is unknown |
| `get_node(node_id)`, `node_edges(node_id, rel, direction, limit)` | metadata; a neuron's neuropils, a column's neurons, a type's ontology terms |
| `neurons_of(spec)`, `type_partners(cell_type, direction, limit)` | resolve a spec; partner types by synapses |
| `strongest_path(source, target)`, `cone(spec, hops, min_syn, direction, limit)` | circuits |
| `query_connectome`, `pack_connectome` | concept search, only with a vector index |
| `snapshot_list`, `snapshot_show`, `snapshot_diff` | metric history |

Arguments outside their bounds come back as tool errors naming the range
(`k` 1-100, `hop`/`hops` 0-5, `limit`/`max_nodes` 1-500, `min_syn` 1-10000,
text at most 500 characters, a `label:` regex at most 100 and compilable);
fix the argument rather than retrying. Validation lives in `ConnectomeKG`
(`connectomekg/validation.py`), so the CLI and the Python API enforce the same
bounds. The first `strongest_path` or `cone` call in a server loads every
synapse edge; later calls reuse it.

## Not available yet

Do not claim or try these; they are planned, not built:

- KGRAG registration or federated queries across KGs
- other datasets (hemibrain, MANC, BANC) or a neuPrint reader
- activity simulation, and neuropil meshes (no mesh source in the download;
  a neuropil is visible only as the density of the 3-D context cloud)
- soma positions in the graph itself: neuron `x`/`y`/`z` metadata is a marked
  point, not necessarily the soma. `connkg quilt`/`viz3d` read each neuron's
  real soma from its skeleton file when one exists (falling back to the
  skeleton's root point otherwise); nothing has back-filled the soma into the
  graph's own `x`/`y`/`z` metadata
