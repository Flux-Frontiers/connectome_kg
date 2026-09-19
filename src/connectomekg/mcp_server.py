#!/usr/bin/env python3
"""ConnectomeKG MCP server: the connectome graph as Model Context Protocol tools.

Tools
-----
graph_stats()
    Node and edge counts. Start here.
find_nodes(name, kind, limit)
    Nodes whose name contains a string, when the id is unknown.
get_node(node_id)
    One node with its metadata.
node_edges(node_id, rel, direction, limit)
    Edges at a node: a neuron's neuropils, a column's neurons, a type's terms.
neurons_of(spec, limit)
    Resolve a cell type, root id, neuron id or ``label:<regex>`` to neurons.
type_partners(cell_type, direction, limit)
    A cell type's partner types, strongest first.
strongest_path(source, target)
    Strongest synaptic path between two specs.
cone(spec, hops, min_syn, direction, limit)
    Downstream or upstream cone of a spec, by hop.
neuroglancer_link(specs, limit)
    A Neuroglancer URL showing specs' neurons as meshes in the browser.
query_connectome(q, k, hop)
    Semantic search with graph expansion (needs the vector index).
pack_connectome(q, k, hop, max_nodes)
    The same search as a Markdown pack.
analyze_connectome()
    The Markdown analysis report.
snapshot_list(limit), snapshot_show(key), snapshot_diff(key_a, key_b)
    Saved metric snapshots.

Hardening follows FLEET_STANDARDS: every argument is validated inside
``ConnectomeKG`` (connectomekg.validation), shared with the CLI; out-of-range
values are rejected, never clamped; and a ``lifespan`` hook closes the graph
when the server stops, on either transport.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from connectomekg.datasets import STORE_DIR, dataset_dir, resolve_dataset
from connectomekg.module import ConnectomeKG
from connectomekg.snapshots import SnapshotManager
from connectomekg.validation import MAX_LIMIT, bounded_int, normalize_node_id

_kg: ConnectomeKG | None = None
_snapshot_mgr: SnapshotManager | None = None


def _get_kg() -> ConnectomeKG:
    if _kg is None:
        raise RuntimeError(
            "ConnectomeKG not initialised. Run the server via 'connkg-mcp --root PATH'"
        )
    return _kg


def _get_snapshot_mgr() -> SnapshotManager:
    if _snapshot_mgr is None:
        raise RuntimeError(
            "SnapshotManager not initialised. Run the server via 'connkg-mcp --root PATH'"
        )
    return _snapshot_mgr


def _json(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False)


@asynccontextmanager
async def _lifespan(_server: FastMCP) -> AsyncIterator[None]:
    """Close the long-lived ConnectomeKG when the server shuts down.

    Per FLEET_STANDARDS (resource cleanup, settled 2026-08-24). ``main()`` sets
    ``_kg`` before ``mcp.run()``, and the stdio and SSE transports both route
    through the same ``Server.run()``, so this one hook covers both.
    """
    try:
        yield
    finally:
        if _kg is not None:
            _kg.close()


mcp = FastMCP(
    "connkg",
    lifespan=_lifespan,
    instructions=(
        "ConnectomeKG is a knowledge graph of an electron-microscopy connectome, "
        "first the FlyWire FAFB v783 adult Drosophila brain: 139,255 neurons, 8,772 "
        "cell types, 3.7 M synaptic pairs, neuropils, taxonomy, hemilineages, nerves, "
        "visual families and retinotopic columns, connectivity tags, community labels "
        "and Fly Anatomy Ontology (FBbt) terms. Node ids look like "
        "'connectome:fafb783:t:LC4' (cell type), ':n:<root id>' (neuron), ':np:LO_R' "
        "(neuropil), ':col:right/97' (column), ':nv:AN' (nerve), ':fbbt:FBbt_00003733'.\n\n"
        "## Workflows\n\n"
        "- Orient: graph_stats.\n"
        "- Find a type or node by name: find_nodes('DNp', kind='cell_type').\n"
        "- What a type talks to: type_partners('LC4', direction='down').\n"
        "- Route between two populations: strongest_path('LPLC2', 'DNp01'). Strength "
        "is the product of each hop's share of the postsynaptic neuron's input.\n"
        "- Everything downstream or upstream: cone('LC4', hops=2, min_syn=10).\n"
        "- A neuron's neuropils, a column's neurons, a type's ontology terms: "
        "node_edges(node_id, rel=...).\n"
        "- See neurons as meshes: neuroglancer_link(['LPLC2', 'DNp01']) returns a URL "
        "that opens them in Neuroglancer, one colour per spec, no login.\n"
        "- Concept search: query_connectome or pack_connectome, only when the vector "
        "index was built; otherwise they return an error saying so.\n\n"
        "A spec (strongest_path, cone, neurons_of) is an exact, case-sensitive cell type "
        "name, a root id, a neuron node id, or 'label:<regex>' over community labels. "
        "The first strongest_path or cone call loads every synapse edge and takes a "
        "while; later calls reuse it.\n\n"
        "## Argument bounds\n\n"
        "Out-of-range arguments are rejected with a message naming the range, never "
        "clamped. k 1-100, hop and hops 0-5, max_nodes 1-500, limit 1-500, min_syn "
        "1-10000, queries and ids at most 500 characters, a label: pattern at most 100 "
        "characters and a valid regex. Ids may carry backticks or quotes; they are "
        "stripped."
    ),
)


@mcp.tool()
def graph_stats() -> str:
    """Node and edge counts by kind and relation for the loaded graph.

    :return: JSON with total_nodes, total_edges, node_counts and edge_counts.
    """
    s = _get_kg().store.stats()
    keys = ("total_nodes", "total_edges", "node_counts", "edge_counts")
    return _json({k: s[k] for k in keys if k in s})


@mcp.tool()
def find_nodes(name: str, kind: str = "", limit: int = 20) -> str:
    """Nodes whose name contains a string, case-insensitively, shortest names first.

    :param name: Substring, e.g. ``"DNp"``.
    :param kind: One node kind (cell_type, neuron, neuropil, column, nerve, taxon,
        ontology_term, connectivity_tag, label, hemilineage, dataset), or ``""``.
    :param limit: Nodes returned, 1-500.
    :return: JSON list of {id, kind, name, qualname}.
    """
    return _json(_get_kg().find_nodes(name, kind=kind, limit=limit))


@mcp.tool()
def get_node(node_id: str) -> str:
    """One node with its decoded metadata.

    :param node_id: Node id, e.g. ``"connectome:fafb783:t:LC4"``.
    :return: JSON node, or ``null`` if there is no such node.
    """
    return _json(_get_kg().describe(node_id))


@mcp.tool()
def node_edges(node_id: str, rel: str = "", direction: str = "out", limit: int = 50) -> str:
    """Edges at a node, with the node at the other end and the edge evidence.

    :param node_id: Node id.
    :param rel: One relation (SYNAPSES_TO, TYPE_SYNAPSES_TO, INSTANCE_OF, IN_NEUROPIL,
        INNERVATES, CONTAINS, MEMBER_OF, MAPS_TO, LABELED, MIRROR_OF, VIA_NERVE,
        IN_COLUMN, TAGGED, IN_DATASET), or ``""`` for all.
    :param direction: ``"out"`` (the node is the source) or ``"in"``.
    :param limit: Edges returned, 1-500.
    :return: JSON list of {rel, node, name, kind, evidence}.
    """
    return _json(_get_kg().node_edges(node_id, rel=rel, direction=direction, limit=limit))


@mcp.tool()
def neurons_of(spec: str, limit: int = 100) -> str:
    """Resolve a spec to neuron node ids.

    :param spec: Cell type name, root id, neuron node id, or ``"label:<regex>"``.
    :param limit: Ids listed, 1-500; ``count`` is always the full total.
    :return: JSON {count, neurons}.
    """
    limit = bounded_int("limit", limit, 1, MAX_LIMIT)
    ids = _get_kg().neurons_of(spec)
    return _json({"count": len(ids), "neurons": ids[:limit]})


@mcp.tool()
def type_partners(cell_type: str, direction: str = "down", limit: int = 20) -> str:
    """A cell type's partner cell types, by synapse count.

    :param cell_type: Exact cell type name, e.g. ``"LC4"``.
    :param direction: ``"down"`` for the types it synapses onto, ``"up"`` for its inputs.
    :param limit: Partners returned, 1-500.
    :return: JSON list of {cell_type, syn_count, n_pairs, nt_type}; empty for an unknown type.
    """
    return _json(_get_kg().type_partners(cell_type, direction=direction, limit=limit))


@mcp.tool()
def strongest_path(source: str, target: str) -> str:
    """Strongest synaptic path between two specs.

    :param source: Spec for the start population.
    :param target: Spec for the end population.
    :return: JSON {strength, net_sign, hops: [{node_id, qualname, syn_count, fraction,
        sign}]}, or ``null`` when no path exists or a spec matches no neurons.
    """
    kg = _get_kg()
    res = kg.strongest_path(source, target)
    if res is None:
        return _json(None)
    hops = []
    for h in res.hops:
        node = kg.store.node(h.node_id) or {}
        hops.append(
            {
                "node_id": h.node_id,
                "qualname": node.get("qualname"),
                "syn_count": h.syn_count,
                "fraction": h.fraction,
                "sign": h.sign,
            }
        )
    return _json({"strength": res.strength, "net_sign": res.net_sign, "hops": hops})


@mcp.tool()
def cone(
    spec: str, hops: int = 1, min_syn: int = 1, direction: str = "down", limit: int = 20
) -> str:
    """Neurons reachable from a spec within some hops, grouped by hop.

    :param spec: Spec for the seed population.
    :param hops: Depth, 0-5.
    :param min_syn: Minimum synapses per edge followed, 1-10000.
    :param direction: ``"down"`` (outputs) or ``"up"`` (inputs).
    :param limit: Neurons listed per hop, 1-500; counts are always complete.
    :return: JSON {hop: {count, neurons: [qualname]}}.
    """
    limit = bounded_int("limit", limit, 1, MAX_LIMIT)
    kg = _get_kg()
    reached = kg.cone(spec, hops=hops, min_syn=min_syn, direction=direction)
    by_hop: dict[int, list[str]] = {}
    for nid, h in reached.items():
        by_hop.setdefault(h, []).append(nid)
    out = {}
    for h in sorted(by_hop):
        ids = sorted(by_hop[h])
        names = [(kg.store.node(i) or {}).get("qualname") or i for i in ids[:limit]]
        out[str(h)] = {"count": len(ids), "neurons": names}
    return _json(out)


@mcp.tool()
def neuroglancer_link(specs: list[str], limit: int = 200) -> str:
    """A Neuroglancer URL showing each spec's neurons as FlyWire meshes, one colour per spec.

    Opens in a browser with no login, on the dataset's public segmentation
    (FAFB v783 only). Give the URL to the user; do not fetch it.

    :param specs: One to seven specs, e.g. ``["LPLC2", "DNp01"]``.
    :param limit: Neurons shown per spec, 1-500; ``count`` is always the full total.
    :return: JSON {url, specs: [{spec, count, shown, color}]}.
    """
    return _json(_get_kg().neuroglancer_link(specs, limit=limit))


@mcp.tool()
def query_connectome(q: str, k: int = 8, hop: int = 1) -> str:
    """Semantic search with graph expansion over cell types, neuropils, labels and taxa.

    Needs the vector index (a build without --no-index); returns an error otherwise.

    :param q: Natural-language query, at most 500 characters.
    :param k: Seed hits, 1-100.
    :param hop: Expansion hops, 0-5.
    :return: JSON QueryResult.
    """
    return _get_kg().query(q, k=k, hop=hop).to_json()


@mcp.tool()
def pack_connectome(q: str, k: int = 8, hop: int = 1, max_nodes: int = 15) -> str:
    """The same search as query_connectome, as a ranked Markdown pack of node descriptions.

    :param q: Natural-language query, at most 500 characters.
    :param k: Seed hits, 1-100.
    :param hop: Expansion hops, 0-5.
    :param max_nodes: Nodes in the pack, 1-500.
    :return: Markdown.
    """
    return _get_kg().pack(q, k=k, hop=hop, max_nodes=max_nodes).to_markdown()


@mcp.tool()
def analyze_connectome() -> str:
    """The Markdown analysis report: counts, hub neurons, strongest type pairs, neuropils, coverage.

    :return: Markdown.
    """
    return _get_kg().analyze()


@mcp.tool()
def snapshot_list(limit: int = 10) -> str:
    """Saved metric snapshots, newest first.

    :param limit: Snapshots returned, 1-500.
    :return: JSON list of manifest entries.
    """
    limit = bounded_int("limit", limit, 1, MAX_LIMIT)
    return _json(_get_snapshot_mgr().list_snapshots(limit=limit))


@mcp.tool()
def snapshot_show(key: str = "latest") -> str:
    """One snapshot in full.

    :param key: Snapshot key (a release tag or UTC timestamp), or ``"latest"``.
    :return: JSON snapshot, or ``null`` if there is none.
    """
    snap = _get_snapshot_mgr().load_snapshot(normalize_node_id(key))
    return _json(snap.to_dict() if snap else None)


@mcp.tool()
def snapshot_diff(key_a: str, key_b: str) -> str:
    """Compare two snapshots (B minus A).

    :param key_a: Earlier snapshot key.
    :param key_b: Later snapshot key.
    :return: JSON with both snapshots' metrics and the deltas.
    """
    result = _get_snapshot_mgr().diff_snapshots(normalize_node_id(key_a), normalize_node_id(key_b))
    if "error" in result:
        raise ValueError(result["error"])
    return _json(result)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="connkg-mcp",
        description="ConnectomeKG MCP server: connectome graph tools for AI agents.",
    )
    p.add_argument(
        "--root",
        "--repo",
        dest="root",
        default=".",
        help="Directory holding connectomes/<dataset>/ (--repo is accepted for fleet configs).",
    )
    p.add_argument(
        "--dataset",
        default=None,
        help="Dataset id, e.g. fafb783 (default: the only built dataset under --root).",
    )
    p.add_argument(
        "--db",
        default=None,
        help="Graph path (default: <root>/connectomes/<dataset>/.connectomekg/graph.sqlite)",
    )
    p.add_argument("--transport", choices=["stdio", "sse"], default="stdio")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Start the MCP server.

    :param argv: Argument vector; defaults to ``sys.argv[1:]``.
    """
    global _kg, _snapshot_mgr

    args = _parse_args(argv)
    root = Path(args.root).resolve()
    try:
        home = dataset_dir(root, resolve_dataset(root, args.dataset))
    except ValueError as exc:
        raise SystemExit(f"connkg-mcp: {exc}") from exc
    _kg = ConnectomeKG(home, db_path=args.db)
    _snapshot_mgr = SnapshotManager(home / STORE_DIR / "snapshots", db_path=_kg.db_path)
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
