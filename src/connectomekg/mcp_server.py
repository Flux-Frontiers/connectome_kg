#!/usr/bin/env python3
"""ConnectomeKG MCP server: the connectome graph as Model Context Protocol tools.

Built on the fleet's shared server base, :mod:`kg_utils.mcp`. The server
answers the fleet's canonical tools -- ``stats``, ``query``, ``pack``,
``get_node``, ``neighbors`` -- under the same names as every other KG server,
then ConnectomeKG's own: ``find_nodes``, ``node_edges``, ``neurons_of``,
``type_partners``, ``influence``, ``strongest_path``, ``cone``,
``neuroglancer_link``, ``analyze_connectome`` and the three snapshot tools.

The tool list is not kept by hand anywhere: each tool's docstring is its
description, the server's instructions are generated from them, and::

    connkg mcp --manifest

prints the whole list as JSON without opening a graph.

Hardening follows FLEET_STANDARDS: every argument is validated inside
``ConnectomeKG`` (connectomekg.validation), shared with the CLI; out-of-range
values are rejected, never clamped. The graph is opened when a session starts
and closed when it ends, and a dataset with no graph is refused rather than
served empty.

Usage
-----
::

    connkg --root /path --dataset fafb783 mcp
    connkg mcp --repo /path/connectomes/fafb783

``--repo`` names either a root holding ``connectomes/<dataset>/`` (the dataset
is connkg's ``--dataset``, or the only one built) or a dataset directory
itself. ``connkg-mcp`` is the same command under its older name and still
takes ``--root`` and ``--dataset``.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from kg_utils.mcp import Context, KGServer, kg_from, make_server
from kg_utils.validation import bounded_int

from connectomekg import __version__
from connectomekg.datasets import STORE_DIR, dataset_dir, resolve_dataset
from connectomekg.module import ConnectomeKG
from connectomekg.snapshots import SnapshotManager
from connectomekg.validation import MAX_LIMIT, normalize_node_id

#: Environment variable naming the dataset when no ``--dataset`` reached the
#: command (``connkg-mcp --dataset`` sets it for its own process).
DATASET_ENV = "CONNKG_DATASET"

PREAMBLE = (
    "ConnectomeKG is a knowledge graph of an electron-microscopy connectome, "
    "first the FlyWire FAFB v783 adult Drosophila brain: 139,255 neurons, 8,772 "
    "cell types, 3.7 M synaptic pairs, neuropils, taxonomy, hemilineages, nerves, "
    "visual families and retinotopic columns, connectivity tags, community labels "
    "and Fly Anatomy Ontology (FBbt) terms. Node ids look like "
    "'connectome:fafb783:t:LC4' (cell type), ':n:<root id>' (neuron), ':np:LO_R' "
    "(neuropil), ':col:right/97' (column), ':nv:AN' (nerve), ':fbbt:FBbt_00003733'.\n\n"
    "## Workflows\n\n"
    "- Orient: stats.\n"
    "- Find a type or node by name: find_nodes('DNp', kind='cell_type').\n"
    "- What a type talks to: type_partners('LC4', direction='down').\n"
    "- Route between two populations: strongest_path('LPLC2', 'DNp01'). Strength "
    "is the product of each hop's share of the postsynaptic neuron's input.\n"
    "- Everything downstream or upstream: cone('LC4', hops=2, min_syn=10).\n"
    "- A neuron's neuropils, a column's neurons, a type's ontology terms: "
    "node_edges(node_id, rel=...), or neighbors(node_id) for both directions.\n"
    "- See neurons as meshes: neuroglancer_link(['LPLC2', 'DNp01']) returns a URL "
    "that opens them in Neuroglancer, one color per spec, no login.\n"
    "- Concept search: query or pack, only when the vector "
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
)


def _json(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False)


def _snapshot_mgr(ctx: Context) -> SnapshotManager:
    """The served dataset's snapshot manager."""
    kg: ConnectomeKG = kg_from(ctx)
    return SnapshotManager(kg.repo_root / STORE_DIR / "snapshots", db_path=kg.db_path)


def get_node(node_id: str, ctx: Context) -> dict[str, Any]:
    """One node with its decoded metadata.

    :param node_id: Node id, e.g. ``"connectome:fafb783:t:LC4"``; backticks and
        quotes are stripped.
    """
    node = kg_from(ctx).describe(node_id)
    if node is None:
        raise ValueError(f"no node with id {node_id!r}")
    return node


def find_nodes(name: str, kind: str = "", limit: int = 20, *, ctx: Context) -> str:
    """Nodes whose name contains a string, case-insensitively, shortest names first.

    :param name: Substring, e.g. ``"DNp"``.
    :param kind: One node kind (cell_type, neuron, neuropil, column, nerve, taxon,
        ontology_term, connectivity_tag, label, hemilineage, dataset), or ``""``.
    :param limit: Nodes returned, 1-500.
    :return: JSON list of {id, kind, name, qualname}.
    """
    return _json(kg_from(ctx).find_nodes(name, kind=kind, limit=limit))


