"""``connkg viz`` -- draw a cell type's local circuit to a self-contained HTML file.

``network`` is the type with its strongest input and output partner types as an
interactive graph; ``partners`` is the same partners as a diverging bar chart.
Both need the ``viz`` extra, and the renderer is imported inside the command:
this module loads whenever the CLI starts, and the libraries only arrive with
the extra.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import click

from connectomekg.cli.group import cli
from connectomekg.cli.options import open_kg, usage_errors
from connectomekg.validation import MAX_LIMIT

_VIZ_EXTRA = 'pip install "connectome-kg[viz]"'


@cli.command("viz")
@click.argument("cell_type")
@click.option(
    "--view",
    type=click.Choice(["network", "partners"]),
    default="network",
    show_default=True,
    help="'network' draws the partner graph; 'partners' draws a diverging bar chart.",
)
@click.option(
    "--limit",
    default=15,
    show_default=True,
    type=click.IntRange(1, MAX_LIMIT),
    help="Partner types per direction. A graph is unreadable well below the maximum.",
)
@click.option(
    "-o",
    "--output",
    default=None,
    type=click.Path(dir_okay=False, writable=True),
    help="HTML file to write (default: <cell type>_<view>.html).",
)
@click.pass_context
def viz(ctx: click.Context, cell_type: str, view: str, limit: int, output: str | None) -> None:
    """Draw CELL_TYPE's strongest partner types to a self-contained HTML file.

    The file has its rendering library inlined, so it opens straight from the
    filesystem and can be sent to someone without the data or Python.
    """
    missing = "pyvis" if view == "network" else "plotly"
    if importlib.util.find_spec(missing) is None:
        raise click.UsageError(
            f"{missing} is not installed. Install the viz extra with:\n  {_VIZ_EXTRA}"
        )

    from connectomekg import viz as render  # noqa: PLC0415 - arrives with the viz extra

    path = Path(output or f"{cell_type}_{view}.html".replace("/", "_"))
    with open_kg(ctx.obj["root"], dataset=ctx.obj["dataset"]) as kg, usage_errors():
        if view == "network":
            path.write_text(render.type_network_html(kg, cell_type, limit=limit), encoding="utf-8")
        else:
            render.partners_figure(kg, cell_type, limit=limit).write_html(
                path, include_plotlyjs=True
            )
    click.echo(f"wrote {path} -- {view} of {cell_type}, top {limit} partner types each way")
