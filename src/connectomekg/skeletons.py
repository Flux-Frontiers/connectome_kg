"""SWC skeleton reading, writing and simplification -- NumPy only.

FlyWire's Codex download carries one navis-written ``.swc`` file per neuron
(``fafb_v783/sk_lod1_783_healed/<root_id>.swc``): a header of ``#`` comment
lines, then one row per traced point --
``PointNo Label X Y Z Radius Parent``, coordinates in nanometres, sharing the
graph's own ``x``/``y``/``z`` frame. ``Parent`` names another row's
``PointNo``, or ``-1`` for a root; ``PointNo`` itself may have gaps and is not
the row index. Files mix CRLF and LF line endings. Label values: ``0``
undefined, ``1`` soma, ``5`` fork point, ``6`` end point.

This module has no PyVista or Qt import anywhere, so it stays importable with
no extra installed -- :mod:`connectomekg.scene` builds on it lazily.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np

#: Subdirectory of the Codex download holding one ``.swc`` file per neuron.
SKELETON_SUBDIR: Final = "sk_lod1_783_healed"

#: SWC label values used structurally, beyond a plain undefined (0) point.
_LABEL_SOMA = 1
_LABEL_FORK = 5
_LABEL_END = 6


@dataclass(frozen=True)
class Skeleton:
    """One neuron's traced skeleton.

    :param root_id: Neuron root id, from the SWC file's stem.
    :param points: ``(n, 3)`` float64 point coordinates, nanometres.
    :param radius: ``(n,)`` float64 radius per point, nanometres.
    :param labels: ``(n,)`` int SWC label per point (0 undefined, 1 soma,
        5 fork, 6 end).
    :param parent: ``(n,)`` int, each point's parent as a row index into
        these arrays, or ``-1`` for a root.
    """

    root_id: int
    points: np.ndarray
    radius: np.ndarray
    labels: np.ndarray
    parent: np.ndarray

    def __len__(self) -> int:
        return len(self.points)


def read_swc(path: str | Path) -> Skeleton:
    """Parse one SWC file into a :class:`Skeleton`.

    :param path: Path to the ``.swc`` file; ``root_id`` comes from its stem.
    :return: The parsed skeleton.
    :raises ValueError: If a row has too few fields, a ``Parent`` names no
        ``PointNo`` in the file, or the file has no point rows at all.
    """
    path = Path(path)
    # str.splitlines() treats CRLF, LF and lone CR uniformly -- the files mix
    # line endings, and this sidesteps that rather than special-casing it.
    raw_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()

    point_ids: list[int] = []
    labels: list[int] = []
    coords: list[tuple[float, float, float]] = []
    radii: list[float] = []
    parent_ids: list[int] = []
    line_numbers: list[int] = []

    for lineno, raw in enumerate(raw_lines, start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 7:
            raise ValueError(f"{path}: line {lineno}: expected 7 fields, got {len(parts)}")
        pid, label, x, y, z, r, parent = parts[:7]
        point_ids.append(int(pid))
        labels.append(int(label))
        coords.append((float(x), float(y), float(z)))
        radii.append(float(r))
        parent_ids.append(int(parent))
        line_numbers.append(lineno)

    if not point_ids:
        raise ValueError(f"{path}: no SWC point rows found")

    index_of = {pid: i for i, pid in enumerate(point_ids)}
    parent = np.empty(len(point_ids), dtype=np.int64)
    for i, (praw, lineno) in enumerate(zip(parent_ids, line_numbers, strict=True)):
        if praw == -1:
            parent[i] = -1
        elif praw in index_of:
            parent[i] = index_of[praw]
        else:
            raise ValueError(f"{path}: line {lineno}: parent {praw} names no PointNo in this file")

    try:
        root_id = int(path.stem)
    except ValueError as exc:
        raise ValueError(f"{path}: file stem {path.stem!r} is not a root id") from exc

    return Skeleton(
        root_id=root_id,
        points=np.asarray(coords, dtype=np.float64),
        radius=np.asarray(radii, dtype=np.float64),
        labels=np.asarray(labels, dtype=np.int64),
        parent=parent,
    )


def write_swc(skeleton: Skeleton, path: str | Path) -> None:
    """Write a :class:`Skeleton` back out as an SWC file, for fixtures and round trips.

    ``PointNo`` is the 1-based row index; this is only ever read back by
    :func:`read_swc`, which does not assume that, so the choice is arbitrary
    but self-consistent.

    :param skeleton: The skeleton to write.
    :param path: Destination path.
    """
    path = Path(path)
    lines = [
        "# SWC format file",
        f'# Meta: {{"id": "{skeleton.root_id}"}}',
        "# PointNo Label X Y Z Radius Parent",
    ]
    for i in range(len(skeleton)):
        point_no = i + 1
        parent_no = -1 if skeleton.parent[i] == -1 else int(skeleton.parent[i]) + 1
        x, y, z = (float(v) for v in skeleton.points[i])
        lines.append(
            f"{point_no} {int(skeleton.labels[i])} {x} {y} {z} "
            f"{float(skeleton.radius[i])} {parent_no}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def soma(skeleton: Skeleton) -> tuple[np.ndarray, bool]:
    """The skeleton's soma point, or a fallback.

    :param skeleton: The skeleton to inspect.
    :return: ``(point, is_soma)`` -- the ``Label 1`` point's coordinates and
        ``True`` when one exists; otherwise the first root point's
        coordinates and ``False``.
    :raises ValueError: If the skeleton has neither a ``Label 1`` row nor a
        root (``Parent == -1``) row.
    """
    labeled = np.nonzero(skeleton.labels == _LABEL_SOMA)[0]
    if labeled.size:
        return skeleton.points[labeled[0]], True
    roots = np.nonzero(skeleton.parent == -1)[0]
    if roots.size == 0:
        raise ValueError("skeleton has no soma row and no root point")
    return skeleton.points[roots[0]], False


def _topological_order(parent: np.ndarray) -> list[int]:
    """Row indices in an order where each point follows its own parent.

    Iterative (no recursion), so it is safe on skeletons with tens of
    thousands of points on one long unbranched run.

    :param parent: ``(n,)`` parent-index array, ``-1`` for a root.
    :return: Row indices, parents before children.
    """
    children: dict[int, list[int]] = {}
    roots: list[int] = []
    for i, p in enumerate(parent):
        if p == -1:
            roots.append(i)
        else:
            children.setdefault(int(p), []).append(i)
    order: list[int] = []
    stack = list(roots)
    while stack:
        i = stack.pop()
        order.append(i)
        stack.extend(children.get(i, ()))
    return order


def _simplify_keep_mask(parent: np.ndarray, labels: np.ndarray, step: int) -> np.ndarray:
    """Which points :func:`segments` keeps when simplifying.

    Always kept: roots, the soma row, and every structural branch or leaf
    point (out-degree != 1) -- computed from the parent links themselves
    rather than trusted to the file's own fork (5) / end (6) labels, which
    real skeletons do not label consistently, so that topology survives even
    on a file with no fork/end annotations at all. Explicit fork/end labels
    are kept too. Along every run of points strictly between two kept
    points, every ``step``-th point is kept as well.

    :param parent: ``(n,)`` parent-index array.
    :param labels: ``(n,)`` SWC label array.
    :param step: Keep every this-th point along an unbranched run.
    :return: Boolean keep mask, ``(n,)``.
    """
    n = len(parent)
    out_degree = np.zeros(n, dtype=np.int64)
    for p in parent:
        if p != -1:
            out_degree[p] += 1
    structural = (
        (parent == -1) | (out_degree != 1) | (labels == _LABEL_FORK) | (labels == _LABEL_END)
    )
    soma_rows = labels == _LABEL_SOMA
    keep = structural | soma_rows

    children: dict[int, list[int]] = {}
    for i, p in enumerate(parent):
        if p != -1:
            children.setdefault(int(p), []).append(i)
    roots = [i for i in range(n) if parent[i] == -1]

    # Distance (in edges) since the nearest kept ancestor, reset to 0 every
    # time a kept point is passed. Iterative DFS -- safe on a long run.
    stack: list[tuple[int, int]] = [(r, 0) for r in roots]
    visited = np.zeros(n, dtype=bool)
    while stack:
        i, dist = stack.pop()
        if visited[i]:
            continue
        visited[i] = True
        already_kept = bool(keep[i])
        if already_kept or (step > 0 and dist % step == 0):
            keep[i] = True
            next_dist = 0
        else:
            next_dist = dist
        for c in children.get(i, ()):
            stack.append((c, next_dist + 1))
    return keep


def _nearest_kept_ancestor(parent: np.ndarray, keep: np.ndarray) -> np.ndarray:
    """Each point's nearest kept ancestor, walking up the parent chain.

    :param parent: ``(n,)`` parent-index array.
    :param keep: ``(n,)`` boolean keep mask.
    :return: ``(n,)`` int array; ``-1`` when a point has no kept ancestor
        (it is itself a root).
    """
    n = len(parent)
    anc = np.full(n, -1, dtype=np.int64)
    for i in _topological_order(parent):
        p = parent[i]
        if p == -1:
            anc[i] = -1
        elif keep[p]:
            anc[i] = p
        else:
            anc[i] = anc[p]
    return anc


def segments(skeleton: Skeleton, *, step: int = 1) -> np.ndarray:
    """Child-to-parent line segments, optionally simplified.

    :param skeleton: The skeleton to draw.
    :param step: ``1`` (default) draws every point-to-parent edge. Above
        ``1``, simplifies first via :func:`_simplify_keep_mask` and connects
        each kept point straight to its nearest kept ancestor, so the
        simplified skeleton's topology (which points connect to which)
        matches the full one.
    :return: ``(m, 2, 3)`` array of ``(start, end)`` point pairs, nanometres.
    """
    parent = skeleton.parent
    if step <= 1:
        keep = np.ones(len(parent), dtype=bool)
        anc = parent
    else:
        keep = _simplify_keep_mask(parent, skeleton.labels, step)
        anc = _nearest_kept_ancestor(parent, keep)
    idx = np.nonzero(keep & (anc != -1))[0]
    if idx.size == 0:
        return np.empty((0, 2, 3), dtype=np.float64)
    starts = skeleton.points[idx]
    ends = skeleton.points[anc[idx]]
    return np.stack([starts, ends], axis=1)


def skeleton_path(data_dir: str | Path, root_id: int) -> Path:
    """The SWC file path for one neuron in the Codex skeleton download.

    :param data_dir: Root of the download (default layout: ``fafb_v783``).
    :param root_id: Neuron root id.
    :return: ``<data_dir>/sk_lod1_783_healed/<root_id>.swc``.
    """
    return Path(data_dir) / SKELETON_SUBDIR / f"{int(root_id)}.swc"


def load_skeletons(
    data_dir: str | Path, root_ids: Iterable[int]
) -> tuple[dict[int, Skeleton], list[int]]:
    """Load whichever of ``root_ids`` have a skeleton file, reporting the rest.

    :param data_dir: Root of the skeleton download.
    :param root_ids: Neuron root ids to load.
    :return: ``(skeletons, missing)`` -- loaded skeletons keyed by root id,
        and the root ids with no file at :func:`skeleton_path`.
    """
    loaded: dict[int, Skeleton] = {}
    missing: list[int] = []
    for root_id in root_ids:
        path = skeleton_path(data_dir, root_id)
        if path.exists():
            loaded[int(root_id)] = read_swc(path)
        else:
            missing.append(int(root_id))
    return loaded, missing


__all__ = [
    "SKELETON_SUBDIR",
    "Skeleton",
    "load_skeletons",
    "read_swc",
    "segments",
    "skeleton_path",
    "soma",
    "write_swc",
]
