"""Module contract: kind, stats, analyze, CLI."""

from __future__ import annotations

import pytest

from connectomekg.cli import main


def test_kind_and_stats(kg):
    assert kg.kind() == "connectome"
    s = kg.store.stats()
    assert s["total_nodes"] > 600 and s["total_edges"] > 600


def test_analyze_is_markdown(kg):
    md = kg.analyze()
    assert md.startswith("# ConnectomeKG analysis")
    assert "SYNAPSES_TO" in md and "Coverage" in md and "100.0%" in md


def test_cli_fixture_build_path(tmp_path, capsys):
    data = tmp_path / "codex"
    assert main(["fixture", "--out", str(data), "--n", "400", "--seed", "3"]) == 0
    root = tmp_path / "root"
    root.mkdir()
    assert (
        main(
            [
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
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "--root",
                str(root),
                "path",
                "--dataset-id",
                "synthetic400",
                "--from",
                "GRN_sugar",
                "--to",
                "MN9",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "SEZ_IN1" in out and "MN9" in out
    assert main(["--root", str(root), "stats", "--dataset-id", "synthetic400"]) == 0


def test_query_needs_semantic_extra(kg):
    pytest.importorskip("sentence_transformers")
    kg.build_index(wipe=True)
    res = kg.query("looming detector giant fibre escape", k=5, hop=1)
    names = {n["name"] for n in res.nodes}
    assert names & {"LC4", "LPLC2", "DNp01"}
