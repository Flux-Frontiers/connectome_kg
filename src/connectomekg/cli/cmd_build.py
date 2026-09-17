"""``connkg build`` -- a release into SQLite and, optionally, the vector index."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click
from kg_utils.specs import BuildStats

from connectomekg.cli.group import cli
from connectomekg.cli.options import open_kg, source_options
from connectomekg.report import BuildRun, write_build_report
from connectomekg.schema import DatasetInfo


@cli.command("build")
@source_options
@click.option("--wipe", is_flag=True, help="Clear the existing graph first.")
@click.option("--no-index", is_flag=True, help="Skip the vector index.")
@click.pass_context
def build(ctx: click.Context, wipe: bool, no_index: bool, **source: Any) -> None:
    """Extract into SQLite (and the vector index).

    Every run, successful or not, writes a provenance report to
    <root>/reports/build_<timestamp>.md.
    """
    run = BuildRun(Path(ctx.obj["root"]), {**source, "wipe": wipe, "no_index": no_index})

    def progress(message: str) -> None:
        # stderr is unbuffered, so progress shows live even when stdout is piped.
        click.echo(message, err=True)
        run.stage(message)

    stats: BuildStats | None = None
    dataset: DatasetInfo | None = None
    db_path: Path | None = None
    error: Exception | None = None
    try:
        with open_kg(ctx.obj["root"], progress=progress, **source) as kg:
            db_path = kg.db_path
            stats = kg.build_graph(wipe=wipe) if no_index else kg.build(wipe=wipe)
            dataset = kg.tables().dataset
    except Exception as exc:
        error = exc
        raise
    finally:
        report = write_build_report(run, stats=stats, dataset=dataset, db_path=db_path, error=error)
        click.echo(f"report: {report}", err=True)
    click.echo(str(stats))
