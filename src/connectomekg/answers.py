"""Turning a question into something drawable: a path or a cone as coloured groups.

``connkg path`` and ``connkg cone`` already know which neurons answer a
question and in what order. This turns that answer into
:class:`connectomekg.scene.NeuronGroup` objects, one per hop, coloured along
:func:`connectomekg.colors.hop_color` so the order is legible.

It also gives the answers a spec-like written form, so anywhere that takes a
spec can take an answer instead:

===========================  ========================================
``path:LPLC2>DNp01``         the strongest path between two specs
``cone:DNp01``               one hop downstream
``cone:DNp01>3``             three hops downstream
``cone:DNp01<2``             two hops upstream
===========================  ========================================

The arrow points the way the signal travels, which is why upstream uses ``<``.
That form is what lets the 3-D viewer's Show box draw an answer without a
grammar of its own, and it follows the ``label:`` prefix the spec grammar
already has.

No PyVista and no Qt here, so it is testable with no extra installed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from connectomekg.colors import hop_color
from connectomekg.validation import MAX_HOP, MAX_SCENE_NEURONS, bounded_int

if TYPE_CHECKING:
    from connectomekg.module import ConnectomeKG
    from connectomekg.scene import NeuronGroup

__all__ = ["Answer", "ANSWER_SYNTAX", "answer_groups", "is_answer", "parse_answer"]

#: Shown wherever an answer query can be typed or passed.
ANSWER_SYNTAX = "path:FROM>TO, cone:SPEC, cone:SPEC>HOPS (downstream), cone:SPEC<HOPS (upstream)"

# Either side may be empty here so that `path:A>` reaches the error below,
# which names the forms, rather than falling through to the generic one.
_PATH = re.compile(r"^path:(?P<source>.*?)>(?P<target>.*)$", re.IGNORECASE)
_CONE = re.compile(r"^cone:(?P<spec>.+?)(?:(?P<arrow>[<>])(?P<hops>\d+))?$", re.IGNORECASE)


@dataclass(frozen=True)
class Answer:
    """A drawable answer.

    :param groups: One per hop, in order, each carrying its colour.
    :param labels: ``(neuron node id, text)`` to draw at that neuron.
    :param title: Short description of what was asked.
    :param stem: Filesystem-safe stem for an output file.
    """

    groups: list[NeuronGroup]
    labels: list[tuple[str, str]]
    title: str
    stem: str

    def __len__(self) -> int:
        return sum(len(g.neuron_ids) for g in self.groups)


def is_answer(query: str) -> bool:
    """Whether *query* is an answer query rather than a plain spec.

    :param query: The text typed or passed.
    :return: ``True`` for a ``path:`` or ``cone:`` form.
    """
    lowered = query.strip().lower()
    return lowered.startswith(("path:", "cone:"))


def parse_answer(query: str) -> tuple[str, dict[str, object]]:
    """Read an answer query into a kind and its arguments.

    :param query: e.g. ``"path:LPLC2>DNp01"`` or ``"cone:DNp01<2"``.
    :return: ``("path", {...})`` or ``("cone", {...})``.
    :raises ValueError: If the form is not one this module knows, naming the
        forms that are.
    """
    text = query.strip()
    match = _PATH.match(text)
    if match:
        source = match.group("source").strip()
        target = match.group("target").strip()
        if not source or not target:
            raise ValueError(f"{query!r} needs a spec on each side of '>'; try {ANSWER_SYNTAX}")
        return "path", {"source": source, "target": target}
    match = _CONE.match(text)
    if match:
        spec = match.group("spec").strip()
        if not spec:
            raise ValueError(f"{query!r} needs a spec after 'cone:'; try {ANSWER_SYNTAX}")
        hops = bounded_int("hops", int(match.group("hops") or 1), 1, MAX_HOP)
        direction = "up" if match.group("arrow") == "<" else "down"
        return "cone", {"spec": spec, "hops": hops, "direction": direction}
    raise ValueError(f"{query!r} is not an answer query; try {ANSWER_SYNTAX}")


def answer_groups(kg: ConnectomeKG, query: str, *, min_syn: int = 1) -> Answer:
    """Resolve an answer query into groups ready to draw.

    :param kg: An open ``ConnectomeKG``.
    :param query: An answer query; see :data:`ANSWER_SYNTAX`.
    :param min_syn: Synapse threshold, for a cone.
    :return: The :class:`Answer`.
    :raises ValueError: If the query does not parse, resolves to nothing, or
        holds more neurons than one scene may draw.
    """
    kind, args = parse_answer(query)
    if kind == "path":
        answer = _path_answer(kg, source=str(args["source"]), target=str(args["target"]))
    else:
        answer = _cone_answer(
            kg,
            spec=str(args["spec"]),
            hops=int(str(args["hops"])),
            direction=str(args["direction"]),
            min_syn=min_syn,
        )
    if not len(answer):
        raise ValueError(f"{query!r} resolves to no neurons")
    if len(answer) > MAX_SCENE_NEURONS:
        raise ValueError(
            f"{len(answer)} neurons in this answer, over the cap of {MAX_SCENE_NEURONS} for "
            "one scene; narrow it with fewer hops or a higher min_syn"
        )
    return answer


def _path_answer(kg: ConnectomeKG, *, source: str, target: str) -> Answer:
    """One group per hop, dark to bright along the route."""
    from connectomekg.scene import NeuronGroup  # noqa: PLC0415 - avoids a cycle

    result = kg.strongest_path(source, target)
    if result is None:
        raise ValueError(f"no path from {source} to {target}")
    n = len(result.hops)
    groups, labels = [], []
    for i, hop in enumerate(result.hops):
        node = kg.store.node(hop.node_id) or {}
        name = str(node.get("name") or hop.node_id)
        groups.append(NeuronGroup(f"hop {i} {name}", [hop.node_id], hop_color(i, n)))
        labels.append((hop.node_id, name if not hop.syn_count else f"{name}  {hop.syn_count} syn"))
    return Answer(groups, labels, f"path {source} to {target}", f"path_{source}_to_{target}")


def _cone_answer(kg: ConnectomeKG, *, spec: str, hops: int, direction: str, min_syn: int) -> Answer:
    """One group per hop, dark at the seed and bright outward."""
    from connectomekg.scene import NeuronGroup  # noqa: PLC0415 - avoids a cycle

    reached = kg.cone(spec, hops=hops, min_syn=min_syn, direction=direction)
    by_hop: dict[int, list[str]] = {}
    for node_id, hop in reached.items():
        by_hop.setdefault(hop, []).append(node_id)
    order = sorted(by_hop)
    groups = [
        NeuronGroup(f"hop {hop}", sorted(by_hop[hop]), hop_color(i, len(order)))
        for i, hop in enumerate(order)
    ]
    arrow = "<" if direction == "up" else ">"
    return Answer(
        groups,
        [],
        f"cone {spec} {direction} {hops}",
        f"cone_{spec}_{direction}_{hops}".replace(arrow, ""),
    )
