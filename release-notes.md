# Release Notes -- v0.10.0

> Released: 2026-10-26

connkg's MCP server now runs on the fleet's shared base, `kg_utils.mcp`, so its
first five tools have the same names on every Flux-Frontiers KG server:
`stats`, `query`, `pack`, `get_node` and `neighbors`. Its twelve connectome
tools (`strongest_path`, `cone`, `influence`, `type_partners`,
`neuroglancer_link` and the rest) are unchanged, and existing `connkg-mcp`
configs keep working.

## What changed

**Canonical tool names.** `graph_stats` is `stats`, `query_connectome` is
`query` and `pack_connectome` is `pack`, with no aliases. The new `neighbors`
tool returns a node's edges in either direction and the nodes at their ends.
`get_node` still returns the node's decoded metadata, and a missing node is
now a tool error rather than `null`. 17 tools in all, the canonical five
first.

**One command, standard flags.** `connkg mcp` takes the fleet's `--repo`,
`--db`, `--vectors`, `--model`, `--transport stdio|streamable-http`, `--host`,
`--port` and `--manifest`, with the dataset from connkg's own `--dataset`:
`connkg --root /path --dataset fafb783 mcp`. `--repo` may also name a dataset
directory directly. `connkg-mcp` is the same command and still takes `--root`
and `--dataset`. The graph opens per session and closes after, and a dataset
with no graph is refused instead of served empty.

## Upgrading

Rename the tools in agent instructions and scripts (`graph_stats` -> `stats`,
`query_connectome` -> `query`, `pack_connectome` -> `pack`) and drop
`--transport sse` from any config. A machine with more than one built dataset
needs `--dataset` in its MCP entry. connectome-kg now takes the MCP SDK
through `kgmodule-utils[mcp]>=0.29.0`. Nothing needs rebuilding.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
