"""Shared fixtures: one synthetic connectome and one built graph per session."""

from __future__ import annotations

from pathlib import Path

import pytest

from connectomekg import ConnectomeKG
from connectomekg.readers.synthetic import synthetic_tables


@pytest.fixture(scope="session")
def tables():
    return synthetic_tables(600, seed=7)


@pytest.fixture(scope="session")
def kg(tmp_path_factory, tables) -> ConnectomeKG:
    root: Path = tmp_path_factory.mktemp("kg")
    module = ConnectomeKG(root, tables=tables)
    module.build_graph(wipe=True)
    return module
