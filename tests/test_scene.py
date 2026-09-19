"""Tests for connectomekg.scene against the synthetic fixture (600 neurons).

Split like the module itself: world-frame/point-set tests need no PyVista;
the scene composition tests do (``pytest.importorskip("pyvista")``).
"""

from __future__ import annotations

import re

import numpy as np
import pytest

from connectomekg import scene
from connectomekg.colors import REGION_COLOR, UNKNOWN_COLOR
from connectomekg.neuropils import NEUROPIL_NAMES, NEUROPIL_REGION, REGION_NAMES
from connectomekg.skeletons import Skeleton, write_swc

_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


class _FakeKG:
    """A stand-in with just enough surface for circuit_neurons's cap check."""

    def __init__(self, mapping: dict[str, list[str]]) -> None:
        self._mapping = mapping

    def neurons_of(self, spec: str) -> list[str]:
        return self._mapping[spec]


# ---------------------------------------------------------------------------
# Pure -- no PyVista
# ---------------------------------------------------------------------------


def test_world_frame_centers_on_the_median_neuron_position(kg):
    rows = kg.store.con.execute(
        "SELECT json_extract(metadata,'$.x'), json_extract(metadata,'$.y'), "
        "json_extract(metadata,'$.z') FROM nodes WHERE kind='neuron' "
        "AND json_extract(metadata,'$.x') IS NOT NULL"
    ).fetchall()
    expected = np.median(np.asarray(rows, dtype=np.float64), axis=0)
    frame = scene.world_frame(kg.store)
    np.testing.assert_allclose(frame.center, expected)
    assert frame.scale == scene.NM_PER_WORLD_UNIT


def test_to_world_puts_dorsal_up():
    frame = scene.WorldFrame(center=np.array([0.0, 0.0, 0.0]), scale=1.0)
    # FAFB y grows ventrally: a smaller y is more dorsal and must land at a
    # larger world z.
    dorsal = frame.to_world(np.array([0.0, -10.0, 0.0]))[0]
    ventral = frame.to_world(np.array([0.0, 10.0, 0.0]))[0]
    assert dorsal[2] > ventral[2]


def test_to_world_centers_and_scales():
    frame = scene.WorldFrame(center=np.array([100.0, 200.0, 300.0]), scale=100_000.0)
    world = frame.to_world(np.array([100.0 + 100_000.0, 200.0, 300.0]))[0]
    np.testing.assert_allclose(world, [1.0, 0.0, 0.0])


def test_context_points_every_coordinate_neuron_appears_once(kg):
    n_expected = kg.store.con.execute(
        "SELECT COUNT(*) FROM nodes WHERE kind='neuron' "
        "AND json_extract(metadata,'$.x') IS NOT NULL"
    ).fetchone()[0]
    ids, points, colors, n_somas = scene.context_points(kg.store)
    assert len(ids) == len(set(ids)) == n_expected
    assert n_somas == 0
    assert points.shape == (n_expected, 3)
    assert len(colors) == n_expected


def test_context_points_colors_are_valid_hex(kg):
    _, _, colors, _ = scene.context_points(kg.store, color_by="super_class")
    assert all(_HEX.match(c) for c in colors)
    _, _, colors, _ = scene.context_points(kg.store, color_by="sign")
    assert all(_HEX.match(c) for c in colors)


def test_context_points_rejects_bad_color_by(kg):
    with pytest.raises(ValueError, match="color_by"):
        scene.context_points(kg.store, color_by="mood")


def test_circuit_neurons_unions_and_dedupes_specs(kg):
    lc4 = kg.neurons_of("LC4")
    dnp01 = kg.neurons_of("DNp01")
    result = scene.circuit_neurons(kg, ["LC4", "DNp01", "LC4"])
    assert result == sorted(set(lc4) | set(dnp01))


