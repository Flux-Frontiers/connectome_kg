"""connectomekg/scene.py

Builds the real-geometry 3-D views of a connectome: view A, every neuron's
marked point as a dim context cloud, and view B, the skeletons of a query's
neurons drawn at full brightness inside it. Unlike the fleet's other viz3d
consumers (``gutenberg_kg``, ``pycode_kg``, ``genealogy_kg``), this graph
already has space -- every neuron carries real ``x``/``y``/``z`` coordinates
and the download holds a traced skeleton for most of them -- so there is no
tree to grow here, no ``kg_utils.viz3d.organic`` call anywhere in this file.
What is reused from that engine is just the camera rule (``frame_tree``, in
``cli/cmd_viz3d.py``) and ``seed_from_key`` for a stable per-type colour.

Split the way ``pycode_kg.scene3d`` and ``genealogy_kg.scene`` split their own
layout from composition, so most of this is testable without PyVista:

* :class:`WorldFrame`, :func:`world_frame`, :func:`context_points` and
  :func:`circuit_neurons` are pure NumPy plus SQL -- no PyVista import.
* :func:`build_brain_scene` composes those into a caller-supplied
  ``pv.Plotter``. This half needs the ``viz3d`` extra.

Colours come from :mod:`connectomekg.colors`, never from :mod:`connectomekg.viz`
-- ``viz.py`` imports ``plotly`` at module scope, and this module must stay
importable with only the ``viz3d`` extra installed, no ``viz``. The same
reason ``genealogy_kg`` keeps its palette in ``theme.py`` rather than
``viz.py``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

import numpy as np
from kg_utils.store import GraphStore
from kg_utils.viz3d import seed_from_key

from connectomekg.colors import SIGN_COLOR, SUPER_CLASS_COLOR, UNKNOWN_COLOR
from connectomekg.skeletons import Skeleton, load_skeletons, segments, soma
from connectomekg.validation import (
    MAX_SCENE_NEURONS,
    MAX_SKELETON_STEP,
    bounded_int,
    require_choice,
)

if TYPE_CHECKING:
    import pyvista as pv

    from connectomekg.module import ConnectomeKG

#: World units per nanometre's worth of scale: 1 world unit per 100,000 nm,
#: so the brain (about 0.81 x 0.39 x 0.28 mm) is roughly 8 x 4 x 3 units --
#: inside the depth budget ``quiltwright.depth_report`` checks. See
#: kgrag_priv/docs/CONNECTOME_VIZ3D_PLAN.md section 5.
NM_PER_WORLD_UNIT: Final = 100_000.0

_SQL_NEURON_XYZ = (
    "kind='neuron' AND json_extract(metadata,'$.x') IS NOT NULL "
    "AND json_extract(metadata,'$.y') IS NOT NULL "
    "AND json_extract(metadata,'$.z') IS NOT NULL"
)

#: Point size and darkening for the context cloud -- dim rather than
#: transparent, since alpha ghosts in light-field renders (plan section 3.A).
_CONTEXT_POINT_SIZE: Final = 3.0
_CONTEXT_DIM: Final = 0.55
#: Sphere radii, world units. A fallback sphere (no skeleton) is drawn larger
#: than a real soma so it reads as a stand-in, not a measurement.
_SOMA_RADIUS: Final = 0.05
_FALLBACK_RADIUS: Final = 0.09
_TUBE_RADIUS: Final = 0.01

#: Qualitative palette a cell type's colour is deterministically drawn from,
#: via :func:`type_color`. Okabe-Ito colour-blind-safe eight, extended with a
#: further seven visually distinct hues so nearby types rarely collide.
_TYPE_PALETTE: Final[tuple[str, ...]] = (
    "#E69F00",
    "#56B4E9",
    "#009E73",
    "#F0E442",
    "#0072B2",
    "#D55E00",
    "#CC79A7",
    "#999999",
    "#882255",
    "#44AA99",
    "#332288",
    "#AA4499",
    "#117733",
    "#DDCC77",
    "#88CCEE",
)


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
) -> tuple[list[str], np.ndarray, list[str]]:
    """Every neuron's marked point, for the whole-brain context cloud (view A).

    :param store: The graph store.
    :param color_by: ``"super_class"`` or ``"sign"``.
    :return: ``(neuron_ids, points_nm, colors)`` -- ``points_nm`` is
        ``(n, 3)``, ``colors`` is one ``#RRGGBB`` string per neuron, same
        order as ``neuron_ids``. Neurons with no coordinates are omitted.
    :raises ValueError: If ``color_by`` is not one of the two choices.
    """
    color_by = require_choice("color_by", color_by, ("super_class", "sign"))
    rows = store.con.execute(
        f"SELECT id, json_extract(metadata,'$.x'), json_extract(metadata,'$.y'), "
        f"json_extract(metadata,'$.z'), json_extract(metadata,'$.super_class'), "
        f"json_extract(metadata,'$.sign') FROM nodes WHERE {_SQL_NEURON_XYZ}"
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
    return ids, points, colors


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
    """

    title: str
    points: np.ndarray
    n_context: int
    n_circuit: int
    n_skeletons: int
    missing_skeletons: list[int]
    soma_fallbacks: int


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


