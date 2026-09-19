"""Simplified skeletons and somas, cached per dataset from one pass over the SWC download.

The Codex skeleton download is 31 GB of SWC text, one file per neuron
(:func:`connectomekg.skeletons.skeleton_path`). Two things in it are worth
keeping and the rest is not:

* **The soma.** A neuron node's ``x``/``y``/``z`` is FlyWire's *marked point*,
  an anchor that can sit tens of microns from the cell body. The soma is the
  ``Label 1`` row of the skeleton, and it is what every fly atlas draws.
  :func:`write_somas` copies it into the neuron node's metadata as
  ``soma_x``/``soma_y``/``soma_z`` with a ``has_soma`` flag, so the graph
  answers for it without the download and so does every query over it.
* **The shape, simplified.** At :data:`DEFAULT_CACHE_STEP` a skeleton keeps
  about 29 % of its points and all of its topology (see
  :func:`connectomekg.skeletons.segments`), which is what the 3-D circuit view
  draws anyway. One Parquet file holds every neuron's kept points, so a render
  needs neither the 31 GB nor an SWC parse.

Both come out of the same pass, so :func:`build_skeleton_cache` does both and
``connkg skeletons`` writes both. The pass reads every file once and takes
about 25 minutes on a laptop; nothing else in the module needs the download
afterwards.

The cache carries no radii -- the renderer does not use them -- and its labels
are reconstructed, not stored: a cached skeleton's only label is the soma's.
Everything else about it round-trips, so
:func:`connectomekg.skeletons.segments` and :func:`connectomekg.skeletons.soma`
read a cached skeleton exactly as they read a parsed one.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from kg_utils.store import GraphStore

from connectomekg.skeletons import (
    Skeleton,
    _nearest_kept_ancestor,
    _simplify_keep_mask,
    read_swc,
    skeleton_path,
)

__all__ = [
    "DEFAULT_CACHE_STEP",
    "SKELETON_CACHE",
    "CacheReport",
    "build_skeleton_cache",
    "cache_info",
    "effective_step",
    "load_cached_skeletons",
    "skeleton_cache_path",
    "write_somas",
]

#: Cache file name inside a dataset's ``.connectomekg/`` directory.
SKELETON_CACHE: Final = "skeletons.parquet"

#: Simplification stride the cache is built at, matching the circuit view's default.
DEFAULT_CACHE_STEP: Final = 4

#: Neurons per Parquet row group. Rows are written in root-id order, so a read
#: for a few hundred neurons touches a few row groups, not the whole file.
_ROW_GROUP: Final = 2000

_FORMAT: Final = "connectomekg-skeletons-1"

_SCHEMA: Final = pa.schema(
    [
        pa.field("root_id", pa.int64(), nullable=False),
        pa.field("x", pa.list_(pa.float32()), nullable=False),
        pa.field("y", pa.list_(pa.float32()), nullable=False),
        pa.field("z", pa.list_(pa.float32()), nullable=False),
        pa.field("parent", pa.list_(pa.int32()), nullable=False),
        pa.field("soma_index", pa.int32(), nullable=False),
    ]
)


@dataclass(frozen=True)
class CacheReport:
    """What one :func:`build_skeleton_cache` pass found.

    :param n_cached: Neurons written to the cache.
    :param n_missing: Requested neurons with no SWC file.
    :param n_unreadable: Neurons whose SWC file failed to parse.
    :param n_soma: Cached neurons with a real ``Label 1`` soma row.
    :param n_points: Kept points across every cached skeleton.
    :param step: The stride the cache was built at.
    :param bytes_written: Size of the Parquet file.
    """

    n_cached: int
    n_missing: int
    n_unreadable: int
    n_soma: int
    n_points: int
    step: int
    bytes_written: int

    def __str__(self) -> str:
        mb = self.bytes_written / 1e6
        size = f"{mb / 1000:.2f} GB" if mb >= 1000 else f"{mb:.0f} MB"
        lines = [
            f"cached {self.n_cached} skeletons at step {self.step}: "
            f"{self.n_points / 1e6:.1f} M points, {size}",
            f"somas: {self.n_soma} real, {self.n_cached - self.n_soma} fell back to a root point",
        ]
        if self.n_missing:
            lines.append(f"{self.n_missing} neurons have no skeleton file")
        if self.n_unreadable:
            lines.append(f"{self.n_unreadable} skeleton files could not be parsed")
        return "\n".join(lines)


def skeleton_cache_path(db_path: str | Path) -> Path:
    """Where a dataset's skeleton cache lives: beside its graph.

    :param db_path: The dataset's ``graph.sqlite``.
    :return: ``<dataset dir>/.connectomekg/skeletons.parquet``, which may not exist.
    """
    return Path(db_path).parent / SKELETON_CACHE


def effective_step(requested: int, cache_step: int) -> int:
    """The stride to draw a *cached* skeleton with, given the one the caller asked for.

    A cached skeleton has already been simplified at ``cache_step``, so passing
    the caller's stride straight to :func:`connectomekg.skeletons.segments`
    would simplify it a second time and thin it to their product. Dividing
    instead makes the drawn stride approximately the requested one, and a
    request at or below ``cache_step`` draws the cache as it stands -- the
    cache's own stride is the finest detail it holds.

    :param requested: The caller's ``skeleton_step``.
    :param cache_step: The stride the cache was built at.
    :return: The stride to pass to :func:`connectomekg.skeletons.segments`, at least 1.
    """
    return max(1, int(requested) // max(1, int(cache_step)))


def _simplified_row(skeleton: Skeleton, step: int) -> tuple[dict, bool, int]:
    """One skeleton reduced to the columns the cache stores.

    :param skeleton: The parsed skeleton.
    :param step: Simplification stride.
    :return: ``(row, has_soma, n_points)``.
    """
    if step <= 1:
        keep = np.ones(len(skeleton.parent), dtype=bool)
        ancestor = skeleton.parent
    else:
        keep = _simplify_keep_mask(skeleton.parent, skeleton.labels, step)
        ancestor = _nearest_kept_ancestor(skeleton.parent, keep)
    kept = np.nonzero(keep)[0]
    # Kept rows renumbered 0..k-1, so a parent link points inside the kept set.
    position = np.full(len(keep), -1, dtype=np.int64)
    position[kept] = np.arange(len(kept))
    parent = np.where(ancestor[kept] == -1, -1, position[ancestor[kept]])

    soma_rows = np.nonzero(skeleton.labels[kept] == 1)[0]
    points = skeleton.points[kept]
    row = {
        "root_id": int(skeleton.root_id),
        "x": points[:, 0].astype(np.float32),
        "y": points[:, 1].astype(np.float32),
        "z": points[:, 2].astype(np.float32),
        "parent": parent.astype(np.int32),
        "soma_index": int(soma_rows[0]) if soma_rows.size else -1,
    }
    return row, bool(soma_rows.size), len(kept)


def build_skeleton_cache(
    data_dir: str | Path,
    root_ids: Iterable[int],
    dest: str | Path,
    *,
    step: int = DEFAULT_CACHE_STEP,
    progress: Callable[[str], None] | None = None,
) -> tuple[CacheReport, dict[int, tuple[np.ndarray, bool]]]:
    """Read every neuron's SWC file once, writing the cache and collecting somas.

    :param data_dir: Root of the skeleton download (default layout: ``fafb_v783``).
    :param root_ids: Neuron root ids to read, in any order; the cache is
        written in ascending root-id order regardless.
    :param dest: The Parquet file to write, usually
        ``<dataset dir>/.connectomekg/skeletons.parquet``.
    :param step: Simplification stride, at least 1.
    :param progress: Called with a short message every 5,000 neurons.
    :return: ``(report, somas)`` -- ``somas`` maps root id to
        ``(point_nm, is_soma)`` as :func:`connectomekg.skeletons.soma` defines it.
    :raises ValueError: If ``step`` is below 1.
    """
    step = int(step)
    if step < 1:
        raise ValueError(f"step must be at least 1, got {step}")
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    ids = sorted({int(r) for r in root_ids})
    somas: dict[int, tuple[np.ndarray, bool]] = {}
    n_cached = n_missing = n_unreadable = n_soma = n_points = 0
    batch: list[dict] = []
    # Written to a partial file and renamed, so an interrupted pass leaves no
    # half-built cache where the renderer would find one.
    partial = dest.with_suffix(".part")
    writer = pq.ParquetWriter(
        partial,
        _SCHEMA,
        compression="zstd",
        # Read back with a root_id filter; sorted rows make these prune.
        write_statistics=True,
    )

    def flush() -> None:
        if batch:
            writer.write_table(pa.Table.from_pylist(batch, schema=_SCHEMA))
            batch.clear()

    try:
        for i, root_id in enumerate(ids, 1):
            path = skeleton_path(data_dir, root_id)
            if not path.exists():
                n_missing += 1
            else:
                try:
                    skeleton = read_swc(path)
                except ValueError:
                    n_unreadable += 1
                else:
                    row, has_soma, kept = _simplified_row(skeleton, step)
                    batch.append(row)
                    n_cached += 1
                    n_points += kept
                    n_soma += has_soma
                    index = row["soma_index"]
                    if index < 0:
                        roots = np.nonzero(row["parent"] == -1)[0]
                        index = int(roots[0]) if roots.size else 0
                    somas[int(root_id)] = (
                        np.asarray(
                            [row["x"][index], row["y"][index], row["z"][index]], dtype=np.float64
                        ),
                        has_soma,
                    )
                    if len(batch) >= _ROW_GROUP:
                        flush()
            if progress is not None and (i % 5000 == 0 or i == len(ids)):
                progress(f"read {i} of {len(ids)} skeletons ({n_cached} cached)")
        flush()
        writer.add_key_value_metadata(
            {
                "connectomekg.format": _FORMAT,
                "connectomekg.step": str(step),
                "connectomekg.n_neurons": str(n_cached),
            }
        )
    finally:
        writer.close()
    partial.replace(dest)

    return (
        CacheReport(
            n_cached=n_cached,
            n_missing=n_missing,
            n_unreadable=n_unreadable,
            n_soma=n_soma,
            n_points=n_points,
            step=step,
            bytes_written=dest.stat().st_size,
        ),
        somas,
    )


def cache_info(path: str | Path) -> tuple[int, int]:
    """A cache's stride and neuron count, read from its Parquet metadata alone.

    :param path: The cache file.
    :return: ``(step, n_neurons)``.
    :raises ValueError: If the file is not a cache this module wrote.
    """
    # Key-value metadata added at close lands in the file footer, not on the
    # Arrow schema -- `schema_arrow.metadata` reads back None for it.
    metadata = pq.ParquetFile(path).metadata.metadata or {}

    def value(key: str) -> str:
        # Only this module's own keys are decoded: pyarrow's own ARROW:schema
        # entry beside them is not text.
        return (metadata.get(key.encode()) or b"").decode()

    if value("connectomekg.format") != _FORMAT:
        raise ValueError(f"{path}: not a {_FORMAT} skeleton cache")
    return int(value("connectomekg.step")), int(value("connectomekg.n_neurons"))


def load_cached_skeletons(
    path: str | Path, root_ids: Iterable[int]
) -> tuple[dict[int, Skeleton], list[int]]:
    """Read whichever of ``root_ids`` the cache holds, reporting the rest.

    Mirrors :func:`connectomekg.skeletons.load_skeletons`, so a caller can use
    either source.

    :param path: The cache file.
    :param root_ids: Neuron root ids to read.
    :return: ``(skeletons, missing)`` -- the skeletons the cache holds, already
        simplified at its own stride, and the root ids it does not.
    """
    wanted = [int(r) for r in root_ids]
    if not wanted:
        return {}, []
    table = pq.read_table(
        path, filters=[("root_id", "in", set(wanted))], schema=_SCHEMA, use_threads=True
    )
    loaded: dict[int, Skeleton] = {}
    for row in table.to_pylist():
        x = np.asarray(row["x"], dtype=np.float64)
        y = np.asarray(row["y"], dtype=np.float64)
        z = np.asarray(row["z"], dtype=np.float64)
        labels = np.zeros(len(x), dtype=np.int64)
        if row["soma_index"] >= 0:
            labels[row["soma_index"]] = 1
        loaded[int(row["root_id"])] = Skeleton(
            root_id=int(row["root_id"]),
            points=np.stack([x, y, z], axis=1),
            radius=np.zeros(len(x), dtype=np.float64),
            labels=labels,
            parent=np.asarray(row["parent"], dtype=np.int64),
        )
    return loaded, [r for r in wanted if r not in loaded]


def write_somas(store: GraphStore, somas: dict[int, tuple[np.ndarray, bool]]) -> int:
    """Copy somas into their neuron nodes' metadata, in one transaction.

    Adds ``soma_x``, ``soma_y``, ``soma_z`` and ``has_soma`` to each neuron
    node that has a soma here, leaving the marked point (``x``/``y``/``z``) and
    every other key as they were. Running again overwrites the four keys, so a
    second pass over a corrected download is safe.

    :param store: The open store to update.
    :param somas: ``{root_id: (point_nm, is_soma)}``, as
        :func:`build_skeleton_cache` returns.
    :return: Neuron nodes updated.
    """
    con = store.con
    by_root = {
        int(root_id): node_id
        for node_id, root_id in con.execute(
            "SELECT id, json_extract(metadata,'$.root_id') FROM nodes WHERE kind = 'neuron'"
        )
        if root_id is not None
    }
    updates = [
        (
            json.dumps(
                {
                    "soma_x": float(point[0]),
                    "soma_y": float(point[1]),
                    "soma_z": float(point[2]),
                    "has_soma": bool(is_soma),
                }
            ),
            by_root[root_id],
        )
        for root_id, (point, is_soma) in somas.items()
        if root_id in by_root
    ]
    with con:
        con.executemany("UPDATE nodes SET metadata = json_patch(metadata, ?) WHERE id = ?", updates)
    return len(updates)
