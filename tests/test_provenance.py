"""Per-run build reports and graph snapshots, through the CLI."""

from __future__ import annotations

import json
import re
import sqlite3

import numpy as np
import pytest
from click.testing import CliRunner

from connectomekg.cli import cli
from connectomekg.readers.synthetic import write_codex_dir
from connectomekg.skeletons import Skeleton, skeleton_path, write_swc


def _run(*args: str, ok: bool = True):
    res = CliRunner().invoke(cli, list(args))
    if ok:
        assert res.exit_code == 0, f"{res.output}\n{res.exception!r}"
    return res


@pytest.fixture(scope="module")
def built(tables, tmp_path_factory):
    data = write_codex_dir(tables, tmp_path_factory.mktemp("codex"))
    root = tmp_path_factory.mktemp("root")
    _run(
        "--root",
        str(root),
        "--dataset",
        "synthetic",
        "build",
        "--data-dir",
        str(data),
        "--no-index",
        "--wipe",
    )
    return root


def test_build_writes_a_provenance_report(built):
    reports = sorted((built / "reports").glob("build_*.md"))
    assert len(reports) == 1
    text = reports[0].read_text()
    assert "**Status:** SUCCESS" in text
    assert "**Peak memory:**" in text and "**kgmodule-utils:**" in text
    assert "| data_dir |" in text and "| no_index | `True` |" in text
    # Every input is hashed; the fixture's files cannot match the v783 digests.
    assert "| neurons.csv.gz |" in text and "differs (portal drift)" in text
    assert "| processed_labels.csv.gz |" in text and "no recorded digest" in text
    # Stages come from the progress messages; counters inside a stage do not.
    assert "| synaptic pairs (" in text and "| extraction done;" in text
    assert "| neuron |" in text and "| SYNAPSES_TO |" in text


