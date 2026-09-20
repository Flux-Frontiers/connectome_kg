"""ConnectomeKG: the KGModule for connectomes."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from kg_utils.extractor import KGExtractor
from kg_utils.pipeline import KGModule
from kg_utils.specs import QueryResult, SnippetPack

from connectomekg.extractor import DEFAULT_RELS, EDGE_KINDS, NODE_KINDS, ConnectomeExtractor
from connectomekg.neuroglancer import SPEC_COLORS, neuroglancer_url
from connectomekg.paths import InfluenceResult, PathResult, SynapseGraph
from connectomekg.readers.codex import read_codex
from connectomekg.readers.synthetic import synthetic_tables
from connectomekg.schema import FAFB_783, ConnectomeTables, DatasetInfo
from connectomekg.validation import (
    MAX_HOP,
    MAX_K,
    MAX_LIMIT,
    MAX_MAX_NODES,
    MAX_MIN_SYN,
    bounded_int,
    normalize_node_id,
    normalize_spec,
    require_choice,
    require_query,
)

_KIND_PRIORITY = {
    "cell_type": 0,
    "neuropil": 1,
    "neuron": 2,
    "ontology_term": 3,
    "label": 4,
    "taxon": 5,
    "hemilineage": 6,
    "nerve": 7,
    "connectivity_tag": 8,
    "column": 9,
    "dataset": 10,
}


class ConnectomeKG(KGModule):
    """Knowledge graph over one connectome release.

    :param repo_root: Directory that owns the ``.connectomekg/`` artefacts.
    :param data_dir: Codex release directory (``source="codex"``).
    :param source: ``"codex"`` or ``"synthetic"``.
    :param dataset: Provenance record; defaults to FAFB v783 for codex.
    :param n_neurons: Synthetic size (``source="synthetic"``).
    :param seed: Synthetic seed.
    :param embed_neurons: Also embed neuron nodes (off by default, see plan 4.3).
    :param min_syn: Drop connections below this synapse count at extraction.
    :param connections_file: Name of the connections table inside ``data_dir``;
        omit it to auto-detect whichever one the download contains.
    :param tables: Pre-loaded tables; overrides ``source`` and ``data_dir``.
    :param progress: Called with a short message at each extraction stage;
        ``None`` (the default) keeps the build silent.
    """

    _default_dir = ".connectomekg"

    def __init__(
        self,
        repo_root: str | Path,
        *,
        data_dir: str | Path | None = None,
        source: str = "codex",
        dataset: DatasetInfo | None = None,
        n_neurons: int = 1000,
        seed: int = 1,
        embed_neurons: bool = False,
        min_syn: int = 1,
        connections_file: str | None = None,
        tables: ConnectomeTables | None = None,
        progress: Callable[[str], None] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(repo_root, **kwargs)
        self.data_dir = Path(data_dir) if data_dir else None
        self.source = source
        self.dataset = dataset
        self.n_neurons = n_neurons
        self.seed = seed
        self.embed_neurons = embed_neurons
        self.min_syn = min_syn
        self.connections_file = connections_file
        self._tables = tables
        self.progress = progress
        self._graph: SynapseGraph | None = None

    def __enter__(self) -> ConnectomeKG:
        # KGModule.__enter__ is typed as the base class; narrow it for callers.
        return self

    # ------------------------------------------------------------ contract
    def kind(self) -> str:
        return "connectome"

    def tables(self) -> ConnectomeTables:
        """Load (once) the normalised tables for the configured source."""
        if self._tables is None:
            if self.source == "synthetic":
                self._tables = synthetic_tables(self.n_neurons, self.seed)
            elif self.source == "codex":
                if self.data_dir is None:
                    raise ValueError("source='codex' needs data_dir")
                self._tables = read_codex(
                    self.data_dir,
                    self.dataset or FAFB_783,
                    connections_file=self.connections_file,
                )
            else:
                raise ValueError(f"unknown source {self.source!r}")
            if self.dataset is not None and self._tables.dataset != self.dataset:
                self._tables.dataset = self.dataset
        return self._tables

    def make_extractor(self) -> KGExtractor:
        return ConnectomeExtractor(
            self.repo_root,
            {
                "tables": self.tables,  # called on first use, not here
                "embed_neurons": self.embed_neurons,
                "min_syn": self.min_syn,
                "progress": self.progress,
            },
        )

    def _kind_priority(self, kind: str) -> int:
        return _KIND_PRIORITY.get(kind, 99)

    def query(
        self,
        q: str,
        *,
        k: int = 8,
        hop: int = 1,
        rels: tuple[str, ...] = DEFAULT_RELS,
        **kw: Any,
    ) -> QueryResult:
        """Semantic query with graph expansion, validated at the boundary.

        :param q: Natural-language query, at most 500 characters.
        :param k: Seed hits, 1-100.
        :param hop: Expansion hops, 0-5.
        :param rels: Relations to expand along.
        :return: Ranked nodes and edges.
        :raises ValueError: On an out-of-range argument.
        :raises FileNotFoundError: When the vector index has not been built.
        """
        q, k, hop = self._check_search(q, k, hop, kw)
        return super().query(q, k=k, hop=hop, rels=rels, **kw)

    def pack(
        self,
        q: str,
        *,
        k: int = 8,
        hop: int = 1,
        rels: tuple[str, ...] = DEFAULT_RELS,
        **kw: Any,
    ) -> SnippetPack:
        """Semantic query returned as a Markdown pack, validated at the boundary.

        :param q: Natural-language query, at most 500 characters.
        :param k: Seed hits, 1-100.
        :param hop: Expansion hops, 0-5.
        :param rels: Relations to expand along.
        :return: The pack.
        :raises ValueError: On an out-of-range argument.
        :raises FileNotFoundError: When the vector index has not been built.
        """
        q, k, hop = self._check_search(q, k, hop, kw)
        return super().pack(q, k=k, hop=hop, rels=rels, **kw)

    def _check_search(self, q: str, k: int, hop: int, kw: dict[str, Any]) -> tuple[str, int, int]:
        q = require_query(q)
        k = bounded_int("k", k, 1, MAX_K)
        hop = bounded_int("hop", hop, 0, MAX_HOP)
        if kw.get("max_nodes") is not None:
            kw["max_nodes"] = bounded_int("max_nodes", kw["max_nodes"], 1, MAX_MAX_NODES)
        if not Path(self.vectors_path).exists():
            raise FileNotFoundError(
                f"no vector index at {self.vectors_path}: semantic search needs a build "
                "without --no-index and the semantic extra"
            )
        return q, k, hop

    # --------------------------------------------------------- navigation
    @property
    def graph(self) -> SynapseGraph:
        """Neuron-level synapse graph of the built store (lazy, cached on disk)."""
        if self._graph is None:
            self._graph = SynapseGraph.from_store(self.store, cache_for=self.db_path)
        return self._graph

    def neurons_of(self, spec: str) -> list[str]:
        """Resolve a cell type name, a root id, a neuron node id, or a label regex.

        :param spec: ``"LC4"``, ``"720575940612345678"``, a ``connectome:...:n:`` id,
            or ``"label:<regex>"``.
        :return: Neuron node ids, possibly empty.
        :raises ValueError: If the spec is empty, too long, or a bad ``label:`` pattern.
        """
        spec = normalize_spec(spec)
        con = self.store.con
        if spec.startswith("connectome:") and ":n:" in spec:
            return [spec] if self.store.node(spec) else []
        if spec.isdigit():
            rows = con.execute(
                "SELECT id FROM nodes WHERE kind='neuron' AND id LIKE ?", (f"%:n:{spec}",)
            ).fetchall()
            return [r[0] for r in rows]
        if spec.startswith("label:"):
            pat = re.compile(spec[6:], re.IGNORECASE)
            # Match the distinct label texts first (thousands), then fetch only
            # their edges, rather than running the pattern over every LABELED row.
            labels = [
                lid
                for lid, text in con.execute("SELECT id, qualname FROM nodes WHERE kind='label'")
                if pat.search(text or "")
            ]
            found: set[str] = set()
            for lid in labels:
                found.update(
                    r[0]
                    for r in con.execute(
                        "SELECT src FROM edges WHERE rel='LABELED' AND dst=?", (lid,)
                    )
                )
            return sorted(found)
        rows = con.execute(
            "SELECT e.src FROM edges e JOIN nodes t ON t.id = e.dst "
            "WHERE e.rel='INSTANCE_OF' AND t.kind='cell_type' AND t.name = ?",
            (spec,),
        ).fetchall()
        return sorted(r[0] for r in rows)

    def strongest_path(self, source: str, target: str) -> PathResult | None:
        """Strongest synaptic path between two specs (see :meth:`neurons_of`)."""
        # Resolve (and so validate) both specs before loading the synapse graph.
        sources, targets = self.neurons_of(source), self.neurons_of(target)
        return self.graph.strongest_path(sources, targets)

    def influence(
        self,
        source: str,
        target: str | None = None,
        *,
        hops: int = 3,
        signed: bool = True,
        limit: int = 20,
    ) -> InfluenceResult:
        """Effective connectivity: how much one population drives another, hop by hop.

        A value is the share of the receiving neuron's input synapses that the
        source drives, averaged over the receiving neurons, so 0.15 reads as
        "the average target gets 15 % of its input from the source". Signed,
        a negative value is net inhibition, and two routes of opposite sign
        cancel -- which is what makes this different from counting paths.

        At hop 1 and unsigned, the value is exactly the source's share of the
        target's input synapses. Signed, a source neuron whose transmitter is
        unresolved contributes nothing, so the signed value is the lower of the
        two by however much of the population that is.

        :param source: See :meth:`neurons_of`.
        :param target: See :meth:`neurons_of`; ``None`` ranks cell types
            instead of measuring one population.
        :param hops: Hops to propagate, 1-5.
        :param signed: Apply transmitter signs.
        :param limit: Cell types listed per hop, 1-500.
        :return: :class:`InfluenceResult`.
        :raises ValueError: On an out-of-range argument or an unresolvable spec.
        """
        hops = bounded_int("hops", hops, 1, MAX_HOP)
        limit = bounded_int("limit", limit, 1, MAX_LIMIT)
        sources = self.neurons_of(source)
        targets = self.neurons_of(target) if target is not None else []
        graph = self.graph
        per_hop = graph.influence(sources, hops=hops, signed=signed)

        onto: list[float] = []
        if target is not None:
            columns = [graph.index[t] for t in targets if t in graph.index]
            # Mean, not sum: see InfluenceResult. An empty target set averages
            # to nothing rather than dividing by zero.
            onto = [float(row[columns].mean()) if columns else 0.0 for row in per_hop]

        types = self._types_by_index(graph.ids)
        ranked: list[list[tuple[str, float]]] = []
        for row in per_hop:
            totals: dict[str, list[float]] = {}
            for name, value in zip(types, row, strict=True):
                if name:
                    totals.setdefault(name, []).append(float(value))
            means = [(n, sum(v) / len(v)) for n, v in totals.items()]
            means.sort(key=lambda nv: (-abs(nv[1]), nv[0]))
            ranked.append([nv for nv in means[:limit] if nv[1] != 0.0])

        return InfluenceResult(
            source=source,
            target=target,
            hops=hops,
            signed=signed,
            n_sources=len(sources),
            n_targets=len(targets),
            onto=onto,
            ranked=ranked,
        )

    def _types_by_index(self, ids: list[str]) -> list[str]:
        """Each neuron's cell type, aligned to ``ids``, empty where untyped."""
        rows = dict(
            self.store.con.execute(
                "SELECT id, json_extract(metadata,'$.cell_type') FROM nodes WHERE kind='neuron'"
            )
        )
        return [str(rows.get(i) or "") for i in ids]

    def cone(self, spec: str, *, hops: int = 1, min_syn: int = 1, direction: str = "down"):
        """Downstream or upstream cone of a spec, as ``{node_id: hop}``.

        :param spec: See :meth:`neurons_of`.
        :param hops: Depth, 0-5.
        :param min_syn: Synapse threshold per edge, 1-10000.
        :param direction: ``"down"`` or ``"up"``.
        :raises ValueError: On an out-of-range argument.
        """
        hops = bounded_int("hops", hops, 0, MAX_HOP)
        min_syn = bounded_int("min_syn", min_syn, 1, MAX_MIN_SYN)
        direction = require_choice("direction", direction, ("down", "up"))
        seeds = self.neurons_of(spec)
        return self.graph.cone(seeds, hops=hops, min_syn=min_syn, direction=direction)

    def neuroglancer_link(self, specs: list[str], *, limit: int = 200) -> dict[str, Any]:
        """A Neuroglancer URL showing each spec's neurons as meshes, one colour per spec.

        :param specs: One to seven specs (see :meth:`neurons_of`).
        :param limit: Neurons shown per spec, 1-500; ``count`` is always the full total.
        :return: ``{"url", "specs": [{spec, count, shown, color}]}``.
        :raises ValueError: On an out-of-range argument, a dataset with no
            public segmentation, or specs that match no neurons.
        """
        if isinstance(specs, str) or not specs:
            raise ValueError("specs must be a non-empty list of specs")
        bounded_int("specs", len(specs), 1, len(SPEC_COLORS))
        limit = bounded_int("limit", limit, 1, MAX_LIMIT)
        row = self.store.con.execute("SELECT qualname FROM nodes WHERE kind='dataset'").fetchone()
        dataset_id = row[0] if row else ""
        groups, found = [], []
        for i, spec in enumerate(specs):
            ids = self.neurons_of(spec)
            groups.append([int(nid.rsplit(":", 1)[1]) for nid in ids[:limit]])
            found.append(
                {
                    "spec": spec,
                    "count": len(ids),
                    "shown": len(groups[-1]),
                    "color": SPEC_COLORS[i],
                }
            )
        if not any(groups):
            raise ValueError(f"no neurons match {', '.join(specs)}")
        return {"url": neuroglancer_url(dataset_id, groups), "specs": found}

    def describe(self, node_id: str) -> dict[str, Any] | None:
        """A node with its metadata decoded.

        :param node_id: Node id; surrounding backticks, quotes and whitespace are stripped.
        :raises ValueError: If the id is empty or too long.
        """
        return self.store.node(normalize_node_id(node_id))

    def cell_type_node(self, name: str) -> dict[str, Any]:
        """The node for a cell type, by exact name.

        :param name: Cell type name, e.g. ``"LC4"``.
        :return: The node dict.
        :raises ValueError: If there is no such type; the message names types
            whose names contain it, so a near miss is one step from fixed.
        """
        name = normalize_spec(name)
        row = self.store.con.execute(
            "SELECT id FROM nodes WHERE kind='cell_type' AND name=?", (name,)
        ).fetchone()
        node = self.store.node(row[0]) if row else None
        if node is not None:
            return node
        near = [n["name"] for n in self.find_nodes(name, kind="cell_type", limit=8)]
        hint = f"; types containing it: {', '.join(near)}" if near else ""
        raise ValueError(f"no cell type named {name!r}{hint}")

    def type_partners(
        self, cell_type: str, *, direction: str = "down", limit: int = 20
    ) -> list[dict[str, Any]]:
        """A cell type's partner types, strongest first.

        :param cell_type: Cell type name, e.g. ``"LC4"``.
        :param direction: ``"down"`` for types it synapses onto, ``"up"`` for its inputs.
        :param limit: Partners returned, 1-500.
        :return: Dicts with ``cell_type``, ``syn_count``, ``n_pairs`` and ``nt_type``.
        :raises ValueError: On an out-of-range argument.
        """
        name = normalize_spec(cell_type)
        direction = require_choice("direction", direction, ("down", "up"))
        limit = bounded_int("limit", limit, 1, MAX_LIMIT)
        tid = next(
            (
                r[0]
                for r in self.store.con.execute(
                    "SELECT id FROM nodes WHERE kind='cell_type' AND name=?", (name,)
                )
            ),
            None,
        )
        if tid is None:
            return []
        mine, other = ("src", "dst") if direction == "down" else ("dst", "src")
        rows = self.store.con.execute(
            f"SELECT n.name, json_extract(e.evidence,'$.syn_count') AS syn, "
            f"json_extract(e.evidence,'$.n_pairs'), json_extract(e.evidence,'$.nt_type') "
            f"FROM edges e JOIN nodes n ON n.id = e.{other} "
            f"WHERE e.{mine} = ? AND e.rel = 'TYPE_SYNAPSES_TO' ORDER BY syn DESC LIMIT ?",
            (tid, limit),
        ).fetchall()
        return [
            {"cell_type": r[0], "syn_count": r[1], "n_pairs": r[2], "nt_type": r[3]} for r in rows
        ]

    def node_edges(
        self, node_id: str, *, rel: str = "", direction: str = "out", limit: int = 50
    ) -> list[dict[str, Any]]:
        """Edges at one node, with the node at the other end.

        :param node_id: Node id.
        :param rel: One relation from ``EDGE_KINDS``, or ``""`` for all.
        :param direction: ``"out"`` (node is the source) or ``"in"``.
        :param limit: Edges returned, 1-500.
        :return: Dicts with ``rel``, ``node`` (id), ``name``, ``kind`` and ``evidence``.
        :raises ValueError: On an out-of-range argument or unknown relation.
        """
        nid = normalize_node_id(node_id)
        if rel:
            require_choice("rel", rel, EDGE_KINDS)
        direction = require_choice("direction", direction, ("out", "in"))
        limit = bounded_int("limit", limit, 1, MAX_LIMIT)
        mine, other = ("src", "dst") if direction == "out" else ("dst", "src")
        sql = (
            f"SELECT e.rel, e.{other}, n.name, n.kind, e.evidence FROM edges e "
            f"LEFT JOIN nodes n ON n.id = e.{other} WHERE e.{mine} = ?"
        )
        args: list[Any] = [nid]
        if rel:
            sql += " AND e.rel = ?"
            args.append(rel)
        sql += " LIMIT ?"
        args.append(limit)
        return [
            {
                "rel": r[0],
                "node": r[1],
                "name": r[2],
                "kind": r[3],
                "evidence": json.loads(r[4]) if r[4] else None,
            }
            for r in self.store.con.execute(sql, args)
        ]

    def find_nodes(self, name: str, *, kind: str = "", limit: int = 20) -> list[dict[str, Any]]:
        """Nodes whose name contains a string, case-insensitively.

        :param name: Substring to look for, e.g. ``"DNp"``.
        :param kind: One kind from ``NODE_KINDS``, or ``""`` for all.
        :param limit: Nodes returned, 1-500.
        :return: Dicts with ``id``, ``kind``, ``name`` and ``qualname``.
        :raises ValueError: On an out-of-range argument or unknown kind.
        """
        needle = require_query(name)
        if kind:
            require_choice("kind", kind, NODE_KINDS)
        limit = bounded_int("limit", limit, 1, MAX_LIMIT)
        sql = "SELECT id, kind, name, qualname FROM nodes WHERE instr(lower(name), lower(?)) > 0"
        args: list[Any] = [needle]
        if kind:
            sql += " AND kind = ?"
            args.append(kind)
        sql += " ORDER BY length(name), name LIMIT ?"
        args.append(limit)
        return [
            {"id": r[0], "kind": r[1], "name": r[2], "qualname": r[3]}
            for r in self.store.con.execute(sql, args)
        ]

    # ------------------------------------------------------------ analyze
    def analyze(self) -> str:
        """Markdown report: counts, hubs, type-level rich club, neuropil flow."""
        try:
            return self._analyze()
        except Exception as exc:  # noqa: BLE001 -- contract: never raise
            return f"# ConnectomeKG analysis\n\nAnalysis failed: {exc}\n"

    def _analyze(self) -> str:
        con = self.store.con
        s = self.store.stats()
        ds = con.execute("SELECT name, metadata FROM nodes WHERE kind='dataset'").fetchone()
        meta = json.loads(ds[1]) if ds and ds[1] else {}
        out = [f"# ConnectomeKG analysis: {ds[0] if ds else 'unknown dataset'}", ""]
        out.append(f"Licence: {meta.get('licence', '?')}. {meta.get('citation', '')}")
        out.append("")
        out.append("## Counts")
        out.append("")
        out.append("| kind | nodes |")
        out.append("|---|---|")
        for k, v in sorted(s["node_counts"].items()):
            out.append(f"| {k} | {v} |")
        out.append("")
        out.append("| relation | edges |")
        out.append("|---|---|")
        for k, v in sorted(s["edge_counts"].items()):
            out.append(f"| {k} | {v} |")
        out.append("")

        rows = con.execute(
            "SELECT name, qualname, json_extract(metadata,'$.n_out_syn'), "
            "json_extract(metadata,'$.n_in_syn') FROM nodes WHERE kind='neuron' "
            "ORDER BY json_extract(metadata,'$.n_out_syn') DESC LIMIT 10"
        ).fetchall()
        out.append("## Hub neurons by output synapses")
        out.append("")
        out.append("| type | neuron | out | in |")
        out.append("|---|---|---|---|")
        for name, qn, o, i in rows:
            out.append(f"| {name} | {qn} | {o} | {i} |")
        out.append("")

        rows = con.execute(
            "SELECT a.name, b.name, json_extract(e.evidence,'$.syn_count'), "
            "json_extract(e.evidence,'$.n_pairs') FROM edges e "
            "JOIN nodes a ON a.id=e.src JOIN nodes b ON b.id=e.dst "
            "WHERE e.rel='TYPE_SYNAPSES_TO' ORDER BY 3 DESC LIMIT 15"
        ).fetchall()
        out.append("## Strongest type-to-type connections")
        out.append("")
        out.append("| from | to | synapses | pairs |")
        out.append("|---|---|---|---|")
        for a, b, syn, n in rows:
            out.append(f"| {a} | {b} | {syn} | {n} |")
        out.append("")

        rows = con.execute(
            "SELECT name, json_extract(metadata,'$.n_neurons'), json_extract(metadata,'$.n_synapses') "
            "FROM nodes WHERE kind='neuropil' ORDER BY 3 DESC"
        ).fetchall()
        out.append("## Neuropils by synapses")
        out.append("")
        out.append("| neuropil | neurons | synapses |")
        out.append("|---|---|---|")
        for name, n, syn in rows:
            out.append(f"| {name} | {n} | {syn} |")
        out.append("")

        n_neu = s["node_counts"].get("neuron", 0)
        typed = con.execute(
            "SELECT COUNT(*) FROM nodes WHERE kind='neuron' AND "
            "json_extract(metadata,'$.cell_type') != ''"
        ).fetchone()[0]
        signed = con.execute(
            "SELECT COUNT(*) FROM nodes WHERE kind='neuron' AND json_extract(metadata,'$.sign') != 0"
        ).fetchone()[0]
        labelled = con.execute(
            "SELECT COUNT(DISTINCT src) FROM edges WHERE rel='LABELED'"
        ).fetchone()[0]
        out.append("## Coverage")
        out.append("")
        if n_neu:
            out.append(f"- neurons with a cell type: {typed} of {n_neu} ({typed / n_neu:.1%})")
            out.append(
                f"- neurons with a resolved sign: {signed} of {n_neu} ({signed / n_neu:.1%})"
            )
            out.append(
                f"- neurons with a community label: {labelled} of {n_neu} ({labelled / n_neu:.1%})"
            )
            layers = (
                ("a visual family", "json_extract(metadata,'$.visual_family') != ''"),
                ("a visual column", "json_extract(metadata,'$.column') != ''"),
                ("an ontology term", "json_array_length(metadata,'$.fbbt') > 0"),
                ("a cable length", "json_extract(metadata,'$.length_nm') IS NOT NULL"),
            )
            for what, cond in layers:
                k = con.execute(
                    f"SELECT COUNT(*) FROM nodes WHERE kind='neuron' AND {cond}"
                ).fetchone()[0]
                out.append(f"- neurons with {what}: {k} of {n_neu} ({k / n_neu:.1%})")
        out.append("")
        return "\n".join(out)
