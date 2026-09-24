# Release Notes -- v0.8.0

> Released: 2026-09-23

ConnectomeKG now builds three connectomes instead of one. BANC v888 (a female brain with its ventral nerve cord, 158,262 neurons) and the FlyEM Male CNS v1.0 (166,700 neurons) build from their Codex exports beside FlyWire FAFB v783. Each goes into its own graph and answers the same path, cone and influence queries. The 3-D viewer can switch between the three without restarting.

## What changed

**Two new connectomes.** Codex exports BANC and MCNS as a single neuron-attributes table, a different layout from FAFB's. The reader recognizes the layout from the table's header, so no classification file is needed. It also normalizes the three releases so they can be compared:
- Super classes take FAFB's spelling.
- Pairs below 5 synapses are dropped, matching FAFB's filtered table.
- A connection with no transmitter takes the transmitter of its presynaptic neuron.
- Histamine counts as inhibitory.
- The nerve cord's neuropils, nerves and neck connective have names and brain regions.

`connkg verify` checks each download against its own manifest. Both releases are CC BY 4.0. `docs/DOWNLOAD.md` covers the download and what the reader normalizes.

**Soma positions for BANC and MCNS.** Codex exports no coordinates for either release, so every neuron would have had no position and the 3-D views would have drawn nothing. Both projects publish soma positions separately. The reader finds that table in the download directory by its columns and scales MCNS's voxel coordinates to nanometers. 88.7% of BANC's neurons and 83.8% of MCNS's get a position. The table is optional: without it, the build is unchanged.

**The viewer switches datasets, views and backgrounds.** `connkg viz3d` has two new boxes at the top of its control rail. **Dataset** lists every connectome built under `--root`. **View** switches between the circuit and flow views. When you switch dataset, the viewer keeps the specs in the Show box if they exist in the new connectome, and otherwise goes back to its opening scene. A Background box in the Display tab offers gray, charcoal, black, navy and light presets, or any color. The same choice is available on the command line as `--background` for `viz3d` and `quilt`. Saved images, quilts and casts use the chosen background.

**Marks keep their size on a larger connectome.** Neuropil spheres and flow tubes were sized for the FAFB brain. BANC's brain and nerve cord stand 2.3 times as tall, so the camera zoomed out and its spheres drew at under half size. Sizes now scale with each dataset's extent compared to FAFB's: 1.0 on FAFB, 2.32 on BANC and 1.12 on MCNS. FAFB renders are unchanged.

**A shorter README, with more in the docs site.** The README is now install, a quickstart that needs no download, the three datasets, and examples grouped by task. The node and edge reference moved to a new "What is in the graph" page. The MCP tool list moved to the command reference.

## Upgrading

- **FAFB graph:** no rebuild needed. Its build is unchanged, and its 0.8.0 snapshot matches 0.7.1.
- **BANC and MCNS:** download the Codex export and, for the 3-D views, the soma table. `docs/DOWNLOAD.md` names both. Then run `connkg --dataset banc888 build --data-dir <dir>`, or the same with `mcns1`.
- **`--dataset` is now required** on every command once a root holds more than one graph. It is a global option, so it goes before the command.
- **kgmodule-utils:** the floor is now 0.24.0. With it, `build --no-index --wipe` removes a stale vector index instead of keeping it.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