def test_a_failed_build_still_leaves_a_report(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    res = _run("--root", str(tmp_path), "build", "--data-dir", str(empty), "--no-index", ok=False)
    assert res.exit_code != 0
    (report,) = (tmp_path / "reports").glob("build_*.md")
    text = report.read_text()
    assert "**Status:** FAILED: FileNotFoundError" in text
    assert "## Output" not in text


def test_snapshot_save_list_show_diff(built):
    root = str(built)
    out = _run("--root", root, "snapshot", "save").output
    assert "subject  corpus:synthetic" in out
    # Saving unchanged metrics refreshes the entry instead of adding one.
    _run("--root", root, "snapshot", "save")
    listed = json.loads(_run("--root", root, "snapshot", "list", "--json").output)
    assert len(listed) == 1

    snap = json.loads(_run("--root", root, "snapshot", "show").output)
    assert snap["tool"] == "connectome-kg" and snap["subject"] == "corpus:synthetic"
    m = snap["metrics"]
    assert m["n_neurons"] == 600 and m["coverage"]["cell_type"] == 1.0
    assert m["node_counts"]["neuron"] == 600
    assert (
        snap["hotspots"] and snap["hotspots"][0]["n_out_syn"] >= snap["hotspots"][-1]["n_out_syn"]
    )

    _run("--root", root, "snapshot", "save", "v9", "--force")
    diff = _run("--root", root, "snapshot", "diff", listed[0]["key"], "v9").output
    assert "total_nodes" in diff and "n_synapses" in diff


def test_snapshot_save_needs_a_built_graph(tmp_path):
    res = _run("--root", str(tmp_path), "snapshot", "save", ok=False)
    assert res.exit_code != 0 and "run `connkg build` first" in res.output


def test_snapshot_save_matches_the_fleet_cli_contract():
    """``snapshot save [OPTIONS] VERSION``, no ``--key``: the fleet-wide contract."""
    res = _run("snapshot", "save", "--help")
    assert "[OPTIONS] VERSION" in res.output
    assert "--key" not in res.output


def test_snapshot_keys_on_version_or_timestamp_never_the_tree_hash(tables, tmp_path):
    data = write_codex_dir(tables, tmp_path / "codex")
    root = str(tmp_path / "root")
    _run("--root", root, "--dataset", "synthetic", "build", "--data-dir", str(data), "--no-index")
    snaps = tmp_path / "root" / "connectomes" / "synthetic" / ".connectomekg" / "snapshots"

    _run("--root", root, "snapshot", "save", "0.2.0", "--force")
    tagged = json.loads((snaps / "0.2.0.json").read_text())
    assert tagged["key"] == "0.2.0"
    assert tagged["tree_hash"] != tagged["key"]

    _run("--root", root, "snapshot", "save", "--force", "--subject", "repo:connectome-kg")
    (entry,) = [
        e
        for e in json.loads((snaps / "manifest.json").read_text())["snapshots"]
        if e["key"] != "0.2.0"
    ]
    # A UTC timestamp, not a 40-character hex tree hash.
    assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", entry["key"])
    assert not re.fullmatch(r"[0-9a-f]{40}", entry["key"])
    assert (
        json.loads(_run("--root", root, "snapshot", "show", entry["key"]).output)["subject"]
        == "repo:connectome-kg"
    )


@pytest.fixture(scope="module")
def download(tmp_path_factory, built):
    """A skeleton directory for the built graph: three quarters of its neurons."""
    db = built / "connectomes" / "synthetic" / ".connectomekg" / "graph.sqlite"
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        ids = [
            int(r[0])
            for r in con.execute(
                "SELECT json_extract(metadata,'$.root_id') FROM nodes WHERE kind='neuron' "
                "ORDER BY id"
            )
        ]
    finally:
        con.close()
    data = tmp_path_factory.mktemp("swc")
    (data / "sk_lod1_783_healed").mkdir()
    for k, root_id in enumerate(ids[: len(ids) * 3 // 4]):
        n = 12
        points = np.stack([np.arange(n, dtype=float), np.zeros(n), np.zeros(n)], axis=1)
        labels = np.zeros(n, dtype=np.int64)
        if k % 5:  # every fifth skeleton has no soma row, so fallbacks are counted
            labels[0] = 1
        parent = np.array([-1] + list(range(n - 1)), dtype=np.int64)
        write_swc(
            Skeleton(root_id, points, np.full(n, 5.0), labels, parent),
            skeleton_path(data, root_id),
        )
    return data, len(ids)


def test_skeletons_writes_a_provenance_report(built, download):
    data, n_neurons = download
    n_cached = n_neurons * 3 // 4
    _run("--root", str(built), "--dataset", "synthetic", "skeletons", "--data-dir", str(data))

    (report,) = (built / "reports").glob("skeletons_*.md")
    text = report.read_text()
    assert "**Status:** SUCCESS" in text
    assert "**Peak memory:**" in text and "**kgmodule-utils:**" in text
    assert "| command | `skeletons` |" in text and "| step | `4` |" in text
    assert f"{n_cached:,} `.swc` files" in text
    assert f"| neurons cached | {n_cached:,} |" in text
    assert f"| no skeleton file | {n_neurons - n_cached:,} |" in text
    # The soma back-fill is the half a build report cannot describe.
    assert f"{n_cached:,} neuron nodes gained" in text
    assert "Snapshots taken before this pass" in text


def test_skeletons_report_records_a_graph_it_left_alone(built, download):
    data, _ = download
    for stale in (built / "reports").glob("skeletons_*.md"):
        stale.unlink()
    _run(
        "--root", str(built), "--dataset", "synthetic",
        "skeletons", "--data-dir", str(data), "--no-somas",
    )  # fmt: skip

    (report,) = (built / "reports").glob("skeletons_*.md")
    text = report.read_text()
    assert "| no_somas | `True` |" in text
    assert "was not modified (--no-somas)." in text
    assert "neuron nodes gained" not in text


def test_a_failed_skeletons_pass_still_leaves_a_report(tmp_path, tables, download):
    data, _ = download
    codex = write_codex_dir(tables, tmp_path / "codex")
    _run(
        "--root", str(tmp_path), "--dataset", "synthetic",
        "build", "--data-dir", str(codex), "--no-index", "--wipe",
    )  # fmt: skip
    # A directory where the cache file goes: the pass reads every skeleton,
    # then fails renaming its partial into place.
    store = tmp_path / "connectomes" / "synthetic" / ".connectomekg"
    (store / "skeletons.parquet").mkdir()
    (store / "skeletons.parquet" / "occupied").touch()

    res = _run(
        "--root", str(tmp_path), "--dataset", "synthetic",
        "skeletons", "--data-dir", str(data), ok=False,
    )  # fmt: skip

    assert res.exit_code != 0
    (report,) = (tmp_path / "reports").glob("skeletons_*.md")
    text = report.read_text()
    assert "**Status:** FAILED" in text
    assert "Nothing was written." in text
    # The graph is reported untouched, because the somas are written last.
    assert "neuron nodes gained" not in text
    # And the partial is cleaned up rather than left as hundreds of megabytes.
    assert not (store / "skeletons.part").exists()
