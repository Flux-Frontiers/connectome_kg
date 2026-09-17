"""Module contract: kind, stats, analyze, CLI."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from connectomekg.cli import cli
from connectomekg.manifest import FAFB_783_FILES, verify_dir
from connectomekg.readers.synthetic import write_codex_dir


def test_kind_and_stats(kg):
    assert kg.kind() == "connectome"
    s = kg.store.stats()
    assert s["total_nodes"] > 600 and s["total_edges"] > 600


def test_analyze_is_markdown(kg):
    md = kg.analyze()
    assert md.startswith("# ConnectomeKG analysis")
    assert "SYNAPSES_TO" in md and "Coverage" in md and "100.0%" in md


def run(*args: str) -> str:
    """Invoke connkg in-process and return its output, failing on a non-zero exit."""
    res = CliRunner().invoke(cli, list(args))
    assert res.exit_code == 0, f"{res.output}\n{res.exception!r}"
    return res.output


def test_cli_fixture_build_path(tmp_path):
    data = tmp_path / "codex"
    run("fixture", "--out", str(data), "--n", "400", "--seed", "3")
    root = tmp_path / "root"
    root.mkdir()
    built = run(
        "--root",
        str(root),
        "build",
        "--data-dir",
        str(data),
        "--source",
        "codex",
        "--dataset-id",
        "synthetic400",
        "--no-index",
        "--wipe",
    )
    # A build reports its stages rather than sitting silent.
    assert "synaptic pairs" in built and "extraction done" in built
    out = run(
        "--root",
        str(root),
        "path",
        "--dataset-id",
        "synthetic400",
        "--from",
        "GRN_sugar",
        "--to",
        "MN9",
    )
    assert "SEZ_IN1" in out and "MN9" in out
    run("--root", str(root), "stats", "--dataset-id", "synthetic400")


def test_cli_rejects_out_of_range_options():
    res = CliRunner().invoke(cli, ["query", "anything", "--k", "0"])
    assert res.exit_code == 2 and "--k" in res.output


def test_query_needs_semantic_extra(kg):
    pytest.importorskip("sentence_transformers")
    kg.build_index(wipe=True)
    res = kg.query("looming detector giant fibre escape", k=5, hop=1)
    names = {n["name"] for n in res.nodes}
    assert names & {"LC4", "LPLC2", "DNp01"}


def test_verify_reports_drift_without_calling_it_a_failure(tables, tmp_path, capsys):
    """The Codex portal updates continually, so a changed digest is not corruption."""
    d = write_codex_dir(tables, tmp_path / "codex")
    # The fixture's files cannot match the real v783 digests, so every file
    # with a recorded checksum drifts.
    report = verify_dir(d, checksums=True)
    assert report.drifted, "expected drift against the recorded v783 digests"
    assert report.ok, "drift alone must not block a build"
    assert not report.missing_required
    assert "ready to build" in str(report)

    # A missing required file is the one hard failure.
    (d / "neurons.csv.gz").unlink()
    broken = verify_dir(d, checksums=False)
    assert not broken.ok and broken.missing_required == ["neurons.csv.gz"]
    with pytest.raises(FileNotFoundError):
        verify_dir(d, checksums=False, strict=True)
    assert all(f.display for f in FAFB_783_FILES), "every file needs its portal label"


def test_files_command_maps_portal_labels_to_file_names():
    out = run("files")
    # The label that sent us looking for a file called "neurons".
    assert "Neurotransmitter Type Predictions" in out and "neurons.csv.gz" in out
    assert "Connections (Filtered)" in out
    assert "zenodo.org/records/10676866" in out


def test_package_is_runnable_without_installing(tmp_path):
    """`python -m connectomekg` must work from a clone; the script needs an install."""
    src = str(Path(__file__).resolve().parents[1] / "src")
    env = {**os.environ, "PYTHONPATH": src}
    out = subprocess.run(
        [sys.executable, "-m", "connectomekg", "files"],
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
        check=True,
    )
    assert "neurons.csv.gz" in out.stdout
