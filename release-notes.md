# Release Notes -- v0.9.0

> Released: 2026-10-26

`ConnectomeKG.stats()` now returns the fleet's statistics shape, the one every
KG module and KGRAG read since kgmodule-utils 0.29.0. Against that release the
old reads of the flat keys raised, so this version is the one to use with it.
No commands, options or graph contents change.

## What changed

**Statistics in the fleet shape.** `ConnectomeKG.stats()` returns `kind`
(`connectome`), `nodes` (`total`, `by_kind`) and `edges` (`total`, `by_rel`),
plus the connectome figures: `dataset_id`, `n_neurons`, `n_cell_types`,
`n_neuropils`, `n_pairs` and `n_synapses`. The MCP `graph_stats` tool returns
`kind`, `nodes` and `edges` in place of the four flat count keys.
`connkg stats` still prints the flat keys, and snapshots record what they did
before.

**Newer dependency floor.** `kgmodule-utils` is now `>=0.29.0` for the package
and every extra, and the lock file is refreshed.

## Upgrading

Code that read `ConnectomeKG.stats()["node_counts"]` reads
`["nodes"]["by_kind"]` instead, and `["total_nodes"]` becomes
`["nodes"]["total"]`. Scripts that parse the MCP `graph_stats` result read the
same nested keys. Nothing needs rebuilding.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
