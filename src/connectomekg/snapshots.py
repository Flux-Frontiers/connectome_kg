"""Snapshots of a built ConnectomeKG graph, on the shared ``kg_utils`` manager.

A snapshot records a graph's metrics at a point in time. It is keyed on a
release tag, or on a UTC timestamp between releases, never on the git tree
hash, which the shared manager records only as provenance alongside the tool,
its version, the branch and the subject (``corpus:<dataset id>``). This module follows the fleet snapshot standard: it sets
``package_name`` and supplies connectome metrics through ``_domain_metrics``,
and overrides nothing else. Saving, keying, listing, diffing and pruning are
the base class's.

Snapshots live in ``.connectomekg/snapshots/`` and are tracked in git.

Usage
-----
>>> from connectomekg.snapshots import SnapshotManager
>>> mgr = SnapshotManager(".connectomekg/snapshots", db_path=".connectomekg/graph.sqlite")
>>> snap = mgr.capture(graph_stats_dict=stats, key="0.2.0", subject="corpus:fafb783",
...                    hotspots=mgr.hub_neurons())
>>> mgr.save_snapshot(snap, force=True)
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from typing import Any

from kg_utils.snapshots import Snapshot as Snapshot  # noqa: F401 -- re-export
from kg_utils.snapshots import SnapshotManager as _BaseSnapshotManager

__all__ = ["Snapshot", "SnapshotManager"]

#: Coverage metric name to the neuron-metadata condition that counts toward it.
_COVERAGE = {
    "cell_type": "json_extract(metadata,'$.cell_type') != ''",
    "sign": "json_extract(metadata,'$.sign') != 0",
    "visual_family": "json_extract(metadata,'$.visual_family') != ''",
    "column": "json_extract(metadata,'$.column') != ''",
    "ontology_term": "json_array_length(metadata,'$.fbbt') > 0",
    "length": "json_extract(metadata,'$.length_nm') IS NOT NULL",
    # Written by `connkg skeletons`, not by the build, so this one is 0 on a
    # freshly built graph and rises once the skeleton download has been read.
    # Without it a snapshot cannot tell a graph that knows where its cell
    # bodies are from one that only has FlyWire's marked points: the back-fill
    # adds metadata, never a node or an edge, so every other metric here is
    # identical either way.
    "soma": "json_extract(metadata,'$.has_soma') = 1",
}


class SnapshotManager(_BaseSnapshotManager):
    """ConnectomeKG snapshot manager.

    Adds the dataset record (id, version, neurons, pairs, synapses) and the
    share of neurons carrying each annotation layer to every snapshot's
    metrics, read from the graph database.
    """

    package_name = "connectome-kg"

    #: ``GraphStore.stats()`` counts the snapshots on disk, so saving one changes
    #: it; left in, no two saves would ever look unchanged and dedup would never
    #: happen.
    metrics_ignore = frozenset({"snapshot_count"})

    def _domain_metrics(self, stats: dict[str, Any]) -> dict[str, Any]:
        """Dataset figures and per-layer neuron coverage from the graph.

        :param stats: Graph stats passed to ``capture()``; not used.
        :return: ``dataset_id``, ``dataset_version``, ``n_neurons``, ``n_pairs``,
            ``n_synapses`` and ``coverage`` (fraction of neurons per layer).
        """
        con = self._connect()
        if con is None:
            return {}
        with closing(con):
            row = con.execute(
                "SELECT qualname, metadata FROM nodes WHERE kind='dataset'"
            ).fetchone()
            meta = json.loads(row[1]) if row and row[1] else {}
            n = con.execute("SELECT COUNT(*) FROM nodes WHERE kind='neuron'").fetchone()[0]
            coverage = {}
            if n:
                for name, cond in _COVERAGE.items():
                    k = con.execute(
                        f"SELECT COUNT(*) FROM nodes WHERE kind='neuron' AND {cond}"
                    ).fetchone()[0]
                    coverage[name] = round(k / n, 4)
        return {
            "dataset_id": row[0] if row else "",
            "dataset_version": meta.get("version", ""),
            "n_neurons": meta.get("n_neurons", n),
            "n_pairs": meta.get("n_pairs", 0),
            "n_synapses": meta.get("n_synapses", 0),
            "coverage": coverage,
        }

    def hub_neurons(self, top: int = 10) -> list[dict[str, Any]]:
        """The neurons with the most output synapses, for a snapshot's ``hotspots``.

        :param top: How many to return.
        :return: Dicts with ``id``, ``name``, ``qualname``, ``n_out_syn`` and ``n_in_syn``.
        """
        con = self._connect()
        if con is None:
            return []
        with closing(con):
            rows = con.execute(
                "SELECT id, name, qualname, json_extract(metadata,'$.n_out_syn'), "
                "json_extract(metadata,'$.n_in_syn') FROM nodes WHERE kind='neuron' "
                "ORDER BY json_extract(metadata,'$.n_out_syn') DESC LIMIT ?",
                (top,),
            ).fetchall()
        return [
            {"id": r[0], "name": r[1], "qualname": r[2], "n_out_syn": r[3], "n_in_syn": r[4]}
            for r in rows
        ]

    def _connect(self) -> sqlite3.Connection | None:
        if not self.db_path or not self.db_path.exists():
            return None
        try:
            return sqlite3.connect(str(self.db_path))
        except sqlite3.Error:
            return None
