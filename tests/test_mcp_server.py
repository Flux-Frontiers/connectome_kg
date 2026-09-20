"""The MCP server, driven over the real protocol.

Every tool is called through ``mcp.shared.memory``'s in-process transport, an
actual ``Server.run()`` and lifespan cycle with a ``ClientSession``, not a call
into the ``ConnectomeKG`` method underneath. That is the harness FLEET_STANDARDS
names for MCP servers (genealogy_kg's test_mcp_lifespan.py and test_mcp_tools.py).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from mcp.client.session import ClientSession
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import CallToolResult, TextContent

from connectomekg import ConnectomeKG, mcp_server
from connectomekg.readers.synthetic import synthetic_tables
from connectomekg.schema import FAFB_783
from connectomekg.snapshots import SnapshotManager

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="module")
def graph_root(tables, tmp_path_factory) -> Path:
    # Its own graph, not the session `kg` fixture: the lifespan hook closes the
    # instance the server holds, and other tests share that one.
    root = tmp_path_factory.mktemp("mcp")
    with ConnectomeKG(root, tables=tables) as kg:
        kg.build_graph(wipe=True)
    return root


@asynccontextmanager
async def _session(root: Path) -> AsyncIterator[ClientSession]:
    mcp_server._kg = ConnectomeKG(root)
    mcp_server._snapshot_mgr = SnapshotManager(
        root / ".connectomekg" / "snapshots", db_path=mcp_server._kg.db_path
    )
    try:
        async with create_connected_server_and_client_session(mcp_server.mcp) as session:
            yield session
    finally:
        mcp_server._kg = None
        mcp_server._snapshot_mgr = None


def _text(result: CallToolResult) -> str:
    return "".join(c.text for c in result.content if isinstance(c, TextContent))


async def _call(session: ClientSession, tool: str, **args):
    result = await session.call_tool(tool, args)
    assert not result.isError, _text(result)
    return json.loads(_text(result))


async def _error(session: ClientSession, tool: str, **args) -> str:
    result = await session.call_tool(tool, args)
    assert result.isError, f"{tool}({args}) should have been rejected"
    return _text(result)


async def test_every_tool_is_registered(graph_root):
    async with _session(graph_root) as s:
        names = {t.name for t in (await s.list_tools()).tools}
    assert names == {
        "graph_stats",
        "find_nodes",
        "get_node",
        "node_edges",
        "neurons_of",
        "type_partners",
        "strongest_path",
        "influence",
        "cone",
        "neuroglancer_link",
        "query_connectome",
        "pack_connectome",
        "analyze_connectome",
        "snapshot_list",
        "snapshot_show",
        "snapshot_diff",
    }


async def test_lookup_tools(graph_root):
    async with _session(graph_root) as s:
        stats = await _call(s, "graph_stats")
        assert stats["node_counts"]["neuron"] == 600

        found = await _call(s, "find_nodes", name="dnp", kind="cell_type")
        assert "connectome:synthetic:t:DNp01" in {n["id"] for n in found}

        node = await _call(s, "get_node", node_id="`connectome:synthetic:t:LC4`")
        assert node["name"] == "LC4" and node["metadata"]["n_neurons"] == 8
        assert await _call(s, "get_node", node_id="connectome:synthetic:t:NOPE") is None

        terms = await _call(s, "node_edges", node_id="connectome:synthetic:t:LC4", rel="MAPS_TO")
        assert [e["node"] for e in terms] == ["connectome:synthetic:fbbt:FBbt_99000007"]

        resolved = await _call(s, "neurons_of", spec="LC4", limit=3)
        assert resolved["count"] == 8 and len(resolved["neurons"]) == 3


async def test_circuit_tools(graph_root):
    async with _session(graph_root) as s:
        partners = await _call(s, "type_partners", cell_type="LC4", direction="down")
        assert "DNp01" in {p["cell_type"] for p in partners}
        assert await _call(s, "type_partners", cell_type="NOPE") == []

        path = await _call(s, "strongest_path", source="GRN_sugar", target="MN9")
        assert path["strength"] > 0 and path["hops"][-1]["qualname"].startswith("MN9/")

        reach = await _call(s, "cone", spec="LC4", hops=1, limit=2)
        assert reach["0"]["count"] == 8 and len(reach["0"]["neurons"]) == 2
        assert reach["1"]["count"] >= 1


async def test_neuroglancer_link_tool(graph_root, tmp_path):
    async with _session(graph_root) as s:
        assert "no public Neuroglancer source" in await _error(
            s, "neuroglancer_link", specs=["LC4"]
        )
    fafb, tables = tmp_path / "fafb", synthetic_tables(400, seed=5)
    tables.dataset = FAFB_783
    with ConnectomeKG(fafb, tables=tables) as kg:
        kg.build_graph(wipe=True)
    async with _session(fafb) as s:
        link = await _call(s, "neuroglancer_link", specs=["LC4", "DNp01"], limit=2)
        assert link["url"].startswith("https://neuroglancer-demo.appspot.com/#!")
        assert [(x["spec"], x["count"], x["shown"]) for x in link["specs"]][0] == ("LC4", 8, 2)
        assert "limit must be between" in await _error(
            s, "neuroglancer_link", specs=["LC4"], limit=0
        )


async def test_report_and_snapshot_tools(graph_root):
    async with _session(graph_root) as s:
        report = await s.call_tool("analyze_connectome", {})
        assert not report.isError and _text(report).startswith("# ConnectomeKG analysis")
        assert await _call(s, "snapshot_list") == []
        assert await _call(s, "snapshot_show") is None
        assert "not found" in await _error(s, "snapshot_diff", key_a="a", key_b="b")


async def test_semantic_search_without_an_index_says_why(graph_root):
    async with _session(graph_root) as s:
        assert "no vector index" in await _error(s, "query_connectome", q="giant fibre")
        assert "no vector index" in await _error(s, "pack_connectome", q="giant fibre")


@pytest.mark.parametrize(
    ("tool", "args", "message"),
    [
        ("query_connectome", {"q": "   "}, "must not be empty"),
        ("query_connectome", {"q": "x", "k": 0}, "k must be between 1 and 100"),
        ("pack_connectome", {"q": "x", "max_nodes": 501}, "max_nodes must be between 1 and 500"),
        ("cone", {"spec": "LC4", "hops": 6}, "hops must be between 0 and 5"),
        ("cone", {"spec": "LC4", "min_syn": 0}, "min_syn must be between 1 and 10000"),
        ("cone", {"spec": "LC4", "limit": 501}, "limit must be between 1 and 500"),
        ("cone", {"spec": "LC4", "direction": "sideways"}, "direction must be one of"),
        ("strongest_path", {"source": "label:(", "target": "MN9"}, "not a valid regex"),
        ("neurons_of", {"spec": "label:" + "a" * 101}, "at most 100"),
        ("node_edges", {"node_id": "x", "rel": "DROP TABLE"}, "rel must be one of"),
        ("find_nodes", {"name": "LC", "kind": "nodes; --"}, "kind must be one of"),
        ("get_node", {"node_id": "``"}, "must not be empty"),
        ("type_partners", {"cell_type": "LC4", "limit": 0}, "limit must be between 1 and 500"),
        ("snapshot_list", {"limit": 10_000}, "limit must be between 1 and 500"),
    ],
)
async def test_out_of_range_arguments_are_rejected_not_clamped(graph_root, tool, args, message):
    async with _session(graph_root) as s:
        assert message in await _error(s, tool, **args)


async def test_lifespan_closes_the_graph_on_shutdown(graph_root):
    kg = ConnectomeKG(graph_root)
    mcp_server._kg = kg
    try:
        async with create_connected_server_and_client_session(mcp_server.mcp) as session:
            result = await session.call_tool("graph_stats", {})
            assert not result.isError
        # The server has unwound by here, so the lifespan's finally has run.
        assert kg._store is not None  # noqa: SLF001 - the tool call opened it
        assert kg._store._con is None  # noqa: SLF001 - and the lifespan closed it
    finally:
        mcp_server._kg = None


async def test_lifespan_is_a_noop_when_no_graph_was_set():
    assert mcp_server._kg is None
    async with create_connected_server_and_client_session(mcp_server.mcp):
        pass


async def test_influence_tool(graph_root):
    async with _session(graph_root) as s:
        result = await _call(s, "influence", source="GRN_sugar", target="MN9", hops=2, signed=False)
        assert result["n_sources"] > 0 and result["n_targets"] > 0
        assert len(result["onto"]) == 2
        assert result["onto_total"] == pytest.approx(sum(result["onto"]))
        assert "share of the receiving neuron's input" in result["units"]
        # Two hops from sugar to the motor neuron, via the planted interneuron.
        assert result["onto"][1] > 0
        assert "SEZ_IN1" in {r["cell_type"] for r in result["ranked"][0]}

        # No target ranks cell types instead of measuring a population.
        ranked = await _call(s, "influence", source="GRN_sugar", limit=2)
        assert ranked["target"] is None and ranked["onto"] == []
        assert all(len(hop) <= 2 for hop in ranked["ranked"])


async def test_influence_rejects_out_of_range_arguments(graph_root):
    async with _session(graph_root) as s:
        assert "hops must be between 1 and 5" in await _error(
            s, "influence", source="GRN_sugar", hops=6
        )
        assert "limit must be between 1 and 500" in await _error(
            s, "influence", source="GRN_sugar", limit=0
        )
