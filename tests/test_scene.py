"""Tests for connectomekg.scene against the synthetic fixture (600 neurons).

Split like the module itself: world-frame/point-set tests need no PyVista;
the scene composition tests do (``pytest.importorskip("pyvista")``).
"""

from __future__ import annotations

import logging
import re

import numpy as np
import pytest

from connectomekg import scene
from connectomekg.colors import HOP_RAMP, REGION_COLOR, UNKNOWN_COLOR, hop_color
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


def _write_stub_skeleton(swc_dir, root_id: int, radius_nm: float = 50.0) -> None:
    points = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]])
    labels = np.array([1, 0, 6])  # soma at the root, end at the tip
    parent = np.array([-1, 0, 1])
    radius = np.full(3, radius_nm)
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


def test_circuit_records_one_pick_owner_per_drawn_neuron(kg):
    pv = pytest.importorskip("pyvista")
    plotter = pv.Plotter(off_screen=True)
    specs = ["GRN_sugar"]
    info = scene.build_brain_scene(plotter, kg, specs=specs, cloud=False, neuropils=False)
    picks = info.picks
    assert info.n_circuit > 0
    # Every circuit neuron is clickable: either its skeleton or its fallback sphere.
    assert set(picks.neuron_ids) == set(scene.circuit_neurons(kg, specs))
    assert len(picks.points) == len(picks.owner)
    assert picks.owner.max() < len(picks.neuron_ids)
    # And each one's own points resolve back to it.
    for i, node_id in enumerate(picks.neuron_ids):
        mine = picks.points[picks.owner == i]
        assert len(mine)
        assert picks.nearest(mine[0]) == node_id


def test_the_flow_view_has_nothing_to_pick(kg):
    pv = pytest.importorskip("pyvista")
    plotter = pv.Plotter(off_screen=True)
    info = scene.build_brain_scene(plotter, kg, view="flow", cloud=False, neuropils=False)
    assert len(info.picks) == 0
    assert info.picks.nearest([0.0, 0.0, 0.0]) is None


def test_pick_points_are_the_drawn_world_coordinates(kg):
    pv = pytest.importorskip("pyvista")
    plotter = pv.Plotter(off_screen=True)
    info = scene.build_brain_scene(plotter, kg, specs=["MN9"], cloud=False, neuropils=False)
    # info.points is every drawn point; the pick targets are a subset of it,
    # in the same frame, so they must sit inside its bounding box.
    lo, hi = info.points.min(axis=0), info.points.max(axis=0)
    assert (info.picks.points >= lo - 1e-3).all()
    assert (info.picks.points <= hi + 1e-3).all()


def test_hop_colors_span_the_ramp_in_order():
    assert hop_color(0, 1) == HOP_RAMP[0]
    assert hop_color(0, 4) == HOP_RAMP[0] and hop_color(3, 4) == HOP_RAMP[-1]

    # Luminance rises monotonically, which is what carries the order to a
    # color-blind reader.
    def luminance(c):
        r, g, b = (int(c[i : i + 2], 16) for i in (1, 3, 5))
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    values = [luminance(hop_color(i, 6)) for i in range(6)]
    assert values == sorted(values)
    assert all(_HEX.match(hop_color(i, 6)) for i in range(6))
    # Out-of-range hops clamp rather than raise or wrap.
    assert hop_color(-1, 4) == HOP_RAMP[0] and hop_color(99, 4) == HOP_RAMP[-1]


def test_groups_override_the_cell_type_grouping(kg):
    pv = pytest.importorskip("pyvista")
    plotter = pv.Plotter(off_screen=True)
    sugar, mn9 = kg.neurons_of("GRN_sugar"), kg.neurons_of("MN9")
    groups = [
        scene.NeuronGroup("hop 0", sugar, "#440154"),
        scene.NeuronGroup("hop 1", mn9, "#FDE725"),
    ]
    info = scene.build_brain_scene(plotter, kg, groups=groups, cloud=False, neuropils=False)

    assert info.n_circuit == len(set(sugar) | set(mn9))
    # Actors are named for the group, not for a cell type.
    names = set(plotter.renderer.actors)
    assert any(n.startswith("skeleton:hop 0") or n.startswith("fallback:hop 0") for n in names)
    assert any(n.startswith("skeleton:hop 1") or n.startswith("fallback:hop 1") for n in names)
    # Every grouped neuron is still pickable.
    assert set(info.picks.neuron_ids) <= set(sugar) | set(mn9)


