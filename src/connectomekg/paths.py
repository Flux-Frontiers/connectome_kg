"""Path and cone queries over the neuron-level synapse graph.

Loads the ``SYNAPSES_TO`` edges of a built store into a sparse matrix once,
then answers strongest-path and downstream/upstream-cone questions with
scipy. Path strength follows the connectome-interpreter convention: an edge's
weight is the fraction of the postsynaptic neuron's input synapses it carries,
and a path's strength is the product along it, so the strongest path is the
Dijkstra shortest path on ``-log(fraction)``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np
import scipy.sparse as sp
from kg_utils.store import GraphStore
from scipy.sparse.csgraph import dijkstra


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
    def from_store(cls, store: GraphStore, *, min_syn: int = 1) -> SynapseGraph:
        """Load every ``SYNAPSES_TO`` edge from the store.

        :param store: A built :class:`GraphStore`.
        :param min_syn: Drop edges below this synapse count.
        :return: :class:`SynapseGraph`.
        """
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
        return cls(list(ids), counts, signs)

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
