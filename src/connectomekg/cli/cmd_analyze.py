"""``connkg stats`` and ``analyze`` -- what a built graph holds."""

from __future__ import annotations

import click

from connectomekg.cli.group import cli
from connectomekg.cli.options import open_kg


@cli.command("stats")
@click.pass_context
def stats(ctx: click.Context) -> None:
    """Node and edge counts for the built graph."""
    with open_kg(ctx.obj["root"], dataset=ctx.obj["dataset"]) as kg:
        for k, v in kg.stats().items():
            click.echo(f"{k}: {v}")


@cli.command("analyze")
@click.pass_context
def analyze(ctx: click.Context) -> None:
    """Markdown analysis of the built graph."""
    with open_kg(ctx.obj["root"], dataset=ctx.obj["dataset"]) as kg:
        click.echo(kg.analyze())
