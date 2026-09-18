"""One graph per dataset under ``<root>/connectomes/<dataset>/``."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from connectomekg import mcp_server
from connectomekg.cli import cli
from connectomekg.datasets import dataset_dir, graph_path, resolve_dataset, scan_datasets


def _run(*args: str, ok: bool = True):
    res = CliRunner().invoke(cli, list(args))
    if ok:
        assert res.exit_code == 0, f"{res.output}\n{res.exception!r}"
    return res


@pytest.fixture(scope="module")
def two(tmp_path_factory):
    """A root holding two synthetic datasets of different sizes."""
    root = str(tmp_path_factory.mktemp("two"))
    for name, n in (("small", 400), ("large", 700)):
        _run(
            "--root",
            root,
            "--dataset",
            name,
            "build",
            "--source",
            "synthetic",
            "--n",
            str(n),
            "--no-index",
        )
    return root


def test_each_dataset_has_its_own_graph(two):
    assert scan_datasets(two) == ["large", "small"]
    small = _run("--root", two, "--dataset", "small", "stats").output
    large = _run("--root", two, "--dataset", "large", "stats").output
    assert small != large
    assert graph_path(two, "small") != graph_path(two, "large")


def test_datasets_lists_every_built_dataset(two):
    out = _run("--root", two, "datasets").output
    rows = {line.split()[0] for line in out.splitlines()[1:]}
    assert rows == {"small", "large"} and " MB " in out


def test_several_datasets_need_one_named(two):
    res = _run("--root", two, "stats", ok=False)
    assert res.exit_code == 2
    assert "large, small" in res.output and "--dataset" in res.output


def test_snapshots_are_kept_per_dataset(two):
    _run("--root", two, "--dataset", "small", "snapshot", "save", "v1")
    assert (dataset_dir(two, "small") / ".connectomekg" / "snapshots" / "v1.json").is_file()
    assert "no snapshots" in _run("--root", two, "--dataset", "large", "snapshot", "list").output


def test_the_only_built_dataset_is_the_default(tmp_path):
    root = str(tmp_path)
    _run("--root", root, "build", "--source", "synthetic", "--n", "400", "--no-index")
    assert scan_datasets(root) == ["synthetic"]
    assert "neuron" in _run("--root", root, "stats").output


@pytest.mark.parametrize("bad", ["../escape", "FAFB", "a/b", ".hidden", ""])
def test_unsafe_dataset_ids_are_rejected(tmp_path, bad):
    if not bad:
        # An empty --dataset means "not given", so it falls through to the scan.
        with pytest.raises(ValueError, match="no dataset is built"):
            resolve_dataset(tmp_path, bad)
        return
    with pytest.raises(ValueError, match="invalid dataset id"):
        resolve_dataset(tmp_path, bad)
    res = _run("--root", str(tmp_path), "--dataset", bad, "stats", ok=False)
    assert res.exit_code == 2 and "invalid dataset id" in res.output


def test_a_pre_dataset_store_gets_a_move_hint(tmp_path):
    legacy = tmp_path / ".connectomekg"
    legacy.mkdir()
    (legacy / "graph.sqlite").write_bytes(b"x")
    with pytest.raises(ValueError, match=r"mv .*\.connectomekg/\*\.sqlite\*"):
        resolve_dataset(tmp_path)


def test_mcp_server_opens_the_named_dataset(two, monkeypatch):
    monkeypatch.setattr(mcp_server.mcp, "run", lambda transport: None)
    try:
        mcp_server.main(["--root", two, "--dataset", "large"])
        assert mcp_server._kg.db_path == graph_path(two, "large").resolve()
        with pytest.raises(SystemExit, match="name one with --dataset"):
            mcp_server.main(["--root", two])
    finally:
        mcp_server._kg = None
        mcp_server._snapshot_mgr = None
