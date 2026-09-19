"""``connkg fixture``, ``files``, ``verify``, ``meshes`` and ``datasets`` -- getting, checking and listing releases."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import click

from connectomekg.cli.group import cli
from connectomekg.cli.options import open_kg, usage_errors
from connectomekg.datasets import DATASETS_DIR, graph_path, scan_datasets
from connectomekg.manifest import STATIC_ARCHIVES, portal_guide, verify_dir
from connectomekg.neuropil_meshes import fetch_neuropil_meshes, neuropil_mesh_path
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


@cli.command("meshes")
@click.pass_context
def meshes(ctx: click.Context) -> None:
    """Fetch the neuropil surface meshes the 3-D views draw (FAFB v783, about 1 MB).

    Downloads from FlyWire's public bucket, no sign-in, and caches them beside
    the dataset's graph. Run again to refresh the cache.
    """
    with open_kg(ctx.obj["root"], dataset=ctx.obj["dataset"]) as kg, usage_errors():
        row = kg.store.con.execute("SELECT qualname FROM nodes WHERE kind='dataset'").fetchone()
        path = fetch_neuropil_meshes(
            row[0] if row else "",
            neuropil_mesh_path(kg.db_path),
            progress=lambda m: click.echo(m, err=True),
        )
    click.echo(f"wrote {path}")


@cli.command("datasets")
@click.pass_context
def datasets(ctx: click.Context) -> None:
    """List the datasets built under --root, one graph each."""
    root = ctx.obj["root"]
    ids = scan_datasets(root)
    if not ids:
        click.echo(f"no datasets built under {Path(root) / DATASETS_DIR}")
        return
    click.echo(f"{'dataset':<16} {'graph':>9}  name")
    for dataset_id in ids:
        db = graph_path(root, dataset_id)
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            row = con.execute("SELECT name FROM nodes WHERE kind = 'dataset'").fetchone()
        finally:
            con.close()
        n = db.stat().st_size
        size = f"{n / 1e9:.1f} GB" if n >= 1e9 else f"{n / 1e6:.1f} MB"
        click.echo(f"{dataset_id:<16} {size:>9}  {row[0] if row else '?'}")
