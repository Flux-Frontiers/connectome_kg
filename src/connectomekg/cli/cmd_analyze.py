"""``connkg stats`` and ``analyze`` -- what a built graph holds."""

from __future__ import annotations

from typing import Any

import click

from connectomekg.cli.group import cli
from connectomekg.cli.options import open_kg, source_options


@cli.command("stats")
@source_options
@click.pass_context
def stats(ctx: click.Context, **source: Any) -> None:
    """Node and edge counts for the built graph."""
    with open_kg(ctx.obj["root"], dataset=ctx.obj["dataset"], **source) as kg:
        for k, v in kg.store.stats().items():
            click.echo(f"{k}: {v}")


@cli.command("analyze")
@source_options
@click.pass_context
def analyze(ctx: click.Context, **source: Any) -> None:
    """Markdown analysis of the built graph."""
    with open_kg(ctx.obj["root"], dataset=ctx.obj["dataset"], **source) as kg:
        click.echo(kg.analyze())