def test_circuit_neurons_raises_over_the_cap(monkeypatch):
    monkeypatch.setattr(scene, "MAX_SCENE_NEURONS", 3)
    fake = _FakeKG({"big": [f"connectome:x:n:{i}" for i in range(10)]})
    with pytest.raises(ValueError, match="10 neurons.*over the cap of 3"):
        scene.circuit_neurons(fake, ["big"])


def test_every_neuropil_has_a_region_and_every_region_a_colour():
    assert set(NEUROPIL_NAMES) <= set(NEUROPIL_REGION)
    assert set(NEUROPIL_REGION.values()) == set(REGION_NAMES) == set(REGION_COLOR)
    assert all(_HEX.match(c) for c in REGION_COLOR.values())


def test_region_color_ignores_side_and_falls_back_to_grey():
    assert scene.region_color("LO_L") == scene.region_color("LO_R") == REGION_COLOR["OL"]
    assert scene.region_color("ME_R") == REGION_COLOR["OL"]
    assert scene.region_color("FB") == REGION_COLOR["CX"]
    assert scene.region_color("NOT_A_NEUROPIL") == UNKNOWN_COLOR


def test_type_color_is_deterministic_and_valid_hex():
    a = scene.type_color("LC4")
    b = scene.type_color("LC4")
    assert a == b
    assert _HEX.match(a)
    assert a in scene._TYPE_PALETTE


class _FlowStore:
    """An in-memory store with the nodes/edges columns neuropil_flow reads."""

    def __init__(self, neurons, neuropils, in_neuropil) -> None:
        import json  # noqa: PLC0415
        import sqlite3  # noqa: PLC0415

        self.con = sqlite3.connect(":memory:")
        self.con.execute("CREATE TABLE nodes (id TEXT, kind TEXT, name TEXT, metadata TEXT)")
        self.con.execute("CREATE TABLE edges (src TEXT, rel TEXT, dst TEXT, evidence TEXT)")
        for nid, xyz in neurons.items():
            meta = dict(zip("xyz", xyz, strict=True))
            self.con.execute(
                "INSERT INTO nodes VALUES (?,'neuron',?,?)", (nid, nid, json.dumps(meta))
            )
        for name, n_syn in neuropils.items():
            meta = {"base": name.split("_")[0], "n_synapses": n_syn}
            self.con.execute(
                "INSERT INTO nodes VALUES (?,'neuropil',?,?)",
                (f"np:{name}", name, json.dumps(meta)),
            )
        for nid, name, pre, post in in_neuropil:
            self.con.execute(
                "INSERT INTO edges VALUES (?,'IN_NEUROPIL',?,?)",
                (nid, f"np:{name}", json.dumps({"pre": pre, "post": post})),
            )


def _two_neuron_store() -> _FlowStore:
    # n1: input 30 in A and 10 in B; output 20 in B and 40 in C.
    # n2: input only in C (5); output 50 in A. n2 has no coordinates.
    return _FlowStore(
        neurons={"n1": (0.0, 0.0, 0.0)},
        neuropils={"A_L": 100, "B_L": 50, "C_R": 10},
        in_neuropil=[
            ("n1", "A_L", 0, 30),
            ("n1", "B_L", 20, 10),
            ("n1", "C_R", 40, 0),
            ("n2", "C_R", 0, 5),
            ("n2", "A_L", 50, 0),
        ],
    )


def test_neuropil_flow_apportions_output_by_input_share():
    flow = scene.neuropil_flow(_two_neuron_store())
    pairs = {(a, b): w for a, b, w in flow.pairs}
    # n1: 3/4 of its input is in A, 1/4 in B.
    assert pairs[("A_L", "B_L")] == pytest.approx(20 * 0.75)
    assert pairs[("A_L", "C_R")] == pytest.approx(40 * 0.75)
    assert pairs[("B_L", "C_R")] == pytest.approx(40 * 0.25)
    assert pairs[("C_R", "A_L")] == pytest.approx(50.0)  # all of n2's input is in C
    assert ("B_L", "B_L") not in pairs  # intrinsic flow is excluded
    assert [w for _, _, w in flow.pairs] == sorted((w for _, _, w in flow.pairs), reverse=True)


