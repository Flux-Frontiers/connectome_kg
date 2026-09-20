"""The answer grammar: path: and cone: queries resolved into coloured groups.

No PyVista and no Qt in the module under test, so these run with no extra
installed.
"""

from __future__ import annotations

import pytest

from connectomekg import answers


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("path:A>B", ("path", {"source": "A", "target": "B"})),
        ("  path:A>B  ", ("path", {"source": "A", "target": "B"})),
        ("PATH:A>B", ("path", {"source": "A", "target": "B"})),
        ("cone:X", ("cone", {"spec": "X", "hops": 1, "direction": "down"})),
        ("cone:X>3", ("cone", {"spec": "X", "hops": 3, "direction": "down"})),
        ("cone:X<2", ("cone", {"spec": "X", "hops": 2, "direction": "up"})),
        # A spec may itself contain a colon, as label: does.
        (
            "cone:label:giant fib>2",
            ("cone", {"spec": "label:giant fib", "hops": 2, "direction": "down"}),
        ),
    ],
)
def test_the_grammar_parses(query, expected):
    assert answers.parse_answer(query) == expected


@pytest.mark.parametrize("query", ["LC4", "label:giant", "", "   "])
def test_a_plain_spec_is_not_an_answer(query):
    assert not answers.is_answer(query)
    with pytest.raises(ValueError, match="not an answer query"):
        answers.parse_answer(query)


@pytest.mark.parametrize(
    ("query", "message"),
    [
        ("path:>B", "spec on each side"),
        ("path:A>", "spec on each side"),
        ("cone:X>9", "hops must be between 1 and 5"),
        ("cone:X>0", "hops must be between 1 and 5"),
    ],
)
def test_a_malformed_answer_says_what_the_forms_are(query, message):
    with pytest.raises(ValueError, match=message):
        answers.parse_answer(query)


def test_a_path_becomes_one_group_per_hop_dark_to_bright(kg):
    answer = answers.answer_groups(kg, "path:GRN_sugar>MN9")
    assert len(answer.groups) >= 2
    assert all(len(g.neuron_ids) == 1 for g in answer.groups), "one neuron per hop"
    assert answer.groups[0].color == "#440154" and answer.groups[-1].color == "#FDE725"
    assert [g.label.split()[1] for g in answer.groups] == [
        str(i) for i in range(len(answer.groups))
    ]
    # Every hop but the first is labelled with the synapses entering it.
    assert len(answer.labels) == len(answer.groups)
    assert any("syn" in text for _, text in answer.labels)
    assert answer.stem == "path_GRN_sugar_to_MN9"


def test_a_cone_becomes_one_group_per_shell(kg):
    answer = answers.answer_groups(kg, "cone:GRN_sugar>1")
    assert len(answer.groups) == 2, "the seed and one shell"
    assert answer.groups[0].neuron_ids == sorted(kg.neurons_of("GRN_sugar"))
    assert answer.labels == [], "a cone has no per-neuron number to show"
    assert "down" in answer.title


def test_an_upstream_cone_reads_the_other_way(kg):
    down = answers.answer_groups(kg, "cone:MN9>1")
    up = answers.answer_groups(kg, "cone:MN9<1")
    assert set(down.groups[1].neuron_ids) != set(up.groups[1].neuron_ids)
    assert "up" in up.title and "down" in down.title


def test_an_answer_that_reaches_nothing_says_so(kg):
    with pytest.raises(ValueError, match="no path"):
        answers.answer_groups(kg, "path:GRN_sugar>NoSuchType")


def test_an_answer_over_the_cap_is_refused_with_the_remedy(kg, monkeypatch):
    monkeypatch.setattr(answers, "MAX_SCENE_NEURONS", 1)
    with pytest.raises(ValueError, match="over the cap of 1"):
        answers.answer_groups(kg, "cone:GRN_sugar>1")


def test_min_syn_narrows_a_cone(kg):
    wide = answers.answer_groups(kg, "cone:GRN_sugar>1", min_syn=1)
    narrow = answers.answer_groups(kg, "cone:GRN_sugar>1", min_syn=10_000)
    assert len(narrow) < len(wide)
