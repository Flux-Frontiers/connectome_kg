# Release Notes -- v0.4.0

> Released: 2026-09-19

The brain gets its anatomy. This release gives every neuron its cell body, draws the neuropil surfaces around a circuit, links any query to Neuroglancer, and caches the two things a query used to pay for on every run.

## What changed

**Every neuron knows where its cell body is.** A neuron's `x`/`y`/`z` has always been FlyWire's marked point, an anchor that can sit tens of microns from the soma. `connkg skeletons --data-dir fafb_v783 -j 12` reads the skeleton download once and writes each neuron's real soma into the graph as `soma_x`, `soma_y`, `soma_z` and `has_soma`, alongside the marked point rather than over it. On FAFB v783 that is 134,675 of 139,255 neurons, 96.7%; the remaining 3.3% have no soma row in their skeleton file and fall back to its root point. The whole-brain context cloud in the 3-D views draws somas from then on, and so can any query.

**The same pass caches the skeletons.** It writes `.connectomekg/skeletons/`, holding every neuron's skeleton simplified at `--step` (4 by default): 212,351,918 points in 2.5 GB, against the download's 31 GB. The 3-D circuit view reads it in place of the download, so rendering a circuit no longer needs the 31 GB at all, and a cached render is faster than parsing SWC.

**That pass reads in parallel.** Parsing SWC is pure Python and holds the GIL, so it pegged one core and left the rest idle. `-j N` splits the neurons into contiguous ranges, one worker process and one cache shard each. On an 18-core laptop the FAFB v783 pass goes from 19 minutes 30 seconds to 2 minutes 39 seconds, a 7.4x speed-up, for a cache verified identical to the single-core one.

**Neuropil surfaces in the 3-D views.** `connkg meshes` fetches the 78 FAFB v783 neuropil surfaces from FlyWire's public bucket, about 1 MB with no sign-in. `connkg quilt` and `connkg viz3d` then draw them: pale shells in the circuit view, region-tinted in the flow view. These are the surfaces of the volumes FlyWire assigned v783 synapses to neuropils with, so a mesh encloses what the graph's `IN_NEUROPIL` edges count. With the surfaces drawn the context cloud is redundant and turns off; `--cloud` draws both.

**Neuroglancer links for any spec.** `connkg link LC4 DNp01` prints a URL that opens those neurons as meshes in the public Neuroglancer, with no login and one colour per spec. The same link comes from the `neuroglancer_link` MCP tool and from `ConnectomeKG.neuroglancer_link()`. The URL is the only thing on stdout, so `connkg link LC4 | pbcopy` works.

**Path and cone queries stop reloading the brain.** `connkg path` and `connkg cone` used to read all 3.7 million synapse edges out of SQLite on every invocation, with a JSON parse each. They now cache the loaded matrix beside the graph, 14 MB, and `connkg path --from LPLC2 --to DNp01` goes from 8.8 seconds to 1.8. The cache is keyed on the edge table's shape and the graph file, so an edited or rebuilt graph is never answered from a stale one.

**The vector index is built by default.** The documented build no longer passes `--no-index`, so a fresh install has `connkg query` and the `query_connectome` and `pack_connectome` MCP tools without a second step. On v783 the index is 16,861 vectors, 25 seconds and 29 MB. `connkg build` now checks for the `semantic` extra before it starts rather than failing after the graph is written, and `--no-index` warns when it leaves an older index in place.

**Provenance for the long passes.** `connkg skeletons` writes `reports/skeletons_<timestamp>.md` the way `connkg build` has always written its own: versions and git commit, options, host, what was read, what was written, timings and peak memory, with a failed pass recorded as FAILED. Graph snapshots gained a `coverage.soma` metric, since the back-fill writes metadata and never a node or an edge, and without it a snapshot could not tell a graph that knows where its cell bodies are from one that does not.

## Upgrading

`pip install -U connectome-kg`. An existing graph keeps working and every existing command behaves as before.

To get what this release adds, on a graph you have already built:

```bash
connkg --root . --dataset fafb783 meshes
connkg --root . --dataset fafb783 skeletons --data-dir fafb_v783 -j 12
connkg --root . --dataset fafb783 snapshot save
```

`meshes` takes about 11 seconds. `skeletons` needs the 31 GB skeleton download and is the only thing that does; pass your core count to `-j`, which defaults to 1. Re-snapshot afterwards, because the soma back-fill changes the graph a snapshot measures.

One API change: `connectomekg.scene.context_points` returns a fourth value, the count of cloud points that are a real soma rather than a marked point.

---

_Full changelog: [CHANGELOG.md](https://github.com/Flux-Frontiers/connectome_kg/blob/main/CHANGELOG.md)_
