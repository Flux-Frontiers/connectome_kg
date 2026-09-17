"""``connkg query``, ``path`` and ``cone`` -- asking the graph things."""

from __future__ import annotations

import sys
from typing import Any

import click

from connectomekg.cli.group import cli
from connectomekg.cli.options import MAX_HOP, MAX_K, open_kg, source_options, usage_errors


@cli.command("query")
@source_options
@click.argument("q")
@click.option("--k", default=8, show_default=True, type=click.IntRange(1, MAX_K))
@click.option("--hop", default=1, show_default=True, type=click.IntRange(0, MAX_HOP))
@click.pass_context
def query(ctx: click.Context, q: str, k: int, hop: int, **source: Any) -> None:
    """Semantic query with graph expansion."""
    with open_kg(ctx.obj["root"], **source) as kg, usage_errors():
        try:
            result = kg.query(q, k=k, hop=hop)
        except FileNotFoundError as exc:
            raise click.ClickException(str(exc)) from exc
        result.print_summary()


@cli.command("path")
@source_options
@click.option("--from", "src", required=True, help="Source spec: cell type, neuron or label.")
@click.option("--to", "dst", required=True, help="Target spec.")
@click.pass_context
def path(ctx: click.Context, src: str, dst: str, **source: Any) -> None:
    """Strongest synaptic path between two specs."""
    with open_kg(ctx.obj["root"], **source) as kg:
        with usage_errors():
            res = kg.strongest_path(src, dst)
        if res is None:
            click.echo(f"no path from {src} to {dst}")
            sys.exit(1)
        click.echo(f"strength {res.strength:.4g}, net sign {res.net_sign:+d}")
        for h in res.hops:
            n = kg.store.node(h.node_id) or {}
            tag = n.get("qualname") or h.node_id
            if h.syn_count:
                click.echo(
                    f"  -> {tag}  ({h.syn_count} syn, {h.fraction:.1%} of input, sign {h.sign:+d})"
                )
            else:
                click.echo(f"  {tag}")


@cli.command("cone")
@source_options
@click.argument("spec")
@click.option("--hops", default=1, show_default=True, type=click.IntRange(0, MAX_HOP))
@click.option("--direction", default="down", show_default=True, type=click.Choice(["down", "up"]))
@click.option(
    "--limit",
    default=20,
    show_default=True,
    type=click.IntRange(min=1),
    help="Neurons listed per hop.",
)
@click.pass_context
def cone(
    ctx: click.Context, spec: str, hops: int, direction: str, limit: int, **source: Any
) -> None:
    """Downstream or upstream cone of a spec."""
    with open_kg(ctx.obj["root"], **source) as kg:
        with usage_errors():
            reached = kg.cone(spec, hops=hops, min_syn=source["min_syn"], direction=direction)
        by_hop: dict[int, list[str]] = {}
        for nid, h in reached.items():
            n = kg.store.node(nid) or {}
            by_hop.setdefault(h, []).append(n.get("qualname") or nid)
        for h in sorted(by_hop):
            click.echo(f"hop {h}: {len(by_hop[h])} neurons")
            for q in sorted(by_hop[h])[:limit]:
                click.echo(f"  {q}")
