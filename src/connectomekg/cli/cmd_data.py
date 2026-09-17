"""``connkg fixture``, ``files`` and ``verify`` -- getting and checking a release."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from connectomekg.cli.group import cli
from connectomekg.manifest import STATIC_ARCHIVES, portal_guide, verify_dir
from connectomekg.readers.synthetic import synthetic_tables, write_codex_dir


@cli.command("fixture")
@click.option(
    "--out",
    required=True,
    type=click.Path(file_okay=False),
    help="Directory to write the release into.",
)
@click.option(
    "--n",
    default=1000,
    show_default=True,
    type=click.IntRange(min=1),
    help="Neurons; at least min_neurons().",
)
@click.option("--seed", default=1, show_default=True, type=int)
def fixture(out: str, n: int, seed: int) -> None:
    """Write a synthetic Codex-format release."""
    d = write_codex_dir(synthetic_tables(n, seed), out)
    click.echo(f"wrote synthetic Codex release to {d}")


@cli.command("files")
def files() -> None:
    """Portal labels beside the file names they download as."""
    click.echo("FlyWire Codex FAFB v783, https://codex.flywire.ai/api/download?dataset=fafb")
    click.echo("(sign in with a Google account; the portal lists labels, not file names)\n")
    click.echo(portal_guide())
    click.echo("\nThe portal is live and updated continually. For a reproducible build")
    click.echo("use the October 2024 published snapshot instead:\n")
    for what, url in STATIC_ARCHIVES.items():
        click.echo(f"  {what}: {url}")


@cli.command("verify")
@click.option("--data-dir", required=True, type=click.Path(file_okay=False))
@click.option("--no-checksums", is_flag=True, help="Skip the SHA-256 comparison.")
def verify(data_dir: str, no_checksums: bool) -> None:
    """Check a Codex download against the v783 manifest."""
    report = verify_dir(Path(data_dir), checksums=not no_checksums)
    click.echo(str(report))
    if report.missing_required:
        click.echo("\nThe portal lists display names, not file names:\n")
        click.echo(portal_guide())
    if not report.ok:
        sys.exit(1)
