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
  draws anyway. The cache is a directory of Parquet shards holding every
  neuron's kept points -- 212 M of them in 2.5 GB on FAFB v783, against the
  download's 31 GB -- so a render needs neither the download nor an SWC parse.

Both come out of the same pass, so :func:`build_skeleton_cache` does both and
``connkg skeletons`` writes both. The pass reads every file once: 19m 30s on
one core for FAFB v783, or 2m 39s across twelve, since parsing SWC is pure
Python and splits cleanly across processes. Nothing else in the module needs
the download afterwards.

The cache carries no radii -- the renderer does not use them -- and its labels
are reconstructed, not stored: a cached skeleton's only label is the soma's.
Everything else about it round-trips, so
:func:`connectomekg.skeletons.segments` and :func:`connectomekg.skeletons.soma`
read a cached skeleton exactly as they read a parsed one.
"""

from __future__ import annotations

import json
import multiprocessing
import shutil
from collections.abc import Callable, Iterable, Iterator
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

#: Cache directory name inside a dataset's ``.connectomekg/`` directory. It
#: holds one ``part-NNNN.parquet`` shard per worker that built it.
SKELETON_CACHE: Final = "skeletons"

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
    :param bytes_written: Total size of the cache's Parquet shards.
    :param n_shards: Shards written, one per worker.
    """

    n_cached: int
    n_missing: int
    n_unreadable: int
    n_soma: int
    n_points: int
    step: int
    bytes_written: int
    n_shards: int = 1

    def __str__(self) -> str:
        n = float(self.bytes_written)
        for unit in ("B", "KB", "MB", "GB"):
            if n < 1000 or unit == "GB":
                size = f"{int(n)} {unit}" if unit == "B" else f"{n:.1f} {unit}"
                break
            n /= 1000
        points = (
            f"{self.n_points / 1e6:.1f} M points"
            if self.n_points >= 1e6
            else f"{self.n_points:,} points"
        )
        shards = "" if self.n_shards <= 1 else f" across {self.n_shards} shards"
        lines = [
            f"cached {self.n_cached} skeletons at step {self.step}: {points}, {size}{shards}",
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
    :return: ``<dataset dir>/.connectomekg/skeletons/``, which may not exist.
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


@dataclass(frozen=True)
class _ShardResult:
    """What one worker sends back: counters and somas, never the geometry.

    The geometry is the whole point of the cache and far too big to pipe --
    3.7 GB of it on FAFB v783 -- so a worker writes its own shard and returns
    only what the parent has to add up. This is where the pattern departs from
    ``proteusPy``'s ``extract_disulfides_chunk``, which hands its results back
    for the parent to concatenate.
    """

    n_cached: int
    n_missing: int
    n_unreadable: int
    n_soma: int
    n_points: int
    somas: dict[int, tuple[np.ndarray, bool]]


def _write_shard(args: tuple[str, list[int], str, int]) -> _ShardResult:
    """Read one contiguous range of root ids into one Parquet shard.

    Module-level and taking a single plain tuple, so it is picklable for
    :class:`multiprocessing.Pool`. Root ids arrive already sorted and the
    ranges are disjoint, so each shard's row-group statistics cover a range no
    other shard touches and a filtered read still prunes to a handful of them.

    :param args: ``(data_dir, root_ids, shard_path, step)``.
    :return: The shard's counters and somas.
    """
    data_dir, ids, shard_path, step = args
    somas: dict[int, tuple[np.ndarray, bool]] = {}
    n_cached = n_missing = n_unreadable = n_soma = n_points = 0
    batch: list[dict] = []
    writer = pq.ParquetWriter(shard_path, _SCHEMA, compression="zstd", write_statistics=True)

    def flush() -> None:
        if batch:
            writer.write_table(pa.Table.from_pylist(batch, schema=_SCHEMA))
            batch.clear()

    try:
        for root_id in ids:
            path = skeleton_path(data_dir, root_id)
            if not path.exists():
                n_missing += 1
                continue
            try:
                skeleton = read_swc(path)
            except ValueError:
                n_unreadable += 1
                continue
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
                np.asarray([row["x"][index], row["y"][index], row["z"][index]], dtype=np.float64),
                has_soma,
            )
            if len(batch) >= _ROW_GROUP:
                flush()
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
    return _ShardResult(n_cached, n_missing, n_unreadable, n_soma, n_points, somas)


