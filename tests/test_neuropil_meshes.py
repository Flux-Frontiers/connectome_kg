"""Neuropil meshes: fragment decoding, the fetch-and-cache round trip, the scene, ``connkg meshes``."""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
import pytest
from click.testing import CliRunner

from connectomekg.cli import cli, cmd_data
from connectomekg.neuropil_meshes import (
    FAFB_783_MESH_NAMES,
    MESH_CACHE,
    decode_fragment,
    fetch_neuropil_meshes,
    has_mesh_source,
    load_neuropil_meshes,
    neuropil_mesh_path,
)
from connectomekg.neuropils import NEUROPIL_NAMES, UNPAIRED, split_neuropil

TETRA_VERTICES = np.array([[0, 0, 0], [1e4, 0, 0], [0, 1e4, 0], [0, 0, 1e4]], dtype=np.float32)
TETRA_FACES = np.array([[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]], dtype=np.uint32)


def fragment(vertices: np.ndarray, faces: np.ndarray) -> bytes:
    """Encode a legacy Neuroglancer mesh fragment."""
    return (
        struct.pack("<I", len(vertices))
        + vertices.astype("<f4").tobytes()
        + faces.astype("<u4").tobytes()
    )


def fake_fetch(urls: list[str]):
    def fetch(url: str) -> bytes:
        urls.append(url)
        return fragment(TETRA_VERTICES, TETRA_FACES)

    return fetch


def test_decode_fragment_round_trips():
    vertices, faces = decode_fragment(fragment(TETRA_VERTICES, TETRA_FACES))
    np.testing.assert_array_equal(vertices, TETRA_VERTICES)
    np.testing.assert_array_equal(faces, TETRA_FACES)


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"\x01", "shorter than its header"),
        (struct.pack("<I", 5) + b"\x00" * 12, "does not hold 5 vertices"),
        (b"<?xml version='1.0'?><Error>NoSuchKey</Error>", "does not hold"),
        (fragment(TETRA_VERTICES, np.array([[0, 1, 9]], dtype=np.uint32)), "beyond its vertices"),
    ],
)
def test_decode_fragment_rejects_malformed_bytes(data, message):
    with pytest.raises(ValueError, match=message):
        decode_fragment(data)


def test_the_name_table_is_78_distinct_flywire_neuropils():
    names = list(FAFB_783_MESH_NAMES.values())
    assert sorted(FAFB_783_MESH_NAMES) == list(range(78))
    assert len(set(names)) == 78
    for name in names:
        base, side = split_neuropil(name)
        assert base in NEUROPIL_NAMES
        assert (side == "M") == (base in UNPAIRED)
    # The one v783 neuropil with no surface: synapses no volume claimed.
    assert "UNASGD" not in names


def test_fetch_caches_every_named_mesh(tmp_path):
    urls: list[str] = []
    messages: list[str] = []
    dest = fetch_neuropil_meshes(
        "fafb783", tmp_path / MESH_CACHE, fetch=fake_fetch(urls), progress=messages.append
    )
    assert len(urls) == 78
    assert urls[0].endswith("/neuropil_mesh_v141_v6/mesh/0:0:0")
    assert messages[-1] == "fetched 78 of 78 neuropil meshes"
    meshes = load_neuropil_meshes(dest)
    assert set(meshes) == set(FAFB_783_MESH_NAMES.values())
    np.testing.assert_array_equal(meshes["LO_R"][0], TETRA_VERTICES)
    assert list(tmp_path.iterdir()) == [dest]  # no partial file left behind


def test_a_bad_fragment_leaves_the_old_cache_alone(tmp_path):
    dest = fetch_neuropil_meshes("fafb783", tmp_path / MESH_CACHE, fetch=fake_fetch([]))
    before = dest.read_bytes()

    def broken(url: str) -> bytes:
        return b"<Error/>" if url.endswith("/5:0:0") else fragment(TETRA_VERTICES, TETRA_FACES)

    with pytest.raises(ValueError):
        fetch_neuropil_meshes("fafb783", dest, fetch=broken)
    assert dest.read_bytes() == before


def test_fetch_refuses_a_dataset_without_meshes(tmp_path):
    assert has_mesh_source("fafb783") and not has_mesh_source("synthetic")
    with pytest.raises(ValueError, match="no neuropil meshes published for dataset 'synthetic'"):
        fetch_neuropil_meshes("synthetic", tmp_path / MESH_CACHE, fetch=fake_fetch([]))


# ---------------------------------------------------------------------------
# The scene -- needs PyVista
# ---------------------------------------------------------------------------


