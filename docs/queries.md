# Asking the graph a question

Five commands answer questions about wiring, and they all take the same
grammar for naming neurons. This page covers that grammar, the four query
commands built on it, and the three that describe a build rather than query it.

`connkg specs` prints the grammar at any time, and every command takes
`--help`.

```bash
connkg --root . --dataset fafb783 specs
```

## A SPEC names neurons

| spec | means |
|---|---|
| `LC4` | every neuron of a cell type, by exact name (case-sensitive) |
| `DNp01` | the two giant fiber descending neurons |
| `720575940622838154` | one neuron, by FlyWire root id |
| `connectome:fafb783:n:720575940622838154` | the same neuron, by node id |
| `label:giant fib` | every neuron a community label matches, as a regex |
| `label:^LPLC2_` | anchored, so it matches the label's start |

Cell type names are case-sensitive, so `lc4` finds nothing. A `label:` pattern
is a regular expression matched against FlyWire's community labels, which are
free text written by annotators: the v783 label for the giant fiber reads
`giant fiber/giant fibre/GF/GFN`, which is why the short pattern `label:giant
fib` is the reliable one.

## An ANSWER names a query

An answer goes anywhere a spec goes, and stands for the neurons a query
returns rather than a named set:

| answer | means |
|---|---|
| `path:LPLC2>DNp01` | the strongest signed path, hop by hop |
| `path:LC4>DNp01` | looming detectors to the giant fiber: the escape circuit |
| `path:label:giant fib>DNp04` | a path may start from a label |
| `cone:LC4` | everything one hop downstream: 489 neurons |
| `cone:DNp01<1` | one hop upstream: 663 |
| `cone:label:giant fib<1` | a spec may itself carry a prefix |

The arrow follows the signal, which is why upstream is `<` and downstream is
`>`. `cone:SPEC` with no arrow is one hop downstream.

Because an answer is just a string, it reaches the 3-D views too:

```bash
connkg viz3d "path:LPLC2>DNp01"     # opens on the answer, hop-colored
connkg quilt "cone:DNp01<1"
```

An answer holding more neurons than one scene may draw is refused with the
count and the remedy rather than drawn badly. Narrow it with `--min-syn`.

## `connkg path` -- the strongest route

```bash
connkg --root . --dataset fafb783 path --from LC4 --to DNp01
```

```text
strength 0.005209, net sign +1
  LC4/right/720575940612380723
  -> DNp01/right/720575940632499757  (56 syn, 0.5% of input, sign +1)
```

An edge's weight is **the fraction of the postsynaptic neuron's input synapses
that it carries**, not its raw synapse count. This is the
connectome-interpreter convention, and it is the reason a 40-synapse input
that is half of a small neuron's drive outranks a 40-synapse input that is 1%
of a large one's.

A path's strength is the product of those fractions along it, so the strongest
path is the Dijkstra shortest path on `-log(fraction)`. Each hop reports its
synapse count, its fraction and its transmitter sign, and the path reports a
net sign: the product of the hop signs, so two inhibitory hops make an
excitatory route.

Add `--render` to draw it as a still image, each hop in its own color running
dark to bright along the route. That needs the `viz3d` extra.

## `connkg cone` -- everything reachable

```bash
connkg --root . --dataset fafb783 cone LC4 --hops 1
```

```text
hop 0: 104 neurons
  LC4/left/720575940605598892
  LC4/left/720575940610522009
  ...
```

`--direction up` walks upstream instead. `--min-syn N` drops connections below
`N` synapses, which is what keeps a multi-hop cone to a usable size: `cone:LC4`
two hops out is 19,866 neurons at the default threshold and 104 at
`--min-syn 200`. `--render` draws the cone as shells, dark at the seed and
bright outward.

## `connkg influence` -- how much one population drives another

A path says a route exists and a cone says what is reachable. Neither says how
much of the target's drive the source actually accounts for, and neither
notices that two routes of opposite sign cancel. That is what this measures.

```bash
connkg --root . --dataset fafb783 influence --from LC4 --to DNp01
```

```text
influence of LC4 (104 neurons), signed, as a share of the receiving neuron's input

onto DNp01 (2 neurons), averaged:
  hop 1: +0.1469
  hop 2: -0.0020
  hop 3: -0.0019
  total: +0.1430

strongest cell types at hop 1:
  +0.5916  PVLP024
  +0.5593  DNp04
  +0.2659  CB2917
  ...
```

