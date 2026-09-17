"""``connkg snapshot`` -- save, list, show, diff and prune graph snapshots.

Snapshots live in ``<root>/.connectomekg/snapshots/`` and are tracked in git.
A snapshot is keyed on the VERSION given to ``save``, or on a UTC timestamp
when none is given; the git tree hash is recorded as provenance, not used as
the key.
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from connectomekg.cli.group import cli
from connectomekg.cli.options import open_kg
from connectomekg.snapshots import SnapshotManager


def _manager(ctx: click.Context) -> SnapshotManager:
    root = Path(ctx.obj["root"])
    return SnapshotManager(
        root / ".connectomekg" / "snapshots", db_path=root / ".connectomekg" / "graph.sqlite"
    )


@cli.group("snapshot")
def snapshot() -> None:
    """Point-in-time metric snapshots of the built graph."""


@snapshot.command("save")
@click.argument("version", default="", required=False)
@click.option("--subject", default="", help="What was measured (default: dataset:<dataset id>).")
@click.option("--force", is_flag=True, help="Write a new entry even if nothing changed.")
@click.pass_context
def save(ctx: click.Context, version: str, subject: str, force: bool) -> None:
    """Capture the built graph's metrics as a snapshot.

    Pass VERSION (a release tag) to key the snapshot on it; omit it to key on a
    UTC timestamp.
    """
    mgr = _manager(ctx)
    if mgr.db_path is None or not mgr.db_path.exists():
        raise click.ClickException(f"no graph at {mgr.db_path}; run `connkg build` first")
    with open_kg(ctx.obj["root"]) as kg:
        stats = kg.store.stats()
        row = kg.store.con.execute("SELECT qualname FROM nodes WHERE kind='dataset'").fetchone()
    snap = mgr.capture(
        version=version or None,
        graph_stats_dict=stats,
        hotspots=mgr.hub_neurons(),
        key=version,
        subject=subject or f"dataset:{row[0] if row else 'unknown'}",
    )
    path = mgr.save_snapshot(snap, force=force)
    m = snap.metrics
    click.echo(f"saved {path}")
    click.echo(f"  key      {snap.key}")
    click.echo(f"  subject  {snap.subject}")
    click.echo(
        f"  tool     {snap.tool} {snap.tool_version}, {snap.branch} tree {snap.tree_hash[:10]}"
    )
    click.echo(f"  nodes    {m.get('total_nodes', 0):,}   edges {m.get('total_edges', 0):,}")


@snapshot.command("list")
@click.option("--limit", type=click.IntRange(min=1), default=None, help="Newest N only.")
@click.option("--json", "as_json", is_flag=True, help="Print the manifest entries as JSON.")
@click.pass_context
def list_(ctx: click.Context, limit: int | None, as_json: bool) -> None:
    """List snapshots, newest first."""
    snaps = _manager(ctx).list_snapshots(limit=limit)
    if as_json:
        click.echo(json.dumps(snaps, indent=2))
        return
    if not snaps:
        click.echo("no snapshots")
        return
    click.echo(f"{'key':<34} {'subject':<18} {'version':<9} {'nodes':>9} {'edges':>11}")
    for s in snaps:
        m = s.get("metrics", {})
        click.echo(
            f"{s['key'][:34]:<34} {s.get('subject', '')[:18]:<18} {s.get('version', '')[:9]:<9} "
            f"{m.get('total_nodes', 0):>9,} {m.get('total_edges', 0):>11,}"
        )


@snapshot.command("show")
@click.argument("key", default="latest", required=False)
@click.pass_context
def show(ctx: click.Context, key: str) -> None:
    """Show one snapshot as JSON (default: the latest)."""
    snap = _manager(ctx).load_snapshot(key)
    if snap is None:
        raise click.ClickException(f"no snapshot {key!r}")
    click.echo(json.dumps(snap.to_dict(), indent=2))


@snapshot.command("diff")
@click.argument("key_a")
@click.argument("key_b")
@click.pass_context
def diff(ctx: click.Context, key_a: str, key_b: str) -> None:
    """Compare two snapshots (B minus A): totals, and node and edge counts that changed."""
    result = _manager(ctx).diff_snapshots(key_a, key_b)
    if "error" in result:
        raise click.ClickException(result["error"])
    a, b = result["a"]["metrics"], result["b"]["metrics"]
    for name in ("total_nodes", "total_edges", "n_neurons", "n_pairs", "n_synapses"):
        va, vb = a.get(name, 0), b.get(name, 0)
        click.echo(f"{name:<14} {va:>12,} {vb:>12,} {vb - va:>+12,}")
    for label, deltas in (("nodes", "node_counts_delta"), ("edges", "edge_counts_delta")):
        changed = {k: v for k, v in result.get(deltas, {}).items() if v}
        for k, v in sorted(changed.items()):
            click.echo(f"  {label} {k}: {v:+,}")
    ca, cb = a.get("coverage", {}), b.get("coverage", {})
    for k in sorted(set(ca) | set(cb)):
        if ca.get(k) != cb.get(k):
            click.echo(f"  coverage {k}: {ca.get(k, 0):.1%} -> {cb.get(k, 0):.1%}")


@snapshot.command("prune")
@click.option("--dry-run", is_flag=True, help="Show what would go without deleting anything.")
@click.pass_context
def prune(ctx: click.Context, dry_run: bool) -> None:
    """Remove snapshots that add no new metrics, broken entries and orphaned files."""
    result = _manager(ctx).prune_snapshots(dry_run=dry_run)
    verb = "would remove" if dry_run else "removed"
    for label, items in (
        ("unchanged", result.removed),
        ("broken entries", result.broken_entries),
        ("orphaned files", result.orphaned_files),
    ):
        if items:
            click.echo(f"{verb} {len(items)} {label}: {', '.join(items)}")
    if not (result.removed or result.broken_entries or result.orphaned_files):
        click.echo("nothing to prune")
