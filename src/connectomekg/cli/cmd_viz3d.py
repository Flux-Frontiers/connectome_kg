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
(see ``renders/README.md``): ``stills/`` for working PNGs (``--still``,
``--preview``), ``quilts/`` for Looking Glass quilts, ``views/``
reserved for per-view captures, ``reports/`` reserved for future per-render
provenance records.
"""

from __future__ import annotations

import importlib.util
import re
from dataclasses import replace
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

#: Height of a ``--still`` image; the width follows the preset's aspect, so a
#: 16-landscape still is 3840 x 2160.
STILL_HEIGHT = 2160
#: Default quilt view cone, degrees. quiltwright's library sweeps a preset's
#: full cone (50 for 16-landscape); its CLI and render scripts cap at 35.
DEFAULT_VIEW_CONE = 35.0


def resolve_elevation(floor: bool, elevation: float | None) -> float:
    """The camera elevation to render at: explicit, else a floor's default.

    :param floor: Whether ``--floor`` was given.
    :param elevation: The ``--elevation`` value, or ``None`` when omitted.
    :return: *elevation* when given; otherwise ``FLOOR_ELEVATION`` with a
        floor, which is invisible from a level camera, and 0 without.
    """
    if elevation is not None:
        return elevation
    from connectomekg.scene import FLOOR_ELEVATION  # noqa: PLC0415 - numpy only, no extra

    return FLOOR_ELEVATION if floor else 0.0


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
    help="Colour the context cloud by super class or transmitter sign (circuit view; "
    "the flow view's cloud is neutral grey).",
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
floor_option = click.option(
    "--floor",
    is_flag=True,
    help="Stand the scene over a floor lit from above, with shadows. Tilts the "
    "camera down (see --elevation).",
)
neuropils_option = click.option(
    "--neuropils/--no-neuropils",
    default=True,
    show_default=True,
    help="Draw the neuropil surface meshes, when fetched with `connkg meshes`.",
)
cloud_option = click.option(
    "--cloud/--no-cloud",
    default=None,
    help="Draw the whole-brain context cloud of marked points. Default: only "
    "when the neuropil surfaces are not drawn.",
)
elevation_option = click.option(
    "--elevation",
    default=None,
    type=click.FloatRange(-80.0, 80.0),
    help="Degrees to tilt the camera up from the front view, so it looks down. "
    "Default 25 with --floor, else 0.",
)


@cli.command("quilt")
@click.argument("specs", nargs=-1)
@view_option
@data_dir_option
@color_by_option
@skeleton_step_option
@tubes_option
@top_option
@neuropils_option
@cloud_option
@floor_option
@elevation_option
@preset_option
@click.option(
    "--view-cone",
    default=DEFAULT_VIEW_CONE,
    show_default=True,
    type=click.FloatRange(1.0, 90.0),
    help="Degrees the quilt cameras sweep; the preset's own cone can exceed what fuses.",
)
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
    help="Output directory (default: renders/quilts, or renders/stills with --still).",
)
@click.option(
    "--still",
    is_flag=True,
    help="Render one flat centre view at the preset's aspect (3840x2160 for "
    "16-landscape) instead of a quilt.",
)
@click.option(
    "--preview",
    default=None,
    type=click.Path(dir_okay=False),
    help="Also write one plain PNG of the framed view (bare filename -> renders/stills/).",
)
@click.option("--cast", is_flag=True, help="Send the finished quilt to Looking Glass Bridge.")
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
    neuropils: bool,
    cloud: bool | None,
    floor: bool,
    elevation: float | None,
    preset: str,
    view_cone: float,
    fov: float,
    zoom: float,
    out_dir: Path | None,
    still: bool,
    preview: str | None,
    cast: bool,
) -> None:
    """Render SPEC(s)' circuit or the neuropil flow in the whole brain as a Looking Glass quilt.

    Each SPEC is a cell type, root id, neuron node id or ``label:<regex>``
    (see ``ConnectomeKG.neurons_of``). With ``--view circuit`` their union is
    the circuit drawn at full brightness, capped at ``MAX_SCENE_NEURONS``
    neurons. With ``--view flow`` SPECs are optional and restrict the flow to
    their neurons. ``--still`` renders the same camera's centre view as one
    flat image.
    """
    require_specs_for_view(view, specs)
    if still and cast:
        raise click.UsageError("--cast sends a quilt; it cannot be combined with --still")
    missing = _missing_modules("pyvista", "quiltwright")
    if missing:
        raise click.UsageError(
            f"{', '.join(missing)} not installed. Install the viz3d extra with:\n  {_VIZ3D_EXTRA}"
        )

    import pyvista as pv  # noqa: PLC0415 - arrives with the viz3d extra
    from quiltwright import (  # noqa: PLC0415
        QUILT_PRESETS,
        depth_report,
        render_quilt,
        save_and_cast_quilt,
        save_quilt,
    )

    from connectomekg import scene as render3d  # noqa: PLC0415

    if preset not in QUILT_PRESETS:
        raise click.UsageError(
            f"Unknown quilt preset {preset!r}. Choose from: {', '.join(QUILT_PRESETS)}"
        )
    spec_obj = replace(QUILT_PRESETS[preset], view_cone=view_cone)
    if still:
        spec_obj = spec_obj.still(height=STILL_HEIGHT)

    plotter = pv.Plotter(off_screen=True)
    with open_kg(ctx.obj["root"], dataset=ctx.obj["dataset"]) as kg, usage_errors():
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
            neuropils=neuropils,
            cloud=cloud,
            progress=lambda m: click.echo(f"  {m}", err=True),
        )

    if view == "circuit":
        click.echo(
            f"Scene: {info.title} (missing skeletons: {len(info.missing_skeletons)}, "
            f"soma fallbacks: {info.soma_fallbacks})"
        )
    else:
        click.echo(f"Scene: {info.title}")

    render3d.aim_camera(
        plotter,
        info.points,
        fov=fov,
        elevation=resolve_elevation(floor, elevation),
        spec=spec_obj,
    )
    # The camera is locked now, so the report and the render both take
    # fov=None. The report comes before the floor, which reaches past the
    # camera and would otherwise be what it measures.
    if not still:
        click.echo(depth_report(plotter, spec_obj, fov=None, zoom=zoom))
    if floor:
        render3d.add_floor(plotter)

    if preview is not None:
        preview_path = resolve_preview_path(preview)
        plotter.screenshot(str(preview_path))
        click.echo(f"Wrote preview {preview_path}")

    out_dir = out_dir or (STILLS_DIR if still else QUILTS_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = out_dir / scene_stem(view, specs)
    click.echo(
        f"Rendering {spec_obj.n_views} views at {spec_obj.tile_width}x{spec_obj.tile_height}..."
    )
    image = render_quilt(plotter, spec_obj, fov=None, zoom=zoom)
    plotter.close()
    if cast:
        path, error = save_and_cast_quilt(image, stem, spec_obj)
        click.echo(f"Wrote {path}")
        if error:
            click.echo(f"Cast failed (is Looking Glass Bridge running?): {error}", err=True)
        else:
            click.echo("Cast to Looking Glass Bridge.")
    else:
        path = save_quilt(image, stem, spec_obj)
        click.echo(f"Wrote {path}")


@cli.command("viz3d")
@click.argument("specs", nargs=-1)
@view_option
@data_dir_option
@color_by_option
@skeleton_step_option
@tubes_option
@top_option
@neuropils_option
@cloud_option
@floor_option
@elevation_option
@preset_option
@click.option("--width", default=1400, show_default=True, type=int, help="Window width, pixels.")
@click.option("--height", default=900, show_default=True, type=int, help="Window height, pixels.")
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
    neuropils: bool,
    cloud: bool | None,
    floor: bool,
    elevation: float | None,
    preset: str,
    width: int,
    height: int,
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
            neuropils=neuropils,
            cloud=cloud,
            floor=floor,
            elevation=resolve_elevation(floor, elevation),
            preset=preset,
            dataset=ctx.obj["dataset"],
            width=width,
            height=height,
        )
    except ValueError as exc:
        raise click.UsageError(str(exc)) from exc
