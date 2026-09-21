"""connectomekg/circuits.py

Named circuits: curated sets of cell types that are worth drawing together,
reachable as the spec form ``circuit:<name>``.

A circuit is not a graph object. It is an editorial shortcut: the central
complex's head-direction system is five cell types that nobody remembers as
five names, and typing them out is the only thing standing between a user and
a scene worth looking at. ``circuit:compass`` expands to their union
wherever a spec is accepted, so ``connkg quilt``, ``viz3d``, ``path``,
``cone``, ``influence`` and ``link`` all take it without knowing it exists.

The union is deliberately flat. The circuit view colors by the cell type each
neuron carries (see :func:`connectomekg.scene.build_brain_scene`), not by the
spec that resolved it, so ``circuit:compass`` still draws five colors and a
member spec that is itself a ``label:`` pattern still draws one per type it
matches.

Every member spec here resolves on FAFB v783, and every circuit fits in one
scene under :data:`connectomekg.validation.MAX_SCENE_NEURONS`; the counts in
each summary were measured on a built v783 graph.

Author: Eric G. Suchanek, PhD
License: Elastic 2.0
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

__all__ = [
    "CIRCUITS",
    "CIRCUIT_PREFIX",
    "Circuit",
    "circuit_name",
    "circuit_specs",
    "is_circuit",
]

#: What marks a spec as a named circuit rather than a cell type.
CIRCUIT_PREFIX = "circuit:"


@dataclass(frozen=True)
class Circuit:
    """One named circuit.

    :param specs: Member specs, each in a form :meth:`ConnectomeKG.neurons_of`
        accepts. Order is the order they are listed in, which is the order a
        reader should meet them, not a drawing order -- the scene groups by
        cell type regardless.
    :param summary: One line, shown by ``connkg circuits`` and in the viewer.
    """

    specs: tuple[str, ...]
    summary: str


#: The circuits, by name. Names are lowercase and hyphenated, matched
#: case-insensitively with ``_`` treated as ``-`` (see :func:`circuit_name`),
#: so ``circuit:Optic_Flow`` finds ``optic-flow``.
CIRCUITS: Final[dict[str, Circuit]] = {
    "compass": Circuit(
        ("EPG", "Delta7", "PEG", "PEN_a/PEN1", "PEN_b/PEN2"),
        "the central complex's head-direction system: 151 neurons wiring the "
        "ellipsoid body to the protocerebral bridge",
    ),
    "optic-flow": Circuit(
        ("HSN", "HSE", "HSS", "VS1", "VS2", "VS3", "VS4", "VS5", "VS6", "VS7", "VS8", "DNp15"),
        "lobula plate tangential cells, horizontal and vertical, and the "
        "descending neuron they steer gaze through",
    ),
    "mushroom-body": Circuit(
        ("label:^MBON",),
        "the mushroom body's output neurons, the readout of learning and "
        "memory, one color per compartment's type",
    ),
    "clock": Circuit(
        ("label:clock|circadian|LNv|LNd",),
        "the circadian pacemaker network, sparse and bilateral",
    ),
}


def circuit_name(spec: str) -> str:
    """The circuit name a ``circuit:`` spec asks for, normalized.

    :param spec: A spec starting with :data:`CIRCUIT_PREFIX`.
    :return: The name, lowercased with ``_`` folded to ``-``.
    """
    return spec[len(CIRCUIT_PREFIX) :].strip().lower().replace("_", "-")


def is_circuit(spec: str) -> bool:
    """Whether *spec* asks for a named circuit.

    Prefix only: whether the name is one that exists is a separate question,
    so that an unknown name can be reported by name rather than falling
    through and resolving to nothing.

    :param spec: Any spec.
    :return: True if it starts with :data:`CIRCUIT_PREFIX`, case-insensitively.
    """
    return spec[: len(CIRCUIT_PREFIX)].lower() == CIRCUIT_PREFIX


def circuit_specs(spec: str) -> tuple[str, ...]:
    """The member specs of a ``circuit:`` spec.

    :param spec: A spec starting with :data:`CIRCUIT_PREFIX`.
    :return: The member specs, in listed order.
    :raises ValueError: If the name is empty or unknown, naming what there is.
    """
    name = circuit_name(spec)
    if not name:
        raise ValueError(f"circuit: spec needs a name, one of: {', '.join(CIRCUITS)}")
    circuit = CIRCUITS.get(name)
    if circuit is None:
        raise ValueError(f"unknown circuit {name!r}; try one of: {', '.join(CIRCUITS)}")
    return circuit.specs