def node_edges(
    node_id: str, rel: str = "", direction: str = "out", limit: int = 50, *, ctx: Context
) -> str:
    """Edges at a node, with the node at the other end and the edge evidence.

    :param node_id: Node id.
    :param rel: One relation (SYNAPSES_TO, TYPE_SYNAPSES_TO, INSTANCE_OF, IN_NEUROPIL,
        INNERVATES, CONTAINS, MEMBER_OF, MAPS_TO, LABELED, MIRROR_OF, VIA_NERVE,
        IN_COLUMN, TAGGED, IN_DATASET), or ``""`` for all.
    :param direction: ``"out"`` (the node is the source) or ``"in"``.
    :param limit: Edges returned, 1-500.
    :return: JSON list of {rel, node, name, kind, evidence}.
    """
    return _json(kg_from(ctx).node_edges(node_id, rel=rel, direction=direction, limit=limit))


def neurons_of(spec: str, limit: int = 100, *, ctx: Context) -> str:
    """Resolve a spec to neuron node ids.

    :param spec: Cell type name, root id, neuron node id, or ``"label:<regex>"``.
    :param limit: Ids listed, 1-500; ``count`` is always the full total.
    :return: JSON {count, neurons}.
    """
    limit = bounded_int("limit", limit, 1, MAX_LIMIT)
    ids = kg_from(ctx).neurons_of(spec)
    return _json({"count": len(ids), "neurons": ids[:limit]})


def type_partners(cell_type: str, direction: str = "down", limit: int = 20, *, ctx: Context) -> str:
    """A cell type's partner cell types, by synapse count.

    :param cell_type: Exact cell type name, e.g. ``"LC4"``.
    :param direction: ``"down"`` for the types it synapses onto, ``"up"`` for its inputs.
    :param limit: Partners returned, 1-500.
    :return: JSON list of {cell_type, syn_count, n_pairs, nt_type}; empty for an unknown type.
    """
    return _json(kg_from(ctx).type_partners(cell_type, direction=direction, limit=limit))


def influence(
    source: str,
    target: str = "",
    hops: int = 3,
    signed: bool = True,
    limit: int = 20,
    *,
    ctx: Context,
) -> str:
    """Effective connectivity: how much one population drives another, hop by hop.

    A value is the share of the receiving neuron's input synapses that the
    source drives, averaged over the receiving neurons, so 0.15 means the
    average target gets 15% of its input from the source. Signed, a negative
    value is net inhibition, and two routes of opposite sign cancel.

    Unlike ``strongest_path``, which returns one best route, this sums every
    route of the given length at once. Use it to ask "does A drive B, and net
    of what sign" rather than "how does A reach B".

    :param source: Spec for the driving population.
    :param target: Spec for the receiving population; empty ranks cell types
        instead of measuring one population.
    :param hops: Hops to propagate, 1-5.
    :param signed: Apply transmitter signs; False treats every synapse as
        excitatory, which matches the raw input share at hop 1.
    :param limit: Cell types listed per hop, 1-500.
    :return: JSON with per-hop values onto the target and the strongest cell
        types at each hop.
    """
    result = kg_from(ctx).influence(source, target or None, hops=hops, signed=signed, limit=limit)
    return _json(
        {
            "source": result.source,
            "target": result.target,
            "signed": result.signed,
            "n_sources": result.n_sources,
            "n_targets": result.n_targets,
            "units": "share of the receiving neuron's input synapses, averaged over them",
            "onto": [round(v, 6) for v in result.onto],
            "onto_total": round(sum(result.onto), 6) if result.onto else None,
            "ranked": [
                [{"cell_type": n, "influence": round(v, 6)} for n, v in hop]
                for hop in result.ranked
            ],
        }
    )


def strongest_path(source: str, target: str, *, ctx: Context) -> str:
    """Strongest synaptic path between two specs.

    :param source: Spec for the start population.
    :param target: Spec for the end population.
    :return: JSON {strength, net_sign, hops: [{node_id, qualname, syn_count, fraction,
        sign}]}, or ``null`` when no path exists or a spec matches no neurons.
    """
    kg = kg_from(ctx)
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


