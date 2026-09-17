"""The graph the extractor emits, checked through a built store."""

from __future__ import annotations

import json

import pandas as pd
from kg_utils.specs import NodeSpec

from connectomekg.extractor import SELECTIVE_TAGS, type_ontology_terms


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


def _has_edge(kg, rel: str, src: str, dst: str) -> bool:
    row = kg.store.con.execute(
        "SELECT 1 FROM edges WHERE rel=? AND src=? AND dst=?", (rel, src, dst)
    ).fetchone()
    return row is not None


def test_sub_classes_hang_off_their_class(kg, tables):
    n = tables.neurons
    row = n[n["sub_class"] != ""].iloc[0]
    cls_id = f"connectome:synthetic:c:{row['super_class']}/{row['class']}"
    sub_id = f"{cls_id}/{row['sub_class']}"
    sub = kg.store.node(sub_id)
    assert sub is not None and sub["metadata"]["level"] == "sub_class"
    assert _has_edge(kg, "CONTAINS", cls_id, sub_id)


def test_nerves_columns_and_tags(kg, tables):
    n = tables.neurons
    s = kg.store.stats()
    nc, ec = s["node_counts"], s["edge_counts"]
    nerved = n["nerve"].fillna("") != ""
    assert nc["nerve"] == n.loc[nerved, "nerve"].nunique()
    assert ec["VIA_NERVE"] == int(nerved.sum())
    in_col = n[n["column_id"].notna()]
    # Column ids repeat across hemispheres, so a column is (hemisphere, id).
    assert nc["column"] == in_col.groupby(["column_hemisphere", "column_id"]).ngroups
    assert nc["column"] > in_col["column_id"].nunique()
    assert ec["IN_COLUMN"] == len(in_col)
    # Only the selective tags become nodes; the near-universal ones stay metadata.
    assert nc["connectivity_tag"] == 3
    assert kg.store.node("connectome:synthetic:tag:feedforward_loop_participant") is None
    assert ec["TAGGED"] == sum(len(set(t) & set(SELECTIVE_TAGS)) for t in n["connectivity_tags"])


def test_visual_family_contains_its_cell_types(kg):
    fam = "connectome:synthetic:v:family/Lobula Columnar"
    assert _has_edge(kg, "CONTAINS", "connectome:synthetic:v:subsystem/Object", fam)
    assert _has_edge(kg, "CONTAINS", fam, "connectome:synthetic:t:LC4")
    lc4 = kg.store.node("connectome:synthetic:t:LC4")
    assert "visual family Lobula Columnar in the Object subsystem" in lc4["docstring"]


def test_ontology_terms_are_normalised_and_mapped(kg):
    # The fixture spells this id "Fbbt_", as Codex sometimes does.
    term = kg.store.node("connectome:synthetic:fbbt:FBbt_99000000")
    assert term is not None and term["kind"] == "ontology_term"
    assert term["metadata"]["description"] == "synthetic GRN_sugar neuron"
    assert kg.store.node("connectome:synthetic:fbbt:Fbbt_99000000") is None
    assert _has_edge(
        kg, "MAPS_TO", "connectome:synthetic:t:GRN_sugar", "connectome:synthetic:fbbt:FBbt_99000000"
    )
    assert kg.store.node("connectome:synthetic:t:LC4")["metadata"]["fbbt"] == ["FBbt_99000007"]


def test_neuron_carries_scores_and_size(kg):
    meta = kg.store.node(kg.neurons_of("MN9")[0])["metadata"]
    assert set(meta["nt_scores"]) == {"ACH", "DA", "GABA", "GLUT", "OCT", "SER"}
    assert meta["nt_scores"]["ACH"] == max(meta["nt_scores"].values())
    assert meta["length_nm"] > 0 and meta["volume_nm3"] > meta["area_nm2"]
    assert meta["flow"] == "efferent"


def test_stray_ontology_labels_do_not_map_a_type():
    # The v783 shape: most T4b neurons carry T4b's term, a few carry T4a's.
    neurons = pd.DataFrame(
        {
            "cell_type": ["T4b"] * 30 + ["T4a"] * 4 + ["Mi1", ""],
            "fbbt": [("FBbt_00003733",)] * 28
            + [("FBbt_00003732",)] * 2
            + [("FBbt_00003732",)] * 4
            + [("FBbt_00000001", "FBbt_00000002"), ("FBbt_00000003",)],
        }
    )
    terms = type_ontology_terms(neurons)
    assert terms["T4b"] == {"FBbt_00003733": 28}
    assert terms["T4a"] == {"FBbt_00003732": 4}
    # Two terms equally supported both stay; an untyped neuron maps nothing.
    assert terms["Mi1"] == {"FBbt_00000001": 1, "FBbt_00000002": 1}
    assert "" not in terms
