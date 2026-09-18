"""Shared fixtures: one synthetic connectome and one built graph per session."""

from __future__ import annotations

from pathlib import Path

import pytest

from connectomekg import ConnectomeKG
from connectomekg.datasets import dataset_dir
from connectomekg.readers.synthetic import synthetic_tables


@pytest.fixture(scope="session")
def tables():
    return synthetic_tables(600, seed=7)


@pytest.fixture(scope="session")
def kg_root(tmp_path_factory) -> Path:
    """The ``--root`` of the session graph: it holds ``connectomes/synthetic/``."""
    return tmp_path_factory.mktemp("kg")


@pytest.fixture(scope="session")
def kg(kg_root, tables) -> ConnectomeKG:
    module = ConnectomeKG(dataset_dir(kg_root, "synthetic"), tables=tables)
    module.build_graph(wipe=True)
    return module
