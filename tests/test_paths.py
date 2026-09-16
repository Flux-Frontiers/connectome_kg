"""Path and cone queries on the planted circuits."""

from __future__ import annotations


def test_sugar_to_mn9_goes_through_the_planted_interneurons(kg):
    res = kg.strongest_path("GRN_sugar", "MN9")
    assert res is not None
    names = [kg.store.node(h.node_id)["name"] for h in res.hops]
    assert names[0] == "GRN_sugar" and names[-1] == "MN9"
    assert names[1] == "SEZ_IN1" and len(names) == 3
    assert res.net_sign == 1
    assert res.hops[1].syn_count >= 20 and res.hops[2].syn_count >= 40


def test_bitter_path_is_inhibitory(kg):
    res = kg.strongest_path("GRN_bitter", "MN9")
    assert res is not None
    names = [kg.store.node(h.node_id)["name"] for h in res.hops]
    assert "SEZ_INb" in names
    assert res.net_sign == -1


def test_escape_cone_reaches_the_giant_fibre(kg):
    cone = kg.cone("LC4", hops=1, min_syn=5)
    hop1 = {kg.store.node(k)["name"] for k, v in cone.items() if v == 1}
    assert "DNp01" in hop1
    up = kg.cone("DNp01", hops=1, min_syn=5, direction="up")
    assert {kg.store.node(k)["name"] for k, v in up.items() if v == 1} >= {"LC4", "LPLC2"}


def test_neurons_of_specs(kg):
    ids = kg.neurons_of("GRN_sugar")
    assert len(ids) == 6
    assert kg.neurons_of(ids[0]) == [ids[0]]
    root = ids[0].rsplit(":", 1)[1]
    assert kg.neurons_of(root) == [ids[0]]
    assert set(kg.neurons_of("label:sugar gustatory")) == set(ids)
    assert kg.neurons_of("no_such_type") == []


def test_unknown_spec_returns_none(kg):
    assert kg.strongest_path("no_such_type", "MN9") is None
