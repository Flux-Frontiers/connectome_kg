"""Path and cone queries over the neuron-level synapse graph.

Loads the ``SYNAPSES_TO`` edges of a built store into a sparse matrix once,
then answers strongest-path and downstream/upstream-cone questions with
scipy. Path strength follows the connectome-interpreter convention: an edge's
weight is the fraction of the postsynaptic neuron's input synapses it carries,
and a path's strength is the product along it, so the strongest path is the
Dijkstra shortest path on ``-log(fraction)``.

Reading those edges out of SQLite costs a JSON parse per edge -- on FAFB v783
that is 3.7 M of them, and a process that answers one question pays it once
and then exits. :meth:`SynapseGraph.from_store` therefore writes the matrix it
built to :data:`SYNAPSE_CACHE` beside the graph and reuses it next time: on
FAFB v783 that is 8 seconds of loading turned into under one, for 14 MB. The
cache is keyed on the edge table's shape and the graph file's identity as well
as ``min_syn`` (see :func:`_stamp`), so a rebuilt or re-edited graph is not
answered from a stale one. It is derived data and safe to delete.
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
import scipy.sparse as sp
from kg_utils.store import GraphStore
from scipy.sparse.csgraph import dijkstra

#: Cache file name inside a dataset's ``.connectomekg/`` directory.
SYNAPSE_CACHE: Final = "synapse_graph.npz"

_CACHE_FORMAT: Final = "connectomekg-synapse-graph-1"


def synapse_cache_path(db_path: str | Path) -> Path:
    """Where a dataset's synapse-graph cache lives: beside its graph.

    :param db_path: The dataset's ``graph.sqlite``.
    :return: ``<dataset dir>/.connectomekg/synapse_graph.npz``, which may not exist.
    """
    return Path(db_path).parent / SYNAPSE_CACHE


def _stamp(store: GraphStore, db_path: Path, min_syn: int) -> np.ndarray:
    """The identity a cache is checked against: the edge table, the file, the threshold.

    The edge count and highest rowid come from the store rather than the file,
    because these graphs run in WAL mode: a commit lands in ``graph.sqlite-wal``
    and leaves ``graph.sqlite`` untouched until a checkpoint, so a file stamp
    alone would answer an edited graph from a cache built before the edit.
    Stamping the log file instead does not work either -- merely opening the
    database writes to it, which would invalidate the cache on every run. The
    two together cost about a quarter of a second against the eight this cache
    saves.

    The one edit they do not see is an in-place rewrite of an existing edge's
    ``evidence``, which changes neither count nor rowid. Nothing in this module
    does that; anything that did should delete the cache, which is derived data
    and safe to remove at any time.

    :param store: The open store, for the edge table's shape.
    :param db_path: The dataset's ``graph.sqlite``.
    :param min_syn: The threshold the cached matrix was built with.
    :return: The stamp, as int64.
    """
    n_edges, max_rowid = store.con.execute("SELECT COUNT(*), MAX(rowid) FROM edges").fetchone()
    try:
        stat = db_path.stat()
        size, mtime = stat.st_size, stat.st_mtime_ns
    except OSError:
        size = mtime = 0
    return np.asarray(
        [int(min_syn), int(n_edges or 0), int(max_rowid or 0), size, mtime], dtype=np.int64
    )


@dataclass
class PathHop:
    """One hop of a path.

    :param node_id: Neuron node id.
    :param syn_count: Synapses from the previous hop into this neuron (0 at the start).
    :param fraction: Share of this neuron's input synapses that came from the previous hop.
    :param sign: Sign of the previous hop's transmitter (+1, -1, 0).
    """

    node_id: str
    syn_count: int
    fraction: float
    sign: int


@dataclass
class PathResult:
    """A strongest path.

    :param hops: The hops from source to target inclusive.
    :param strength: Product of the per-hop fractions.
    :param net_sign: Product of the per-hop signs; 0 if any hop is unresolved.
    """

    hops: list[PathHop]
    strength: float
    net_sign: int


@dataclass
class InfluenceResult:
    """How strongly one population drives another, hop by hop.

    A value is a *share of the receiving neuron's input synapses*, averaged
    over the receiving neurons, so it reads directly: 0.15 means the average
    target gets 15 % of its input from the source. Signed, a negative value is
    net inhibition. Shares are averaged rather than summed because a sum over
    several targets is not a share of anything and can exceed 1.

    :param source: The source spec, as given.
    :param target: The target spec, or ``None`` when none was asked for.
    :param hops: Hops computed.
    :param signed: Whether transmitter signs were applied.
    :param n_sources: Source neurons the spec resolved to.
    :param n_targets: Target neurons, 0 when there is no target.
    :param onto: Per-hop mean share onto the target, empty without a target.
    :param ranked: Per-hop ``(cell type, mean share)``, strongest absolute
        influence first.
    """

    source: str
    target: str | None
    hops: int
    signed: bool
    n_sources: int
    n_targets: int
    onto: list[float]
    ranked: list[list[tuple[str, float]]]

    def __str__(self) -> str:
        sign_word = "signed" if self.signed else "unsigned"
        lines = [
            f"influence of {self.source} ({self.n_sources} neurons), {sign_word}, "
            f"as a share of the receiving neuron's input"
        ]
        if self.target is not None:
            lines.append(f"\nonto {self.target} ({self.n_targets} neurons), averaged:")
            lines += [f"  hop {k + 1}: {value:+.4f}" for k, value in enumerate(self.onto)]
            lines.append(f"  total: {sum(self.onto):+.4f}")
        for k, hop in enumerate(self.ranked):
            lines.append(f"\nstrongest cell types at hop {k + 1}:")
            lines += [f"  {value:+.4f}  {name}" for name, value in hop] or ["  (none)"]
        return "\n".join(lines)


class SynapseGraph:
    """The neuron-level wiring of a built store as sparse matrices."""

    def __init__(self, ids: list[str], counts: sp.csr_matrix, signs: np.ndarray) -> None:
        self.ids = ids
        self.index = {nid: i for i, nid in enumerate(ids)}
        self.counts = counts  # (n, n) int synapse counts, row = pre, col = post
        self.signs = signs  # per presynaptic neuron
        in_tot = np.asarray(counts.sum(axis=0)).ravel().astype(float)
        in_tot[in_tot == 0] = 1.0
        frac = counts.tocoo().astype(float)
        frac.data = frac.data / in_tot[frac.col]
        self.fraction = frac.tocsr()
        cost = frac.copy()
        cost.data = -np.log(np.clip(cost.data, 1e-12, 1.0))
        self.cost = cost.tocsr()

    @classmethod
    def from_store(
        cls, store: GraphStore, *, min_syn: int = 1, cache_for: str | Path | None = None
    ) -> SynapseGraph:
        """Load every ``SYNAPSES_TO`` edge from the store.

        :param store: A built :class:`GraphStore`.
        :param min_syn: Drop edges below this synapse count.
        :param cache_for: The store's ``graph.sqlite`` path. When given, a
            matching :func:`synapse_cache_path` cache is read instead of the
            edges, and written after a load that had to read them. ``None``
            reads the edges and writes nothing.
        :return: :class:`SynapseGraph`.
        """
        db_path = Path(cache_for) if cache_for is not None else None
        if db_path is not None:
            cached = cls._read_cache(synapse_cache_path(db_path), _stamp(store, db_path, min_syn))
            if cached is not None:
                return cached
        rows = store.con.execute(
            "SELECT src, dst, evidence FROM edges WHERE rel = 'SYNAPSES_TO'"
        ).fetchall()
        ids: dict[str, int] = {}
        pre, post, cnt, sgn = [], [], [], {}
        for src, dst, ev in rows:
            meta = json.loads(ev) if ev else {}
            s = int(meta.get("syn_count", 1))
            if s < min_syn:
                continue
            for nid in (src, dst):
                if nid not in ids:
                    ids[nid] = len(ids)
            pre.append(ids[src])
            post.append(ids[dst])
            cnt.append(s)
            sgn[ids[src]] = int(meta.get("sign", 0))
        n = len(ids)
        counts = sp.csr_matrix((np.array(cnt, dtype=np.int64), (pre, post)), shape=(n, n))
        signs = np.zeros(n, dtype=int)
        for i, v in sgn.items():
            signs[i] = v
        graph = cls(list(ids), counts, signs)
        if db_path is not None:
            graph._write_cache(synapse_cache_path(db_path), _stamp(store, db_path, min_syn))
        return graph

    @classmethod
    def _read_cache(cls, path: Path, stamp: np.ndarray) -> SynapseGraph | None:
        """Read a cache written by :meth:`_write_cache`, if it matches ``stamp``.

        Any unreadable, truncated or mismatched cache is simply ignored -- it
        is derived data, and rebuilding it costs only the load it was meant to
        save.

        :param path: The cache file.
        :param stamp: The identity the cache must carry to be used.
        :return: The cached graph, or ``None``.
        """
        if not path.exists():
            return None
        try:
            with np.load(path, allow_pickle=False) as npz:
                if str(npz["format"]) != _CACHE_FORMAT or not np.array_equal(npz["stamp"], stamp):
                    return None
                counts = sp.csr_matrix(
                    (npz["data"], npz["indices"], npz["indptr"]), shape=tuple(npz["shape"])
                )
                return cls([str(i) for i in npz["ids"]], counts, npz["signs"])
        except (OSError, ValueError, KeyError):
            return None

    def _write_cache(self, path: Path, stamp: np.ndarray) -> None:
        """Write this graph's matrix beside the store, whole then renamed.

        A failure here is not worth raising over -- the caller has the graph it
        asked for either way -- so an unwritable directory leaves no cache and
        no error.

        :param path: The cache file.
        :param stamp: The identity to record, from :func:`_stamp`.
        """
        buffer = io.BytesIO()
        np.savez_compressed(
            buffer,
            format=np.asarray(_CACHE_FORMAT),
            stamp=stamp,
            ids=np.asarray(self.ids),
            data=self.counts.data,
            indices=self.counts.indices,
            indptr=self.counts.indptr,
            shape=np.asarray(self.counts.shape, dtype=np.int64),
            signs=np.asarray(self.signs),
        )
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            partial = path.with_suffix(".part")
            partial.write_bytes(buffer.getvalue())
            partial.replace(path)
        except OSError:
            return

    def influence(self, sources: list[str], *, hops: int = 3, signed: bool = True) -> np.ndarray:
        """How much of each neuron's input the source population drives, hop by hop.

        The convention is the one :class:`SynapseGraph` already uses for path
        strength, from connectome-interpreter: an edge's weight is the share of
        the postsynaptic neuron's input synapses it carries. Starting a unit of
        drive on every source neuron and propagating it forward therefore gives,
        at hop 1, the share of each neuron's input that comes from the sources;
        at hop 2, the share arriving through one intermediary; and so on. The
        values need no normalisation to be read, because a share of a neuron's
        input is already what they are.

        Signed, that share can be negative: a source reaching a target through
        an inhibitory neuron subtracts from it, and two routes of opposite sign
        cancel, which is the point of computing it rather than counting paths.

        Computed by propagating a vector, not by raising the matrix to a power.
        The matrix is 139,255 square on FAFB v783, so a single dense power is
        1.5e10 entries; a sparse matrix-vector product is one pass over the
        3.7 M edges and runs in milliseconds.

        Recurrence is not removed. A source that is also downstream of itself
        appears again at a later hop, which is a property of the brain rather
        than of the arithmetic.

        :param sources: Neuron node ids to start the drive on. Ids not in this
            graph are ignored.
        :param hops: Hops to propagate, at least 1.
        :param signed: Weight each step by the presynaptic transmitter sign, so
            the result is net excitation (positive) or inhibition (negative).
            Unsigned treats every synapse as excitatory.
        :return: ``(hops, n)`` float64; row ``k`` is the share arriving in
            exactly ``k + 1`` hops, indexed like :attr:`ids`.
        :raises ValueError: If ``hops`` is below 1.
        """
        if int(hops) < 1:
            raise ValueError(f"hops must be at least 1, got {hops}")
        weights = self.fraction
        if signed:
            # Row i carries neuron i's outgoing edges, so its sign scales the
            # whole row; signs of 0 (unresolved transmitter) zero that route,
            # which is honest -- an unknown sign cannot be added up.
            weights = sp.diags(self.signs.astype(float)) @ self.fraction
        drive = np.zeros(len(self.ids), dtype=float)
        seeded = [self.index[s] for s in sources if s in self.index]
        drive[seeded] = 1.0
        out = np.empty((int(hops), len(self.ids)), dtype=float)
        for k in range(int(hops)):
            drive = drive @ weights
            out[k] = drive
        return out

    def strongest_path(self, sources: list[str], targets: list[str]) -> PathResult | None:
        """Strongest path from any source neuron to any target neuron.

        :param sources: Neuron node ids to start from.
        :param targets: Neuron node ids to reach.
        :return: :class:`PathResult`, or ``None`` when nothing is reachable.
        """
        src = [self.index[s] for s in sources if s in self.index]
        dst = [self.index[t] for t in targets if t in self.index]
        if not src or not dst:
            return None
        dist, pred, srcs = dijkstra(
            self.cost, directed=True, indices=src, return_predecessors=True, min_only=True
        )
        best = min(dst, key=lambda j: dist[j])
        if not np.isfinite(dist[best]):
            return None
        chain = [best]
        while pred[chain[-1]] >= 0:
            chain.append(int(pred[chain[-1]]))
        chain.reverse()
        hops = [PathHop(self.ids[chain[0]], 0, 1.0, 0)]
        for a, b in zip(chain, chain[1:], strict=False):
            hops.append(
                PathHop(
                    self.ids[b],
                    int(self.counts[a, b]),
                    float(self.fraction[a, b]),
                    int(self.signs[a]),
                )
            )
        net = 1
        for h in hops[1:]:
            net *= h.sign
        return PathResult(hops, float(np.exp(-dist[best])), int(net))

    def cone(
        self, seeds: list[str], *, hops: int = 1, min_syn: int = 1, direction: str = "down"
    ) -> dict[str, int]:
        """Neurons reachable within ``hops`` steps above a synapse threshold.

        :param seeds: Neuron node ids at hop 0.
        :param hops: Number of steps.
        :param min_syn: Only follow edges with at least this many synapses.
        :param direction: ``"down"`` follows outputs, ``"up"`` follows inputs.
        :return: ``{node_id: first hop reached}`` including the seeds at 0.
        """
        m = self.counts if direction == "down" else self.counts.T.tocsr()
        reached = {self.index[s]: 0 for s in seeds if s in self.index}
        frontier = list(reached)
        for h in range(1, hops + 1):
            nxt = []
            for i in frontier:
                row = m.getrow(i)
                for j, s in zip(row.indices, row.data, strict=True):
                    if s >= min_syn and j not in reached:
                        reached[int(j)] = h
                        nxt.append(int(j))
            frontier = nxt
        return {self.ids[i]: h for i, h in reached.items()}