def test_neuropil_flow_restricts_the_sum_but_not_the_centroids():
    store = _two_neuron_store()
    everyone = scene.neuropil_flow(store)
    only_n2 = scene.neuropil_flow(store, ["n2"])
    assert only_n2.pairs == [("C_R", "A_L", 50.0)]
    np.testing.assert_array_equal(only_n2.centroids_nm, everyone.centroids_nm)


def test_neuropil_flow_centroids_skip_neurons_without_coordinates():
    flow = scene.neuropil_flow(_two_neuron_store())
    assert flow.names == ["A_L", "B_L", "C_R"]
    assert flow.bases == ["A", "B", "C"]
    # Every neuropil has n1 (at the origin) in it, so every centroid is the origin.
    np.testing.assert_allclose(flow.centroids_nm, np.zeros((3, 3)))
    np.testing.assert_array_equal(flow.n_synapses, [100, 50, 10])


def test_neuropil_flow_on_the_fixture_is_well_formed(kg):
    flow = scene.neuropil_flow(kg.store)
    assert flow.pairs
    assert all(a != b and w > 0 for a, b, w in flow.pairs)
    assert set(flow.names) >= {name for a, b, _ in flow.pairs for name in (a, b)}


def test_flow_arc_ends_on_its_endpoints_and_opposite_directions_bow_apart():
    start, end = np.array([0.0, 0.0, 0.0]), np.array([2.0, 0.0, 0.0])
    forward = scene.flow_arc(start, end, n_points=9)
    backward = scene.flow_arc(end, start, n_points=9)
    np.testing.assert_allclose(forward[0], start)
    np.testing.assert_allclose(forward[-1], end)
    assert forward[4, 1] * backward[4, 1] < 0  # midpoints on opposite sides


def test_flow_arc_vertical_chord_still_bows():
    arc = scene.flow_arc(np.zeros(3), np.array([0.0, 0.0, 1.0]), n_points=5)
    assert abs(arc[2, 0]) > 0


# ---------------------------------------------------------------------------
# Scene composition -- needs the viz3d extra
# ---------------------------------------------------------------------------


def _lc4_root_ids(kg) -> list[int]:
    return [int(kg.store.node(nid)["metadata"]["root_id"]) for nid in kg.neurons_of("LC4")]


def _write_stub_skeleton(swc_dir, root_id: int) -> None:
    points = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]])
    labels = np.array([1, 0, 6])  # soma at the root, end at the tip
    parent = np.array([-1, 0, 1])
    radius = np.full(3, 50.0)
    write_swc(
        Skeleton(root_id=root_id, points=points, radius=radius, labels=labels, parent=parent),
        swc_dir / f"{root_id}.swc",
    )


def test_build_brain_scene_context_only(kg):
    pv = pytest.importorskip("pyvista")
    plotter = pv.Plotter(off_screen=True)
    info = scene.build_brain_scene(plotter, kg)
    assert "context" in plotter.actors
    assert plotter.background_color == scene.BACKGROUND
    assert info.n_context > 0
    assert info.n_circuit == 0
    assert info.n_skeletons == 0
    assert info.missing_skeletons == []


def test_build_brain_scene_without_data_dir_falls_back_to_marked_points(kg):
    pv = pytest.importorskip("pyvista")
    plotter = pv.Plotter(off_screen=True)
    info = scene.build_brain_scene(plotter, kg, specs=["LC4"])
    n_lc4 = len(kg.neurons_of("LC4"))
    assert info.n_circuit == n_lc4
    assert info.n_skeletons == 0
    assert len(info.missing_skeletons) == n_lc4
    assert "fallback:LC4" in plotter.actors
    assert "skeleton:LC4" not in plotter.actors