def cone(
    spec: str,
    hops: int = 1,
    min_syn: int = 1,
    direction: str = "down",
    limit: int = 20,
    *,
    ctx: Context,
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
    kg = kg_from(ctx)
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


def neuroglancer_link(specs: list[str], limit: int = 200, *, ctx: Context) -> str:
    """A Neuroglancer URL showing each spec's neurons as FlyWire meshes, one color per spec.

    Opens in a browser with no login, on the dataset's public segmentation
    (FAFB v783 only). Give the URL to the user; do not fetch it.

    :param specs: One to seven specs, e.g. ``["LPLC2", "DNp01"]``.
    :param limit: Neurons shown per spec, 1-500; ``count`` is always the full total.
    :return: JSON {url, specs: [{spec, count, shown, color}]}.
    """
    return _json(kg_from(ctx).neuroglancer_link(specs, limit=limit))


def analyze_connectome(ctx: Context) -> str:
    """The Markdown analysis report: counts, hub neurons, strongest type pairs, neuropils, coverage.

    :return: Markdown.
    """
    return kg_from(ctx).analyze()


def snapshot_list(limit: int = 10, *, ctx: Context) -> str:
    """Saved metric snapshots, newest first.

    :param limit: Snapshots returned, 1-500.
    :return: JSON list of manifest entries.
    """
    limit = bounded_int("limit", limit, 1, MAX_LIMIT)
    return _json(_snapshot_mgr(ctx).list_snapshots(limit=limit))


def snapshot_show(key: str = "latest", *, ctx: Context) -> str:
    """One snapshot in full.

    :param key: Snapshot key (a release tag or UTC timestamp), or ``"latest"``.
    :return: JSON snapshot, or ``null`` if there is none.
    """
    snap = _snapshot_mgr(ctx).load_snapshot(normalize_node_id(key))
    return _json(snap.to_dict() if snap else None)


def snapshot_diff(key_a: str, key_b: str, *, ctx: Context) -> str:
    """Compare two snapshots (B minus A).

    :param key_a: Earlier snapshot key.
    :param key_b: Later snapshot key.
    :return: JSON with both snapshots' metrics and the deltas.
    """
    result = _snapshot_mgr(ctx).diff_snapshots(normalize_node_id(key_a), normalize_node_id(key_b))
    if "error" in result:
        raise ValueError(result["error"])
    return _json(result)


#: Domain tools, registered after the canonical five in this order.
EXTRA_TOOLS = (
    find_nodes,
    node_edges,
    neurons_of,
    type_partners,
    influence,
    strongest_path,
    cone,
    neuroglancer_link,
    analyze_connectome,
    snapshot_list,
    snapshot_show,
    snapshot_diff,
)


def dataset_home(repo: str | Path, dataset: str | None = None) -> Path:
    """The directory of the dataset to serve.

    :param repo: A dataset directory (holding ``.connectomekg/``), or a root
        holding ``connectomes/<dataset>/``.
    :param dataset: Dataset id under a root; ``None`` for the only one built.
    :return: The dataset directory.
    :raises ValueError: When a root holds no dataset, or several and none is named.
    """
    repo = Path(repo).resolve()
    if dataset is None and (repo / STORE_DIR).is_dir():
        return repo
    return dataset_dir(repo, resolve_dataset(repo, dataset))


def build_server(
    repo: str | Path,
    db: str | Path | None = None,
    vectors: str | Path | None = None,
    model: str | None = None,
    *,
    dataset: str | None = None,
) -> KGServer:
    """Build the ConnectomeKG MCP server, without opening its graph.

    The dataset is resolved when a session starts, so ``--manifest`` answers
    with nothing built.

    :param repo: Dataset directory, or a root holding ``connectomes/``.
    :param db: Graph database; ``None`` for the dataset's ``.connectomekg/graph.sqlite``.
    :param vectors: Vector store; ``None`` for the one beside the graph.
    :param model: Embedding model; ``None`` for the default.
    :param dataset: Dataset id under a root; ``None`` for ``$CONNKG_DATASET`` or
        the only one built.
    :return: The server; serve it with :func:`kg_utils.mcp.run`.
    """
    kwargs: dict[str, Any] = {"model": model} if model else {}

    def open_kg() -> ConnectomeKG:
        home = dataset_home(repo, dataset or os.environ.get(DATASET_ENV) or None)
        return ConnectomeKG(home, db_path=db, vectors_path=vectors, **kwargs)

    server = make_server(
        open_kg, name="connkg", kind="connectome", version=__version__, instructions=PREAMBLE
    )
    server.canonical("get_node")(get_node)
    for fn in EXTRA_TOOLS:
        server.tool()(fn)
    return server


def main(argv: list[str] | None = None) -> None:
    """Entry point for ``connkg-mcp``: the same command as ``connkg mcp``.

    Takes ``--root`` for ``--repo``, and ``--dataset ID``, the spellings
    ``connkg-mcp`` used before the standard command.

    :param argv: Arguments; ``None`` for ``sys.argv[1:]``.
    """
    from connectomekg.cli.cmd_mcp import mcp_command  # noqa: PLC0415 -- cli imports this lazily

    args = list(sys.argv[1:] if argv is None else argv)
    out: list[str] = []
    while args:
        a = args.pop(0)
        if a == "--dataset" and args:
            os.environ[DATASET_ENV] = args.pop(0)
        elif a.startswith("--dataset="):
            os.environ[DATASET_ENV] = a.split("=", 1)[1]
        elif a.split("=")[0] == "--root":
            out.append("--repo" + a[len("--root") :])
        else:
            out.append(a)
    mcp_command.main(args=out, prog_name="connkg-mcp")


if __name__ == "__main__":
    main()
