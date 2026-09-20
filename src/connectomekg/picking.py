"""Turning a click in the 3-D viewer into a neuron, and a neuron into a description.

The circuit view draws every neuron of one cell type into a *single* line mesh
(``skeleton:<type>`` in :func:`connectomekg.scene.build_brain_scene`), which is
what keeps a 500-neuron scene at a handful of draw calls. It also means VTK can
say which actor was clicked, and therefore which cell type, but not which
neuron -- and "which neuron" is the whole question a click is asking.

So identity is carried beside the geometry rather than inside it.
:class:`PickTargets` holds every point the circuit drew, in world coordinates,
with the index of the neuron that owns it, and resolves a clicked position to
the nearest one. Nothing here depends on how the mesh was built, so it is
unaffected by ``--tubes``, by the simplification stride, and by whether VTK
propagates point data through ``tube()`` and ``glyph()``, which it does
inconsistently.

This module imports neither PyVista nor Qt, so it is testable with no extra
installed; :mod:`connectomekg.viz3d` is the only caller that needs either.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from scipy.spatial import cKDTree

    from connectomekg.module import ConnectomeKG

__all__ = ["PickTargets", "neuron_partners", "pick_summary"]

#: Partner types listed per direction in a pick summary.
DEFAULT_PARTNER_LIMIT = 5


@dataclass
class PickTargets:
    """Every point the circuit view drew, and which neuron owns each one.

    :param points: ``(n, 3)`` float32 world coordinates, one row per drawn
        point: skeleton vertices, and the marked point of a neuron drawn as a
        fallback sphere.
    :param owner: ``(n,)`` int32 index into :attr:`neuron_ids`.
    :param neuron_ids: Neuron node ids, indexed by :attr:`owner`.
    """

    points: np.ndarray
    owner: np.ndarray
    neuron_ids: list[str]
    _tree: cKDTree | None = field(default=None, repr=False, compare=False)

    def __len__(self) -> int:
        return len(self.points)

    @classmethod
    def empty(cls) -> PickTargets:
        """Targets for a scene with no circuit in it, such as the flow view."""
        return cls(np.empty((0, 3), dtype=np.float32), np.empty(0, dtype=np.int32), [])

    def nearest(self, point: Any, *, within: float | None = None) -> str | None:
        """The neuron whose drawn geometry lies closest to a clicked position.

        The tree is built on the first call and kept, so the cost falls on the
        first click rather than on composing the scene.

        :param point: A 3-vector in world coordinates.
        :param within: Reject a hit further away than this, in world units
            (1 unit is 100,000 nm). ``None`` accepts the nearest whatever the
            distance.
        :return: The neuron's node id, or ``None`` when the scene drew no
            circuit or nothing lies close enough.
        """
        if not len(self.points):
            return None
        if self._tree is None:
            from scipy.spatial import cKDTree  # noqa: PLC0415 - built on first pick only

            self._tree = cKDTree(self.points)
        distance, index = self._tree.query(np.asarray(point, dtype=np.float64).reshape(3))
        if within is not None and distance > within:
            return None
        return self.neuron_ids[int(self.owner[int(index)])]


class _Collector:
    """Accumulates pick targets while the circuit is drawn, one neuron at a time."""

    def __init__(self) -> None:
        self._batches: list[np.ndarray] = []
        self._owners: list[np.ndarray] = []
        self.neuron_ids: list[str] = []

    def add(self, node_id: str, points_world: np.ndarray) -> None:
        """Record one neuron's drawn points.

        :param node_id: The neuron's node id.
        :param points_world: ``(k, 3)`` world coordinates; ignored when empty.
        """
        points = np.asarray(points_world, dtype=np.float32).reshape(-1, 3)
        if not len(points):
            return
        index = len(self.neuron_ids)
        self.neuron_ids.append(node_id)
        self._batches.append(points)
        self._owners.append(np.full(len(points), index, dtype=np.int32))

    def build(self) -> PickTargets:
        """The accumulated targets."""
        if not self._batches:
            return PickTargets.empty()
        return PickTargets(
            np.concatenate(self._batches, axis=0),
            np.concatenate(self._owners, axis=0),
            self.neuron_ids,
        )


def neuron_partners(
    kg: ConnectomeKG, node_id: str, *, limit: int = DEFAULT_PARTNER_LIMIT
) -> tuple[list[tuple[str, int]], list[tuple[str, int]]]:
    """One neuron's strongest partner *types*, by synapses, each way.

    Types rather than individual partners: a click is asking what this neuron
    talks to, and a list of root ids does not answer that.

    :param kg: An open ``ConnectomeKG``.
    :param node_id: The neuron's node id.
    :param limit: Types per direction.
    :return: ``(inputs, outputs)``, each ``(cell type, synapses)`` strongest first.
    """

    def side(column: str, other: str) -> list[tuple[str, int]]:
        totals: dict[str, int] = {}
        rows = kg.store.con.execute(
            f"SELECT n.name, e.evidence FROM edges e JOIN nodes n ON n.id = e.{other} "
            f"WHERE e.rel = 'SYNAPSES_TO' AND e.{column} = ?",
            (node_id,),
        )
        for name, evidence in rows:
            count = int(json.loads(evidence).get("syn_count", 0)) if evidence else 0
            key = name or "untyped"
            totals[key] = totals.get(key, 0) + count
        ranked = sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))
        return ranked[:limit]

    return side("dst", "src"), side("src", "dst")


def pick_summary(kg: ConnectomeKG, node_id: str, *, limit: int = DEFAULT_PARTNER_LIMIT) -> str:
    """What the viewer shows when a neuron is clicked.

    The neuron's own line is its stored ``docstring``, written by
    :func:`connectomekg.describe.neuron_docstring` when the graph was built, so
    a picked neuron reads exactly as it does everywhere else in the module.

    :param kg: An open ``ConnectomeKG``.
    :param node_id: The neuron's node id.
    :param limit: Partner types listed per direction.
    :return: Plain text, one blank line between sections.
    """
    node = kg.describe(node_id)
    if node is None:
        return f"{node_id}\n\nNo such node in this graph."
    lines = [node.get("qualname") or node.get("name") or node_id]
    docstring = (node.get("docstring") or "").strip()
    if docstring:
        lines += ["", docstring]
    inputs, outputs = neuron_partners(kg, node_id, limit=limit)
    for label, partners in (("Inputs", inputs), ("Outputs", outputs)):
        lines += [
            "",
            f"{label}: "
            + (", ".join(f"{name} ({count})" for name, count in partners) if partners else "none"),
        ]
    return "\n".join(lines)
