"""The synthetic generator: validity, shape, planted circuits, Codex round trip."""

from __future__ import annotations

import pytest

from connectomekg.readers.codex import read_codex
from connectomekg.readers.synthetic import min_neurons, synthetic_tables, write_codex_dir


def test_tables_validate_and_are_deterministic(tables):
    tables.validate()
    again = synthetic_tables(600, seed=7)
    assert tables.neurons.equals(again.neurons)
    assert tables.connections.equals(again.connections)


def test_population_shape(tables):
    n = tables.neurons
    assert len(n) == 600
    shares = n["super_class"].value_counts(normalize=True)
    assert 0.45 < shares["optic"] < 0.65
    assert 0.15 < shares["central"] < 0.32
    sign = tables.sign_of()
    assert 0.55 < (sign > 0).mean() < 0.80
    assert (sign != 0).all()


def test_planted_circuits_present(tables):
    counts = tables.neurons["cell_type"].value_counts()
    for ct, k in {"GRN_sugar": 6, "SEZ_IN1": 3, "MN9": 2, "LC4": 8, "DNp01": 2, "aDN1": 2}.items():
        assert counts[ct] == k
    labels = tables.labels
    sugar = tables.neurons.loc[tables.neurons["cell_type"] == "GRN_sugar", "root_id"]
    assert set(sugar) <= set(labels.loc[labels["text"].str.contains("sugar"), "root_id"])


def test_codex_round_trip(tables, tmp_path):
    d = write_codex_dir(tables, tmp_path / "codex")
    assert {p.name for p in d.iterdir()} >= {
        "neurons.csv.gz",
        "classification.csv.gz",
        "connections_princeton.csv.gz",
        "consolidated_cell_types.csv.gz",
        "coordinates.csv.gz",
        "labels.csv.gz",
    }
    back = read_codex(d, tables.dataset)
    assert len(back.neurons) == len(tables.neurons)
    assert len(back.connections) == len(tables.connections)
    assert len(back.labels) == len(tables.labels)
    assert list(back.neurons["cell_type"]) == list(tables.neurons["cell_type"])
    assert back.connections["syn_count"].sum() == tables.connections["syn_count"].sum()
    assert back.neurons["x"].notna().all()


def test_too_few_neurons_is_refused_not_silently_shrunk():
    floor = min_neurons()
    assert 300 < floor < 600
    with pytest.raises(ValueError, match="too small for the planted circuits"):
        synthetic_tables(floor - 1, seed=1)
    smallest = synthetic_tables(floor, seed=1)
    counts = smallest.neurons["cell_type"].value_counts()
    assert counts["LPLC2"] == 10 and counts["MN9"] == 2
