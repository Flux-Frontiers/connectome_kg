"""``connkg query``, ``path``, ``cone`` and ``link`` -- asking the graph things."""

from __future__ import annotations

import sys
from typing import Any

import click

from connectomekg.cli.group import cli
from connectomekg.cli.options import MAX_HOP, MAX_K, open_kg, source_options, usage_errors
from connectomekg.validation import MAX_LIMIT


@cli.command("query")
@source_options
@click.argument("q")
@click.option("--k", default=8, show_default=True, type=click.IntRange(1, MAX_K))
@click.option("--hop", default=1, show_default=True, type=click.IntRange(0, MAX_HOP))
@click.pass_context
def query(ctx: click.Context, q: str, k: int, hop: int, **source: Any) -> None:
    """Semantic query with graph expansion."""
    with open_kg(ctx.obj["root"], dataset=ctx.obj["dataset"], **source) as kg, usage_errors():
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
    with open_kg(ctx.obj["root"], dataset=ctx.obj["dataset"], **source) as kg:
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
    with open_kg(ctx.obj["root"], dataset=ctx.obj["dataset"], **source) as kg:
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


@cli.command("influence")
@source_options
@click.option("--from", "source_spec", required=True, help="Source spec.")
@click.option("--to", "target_spec", default=None, help="Target spec; omit to rank cell types.")
@click.option("--hops", default=3, show_default=True, type=click.IntRange(1, MAX_HOP))
@click.option(
    "--unsigned",
    is_flag=True,
    help="Treat every synapse as excitatory instead of applying transmitter signs.",
)
@click.option(
    "--limit",
    default=20,
    show_default=True,
    type=click.IntRange(1, MAX_LIMIT),
    help="Cell types listed per hop.",
)
@click.pass_context
def influence(
    ctx: click.Context,
    source_spec: str,
    target_spec: str | None,
    hops: int,
    unsigned: bool,
    limit: int,
    **source: Any,
) -> None:
    """Effective connectivity: how much one population drives another, hop by hop.

    A value is the share of the receiving neuron's input synapses the source
    drives, averaged over the receiving neurons, so 0.15 reads as "the average
    target gets 15% of its input from the source". Signed by default, so a
    negative value is net inhibition and two routes of opposite sign cancel --
    which is what this answers that counting paths does not.

    Unlike `connkg path`, which finds one strongest route, this sums every
    route of the given length at once.
    """
    with open_kg(ctx.obj["root"], dataset=ctx.obj["dataset"], **source) as kg, usage_errors():
        result = kg.influence(source_spec, target_spec, hops=hops, signed=not unsigned, limit=limit)
        click.echo(str(result))


@cli.command("link")
@source_options
@click.argument("specs", nargs=-1, required=True)
@click.option(
    "--limit",
    default=200,
    show_default=True,
    type=click.IntRange(1, MAX_LIMIT),
    help="Neurons shown per spec.",
)
@click.pass_context
def link(ctx: click.Context, specs: tuple[str, ...], limit: int, **source: Any) -> None:
    """Neuroglancer URL showing each spec's neurons as meshes, one colour per spec."""
    with open_kg(ctx.obj["root"], dataset=ctx.obj["dataset"], **source) as kg, usage_errors():
        res = kg.neuroglancer_link(list(specs), limit=limit)
    for s in res["specs"]:
        more = f", first {s['shown']} shown" if s["shown"] < s["count"] else ""
        click.echo(f"{s['color']}  {s['spec']}: {s['count']} neurons{more}", err=True)
    click.echo(res["url"])
