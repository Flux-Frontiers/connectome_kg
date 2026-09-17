"""``connkg quilt``/``viz3d`` -- real-geometry 3-D views of a connectome.

``quilt`` composes the whole-brain context cloud plus a circuit's skeletons
(``--view circuit``) or the neuropil flow (``--view flow``), see
:mod:`connectomekg.scene`, and renders it to a Looking Glass quilt;
``viz3d`` opens the same scene in an interactive viewer. Both need the
``viz3d`` extra, and the renderer is imported inside each command: this
module loads whenever the CLI starts, and PyVista/Qt/quiltwright only arrive
with the extra -- the same ``importlib.util.find_spec`` + install-hint
pattern as ``cli/cmd_viz.py``.

Output layout under ``renders/`` follows quiltwright's own
(kgrag_priv/docs/CONNECTOME_VIZ3D_PLAN.md section 4): ``stills/`` for working
PNGs (``--preview``), ``quilts/`` for Looking Glass quilts, ``views/``
reserved for per-view captures, ``reports/`` reserved for future per-render
provenance records.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import click

from connectomekg.cli.group import cli
from connectomekg.cli.options import open_kg, usage_errors
from connectomekg.validation import MAX_FLOW_PAIRS, MAX_SKELETON_STEP

_VIZ3D_EXTRA = 'pip install "connectome-kg[viz3d]"'

#: renders/ layout -- see the module docstring.
RENDERS_ROOT = Path("renders")
STILLS_DIR = RENDERS_ROOT / "stills"
QUILTS_DIR = RENDERS_ROOT / "quilts"
VIEWS_DIR = RENDERS_ROOT / "views"
REPORTS_DIR = RENDERS_ROOT / "reports"


def resolve_preview_path(preview: str) -> Path:
    """Where a ``--preview`` argument writes its PNG.

    A bare filename (no directory component) lands under :data:`STILLS_DIR`;
    a path that already names a directory is used as given, so
    ``--preview out/x.png`` is not redirected. Either way the parent
    directory is created.

    :param preview: The ``--preview`` option's raw value.
    :return: The resolved path.
    """
    path = Path(preview)
    if path.parent == Path():
        path = STILLS_DIR / path.name
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _missing_modules(*names: str) -> list[str]:
    return [name for name in names if importlib.util.find_spec(name) is None]


def require_specs_for_view(view: str, specs: tuple[str, ...]) -> None:
    """Raise a usage error when ``--view circuit`` has no SPEC to draw.

    :param view: The ``--view`` value.
    :param specs: The SPEC arguments.
    :raises click.UsageError: For ``circuit`` with no SPEC.
    """
    if view == "circuit" and not specs:
        raise click.UsageError("--view circuit needs at least one SPEC")


def scene_stem(view: str, specs: tuple[str, ...]) -> str:
    """A default output stem: the specs for a circuit, ``flow_<specs>`` for a flow."""
    return sanitize_specs(specs) if view == "circuit" else sanitize_specs(("flow", *specs))


def sanitize_specs(specs: tuple[str, ...]) -> str:
    """A filesystem-safe stem from the SPEC arguments, for a default output name."""
    joined = "_".join(specs)
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", joined).strip("_")
    return safe or "scene"


data_dir_option = click.option(
    "--data-dir",
    default="fafb_v783",
    show_default=True,
    type=click.Path(file_okay=False),
    help="Skeleton download root (sk_lod1_783_healed/ lives inside it).",
)
color_by_option = click.option(
    "--color-by",
    type=click.Choice(["super_class", "sign"]),
    default="super_class",
    show_default=True,
    help="Colour the context cloud by super class or transmitter sign.",
)
skeleton_step_option = click.option(
    "--skeleton-step",
    default=4,
    show_default=True,
    type=click.IntRange(1, MAX_SKELETON_STEP),
    help="Skeleton simplification stride; 1 draws every traced point.",
)
tubes_option = click.option(
    "--tubes", is_flag=True, help="Draw circuit skeletons as tubes instead of lines."
)
preset_option = click.option(
    "--preset",
    default="16-landscape",
    show_default=True,
    help="Looking Glass quilt preset.",
)
view_option = click.option(
    "--view",
    type=click.Choice(["circuit", "flow"]),
    default="circuit",
    show_default=True,
    help="circuit: SPEC(s)' skeletons; flow: signal flow between neuropils, "
    "optionally carried only by SPEC(s)' neurons.",
)
top_option = click.option(
    "--top",
    default=100,
    show_default=True,
    type=click.IntRange(1, MAX_FLOW_PAIRS),
    help="Flow view: strongest neuropil pairs drawn.",
)
dataset_id_option = click.option(
    "--dataset-id", default=None, help="Dataset id; fafb783 selects FAFB v783."
)


@cli.command("quilt")
@click.argument("specs", nargs=-1)
@view_option
@data_dir_option
@color_by_option
@skeleton_step_option
@tubes_option
@top_option
@preset_option
@click.option(
    "--fov",
    default=14.0,
    show_default=True,
    type=float,
    help="Per-view vertical field of view, degrees.",
)
@click.option(
    "--zoom", default=1.0, show_default=True, type=float, help="Camera dolly after framing."
)
@click.option(
    "-o",
    "--out",
    "out_dir",
    default=None,
    type=click.Path(file_okay=False, path_type=Path),
    help="Output directory for the quilt (default: renders/quilts).",
)
@click.option(
    "--preview",
    default=None,
    type=click.Path(dir_okay=False),
    help="Also write one plain PNG of the framed view (bare filename -> renders/stills/).",
)
@click.option("--cast", is_flag=True, help="Send the finished quilt to Looking Glass Bridge.")
@dataset_id_option
@click.pass_context
def quilt(
    ctx: click.Context,
    specs: tuple[str, ...],
    view: str,
    data_dir: str,
    color_by: str,
    skeleton_step: int,
    tubes: bool,
    top: int,
    preset: str,
    fov: float,
    zoom: float,
    out_dir: Path | None,
    preview: str | None,
    cast: bool,
    dataset_id: str | None,
) -> None:
    """Render SPEC(s)' circuit or the neuropil flow in the whole brain as a Looking Glass quilt.

    Each SPEC is a cell type, root id, neuron node id or ``label:<regex>``
    (see ``ConnectomeKG.neurons_of``). With ``--view circuit`` their union is
    the circuit drawn at full brightness, capped at ``MAX_SCENE_NEURONS``
    neurons. With ``--view flow`` SPECs are optional and restrict the flow to
    their neurons.
    """
    require_specs_for_view(view, specs)
    missing = _missing_modules("pyvista", "quiltwright")
    if missing:
        raise click.UsageError(
            f"{', '.join(missing)} not installed. Install the viz3d extra with:\n  {_VIZ3D_EXTRA}"
        )

    import pyvista as pv  # noqa: PLC0415 - arrives with the viz3d extra
    from kg_utils.viz3d import frame_tree  # noqa: PLC0415
    from quiltwright import QUILT_PRESETS, depth_report, render_quilt, save_quilt  # noqa: PLC0415

    from connectomekg import scene as render3d  # noqa: PLC0415

    if preset not in QUILT_PRESETS:
        raise click.UsageError(
            f"Unknown quilt preset {preset!r}. Choose from: {', '.join(QUILT_PRESETS)}"
        )
    spec_obj = QUILT_PRESETS[preset]

    plotter = pv.Plotter(off_screen=True)
    with open_kg(ctx.obj["root"], dataset_id=dataset_id) as kg, usage_errors():
        info = render3d.build_brain_scene(
            plotter,
            kg,
            specs=specs,
            view=view,
            data_dir=data_dir,
            color_by=color_by,
            skeleton_step=skeleton_step,
            tubes=tubes,
            top=top,
            progress=lambda m: click.echo(f"  {m}", err=True),
        )

    if view == "circuit":
        click.echo(
            f"Scene: {info.title} (missing skeletons: {len(info.missing_skeletons)}, "
            f"soma fallbacks: {info.soma_fallbacks})"
        )
    else:
        click.echo(f"Scene: {info.title}")

    frame = frame_tree(info.points, fov=fov)
    plotter.camera.position = frame.position
    plotter.camera.focal_point = frame.focal_point
    plotter.camera.up = frame.up
    plotter.reset_camera()  # ty: ignore[missing-argument]

    click.echo(depth_report(plotter, spec_obj, fov=fov, zoom=zoom))

    if preview is not None:
        preview_path = resolve_preview_path(preview)
        plotter.screenshot(str(preview_path))
        click.echo(f"Wrote preview {preview_path}")

    out_dir = out_dir or QUILTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = out_dir / scene_stem(view, specs)
    click.echo(
        f"Rendering {spec_obj.n_views} views at {spec_obj.tile_width}x{spec_obj.tile_height}..."
    )
    path = save_quilt(render_quilt(plotter, spec_obj, fov=fov, zoom=zoom), stem, spec_obj)
    plotter.close()
    click.echo(f"Wrote {path}")

    if cast:
        from quiltwright import cast_quilt  # noqa: PLC0415

        try:
            cast_quilt(path.resolve(), spec_obj)
            click.echo("Cast to Looking Glass Bridge.")
        except Exception as exc:  # noqa: BLE001 - Bridge absence must not fail the render
            click.echo(f"Cast failed (is Looking Glass Bridge running?): {exc}", err=True)


@cli.command("viz3d")
@click.argument("specs", nargs=-1)
@view_option
@data_dir_option
@color_by_option
@skeleton_step_option
@tubes_option
@top_option
@preset_option
@click.option("--width", default=1400, show_default=True, type=int, help="Window width, pixels.")
@click.option("--height", default=900, show_default=True, type=int, help="Window height, pixels.")
@dataset_id_option
@click.pass_context
def viz3d(
    ctx: click.Context,
    specs: tuple[str, ...],
    view: str,
    data_dir: str,
    color_by: str,
    skeleton_step: int,
    tubes: bool,
    top: int,
    preset: str,
    width: int,
    height: int,
    dataset_id: str | None,
) -> None:
    """Launch an interactive 3-D viewer of SPEC(s)' circuit or the neuropil flow.

    Orbit/zoom/pan with the mouse. The toolbar's "Cast to Looking Glass"
    button sends the current view to Bridge.
    """
    require_specs_for_view(view, specs)
    missing = _missing_modules("pyvista", "pyvistaqt", "PyQt5", "quiltwright")
    if missing:
        raise click.UsageError(
            f"{', '.join(missing)} not installed. Install the viz3d extra with:\n  {_VIZ3D_EXTRA}"
        )

    from connectomekg import viz3d as viewer  # noqa: PLC0415 - arrives with the viz3d extra

    root = ctx.obj["root"]
    try:
        viewer.launch(
            root,
            list(specs),
            view=view,
            data_dir=data_dir,
            color_by=color_by,
            skeleton_step=skeleton_step,
            tubes=tubes,
            top=top,
            preset=preset,
            dataset_id=dataset_id,
            width=width,
            height=height,
        )
    except ValueError as exc:
        raise click.UsageError(str(exc)) from exc
