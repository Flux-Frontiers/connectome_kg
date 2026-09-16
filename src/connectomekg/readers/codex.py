"""Read a FlyWire Codex release directory into the normalised tables.

Column names follow the v783 release as verified 2026-09-16:

- ``neurons.csv.gz``: root_id, group, nt_type, nt_type_score, per-transmitter averages
- ``classification.csv.gz``: root_id, flow, super_class, class, sub_class, cell_type,
  hemibrain_type, hemilineage, side, nerve
- ``consolidated_cell_types.csv.gz``: root_id, primary_type, additional_type(s)
- ``connections_princeton.csv.gz``: pre_root_id, post_root_id, neuropil, syn_count, nt_type
- ``coordinates.csv.gz``: root_id, position ("[x y z]" in nanometres), supervoxel_id
- ``labels.csv.gz``: root_id, label, user_name, user_affiliation, date_created, ...
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from connectomekg.schema import (
    CONNECTION_COLUMNS,
    FAFB_783,
    LABEL_COLUMNS,
    NEURON_COLUMNS,
    ConnectomeTables,
    DatasetInfo,
)

_STR = "object"


def _read(path: Path, usecols: list[str] | None = None, **kw) -> pd.DataFrame:
    return pd.read_csv(path, usecols=usecols, **kw)


def _parse_positions(series: pd.Series) -> np.ndarray:
    """Turn Codex ``"[x y z]"`` strings into an (n, 3) float array (NaN when blank)."""
    out = np.full((len(series), 3), np.nan)
    for i, raw in enumerate(series.astype(str)):
        s = raw.strip("[] ")
        if not s or s == "nan":
            continue
        parts = s.replace(",", " ").split()
        if len(parts) == 3:
            out[i] = [float(v) for v in parts]
    return out


def read_codex(
    data_dir: str | Path,
    dataset: DatasetInfo = FAFB_783,
    *,
    connections_file: str = "connections_princeton.csv.gz",
) -> ConnectomeTables:
    """Load a Codex release directory.

    :param data_dir: Directory with the ``*.csv.gz`` files.
    :param dataset: Provenance record to attach.
    :param connections_file: Which connections table to use; the default is the
        5-synapse thresholded Princeton table Codex ships as its standard.
    :return: Validated :class:`ConnectomeTables`.
    :raises FileNotFoundError: When a required file is absent.
    """
    d = Path(data_dir)
    for name in ("neurons.csv.gz", "classification.csv.gz", connections_file):
        if not (d / name).is_file():
            raise FileNotFoundError(f"{name} not found in {d}")

    neurons = _read(
        d / "neurons.csv.gz",
        ["root_id", "nt_type", "nt_type_score"],
        dtype={"root_id": np.int64, "nt_type": _STR, "nt_type_score": float},
    )
    cls = _read(
        d / "classification.csv.gz",
        [
            "root_id",
            "flow",
            "super_class",
            "class",
            "sub_class",
            "cell_type",
            "hemilineage",
            "side",
            "nerve",
        ],
        dtype={"root_id": np.int64},
    )
    df = neurons.merge(cls, on="root_id", how="left")

    ctypes = d / "consolidated_cell_types.csv.gz"
    if ctypes.is_file():
        ct = _read(ctypes, ["root_id", "primary_type"], dtype={"root_id": np.int64})
        df = df.merge(ct, on="root_id", how="left")
        # The consolidated primary type wins; classification.cell_type fills gaps.
        df["cell_type"] = df["primary_type"].where(df["primary_type"].notna(), df["cell_type"])
        df = df.drop(columns=["primary_type"])

    coords = d / "coordinates.csv.gz"
    if coords.is_file():
        co = _read(coords, ["root_id", "position"], dtype={"root_id": np.int64, "position": _STR})
        co = co.drop_duplicates("root_id", keep="first")
        xyz = _parse_positions(co["position"])
        co = co.assign(x=xyz[:, 0], y=xyz[:, 1], z=xyz[:, 2]).drop(columns=["position"])
        df = df.merge(co, on="root_id", how="left")
    else:
        df["x"] = df["y"] = df["z"] = np.nan

    df["nt_type"] = df["nt_type"].fillna("").astype(str).str.upper()
    df = df.rename(columns={"nt_type_score": "nt_score"})
    df = df.sort_values("root_id", kind="mergesort").reset_index(drop=True)
    df = df.reindex(columns=list(NEURON_COLUMNS))

    con = _read(
        d / connections_file,
        ["pre_root_id", "post_root_id", "neuropil", "syn_count", "nt_type"],
        dtype={
            "pre_root_id": np.int64,
            "post_root_id": np.int64,
            "neuropil": _STR,
            "syn_count": np.int32,
            "nt_type": _STR,
        },
    ).rename(columns={"pre_root_id": "pre", "post_root_id": "post"})
    con["nt_type"] = con["nt_type"].fillna("").astype(str).str.upper()
    known = set(df["root_id"].tolist())
    con = con[con["pre"].isin(known) & con["post"].isin(known)]
    con = con[con["pre"] != con["post"]].reset_index(drop=True)
    con = con.reindex(columns=list(CONNECTION_COLUMNS))

    lab_path = d / "labels.csv.gz"
    if lab_path.is_file():
        lab = _read(
            lab_path,
            ["root_id", "label", "user_name", "user_affiliation", "date_created"],
            dtype={"root_id": np.int64},
        ).rename(
            columns={
                "label": "text",
                "user_name": "user",
                "user_affiliation": "affiliation",
                "date_created": "date",
            }
        )
        lab["text"] = lab["text"].astype(str).str.strip()
        lab = lab[lab["root_id"].isin(known) & (lab["text"] != "")]
        lab = lab.reindex(columns=list(LABEL_COLUMNS)).reset_index(drop=True)
    else:
        lab = pd.DataFrame(columns=list(LABEL_COLUMNS))

    tables = ConnectomeTables(dataset=dataset, neurons=df, connections=con, labels=lab)
    tables.validate()
    return tables
