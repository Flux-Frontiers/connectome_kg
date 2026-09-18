"""Root Click group for the connkg CLI.

Command modules import ``cli`` from here to avoid circular imports;
``connectomekg.cli`` imports every command module to register them.
"""

from __future__ import annotations

import click


@click.group()
# package_name, not version=: the version is looked up only when --version is
# given, so the CLI still runs from a clone with nothing installed.
@click.version_option(package_name="connectome-kg")
@click.option(
    "--root",
    default=".",
    show_default=True,
    type=click.Path(file_okay=False),
    help="Directory holding connectomes/<dataset>/.connectomekg/.",
)
@click.option(
    "--dataset",
    default=None,
    metavar="ID",
    help=(
        "Dataset to work on, e.g. fafb783. Default: for build, fafb783 (synthetic "
        "with --source synthetic); otherwise the only built dataset."
    ),
)
@click.pass_context
def cli(ctx: click.Context, root: str, dataset: str | None) -> None:
    """connkg -- connectomes as fleet knowledge graphs."""
    ctx.obj = {"root": root, "dataset": dataset}
