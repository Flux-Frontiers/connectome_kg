"""Tests for connkg quilt / connkg viz3d -- argument validation only.

No quilt is ever rendered here: these exercise usage errors, the install
hint, and the renders/ path-resolution helpers directly.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from connectomekg import scene as scene_mod
from connectomekg.cli import cli
from connectomekg.cli import cmd_viz3d as mod

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


def test_quilt_unknown_preset_is_a_usage_error(kg):
    result = CliRunner().invoke(
        cli, ["--root", str(kg.repo_root), "quilt", "LC4", "--preset", "nope"]
    )
    assert result.exit_code == 2, result.output
    assert "Unknown quilt preset" in result.output


def test_quilt_over_the_cap_is_a_usage_error(kg, monkeypatch):
    monkeypatch.setattr(scene_mod, "MAX_SCENE_NEURONS", 1)
    result = CliRunner().invoke(cli, ["--root", str(kg.repo_root), "quilt", "LC4"])
    assert result.exit_code == 2, result.output
    assert "over the cap of 1" in result.output


def test_quilt_missing_extra_shows_install_hint(kg, monkeypatch):
    monkeypatch.setattr(mod.importlib.util, "find_spec", lambda name: None)
    result = CliRunner().invoke(cli, ["--root", str(kg.repo_root), "quilt", "LC4"])
    assert result.exit_code == 2, result.output
    assert 'pip install "connectome-kg[viz3d]"' in result.output


def test_viz3d_missing_extra_shows_install_hint(kg, monkeypatch):
    monkeypatch.setattr(mod.importlib.util, "find_spec", lambda name: None)
    result = CliRunner().invoke(cli, ["--root", str(kg.repo_root), "viz3d", "LC4"])
    assert result.exit_code == 2, result.output
    assert 'pip install "connectome-kg[viz3d]"' in result.output


def test_quilt_requires_at_least_one_spec():
    result = CliRunner().invoke(cli, ["quilt"])
    assert result.exit_code == 2


def test_quilt_rejects_oversized_skeleton_step(kg):
    result = CliRunner().invoke(
        cli, ["--root", str(kg.repo_root), "quilt", "LC4", "--skeleton-step", "1000"]
    )
    assert result.exit_code == 2
