"""Turn :class:`ConnectomeTables` into the section 4 graph of the plan.

Node kinds: dataset, taxon, hemilineage, neuropil, cell_type, neuron, label.
Edge kinds: CONTAINS, MEMBER_OF, INNERVATES, INSTANCE_OF, IN_NEUROPIL, LABELED,
SYNAPSES_TO, TYPE_SYNAPSES_TO, MIRROR_OF, IN_DATASET.

Edge weight is not persisted by the store, so the synapse count lives in
``metadata["syn_count"]`` as well as in ``weight``.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from kg_utils.extractor import KGExtractor
from kg_utils.specs import EdgeSpec, NodeSpec

from connectomekg.describe import cell_type_docstring, neuron_docstring, neuropil_docstring
from connectomekg.neuropils import neuropil_full_name, split_neuropil
from connectomekg.schema import NT_SIGN, ConnectomeTables

NODE_KINDS = ("dataset", "taxon", "hemilineage", "neuropil", "cell_type", "neuron", "label")
EDGE_KINDS = (
    "CONTAINS",
    "MEMBER_OF",
    "INNERVATES",
    "INSTANCE_OF",
    "IN_NEUROPIL",
    "LABELED",
    "SYNAPSES_TO",
    "TYPE_SYNAPSES_TO",
    "MIRROR_OF",
    "IN_DATASET",
)
#: Relations a query expands along by default: structure plus the type-level wiring.
DEFAULT_RELS = ("CONTAINS", "INSTANCE_OF", "INNERVATES", "TYPE_SYNAPSES_TO", "LABELED")
#: Pairs between progress reports in the synapse loop, which dominates extraction.
_PROGRESS_EVERY = 250_000


def _s(v: Any) -> str:
    if v is None:
        return ""
    t = str(v).strip()
    return "" if t.lower() in ("nan", "none") else t


def _majority(series: pd.Series) -> str:
    vals = [v for v in series.map(_s) if v]
    if not vals:
        return ""
    return pd.Series(vals).value_counts().index[0]


class ConnectomeExtractor(KGExtractor):
    """Emit nodes and edges for one connectome.

    :param repo_path: Corpus root (unused for ids; kept for the SDK contract).
    :param config: ``tables`` (a :class:`ConnectomeTables`), optional
        ``embed_neurons`` (bool, default False), ``min_syn`` (int, default 1),
        ``top_k`` (int, partners listed per type, default 5), ``progress``
        (a callable taking one message string, default None for silence).
    """

    def __init__(self, repo_path: Path, config: dict[str, Any] | None = None) -> None:
        super().__init__(repo_path, config)
        self.tables: ConnectomeTables = self.config["tables"]
        self.embed_neurons: bool = bool(self.config.get("embed_neurons", False))
        self.min_syn: int = int(self.config.get("min_syn", 1))
        self.top_k: int = int(self.config.get("top_k", 5))
        self.progress: Callable[[str], None] | None = self.config.get("progress")
        self.prefix = f"connectome:{self.tables.dataset.dataset_id}"

    # ------------------------------------------------------------------ ids
    def dataset_id(self) -> str:
        return self.prefix

    def neuron_id(self, root_id: int) -> str:
        return f"{self.prefix}:n:{int(root_id)}"

    def type_id(self, name: str) -> str:
        return f"{self.prefix}:t:{name}"

    def neuropil_id(self, abbrev: str) -> str:
        return f"{self.prefix}:np:{abbrev}"

    def hemilineage_id(self, name: str) -> str:
        return f"{self.prefix}:hl:{name}"

    def taxon_id(self, *parts: str) -> str:
        return f"{self.prefix}:c:" + "/".join(parts)

    def label_id(self, text: str) -> str:
        h = hashlib.sha1(text.lower().encode("utf-8")).hexdigest()[:12]
        return f"{self.prefix}:l:{h}"

    # ------------------------------------------------------------ contract
    def node_kinds(self) -> list[str]:
        return list(NODE_KINDS)

    def edge_kinds(self) -> list[str]:
        return list(EDGE_KINDS)

    def meaningful_node_kinds(self) -> list[str]:
        kinds = ["cell_type", "neuropil", "hemilineage", "label", "taxon"]
        if self.embed_neurons:
            kinds.append("neuron")
        return kinds

    def coverage_metric(self, nodes: list[NodeSpec]) -> float:
        """Fraction of neurons with a cell type and a resolved transmitter sign."""
        neurons = [n for n in nodes if n.kind == "neuron"]
        if not neurons:
            return 0.0
        good = sum(
            1 for n in neurons if n.metadata.get("cell_type") and n.metadata.get("sign", 0) != 0
        )
        return good / len(neurons)

    # ------------------------------------------------------------- extract
    def extract(self) -> Iterator[NodeSpec | EdgeSpec]:
        t = self.tables
        ds = t.dataset
        neurons = t.neurons.copy()
        con = t.connections
        if self.min_syn > 1:
            con = con[con["syn_count"] >= self.min_syn]

        self._say(f"aggregating {len(con):,} connection rows over {len(neurons):,} neurons")
        sign = t.sign_of()
        neurons["sign"] = neurons["root_id"].map(sign).fillna(0).astype(int)
        for col in ("cell_type", "super_class", "class", "hemilineage", "side", "nt_type"):
            neurons[col] = neurons[col].map(_s)

        # Pair-level aggregation: one edge per (pre, post) with a neuropil breakdown.
        pairs = con.groupby(["pre", "post"], sort=False).agg(
            syn_count=("syn_count", "sum"), nt_type=("nt_type", "first")
        )
        by_np = con.groupby(["pre", "post", "neuropil"], sort=False)["syn_count"].sum()
        np_breakdown: dict[tuple[int, int], dict[str, int]] = {}
        for (pre, post, npil), s in by_np.items():
            np_breakdown.setdefault((pre, post), {})[npil] = int(s)

        # Per-neuron synapse totals and neuropil membership.
        out_syn = con.groupby("pre")["syn_count"].sum()
        in_syn = con.groupby("post")["syn_count"].sum()
        pre_np = con.groupby(["pre", "neuropil"])["syn_count"].sum()
        post_np = con.groupby(["post", "neuropil"])["syn_count"].sum()
        pre_np.index.names = post_np.index.names = ["root_id", "neuropil"]
        np_tot = pre_np.add(post_np, fill_value=0).astype(int)
        np_by_neuron: dict[int, list[tuple[str, int, int, int]]] = {}
        pre_d = pre_np.to_dict()
        post_d = post_np.to_dict()
        for (rid, npil), s in np_tot.items():
            np_by_neuron.setdefault(int(rid), []).append(
                (npil, int(s), int(pre_d.get((rid, npil), 0)), int(post_d.get((rid, npil), 0)))
            )
        for lst in np_by_neuron.values():
            lst.sort(key=lambda x: -x[1])

        labels_by_neuron: dict[int, list[str]] = {}
        for rid, text in zip(t.labels["root_id"], t.labels["text"], strict=True):
            labels_by_neuron.setdefault(int(rid), []).append(str(text))

        # ---------------------------------------------------------- dataset
        self._say("taxa, hemilineages, neuropils")
        yield NodeSpec(
            node_id=self.dataset_id(),
            kind="dataset",
            name=f"{ds.name} v{ds.version}",
            qualname=ds.dataset_id,
            source_path="",
            docstring=(
                f"{ds.name} version {ds.version}, {ds.organism}. {len(neurons)} neurons, "
                f"{len(pairs)} connected pairs, {int(con['syn_count'].sum())} synapses. "
                f"Licence {ds.licence}. {ds.citation}"
            ),
            metadata={
                "version": ds.version,
                "organism": ds.organism,
                "licence": ds.licence,
                "url": ds.url,
                "citation": ds.citation,
                "n_neurons": int(len(neurons)),
                "n_pairs": int(len(pairs)),
                "n_synapses": int(con["syn_count"].sum()),
            },
        )

        # ------------------------------------------------------------ taxa
        top_level: list[str] = []
        for sc, g in neurons.groupby("super_class", sort=True):
            if not sc:
                continue
            sc = str(sc)
            sid = self.taxon_id(sc)
            top_level.append(sid)
            yield NodeSpec(
                node_id=sid,
                kind="taxon",
                name=sc,
                qualname=sc,
                source_path="",
                docstring=f"Super class {sc.replace('_', ' ')}: {len(g)} neurons.",
                metadata={"level": "super_class", "n_neurons": int(len(g))},
            )
            for cls, gg in g.groupby("class", sort=True):
                if not cls:
                    continue
                cls = str(cls)
                cid = self.taxon_id(sc, cls)
                yield NodeSpec(
                    node_id=cid,
                    kind="taxon",
                    name=cls,
                    qualname=f"{sc}/{cls}",
                    source_path="",
                    docstring=(
                        f"Class {cls.replace('_', ' ')} within {sc.replace('_', ' ')}: "
                        f"{len(gg)} neurons."
                    ),
                    metadata={"level": "class", "super_class": sc, "n_neurons": int(len(gg))},
                )
                yield EdgeSpec(sid, cid, "CONTAINS")

        # ------------------------------------------------------ hemilineages
        for hl, g in neurons.groupby("hemilineage", sort=True):
            if not hl:
                continue
            hl = str(hl)
            hid = self.hemilineage_id(hl)
            top_level.append(hid)
            types = sorted({x for x in g["cell_type"] if x})
            yield NodeSpec(
                node_id=hid,
                kind="hemilineage",
                name=hl,
                qualname=hl,
                source_path="",
                docstring=(
                    f"Hemilineage {hl}: {len(g)} neurons, {len(types)} cell types"
                    + (": " + ", ".join(types[:12]) if types else "")
                    + "."
                ),
                metadata={"n_neurons": int(len(g)), "n_types": len(types)},
            )

        # --------------------------------------------------------- neuropils
        np_neurons = np_tot.groupby(level="neuropil").size()
        np_syn = con.groupby("neuropil")["syn_count"].sum()
        for abbrev in sorted(np_syn.index):
            nid = self.neuropil_id(abbrev)
            top_level.append(nid)
            base, side = split_neuropil(abbrev)
            yield NodeSpec(
                node_id=nid,
                kind="neuropil",
                name=abbrev,
                qualname=neuropil_full_name(abbrev),
                source_path="",
                docstring=neuropil_docstring(
                    abbrev, n_neurons=int(np_neurons.get(abbrev, 0)), n_synapses=int(np_syn[abbrev])
                ),
                metadata={
                    "base": base,
                    "side": side,
                    "n_neurons": int(np_neurons.get(abbrev, 0)),
                    "n_synapses": int(np_syn[abbrev]),
                },
            )

        # -------------------------------------------------------- cell types
        self._say("cell types")
        type_of = dict(zip(neurons["root_id"], neurons["cell_type"], strict=True))
        pairs_t = pairs.reset_index()
        pairs_t["pre_t"] = pairs_t["pre"].map(type_of)
        pairs_t["post_t"] = pairs_t["post"].map(type_of)
        typed = pairs_t[(pairs_t["pre_t"] != "") & (pairs_t["post_t"] != "")]
        type_pairs = typed.groupby(["pre_t", "post_t"], sort=False).agg(
            syn_count=("syn_count", "sum"),
            n_pairs=("syn_count", "size"),
            nt_type=("nt_type", "first"),
        )
        out_by_type: dict[str, list[tuple[str, int]]] = {}
        in_by_type: dict[str, list[tuple[str, int]]] = {}
        for (a, b), row in type_pairs.iterrows():
            out_by_type.setdefault(a, []).append((b, int(row["syn_count"])))
            in_by_type.setdefault(b, []).append((a, int(row["syn_count"])))
        for d in (out_by_type, in_by_type):
            for lst in d.values():
                lst.sort(key=lambda x: -x[1])

        for ct, g in neurons.groupby("cell_type", sort=True):
            if not ct:
                continue
            ct = str(ct)
            tid = self.type_id(ct)
            top_level.append(tid)
            sides = g["side"].str.upper().str[:1]
            n_l, n_r = int((sides == "L").sum()), int((sides == "R").sum())
            sc, cls, nt, hl = (
                _majority(g["super_class"]),
                _majority(g["class"]),
                _majority(g["nt_type"]),
                _majority(g["hemilineage"]),
            )
            npils: dict[str, int] = {}
            for rid in g["root_id"]:
                for npil, s, _, _ in np_by_neuron.get(int(rid), []):
                    npils[npil] = npils.get(npil, 0) + s
            top_np = sorted(npils, key=lambda k: -npils[k])[: self.top_k]
            labs = sorted(
                {lab for rid in g["root_id"] for lab in labels_by_neuron.get(int(rid), [])}
            )
            yield NodeSpec(
                node_id=tid,
                kind="cell_type",
                name=ct,
                qualname=ct,
                source_path="",
                docstring=cell_type_docstring(
                    ct,
                    n_left=n_l,
                    n_right=n_r,
                    super_class=sc,
                    cls=cls,
                    nt=nt,
                    hemilineage=hl,
                    top_out=out_by_type.get(ct, [])[: self.top_k],
                    top_in=in_by_type.get(ct, [])[: self.top_k],
                    neuropils=top_np,
                    labels=labs,
                ),
                metadata={
                    "n_neurons": int(len(g)),
                    "n_left": n_l,
                    "n_right": n_r,
                    "super_class": sc,
                    "class": cls,
                    "nt_type": nt,
                    "sign": NT_SIGN.get(nt, 0),
                    "hemilineage": hl,
                },
            )
            if sc:
                parent = self.taxon_id(sc, cls) if cls else self.taxon_id(sc)
                yield EdgeSpec(parent, tid, "CONTAINS")
            if hl:
                yield EdgeSpec(tid, self.hemilineage_id(hl), "MEMBER_OF")
            for npil in top_np:
                yield EdgeSpec(
                    tid,
                    self.neuropil_id(npil),
                    "INNERVATES",
                    weight=float(npils[npil]),
                    metadata={"syn_count": int(npils[npil])},
                )
            if n_l == 1 and n_r == 1:
                left = int(g.loc[sides == "L", "root_id"].iloc[0])
                right = int(g.loc[sides == "R", "root_id"].iloc[0])
                yield EdgeSpec(self.neuron_id(left), self.neuron_id(right), "MIRROR_OF")

        for (a, b), row in type_pairs.iterrows():
            yield EdgeSpec(
                self.type_id(a),
                self.type_id(b),
                "TYPE_SYNAPSES_TO",
                weight=float(row["syn_count"]),
                metadata={
                    "syn_count": int(row["syn_count"]),
                    "n_pairs": int(row["n_pairs"]),
                    "nt_type": _s(row["nt_type"]),
                },
            )

        # ----------------------------------------------------------- labels
        self._say(f"labels ({len(t.labels):,})")
        seen_labels: set[str] = set()
        for rid, text, user, aff, date in zip(
            t.labels["root_id"],
            t.labels["text"],
            t.labels["user"],
            t.labels["affiliation"],
            t.labels["date"],
            strict=True,
        ):
            lid = self.label_id(str(text))
            if lid not in seen_labels:
                seen_labels.add(lid)
                yield NodeSpec(
                    node_id=lid,
                    kind="label",
                    name=str(text)[:80],
                    qualname=str(text),
                    source_path="",
                    docstring=str(text),
                    metadata={"user": _s(user), "affiliation": _s(aff)},
                )
            yield EdgeSpec(
                self.neuron_id(int(rid)),
                lid,
                "LABELED",
                metadata={"user": _s(user), "affiliation": _s(aff), "date": _s(date)},
            )

        # ---------------------------------------------------------- neurons
        self._say(f"neurons ({len(neurons):,})")
        for row in neurons.to_dict("records"):
            rid = int(row["root_id"])
            nid = self.neuron_id(rid)
            nps = np_by_neuron.get(rid, [])
            n_in, n_out = int(in_syn.get(rid, 0)), int(out_syn.get(rid, 0))
            ct = row["cell_type"]
            yield NodeSpec(
                node_id=nid,
                kind="neuron",
                name=ct or str(rid),
                qualname=f"{ct or 'untyped'}/{row['side'] or '?'}/{rid}",
                source_path="",
                docstring=neuron_docstring(
                    row,
                    n_in=n_in,
                    n_out=n_out,
                    top_neuropils=[x[0] for x in nps[:3]],
                    labels=labels_by_neuron.get(rid, []),
                ),
                metadata={
                    "root_id": rid,
                    "side": row["side"],
                    "super_class": row["super_class"],
                    "class": row["class"],
                    "cell_type": ct,
                    "hemilineage": row["hemilineage"],
                    "nt_type": row["nt_type"],
                    "nt_score": _float_or_none(row.get("nt_score")),
                    "sign": int(row["sign"]),
                    "x": _float_or_none(row.get("x")),
                    "y": _float_or_none(row.get("y")),
                    "z": _float_or_none(row.get("z")),
                    "n_in_syn": n_in,
                    "n_out_syn": n_out,
                },
            )
            if ct:
                yield EdgeSpec(nid, self.type_id(ct), "INSTANCE_OF", metadata={"side": row["side"]})
            for npil, s, pre_s, post_s in nps:
                yield EdgeSpec(
                    nid,
                    self.neuropil_id(npil),
                    "IN_NEUROPIL",
                    weight=float(s),
                    metadata={"pre": pre_s, "post": post_s},
                )

        # ---------------------------------------------------------- synapses
        sign_d = dict(zip(neurons["root_id"], neurons["sign"], strict=True))
        n_pairs = len(pairs)
        self._say(f"synaptic pairs ({n_pairs:,})")
        for i, ((pre, post), row) in enumerate(pairs.iterrows(), 1):
            if i % _PROGRESS_EVERY == 0:
                self._say(f"  {i:,} / {n_pairs:,} pairs")
            s = int(row["syn_count"])
            yield EdgeSpec(
                self.neuron_id(int(pre)),
                self.neuron_id(int(post)),
                "SYNAPSES_TO",
                weight=float(s),
                metadata={
                    "syn_count": s,
                    "nt_type": _s(row["nt_type"]),
                    "sign": int(sign_d.get(pre, 0)),
                    "neuropils": np_breakdown.get((pre, post), {}),
                },
            )

        for nid in top_level:
            yield EdgeSpec(nid, self.dataset_id(), "IN_DATASET")
        self._say("extraction done; writing to SQLite (no progress from here)")

    def _say(self, message: str) -> None:
        if self.progress is not None:
            self.progress(message)


def _float_or_none(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(f) else f