def test_groups_are_capped_like_specs(kg, monkeypatch):
    pv = pytest.importorskip("pyvista")
    plotter = pv.Plotter(off_screen=True)
    monkeypatch.setattr(scene, "MAX_SCENE_NEURONS", 1)
    groups = [scene.NeuronGroup("all", kg.neurons_of("GRN_sugar"), "#440154")]
    with pytest.raises(ValueError, match="over the cap"):
        scene.build_brain_scene(plotter, kg, groups=groups, cloud=False, neuropils=False)


def test_every_scene_is_lit_by_the_three_point_rig(kg):
    pv = pytest.importorskip("pyvista")
    plotter = pv.Plotter(off_screen=True)
    scene.build_brain_scene(plotter, kg, specs=["GRN_sugar"], cloud=False, neuropils=False)
    lights = plotter.renderer.lights
    assert len(lights) == len(scene._STUDIO_LIGHTS)
    # Camera-relative, not world-fixed: a world-fixed key turns its lit side
    # away from a brain seen front-on, which measured darker and less
    # saturated than PyVista's own default.
    assert all(light.light_type.name == "CAMERA_LIGHT" for light in lights)
    # And off the view axis, or nothing gets any relief.
    assert any(abs(x) > 0.1 or abs(y) > 0.1 for (x, y, _), _ in scene._STUDIO_LIGHTS)


def test_the_floor_keeps_the_rig_and_adds_a_shadow_light(kg):
    pv = pytest.importorskip("pyvista")
    plotter = pv.Plotter(off_screen=True)
    info = scene.build_brain_scene(plotter, kg, specs=["GRN_sugar"], cloud=False, neuropils=False)
    scene.aim_camera(plotter, info.points, elevation=scene.FLOOR_ELEVATION)
    scene.add_floor(plotter)

    lights = plotter.renderer.lights
    # The rig survives: replacing it left the shells and the cloud unlit.
    assert len(lights) == len(scene._STUDIO_LIGHTS) + 1
    positional = [light for light in lights if light.positional]
    assert len(positional) == 1, "exactly one light casts the shadow"
    assert "floor" in plotter.renderer.actors


def test_the_floor_is_culled_from_below(kg):
    """Orbiting under the scene must not put an opaque plane in front of it."""
    pv = pytest.importorskip("pyvista")
    plotter = pv.Plotter(off_screen=True)
    info = scene.build_brain_scene(plotter, kg, specs=["GRN_sugar"], cloud=False, neuropils=False)
    scene.aim_camera(plotter, info.points, elevation=scene.FLOOR_ELEVATION)
    scene.add_floor(plotter)
    assert plotter.renderer.actors["floor"].prop.culling == "back"


def test_the_floor_shades_skeleton_lines_so_the_shadow_pass_compiles(kg, tmp_path, caplog):
    """Unlit lines under VTK's shadow pass fail to compile, silently, and draw as red strays."""
    pv = pytest.importorskip("pyvista")
    swc_dir = tmp_path / "sk_lod1_783_healed"
    swc_dir.mkdir()
    for rid in _lc4_root_ids(kg):
        _write_stub_skeleton(swc_dir, rid)
    plotter = pv.Plotter(off_screen=True, window_size=(320, 180))
    info = scene.build_brain_scene(
        plotter, kg, specs=["LC4"], data_dir=tmp_path, cloud=False, neuropils=False
    )
    scene.aim_camera(plotter, info.points, elevation=scene.FLOOR_ELEVATION)
    scene.add_floor(plotter)

    assert plotter.renderer.actors["skeleton:LC4"].prop.render_lines_as_tubes
    with caplog.at_level(logging.ERROR):
        plotter.screenshot(return_img=True)
    assert "Could not set shader program" not in caplog.text


