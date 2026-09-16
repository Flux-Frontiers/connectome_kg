"""Compose the docstrings that get embedded, from structured fields only.

Nothing here is authored prose. Every sentence is a rendering of table
columns, so a docstring is exactly as trustworthy as the annotation behind it.
"""

from __future__ import annotations

from typing import Any

from connectomekg.neuropils import neuropil_full_name

_NT_WORD = {
    "ACH": "cholinergic",
    "GABA": "GABAergic",
    "GLUT": "glutamatergic",
    "DA": "dopaminergic",
    "SER": "serotonergic",
    "OCT": "octopaminergic",
}
_SIDE_WORD = {"L": "left", "R": "right", "M": "midline", "C": "central"}


def nt_word(nt: str) -> str:
    """Adjective for a transmitter code, or ``"transmitter unknown"``."""
    return _NT_WORD.get((nt or "").upper(), "transmitter unknown")


def _clean(v: Any) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s.lower() in ("nan", "none") else s


def neuron_docstring(
    row: dict[str, Any],
    *,
    n_in: int,
    n_out: int,
    top_neuropils: list[str],
    labels: list[str],
) -> str:
    """One neuron, described from its annotations.

    :param row: A row of the neurons table as a dict.
    :param n_in: Input synapse count.
    :param n_out: Output synapse count.
    :param top_neuropils: Neuropils holding most of its synapses.
    :param labels: Community labels on this neuron.
    :return: Docstring text.
    """
    ct = _clean(row.get("cell_type")) or "untyped"
    side = _SIDE_WORD.get(_clean(row.get("side")).upper()[:1], _clean(row.get("side")))
    sc = _clean(row.get("super_class")).replace("_", " ")
    cls = _clean(row.get("class")).replace("_", " ")
    parts = [f"{side} {ct}".strip()]
    if sc:
        parts.append(f"{sc} neuron" + (f", class {cls}" if cls and cls != sc else ""))
    nt = _clean(row.get("nt_type"))
    score = row.get("nt_score")
    if nt:
        conf = f" ({float(score):.2f})" if score is not None and str(score) != "nan" else ""
        parts.append(nt_word(nt) + conf)
    hl = _clean(row.get("hemilineage"))
    if hl:
        parts.append(f"hemilineage {hl}")
    parts.append(f"{n_in} input and {n_out} output synapses")
    if top_neuropils:
        parts.append("mainly in " + ", ".join(neuropil_full_name(x) for x in top_neuropils))
    text = "; ".join(parts) + "."
    if labels:
        text += " Labels: " + "; ".join(labels[:6]) + "."
    return text


def cell_type_docstring(
    name: str,
    *,
    n_left: int,
    n_right: int,
    super_class: str,
    cls: str,
    nt: str,
    hemilineage: str,
    top_out: list[tuple[str, int]],
    top_in: list[tuple[str, int]],
    neuropils: list[str],
    labels: list[str],
) -> str:
    """A cell type, described from its members.

    :param name: Type name.
    :param n_left: Members on the left.
    :param n_right: Members on the right.
    :param super_class: Majority super class.
    :param cls: Majority class.
    :param nt: Majority transmitter code.
    :param hemilineage: Majority hemilineage.
    :param top_out: Strongest downstream types as (type, synapses).
    :param top_in: Strongest upstream types as (type, synapses).
    :param neuropils: Neuropils it innervates most.
    :param labels: Distinct community labels over its members.
    :return: Docstring text.
    """
    n = n_left + n_right
    parts = [f"Cell type {name}: {n} neurons ({n_left} left, {n_right} right)"]
    if super_class:
        parts.append(super_class.replace("_", " ") + (f", class {cls}" if cls else ""))
    if nt:
        parts.append(nt_word(nt))
    if hemilineage:
        parts.append(f"hemilineage {hemilineage}")
    if neuropils:
        parts.append("innervates " + ", ".join(neuropil_full_name(x) for x in neuropils))
    text = "; ".join(parts) + "."
    if top_out:
        text += " Outputs to " + ", ".join(f"{t} ({s})" for t, s in top_out) + "."
    if top_in:
        text += " Inputs from " + ", ".join(f"{t} ({s})" for t, s in top_in) + "."
    if labels:
        text += " Labels: " + "; ".join(labels[:8]) + "."
    return text


def neuropil_docstring(abbrev: str, *, n_neurons: int, n_synapses: int) -> str:
    """A neuropil, described by name and size."""
    return (
        f"Neuropil {abbrev}, {neuropil_full_name(abbrev)}: {n_neurons} neurons with synapses "
        f"here, {n_synapses} synapses."
    )
