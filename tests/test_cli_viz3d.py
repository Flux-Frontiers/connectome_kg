"""Tests for connkg quilt / connkg viz3d -- argument validation only.

No quilt is ever rendered here: these exercise usage errors, the install
hint, and the renders/ path-resolution helpers directly.
"""

from __future__ import annotations

from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from connectomekg import scene as scene_mod
from connectomekg.cli import cli
from connectomekg.cli import cmd_viz3d as mod
from connectomekg.scene import FLOOR_ELEVATION

# ---------------------------------------------------------------------------
# renders/ path resolution -- no CLI invocation
# ---------------------------------------------------------------------------


def test_resolve_preview_path_bare_filename_goes_under_stills(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    resolved = mod.resolve_preview_path("dnp01.png")
    assert resolved == mod.STILLS_DIR / "dnp01.png"
    assert resolved.parent.is_dir()


def test_resolve_preview_path_with_directory_is_used_as_given(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    resolved = mod.resolve_preview_path("out/x.png")
    assert resolved == Path("out/x.png")
    assert resolved.parent.is_dir()


def test_default_quilt_out_dir_is_renders_quilts():
    assert mod.QUILTS_DIR == Path("renders") / "quilts"


def test_sanitize_specs_strips_unsafe_characters():
    assert mod.sanitize_specs(("label:giant fib/x",)) == "label_giant_fib_x"
    assert mod.sanitize_specs(()) == "scene"
    assert mod.sanitize_specs(("LC4", "DNp01")) == "LC4_DNp01"


# ---------------------------------------------------------------------------
# CLI -- --help, usage errors, install hint
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("command", ["quilt", "viz3d"])
def test_help(command):
    result = CliRunner().invoke(cli, [command, "--help"])
    assert result.exit_code == 0, result.output


def test_quilt_unknown_preset_is_a_usage_error(kg, kg_root):
    # The preset is checked after the extra's own import check.
    pytest.importorskip("pyvista")
    pytest.importorskip("quiltwright")
    result = CliRunner().invoke(cli, ["--root", str(kg_root), "quilt", "LC4", "--preset", "nope"])
    assert result.exit_code == 2, result.output
    assert "Unknown quilt preset" in result.output


def test_quilt_over_the_cap_is_a_usage_error(kg, monkeypatch, kg_root):
    pytest.importorskip("pyvista")
    pytest.importorskip("quiltwright")
    monkeypatch.setattr(scene_mod, "MAX_SCENE_NEURONS", 1)
    result = CliRunner().invoke(cli, ["--root", str(kg_root), "quilt", "LC4"])
    assert result.exit_code == 2, result.output
    assert "over the cap of 1" in result.output


def test_quilt_missing_extra_shows_install_hint(kg, monkeypatch, kg_root):
    monkeypatch.setattr(mod.importlib.util, "find_spec", lambda name: None)
    result = CliRunner().invoke(cli, ["--root", str(kg_root), "quilt", "LC4"])
    assert result.exit_code == 2, result.output
    assert 'pip install "connectome-kg[viz3d]"' in result.output


def test_viz3d_missing_extra_shows_install_hint(kg, monkeypatch, kg_root):
    monkeypatch.setattr(mod.importlib.util, "find_spec", lambda name: None)
    result = CliRunner().invoke(cli, ["--root", str(kg_root), "viz3d", "LC4"])
    assert result.exit_code == 2, result.output
    assert 'pip install "connectome-kg[viz3d]"' in result.output


@pytest.mark.parametrize("command", ["quilt", "viz3d"])
def test_circuit_view_requires_at_least_one_spec(command):
    result = CliRunner().invoke(cli, [command])
    assert result.exit_code == 2
    assert "--view circuit needs at least one SPEC" in result.output


def test_quilt_rejects_top_over_the_bound(kg, kg_root):
    result = CliRunner().invoke(
        cli, ["--root", str(kg_root), "quilt", "--view", "flow", "--top", "501"]
    )
    assert result.exit_code == 2


def test_scene_stem_names_flow_renders():
    assert mod.scene_stem("circuit", ("LC4",)) == "LC4"
    assert mod.scene_stem("flow", ()) == "flow"
    assert mod.scene_stem("flow", ("LC4",)) == "flow_LC4"


def test_quilt_rejects_oversized_skeleton_step(kg, kg_root):
    result = CliRunner().invoke(
        cli, ["--root", str(kg_root), "quilt", "LC4", "--skeleton-step", "1000"]
    )
    assert result.exit_code == 2


def test_resolve_elevation_defaults_to_a_look_down_only_with_a_floor():
    assert mod.resolve_elevation(False, None) == 0.0
    assert mod.resolve_elevation(True, None) == FLOOR_ELEVATION
    assert mod.resolve_elevation(True, 10.0) == 10.0


def test_quilt_still_with_cast_is_a_usage_error(kg, kg_root):
    result = CliRunner().invoke(cli, ["--root", str(kg_root), "quilt", "LC4", "--still", "--cast"])
    assert result.exit_code == 2, result.output
    assert "cannot be combined with --still" in result.output


@pytest.mark.parametrize("command", ["quilt", "viz3d"])
def test_elevation_out_of_range_is_a_usage_error(kg, command, kg_root):
    result = CliRunner().invoke(cli, ["--root", str(kg_root), command, "LC4", "--elevation", "95"])
    assert result.exit_code == 2, result.output


def test_quilt_still_writes_one_flat_image_with_a_floor(kg, tmp_path, monkeypatch, kg_root):
    pytest.importorskip("pyvista")
    pytest.importorskip("quiltwright")
    monkeypatch.setattr(mod, "STILL_HEIGHT", 90)
    result = CliRunner().invoke(
        cli,
        [
            "--root",
            str(kg_root),
            "quilt",
            "--view",
            "flow",
            "--still",
            "--floor",
            "-o",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    written = list(tmp_path.glob("flow_qs1x1a*.png"))
    assert len(written) == 1
    assert "adjacent-view disparity" not in result.output  # no depth report for a still


def test_quilt_with_floor_reports_depth_and_writes_a_quilt(kg, tmp_path, monkeypatch, kg_root):
    pytest.importorskip("pyvista")
    quiltwright = pytest.importorskip("quiltwright")
    tiny = quiltwright.QuiltSpec(
        columns=2, rows=1, quilt_width=160, quilt_height=45, aspect=1.77778, view_cone=50.0
    )
    monkeypatch.setitem(quiltwright.QUILT_PRESETS, "tiny", tiny)
    result = CliRunner().invoke(
        cli,
        [
            "--root",
            str(kg_root),
            "quilt",
            "--view",
            "flow",
            "--floor",
            "--preset",
            "tiny",
            "-o",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "adjacent-view disparity" in result.output
    assert "35.0 deg" in result.output  # --view-cone default, not the preset's 50
    assert len(list(tmp_path.glob("flow_qs2x1a*.png"))) == 1


# ---------------------------------------------------------------------------
# connkg path --render / connkg cone --render
# ---------------------------------------------------------------------------


def test_render_answer_draws_the_groups_it_is_given(kg, tmp_path, monkeypatch):
    """The one test here that renders, at a tile small enough to be cheap."""
    pytest.importorskip("pyvista")
    pytest.importorskip("quiltwright")
    monkeypatch.setattr(mod, "STILL_HEIGHT", 120)
    sugar, mn9 = kg.neurons_of("GRN_sugar"), kg.neurons_of("MN9")
    groups = [
        scene_mod.NeuronGroup("hop 0", sugar, "#440154"),
        scene_mod.NeuronGroup("hop 1", mn9, "#FDE725"),
    ]
    written = mod.render_answer(
        kg, groups, stem="test_answer", data_dir=None, out_dir=tmp_path,
        labels=[(mn9[0], "MN9  42 syn")],
    )  # fmt: skip
    assert written.exists() and written.stat().st_size > 0
    assert written.parent == tmp_path
    assert "test_answer" in written.name


def test_render_answer_needs_the_extra(kg, monkeypatch, tmp_path):
    monkeypatch.setattr(mod.importlib.util, "find_spec", lambda name: None)
    with pytest.raises(click.UsageError, match="viz3d"):
        mod.render_answer(kg, [], stem="x", data_dir=None, out_dir=tmp_path)


def test_path_render_writes_a_still(kg, kg_root, tmp_path, monkeypatch):
    pytest.importorskip("pyvista")
    pytest.importorskip("quiltwright")
    monkeypatch.setattr(mod, "STILL_HEIGHT", 120)
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        cli,
        ["--root", str(kg_root), "path", "--from", "GRN_sugar", "--to", "MN9", "--render"],
    )
    assert result.exit_code == 0, result.output
    assert "Wrote" in result.output
    written = list((tmp_path / "renders" / "stills").glob("path_GRN_sugar_to_MN9*.png"))
    assert len(written) == 1, result.output


def test_cone_render_writes_a_still(kg, kg_root, tmp_path, monkeypatch):
    pytest.importorskip("pyvista")
    pytest.importorskip("quiltwright")
    monkeypatch.setattr(mod, "STILL_HEIGHT", 120)
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        cli, ["--root", str(kg_root), "cone", "GRN_sugar", "--hops", "1", "--render"]
    )
    assert result.exit_code == 0, result.output
    written = list((tmp_path / "renders" / "stills").glob("cone_GRN_sugar_down*.png"))
    assert len(written) == 1, result.output


def test_cone_render_over_the_cap_is_a_usage_error(kg, kg_root, monkeypatch):
    pytest.importorskip("pyvista")
    monkeypatch.setattr("connectomekg.validation.MAX_SCENE_NEURONS", 1)
    result = CliRunner().invoke(
        cli, ["--root", str(kg_root), "cone", "GRN_sugar", "--hops", "1", "--render"]
    )
    assert result.exit_code == 2, result.output
    assert "over the cap of 1" in result.output
    # The text answer still printed before the refusal: the query succeeded,
    # only the drawing of it did not.
    assert "hop 0:" in result.output


def test_path_without_render_draws_nothing(kg, kg_root, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        cli, ["--root", str(kg_root), "path", "--from", "GRN_sugar", "--to", "MN9"]
    )
    assert result.exit_code == 0, result.output
    assert "Wrote" not in result.output
    assert not (tmp_path / "renders").exists()
