"""``connkg build`` -- a release into SQLite and, optionally, the vector index."""

from __future__ import annotations

from importlib.util import find_spec
from pathlib import Path
from typing import Any

import click
from kg_utils.specs import BuildStats

from connectomekg.cli.group import cli
from connectomekg.cli.options import open_kg, source_options
from connectomekg.report import BuildRun, write_build_report
from connectomekg.schema import DatasetInfo

#: Modules the vector index imports, all from the ``semantic`` extra.
_SEMANTIC_MODULES = ("sentence_transformers", "sqlite_vec")


def missing_semantic() -> list[str]:
    """Modules of the ``semantic`` extra that are not installed.

    :return: Their import names; empty when the index can be built.
    """
    return [m for m in _SEMANTIC_MODULES if find_spec(m) is None]


@cli.command("build")
@source_options
@click.option("--wipe", is_flag=True, help="Clear the existing graph first.")
@click.option("--no-index", is_flag=True, help="Skip the vector index.")
@click.pass_context
def build(ctx: click.Context, wipe: bool, no_index: bool, **source: Any) -> None:
    """Extract into SQLite, then embed the vector index (skip it with --no-index).

    Every run, successful or not, writes a provenance report to
    <root>/reports/build_<timestamp>.md.
    """
    # Checked up front: the index is built last, after minutes of graph work.
    if not no_index and (missing := missing_semantic()):
        raise click.UsageError(
            f"the vector index needs the semantic extra (missing {', '.join(missing)}); "
            "pip install 'connectome-kg[semantic]', or pass --no-index"
        )
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
        with open_kg(
            ctx.obj["root"],
            dataset=ctx.obj["dataset"],
            building=True,
            progress=progress,
            **source,
        ) as kg:
            db_path = kg.db_path
            stats = kg.build_graph(wipe=wipe) if no_index else kg.build(wipe=wipe)
            # A wiped rebuild drops the old index in the SDK (kgmodule-utils
            # 0.24.0, KGModule.drop_index), so only an unwiped graph-only build
            # can reach here with one: kept on purpose, since an unchanged
            # graph still matches it, but worth saying.
            if no_index and kg.vectors_path.exists():
                progress(
                    f"warning: kept the vector index from an earlier build at "
                    f"{kg.vectors_path}; it was not rebuilt and may not match this "
                    "graph. Build without --no-index to refresh it, or delete it."
                )
            dataset = kg.tables().dataset
    except Exception as exc:
        error = exc
        raise
    finally:
        report = write_build_report(run, stats=stats, dataset=dataset, db_path=db_path, error=error)
        click.echo(f"report: {report}", err=True)
    click.echo(str(stats))