def _chunk(ids: list[int], jobs: int) -> list[list[int]]:
    """Split sorted root ids into at most ``jobs`` contiguous, non-empty ranges.

    Contiguous rather than round-robin, so each shard holds a disjoint span of
    root ids and Parquet's own statistics can skip the shards a query does not
    want.

    :param ids: Sorted root ids.
    :param jobs: Requested worker count.
    :return: The ranges, in order.
    """
    jobs = max(1, min(int(jobs), len(ids))) if ids else 1
    size = len(ids) // jobs
    bounds = [(i * size, (i + 1) * size if i != jobs - 1 else len(ids)) for i in range(jobs)]
    return [ids[lo:hi] for lo, hi in bounds if hi > lo]


def build_skeleton_cache(
    data_dir: str | Path,
    root_ids: Iterable[int],
    dest: str | Path,
    *,
    step: int = DEFAULT_CACHE_STEP,
    jobs: int = 1,
    progress: Callable[[str], None] | None = None,
) -> tuple[CacheReport, dict[int, tuple[np.ndarray, bool]]]:
    """Read every neuron's SWC file once, writing the cache and collecting somas.

    Parsing an SWC file is pure Python and holds the GIL, so the pass is bound
    by one core until it is split across processes: ``jobs`` of them, each
    taking a contiguous range of root ids and writing its own shard, after
    ``proteusPy``'s ``DisulfideExtractor_mp``. The cache is the directory of
    those shards, which :func:`load_cached_skeletons` reads as one.

    :param data_dir: Root of the skeleton download (default layout: ``fafb_v783``).
    :param root_ids: Neuron root ids to read, in any order; the cache is
        written in ascending root-id order regardless.
    :param dest: The cache directory to write, usually
        ``<dataset dir>/.connectomekg/skeletons``.
    :param step: Simplification stride, at least 1.
    :param jobs: Worker processes; 1 runs in this process and starts no pool.
        Above the number of neurons it is reduced to that.
    :param progress: Called with a short message as each shard finishes.
    :return: ``(report, somas)`` -- ``somas`` maps root id to
        ``(point_nm, is_soma)`` as :func:`connectomekg.skeletons.soma` defines it.
    :raises ValueError: If ``step`` or ``jobs`` is below 1.
    """
    step = int(step)
    if step < 1:
        raise ValueError(f"step must be at least 1, got {step}")
    if int(jobs) < 1:
        raise ValueError(f"jobs must be at least 1, got {jobs}")
    dest = Path(dest)

    ids = sorted({int(r) for r in root_ids})
    chunks = _chunk(ids, jobs)
    # Built beside the destination and renamed over it at the end, so an
    # interrupted pass never leaves a half-written cache where the renderer
    # would find one, and a rebuild does not read its own leftovers.
    partial = dest.with_name(dest.name + ".part")
    shutil.rmtree(partial, ignore_errors=True)
    partial.mkdir(parents=True)

    totals = _ShardResult(0, 0, 0, 0, 0, {})
    finished = False
    try:
        work = [
            (str(data_dir), chunk, str(partial / f"part-{k:04d}.parquet"), step)
            for k, chunk in enumerate(chunks)
        ]
        done = 0
        for result in _run_shards(work, jobs):
            done += 1
            totals = _ShardResult(
                totals.n_cached + result.n_cached,
                totals.n_missing + result.n_missing,
                totals.n_unreadable + result.n_unreadable,
                totals.n_soma + result.n_soma,
                totals.n_points + result.n_points,
                {**totals.somas, **result.somas},
            )
            if progress is not None:
                progress(
                    f"shard {done} of {len(work)} done "
                    f"({totals.n_cached} of {len(ids)} skeletons cached)"
                )
        if dest.exists():
            shutil.rmtree(dest)
        partial.replace(dest)
        finished = True
    finally:
        # Not `except Exception`: Ctrl-C is the likeliest way a long read ends
        # early, and it must not leave gigabytes of shards behind either.
        if not finished:
            shutil.rmtree(partial, ignore_errors=True)

    return (
        CacheReport(
            n_cached=totals.n_cached,
            n_missing=totals.n_missing,
            n_unreadable=totals.n_unreadable,
            n_soma=totals.n_soma,
            n_points=totals.n_points,
            step=step,
            bytes_written=sum(f.stat().st_size for f in dest.glob("*.parquet")),
            n_shards=len(chunks),
        ),
        totals.somas,
    )


