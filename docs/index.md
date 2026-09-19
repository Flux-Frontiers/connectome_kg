# ConnectomeKG

**Connectomes as knowledge graphs.**

*Eric G. Suchanek, PhD -- Flux-Frontiers*

ConnectomeKG turns an electron-microscopy connectome into a queryable
knowledge graph. Every neuron is a node, and every edge between two neurons
carries a synapse count and a transmitter sign. Cell types, neuropils,
taxonomy, hemilineages and community labels sit on top. The first corpus is
the FlyWire FAFB v783 adult *Drosophila* brain: 139,255 neurons and 3,732,460
connected neuron pairs.

![The escape circuit, LPLC2 to DNp01, inside the brain's neuropil surfaces](images/anatomy_lplc2_dnp01.png)

*The escape circuit in its anatomy. Pink is LPLC2, the looming detectors
filling the lobula of each optic lobe; blue is DNp01, the giant fibre, which
collects from them and sends the two axons leaving the bottom of the frame
down to the nerve cord. Behind them the brain's 78 neuropil surfaces, and one
dot per neuron at its cell body. The whole picture comes from one command,
`connkg quilt LPLC2 DNp01 --tubes --cloud`, over the same spec grammar the
path and cone queries take.*

![Neuropil flow across the FAFB v783 brain](images/flow_all.png)

*Signal flow between neuropils, summed over the neurons that carry it: the
strongest 100 of 5,786 directed pairs, each neuropil a sphere at the
synapse-weighted centroid of its neurons and tinted by brain region.*

!!! note "Data credit and licence"
    The images above are renders of the
    [FlyWire](https://flywire.ai) FAFB v783 connectome: Dorkenwald, S. et al.
    (2024), *Nature* 634, 124-138, and Schlegel, P. et al. (2024), *Nature*
    634, 139-152. The data is licensed under
    [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/).
    The render is an adaptation of it, shared under the same licence, not
    under the software's Elastic License 2.0.

## Where to start

| page | covers |
|---|---|
| [Get the FAFB v783 data](DOWNLOAD.md) | The Codex files the build reads, and how to download and check them |
| [Rendering the connectome in 3-D](rendering.md) | `connkg quilt` and `connkg viz3d`: the circuit and flow views, how each is drawn, and Looking Glass quilts through [quiltwright](https://flux-frontiers.github.io/quiltwright/) |
| [Scene API](api/scene.md) | `build_brain_scene`, `neuropil_flow` and the rest of `connectomekg.scene` |
| [Skeleton API](api/skeletons.md) | Reading, writing and simplifying SWC skeletons |

The [README](https://github.com/Flux-Frontiers/connectome_kg#readme) covers
installation, the build, and every `connkg` command.
