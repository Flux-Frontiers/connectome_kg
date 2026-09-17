"""``connkg build`` -- a release into SQLite and, optionally, the vector index."""

from __future__ import annotations

from typing import Any

import click

from connectomekg.cli.group import cli
from connectomekg.cli.options import open_kg, source_options


def _progress(message: str) -> None:
    # stderr is unbuffered, so progress shows live even when stdout is piped.
    click.echo(message, err=True)


@cli.command("build")
@source_options
@click.option("--wipe", is_flag=True, help="Clear the existing graph first.")
@click.option("--no-index", is_flag=True, help="Skip the vector index.")
@click.pass_context
def build(ctx: click.Context, wipe: bool, no_index: bool, **source: Any) -> None:
    """Extract into SQLite (and the vector index)."""
    with open_kg(ctx.obj["root"], progress=_progress, **source) as kg:
        stats = kg.build_graph(wipe=wipe) if no_index else kg.build(wipe=wipe)
    click.echo(str(stats))