def test_the_floor_draws_translucent_surfaces_after_the_shadowed_opaque_pass(kg):
    """PyVista's default order draws the shadowed floor over any translucent surface."""
    pv = pytest.importorskip("pyvista")
    plotter = pv.Plotter(off_screen=True, window_size=(320, 180))
    info = scene.build_brain_scene(plotter, kg, specs=["GRN_sugar"], cloud=False, neuropils=False)
    scene.aim_camera(plotter, info.points, elevation=scene.FLOOR_ELEVATION)
    scene.add_floor(plotter)
    scene.add_floor(plotter)  # a second call must not stack a second sequence

    passes = plotter.renderer._render_passes._pass_collection
    names = [passes.GetItemAsObject(i).GetClassName() for i in range(passes.GetNumberOfItems())]
    assert "vtkRenderStepsPass" not in names
    assert names[:2] == ["vtkShadowMapBakerPass", "vtkShadowMapPass"]
    assert names[2] in ("vtkTranslucentPass", "vtkDepthPeelingPass")
    assert names[3:] == ["vtkVolumetricPass", "vtkOverlayPass"]


def test_rebuilding_a_shadowed_scene_restores_normal_passes(kg, tmp_path, caplog):
    """Switching examples must not shade new lines with the previous floor's pass."""
    pv = pytest.importorskip("pyvista")
    swc_dir = tmp_path / "sk_lod1_783_healed"
    swc_dir.mkdir()
    for rid in _lc4_root_ids(kg):
        _write_stub_skeleton(swc_dir, rid)
    plotter = pv.Plotter(off_screen=True, window_size=(320, 180))
    try:
        info = scene.build_brain_scene(
            plotter, kg, specs=["LC4"], data_dir=tmp_path, cloud=False, neuropils=False
        )
        scene.aim_camera(plotter, info.points)
        scene.add_floor(plotter)
        plotter.show(auto_close=False)
        with caplog.at_level(logging.ERROR):
            for floor in (True, False, True):
                info = scene.build_brain_scene(
                    plotter, kg, specs=["LC4"], data_dir=tmp_path, cloud=False, neuropils=False
                )
                assert plotter.renderer._render_passes._shadow_map_pass is None
                assert plotter.renderer.GetPass() is None
                assert "floor" not in plotter.renderer.actors
                scene.aim_camera(plotter, info.points)
                if floor:
                    scene.add_floor(plotter)
                    assert plotter.renderer._render_passes._shadow_map_pass is not None
                image = plotter.screenshot(return_img=True)
                assert image.max() > image.min(), "the scene must still render"
        assert "Could not set shader program" not in caplog.text
        assert "without a bound program" not in caplog.text
    finally:
        plotter.close()


def _drawn_tube_radius(plotter) -> float:
    """The widest the drawn tube gets, read off the mesh.

    The stub skeletons run straight along world x, so a tube of radius r puts
    its surface exactly r away in y; the mesh's y half-extent is the radius
    that was actually drawn, whatever the traced radius asked for.
    """
    mesh = next(
        a.mapper.dataset
        for name, a in plotter.renderer.actors.items()
        if name.startswith("skeleton:")
    )
    ys = mesh.points[:, 1]
    return float((ys.max() - ys.min()) / 2)


@pytest.mark.parametrize(
    ("traced_world", "expected"),
    [
        (scene._MAX_TUBE_RADIUS * 5, scene._MAX_TUBE_RADIUS),  # the giant fiber case
        (scene._MIN_TUBE_RADIUS / 5, scene._MIN_TUBE_RADIUS),  # a thread
        ((scene._MIN_TUBE_RADIUS + scene._MAX_TUBE_RADIUS) / 2,) * 2,  # in between: as traced
    ],
)
def test_a_tapered_tube_is_clamped_between_the_old_width_and_the_soma(
    kg, tmp_path, traced_world, expected
):
    """No neurite draws thinner than it used to, nor fatter than its own soma.

    Untamed, the giant fiber tapers to 13x the floor and 2.6x the soma sphere,
    which reads as a sausage swallowing the arbor around it.
    """
    pv = pytest.importorskip("pyvista")
    swc_dir = tmp_path / "sk_lod1_783_healed"
    swc_dir.mkdir()
    for rid in _lc4_root_ids(kg):
        _write_stub_skeleton(swc_dir, rid, radius_nm=traced_world * scene.NM_PER_WORLD_UNIT)
    plotter = pv.Plotter(off_screen=True, window_size=(320, 180))
    try:
        scene.build_brain_scene(
            plotter, kg, specs=["LC4"], data_dir=tmp_path, cloud=False, neuropils=False, tubes=True
        )
        assert _drawn_tube_radius(plotter) == pytest.approx(expected, rel=0.02)
    finally:
        plotter.close()


