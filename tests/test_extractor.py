"""The graph the extractor emits, checked through a built store."""

from __future__ import annotations

import json

from kg_utils.specs import NodeSpec


def test_node_and_edge_kinds(kg, tables):
    s = kg.store.stats()
    nc, ec = s["node_counts"], s["edge_counts"]
    assert nc["dataset"] == 1
    assert nc["neuron"] == len(tables.neurons)
    assert nc["cell_type"] == tables.neurons["cell_type"].nunique()
    assert nc["neuropil"] == tables.connections["neuropil"].nunique()
    assert nc["label"] == tables.labels["text"].str.lower().nunique()
    assert ec["SYNAPSES_TO"] == tables.connections.groupby(["pre", "post"]).ngroups
    assert ec["INSTANCE_OF"] == len(tables.neurons)
    assert ec["LABELED"] == len(tables.labels)
    assert ec["TYPE_SYNAPSES_TO"] > 0 and ec["IN_NEUROPIL"] > 0 and ec["CONTAINS"] > 0


def test_synapse_edge_carries_count_sign_and_neuropils(kg, tables):
    c = tables.connections
    pre, post = int(c.iloc[0]["pre"]), int(c.iloc[0]["post"])
    row = kg.store.con.execute(
        "SELECT evidence FROM edges WHERE rel='SYNAPSES_TO' AND src=? AND dst=?",
        (f"connectome:synthetic:n:{pre}", f"connectome:synthetic:n:{post}"),
    ).fetchone()
    meta = json.loads(row[0])
    expected = int(c[(c["pre"] == pre) & (c["post"] == post)]["syn_count"].sum())
    assert meta["syn_count"] == expected
    assert meta["sign"] in (-1, 1)
    assert sum(meta["neuropils"].values()) == expected


def test_neuron_docstring_and_metadata(kg):
    nid = kg.neurons_of("MN9")[0]
    n = kg.store.node(nid)
    assert n["kind"] == "neuron"
    assert "MN9" in n["docstring"] and "cholinergic" in n["docstring"]
    assert "proboscis motor neuron" in n["docstring"]
    assert n["metadata"]["cell_type"] == "MN9" and n["metadata"]["sign"] == 1


def test_cell_type_docstring_lists_partners(kg):
    t = kg.store.node("connectome:synthetic:t:LC4")
    assert t is not None
    assert "8 neurons" in t["docstring"]
    assert "DNp01" in t["docstring"]


def test_meaningful_kinds_exclude_neurons_by_default(kg):
    kinds = kg.make_extractor().meaningful_node_kinds()
    assert "cell_type" in kinds and "label" in kinds and "neuron" not in kinds


def test_coverage_metric_is_complete_on_fixture(kg):
    ex = kg.make_extractor()
    nodes = [x for x in ex.extract() if isinstance(x, NodeSpec)]
    assert ex.coverage_metric(nodes) == 1.0
