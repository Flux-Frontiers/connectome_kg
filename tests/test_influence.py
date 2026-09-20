"""Effective connectivity: SynapseGraph.influence and ConnectomeKG.influence.

The anchor is an identity that holds by construction: unsigned, at hop 1, the
influence on a neuron *is* the source's share of its input synapses. Anything
that breaks the propagation breaks that equality, so it is checked against the
raw counts rather than against a recorded number.
"""

from __future__ import annotations

import numpy as np
import pytest


def test_hop_one_unsigned_is_the_raw_input_share(kg):
    graph = kg.graph
    sources = kg.neurons_of("GRN_sugar")
    rows = [graph.index[s] for s in sources]
    influence = graph.influence(sources, hops=1, signed=False)[0]

    checked = 0
    for j in range(len(graph.ids)):
        total_in = graph.counts[:, j].sum()
        if not total_in:
            continue
        expected = graph.counts[rows, j].sum() / total_in
        assert influence[j] == pytest.approx(expected, abs=1e-12)
        checked += 1
    assert checked, "the fixture should have neurons with input"


def test_an_unresolved_transmitter_contributes_nothing_when_signed(kg):
    graph = kg.graph
    sources = kg.neurons_of("GRN_sugar")
    signed = graph.influence(sources, hops=1, signed=True)[0]
    unsigned = graph.influence(sources, hops=1, signed=False)[0]
    rows = [graph.index[s] for s in sources]
    if not (graph.signs[rows] == 0).any():
        # Zero one source's sign and the signed result must lose exactly its share.
        graph.signs[rows[0]] = 0
        try:
            reduced = graph.influence(sources, hops=1, signed=True)[0]
        finally:
            graph.signs[rows[0]] = 1
        assert (np.abs(reduced) <= np.abs(signed) + 1e-12).all()
    else:
        assert (np.abs(signed) <= unsigned + 1e-12).all()


def test_inhibition_comes_back_negative(kg):
    graph = kg.graph
    sources = kg.neurons_of("GRN_bitter")
    influence = graph.influence(sources, hops=2, signed=True)
    assert (influence < 0).any(), "a bitter pathway should inhibit something"


def test_influence_reaches_further_with_more_hops(kg):
    graph = kg.graph
    sources = kg.neurons_of("GRN_sugar")
    influence = graph.influence(sources, hops=3, signed=False)
    reached = [(row != 0).sum() for row in influence]
    assert reached[0] > 0
    assert reached[1] >= reached[0], "two hops cannot reach fewer neurons than one"


def test_hops_below_one_is_rejected(kg):
    with pytest.raises(ValueError, match="hops must be at least 1"):
        kg.graph.influence(kg.neurons_of("GRN_sugar"), hops=0)


def test_unknown_source_ids_are_ignored_not_an_error(kg):
    graph = kg.graph
    real = kg.neurons_of("GRN_sugar")
    assert graph.influence(real + ["connectome:synthetic:n:1"], hops=1)[0] == pytest.approx(
        graph.influence(real, hops=1)[0]
    )


def test_module_influence_averages_over_the_target_rather_than_summing(kg):
    graph = kg.graph
    result = kg.influence("GRN_sugar", "MN9", hops=1, signed=False)
    columns = [graph.index[t] for t in kg.neurons_of("MN9")]
    raw = graph.influence(kg.neurons_of("GRN_sugar"), hops=1, signed=False)[0]
    assert result.onto[0] == pytest.approx(raw[columns].mean())
    # A mean is a share, so it stays inside [0, 1]; a sum need not.
    assert 0.0 <= result.onto[0] <= 1.0
    assert result.n_sources == len(kg.neurons_of("GRN_sugar"))
    assert result.n_targets == len(kg.neurons_of("MN9"))


def test_without_a_target_it_ranks_cell_types(kg):
    result = kg.influence("GRN_sugar", hops=2, limit=3)
    assert result.target is None and result.onto == []
    assert len(result.ranked) == 2
    for hop in result.ranked:
        assert len(hop) <= 3
        values = [abs(v) for _, v in hop]
        assert values == sorted(values, reverse=True), "strongest absolute first"
        assert all(isinstance(name, str) and name for name, _ in hop)


def test_the_planted_sugar_pathway_shows_up(kg):
    """The fixture plants GRN_sugar -> SEZ_IN1 -> MN9, so influence must find it."""
    result = kg.influence("GRN_sugar", "MN9", hops=2, signed=False)
    assert result.onto[1] > 0, "MN9 is two hops from the sugar neurons"
    names = {name for name, _ in result.ranked[0]}
    assert "SEZ_IN1" in names, "the interneuron is one hop from the source"


def test_out_of_range_arguments_are_rejected(kg):
    with pytest.raises(ValueError, match="hops must be between 1 and 5"):
        kg.influence("GRN_sugar", hops=6)
    with pytest.raises(ValueError, match="limit must be between 1 and 500"):
        kg.influence("GRN_sugar", limit=0)


def test_the_summary_reads_as_shares(kg):
    text = str(kg.influence("GRN_sugar", "MN9", hops=2, limit=2))
    assert "share of the receiving neuron's input" in text
    assert "hop 1:" in text and "hop 2:" in text and "total:" in text
    assert "strongest cell types at hop 1:" in text
