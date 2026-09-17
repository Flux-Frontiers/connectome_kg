"""Per-run build reports and graph snapshots, through the CLI."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from connectomekg.cli import cli
from connectomekg.readers.synthetic import write_codex_dir


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
        "build",
        "--data-dir",
        str(data),
        "--dataset-id",
        "synthetic",
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
    assert "subject  dataset:synthetic" in out
    # Saving unchanged metrics refreshes the entry instead of adding one.
    _run("--root", root, "snapshot", "save")
    listed = json.loads(_run("--root", root, "snapshot", "list", "--json").output)
    assert len(listed) == 1

    snap = json.loads(_run("--root", root, "snapshot", "show").output)
    assert snap["tool"] == "connectome-kg" and snap["subject"] == "dataset:synthetic"
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