def test_build_brain_scene_loads_skeletons_and_reports_one_missing(kg, tmp_path):
    pv = pytest.importorskip("pyvista")
    root_ids = _lc4_root_ids(kg)
    swc_dir = tmp_path / "sk_lod1_783_healed"
    swc_dir.mkdir()
    present = root_ids[:-1]
    missing = root_ids[-1]
    for rid in present:
        _write_stub_skeleton(swc_dir, rid)

    plotter = pv.Plotter(off_screen=True)
    info = scene.build_brain_scene(plotter, kg, specs=["LC4"], data_dir=tmp_path, skeleton_step=1)
    assert info.n_circuit == len(root_ids)
    assert info.n_skeletons == len(present)
    assert info.missing_skeletons == [missing]
    assert info.soma_fallbacks == 0  # every stub skeleton has a Label 1 row
    assert "skeleton:LC4" in plotter.actors
    assert "soma:LC4" in plotter.actors
    assert "fallback:LC4" in plotter.actors  # the one missing neuron


def test_build_brain_scene_points_bounds_contain_the_circuit(kg, tmp_path):
    pv = pytest.importorskip("pyvista")
    root_ids = _lc4_root_ids(kg)
    swc_dir = tmp_path / "sk_lod1_783_healed"
    swc_dir.mkdir()
    for rid in root_ids:
        _write_stub_skeleton(swc_dir, rid)

    plotter = pv.Plotter(off_screen=True)
    info = scene.build_brain_scene(plotter, kg, specs=["LC4"], data_dir=tmp_path)
    frame = scene.world_frame(kg.store)
    for nid in kg.neurons_of("LC4"):
        meta = kg.store.node(nid)["metadata"]
        world_pt = frame.to_world(np.array([meta["x"], meta["y"], meta["z"]]))[0]
        assert np.all(info.points.min(axis=0) - 1e-6 <= world_pt)
        assert np.all(world_pt <= info.points.max(axis=0) + 1e-6)


def test_build_brain_scene_rejects_bad_color_by(kg):
    pv = pytest.importorskip("pyvista")
    plotter = pv.Plotter(off_screen=True)
    with pytest.raises(ValueError, match="color_by"):
        scene.build_brain_scene(plotter, kg, color_by="mood")


def test_build_brain_scene_rejects_oversized_skeleton_step(kg):
    pv = pytest.importorskip("pyvista")
    plotter = pv.Plotter(off_screen=True)
    with pytest.raises(ValueError, match="skeleton_step must be between 1 and 50"):
        scene.build_brain_scene(plotter, kg, skeleton_step=1000)


def test_build_brain_scene_reports_a_soma_fallback(kg, tmp_path):
    """A skeleton with no Label 1 row counts toward soma_fallbacks."""
    pv = pytest.importorskip("pyvista")
    root_ids = _lc4_root_ids(kg)
    swc_dir = tmp_path / "sk_lod1_783_healed"
    swc_dir.mkdir()
    rid = root_ids[0]
    points = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    labels = np.array([0, 0])  # no soma row at all
    parent = np.array([-1, 0])
    radius = np.full(2, 50.0)
    write_swc(
        Skeleton(root_id=rid, points=points, radius=radius, labels=labels, parent=parent),
        swc_dir / f"{rid}.swc",
    )

    plotter = pv.Plotter(off_screen=True)
    info = scene.build_brain_scene(plotter, kg, specs=[f"{rid}"], data_dir=tmp_path)
    assert info.n_skeletons == 1
    assert info.soma_fallbacks == 1


def test_progress_callback_is_invoked(kg):
    pv = pytest.importorskip("pyvista")
    messages: list[str] = []
    plotter = pv.Plotter(off_screen=True)
    scene.build_brain_scene(plotter, kg, specs=["LC4"], progress=messages.append)
    assert messages


