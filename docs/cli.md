# Command reference

Every `connkg` command, with its options, defaults and one example. Output
shown here is from the built FAFB v783 graph. For what the queries mean, see
[Asking the graph a question](queries.md); for how the 3-D views are drawn,
see [Rendering the connectome in 3-D](rendering.md). This page is the place
to look up a flag.

## Global options

`connkg [OPTIONS] COMMAND [ARGS]...`

| option | meaning |
|---|---|
| `--root DIRECTORY` | Directory holding `connectomes/<dataset>/.connectomekg/`. Default `.` |
| `--dataset ID` | Dataset to work on, e.g. `fafb783`. Default: for `build`, `fafb783` (or `synthetic` with `--source synthetic`); otherwise the only built dataset under `--root` |
| `--version` | Print the version and exit |

Global options go before the command: `connkg --root . --dataset fafb783 stats`.
Most commands need only `--root`; `--dataset` matters once a root holds more
than one graph.

Some commands need an extra installed:

| extra | installs | needed by |
|---|---|---|
| `semantic` | the embedding model | `build` without `--no-index`, `query` |
| `viz` | pyvis, plotly | `viz` |
| `viz3d` | PyVista, PyQt5, pyvistaqt, quiltwright | `quilt`, `viz3d`, `path --render`, `cone --render` |

A command that needs a missing extra says so and names the `pip install` line.

## Specs

