"""Tests for the on-disk SynapseGraph cache in connectomekg.paths.

The cache stands in for a 3.7 M-edge SQL read, so what matters is that it
reproduces the graph exactly and that it is never trusted when the graph it
was built from has moved on.
"""

from __future__ import annotations

import numpy as np
import pytest
from kg_utils.store import GraphStore

from connectomekg.paths import SYNAPSE_CACHE, SynapseGraph, synapse_cache_path


@pytest.fixture
def db(tmp_path, kg):
    """A copy of the session graph, so a test may touch its file freely."""
    destination = tmp_path / ".connectomekg" / "graph.sqlite"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(kg.db_path.read_bytes())
    return destination


def _same(a: SynapseGraph, b: SynapseGraph) -> None:
    assert a.ids == b.ids
    np.testing.assert_array_equal(a.signs, b.signs)
    np.testing.assert_array_equal(a.counts.toarray(), b.counts.toarray())
    np.testing.assert_allclose(a.fraction.toarray(), b.fraction.toarray())


def test_no_cache_path_writes_nothing(kg, db):
    SynapseGraph.from_store(kg.store)
    assert not synapse_cache_path(db).exists()


def test_first_load_writes_the_cache_and_the_second_reproduces_it(kg, db):
    built = SynapseGraph.from_store(kg.store, cache_for=db)
    cache = synapse_cache_path(db)
    assert cache.exists()
    assert not cache.with_suffix(".part").exists()

    reloaded = SynapseGraph.from_store(kg.store, cache_for=db)
    _same(built, reloaded)


def test_an_edited_graph_is_not_answered_from_the_cache(db):
    store = GraphStore(db)
    try:
        cached_nnz = SynapseGraph.from_store(store, cache_for=db).counts.nnz
        assert synapse_cache_path(db).exists()

        # Edit the graph the cache was built from. Its stamp carries the file's
        # size and modification time, so the stale cache must be passed over.
        with store.con:
            store.con.execute(
                "DELETE FROM edges WHERE rel = 'SYNAPSES_TO' AND rowid IN "
                "(SELECT rowid FROM edges WHERE rel = 'SYNAPSES_TO' LIMIT 25)"
            )
        assert SynapseGraph.from_store(store, cache_for=db).counts.nnz == cached_nnz - 25
    finally:
        store.close()


def test_a_different_min_syn_is_not_answered_from_the_cache(kg, db):
    SynapseGraph.from_store(kg.store, cache_for=db, min_syn=1)
    strict = SynapseGraph.from_store(kg.store, cache_for=db, min_syn=50)
    _same(SynapseGraph.from_store(kg.store, min_syn=50), strict)
    assert strict.counts.nnz < SynapseGraph.from_store(kg.store, min_syn=1).counts.nnz


def test_a_corrupt_cache_is_ignored_rather_than_raised(kg, db):
    SynapseGraph.from_store(kg.store, cache_for=db)
    synapse_cache_path(db).write_bytes(b"not an npz")
    _same(SynapseGraph.from_store(kg.store), SynapseGraph.from_store(kg.store, cache_for=db))


def test_a_cached_graph_answers_the_same_path(kg, db):
    direct = SynapseGraph.from_store(kg.store)
    SynapseGraph.from_store(kg.store, cache_for=db)
    cached = SynapseGraph.from_store(kg.store, cache_for=db)
    sources, targets = kg.neurons_of("GRN_sugar"), kg.neurons_of("MN9")
    a, b = direct.strongest_path(sources, targets), cached.strongest_path(sources, targets)
    assert a is not None and b is not None
    assert [h.node_id for h in a.hops] == [h.node_id for h in b.hops]
    assert a.strength == pytest.approx(b.strength)
    assert direct.cone(sources, hops=2) == cached.cone(sources, hops=2)


def test_synapse_cache_path_sits_beside_the_graph(tmp_path):
    db = tmp_path / ".connectomekg" / "graph.sqlite"
    assert synapse_cache_path(db) == tmp_path / ".connectomekg" / SYNAPSE_CACHE