def _run_shards(work: list[tuple[str, list[int], str, int]], jobs: int) -> Iterator[_ShardResult]:
    """Run the shard workers, in this process or in a pool, yielding as they finish.

    One shard never starts a pool: it keeps the single-job path free of
    multiprocessing entirely, which is what the tests and small datasets use.

    :param work: One argument tuple per shard.
    :param jobs: Worker processes requested.
    :yield: Each shard's :class:`_ShardResult`.
    """
    if len(work) <= 1 or jobs <= 1:
        for args in work:
            yield _write_shard(args)
        return
    # A pool whose workers die on Ctrl-C leaves the parent hanging in join();
    # terminate() on the way out is what makes an interrupt actually interrupt.
    pool = multiprocessing.Pool(min(jobs, len(work)))
    try:
        yield from pool.imap_unordered(_write_shard, work)
        pool.close()
    except BaseException:
        pool.terminate()
        raise
    finally:
        pool.join()


def cache_info(path: str | Path) -> tuple[int, int]:
    """A cache's stride and neuron count, read from its Parquet metadata alone.

    Every shard records the same stride, so the stride comes from the first of
    them; the neuron count is summed across all of them, since each shard
    counts only its own.

    :param path: The cache directory.
    :return: ``(step, n_neurons)``.
    :raises ValueError: If the directory holds no shard this module wrote.
    """
    shards = sorted(Path(path).glob("*.parquet"))
    if not shards:
        raise ValueError(f"{path}: no {_FORMAT} shards here")
    step = 0
    n_neurons = 0
    for shard in shards:
        # Key-value metadata added at close lands in the file footer, not on
        # the Arrow schema -- `schema_arrow.metadata` reads back None for it.
        metadata = pq.ParquetFile(shard).metadata.metadata or {}

        def value(key: str, metadata: dict = metadata) -> str:
            # Only this module's own keys are decoded: pyarrow's own
            # ARROW:schema entry beside them is not text.
            return (metadata.get(key.encode()) or b"").decode()

        if value("connectomekg.format") != _FORMAT:
            raise ValueError(f"{shard}: not a {_FORMAT} skeleton cache")
        step = int(value("connectomekg.step"))
        n_neurons += int(value("connectomekg.n_neurons"))
    return step, n_neurons


def load_cached_skeletons(
    path: str | Path, root_ids: Iterable[int]
) -> tuple[dict[int, Skeleton], list[int]]:
    """Read whichever of ``root_ids`` the cache holds, reporting the rest.

    Mirrors :func:`connectomekg.skeletons.load_skeletons`, so a caller can use
    either source.

    The cache is a directory of shards; pyarrow reads it as one table, and
    because each shard holds a disjoint span of root ids their row-group
    statistics prune a filtered read down to the few shards that can match.

    :param path: The cache directory.
    :param root_ids: Neuron root ids to read.
    :return: ``(skeletons, missing)`` -- the skeletons the cache holds, already
        simplified at its own stride, and the root ids it does not.
    """
    wanted = [int(r) for r in root_ids]
    if not wanted or not any(Path(path).glob("*.parquet")):
        return {}, wanted
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