`path`, `cone`, `influence`, `link`, `quilt` and `viz3d` all take a SPEC to
mean "these neurons": a cell type name, a FlyWire root id, a neuron node id,
`label:<regex>` or `circuit:<name>`. Specs are case-sensitive. An answer form,
`path:FROM>TO` or `cone:SPEC`, goes anywhere a spec does and draws the query
instead. `connkg specs` prints the whole grammar with examples; the
[queries page](queries.md#a-spec-names-neurons) explains it.

## Getting the data

### `connkg files`

Prints each Codex portal label beside the file name it downloads as, and the
URLs of the October 2024 static archives for a reproducible build. No options.
See [Get the data](DOWNLOAD.md).

### `connkg verify`

Checks a Codex download against the v783 manifest: file names, sizes and
SHA-256 checksums.

| option | meaning |
|---|---|
| `--data-dir DIRECTORY` | The download. Required |
| `--no-checksums` | Skip the SHA-256 comparison, which is the slow part |

```bash
connkg verify --data-dir /path/to/fafb_v783
```

### `connkg fixture`

Writes a synthetic connectome in Codex format, shaped like v783 with planted
feeding, escape and grooming circuits, so everything downstream can be tried
without the download.

| option | meaning |
|---|---|
| `--out DIRECTORY` | Where to write the release. Required |
| `--n INTEGER` | Neurons. Default 1000; there is a minimum the fixture enforces |
| `--seed INTEGER` | Random seed. Default 1 |

```bash
connkg fixture --out /tmp/synth1k --n 1000 --seed 1
```

```text
wrote synthetic Codex release to /tmp/synth1k
```

## Building

### `connkg build`

Extracts the release into SQLite, then embeds the vector index. Every run,
successful or not, writes a provenance report to
`<root>/reports/build_<timestamp>.md`.

| option | meaning |
|---|---|
| `--data-dir DIRECTORY` | Codex release directory, for `--source codex` |
| `--source [codex\|synthetic]` | Read a Codex download or generate a synthetic release in memory. Default `codex` |
| `--n INTEGER` | Synthetic neuron count. Default 1000 |
| `--seed INTEGER` | Synthetic seed. Default 1 |
| `--min-syn INTEGER` | Drop connections below this synapse count at extraction. Default 1 |
| `--connections-file TEXT` | Connections table inside `--data-dir`. Default: auto-detect |
| `--embed-neurons` | Also embed neuron nodes. Off by default: there are 139k and their names carry little meaning |
| `--wipe` | Clear the existing graph first |
| `--no-index` | Skip the vector index. `connkg query` then reports it missing |

```bash
connkg --root . --dataset fafb783 build --data-dir /path/to/fafb_v783
connkg --root /tmp/kg --dataset synthetic1k build --data-dir /tmp/synth1k --no-index --wipe
```

These are the only extraction options in the CLI; the commands that read a
built graph take none of them. On FAFB v783 the build takes about three
minutes and 7.2 GB peak memory; the index adds 25 seconds. See
[the build footprint](DOWNLOAD.md).

### `connkg meshes`

Fetches the 78 neuropil surface meshes the 3-D views draw, about 1 MB, from
FlyWire's public bucket with no sign-in, and caches them beside the dataset's
graph. Run again to refresh. No options. FAFB v783 only. See
[Neuropil meshes](rendering.md#neuropil-meshes).

### `connkg skeletons`

Reads every neuron's `.swc` file once and writes two things: a simplified
skeleton cache beside the graph, which the circuit view then draws from
instead of the 31 GB download, and each neuron's real soma into its node
metadata, which turns the whole-brain cloud into cell bodies.

| option | meaning |
|---|---|
| `--data-dir DIRECTORY` | Root of the skeleton download, e.g. `fafb_v783`. Required |
| `--step INTEGER` | Keep every Nth skeleton point, 1 to 50. Default 4, the circuit view's own default |
| `-j, --jobs INTEGER` | Worker processes, 1 to 64. Default 1 |
| `--no-somas` | Write the cache without touching the graph |

```bash
connkg --root . --dataset fafb783 skeletons --data-dir /path/to/fafb_v783 -j 12
```

Parsing SWC holds the GIL, so the default pegs one core: 19m 30s on v783
against 2m 39s at `-j 12`. Pass your core count. See
[The skeleton cache](rendering.md#the-skeleton-cache).

### `connkg datasets`

Lists the connectomes built under `--root`, one graph each. No options.

```text
dataset              graph  name
fafb783             2.3 GB  FlyWire FAFB v783
```

## Describing a build

### `connkg stats`

What the graph holds: the dataset and its figures, then nodes and edges by
kind and relation. No options.

```text
dataset_id: fafb783
dataset_version: 783
n_neurons: 139255
n_cell_types: 8772
n_neuropils: 79
n_pairs: 3732460
n_synapses: 50666648
total_nodes: 157698
total_edges: 5072285
node_counts: {'cell_type': 8772, 'column': 1581, ..., 'neuron': 139255, 'neuropil': 79, ...}
edge_counts: {..., 'SYNAPSES_TO': 3732460, 'TYPE_SYNAPSES_TO': 507287, ...}
snapshot_count: 7
vector_backend: sqlite-vec
db_path: /Users/egs/repos/connectome_kg/connectomes/fafb783/.connectomekg/graph.sqlite
```

`n_pairs` is the `SYNAPSES_TO` edge count and `n_synapses` the synapses those
pairs carry, as the build recorded them on the dataset node. The `graph_stats`
MCP tool returns the same figures.

### `connkg analyze`

A Markdown report of the graph: counts, hub neurons, the strongest
type-to-type links, neuropil coverage, and what fraction of neurons carry a
cell type, a sign and a soma. No options; pipe it to a file.

```bash
connkg --root . analyze > analysis.md
```

### `connkg snapshot`

Point-in-time metric snapshots of the built graph, kept under the dataset's
`.connectomekg/`. Five subcommands.

| subcommand | does |
|---|---|
| `save [VERSION]` | Capture the graph's metrics, keyed on VERSION. Omitted, the key is a UTC timestamp |
| `list` | Snapshots, newest first. `--limit N` for the newest N, `--json` for the manifest entries |
| `show [KEY]` | One snapshot as JSON. Default: the latest |
| `diff KEY_A KEY_B` | B minus A: totals, and the node and edge counts that changed |
| `prune` | Remove snapshots that add no new metrics, broken entries and orphaned files. `--dry-run` lists them without deleting |

`save` takes two options: `--subject TEXT`, what was measured (default
`corpus:<dataset id>`, so `corpus:fafb783`), and `--force`, which writes an
entry even when the metrics are unchanged. At release time pass the version
explicitly with `--force`, so an unchanged graph does not replace the previous
release's entry; the git tree hash is recorded as provenance but is never the
key.

```text
$ connkg --root . snapshot list --limit 3
key                                subject            version       nodes       edges
0.5.0                              corpus:fafb783     0.5.0       157,698   5,072,285
0.4.0                              corpus:fafb783     0.4.0       157,698   5,072,285
0.3.2                              corpus:fafb783     0.3.2       157,698   5,072,285
```

## Asking questions

### `connkg specs`

Prints every form a SPEC and an answer can take, with examples, and the named
circuits. No options. The same list feeds the queries page and the viewer's Explore
tab.

### `connkg query`

Semantic search over the human vocabulary in the graph, cell types,
neuropils, labels and taxa, then expansion through the graph. Needs the
vector index, so the `semantic` extra and a build without `--no-index`.

| option | meaning |
|---|---|
| `Q` | The query text. Required |
| `--k INTEGER` | Seeds, 1 to 100. Default 8 |
| `--hop INTEGER` | Graph expansion hops from the seeds, 0 to 5. Default 1; 0 is pure semantic lookup |

```text
$ connkg --root . query "giant fiber escape" --k 3 --hop 0
QUERY: giant fiber escape
Seeds: 3 | Expanded: 3 | Returned: 3 | hop=0
label   giant fiber/giant fibre/GF/GFN  [connectome:fafb783:l:93ace5d07694]
label   AMMC-A1/giant commissural interneuron/GCI  [connectome:fafb783:l:1641f5bfc8b6]
...
```

See [`connkg query`](queries.md#connkg-query-search-by-meaning).

### `connkg path`

The strongest signed synaptic path between two specs. Strength is the product
of each hop's share of the postsynaptic neuron's input.

| option | meaning |
|---|---|
| `--from SPEC` | Source. Required |
| `--to SPEC` | Target. Required |
| `--render` | Also draw the answer as a still under `renders/stills/`: each hop's neuron as a traced skeleton in its own color, dark to bright along the path, on a floor. Needs the `viz3d` extra |
| `--data-dir DIRECTORY` | Skeleton download root, for neurons the cache lacks when rendering. Default `fafb_v783` |

```text
$ connkg --root . path --from LC4 --to DNp01
strength 0.005209, net sign +1
  LC4/right/720575940612380723
  -> DNp01/right/720575940632499757  (56 syn, 0.5% of input, sign +1)
```

Exit status 1 when there is no path. See
[`connkg path`](queries.md#connkg-path-the-strongest-route).

### `connkg cone`

Everything reachable from a spec, downstream or upstream, hop by hop.

| option | meaning |
|---|---|
| `SPEC` | The seed. Required |
| `--hops INTEGER` | 0 to 5. Default 1 |
| `--direction [down\|up]` | Follow outputs or inputs. Default `down` |
| `--min-syn INTEGER` | Ignore connections below this synapse count. Default 1 |
| `--limit INTEGER` | Neurons listed per hop. Default 20 |
| `--render` | Also draw the cone as shells, dark at the seed and bright outward, under `renders/stills/`. Needs the `viz3d` extra |
| `--data-dir DIRECTORY` | Skeleton download root, for rendering. Default `fafb_v783` |

```text
$ connkg --root . cone LC4 --min-syn 200 --limit 3
hop 0: 104 neurons
  LC4/left/720575940605598892
  LC4/left/720575940610522009
  LC4/left/720575940611134833
```

`--min-syn` is what makes a multi-hop cone usable: `cone LC4 --hops 2` is
19,866 neurons at the default and 104 at 200. The first `path` or `cone` in a
process loads every synapse edge and takes a while; later calls reuse it. See
[`connkg cone`](queries.md#connkg-cone-everything-reachable).

### `connkg influence`

Effective connectivity: how much one population drives another, as a share of
the receiving neuron's input synapses averaged over those neurons, summed over
every route of the given length. Signed, so a negative value is net
inhibition.

| option | meaning |
|---|---|
| `--from SPEC` | Source. Required |
| `--to SPEC` | Target. Omit it to rank cell types by influence instead |
| `--hops INTEGER` | Route length, 1 to 5. Default 3 |
| `--unsigned` | Treat every synapse as excitatory |
| `--limit INTEGER` | Cell types listed per hop, 1 to 500. Default 20 |

```text
$ connkg --root . influence --from LC4 --to DNp01 --hops 1
influence of LC4 (104 neurons), signed, as a share of the receiving neuron's input

onto DNp01 (2 neurons), averaged:
  hop 1: +0.1469
  total: +0.1469

strongest cell types at hop 1:
  +0.5916  PVLP024
  +0.5593  DNp04
  ...
```

See [`connkg influence`](queries.md#connkg-influence-how-much-one-population-drives-another).

### `connkg link`

A Neuroglancer URL showing each spec's neurons as meshes, one color per spec,
over a translucent brain. No login. FAFB v783 only.

| option | meaning |
|---|---|
| `SPECS...` | One or more specs. Required |
| `--limit INTEGER` | Neurons shown per spec, 1 to 500. Default 200 |

```text
$ connkg --root . link LC4 DNp01 --limit 5
#E69F00  LC4: 104 neurons, first 5 shown
#56B4E9  DNp01: 2 neurons
https://neuroglancer-demo.appspot.com/#!%7B%22dimensions%22...
```

The two legend lines go to stderr and the URL to stdout, so `connkg link LC4 |
pbcopy` copies only the URL. See
[`connkg link`](queries.md#connkg-link-open-the-neurons-in-a-browser).

## Drawing

### `connkg viz`

A cell type's strongest partner types as a self-contained HTML file, with the
rendering library inlined so it opens from the filesystem and can be sent to
someone without the data or Python. Needs the `viz` extra.

| option | meaning |
|---|---|
| `CELL_TYPE` | The type. Required |
| `--view [network\|partners]` | `network` is an interactive partner graph; `partners` a diverging bar chart. Default `network` |
| `--limit INTEGER` | Partner types per direction, 1 to 500. Default 15; a graph is unreadable well below the maximum |
| `-o, --output FILE` | Where to write. Default `<cell type>_<view>.html` |

```bash
connkg --root . viz LC4 --view partners -o lc4_partners.html
```

### `connkg quilt`

Renders a circuit, or the signal flow between neuropils, inside the whole
brain as a Looking Glass quilt, or as one flat image with `--still`. Needs the
`viz3d` extra. [Rendering the connectome in 3-D](rendering.md) explains every
view and option at length; this is the list.

| option | meaning |
|---|---|
| `SPECS...` | Circuit view: the neurons drawn, capped at the scene limit. Flow view: optional; restricts the flow to their neurons |
| `--view [circuit\|flow]` | Default `circuit` |
| `--data-dir DIRECTORY` | Skeleton download root, for neurons the cache lacks. Default `fafb_v783` |
| `--color-by [super_class\|sign]` | Color the context cloud by super class or transmitter sign. Circuit view only. Default `super_class` |
| `--skeleton-step INTEGER` | Skeleton simplification stride, 1 to 50; 1 draws every traced point. Default scales with the neuron count |
| `--tubes` | Draw skeletons as tubes rather than lines |
| `--top INTEGER` | Flow view: strongest neuropil pairs drawn, 1 to 500. Default 100 |
| `--neuropils / --no-neuropils` | Draw the neuropil surfaces, once `connkg meshes` has fetched them. Default on |
| `--cloud / --no-cloud` | Draw the whole-brain context cloud. Default: on with `--floor`, else only when the surfaces are not drawn |
| `--floor` | Stand the scene over a lit floor with shadows; tilts the camera down |
| `--elevation FLOAT` | Degrees to tilt the camera down from the front view, -80 to 80. Default 25 with `--floor`, else 0 |
| `--background TEXT` | Scene background: `gray`, `charcoal`, `light`, or a `#RRGGBB` color. Default `gray` |
| `--preset TEXT` | Looking Glass quilt preset. Default `16-landscape` |
| `--view-cone FLOAT` | Degrees the quilt cameras sweep, 1 to 90. Default 35 |
| `--fov FLOAT` | Per-view vertical field of view, degrees. Default 14 |
| `--zoom FLOAT` | Camera dolly after framing. Default 1.0 |
| `-o, --out DIRECTORY` | Output directory. Default `renders/quilts`, or `renders/stills` with `--still` |
| `--still` | One flat center view at the preset's aspect, 3840x2160 for `16-landscape`, instead of a quilt |
| `--preview FILE` | Also write one plain PNG of the framed view |
| `--cast` | Send the finished quilt to Looking Glass Bridge |

```bash
connkg --root . quilt LPLC2 DNp01 --tubes --cloud            # the escape circuit, as a quilt
connkg --root . quilt --view flow --floor --cloud --still    # whole-brain flow, one 4K image
connkg --root . quilt circuit:compass --floor --cast         # straight to the panel
```

See [Render a view](rendering.md#render-a-view) and
[Quilts and Looking Glass displays](rendering.md#quilts-and-looking-glass-displays).

### `connkg viz3d`

Opens the same scene in an interactive viewer: orbit, zoom and pan with the
mouse, point at a neuron and press P to identify it, re-draw any spec or
answer from the Show box, and cast to a Looking Glass. Needs the `viz3d`
extra.

It takes `quilt`'s scene options, `SPECS...`, `--view`, `--data-dir`,
`--color-by`, `--skeleton-step`, `--tubes`, `--top`, `--neuropils`,
`--cloud`, `--floor`, `--elevation`, `--background` and `--preset`, with the same meanings, and
two of its own:

| option | meaning |
|---|---|
| `--width INTEGER` | Window width in pixels. Default 1400 |
| `--height INTEGER` | Window height in pixels. Default 900 |

It has no output options: the window is the output. **Save scene** in the
viewer writes a 4K still or a quilt of the current view, and Cast to Looking
Glass sends the quilt; both use `--preset`.

```bash
connkg --root . viz3d                            # circuit:compass, then explore
connkg --root . viz3d LC4 DNp01
connkg --root . viz3d --view flow
connkg --root . viz3d path:LPLC2>DNp01 --floor
connkg --root . --dataset banc888 viz3d --view flow --background charcoal
```

The rail's **Dataset** box switches between the datasets built under
`--root`, and its **View** box between the circuit and flow views, without
restarting. `--dataset` and `--view` only choose where the viewer opens.

With no SPEC the viewer opens on `circuit:compass` inside the whole brain, so
there is a circuit on screen to orbit and pick at from the start. Any SPEC
replaces it, and the Show box redraws without restarting. On a connectome
whose cell types the circuit does not name -- the synthetic fixture, say --
the default resolves to nothing and the viewer opens on the brain alone.
`connkg quilt` still requires a SPEC for `--view circuit`, since it renders a
file and exits.

See [Using the viewer](rendering.md#using-the-viewer).

## The MCP server

### `connkg-mcp`

Serves the graph to an AI agent over the Model Context Protocol: the same
queries as the CLI, as tools. A separate entry point, not a `connkg`
subcommand.

| option | meaning |
|---|---|
| `--root ROOT` | Directory holding `connectomes/<dataset>/`. `--repo` is accepted as an alias for fleet configs |
| `--dataset DATASET` | Dataset id. Default: the only built dataset under `--root` |
| `--db DB` | Graph path. Default `<root>/connectomes/<dataset>/.connectomekg/graph.sqlite` |
| `--transport [stdio\|sse]` | Default `stdio`, which is what an `.mcp.json` entry wants |

```json
{
  "mcpServers": {
    "connkg": {
      "command": "connkg-mcp",
      "args": ["--root", "/path/to/connectome_kg", "--dataset", "fafb783"]
    }
  }
}
```

Put the entry in a project's `.mcp.json`, which holds absolute paths and is
gitignored. If `connkg-mcp` is not on the client's `PATH`, give the full path,
for example `/path/to/connectome_kg/.venv/bin/connkg-mcp`. To serve two
datasets, add two entries.

| tool | answers |
|---|---|
| `graph_stats`, `analyze_connectome` | Counts; the Markdown report |
| `find_nodes`, `get_node`, `node_edges` | Find a node by name; its metadata; its edges (neuropils, columns, nerves, ontology terms) |
| `neurons_of`, `type_partners` | Resolve a spec to neurons; a type's partner types by synapses |
| `strongest_path`, `cone` | The strongest synaptic route; everything within N hops |
| `influence` | Effective connectivity: the share of a target's input the source drives, per hop, signed |
| `neuroglancer_link` | A Neuroglancer URL showing up to seven specs as meshes, one color each |
| `query_connectome`, `pack_connectome` | Semantic search. Needs a build with the vector index |
| `snapshot_list`, `snapshot_show`, `snapshot_diff` | Saved metric snapshots |

Every argument is bounded and checked inside `ConnectomeKG`, so the CLI and
the server reject the same bad input with the same message:

| argument | allowed |
|---|---|
| `k` | 1 to 100 |
| `hop`, `hops` | 0 to 5 (1 to 5 for `influence`) |
| `limit`, `max_nodes` | 1 to 500 |
| `min_syn` | 1 to 10000 |
| queries and ids | at most 500 characters |
| `label:` pattern | at most 100 characters, and it must compile as a regular expression |

The first `strongest_path`, `cone` or `influence` call on FAFB v783 loads all
3.7 million synapse edges; later calls reuse them.