def build_brain_scene(
    plotter: pv.Plotter,
    kg: ConnectomeKG,
    *,
    specs: Sequence[str] = (),
    data_dir: str | Path | None = None,
    color_by: str = "super_class",
    skeleton_step: int = 4,
    tubes: bool = False,
    progress: Callable[[str], None] | None = None,
) -> SceneInfo:
    """Compose the whole-brain context cloud plus a spec's circuit into *plotter*.

    :param plotter: PyVista plotter to compose into; actors are cleared first.
    :param kg: An open ``ConnectomeKG``.
    :param specs: Specs resolved and unioned via :func:`circuit_neurons` for
        the circuit view (view B). Empty draws the context cloud alone.
    :param data_dir: Skeleton download root (``fafb_v783``); without it every
        circuit neuron falls back to a marked-point sphere.
    :param color_by: Context cloud colouring, ``"super_class"`` or ``"sign"``.
    :param skeleton_step: Skeleton simplification stride, bounded to
        ``[1, MAX_SKELETON_STEP]`` via :func:`~connectomekg.validation.bounded_int`.
    :param tubes: Draw circuit skeletons as tubes instead of lines.
    :param progress: Called with a short message at each stage; ``None`` (the
        default) keeps the build silent. The same
        ``Callable[[str], None]`` contract as ``ConnectomeExtractor``'s, so
        the CLI and the viewer share it.
    :return: The composed :class:`SceneInfo`.
    :raises ValueError: On an out-of-range argument, an unknown ``color_by``,
        or a circuit over :data:`connectomekg.validation.MAX_SCENE_NEURONS`.
    """
    import pyvista as pv  # noqa: PLC0415 - the viz3d-render-only import boundary

    skeleton_step = bounded_int("skeleton_step", skeleton_step, 1, MAX_SKELETON_STEP)

    def _say(message: str) -> None:
        if progress is not None:
            progress(message)

    plotter.clear_actors()
    frame = world_frame(kg.store)
    world_points: list[np.ndarray] = []

    _say("context point cloud")
    ctx_ids, ctx_points_nm, ctx_colors = context_points(kg.store, color_by=color_by)
    n_context = len(ctx_ids)
    if n_context:
        ctx_world = frame.to_world(ctx_points_nm)
        cloud = pv.PolyData(ctx_world)
        rgb = np.asarray([_hex_to_rgb(c) for c in ctx_colors], dtype=np.float64)
        cloud.point_data["rgb"] = np.clip(rgb * _CONTEXT_DIM, 0, 255).astype(np.uint8)
        plotter.add_mesh(
            cloud,
            scalars="rgb",
            rgb=True,
            point_size=_CONTEXT_POINT_SIZE,
            render_points_as_spheres=True,
            name="context",
        )
        world_points.append(ctx_world)

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
    if data_dir is not None and root_ids:
        _say(f"loading {len(root_ids)} skeletons from {data_dir}")
        skeletons_by_root, missing_skeletons = load_skeletons(data_dir, root_ids)

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
                segs_nm = segments(skeleton, step=skeleton_step)
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
    ds_row = kg.store.con.execute("SELECT name FROM nodes WHERE kind='dataset'").fetchone()
    dataset_name = ds_row[0] if ds_row else "connectome"
    title = f"{dataset_name} | context={n_context} circuit={n_circuit} skeletons={n_skeletons}"
    _say("scene composed")
    return SceneInfo(
        title=title,
        points=points,
        n_context=n_context,
        n_circuit=n_circuit,
        n_skeletons=n_skeletons,
        missing_skeletons=sorted(set(missing_skeletons)),
        soma_fallbacks=soma_fallbacks,
    )


__all__ = [
    "NM_PER_WORLD_UNIT",
    "SceneInfo",
    "WorldFrame",
    "build_brain_scene",
    "circuit_neurons",
    "context_points",
    "type_color",
    "world_frame",
]