def test_the_radius_clamp_ends_are_the_numbers_they_are_for_a_reason():
    assert scene._MIN_TUBE_RADIUS == scene._TUBE_RADIUS, "the floor is the old constant width"
    assert scene._MAX_TUBE_RADIUS == scene._SOMA_RADIUS, "the ceiling is the soma marker"
    assert scene._MIN_TUBE_RADIUS < scene._MAX_TUBE_RADIUS


def test_a_line_skeleton_carries_no_stray_vertex_cells(kg, tmp_path):
    """Points drawn beside the lines break the floor's shadow pass.

    ``pv.PolyData(points)`` adds a vertex cell per point, and those points
    render alongside the lines with no normals, so the shadow pass fails to
    compile their shader. ``_shade_skeleton_lines`` cannot save them: it turns
    *lines* into tubes. 0.7.0 shipped with one stray point per traced point.
    """
    pv = pytest.importorskip("pyvista")
    swc_dir = tmp_path / "sk_lod1_783_healed"
    swc_dir.mkdir()
    for rid in _lc4_root_ids(kg):
        _write_stub_skeleton(swc_dir, rid)
    plotter = pv.Plotter(off_screen=True, window_size=(320, 180))
    try:
        scene.build_brain_scene(
            plotter, kg, specs=["LC4"], data_dir=tmp_path, cloud=False, neuropils=False
        )
        meshes = [
            a.mapper.dataset
            for name, a in plotter.renderer.actors.items()
            if name.startswith("skeleton:")
        ]
        assert meshes, "the scene must have drawn a skeleton"
        for mesh in meshes:
            assert mesh.n_lines > 0
            assert mesh.n_verts == 0, "the lines must be the only primitive drawn"
    finally:
        plotter.close()


@pytest.mark.parametrize(
    ("value", "expected"),
    [("gray", scene.BACKGROUND), ("Charcoal", "#26292E"), ("#abcdef", "#ABCDEF")],
)
def test_resolve_background_takes_a_name_or_a_hex_color(value, expected):
    assert scene.resolve_background(value) == expected


@pytest.mark.parametrize("value", ["mauve", "#12345", "#GGGGGG", ""])
def test_resolve_background_refuses_anything_else(value):
    with pytest.raises(ValueError, match="background must be"):
        scene.resolve_background(value)


def test_the_floor_steps_away_from_its_background():
    assert scene.floor_color(scene.BACKGROUND) == scene.FLOOR_COLOR
    # Darker under a light background, lighter under a dark one.
    assert scene.floor_color("#B9BCC1") < "#B9BCC1"
    assert scene.floor_color("#26292E") > "#26292E"


class _PointsStore:
    """Just enough of a GraphStore for :func:`scene.world_frame`: fixed positions."""

    def __init__(self, points: np.ndarray) -> None:
        self.con = self
        self._rows = points.tolist()

    def execute(self, *_a):
        return self

    def fetchall(self):
        return self._rows


@pytest.mark.parametrize(
    ("height_nm", "expected"),
    [
        (100_000.0, 1.0),  # smaller than FAFB: never shrunk below FAFB's sizes
        (820_000.0, 2.0),  # twice FAFB's framed extent: markers twice as large
        (1e9, 4.0),  # capped
    ],
)
def test_marker_scale_follows_the_framed_height(height_nm, expected):
    points = np.array([[0.0, 0.0, 0.0], [100.0, height_nm, 0.0]] * 50)
    assert scene.world_frame(_PointsStore(points)).marker_scale == pytest.approx(expected)


def test_marker_scale_reads_width_over_the_frame_aspect():
    """A wide scene frames by its width, divided by the 16:9 aspect."""
    points = np.array([[0.0, 0.0, 0.0], [16 / 9 * 820_000.0, 100.0, 0.0]] * 50)
    assert scene.world_frame(_PointsStore(points)).marker_scale == pytest.approx(2.0)


def test_the_scene_background_is_the_one_asked_for(kg):
    pv = pytest.importorskip("pyvista")
    plotter = pv.Plotter(off_screen=True)
    scene.build_brain_scene(plotter, kg, view="flow", background="charcoal")
    assert plotter.background_color.hex_rgb.upper() == "#26292E"
    plotter.close()


def test_black_and_navy_are_backgrounds_with_a_visible_floor():
    for name in ("black", "navy"):
        color = scene.resolve_background(name)
        # Both are dark, so the floor is shaded lighter, not darker.
        assert scene.floor_color(color) > color
