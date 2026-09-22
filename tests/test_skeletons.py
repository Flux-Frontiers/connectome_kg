"""Tests for connectomekg.skeletons -- SWC parsing, soma, simplification.

No PyVista or Qt import anywhere in the module under test, so these run with
no extra installed.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from connectomekg import skeletons as sk


def _linear_skeleton(root_id: int = 1, n: int = 5) -> sk.Skeleton:
    """A straight chain of n points, each the parent of the next."""
    points = np.array([[float(i), 0.0, 0.0] for i in range(n)])
    radius = np.full(n, 10.0)
    labels = np.zeros(n, dtype=np.int64)
    labels[0] = 1  # soma at the root
    parent = np.array([-1] + list(range(n - 1)), dtype=np.int64)
    return sk.Skeleton(root_id=root_id, points=points, radius=radius, labels=labels, parent=parent)


def _y_skeleton() -> sk.Skeleton:
    """Trunk of 4 points (0-3), forking at 3 into two 4-point branches.

    Point 3 is the fork (label 5); the last point of each branch is an end
    (label 6). 11 points total: trunk 0,1,2,3; branch A 4,5,6,7; branch B
    8,9,10,11 -- wait, keep it at 11 (0..10): trunk 0-3, branch A 4-6,
    branch B 7-9, plus... simplest: trunk 0,1,2,3 (4 pts); branch A
    4,5,6 (parents 3,4,5); branch B 7,8,9 (parents 3,7,8).
    """
    n = 10
    points = np.zeros((n, 3))
    labels = np.zeros(n, dtype=np.int64)
    parent = np.full(n, -1, dtype=np.int64)
    # Trunk: 0 (root/soma) -> 1 -> 2 -> 3 (fork)
    for i in range(4):
        points[i] = [float(i), 0.0, 0.0]
        parent[i] = i - 1
    labels[0] = 1
    labels[3] = 5
    # Branch A: 4 -> 5 -> 6 (end), off the fork at 3
    parent[4] = 3
    parent[5] = 4
    parent[6] = 5
    points[4] = [4.0, 1.0, 0.0]
    points[5] = [5.0, 1.0, 0.0]
    points[6] = [6.0, 1.0, 0.0]
    labels[6] = 6
    # Branch B: 7 -> 8 -> 9 (end), off the fork at 3
    parent[7] = 3
    parent[8] = 7
    parent[9] = 8
    points[7] = [4.0, -1.0, 0.0]
    points[8] = [5.0, -1.0, 0.0]
    points[9] = [6.0, -1.0, 0.0]
    labels[9] = 6
    radius = np.full(n, 5.0)
    return sk.Skeleton(root_id=42, points=points, radius=radius, labels=labels, parent=parent)


# --------------------------------------------------------------------------- read/write


def test_round_trip_read_write(tmp_path):
    original = _linear_skeleton(root_id=720575940596125868, n=6)
    path = tmp_path / f"{original.root_id}.swc"
    sk.write_swc(original, path)
    reread = sk.read_swc(path)
    assert reread.root_id == original.root_id
    np.testing.assert_allclose(reread.points, original.points)
    np.testing.assert_allclose(reread.radius, original.radius)
    np.testing.assert_array_equal(reread.labels, original.labels)
    np.testing.assert_array_equal(reread.parent, original.parent)


def test_crlf_and_lf_parse_the_same(tmp_path):
    body_lf = (
        "# SWC format file\n"
        "# PointNo Label X Y Z Radius Parent\n"
        "1 1 0.0 0.0 0.0 10 -1\n"
        "2 0 1.0 0.0 0.0 10 1\n"
        "3 6 2.0 0.0 0.0 10 2\n"
    )
    body_crlf = body_lf.replace("\n", "\r\n")
    lf_dir, crlf_dir = tmp_path / "lf", tmp_path / "crlf"
    lf_dir.mkdir()
    crlf_dir.mkdir()
    # read_swc keys root_id off the stem, so both copies share the stem "1"
    # and are told apart by directory instead.
    lf_path = lf_dir / "1.swc"
    crlf_path = crlf_dir / "1.swc"
    lf_path.write_bytes(body_lf.encode("utf-8"))
    crlf_path.write_bytes(body_crlf.encode("utf-8"))

    a = sk.read_swc(lf_path)
    b = sk.read_swc(crlf_path)
    np.testing.assert_allclose(a.points, b.points)
    np.testing.assert_array_equal(a.parent, b.parent)
    np.testing.assert_array_equal(a.labels, b.labels)


def test_pointno_gaps_are_handled(tmp_path):
    # PointNo jumps 5 -> 7 -> 12; Parent references the PointNo, not a row index.
    body = (
        "# PointNo Label X Y Z Radius Parent\n"
        "5 1 0.0 0.0 0.0 10 -1\n"
        "7 0 1.0 0.0 0.0 10 5\n"
        "12 6 2.0 0.0 0.0 10 7\n"
    )
    path = tmp_path / "99.swc"
    path.write_text(body)
    skeleton = sk.read_swc(path)
    assert len(skeleton) == 3
    # Row 0 (PointNo 5) is the root; row 1 (PointNo 7)'s parent is row 0;
    # row 2 (PointNo 12)'s parent is row 1.
    np.testing.assert_array_equal(skeleton.parent, [-1, 0, 1])


def test_bad_parent_raises_naming_file_and_line(tmp_path):
    body = "# PointNo Label X Y Z Radius Parent\n1 1 0.0 0.0 0.0 10 -1\n2 0 1.0 0.0 0.0 10 999\n"
    path = tmp_path / "7.swc"
    path.write_text(body)
    with pytest.raises(ValueError, match=r"7\.swc.*line 3.*999"):
        sk.read_swc(path)


def test_too_few_fields_raises(tmp_path):
    path = tmp_path / "7.swc"
    path.write_text("1 1 0.0 0.0 -1\n")
    with pytest.raises(ValueError, match="expected 7 fields"):
        sk.read_swc(path)


def test_empty_file_raises(tmp_path):
    path = tmp_path / "7.swc"
    path.write_text("# just a header, no points\n")
    with pytest.raises(ValueError, match="no SWC point rows"):
        sk.read_swc(path)


# --------------------------------------------------------------------------- soma


def test_soma_uses_label_1_row():
    skeleton = _linear_skeleton()
    skeleton.labels[:] = 0
    skeleton.labels[2] = 1  # the soma label is not on the root
    point, is_soma = sk.soma(skeleton)
    np.testing.assert_allclose(point, skeleton.points[2])
    assert is_soma is True


def test_soma_falls_back_to_root_when_no_label_1():
    skeleton = _linear_skeleton()
    skeleton.labels[:] = 0
    point, is_soma = sk.soma(skeleton)
    np.testing.assert_allclose(point, skeleton.points[0])
    assert is_soma is False


# --------------------------------------------------------------------------- segments


def test_segments_full_skeleton_has_one_edge_per_non_root_point():
    skeleton = _linear_skeleton(n=6)
    segs = sk.segments(skeleton)
    assert segs.shape == (5, 2, 3)
    # Every edge is child -> parent, and consecutive here.
    np.testing.assert_allclose(segs[0, 0], skeleton.points[1])
    np.testing.assert_allclose(segs[0, 1], skeleton.points[0])


def test_segments_simplification_keeps_the_fork():
    skeleton = _y_skeleton()
    # step larger than either branch's run length: only structural points
    # (root, fork, the two ends) should survive.
    segs = sk.segments(skeleton, step=10)
    drawn_points = {tuple(p) for pair in segs for p in pair}
    fork = tuple(skeleton.points[3])
    end_a = tuple(skeleton.points[6])
    end_b = tuple(skeleton.points[9])
    assert fork in drawn_points
    assert end_a in drawn_points
    assert end_b in drawn_points
    # The mid-branch points (5 and 8) are neither structural nor a step hit
    # at this step size, so they must have been dropped -- otherwise this
    # test could not fail on a broken simplification.
    mid_a = tuple(skeleton.points[5])
    assert mid_a not in drawn_points


def test_segments_simplification_preserves_topology_end_to_end():
    """Every simplified segment must chain back to the root through kept points."""
    skeleton = _y_skeleton()
    segs = sk.segments(skeleton, step=3)
    by_start = {tuple(pair[0]): tuple(pair[1]) for pair in segs}
    root = tuple(skeleton.points[0])
    for pair in segs:
        cur = tuple(pair[0])
        hops = 0
        while cur != root:
            assert cur in by_start or cur == root
            cur = by_start.get(cur, root)
            hops += 1
            assert hops < len(skeleton)  # guards against an accidental cycle


def test_segments_step_one_matches_default():
    skeleton = _y_skeleton()
    np.testing.assert_allclose(sk.segments(skeleton), sk.segments(skeleton, step=1))


# --------------------------------------------------------------------------- files


def test_skeleton_path_layout():
    path = sk.skeleton_path("fafb_v783", 720575940596125868)
    assert path == Path("fafb_v783") / "sk_lod1_783_healed" / "720575940596125868.swc"


def test_load_skeletons_reports_missing_without_raising(tmp_path):
    present = _linear_skeleton(root_id=1)
    swc_dir = tmp_path / "sk_lod1_783_healed"
    swc_dir.mkdir()
    sk.write_swc(present, swc_dir / "1.swc")
    loaded, missing = sk.load_skeletons(tmp_path, [1, 2, 3])
    assert set(loaded) == {1}
    assert sorted(missing) == [2, 3]
    assert loaded[1].root_id == 1


def _edges_of(chains):
    """Every (parent, child) index pair a chain list covers, with duplicates kept."""
    return [(int(a), int(b)) for c in chains for a, b in zip(c[:-1], c[1:], strict=True)]


@pytest.mark.parametrize("step", [1, 3, 4, 7])
def test_polylines_cover_exactly_the_edges_segments_draws(step):
    """The chains are a regrouping of the same edges, not a different skeleton.

    Random trees rather than a fixture: the interesting cases are forks, long
    unbranched runs and roots with one child, and a generator hits all three
    in combination faster than examples can be written.
    """
    rng = np.random.default_rng(0)
    for _ in range(50):
        n = int(rng.integers(2, 60))
        parent = np.full(n, -1, dtype=np.int64)
        for i in range(1, n):
            parent[i] = rng.integers(0, i)
        labels = np.zeros(n, dtype=np.int64)
        labels[0] = 1
        skeleton = sk.Skeleton(1, rng.random((n, 3)) * 1000, rng.random(n) * 100, labels, parent)

        edges = _edges_of(sk.polylines(skeleton, step=step))
        assert len(edges) == len(set(edges)), "an edge is drawn twice"
        assert len(edges) == len(sk.segments(skeleton, step=step)), "edge count differs"
        drawn = {(tuple(a), tuple(b)) for a, b in sk.segments(skeleton, step=step)[:, ::-1]}
        assert {(tuple(skeleton.points[a]), tuple(skeleton.points[b])) for a, b in edges} == drawn


def test_a_polyline_is_a_run_between_branch_points():
    """A straight chain is one polyline; a fork ends it and starts two more."""
    #   0 -> 1 -> 2 -> 3      and 2 -> 4, so 2 forks
    parent = np.array([-1, 0, 1, 2, 2], dtype=np.int64)
    labels = np.zeros(5, dtype=np.int64)
    skeleton = sk.Skeleton(
        1, np.arange(15, dtype=np.float64).reshape(5, 3), np.ones(5), labels, parent
    )
    chains = sorted(sk.polylines(skeleton), key=len, reverse=True)
    assert [c.tolist() for c in chains] == [[0, 1, 2], [2, 3], [2, 4]]


def test_a_skeleton_with_no_edges_has_no_polylines():
    skeleton = sk.Skeleton(
        1, np.zeros((1, 3)), np.ones(1), np.zeros(1, dtype=np.int64), np.array([-1], dtype=np.int64)
    )
    assert sk.polylines(skeleton) == []
