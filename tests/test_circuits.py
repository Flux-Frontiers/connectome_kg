"""Tests for connectomekg.circuits: the ``circuit:<name>`` spec form.

The registry names real v783 cell types, which the synthetic fixture does not
have, so these check the shape -- that names parse, that unknown ones are
refused by name, and that the form resolves through ``neurons_of`` -- rather
than the yield. ``test_every_circuit_resolves_on_v783`` in the build tests is
where the counts are checked against the real graph.
"""

from __future__ import annotations

import pytest

from connectomekg import circuits
from connectomekg.answers import SPEC_EXAMPLES, circuit_examples, is_answer, spec_help
from connectomekg.validation import normalize_spec


def test_every_circuit_has_members_and_a_summary():
    assert circuits.CIRCUITS, "the registry must not be empty"
    for name, circuit in circuits.CIRCUITS.items():
        assert name == name.lower().replace("_", "-"), name
        assert circuit.specs, name
        assert len(set(circuit.specs)) == len(circuit.specs), f"{name} repeats a member"
        assert circuit.summary and not circuit.summary.endswith("."), name


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ("circuit:compass", True),
        ("circuit:Compass", True),  # the prefix is case-insensitive
        ("CIRCUIT:compass", True),
        ("LC4", False),
        ("label:giant fib", False),
        ("circuitous", False),  # a prefix, not a substring
    ],
)
def test_is_circuit(spec, expected):
    assert circuits.is_circuit(spec) is expected


@pytest.mark.parametrize(
    ("spec", "name"),
    [
        ("circuit:compass", "compass"),
        ("circuit:Optic_Flow", "optic-flow"),  # _ folds to -, case folds down
        ("circuit: clock ", "clock"),
    ],
)
def test_circuit_name_normalizes(spec, name):
    assert circuits.circuit_name(spec) == name
    assert circuits.circuit_specs(spec) == circuits.CIRCUITS[name].specs


@pytest.mark.parametrize("spec", ["circuit:", "circuit:   ", "circuit:nope"])
def test_an_unusable_circuit_name_is_refused_by_name(spec):
    """The error names the circuits there are, so a typo is self-correcting."""
    with pytest.raises(ValueError, match="compass"):
        circuits.circuit_specs(spec)


def test_normalize_spec_checks_the_name_before_any_query_runs():
    assert normalize_spec("`circuit:compass`") == "circuit:compass"
    with pytest.raises(ValueError, match="unknown circuit"):
        normalize_spec("circuit:nope")


def test_a_circuit_resolves_to_the_union_of_its_members(kg):
    """On the fixture every member is empty, so the union is too -- but it resolves."""
    for name, circuit in circuits.CIRCUITS.items():
        expected: set[str] = set()
        for member in circuit.specs:
            expected.update(kg.neurons_of(member))
        assert set(kg.neurons_of(f"circuit:{name}")) == expected, name


def test_a_circuit_is_a_spec_not_an_answer():
    """It goes where a SPEC goes, so it must not be mistaken for a query form."""
    for example, _ in circuit_examples():
        assert not is_answer(example), example


def test_the_grammar_documents_the_form_and_every_circuit():
    assert any(e.startswith(circuits.CIRCUIT_PREFIX) for e, _ in SPEC_EXAMPLES)
    text = spec_help()
    for name, circuit in circuits.CIRCUITS.items():
        assert f"{circuits.CIRCUIT_PREFIX}{name}" in text
        assert circuit.summary in text
