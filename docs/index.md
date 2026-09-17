# ConnectomeKG

**Connectomes as knowledge graphs.**

*Eric G. Suchanek, PhD -- Flux-Frontiers*

ConnectomeKG turns an electron-microscopy connectome into a queryable
knowledge graph. Every neuron is a node, and every edge between two neurons
carries a synapse count and a transmitter sign. Cell types, neuropils,
taxonomy, hemilineages and community labels sit on top. The first corpus is
the FlyWire FAFB v783 adult *Drosophila* brain: 139,255 neurons and 3,732,460
connected neuron pairs.

![Neuropil flow across the FAFB v783 brain](images/flow_all.png)

## Where to start

| page | covers |
|---|---|
| [Get the FAFB v783 data](DOWNLOAD.md) | The Codex files the build reads, and how to download and check them |
| [Rendering the connectome in 3-D](rendering.md) | `connkg quilt` and `connkg viz3d`: the circuit and flow views, how each is drawn, and Looking Glass quilts through [quiltwright](https://flux-frontiers.github.io/quiltwright/) |
| [Scene API](api/scene.md) | `build_brain_scene`, `neuropil_flow` and the rest of `connectomekg.scene` |
| [Skeleton API](api/skeletons.md) | Reading, writing and simplifying SWC skeletons |

The [README](https://github.com/Flux-Frontiers/connectome_kg#readme) covers
installation, the build, and every `connkg` command.