def test_build_brain_scene_flow_view(kg):
    pv = pytest.importorskip("pyvista")
    plotter = pv.Plotter(off_screen=True)
    info = scene.build_brain_scene(plotter, kg, view="flow", top=5)
    assert info.view == "flow"
    assert info.n_flow_pairs == min(5, info.n_flow_total)
    assert info.n_flow_pairs > 0
    assert "context" in plotter.actors
    assert any(name.startswith("flow:") for name in plotter.actors)
    assert any(name.startswith("neuropil:") for name in plotter.actors)


def test_build_brain_scene_flow_view_restricted_by_spec(kg):
    pv = pytest.importorskip("pyvista")
    plotter = pv.Plotter(off_screen=True)
    everyone = scene.build_brain_scene(plotter, kg, view="flow")
    lc4 = scene.build_brain_scene(plotter, kg, view="flow", specs=["LC4"])
    assert lc4.n_flow_total <= everyone.n_flow_total
    assert "LC4" in lc4.title


def test_build_brain_scene_rejects_bad_view_and_top(kg):
    pv = pytest.importorskip("pyvista")
    plotter = pv.Plotter(off_screen=True)
    with pytest.raises(ValueError, match="view"):
        scene.build_brain_scene(plotter, kg, view="mood")
    with pytest.raises(ValueError, match="top must be between 1 and 500"):
        scene.build_brain_scene(plotter, kg, view="flow", top=501)


def test_aim_camera_elevation_looks_down_and_frames_the_scene(kg):
    pv = pytest.importorskip("pyvista")
    quiltwright = pytest.importorskip("quiltwright")
    spec = quiltwright.QUILT_PRESETS["16-landscape"].scaled(0.05)
    plotter = pv.Plotter(off_screen=True, window_size=(100, 100))
    info = scene.build_brain_scene(plotter, kg, view="flow")
    near, far, focal = scene.aim_camera(
        plotter, info.points, elevation=scene.FLOOR_ELEVATION, spec=spec
    )
    width, height = plotter.window_size
    assert width / height == pytest.approx(spec.aspect, rel=0.02)  # display aspect, not the tile's
    forward = np.subtract(plotter.camera.focal_point, plotter.camera.position)
    assert forward[2] < 0  # looking down
    assert 0 < near <= focal <= far
    assert plotter.camera.view_angle == pytest.approx(14.0)


def test_add_floor_adds_a_floor_below_the_scene_with_shadows(kg):
    pv = pytest.importorskip("pyvista")
    plotter = pv.Plotter(off_screen=True, window_size=(320, 180))
    scene.build_brain_scene(plotter, kg, view="flow")
    zmin = plotter.bounds[4]
    scene.add_floor(plotter)
    assert "floor" in plotter.actors
    floor_z = plotter.actors["floor"].GetMapper().GetInput().GetPoints().GetPoint(0)[2]
    assert floor_z < zmin
    shadow_pass = plotter.renderer._render_passes._shadow_map_pass
    assert shadow_pass is not None
    assert shadow_pass.GetShadowMapBakerPass().GetResolution() == scene._SHADOW_MAP_RESOLUTION
    assert any(light.positional for light in plotter.renderer.lights)


def test_flow_view_thins_the_context_cloud_to_one_neutral_grey(kg):
    ids, points, colors, _ = scene.context_points(kg.store)
    f_ids, f_points, f_colors, f_radius = scene._context_for_view("flow", ids, points, colors)
    assert f_ids == ids[:: scene._FLOW_CONTEXT_STRIDE]
    assert len(f_points) == len(f_ids) == len(f_colors)
    assert set(f_colors) == {scene._FLOW_CONTEXT_COLOR}
    assert f_radius == scene._FLOW_CONTEXT_RADIUS
    c_ids, _, c_colors, _ = scene._context_for_view("circuit", ids, points, colors)
    assert c_ids == ids and c_colors == colors
