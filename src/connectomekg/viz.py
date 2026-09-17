"""2-D renderings of a connectome graph.

Two views of one cell type, as ``connkg viz`` draws them:

* the **network** view: the type with its strongest input and output partner
  types, as an interactive graph (:func:`type_network_html`);
* the **partners** view: the same partners as a diverging bar chart, inputs to
  the left and outputs to the right (:func:`partners_figure`).

The network renderer is ``kg_utils.viz.build_graph_html``, shared with every
other KG module. What lives here is only what is about a connectome: super
class colours, transmitter-sign colours and the fields worth hovering over.

That renderer draws every edge at one width labelled with its relation name.
A connectome edge's meaning is its synapse count and sign, so each drawn edge
is labelled with its count and transmitter ("5,543 ACH") and the theme's
relation colours are built per render to colour those labels by sign. That is configuration of the shared
renderer, not a workaround inside it.

Nothing here is imported at package import time: ``plotly`` and, through
``kg_utils.viz``, ``pyvis`` arrive with the ``viz`` extra, and ``cli/cmd_viz.py``
imports this module inside the command.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Final

import plotly.graph_objects as go
from kg_utils.viz import GraphTheme, KindStyle, TooltipRow, TooltipSpec, build_graph_html

from connectomekg.colors import SIGN_COLOR, SUPER_CLASS_COLOR
from connectomekg.colors import UNKNOWN_COLOR as _UNKNOWN_COLOR
from connectomekg.schema import NT_SIGN

if TYPE_CHECKING:
    from connectomekg.module import ConnectomeKG


def _super_class(node: Mapping[str, Any]) -> str:
    return str((node.get("metadata") or {}).get("super_class") or "")


def _classes_row(node: Mapping[str, Any]) -> str:
    meta = node.get("metadata") or {}
    parts = [meta.get("super_class"), meta.get("class"), meta.get("sub_class")]
    return " / ".join(str(p).replace("_", " ") for p in parts if p)


def _transmitter_row(node: Mapping[str, Any]) -> str:
    meta = node.get("metadata") or {}
    nt = meta.get("nt_type") or ""
    sign = {1: "excitatory", -1: "inhibitory"}.get(meta.get("sign", 0), "sign unknown")
    return f"{nt} ({sign})" if nt else sign


def _size_row(node: Mapping[str, Any]) -> str:
    meta = node.get("metadata") or {}
    n = meta.get("n_neurons")
    return f"{n} neurons ({meta.get('n_left', 0)} L, {meta.get('n_right', 0)} R)" if n else ""


#: What a cell type shows on hover; the docstring is the extractor's summary.
CELL_TYPE_TOOLTIP: Final[TooltipSpec] = TooltipSpec(
    title="name",
    rows=(TooltipRow(_classes_row), TooltipRow(_transmitter_row), TooltipRow(_size_row)),
    body="docstring",
)


def type_network_html(
    kg: ConnectomeKG, cell_type: str, *, limit: int = 15, height: str = "800px"
) -> str:
    """Render a cell type with its strongest partner types as an HTML page.

    The picture holds the type, its ``limit`` strongest output types and its
    ``limit`` strongest input types. Edges between partners are drawn only when
    they are at least as strong as the weakest edge to the centre, so the page
    shows the local circuit without becoming a hairball.

    :param kg: An open ConnectomeKG.
    :param cell_type: Exact cell type name, e.g. ``"LC4"``.
    :param limit: Partner types per direction, 1-500.
    :param height: CSS height of the canvas.
    :return: A self-contained HTML document.
    :raises ValueError: If the type is unknown, or ``limit`` is out of range.
    """
    center = kg.cell_type_node(cell_type)
    downs = kg.type_partners(cell_type, direction="down", limit=limit)
    ups = kg.type_partners(cell_type, direction="up", limit=limit)
    prefix = center["id"].rsplit(":t:", 1)[0]

    ids = {center["id"]} | {f"{prefix}:t:{p['cell_type']}" for p in downs + ups}
    nodes = [n for n in (kg.store.node(i) for i in sorted(ids)) if n is not None]

    ring = [p["syn_count"] for p in downs + ups]
    floor = min(ring) if ring else 1
    edges: list[dict[str, str]] = []
    relation_colors: dict[str, str] = {}
    for e in kg.store.edges_within(ids):
        if e.get("rel") != "TYPE_SYNAPSES_TO":
            continue
        ev = e.get("evidence") or {}
        if isinstance(ev, str):
            ev = json.loads(ev)
        syn = int(ev.get("syn_count", 0))
        touches_center = center["id"] in (e["src"], e["dst"])
        if not touches_center and syn < floor:
            continue
        # The transmitter is in the label so that a label always implies one
        # sign: two edges with equal counts but opposite signs must not share
        # a colour entry.
        nt = str(ev.get("nt_type") or "").upper()
        label = f"{syn:,} {nt or 'syn'}"
        relation_colors[label] = SIGN_COLOR[NT_SIGN.get(nt, 0)]
        edges.append({"src": e["src"], "dst": e["dst"], "rel": label})

    kinds = {
        f"sc:{sc}": KindStyle(color=color, shape="dot", size=18)
        for sc, color in SUPER_CLASS_COLOR.items()
    }
    theme = GraphTheme(
        kinds=kinds,
        fallback=KindStyle(color=_UNKNOWN_COLOR, shape="dot", size=18),
        relations=relation_colors,
        relation_fallback=SIGN_COLOR[0],
        resolve_kind=lambda node: f"sc:{_super_class(node)}",
    )
    return build_graph_html(
        nodes,
        edges,
        theme=theme,
        tooltip=CELL_TYPE_TOOLTIP,
        height=height,
        highlight_ids={center["id"]},
    )


def partners_figure(kg: ConnectomeKG, cell_type: str, *, limit: int = 15) -> go.Figure:
    """Render a cell type's input and output partner types as a diverging bar chart.

    :param kg: An open ConnectomeKG.
    :param cell_type: Exact cell type name, e.g. ``"LC4"``.
    :param limit: Partner types per direction, 1-500.
    :return: A plotly ``Figure``: inputs as negative bars, outputs as positive.
    :raises ValueError: If the type is unknown, or ``limit`` is out of range.
    """
    kg.cell_type_node(cell_type)
    downs = kg.type_partners(cell_type, direction="down", limit=limit)
    ups = kg.type_partners(cell_type, direction="up", limit=limit)

    figure = go.Figure()
    for label, rows, direction in (("inputs", ups, -1), ("outputs", downs, 1)):
        rows = list(reversed(rows))  # strongest at the top
        figure.add_trace(
            go.Bar(
                name=label,
                orientation="h",
                y=[f"{r['cell_type']} ({label[:-1]})" for r in rows],
                x=[direction * r["syn_count"] for r in rows],
                marker={
                    "color": [
                        SIGN_COLOR[NT_SIGN.get(str(r["nt_type"] or "").upper(), 0)] for r in rows
                    ]
                },
                customdata=[[r["syn_count"], r["n_pairs"], r["nt_type"] or "?"] for r in rows],
                hovertemplate="%{y}<br>%{customdata[0]:,} synapses, "
                "%{customdata[1]:,} neuron pairs, %{customdata[2]}<extra></extra>",
            )
        )
    n_rows = len(downs) + len(ups)
    figure.update_layout(
        title=f"{cell_type}: strongest partner types (inputs left, outputs right)",
        barmode="overlay",
        xaxis={"title": "synapses", "zeroline": True, "zerolinecolor": "#33383D"},
        yaxis={"automargin": True},
        height=max(420, 26 * n_rows + 140),
        showlegend=False,
        plot_bgcolor="white",
    )
    return figure


__all__ = [
    "CELL_TYPE_TOOLTIP",
    "SIGN_COLOR",
    "SUPER_CLASS_COLOR",
    "partners_figure",
    "type_network_html",
]
