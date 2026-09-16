"""Normalised in-memory tables every reader produces and the extractor consumes.

Four tables, all pandas: neurons, connections, labels, and a dataset record.
Readers translate a release's files into this shape; nothing downstream knows
which release it came from.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

#: Presynaptic-neurotransmitter sign convention from Shiu et al. 2024
#: (Nature 634:210). Glutamate is inhibitory in Drosophila via GluCl-alpha.
EXCITATORY = ("ACH", "DA", "OCT", "SER")
INHIBITORY = ("GABA", "GLUT")
NT_SIGN: dict[str, int] = {nt: 1 for nt in EXCITATORY} | {nt: -1 for nt in INHIBITORY}

NEURON_COLUMNS = (
    "root_id",
    "side",
    "flow",
    "super_class",
    "class",
    "sub_class",
    "cell_type",
    "hemilineage",
    "nerve",
    "nt_type",
    "nt_score",
    "x",
    "y",
    "z",
)
CONNECTION_COLUMNS = ("pre", "post", "neuropil", "syn_count", "nt_type")
LABEL_COLUMNS = ("root_id", "text", "user", "affiliation", "date")


@dataclass(frozen=True)
class DatasetInfo:
    """Provenance for one connectome release.

    :param dataset_id: Short id used in node ids, e.g. ``fafb783``.
    :param name: Human name of the release.
    :param version: Release version string.
    :param organism: Organism and sex.
    :param licence: SPDX-style licence name.
    :param url: Where the release lives.
    :param citation: The paper(s) to cite.
    """

    dataset_id: str
    name: str
    version: str
    organism: str
    licence: str
    url: str
    citation: str


FAFB_783 = DatasetInfo(
    dataset_id="fafb783",
    name="FlyWire FAFB",
    version="783",
    organism="Drosophila melanogaster, adult female, whole brain",
    licence="CC-BY-NC-SA-4.0",
    url="https://codex.flywire.ai",
    citation=(
        "Dorkenwald et al. 2024 Nature 634:124 (doi:10.1038/s41586-024-07558-y); "
        "Schlegel et al. 2024 Nature 634:139 (doi:10.1038/s41586-024-07686-5); "
        "Eckstein et al. 2024 Cell 187:2574 (doi:10.1016/j.cell.2024.03.016)"
    ),
)


@dataclass
class ConnectomeTables:
    """The normalised tables for one connectome.

    :param dataset: Provenance record.
    :param neurons: One row per neuron, columns :data:`NEURON_COLUMNS`.
    :param connections: One row per (pre, post, neuropil), columns
        :data:`CONNECTION_COLUMNS`. ``pre`` and ``post`` are root ids.
    :param labels: One row per community annotation, columns :data:`LABEL_COLUMNS`.
    """

    dataset: DatasetInfo
    neurons: pd.DataFrame
    connections: pd.DataFrame
    labels: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=LABEL_COLUMNS))

    def validate(self) -> None:
        """Check column sets, id uniqueness and referential integrity.

        :raises ValueError: On any violation, naming it.
        """
        missing = set(NEURON_COLUMNS) - set(self.neurons.columns)
        if missing:
            raise ValueError(f"neurons table missing columns: {sorted(missing)}")
        missing = set(CONNECTION_COLUMNS) - set(self.connections.columns)
        if missing:
            raise ValueError(f"connections table missing columns: {sorted(missing)}")
        missing = set(LABEL_COLUMNS) - set(self.labels.columns)
        if missing:
            raise ValueError(f"labels table missing columns: {sorted(missing)}")
        if self.neurons["root_id"].duplicated().any():
            raise ValueError("neurons table has duplicate root_id values")
        ids = set(self.neurons["root_id"].tolist())
        for col in ("pre", "post"):
            unknown = ~self.connections[col].isin(ids)
            if unknown.any():
                raise ValueError(
                    f"{int(unknown.sum())} connections reference a {col} root_id "
                    "absent from the neurons table"
                )
        if (self.connections["syn_count"] <= 0).any():
            raise ValueError("connections table has non-positive syn_count")
        if (self.connections["pre"] == self.connections["post"]).any():
            raise ValueError("connections table has self-connections")

    def sign_of(self) -> pd.Series:
        """Per-neuron sign (+1, -1, or 0 when unresolved), indexed by root_id."""
        nt = self.neurons["nt_type"].fillna("").str.upper()
        return pd.Series(
            [NT_SIGN.get(t, 0) for t in nt], index=self.neurons["root_id"].to_numpy(), dtype=int
        )
