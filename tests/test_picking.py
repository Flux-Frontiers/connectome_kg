"""Tests for connectomekg.picking -- resolving a click to a neuron, and describing it.

No PyVista or Qt import anywhere in the module under test, so these run with
no extra installed. The viewer wiring itself cannot be tested here: Qt's
offscreen platform has no OpenGL, so a ``BrainSceneWindow`` cannot be built
headlessly.
"""

from __future__ import annotations

import numpy as np

from connectomekg import picking


def _targets():
    """Two neurons, one at x=0 and one at x=10, ten points each."""
    collector = picking._Collector()
    collector.add("n:a", np.stack([np.zeros(10), np.arange(10.0), np.zeros(10)], axis=1))
    collector.add("n:b", np.stack([np.full(10, 10.0), np.arange(10.0), np.zeros(10)], axis=1))
    return collector.build()


def test_a_point_resolves_to_the_neuron_that_owns_it():
    t = _targets()
    assert len(t) == 20
    assert t.neuron_ids == ["n:a", "n:b"]
    assert t.nearest([0.0, 4.0, 0.0]) == "n:a"
    assert t.nearest([10.0, 4.0, 0.0]) == "n:b"
    # Between the two, but nearer b.
    assert t.nearest([6.0, 4.0, 0.0]) == "n:b"


def test_every_drawn_point_resolves_to_its_own_neuron():
    t = _targets()
    for i, point in enumerate(t.points):
        assert t.nearest(point) == t.neuron_ids[int(t.owner[i])]


def test_within_rejects_a_pick_that_landed_on_something_else():
    t = _targets()
    far = [0.0, 4.0, 50.0]
    assert t.nearest(far) == "n:a"  # nearest, however far
    assert t.nearest(far, within=1.0) is None  # but not within reach
    assert t.nearest([0.0, 4.0, 0.5], within=1.0) == "n:a"


def test_an_empty_scene_picks_nothing():
    empty = picking.PickTargets.empty()
    assert len(empty) == 0
    assert empty.nearest([0.0, 0.0, 0.0]) is None
    assert empty.nearest([0.0, 0.0, 0.0], within=1.0) is None


def test_a_neuron_with_no_drawn_points_is_not_an_owner():
    collector = picking._Collector()
    collector.add("n:a", np.zeros((3, 3)))
    collector.add("n:empty", np.empty((0, 3)))
    collector.add("n:b", np.ones((3, 3)))
    targets = collector.build()
    assert targets.neuron_ids == ["n:a", "n:b"]  # no index points at n:empty
    assert set(targets.owner.tolist()) == {0, 1}


def test_the_tree_is_built_once_and_reused():
    t = _targets()
    assert t._tree is None
    t.nearest([0.0, 0.0, 0.0])
    first = t._tree
    assert first is not None
    t.nearest([10.0, 0.0, 0.0])
    assert t._tree is first


def _a_neuron(kg):
    return kg.store.con.execute("SELECT id FROM nodes WHERE kind='neuron' LIMIT 1").fetchone()[0]


def test_partners_are_ranked_types_not_root_ids(kg):
    node_id = kg.store.con.execute(
        "SELECT src FROM edges WHERE rel='SYNAPSES_TO' GROUP BY src ORDER BY COUNT(*) DESC LIMIT 1"
    ).fetchone()[0]
    inputs, outputs = picking.neuron_partners(kg, node_id, limit=3)
    assert outputs, "the busiest presynaptic neuron must have outputs"
    assert len(outputs) <= 3
    assert all(isinstance(name, str) and isinstance(count, int) for name, count in outputs)
    assert [c for _, c in outputs] == sorted((c for _, c in outputs), reverse=True)
    assert all(c > 0 for _, c in outputs)
    # Inputs and outputs are read from opposite columns, so they must differ in
    # general; asserting only that the call is well formed here.
    assert all(len(pair) == 2 for pair in inputs)


def test_summary_leads_with_the_neuron_and_lists_both_directions(kg):
    node_id = _a_neuron(kg)
    text = picking.pick_summary(kg, node_id, limit=2)
    node = kg.describe(node_id)
    assert text.splitlines()[0] == node["qualname"]
    assert node["docstring"].strip() in text
    assert "Inputs:" in text and "Outputs:" in text


def test_summary_of_an_unknown_node_says_so_rather_than_raising(kg):
    text = picking.pick_summary(kg, "connectome:fafb783:n:1")
    assert "No such node" in text


def test_partners_read_only_neuron_level_edges(kg):
    """A cell type carries TYPE_SYNAPSES_TO, never SYNAPSES_TO, so it has none.

    Every neuron in the fixture is connected, so this is how the empty case is
    reached deterministically -- and it also pins the `rel` filter, which would
    otherwise be free to pick up the type-level edges and silently double-count.
    """
    type_id = kg.store.con.execute(
        "SELECT id FROM nodes WHERE kind='cell_type' LIMIT 1"
    ).fetchone()[0]
    assert (
        kg.store.con.execute(
            "SELECT COUNT(*) FROM edges WHERE rel='TYPE_SYNAPSES_TO' AND (src=? OR dst=?)",
            (type_id, type_id),
        ).fetchone()[0]
        > 0
    ), "the fixture should give this type some type-level edges"

    assert picking.neuron_partners(kg, type_id) == ([], [])
    summary = picking.pick_summary(kg, type_id)
    assert "Inputs: none" in summary and "Outputs: none" in summary
