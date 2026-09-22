"""Tests for connectomekg.skeleton_cache -- the Parquet cache and the soma back-fill.

Every test writes real SWC files and reads them back through the same entry
point ``connkg skeletons`` uses, so a cached skeleton is checked against the
parsed one it came from rather than against an assumption about the format.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from connectomekg import skeleton_cache as sc
from connectomekg import skeletons as sk


def _branching_skeleton(root_id: int, n_trunk: int = 40) -> sk.Skeleton:
    """A soma-rooted trunk of ``n_trunk`` points that forks into two equal branches."""
    n = n_trunk * 2 + 1
    points = np.zeros((n, 3))
    labels = np.zeros(n, dtype=np.int64)
    parent = np.full(n, -1, dtype=np.int64)
    labels[0] = 1  # soma
    for i in range(1, n_trunk + 1):
        points[i] = (float(i), 0.0, 0.0)
        parent[i] = i - 1
    fork = n_trunk
    for k in range(n_trunk):
        a, b = fork + 1 + k, fork + 1 + n_trunk // 2 + k
        if b >= n:
            break
        points[a] = (float(fork + k), float(k + 1), 0.0)
        parent[a] = fork if k == 0 else a - 1
    labels[n - 1] = 6  # an end point
    return sk.Skeleton(
        root_id=root_id,
        points=points,
        radius=np.full(n, 10.0),
        labels=labels,
        parent=parent,
    )


@pytest.fixture
def download(tmp_path):
    """A ``data_dir``-shaped directory holding three skeletons, one without a soma."""
    directory = tmp_path / "fafb_v783" / "sk_lod1_783_healed"
    directory.mkdir(parents=True)
    written = {}
    for root_id in (100, 200, 300):
        skeleton = _branching_skeleton(root_id)
        if root_id == 300:
            skeleton = sk.Skeleton(
                root_id=root_id,
                points=skeleton.points,
                radius=skeleton.radius,
                labels=np.zeros_like(skeleton.labels),
                parent=skeleton.parent,
            )
        sk.write_swc(skeleton, sk.skeleton_path(tmp_path / "fafb_v783", root_id))
        written[root_id] = skeleton
    return tmp_path / "fafb_v783", written


def test_build_reports_what_it_read(tmp_path, download):
    data_dir, _ = download
    report, somas = sc.build_skeleton_cache(
        data_dir, [100, 200, 300, 999], tmp_path / "skeletons.parquet", step=4
    )
    assert report.n_cached == 3
    assert report.n_missing == 1  # 999 has no file
    assert report.n_unreadable == 0
    assert report.n_soma == 2  # 300 has no Label 1 row
    assert report.step == 4
    assert report.bytes_written > 0
    assert set(somas) == {100, 200, 300}
    assert somas[300][1] is False
    assert "3 skeletons at step 4" in str(report)


def test_build_leaves_no_partial_file(tmp_path, download):
    data_dir, _ = download
    dest = tmp_path / "skeletons.parquet"
    sc.build_skeleton_cache(data_dir, [100], dest)
    assert dest.exists()
    assert not dest.with_name(dest.name + ".part").exists()


def test_cached_soma_is_the_parsed_soma(tmp_path, download):
    data_dir, written = download
    _, somas = sc.build_skeleton_cache(data_dir, list(written), tmp_path / "c.parquet", step=4)
    for root_id, skeleton in written.items():
        expected, is_soma = sk.soma(skeleton)
        np.testing.assert_allclose(somas[root_id][0], expected, rtol=1e-6)
        assert somas[root_id][1] == is_soma


def test_round_trip_matches_simplifying_the_parsed_skeleton(tmp_path, download):
    data_dir, written = download
    dest = tmp_path / "c.parquet"
    sc.build_skeleton_cache(data_dir, list(written), dest, step=4)
    loaded, missing = sc.load_cached_skeletons(dest, [100, 200, 300])
    assert missing == []
    for root_id, cached in loaded.items():
        # A cached skeleton drawn whole is the parsed one drawn at the cache's
        # stride: same segment count, same endpoints, to float32.
        expected = sk.segments(written[root_id], step=4)
        actual = sk.segments(cached, step=1)
        assert actual.shape == expected.shape
        np.testing.assert_allclose(np.sort(actual, axis=0), np.sort(expected, axis=0), rtol=1e-5)


def test_round_trip_keeps_the_soma_readable(tmp_path, download):
    data_dir, written = download
    dest = tmp_path / "c.parquet"
    sc.build_skeleton_cache(data_dir, list(written), dest, step=4)
    loaded, _ = sc.load_cached_skeletons(dest, [100, 300])
    point, is_soma = sk.soma(loaded[100])
    np.testing.assert_allclose(point, sk.soma(written[100])[0], rtol=1e-6)
    assert is_soma is True
    assert sk.soma(loaded[300])[1] is False


def test_load_reports_root_ids_the_cache_does_not_hold(tmp_path, download):
    data_dir, _ = download
    dest = tmp_path / "c.parquet"
    sc.build_skeleton_cache(data_dir, [100], dest)
    loaded, missing = sc.load_cached_skeletons(dest, [100, 777])
    assert set(loaded) == {100}
    assert missing == [777]


def test_load_of_nothing_reads_nothing(tmp_path):
    assert sc.load_cached_skeletons(tmp_path / "absent.parquet", []) == ({}, [])


def test_cache_info_reads_the_stride_back(tmp_path, download):
    data_dir, _ = download
    dest = tmp_path / "c.parquet"
    sc.build_skeleton_cache(data_dir, [100, 200], dest, step=6)
    assert sc.cache_info(dest) == (6, 2)


def test_cache_info_rejects_a_foreign_parquet(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    pq.write_table(pa.table({"a": [1]}), cache / "part-0000.parquet")
    with pytest.raises(ValueError, match="skeleton cache"):
        sc.cache_info(cache)


def test_cache_info_rejects_a_directory_with_no_shards(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ValueError, match="no .* shards here"):
        sc.cache_info(empty)


def test_build_rejects_a_step_below_one(tmp_path, download):
    data_dir, _ = download
    with pytest.raises(ValueError, match="at least 1"):
        sc.build_skeleton_cache(data_dir, [100], tmp_path / "c.parquet", step=0)


@pytest.mark.parametrize(
    ("requested", "cache_step", "expected"),
    [(4, 4, 1), (1, 4, 1), (2, 4, 1), (8, 4, 2), (50, 4, 12), (4, 1, 4)],
)
def test_effective_step_divides_rather_than_compounds(requested, cache_step, expected):
    assert sc.effective_step(requested, cache_step) == expected


def test_skeleton_cache_path_sits_beside_the_graph(tmp_path):
    db = tmp_path / ".connectomekg" / "graph.sqlite"
    assert sc.skeleton_cache_path(db) == tmp_path / ".connectomekg" / sc.SKELETON_CACHE


def _meta(kg, node_id):
    row = kg.store.con.execute("SELECT metadata FROM nodes WHERE id = ?", (node_id,)).fetchone()
    return json.loads(row[0])


def test_write_somas_adds_keys_without_disturbing_the_rest(kg):
    row = kg.store.con.execute(
        "SELECT id, json_extract(metadata,'$.root_id') FROM nodes WHERE kind='neuron' LIMIT 1"
    ).fetchone()
    node_id, root_id = row[0], int(row[1])
    before = _meta(kg, node_id)

    n = sc.write_somas(
        kg.store, {root_id: (np.asarray([1.0, 2.0, 3.0]), True), -1: (np.zeros(3), True)}
    )

    assert n == 1  # the unknown root id is skipped, not an error
    after = _meta(kg, node_id)
    assert (after["soma_x"], after["soma_y"], after["soma_z"]) == (1.0, 2.0, 3.0)
    assert after["has_soma"] is True
    assert after["x"] == before["x"] and after["cell_type"] == before["cell_type"]

    # Running again overwrites the four keys rather than accumulating.
    sc.write_somas(kg.store, {root_id: (np.asarray([9.0, 9.0, 9.0]), False)})
    again = _meta(kg, node_id)
    assert again["soma_x"] == 9.0
    assert again["has_soma"] is False
    assert len(again) == len(after)

    # Leave the session graph as the other tests expect to find it.
    kg.store.con.execute(
        "UPDATE nodes SET metadata = json_remove(metadata, '$.soma_x', '$.soma_y', "
        "'$.soma_z', '$.has_soma') WHERE id = ?",
        (node_id,),
    )
    kg.store.con.commit()


def test_an_interrupted_pass_leaves_no_partial_behind(tmp_path, download, monkeypatch):
    """A killed 25-minute read must not strand hundreds of megabytes on disk."""
    data_dir, _ = download
    dest = tmp_path / "c.parquet"
    calls = {"n": 0}
    real = sk.read_swc

    def fail_on_the_second(path):
        calls["n"] += 1
        if calls["n"] > 1:
            raise KeyboardInterrupt("maintainer pressed Ctrl-C")
        return real(path)

    monkeypatch.setattr(sc, "read_swc", fail_on_the_second)
    with pytest.raises(KeyboardInterrupt):
        sc.build_skeleton_cache(data_dir, [100, 200, 300], dest)

    assert not dest.with_name(dest.name + ".part").exists()
    assert not dest.exists()


def test_a_cache_that_cannot_be_moved_into_place_cleans_up(tmp_path, download):
    data_dir, _ = download
    dest = tmp_path / "cache"
    dest.write_text("a plain file where the cache directory goes")

    with pytest.raises(OSError):
        sc.build_skeleton_cache(data_dir, [100, 200], dest)

    assert not dest.with_name(dest.name + ".part").exists()
    assert dest.read_text().startswith("a plain file")  # left as it was found


@pytest.mark.parametrize("jobs", [2, 3, 8])
def test_parallel_matches_serial_exactly(tmp_path, download, jobs):
    """The whole point: more workers must not change a single coordinate."""
    data_dir, written = download
    ids = list(written)
    serial, serial_somas = sc.build_skeleton_cache(data_dir, ids, tmp_path / "one", jobs=1)
    parallel, parallel_somas = sc.build_skeleton_cache(
        data_dir, ids, tmp_path / f"many{jobs}", jobs=jobs
    )

    for field in ("n_cached", "n_missing", "n_unreadable", "n_soma", "n_points", "step"):
        assert getattr(serial, field) == getattr(parallel, field), field
    assert serial_somas.keys() == parallel_somas.keys()
    for root_id, (point, is_soma) in serial_somas.items():
        np.testing.assert_array_equal(point, parallel_somas[root_id][0])
        assert is_soma == parallel_somas[root_id][1]

    a, _ = sc.load_cached_skeletons(tmp_path / "one", ids)
    b, _ = sc.load_cached_skeletons(tmp_path / f"many{jobs}", ids)
    assert a.keys() == b.keys()
    for root_id, skeleton in a.items():
        np.testing.assert_array_equal(skeleton.points, b[root_id].points)
        np.testing.assert_array_equal(skeleton.parent, b[root_id].parent)
        np.testing.assert_array_equal(skeleton.labels, b[root_id].labels)


def test_shards_hold_disjoint_root_id_ranges(tmp_path, download):
    """Contiguous ranges are what lets a filtered read skip whole shards."""
    data_dir, written = download
    dest = tmp_path / "cache"
    report, _ = sc.build_skeleton_cache(data_dir, list(written), dest, jobs=3)
    shards = sorted(dest.glob("*.parquet"))
    assert len(shards) == report.n_shards == 3

    spans = []
    for shard in shards:
        ids = pq.read_table(shard, columns=["root_id"]).column("root_id").to_pylist()
        assert ids == sorted(ids)
        spans.append((min(ids), max(ids)))
    spans.sort()
    for (_, hi), (lo, _) in zip(spans, spans[1:], strict=False):  # pairwise
        assert hi < lo, f"shards overlap: {spans}"


def test_more_jobs_than_neurons_is_reduced_not_an_error(tmp_path, download):
    data_dir, written = download
    dest = tmp_path / "cache"
    report, _ = sc.build_skeleton_cache(data_dir, list(written), dest, jobs=50)
    assert report.n_shards == len(written)  # one neuron each, no empty shards
    assert report.n_cached == len(written)


def test_build_rejects_a_job_count_below_one(tmp_path, download):
    data_dir, _ = download
    with pytest.raises(ValueError, match="jobs must be at least 1"):
        sc.build_skeleton_cache(data_dir, [100], tmp_path / "cache", jobs=0)


def test_one_job_starts_no_pool(tmp_path, download, monkeypatch):
    """The single-job path must stay free of multiprocessing entirely."""
    data_dir, written = download

    def explode(*args, **kwargs):
        raise AssertionError("jobs=1 must not start a Pool")

    monkeypatch.setattr(sc.multiprocessing, "Pool", explode)
    report, _ = sc.build_skeleton_cache(data_dir, list(written), tmp_path / "cache", jobs=1)
    assert report.n_cached == len(written)
    assert report.n_shards == 1


def test_round_trip_keeps_the_radius_the_taper_needs(tmp_path, download):
    """Format 2 stores a radius per kept point; without it a neuron is a pipe."""
    data_dir, written = download
    dest = tmp_path / "c.parquet"
    sc.build_skeleton_cache(data_dir, list(written), dest, step=4)
    loaded, _ = sc.load_cached_skeletons(dest, list(written))
    assert loaded
    for root_id, cached in loaded.items():
        keep = sk._simplify_keep_mask(written[root_id].parent, written[root_id].labels, 4)
        np.testing.assert_allclose(cached.radius, written[root_id].radius[keep], rtol=1e-5)
        assert cached.radius.max() > 0, "a cache of zeros would draw at one width"


def test_a_format_1_cache_still_loads_without_a_radius(tmp_path, download):
    """A cache written before the radius column must not stop the viewer.

    Its radii read back as zeros, which the circuit view floors to the
    constant width it drew at when that cache was current. Re-running
    `connkg skeletons` is what upgrades it.
    """
    data_dir, written = download
    dest = tmp_path / "v1.parquet"
    sc.build_skeleton_cache(data_dir, list(written), dest, step=4)
    shard = next(Path(dest).glob("*.parquet"))

    # Rewrite the shard as format 1: drop the radius column and relabel it.
    table = pq.read_table(shard).drop_columns(["radius"])
    metadata = {
        **{
            k.decode(): v.decode()
            for k, v in (pq.ParquetFile(shard).metadata.metadata or {}).items()
            if k != b"ARROW:schema"
        },
        "connectomekg.format": "connectomekg-skeletons-1",
    }
    pq.write_table(table.replace_schema_metadata(metadata), shard)

    step, n = sc.cache_info(dest)
    assert step == 4 and n == len(written)
    loaded, missing = sc.load_cached_skeletons(dest, list(written))
    assert missing == [] and loaded
    for cached in loaded.values():
        assert cached.radius.shape == (len(cached.points),)
        assert not cached.radius.any(), "no radius column means no radius"