@pytest.fixture
def mesh_cache(kg):
    """A mesh cache beside the session graph, removed afterwards so other tests never see it."""
    path = neuropil_mesh_path(kg.db_path)
    fetch_neuropil_meshes("fafb783", path, fetch=fake_fetch([]))
    yield path
    path.unlink()


def test_circuit_view_draws_neutral_neuropil_shells(kg, mesh_cache):
    pv = pytest.importorskip("pyvista")
    from connectomekg import scene  # noqa: PLC0415

    plotter = pv.Plotter(off_screen=True)
    info = scene.build_brain_scene(plotter, kg, specs=["LC4"])
    assert info.n_neuropil_meshes == 78
    assert "neuropils" in plotter.actors


def test_meshes_replace_the_cloud_unless_it_is_asked_for(kg, mesh_cache):
    """The cloud defaults off once surfaces are drawn, and `cloud=True` overrides that."""
    pv = pytest.importorskip("pyvista")
    from connectomekg import scene  # noqa: PLC0415

    plotter = pv.Plotter(off_screen=True)
    default = scene.build_brain_scene(plotter, kg, specs=["LC4"])
    assert default.n_context == 0 and "context" not in plotter.actors

    plotter = pv.Plotter(off_screen=True)
    asked = scene.build_brain_scene(plotter, kg, specs=["LC4"], cloud=True)
    assert asked.n_context > 0 and "context" in plotter.actors


def test_without_meshes_the_cloud_still_draws_by_default(kg):
    pv = pytest.importorskip("pyvista")
    from connectomekg import scene  # noqa: PLC0415

    plotter = pv.Plotter(off_screen=True)
    info = scene.build_brain_scene(plotter, kg, specs=["LC4"])
    assert info.n_neuropil_meshes == 0
    assert info.n_context > 0 and "context" in plotter.actors


def test_flow_view_tints_neuropils_by_region(kg, mesh_cache):
    pv = pytest.importorskip("pyvista")
    from connectomekg import scene  # noqa: PLC0415

    plotter = pv.Plotter(off_screen=True)
    info = scene.build_brain_scene(plotter, kg, view="flow")
    tinted = {name for name in plotter.actors if name.startswith("neuropils:")}
    regions = {scene.region_color(n) for n in FAFB_783_MESH_NAMES.values()}
    assert info.n_neuropil_meshes == 78
    assert tinted == {f"neuropils:{c}" for c in regions}


def test_no_cloud_and_no_neuropils_draw_neither(kg, mesh_cache):
    pv = pytest.importorskip("pyvista")
    from connectomekg import scene  # noqa: PLC0415

    plotter = pv.Plotter(off_screen=True)
    info = scene.build_brain_scene(plotter, kg, specs=["LC4"], neuropils=False, cloud=False)
    assert info.n_context == 0 and info.n_neuropil_meshes == 0
    assert "context" not in plotter.actors and "neuropils" not in plotter.actors
    assert "fallback:LC4" in plotter.actors


def test_without_a_cache_the_scene_says_how_to_fetch_one(kg):
    pv = pytest.importorskip("pyvista")
    from connectomekg import scene  # noqa: PLC0415

    messages: list[str] = []
    plotter = pv.Plotter(off_screen=True)
    info = scene.build_brain_scene(plotter, kg, progress=messages.append)
    assert info.n_neuropil_meshes == 0
    assert "no neuropil meshes cached; `connkg meshes` fetches them" in messages


# ---------------------------------------------------------------------------
# connkg meshes
# ---------------------------------------------------------------------------


def test_meshes_command_refuses_a_dataset_without_meshes(kg, kg_root):
    res = CliRunner().invoke(cli, ["--root", str(kg_root), "meshes"])
    assert res.exit_code == 2
    assert "no neuropil meshes published for dataset 'synthetic'" in res.output


def test_meshes_command_writes_the_cache_beside_the_graph(kg, kg_root, monkeypatch):
    calls: list[tuple[str, Path]] = []

    def fetch(dataset_id, dest, *, progress):
        calls.append((dataset_id, Path(dest)))
        return Path(dest)

    monkeypatch.setattr(cmd_data, "fetch_neuropil_meshes", fetch)
    res = CliRunner().invoke(cli, ["--root", str(kg_root), "meshes"])
    assert res.exit_code == 0, res.output
    assert calls == [("synthetic", neuropil_mesh_path(kg.db_path))]
    assert f"wrote {neuropil_mesh_path(kg.db_path)}" in res.stdout


@pytest.mark.parametrize("command", ["quilt", "viz3d"])
def test_render_commands_offer_the_neuropil_and_cloud_switches(command):
    res = CliRunner().invoke(cli, [command, "--help"])
    assert "--neuropils / --no-neuropils" in res.output
    assert "--cloud / --no-cloud" in res.output
