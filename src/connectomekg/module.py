"""ConnectomeKG: the KGModule for connectomes."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from kg_utils.extractor import KGExtractor
from kg_utils.pipeline import KGModule
from kg_utils.specs import QueryResult, SnippetPack

from connectomekg.extractor import DEFAULT_RELS, ConnectomeExtractor
from connectomekg.paths import PathResult, SynapseGraph
from connectomekg.readers.codex import read_codex
from connectomekg.readers.synthetic import synthetic_tables
from connectomekg.schema import FAFB_783, ConnectomeTables, DatasetInfo

_KIND_PRIORITY = {
    "cell_type": 0,
    "neuropil": 1,
    "neuron": 2,
    "label": 3,
    "taxon": 4,
    "hemilineage": 5,
    "dataset": 6,
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
        self._graph: SynapseGraph | None = None

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
            {"tables": self.tables(), "embed_neurons": self.embed_neurons, "min_syn": self.min_syn},
        )

    def _kind_priority(self, kind: str) -> int:
        return _KIND_PRIORITY.get(kind, 99)

    def query(self, q: str, *, rels: tuple[str, ...] = DEFAULT_RELS, **kw: Any) -> QueryResult:
        return super().query(q, rels=rels, **kw)

    def pack(self, q: str, *, rels: tuple[str, ...] = DEFAULT_RELS, **kw: Any) -> SnippetPack:
        return super().pack(q, rels=rels, **kw)

    # --------------------------------------------------------- navigation
    @property
    def graph(self) -> SynapseGraph:
        """Neuron-level synapse graph of the built store (lazy)."""
        if self._graph is None:
            self._graph = SynapseGraph.from_store(self.store)
        return self._graph

    def neurons_of(self, spec: str) -> list[str]:
        """Resolve a cell type name, a root id, a neuron node id, or a label regex.

        :param spec: ``"LC4"``, ``"720575940612345678"``, a ``connectome:...:n:`` id,
            or ``"label:<regex>"``.
        :return: Neuron node ids, possibly empty.
        """
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
            rows = con.execute(
                "SELECT e.src, n.qualname FROM edges e JOIN nodes n ON n.id = e.dst "
                "WHERE e.rel='LABELED'"
            ).fetchall()
            return sorted({src for src, text in rows if pat.search(text or "")})
        rows = con.execute(
            "SELECT e.src FROM edges e JOIN nodes t ON t.id = e.dst "
            "WHERE e.rel='INSTANCE_OF' AND t.kind='cell_type' AND t.name = ?",
            (spec,),
        ).fetchall()
        return sorted(r[0] for r in rows)

    def strongest_path(self, source: str, target: str) -> PathResult | None:
        """Strongest synaptic path between two specs (see :meth:`neurons_of`)."""
        return self.graph.strongest_path(self.neurons_of(source), self.neurons_of(target))

    def cone(self, spec: str, *, hops: int = 1, min_syn: int = 1, direction: str = "down"):
        """Downstream or upstream cone of a spec, as ``{node_id: hop}``."""
        return self.graph.cone(
            self.neurons_of(spec), hops=hops, min_syn=min_syn, direction=direction
        )

    def describe(self, node_id: str) -> dict[str, Any] | None:
        """A node with its metadata decoded."""
        return self.store.node(node_id)

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
        out.append("")
        return "\n".join(out)
