"""connectome-kg command line."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from connectomekg.manifest import verify_dir
from connectomekg.module import ConnectomeKG
from connectomekg.readers.synthetic import synthetic_tables, write_codex_dir
from connectomekg.schema import FAFB_783, DatasetInfo


def _module(a: argparse.Namespace) -> ConnectomeKG:
    dataset = None
    if getattr(a, "dataset_id", None):
        dataset = DatasetInfo(
            dataset_id=a.dataset_id,
            name=a.dataset_id,
            version="",
            organism="",
            licence="",
            url="",
            citation="",
        )
        if a.dataset_id == "fafb783":
            dataset = FAFB_783
    return ConnectomeKG(
        a.root,
        data_dir=getattr(a, "data_dir", None),
        source=getattr(a, "source", "codex"),
        dataset=dataset,
        n_neurons=getattr(a, "n", 1000),
        seed=getattr(a, "seed", 1),
        embed_neurons=getattr(a, "embed_neurons", False),
        min_syn=getattr(a, "min_syn", 1),
    )


def cmd_fixture(a: argparse.Namespace) -> int:
    d = write_codex_dir(synthetic_tables(a.n, a.seed), a.out)
    print(f"wrote synthetic Codex release to {d}")
    return 0


def cmd_verify(a: argparse.Namespace) -> int:
    report = verify_dir(Path(a.data_dir), checksums=not a.no_checksums)
    print(report)
    return 0 if report.ok else 1


def cmd_build(a: argparse.Namespace) -> int:
    kg = _module(a)
    stats = kg.build_graph(wipe=a.wipe) if a.no_index else kg.build(wipe=a.wipe)
    print(stats)
    return 0


def cmd_stats(a: argparse.Namespace) -> int:
    for k, v in _module(a).store.stats().items():
        print(f"{k}: {v}")
    return 0


def cmd_analyze(a: argparse.Namespace) -> int:
    print(_module(a).analyze())
    return 0


def cmd_query(a: argparse.Namespace) -> int:
    _module(a).query(a.q, k=a.k, hop=a.hop).print_summary()
    return 0


def cmd_path(a: argparse.Namespace) -> int:
    kg = _module(a)
    res = kg.strongest_path(a.src, a.dst)
    if res is None:
        print(f"no path from {a.src} to {a.dst}")
        return 1
    print(f"strength {res.strength:.4g}, net sign {res.net_sign:+d}")
    for h in res.hops:
        n = kg.store.node(h.node_id) or {}
        tag = n.get("qualname") or h.node_id
        if h.syn_count:
            print(f"  -> {tag}  ({h.syn_count} syn, {h.fraction:.1%} of input, sign {h.sign:+d})")
        else:
            print(f"  {tag}")
    return 0


def cmd_cone(a: argparse.Namespace) -> int:
    kg = _module(a)
    reached = kg.cone(a.spec, hops=a.hops, min_syn=a.min_syn, direction=a.direction)
    by_hop: dict[int, list[str]] = {}
    for nid, h in reached.items():
        n = kg.store.node(nid) or {}
        by_hop.setdefault(h, []).append(n.get("qualname") or nid)
    for h in sorted(by_hop):
        print(f"hop {h}: {len(by_hop[h])} neurons")
        for q in sorted(by_hop[h])[: a.limit]:
            print(f"  {q}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="connectome-kg", description=__doc__)
    p.add_argument("--root", default=".", help="directory owning .connectomekg/")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("fixture", help="write a synthetic Codex-format release")
    s.add_argument("--out", required=True)
    s.add_argument("--n", type=int, default=1000)
    s.add_argument("--seed", type=int, default=1)
    s.set_defaults(fn=cmd_fixture)

    s = sub.add_parser("verify", help="check a Codex download against the v783 manifest")
    s.add_argument("--data-dir", required=True)
    s.add_argument("--no-checksums", action="store_true")
    s.set_defaults(fn=cmd_verify)

    def add_source(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--data-dir")
        sp.add_argument("--source", choices=["codex", "synthetic"], default="codex")
        sp.add_argument("--dataset-id", default=None)
        sp.add_argument("--n", type=int, default=1000)
        sp.add_argument("--seed", type=int, default=1)
        sp.add_argument("--min-syn", type=int, default=1)
        sp.add_argument("--embed-neurons", action="store_true")

    s = sub.add_parser("build", help="extract into SQLite (and the vector index)")
    add_source(s)
    s.add_argument("--wipe", action="store_true")
    s.add_argument("--no-index", action="store_true", help="skip the vector index")
    s.set_defaults(fn=cmd_build)

    for name, fn in (("stats", cmd_stats), ("analyze", cmd_analyze)):
        s = sub.add_parser(name)
        add_source(s)
        s.set_defaults(fn=fn)

    s = sub.add_parser("query", help="semantic query with graph expansion")
    add_source(s)
    s.add_argument("q")
    s.add_argument("--k", type=int, default=8)
    s.add_argument("--hop", type=int, default=1)
    s.set_defaults(fn=cmd_query)

    s = sub.add_parser("path", help="strongest synaptic path between two specs")
    add_source(s)
    s.add_argument("--from", dest="src", required=True)
    s.add_argument("--to", dest="dst", required=True)
    s.set_defaults(fn=cmd_path)

    s = sub.add_parser("cone", help="downstream or upstream cone of a spec")
    add_source(s)
    s.add_argument("spec")
    s.add_argument("--hops", type=int, default=1)
    s.add_argument("--direction", choices=["down", "up"], default="down")
    s.add_argument("--limit", type=int, default=20)
    s.set_defaults(fn=cmd_cone)

    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
