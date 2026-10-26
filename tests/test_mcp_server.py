"""The MCP server on kg_utils.mcp, driven over the real protocol.

Every tool is called through ``mcp.shared.memory``'s in-process transport, an
actual ``Server.run()`` and lifespan cycle with a ``ClientSession``, against a
synthetic connectome built by ``ConnectomeKG`` itself. That is the harness
FLEET_STANDARDS names for MCP servers. The server opens its own graph per
session, as it does in production.

Then the surface step 2 of kgrag_priv's MCP centralization plan promises for a
module: the five canonical tools first, under the names every fleet server
shares, then ConnectomeKG's own; the manifest answers without a graph;
``connkg``'s other commands do not import ``mcp``; a dataset is resolved under
a root; ``connkg-mcp`` keeps ``--root`` and ``--dataset``; and a real stdio
subprocess serves.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import anyio
import pytest
from click.testing import CliRunner
from kg_utils.mcp import CANONICAL_TOOLS, manifest
from kg_utils.stats import stats_problems
from mcp import StdioServerParameters
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import CallToolResult, TextContent

import connectomekg
from connectomekg import ConnectomeKG
from connectomekg.cli import cli
from connectomekg.datasets import dataset_dir
from connectomekg.mcp_server import EXTRA_TOOLS, build_server
from connectomekg.readers.synthetic import synthetic_tables
from connectomekg.schema import FAFB_783

_SRC = str(Path(connectomekg.__file__).resolve().parents[1])

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
async def _session(root: Path, **kwargs) -> AsyncIterator[ClientSession]:
    async with create_connected_server_and_client_session(build_server(root, **kwargs)) as session:
        yield session


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


async def test_canonical_tools_then_the_extras(graph_root):
    async with _session(graph_root) as s:
        names = [t.name for t in (await s.list_tools()).tools]
    assert names == [*CANONICAL_TOOLS, *(fn.__name__ for fn in EXTRA_TOOLS)]
    assert not {"graph_stats", "query_connectome", "pack_connectome"} & set(names)


async def test_lookup_tools(graph_root):
    async with _session(graph_root) as s:
        stats = await _call(s, "stats")
        assert stats_problems(stats) == [] and stats["kind"] == "connectome"
        assert stats["nodes"]["by_kind"]["neuron"] == 600
        assert stats["n_neurons"] == 600 and stats["dataset_id"] == "synthetic"
        assert "module_count" not in stats

        found = await _call(s, "find_nodes", name="dnp", kind="cell_type")
        assert "connectome:synthetic:t:DNp01" in {n["id"] for n in found}

        node = await _call(s, "get_node", node_id="`connectome:synthetic:t:LC4`")
        assert node["name"] == "LC4" and node["metadata"]["n_neurons"] == 8
        assert "no node with id" in await _error(
            s, "get_node", node_id="connectome:synthetic:t:NOPE"
        )

        near = await _call(s, "neighbors", node_id="`connectome:synthetic:t:LC4`", rels=["MAPS_TO"])
        assert [n["id"] for n in near["nodes"]] == ["connectome:synthetic:fbbt:FBbt_99000007"]

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
        assert "no vector index" in await _error(s, "query", q="giant fiber")
        assert "no vector index" in await _error(s, "pack", q="giant fiber")


@pytest.mark.parametrize(
    ("tool", "args", "message"),
    [
        ("query", {"q": "   "}, "must not be empty"),
        ("query", {"q": "x", "k": 0}, "k must be between 1 and 100"),
        ("pack", {"q": "x", "max_nodes": 501}, "max_nodes must be between 1 and 500"),
        ("cone", {"spec": "LC4", "hops": 6}, "hops must be between 0 and 5"),
        ("cone", {"spec": "LC4", "min_syn": 0}, "min_syn must be between 1 and 10000"),
        ("cone", {"spec": "LC4", "limit": 501}, "limit must be between 1 and 500"),
        ("cone", {"spec": "LC4", "direction": "sideways"}, "direction must be one of"),
        ("strongest_path", {"source": "label:(", "target": "MN9"}, "not a valid regex"),
        ("neurons_of", {"spec": "label:" + "a" * 101}, "at most 100"),
        ("node_edges", {"node_id": "x", "rel": "DROP TABLE"}, "rel must be one of"),
        ("find_nodes", {"name": "LC", "kind": "nodes; --"}, "kind must be one of"),
        ("get_node", {"node_id": "``"}, "must not be empty"),
        ("neighbors", {"node_id": "``"}, "must not be empty"),
        (
            "neighbors",
            {"node_id": "connectome:synthetic:t:LC4", "limit": 0},
            "limit must be between",
        ),
        ("type_partners", {"cell_type": "LC4", "limit": 0}, "limit must be between 1 and 500"),
        ("snapshot_list", {"limit": 10_000}, "limit must be between 1 and 500"),
    ],
)
async def test_out_of_range_arguments_are_rejected_not_clamped(graph_root, tool, args, message):
    async with _session(graph_root) as s:
        assert message in await _error(s, tool, **args)


async def test_the_session_opens_the_graph_and_closes_it(graph_root, monkeypatch):
    closed: list[ConnectomeKG] = []
    real_close = ConnectomeKG.close

    def counting_close(self: ConnectomeKG) -> None:
        closed.append(self)
        real_close(self)

    monkeypatch.setattr(ConnectomeKG, "close", counting_close)
    async with _session(graph_root) as s:
        assert not (await s.call_tool("stats", {})).isError
        assert closed == [], "the graph stays open for the whole session"
    assert len(closed) == 1
    assert closed[0]._store is not None and closed[0]._store._con is None  # noqa: SLF001


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


# ---------------------------------------------------------------------------
# Datasets, the command and the old entry point
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def two_dataset_root(tables, tmp_path_factory) -> Path:
    """A root holding two built datasets, as a machine with fafb783 and banc888 does."""
    root = tmp_path_factory.mktemp("datasets")
    for dataset in ("synthetic", "fafb783"):
        with ConnectomeKG(dataset_dir(root, dataset), tables=tables) as kg:
            kg.build_graph(wipe=True)
    return root


async def test_a_named_dataset_under_a_root_is_served(two_dataset_root):
    async with _session(two_dataset_root, dataset="synthetic") as s:
        assert (await _call(s, "stats"))["dataset_id"] == "synthetic"


def test_an_unnamed_dataset_among_several_is_refused(two_dataset_root):
    async def run() -> None:
        async with _session(two_dataset_root):
            pass

    with pytest.raises(BaseException) as info:
        anyio.run(run)
    assert "name one with --dataset" in repr(info.value) or any(
        "name one with --dataset" in str(e) for e in getattr(info.value, "exceptions", ())
    )


def test_a_dataset_with_no_graph_is_refused_not_served_empty(tmp_path):
    (tmp_path / ".connectomekg").mkdir()

    async def run() -> None:
        async with _session(tmp_path):
            pass

    with pytest.raises(BaseException) as info:
        anyio.run(run)
    assert "no graph at" in repr(info.value) or any(
        "no graph at" in str(e) for e in getattr(info.value, "exceptions", ())
    )
    assert not (tmp_path / ".connectomekg" / "graph.sqlite").exists()


def test_manifest_answers_without_a_graph_and_creates_nothing(tmp_path):
    result = CliRunner().invoke(cli, ["mcp", "--repo", str(tmp_path), "--manifest"])
    assert result.exit_code == 0, result.output
    m = json.loads(result.output)
    assert m["canonical"] == list(CANONICAL_TOOLS) and m["kind"] == "connectome"
    assert manifest(build_server(tmp_path))["tools"] == m["tools"]
    assert list(tmp_path.iterdir()) == []


def test_sse_is_gone(tmp_path):
    result = CliRunner().invoke(cli, ["mcp", "--repo", str(tmp_path), "--transport", "sse"])
    assert result.exit_code == 2


def test_other_commands_do_not_import_mcp():
    out = subprocess.run(
        [sys.executable, "-c", "import sys, connectomekg.cli; print('mcp' in sys.modules)"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert out == "False"


_SHIM = ["-c", "from connectomekg.mcp_server import main; main()"]
_GROUP = ["-m", "connectomekg.cli"]


def _stdio(args: list[str], cwd: Path, entry: list[str] = _SHIM):
    params = StdioServerParameters(
        command=sys.executable,
        args=[*entry, *args],
        env={**os.environ, "PYTHONPATH": _SRC},
        cwd=str(cwd),
    )

    async def run():
        with open(cwd / "stderr.log", "w", encoding="utf-8") as errlog:
            async with stdio_client(params, errlog=errlog) as (read, write):
                async with ClientSession(read, write) as client:
                    init = await client.initialize()
                    tools = await client.list_tools()
                    stats = await client.call_tool("stats", {})
                    return init, tools, stats

    return anyio.run(run)


def test_connkg_mcp_keeps_root_and_dataset(two_dataset_root):
    init, tools, stats = _stdio(
        ["--root", str(two_dataset_root), "--dataset", "fafb783"], two_dataset_root
    )
    assert (init.serverInfo.name, init.serverInfo.version) == ("connkg", connectomekg.__version__)
    assert [t.name for t in tools.tools][: len(CANONICAL_TOOLS)] == list(CANONICAL_TOOLS)
    assert stats.structuredContent["kind"] == "connectome"
    assert stats.structuredContent["nodes"]["by_kind"]["neuron"] == 600


def test_connkg_group_root_and_dataset_reach_the_server(two_dataset_root):
    """``connkg --root R --dataset D mcp``: the group's options pick the dataset."""
    _, _, stats = _stdio(
        ["--root", str(two_dataset_root), "--dataset", "fafb783", "mcp"],
        two_dataset_root,
        entry=_GROUP,
    )
    assert stats.structuredContent["kind"] == "connectome"
    err = (two_dataset_root / "stderr.log").read_text(encoding="utf-8")
    assert str(dataset_dir(two_dataset_root, "fafb783")) in err