The number is a share of the receiving neuron's input synapses, averaged over
the receiving neurons, so `+0.1469` reads as "the average DNp01 gets about 15%
of its input from LC4". A negative value is net inhibition.

Omit `--to` and it ranks the cell types a population drives most, which is the
form to reach for when the question is "what does this do?" rather than "does
it reach that?". `--limit` sets how many types are listed per hop (default 20),
`--hops` how far to propagate (default 3, maximum 5).

### Checking the number means something

Unsigned and at one hop, influence is *by construction* the source's share of
the target's input synapses. That gives an identity to test it against:

```bash
connkg --root . --dataset fafb783 influence --from LC4 --to DNp01 --hops 1 --unsigned
```

```text
  hop 1: +0.1482
```

Counted straight out of the edge table, LC4 makes 3,080 synapses onto the two
DNp01 neurons:

| DNp01 neuron | from LC4 | total input | share |
|---|---:|---:|---:|
| `...622838154` | 1,401 | 9,999 | 0.1401 |
| `...632499757` | 1,679 | 10,750 | 0.1562 |

whose mean is 0.1482, the number the command printed. Signed, the same pair
reads `+0.1469`; the difference is one LC4 neuron of 104 whose transmitter is
unresolved, which therefore carries nothing.

`--unsigned` treats every synapse as excitatory. Use it when the transmitter
predictions are the thing in doubt, and note that 85.9% of v783 edges carry a
sign at all.

### Why it is fast

The connectivity matrix is 139,255 square. Raising it to a power would be
1.5e10 dense entries, so instead a sparse vector is propagated one hop at a
time over the 3.7M edges: three hops take about 0.02 seconds once the matrix
is loaded.

The first `path`, `cone` or `influence` call in a fresh checkout loads every
synapse edge and caches the matrix beside the graph, about 14 MB. That first
call takes a few seconds; later ones reuse it. The cache is keyed on the edge
table's shape and the graph file, so a rebuilt graph is never answered from a
stale one.

## `connkg query` -- search by meaning

```bash
connkg --root . --dataset fafb783 query "looming sensitive visual projection neurons"
```

A semantic search over cell types, neuropils and labels, expanded through the
graph. It needs the vector index, which `connkg build` writes by default
(16,861 vectors on v783, about 25 seconds and 29 MB) and `--no-index` skips.
Without an index the command says so rather than returning nothing.

This is the only query that is *about* text. Everything else on this page is
exact.

## `connkg link` -- open the neurons in a browser

```bash
connkg --root . --dataset fafb783 link LC4 DNp01
```

Prints a Neuroglancer URL that opens those neurons as FlyWire meshes, one
color per spec, with no login. The URL is the only thing on stdout, so it
pipes:

```bash
connkg link LC4 | pbcopy
```

FAFB v783 only, since the URL points at FlyWire's public segmentation.

## Describing a build

Three commands report on the graph rather than querying it.

| command | answers |
|---|---|
| `connkg stats` | how many nodes and edges, broken down by kind and relation |
| `connkg analyze` | a Markdown report: hubs, the strongest type-to-type links, neuropil coverage, and what fraction of neurons carry a cell type, a sign, a soma |
| `connkg datasets` | which connectomes are built under `--root`, one graph each |

```bash
connkg --root . --dataset fafb783 stats
```

```text
total_nodes: 157698
total_edges: 5072285
node_counts: {'cell_type': 8772, ..., 'neuron': 139255, ...}
edge_counts: {..., 'SYNAPSES_TO': 3732460, ...}
```

`connkg snapshot save [VERSION]` records those metrics as a point in time, and
`connkg snapshot diff A B` compares two. The coverage figures are what tell a
graph that knows where its cell bodies are from one that does not: after
`connkg skeletons` has run, `coverage.soma` on v783 is 0.967.

## Where the same questions have other answers

- [Rendering the connectome in 3-D](rendering.md) draws any of these, and the
  viewer takes the same specs and answers interactively.
- `connkg-mcp` serves `strongest_path`, `cone`, `influence`, `type_partners`,
  `neuroglancer_link` and the rest to an AI agent over MCP. The
  [README](https://github.com/Flux-Frontiers/connectome_kg#as-an-mcp-server)
  has the client configuration.
- From Python, `ConnectomeKG.strongest_path`, `.cone`, `.influence` and
  `.neurons_of` take the same specs.
