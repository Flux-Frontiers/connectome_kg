"""connectomekg/scene.py

Builds the real-geometry 3-D views of a connectome: view A, every neuron's
marked point as a dim context cloud, and view B, the skeletons of a query's
neurons drawn at full brightness inside it, and view C, neuropils linked by
the signal flow their neurons carry between them. Both views can also draw
the neuropil surface meshes ``connkg meshes`` caches
(:mod:`connectomekg.neuropil_meshes`). Unlike the fleet's other viz3d
consumers (``gutenberg_kg``, ``pycode_kg``, ``genealogy_kg``), this graph
already has space -- every neuron carries real ``x``/``y``/``z`` coordinates
and the download holds a traced skeleton for most of them -- so there is no
tree to grow here, no ``kg_utils.viz3d.organic`` call anywhere in this file.
What is reused from that engine is just the camera rule (``frame_tree``, in
``cli/cmd_viz3d.py``) and ``seed_from_key`` for a stable per-type colour.

Split the way ``pycode_kg.scene3d`` and ``genealogy_kg.scene`` split their own
layout from composition, so most of this is testable without PyVista:

* :class:`WorldFrame`, :func:`world_frame`, :func:`context_points`,
  :func:`circuit_neurons`, :func:`neuropil_flow` and :func:`flow_arc` are pure
  NumPy plus SQL -- no PyVista import.
* :func:`build_brain_scene` composes those into a caller-supplied
  ``pv.Plotter``. This half needs the ``viz3d`` extra.

Colours come from :mod:`connectomekg.colors`, never from :mod:`connectomekg.viz`
-- ``viz.py`` imports ``plotly`` at module scope, and this module must stay
importable with only the ``viz3d`` extra installed, no ``viz``. The same
reason ``genealogy_kg`` keeps its palette in ``theme.py`` rather than
``viz.py``.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

import numpy as np
from kg_utils.store import GraphStore
from kg_utils.viz3d import seed_from_key

from connectomekg.colors import REGION_COLOR, SIGN_COLOR, SUPER_CLASS_COLOR, UNKNOWN_COLOR
from connectomekg.neuropil_meshes import Mesh, load_neuropil_meshes, neuropil_mesh_path
from connectomekg.neuropils import neuropil_region
from connectomekg.skeleton_cache import (
    cache_info,
    effective_step,
    load_cached_skeletons,
    skeleton_cache_path,
)
from connectomekg.skeletons import Skeleton, load_skeletons, segments, soma
from connectomekg.validation import (
    MAX_FLOW_PAIRS,
    MAX_SCENE_NEURONS,
    MAX_SKELETON_STEP,
    bounded_int,
    require_choice,
)

if TYPE_CHECKING:
    import pyvista as pv
    from quiltwright import QuiltSpec

    from connectomekg.module import ConnectomeKG

#: World units per nanometre's worth of scale: 1 world unit per 100,000 nm,
#: so the brain (about 0.81 x 0.39 x 0.28 mm) is roughly 8 x 4 x 3 units --
#: inside the depth budget ``quiltwright.depth_report`` checks. See
#: docs/rendering.md, "World coordinates".
NM_PER_WORLD_UNIT: Final = 100_000.0

_SQL_NEURON_XYZ = (
    "kind='neuron' AND json_extract(metadata,'$.x') IS NOT NULL "
    "AND json_extract(metadata,'$.y') IS NOT NULL "
    "AND json_extract(metadata,'$.z') IS NOT NULL"
)

#: The context cloud is one low-poly sphere glyph per neuron, sized in world
#: units rather than screen pixels: a pixel-sized point vanishes on a HiDPI
#: display and in a quilt tile, while a world-sized glyph scales with the view.
#: Its colours are blended part of the way toward the background, which keeps
#: their hue but mutes them, so the subject drawn at full saturation stands
#: out even where it shares a hue with the cloud around it. Toward the grey
#: background, not toward white: lightened colours turn pastel, which
#: colour-blind readers cannot tell apart. Opaque, since alpha ghosts in
#: light-field renders.
_CONTEXT_RADIUS: Final = 0.005
_CONTEXT_MUTE: Final = 0.45
#: Darkening for idle neuropil spheres in the flow view.
_CONTEXT_DIM: Final = 0.85
#: Scene background: a muted mid grey. On PyVista's default white the dimmed
#: context cloud all but disappears; on this grey it reads as the brain's
#: outline without competing with the subject.
BACKGROUND: Final = "#5A5D62"
#: The flow view thins the context cloud to every Nth neuron, drawn with
#: larger glyphs: at full density it hides the neuropil spheres and arcs.
_FLOW_CONTEXT_STRIDE: Final = 10
_FLOW_CONTEXT_RADIUS: Final = 0.014
#: The flow view draws its context cloud in one neutral grey, so that colour
#: in that view means only a neuropil's brain region: super-class colours on
#: the dots would reuse the same hues for something else.
_FLOW_CONTEXT_COLOR: Final = "#8A8F96"
#: Sphere radii, world units. A fallback sphere (no skeleton) is drawn larger
#: than a real soma so it reads as a stand-in, not a measurement.
_SOMA_RADIUS: Final = 0.05
_FALLBACK_RADIUS: Final = 0.09
_TUBE_RADIUS: Final = 0.01
#: View C sizes, world units. A neuropil sphere's radius scales with the cube
#: root of its synapse count, an arc's tube radius with the square root of its
#: flow, each relative to the largest; idle neuropils (no drawn arc) are drawn
#: at half size and dimmed.
_NEUROPIL_MAX_RADIUS: Final = 0.22
_FLOW_MAX_RADIUS: Final = 0.08
_FLOW_MIN_RADIUS: Final = 0.004
_FLOW_BOW: Final = 0.15
_FLOW_ARC_POINTS: Final = 17
#: Ambient share of the lighting on neuropil spheres and flow tubes. Shading
#: darkens a colour toward its neighbours (a shaded yellow reads as orange),
#: and region colours must stay recognisable, so these surfaces are lit more
#: evenly than the default.
_FLOW_AMBIENT: Final = 0.45
#: Neuropil surface meshes. The circuit view draws them as pale neutral
#: shells so the circuit's own colours stay the only colour in the scene; the
#: flow view tints each by its brain region, the colour its sphere already
#: carries. Faint in both, so what sits inside shows through.
_NEUROPIL_SHELL_COLOR: Final = "#C8CCD2"
_NEUROPIL_SHELL_OPACITY: Final = 0.10
_NEUROPIL_TINT_OPACITY: Final = 0.15

#: Floor and shadow rig for :func:`add_floor`, world units. The floor sits a
#: little below the subject and is far larger than any frame, so it fills the
#: view behind the brain. The key light is a wide spotlight high above: a
#: narrow cone shows its circular edge on the floor, and a wide one spreads
#: the shadow map thin, hence the large map. VTK's default 1024 px map draws
#: visibly blocky shadows at 4K.
FLOOR_ELEVATION: Final = 25.0
_FLOOR_DROP: Final = 0.15
_FLOOR_SIZE: Final = 120.0
_KEY_LIGHT_HEIGHT: Final = 20.0
_KEY_LIGHT_OFFSET: Final = (-4.0, -6.0)
_KEY_LIGHT_CONE: Final = 75.0
_KEY_LIGHT_INTENSITY: Final = 0.9
_FILL_LIGHT_INTENSITY: Final = 0.35
_SHADOW_MAP_RESOLUTION: Final = 8192

#: The views :func:`build_brain_scene` composes.
VIEWS: Final = ("circuit", "flow")

#: Qualitative palette a cell type's colour is deterministically drawn from,
#: via :func:`type_color`: the seven saturated Okabe-Ito colours other than
#: black, which stay distinguishable under the common forms of colour
#: blindness. A circuit rarely draws more than a few cell types at once.
_TYPE_PALETTE: Final[tuple[str, ...]] = (
    "#E69F00",
    "#56B4E9",
    "#009E73",
    "#F0E442",
    "#0072B2",
    "#D55E00",
    "#CC79A7",
)


def region_color(neuropil: str) -> str:
    """The colour for a neuropil: its brain region's colour.

    :param neuropil: FlyWire abbreviation, with or without side suffix.
    :return: A ``#RRGGBB`` colour from :data:`connectomekg.colors.REGION_COLOR`,
        or the unknown grey for a neuropil with no region.
    """
    return REGION_COLOR.get(neuropil_region(neuropil) or "", UNKNOWN_COLOR)


def type_color(name: str) -> str:
    """A deterministic colour for a cell type name.

    Indexes a fixed qualitative palette via ``seed_from_key``, so the same
    type name always draws the same colour -- across renders, sessions and a
    printed figure.

    :param name: Cell type name, e.g. ``"LC4"``.
    :return: A ``#RRGGBB`` colour.
    """
    return _TYPE_PALETTE[seed_from_key(name) % len(_TYPE_PALETTE)]


@dataclass(frozen=True)
class WorldFrame:
    """The nm-to-world-units mapping a scene is framed in.

    :param center: ``(3,)`` nm; the point that maps to the world origin.
    :param scale: Nanometres per world unit.
    """

    center: np.ndarray
    scale: float = NM_PER_WORLD_UNIT

    def to_world(self, points_nm: np.ndarray) -> np.ndarray:
        """Map nm points to world units, dorsal up, section axis away from camera.

        ``(x, y, z)`` nm becomes world
        ``((x - cx) / S, (z - cz) / S, -(y - cy) / S)`` -- FAFB's ``y`` grows
        ventrally, so negating it after centring puts dorsal at larger world
        ``z``.

        :param points_nm: ``(n, 3)`` or ``(3,)`` nm coordinates.
        :return: ``(n, 3)`` world coordinates.
        """
        pts = np.atleast_2d(np.asarray(points_nm, dtype=np.float64))
        cx, cy, cz = self.center
        x = (pts[:, 0] - cx) / self.scale
        y = (pts[:, 2] - cz) / self.scale
        z = -(pts[:, 1] - cy) / self.scale
        return np.stack([x, y, z], axis=1)


def world_frame(store: GraphStore) -> WorldFrame:
    """The scene's :class:`WorldFrame`, centred on the median neuron position.

    :param store: The graph store.
    :return: A frame centred on the median of every neuron's marked point
        (skipping neurons with no coordinates), at :data:`NM_PER_WORLD_UNIT`.
    :raises ValueError: If no neuron in the store has coordinates.
    """
    rows = store.con.execute(
        f"SELECT json_extract(metadata,'$.x'), json_extract(metadata,'$.y'), "
        f"json_extract(metadata,'$.z') FROM nodes WHERE {_SQL_NEURON_XYZ}"
    ).fetchall()
    if not rows:
        raise ValueError("no neuron in this graph has x/y/z coordinates")
    center = np.median(np.asarray(rows, dtype=np.float64), axis=0)
    return WorldFrame(center=center)


def context_points(
    store: GraphStore, *, color_by: str = "super_class"
) -> tuple[list[str], np.ndarray, list[str], int]:
    """Every neuron's soma, or its marked point, for the whole-brain context cloud (view A).

    A neuron carries FlyWire's marked point as ``x``/``y``/``z`` always, and
    its real soma as ``soma_x``/``soma_y``/``soma_z`` once ``connkg skeletons``
    has back-filled one (:func:`connectomekg.skeleton_cache.write_somas`). The
    soma wins where there is one, so a graph with the back-fill draws a soma
    cloud and one without still draws the marked-point cloud it always did.

    :param store: The graph store.
    :param color_by: ``"super_class"`` or ``"sign"``.
    :return: ``(neuron_ids, points_nm, colors, n_somas)`` -- ``points_nm`` is
        ``(n, 3)``, ``colors`` is one ``#RRGGBB`` string per neuron, same
        order as ``neuron_ids``, and ``n_somas`` counts how many of those
        points are a real soma rather than a marked point. Neurons with no
        coordinates at all are omitted.
    :raises ValueError: If ``color_by`` is not one of the two choices.
    """
    color_by = require_choice("color_by", color_by, ("super_class", "sign"))
    rows = store.con.execute(
        f"SELECT id, "
        f"COALESCE(json_extract(metadata,'$.soma_x'), json_extract(metadata,'$.x')), "
        f"COALESCE(json_extract(metadata,'$.soma_y'), json_extract(metadata,'$.y')), "
        f"COALESCE(json_extract(metadata,'$.soma_z'), json_extract(metadata,'$.z')), "
        f"json_extract(metadata,'$.super_class'), json_extract(metadata,'$.sign'), "
        f"json_extract(metadata,'$.has_soma') FROM nodes WHERE {_SQL_NEURON_XYZ}"
    ).fetchall()
    ids = [r[0] for r in rows]
    points = (
        np.asarray([(r[1], r[2], r[3]) for r in rows], dtype=np.float64)
        if rows
        else np.empty((0, 3), dtype=np.float64)
    )
    if color_by == "super_class":
        colors = [SUPER_CLASS_COLOR.get(r[4] or "", UNKNOWN_COLOR) for r in rows]
    else:
        colors = [SIGN_COLOR.get(int(r[5]) if r[5] is not None else 0, SIGN_COLOR[0]) for r in rows]
    return ids, points, colors, sum(1 for r in rows if r[6])


def circuit_neurons(kg: ConnectomeKG, specs: Sequence[str]) -> list[str]:
    """The union of every spec's neurons, for the circuit view (view B).

    :param kg: An open ``ConnectomeKG``.
    :param specs: Specs, as accepted by :meth:`ConnectomeKG.neurons_of`.
    :return: Sorted, deduplicated neuron node ids.
    :raises ValueError: If the union exceeds :data:`connectomekg.validation.MAX_SCENE_NEURONS`,
        naming the count and the cap.
    """
    ids: set[str] = set()
    for spec in specs:
        ids.update(kg.neurons_of(spec))
    if len(ids) > MAX_SCENE_NEURONS:
        raise ValueError(
            f"{len(ids)} neurons resolved, over the cap of {MAX_SCENE_NEURONS} for one "
            "scene; narrow the spec(s)"
        )
    return sorted(ids)


@dataclass(frozen=True)
class NeuropilFlow:
    """Neuropil positions and the signal flow between them (view C).

    Flow from neuropil A to B is carried by neurons: each neuron's output
    synapses in B, apportioned by the share of its input synapses that lie in
    A, summed over neurons, with A = B excluded. See docs/rendering.md,
    "What flow measures".

    :param names: Neuropil abbreviations, e.g. ``"ME_R"``, sorted.
    :param bases: Each neuropil's side-free base, e.g. ``"ME"``, same order.
    :param centroids_nm: ``(n, 3)`` synapse-weighted centroid of the marked
        points of every neuron in each neuropil; a row is NaN when no neuron
        in it has coordinates.
    :param n_synapses: ``(n,)`` each neuropil's synapse count.
    :param pairs: ``(source, target, flow)`` for every directed pair with
        nonzero flow, strongest first, ties broken by name.
    """

    names: list[str]
    bases: list[str]
    centroids_nm: np.ndarray
    n_synapses: np.ndarray
    pairs: list[tuple[str, str, float]]


def neuropil_flow(store: GraphStore, neuron_ids: Iterable[str] | None = None) -> NeuropilFlow:
    """Aggregate ``IN_NEUROPIL`` evidence into neuropil centroids and flow.

    Centroids always use every neuron, so neuropils sit in the same place in
    every flow render; only the flow sum is restricted by *neuron_ids*.

    :param store: The graph store.
    :param neuron_ids: Neuron node ids whose flow is summed; ``None`` sums
        every neuron.
    :return: The :class:`NeuropilFlow`.
    """
    con = store.con
    np_rows = con.execute(
        "SELECT id, name, json_extract(metadata,'$.base'), json_extract(metadata,'$.n_synapses') "
        "FROM nodes WHERE kind='neuropil' ORDER BY name"
    ).fetchall()
    names = [r[1] for r in np_rows]
    name_of = {r[0]: r[1] for r in np_rows}
    index = {name: i for i, name in enumerate(names)}

    positions = {
        r[0]: (r[1], r[2], r[3])
        for r in con.execute(
            f"SELECT id, json_extract(metadata,'$.x'), json_extract(metadata,'$.y'), "
            f"json_extract(metadata,'$.z') FROM nodes WHERE {_SQL_NEURON_XYZ}"
        )
    }
    by_neuron: dict[str, list[tuple[str, int, int]]] = defaultdict(list)
    for nid, np_id, pre, post in con.execute(
        "SELECT src, dst, json_extract(evidence,'$.pre'), json_extract(evidence,'$.post') "
        "FROM edges WHERE rel='IN_NEUROPIL'"
    ):
        if np_id in name_of:
            by_neuron[nid].append((name_of[np_id], int(pre or 0), int(post or 0)))

    weighted = np.zeros((len(names), 3), dtype=np.float64)
    weights = np.zeros(len(names), dtype=np.float64)
    for nid, rows in by_neuron.items():
        pos = positions.get(nid)
        if pos is None:
            continue
        for name, pre, post in rows:
            i = index[name]
            weighted[i] += (pre + post) * np.asarray(pos, dtype=np.float64)
            weights[i] += pre + post
    with np.errstate(invalid="ignore", divide="ignore"):
        centroids = weighted / weights[:, None]
    centroids[weights == 0] = np.nan

    selected = (
        by_neuron if neuron_ids is None else {n: by_neuron[n] for n in neuron_ids if n in by_neuron}
    )
    flow: dict[tuple[str, str], float] = defaultdict(float)
    for rows in selected.values():
        total_post = sum(post for _, _, post in rows)
        if total_post == 0:
            continue
        for source, _, post in rows:
            if post == 0:
                continue
            share = post / total_post
            for target, pre, _ in rows:
                if pre and target != source:
                    flow[(source, target)] += pre * share

    pairs = sorted(((a, b, w) for (a, b), w in flow.items()), key=lambda p: (-p[2], p[0], p[1]))
    return NeuropilFlow(
        names=names,
        bases=[r[2] or r[1] for r in np_rows],
        centroids_nm=centroids,
        n_synapses=np.asarray([r[3] or 0 for r in np_rows], dtype=np.float64),
        pairs=pairs,
    )


def flow_arc(
    start: np.ndarray,
    end: np.ndarray,
    *,
    bow: float = _FLOW_BOW,
    n_points: int = _FLOW_ARC_POINTS,
) -> np.ndarray:
    """A quadratic arc from *start* to *end*, bowed to one side of its direction.

    The bow points along ``direction x world-up`` (world ``+x`` when the
    direction is vertical), so the arc for A -> B and the arc for B -> A bow to
    opposite sides instead of overdrawing.

    :param start: ``(3,)`` world start point.
    :param end: ``(3,)`` world end point.
    :param bow: Control point offset as a fraction of the chord length.
    :param n_points: Points along the arc, including both ends.
    :return: ``(n_points, 3)`` world points.
    """
    start = np.asarray(start, dtype=np.float64)
    end = np.asarray(end, dtype=np.float64)
    chord = end - start
    length = float(np.linalg.norm(chord))
    side = np.cross(chord, (0.0, 0.0, 1.0))
    if np.linalg.norm(side) < 1e-9 * max(length, 1.0):
        side = np.array([1.0, 0.0, 0.0])
    side = side / np.linalg.norm(side)
    control = (start + end) / 2 + side * bow * length
    t = np.linspace(0.0, 1.0, n_points)[:, None]
    return (1 - t) ** 2 * start + 2 * (1 - t) * t * control + t**2 * end


@dataclass
class SceneInfo:
    """What a composed brain scene contains.

    :param title: Human-readable summary for a window title or CLI echo.
    :param points: Every drawn point, world units, for camera framing via
        ``kg_utils.viz3d.frame_tree``.
    :param n_context: Neurons drawn in the context cloud.
    :param n_circuit: Neurons resolved for the circuit view.
    :param n_skeletons: Circuit neurons drawn from a loaded skeleton file.
    :param missing_skeletons: Circuit neurons' root ids with no skeleton file
        loaded (no ``data_dir``, or the file was absent) -- drawn as a larger
        fallback sphere at the marked point instead.
    :param soma_fallbacks: Circuit neurons whose skeleton had no ``Label 1``
        row, so the soma sphere sits at the root point instead.
    :param view: The view composed, one of :data:`VIEWS`.
    :param n_flow_pairs: Flow arcs drawn (view C).
    :param n_flow_total: Directed neuropil pairs with nonzero flow (view C).
    :param n_neuropil_meshes: Neuropil surface meshes drawn; 0 when none are cached.
    :param n_context_somas: Context-cloud neurons drawn at a real soma rather
        than at FlyWire's marked point; 0 until ``connkg skeletons`` has
        back-filled somas.
    """

    title: str
    points: np.ndarray
    n_context: int
    n_circuit: int
    n_skeletons: int
    missing_skeletons: list[int]
    soma_fallbacks: int
    view: str = "circuit"
    n_flow_pairs: int = 0
    n_flow_total: int = 0
    n_neuropil_meshes: int = 0
    n_context_somas: int = 0


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return (int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16))


def _segments_to_polydata(segs: np.ndarray) -> pv.PolyData:
    """One flat-numpy line mesh from ``(m, 2, 3)`` segment pairs.

    One draw call regardless of segment count, the same technique
    ``genealogy_kg.scene._line_mesh`` uses.

    :param segs: ``(m, 2, 3)`` ``(start, end)`` point pairs.
    :return: A ``pv.PolyData`` with a ``lines`` cell array; empty if *segs* is empty.
    """
    import pyvista as pv  # noqa: PLC0415 - the viz3d-render-only import boundary

    m = len(segs)
    if m == 0:
        return pv.PolyData()
    points = np.empty((m * 2, 3), dtype=np.float64)
    points[0::2] = segs[:, 0]
    points[1::2] = segs[:, 1]
    cells = np.empty(m * 3, dtype=np.intp)
    cells[0::3] = 2
    cells[1::3] = np.arange(0, m * 2, 2)
    cells[2::3] = np.arange(1, m * 2 + 1, 2)
    mesh = pv.PolyData()
    mesh.points = points
    mesh.lines = cells
    return mesh


def _context_for_view(
    view: str, ids: list[str], points_nm: np.ndarray, colors: list[str]
) -> tuple[list[str], np.ndarray, list[str], float]:
    """The context cloud a view draws: which neurons, their colours, glyph radius.

    The circuit view draws every neuron in its super-class or sign colour.
    The flow view thins the cloud to every :data:`_FLOW_CONTEXT_STRIDE`-th
    neuron, draws larger glyphs, and colours every glyph neutral grey so that
    colour in that view means only a neuropil's region.

    :return: ``(ids, points_nm, colors, radius)``.
    """
    if view != "flow":
        return ids, points_nm, colors, _CONTEXT_RADIUS
    ids = ids[::_FLOW_CONTEXT_STRIDE]
    return (
        ids,
        points_nm[::_FLOW_CONTEXT_STRIDE],
        [_FLOW_CONTEXT_COLOR] * len(ids),
        _FLOW_CONTEXT_RADIUS,
    )


def _draw_neuropil_meshes(
    plotter: pv.Plotter, meshes: dict[str, Mesh], frame: WorldFrame, view: str
) -> None:
    """Draw neuropil surfaces: neutral shells (circuit view) or region-tinted (flow view).

    One actor per colour, ``neuropils`` in the circuit view and
    ``neuropils:<region colour>`` in the flow view, so the brain costs a
    handful of draw calls rather than one per neuropil.
    """
    import pyvista as pv  # noqa: PLC0415 - the viz3d-render-only import boundary

    by_color: dict[str, list[pv.PolyData]] = defaultdict(list)
    for name, (vertices, faces) in meshes.items():
        cells = np.hstack([np.full((len(faces), 1), 3), faces]).astype(np.int64).ravel()
        mesh = pv.PolyData(frame.to_world(vertices.astype(np.float64)), cells)
        color = region_color(name) if view == "flow" else _NEUROPIL_SHELL_COLOR
        by_color[color].append(mesh)
    opacity = _NEUROPIL_TINT_OPACITY if view == "flow" else _NEUROPIL_SHELL_OPACITY
    for color, parts in by_color.items():
        plotter.add_mesh(
            parts[0] if len(parts) == 1 else pv.merge(parts),
            color=color,
            opacity=opacity,
            name="neuropils" if view != "flow" else f"neuropils:{color}",
        )
    # Translucent surfaces composite in the right order only with depth peeling.
    plotter.enable_depth_peeling()  # ty: ignore[missing-argument]


def _draw_flow(
    plotter: pv.Plotter,
    kg: ConnectomeKG,
    specs: Sequence[str],
    frame: WorldFrame,
    top: int,
    world_points: list[np.ndarray],
    say: Callable[[str], None],
) -> tuple[int, int]:
    """Draw neuropil spheres and the *top* flow arcs (view C) into *plotter*.

    One sphere actor per neuropil (``neuropil:<name>``) and one tube actor per
    source neuropil (``flow:<name>``), coloured by the neuropil's brain region
    (:func:`region_color`).

    :return: ``(arcs drawn, directed pairs with nonzero flow)``.
    """
    import pyvista as pv  # noqa: PLC0415 - the viz3d-render-only import boundary

    neuron_ids: set[str] | None = None
    if specs:
        neuron_ids = set()
        for spec in specs:
            neuron_ids.update(kg.neurons_of(spec))
    say(f"neuropil flow over {'all' if neuron_ids is None else len(neuron_ids)} neurons")
    flow = neuropil_flow(kg.store, neuron_ids)

    index = {name: i for i, name in enumerate(flow.names)}
    placed = ~np.isnan(flow.centroids_nm).any(axis=1)
    centers = np.full_like(flow.centroids_nm, np.nan)
    if placed.any():
        centers[placed] = frame.to_world(flow.centroids_nm[placed])

    drawn = [(a, b, w) for a, b, w in flow.pairs if placed[index[a]] and placed[index[b]]][:top]
    active = {name for a, b, _ in drawn for name in (a, b)}

    max_syn = float(flow.n_synapses.max()) if len(flow.n_synapses) else 0.0
    for i, name in enumerate(flow.names):
        if not placed[i]:
            continue
        rel = np.cbrt(flow.n_synapses[i] / max_syn) if max_syn > 0 else 1.0
        radius = max(_NEUROPIL_MAX_RADIUS * float(rel), _FLOW_MIN_RADIUS)
        color = region_color(name)
        if name not in active:
            radius *= 0.5
            rgb = np.clip(np.asarray(_hex_to_rgb(color)) * _CONTEXT_DIM, 0, 255)
            color = "#{:02X}{:02X}{:02X}".format(*(int(c) for c in rgb))
        plotter.add_mesh(
            pv.Sphere(radius=radius, center=centers[i]),
            color=color,
            ambient=_FLOW_AMBIENT,
            diffuse=1.0 - _FLOW_AMBIENT,
            name=f"neuropil:{name}",
        )
    world_points.append(centers[placed])

    say(f"drawing {len(drawn)} flow arcs")
    max_flow = drawn[0][2] if drawn else 0.0
    tubes_by_source: dict[str, list[pv.PolyData]] = defaultdict(list)
    for source, target, weight in drawn:
        arc = flow_arc(centers[index[source]], centers[index[target]])
        radius = max(_FLOW_MAX_RADIUS * float(np.sqrt(weight / max_flow)), _FLOW_MIN_RADIUS)
        tubes_by_source[source].append(pv.lines_from_points(arc).tube(radius=radius, n_sides=8))
        world_points.append(arc)
    for source, meshes in tubes_by_source.items():
        mesh = meshes[0] if len(meshes) == 1 else pv.merge(meshes)
        plotter.add_mesh(
            mesh,
            color=region_color(source),
            ambient=_FLOW_AMBIENT,
            diffuse=1.0 - _FLOW_AMBIENT,
            name=f"flow:{source}",
        )
    return len(drawn), len(flow.pairs)


def aim_camera(
    plotter: pv.Plotter,
    points: np.ndarray,
    *,
    fov: float = 14.0,
    elevation: float = 0.0,
    spec: QuiltSpec | None = None,
) -> tuple[float, float, float]:
    """Point the camera at a composed scene and frame it tightly at that view.

    ``kg_utils.viz3d.frame_tree`` sets the view direction (from the front,
    dorsal up), the camera tilts up by *elevation* degrees so it looks down on
    the scene, and ``quiltwright.frame_and_focus`` then fits the scene at that
    final direction and puts the focal plane at the harmonic mean of its near
    and far depths. ``reset_camera()`` would fit the un-tilted bounds instead,
    which leaves a tilted scene small in frame.

    ``frame_and_focus`` measures ``plotter.bounds``, so call this before
    :func:`add_floor`. It also fits to the window's aspect: pass the quilt or
    still *spec* you will render, and the window is set to the aspect
    ``render_quilt`` captures each view at (16:9 for ``16-landscape``, whose
    tiles are 4:3). Afterwards, pass ``fov=None`` to ``render_quilt`` and
    ``depth_report``: the camera is locked.

    :param plotter: Plotter with the scene composed.
    :param points: World points the view direction is computed from,
        usually ``SceneInfo.points``.
    :param fov: Vertical field of view to lock the camera to, in degrees.
    :param elevation: Degrees to tilt the camera up from the front view.
    :param spec: The ``quiltwright.QuiltSpec`` the scene will be rendered at;
        ``None`` frames at the window's current aspect, as an interactive
        viewer wants.
    :return: ``(near, far, focal_distance)`` from ``frame_and_focus``.
    """
    from kg_utils.viz3d import frame_tree  # noqa: PLC0415 - the viz3d-render-only import boundary
    from quiltwright import frame_and_focus  # noqa: PLC0415

    frame = frame_tree(points, fov=fov)
    camera = plotter.camera
    camera.position = frame.position
    camera.focal_point = frame.focal_point
    camera.up = frame.up
    if elevation:
        camera.Elevation(elevation)
        camera.OrthogonalizeViewUp()
    return frame_and_focus(plotter, fov=fov, spec=spec)


def add_floor(plotter: pv.Plotter) -> None:
    """Put a shadow-receiving floor under the composed scene, lit from above.

    Adds a floor plane (actor ``floor``) in the background grey just below
    ``plotter.bounds``, replaces the lights with a shadow-casting key
    spotlight above the scene plus a weak headlight, and enables shadow
    mapping. The floor is only visible from a camera that looks down on it,
    so pair it with a non-zero ``elevation`` in :func:`aim_camera`, and call
    it after framing: the floor is far larger than the scene and would
    otherwise decide the framing.

    :param plotter: Plotter with the scene composed and the camera framed.
    """
    import pyvista as pv  # noqa: PLC0415 - the viz3d-render-only import boundary

    xmin, xmax, ymin, ymax, zmin, zmax = plotter.bounds
    cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2
    floor = pv.Plane(
        center=(cx, cy, zmin - _FLOOR_DROP),
        direction=(0, 0, 1),
        i_size=_FLOOR_SIZE,
        j_size=_FLOOR_SIZE,
        i_resolution=1,
        j_resolution=1,
    )
    plotter.add_mesh(floor, color=BACKGROUND, ambient=0.25, diffuse=0.8, specular=0.0, name="floor")

    plotter.remove_all_lights()
    dx, dy = _KEY_LIGHT_OFFSET
    key = pv.Light(
        position=(cx + dx, cy + dy, zmax + _KEY_LIGHT_HEIGHT),
        focal_point=(cx, cy, zmin),
        light_type="scene light",
        intensity=_KEY_LIGHT_INTENSITY,
    )
    key.positional = True
    key.cone_angle = _KEY_LIGHT_CONE
    plotter.add_light(key)
    plotter.add_light(pv.Light(light_type="headlight", intensity=_FILL_LIGHT_INTENSITY))
    plotter.enable_shadows()  # ty: ignore[missing-argument]
    # PyVista exposes no setter for the shadow map size.
    shadow_pass = plotter.renderer._render_passes._shadow_map_pass
    if shadow_pass is not None:
        shadow_pass.GetShadowMapBakerPass().SetResolution(_SHADOW_MAP_RESOLUTION)


def build_brain_scene(
    plotter: pv.Plotter,
    kg: ConnectomeKG,
    *,
    specs: Sequence[str] = (),
    view: str = "circuit",
    data_dir: str | Path | None = None,
    color_by: str = "super_class",
    skeleton_step: int = 4,
    tubes: bool = False,
    top: int = 100,
    neuropils: bool = True,
    cloud: bool | None = None,
    progress: Callable[[str], None] | None = None,
) -> SceneInfo:
    """Compose the whole-brain context cloud plus a circuit or neuropil flow into *plotter*.

    :param plotter: PyVista plotter to compose into; actors are cleared first.
    :param kg: An open ``ConnectomeKG``.
    :param specs: For ``view="circuit"``, specs resolved and unioned via
        :func:`circuit_neurons` for the circuit view (view B); empty draws the
        context cloud alone. For ``view="flow"``, specs whose neurons the flow
        sum is restricted to, with no neuron cap; empty sums every neuron.
    :param view: ``"circuit"`` (view B) or ``"flow"`` (view C).
    :param data_dir: Skeleton download root (``fafb_v783``); without it every
        circuit neuron falls back to a marked-point sphere. Unused by the
        flow view.
    :param color_by: Context cloud colouring, ``"super_class"`` or ``"sign"``.
        The flow view ignores it and draws the cloud in neutral grey.
    :param skeleton_step: Skeleton simplification stride, bounded to
        ``[1, MAX_SKELETON_STEP]`` via :func:`~connectomekg.validation.bounded_int`.
    :param tubes: Draw circuit skeletons as tubes instead of lines.
    :param top: Flow arcs drawn, strongest first, bounded to
        ``[1, MAX_FLOW_PAIRS]``.
    :param neuropils: Draw the neuropil surface meshes when the dataset has
        them cached (``connkg meshes``); without the cache the scene is drawn
        without them and *progress* says how to fetch them.
    :param cloud: Draw the whole-brain context cloud of marked points;
        ``None`` (the default) draws it only when no neuropil meshes are.
    :param progress: Called with a short message at each stage; ``None`` (the
        default) keeps the build silent. The same
        ``Callable[[str], None]`` contract as ``ConnectomeExtractor``'s, so
        the CLI and the viewer share it.
    :return: The composed :class:`SceneInfo`.
    :raises ValueError: On an out-of-range argument, an unknown ``view`` or
        ``color_by``, or a circuit over :data:`connectomekg.validation.MAX_SCENE_NEURONS`.
    """
    import pyvista as pv  # noqa: PLC0415 - the viz3d-render-only import boundary

    view = require_choice("view", view, VIEWS)
    skeleton_step = bounded_int("skeleton_step", skeleton_step, 1, MAX_SKELETON_STEP)
    top = bounded_int("top", top, 1, MAX_FLOW_PAIRS)

    def _say(message: str) -> None:
        if progress is not None:
            progress(message)

    plotter.clear_actors()
    plotter.set_background(BACKGROUND)  # ty: ignore[invalid-argument-type]
    frame = world_frame(kg.store)
    world_points: list[np.ndarray] = []

    n_meshes = 0
    if neuropils:
        mesh_path = neuropil_mesh_path(kg.db_path)
        if mesh_path.exists():
            meshes = load_neuropil_meshes(mesh_path)
            _say(f"{len(meshes)} neuropil meshes")
            _draw_neuropil_meshes(plotter, meshes, frame, view)
            world_points.extend(frame.to_world(v.astype(np.float64)) for v, _ in meshes.values())
            n_meshes = len(meshes)
        else:
            _say("no neuropil meshes cached; `connkg meshes` fetches them")

    n_context = 0
    n_context_somas = 0
    if cloud is None:
        # The surfaces show the brain's outline more plainly than 139,255
        # dots, so the cloud stays for a scene that has no meshes drawn.
        cloud = n_meshes == 0
    if cloud:
        _say("context point cloud")
        ctx_ids, ctx_points_nm, ctx_colors, n_context_somas = context_points(
            kg.store, color_by=color_by
        )
        ctx_ids, ctx_points_nm, ctx_colors, radius = _context_for_view(
            view, ctx_ids, ctx_points_nm, ctx_colors
        )
        n_context = len(ctx_ids)
        if n_context:
            ctx_world = frame.to_world(ctx_points_nm)
            cloud_mesh = pv.PolyData(ctx_world)
            rgb = np.asarray([_hex_to_rgb(c) for c in ctx_colors], dtype=np.float64)
            rgb = (
                rgb + (np.asarray(_hex_to_rgb(BACKGROUND), dtype=np.float64) - rgb) * _CONTEXT_MUTE
            )
            cloud_mesh.point_data["rgb"] = np.clip(rgb, 0, 255).astype(np.uint8)
            glyphs = cloud_mesh.glyph(
                geom=pv.Sphere(radius=radius, theta_resolution=6, phi_resolution=4),
                orient=False,
                scale=False,
            )
            plotter.add_mesh(glyphs, scalars="rgb", rgb=True, name="context")
            world_points.append(ctx_world)

    ds_row = kg.store.con.execute("SELECT name FROM nodes WHERE kind='dataset'").fetchone()
    dataset_name = ds_row[0] if ds_row else "connectome"

    if view == "flow":
        n_pairs, n_total = _draw_flow(plotter, kg, specs, frame, top, world_points, _say)
        points = np.concatenate(world_points, axis=0) if world_points else np.zeros((1, 3))
        scope = f" via {', '.join(specs)}" if specs else ""
        title = (
            f"{dataset_name} | neuropil flow{scope}: top {n_pairs} of {n_total} pairs "
            f"context={n_context}"
        )
        _say("scene composed")
        return SceneInfo(
            title=title,
            points=points,
            n_context=n_context,
            n_circuit=0,
            n_skeletons=0,
            missing_skeletons=[],
            soma_fallbacks=0,
            view=view,
            n_flow_pairs=n_pairs,
            n_flow_total=n_total,
            n_neuropil_meshes=n_meshes,
            n_context_somas=n_context_somas,
        )

    circuit_ids = circuit_neurons(kg, specs) if specs else []
    n_circuit = len(circuit_ids)

    _say(f"resolving {n_circuit} circuit neurons")
    neurons_by_type: dict[str, list[dict]] = {}
    root_ids: list[int] = []
    for nid in circuit_ids:
        node = kg.store.node(nid)
        if node is None:
            continue
        meta = node.get("metadata") or {}
        cell_type = str(meta.get("cell_type") or "unknown")
        neurons_by_type.setdefault(cell_type, []).append(meta)
        root_id = meta.get("root_id")
        if root_id is not None:
            root_ids.append(int(root_id))

    skeletons_by_root: dict[int, Skeleton] = {}
    missing_skeletons: list[int] = list(root_ids)
    cached_roots: set[int] = set()
    cache_path = skeleton_cache_path(kg.db_path)
    if root_ids and cache_path.exists():
        _say(f"loading {len(root_ids)} skeletons from {cache_path.name}")
        skeletons_by_root, missing_skeletons = load_cached_skeletons(cache_path, root_ids)
        cached_roots = set(skeletons_by_root)
    if data_dir is not None and missing_skeletons:
        _say(f"loading {len(missing_skeletons)} skeletons from {data_dir}")
        from_swc, missing_skeletons = load_skeletons(data_dir, missing_skeletons)
        skeletons_by_root.update(from_swc)
    # A cached skeleton is already simplified, so it is drawn with the stride
    # divided down rather than applied a second time; see
    # connectomekg.skeleton_cache.effective_step.
    cached_step = effective_step(skeleton_step, cache_info(cache_path)[0]) if cached_roots else 1

    n_skeletons = 0
    soma_fallbacks = 0
    if circuit_ids:
        _say(f"drawing {n_circuit} circuit neurons")
    for cell_type, metas in neurons_by_type.items():
        color = type_color(cell_type)
        segment_batches: list[np.ndarray] = []
        soma_world: list[np.ndarray] = []
        fallback_world: list[np.ndarray] = []
        for meta in metas:
            root_id = meta.get("root_id")
            skeleton = skeletons_by_root.get(int(root_id)) if root_id is not None else None
            if skeleton is not None:
                n_skeletons += 1
                step = cached_step if skeleton.root_id in cached_roots else skeleton_step
                segs_nm = segments(skeleton, step=step)
                if segs_nm.size:
                    segment_batches.append(frame.to_world(segs_nm.reshape(-1, 3)).reshape(-1, 2, 3))
                soma_nm, is_soma = soma(skeleton)
                if not is_soma:
                    soma_fallbacks += 1
                soma_world.append(frame.to_world(soma_nm)[0])
            else:
                x, y, z = meta.get("x"), meta.get("y"), meta.get("z")
                if x is None or y is None or z is None:
                    continue
                fallback_world.append(frame.to_world(np.asarray([x, y, z], dtype=np.float64))[0])

        if segment_batches:
            segs = np.concatenate(segment_batches, axis=0)
            mesh = _segments_to_polydata(segs)
            if tubes:
                mesh = mesh.tube(radius=_TUBE_RADIUS, n_sides=6)
            plotter.add_mesh(mesh, color=color, line_width=2, name=f"skeleton:{cell_type}")
            world_points.append(segs.reshape(-1, 3))
        if soma_world:
            arr = np.asarray(soma_world)
            glyph = pv.PolyData(arr).glyph(
                geom=pv.Sphere(radius=_SOMA_RADIUS), orient=False, scale=False
            )
            plotter.add_mesh(glyph, color=color, name=f"soma:{cell_type}")
            world_points.append(arr)
        if fallback_world:
            arr = np.asarray(fallback_world)
            glyph = pv.PolyData(arr).glyph(
                geom=pv.Sphere(radius=_FALLBACK_RADIUS), orient=False, scale=False
            )
            plotter.add_mesh(glyph, color=color, name=f"fallback:{cell_type}")
            world_points.append(arr)

    points = np.concatenate(world_points, axis=0) if world_points else np.zeros((1, 3))
    cloud_kind = "somas" if n_context_somas else "context"
    title = f"{dataset_name} | {cloud_kind}={n_context} circuit={n_circuit} skeletons={n_skeletons}"
    _say("scene composed")
    return SceneInfo(
        title=title,
        points=points,
        n_context=n_context,
        n_circuit=n_circuit,
        n_skeletons=n_skeletons,
        missing_skeletons=sorted(set(missing_skeletons)),
        soma_fallbacks=soma_fallbacks,
        n_neuropil_meshes=n_meshes,
        n_context_somas=n_context_somas,
    )


__all__ = [
    "BACKGROUND",
    "FLOOR_ELEVATION",
    "NM_PER_WORLD_UNIT",
    "VIEWS",
    "NeuropilFlow",
    "SceneInfo",
    "WorldFrame",
    "add_floor",
    "aim_camera",
    "build_brain_scene",
    "circuit_neurons",
    "context_points",
    "flow_arc",
    "neuropil_flow",
    "region_color",
    "type_color",
    "world_frame",
]
