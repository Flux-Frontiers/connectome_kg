"""Read a FlyWire Codex release directory into the normalised tables.

Column names follow the v783 release as verified 2026-09-16:

- ``neurons.csv.gz``: root_id, group, nt_type, nt_type_score, per-transmitter averages
- ``classification.csv.gz``: root_id, flow, super_class, class, sub_class, cell_type,
  hemibrain_type, hemilineage, side, nerve
- ``consolidated_cell_types.csv.gz``: root_id, primary_type, additional_type(s)
- the connections table: pre_root_id, post_root_id, neuropil, syn_count, nt_type.
  Codex has shipped this under several names (``connections_princeton.csv.gz``,
  ``connections.csv.gz``), so :func:`find_connections_file` picks whichever the
  download actually contains rather than hard-coding one.
- ``coordinates.csv.gz``: root_id, position ("[x y z]" in nanometres), supervoxel_id
- ``labels.csv.gz``: root_id, label, user_name, user_affiliation, date_created, ...

Optional annotation files, each joined on root_id when present:

- ``cell_stats.csv.gz``: root_id, length_nm, area_nm, size_nm
- ``visual_neuron_types.csv.gz``: root_id, type, family, subsystem, category, side
- ``column_assignment.csv.gz``: root_id, hemisphere, type, column_id, x, y, p, q.
  ``column_id`` is unique only within a hemisphere.
- ``connectivity_tags.csv.gz``: root_id, connectivity_tag (comma-separated)
- ``processed_labels.csv.gz``: root_id, processed_labels (a Python list literal)
"""

from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pandas as pd

from connectomekg.schema import (
    CONNECTION_COLUMNS,
    FAFB_783,
    LABEL_COLUMNS,
    LIST_COLUMNS,
    NEURON_COLUMNS,
    ConnectomeTables,
    DatasetInfo,
    fbbt_ids,
)

_STR = "object"

#: Connections tables in preference order. Codex renames this file between
#: exports, and the unthresholded variants are deliberately last: they carry
#: millions of single-synapse edges that are mostly detection noise.
CONNECTIONS_CANDIDATES = (
    "connections_princeton.csv.gz",
    "connections.csv.gz",
    "connections_buhmann.csv.gz",
    "connections_princeton_no_threshold.csv.gz",
    "connections_no_threshold.csv.gz",
    "connections_buhmann_no_threshold.csv.gz",
)

#: Accepted spellings for each column the connections table must supply.
_CONNECTION_ALIASES = {
    "pre": ("pre_root_id", "pre_pt_root_id", "pre", "pre_id"),
    "post": ("post_root_id", "post_pt_root_id", "post", "post_id"),
    "neuropil": ("neuropil", "neuropil_name", "region"),
    "syn_count": ("syn_count", "syn_cnt", "synapses", "count", "weight"),
    "nt_type": ("nt_type", "neurotransmitter", "nt"),
}


def find_connections_file(data_dir: str | Path) -> Path:
    """The connections table present in a download directory.

    :param data_dir: Directory holding the Codex files.
    :return: Path to the highest-preference connections table found.
    :raises FileNotFoundError: When none of :data:`CONNECTIONS_CANDIDATES` and no
        other ``connections*.csv*`` file is present, listing what the directory
        does hold.
    """
    d = Path(data_dir)
    for name in CONNECTIONS_CANDIDATES:
        if (d / name).is_file():
            return d / name
    loose = sorted(p for p in d.glob("connections*.cs*") if p.is_file())
    if loose:
        return loose[0]
    have = sorted(p.name for p in d.iterdir() if p.is_file()) if d.is_dir() else []
    expected = ", ".join(CONNECTIONS_CANDIDATES[:2])
    raise FileNotFoundError(
        f"no connections table in {d}. Expected one of {expected}. "
        f"Found: {', '.join(have) or 'nothing'}"
    )


def _resolve_connection_columns(path: Path) -> dict[str, str]:
    """Map our column names onto this file's spelling of them.

    :param path: The connections table.
    :return: ``{our_name: their_name}`` for every column we need.
    :raises ValueError: When a required column has no recognised spelling.
    """
    header = list(pd.read_csv(path, nrows=0).columns)
    lower = {c.lower(): c for c in header}
    resolved: dict[str, str] = {}
    missing: list[str] = []
    for ours, aliases in _CONNECTION_ALIASES.items():
        hit = next((lower[a] for a in aliases if a in lower), None)
        if hit is None:
            missing.append(f"{ours} (tried {'/'.join(aliases)})")
        else:
            resolved[ours] = hit
    if missing:
        raise ValueError(
            f"{path.name} does not look like a Codex connections table. "
            f"Missing: {'; '.join(missing)}. Its columns: {', '.join(header)}"
        )
    return resolved


def _read(path: Path, usecols: list[str] | None = None, **kw) -> pd.DataFrame:
    return pd.read_csv(path, usecols=usecols, **kw)


#: Codex per-transmitter averages in neurons.csv.gz, to the normalised score columns.
_NT_AVG = {
    "ach_avg": "score_ach",
    "da_avg": "score_da",
    "gaba_avg": "score_gaba",
    "glut_avg": "score_glut",
    "oct_avg": "score_oct",
    "ser_avg": "score_ser",
}


def _header(path: Path) -> set[str]:
    return set(pd.read_csv(path, nrows=0).columns)


def _split_tags(raw: object) -> tuple[str, ...]:
    if not isinstance(raw, str):
        return ()
    return tuple(sorted({t.strip() for t in raw.split(",") if t.strip()}))


def _parse_label_list(raw: object) -> tuple[str, ...]:
    """Codex stores refined labels as a Python list literal, e.g. ``"['T4b; FBbt_00003733']"``."""
    if not isinstance(raw, str) or not raw.strip():
        return ()
    try:
        vals = ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        return (raw.strip(),)
    if isinstance(vals, str):
        vals = [vals]
    return tuple(str(v).strip() for v in vals if str(v).strip())


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
    connections_file: str | None = None,
) -> ConnectomeTables:
    """Load a Codex release directory.

    :param data_dir: Directory with the ``*.csv.gz`` files.
    :param dataset: Provenance record to attach.
    :param connections_file: Name of the connections table to use. Omit it to
        take whichever of :data:`CONNECTIONS_CANDIDATES` the directory holds,
        preferring the 5-synapse thresholded Princeton table.
    :return: Validated :class:`ConnectomeTables`.
    :raises FileNotFoundError: When a required file is absent.
    :raises ValueError: When the connections table lacks a required column.
    """
    d = Path(data_dir)
    for name in ("neurons.csv.gz", "classification.csv.gz"):
        if not (d / name).is_file():
            raise FileNotFoundError(f"{name} not found in {d}")
    con_path = (d / connections_file) if connections_file else find_connections_file(d)
    if not con_path.is_file():
        raise FileNotFoundError(f"{con_path.name} not found in {d}")

    neurons_path = d / "neurons.csv.gz"
    avgs = [c for c in _NT_AVG if c in _header(neurons_path)]
    neurons = _read(
        neurons_path,
        ["root_id", "nt_type", "nt_type_score", *avgs],
        dtype={"root_id": np.int64, "nt_type": _STR, "nt_type_score": float},
    ).rename(columns=_NT_AVG)
    # Codex dropped cell_type from classification; consolidated_cell_types now
    # carries it. Ask only for the columns this download actually has.
    cls_path = d / "classification.csv.gz"
    cls_have = set(pd.read_csv(cls_path, nrows=0).columns)
    cls = _read(
        cls_path,
        [
            c
            for c in (
                "root_id",
                "flow",
                "super_class",
                "class",
                "sub_class",
                "cell_type",
                "hemilineage",
                "side",
                "nerve",
            )
            if c in cls_have
        ],
        dtype={"root_id": np.int64},
    )
    if "cell_type" not in cls_have:
        cls["cell_type"] = pd.NA
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

    df = _join_annotations(df, d)

    df["nt_type"] = df["nt_type"].fillna("").astype(str).str.upper()
    df = df.rename(columns={"nt_type_score": "nt_score"})
    df = df.sort_values("root_id", kind="mergesort").reset_index(drop=True)
    df = df.reindex(columns=list(NEURON_COLUMNS))
    for col in LIST_COLUMNS:
        df[col] = df[col].map(lambda v: v if isinstance(v, tuple) else ())

    cols = _resolve_connection_columns(con_path)
    con = _read(
        con_path,
        [cols[k] for k in ("pre", "post", "neuropil", "syn_count", "nt_type")],
        dtype={
            cols["pre"]: np.int64,
            cols["post"]: np.int64,
            cols["neuropil"]: _STR,
            cols["syn_count"]: np.int32,
            cols["nt_type"]: _STR,
        },
    ).rename(columns={v: k for k, v in cols.items()})
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


def _join_annotations(df: pd.DataFrame, d: Path) -> pd.DataFrame:
    """Left-join the optional per-neuron annotation files present in ``d``.

    :param df: Neurons so far, one row per root_id.
    :param d: Release directory.
    :return: ``df`` with whichever annotation columns the directory supplies.
    """
    ids = {"root_id": np.int64}
    path = d / "cell_stats.csv.gz"
    if path.is_file():
        cs = _read(path, ["root_id", "length_nm", "area_nm", "size_nm"], dtype=ids)
        df = df.merge(
            cs.rename(columns={"area_nm": "area_nm2", "size_nm": "volume_nm3"}),
            on="root_id",
            how="left",
        )
    path = d / "visual_neuron_types.csv.gz"
    if path.is_file():
        vis = _read(path, ["root_id", "family", "subsystem", "category"], dtype=ids)
        df = df.merge(
            vis.rename(
                columns={
                    "family": "visual_family",
                    "subsystem": "visual_subsystem",
                    "category": "visual_category",
                }
            ),
            on="root_id",
            how="left",
        )
    path = d / "column_assignment.csv.gz"
    if path.is_file():
        col = _read(path, ["root_id", "hemisphere", "column_id", "x", "y", "p", "q"], dtype=ids)
        df = df.merge(
            col.rename(
                columns={
                    "hemisphere": "column_hemisphere",
                    "x": "column_x",
                    "y": "column_y",
                    "p": "column_p",
                    "q": "column_q",
                }
            ),
            on="root_id",
            how="left",
        )
    path = d / "connectivity_tags.csv.gz"
    if path.is_file():
        tags = _read(path, ["root_id", "connectivity_tag"], dtype=ids)
        tags["connectivity_tags"] = tags["connectivity_tag"].map(_split_tags)
        df = df.merge(tags[["root_id", "connectivity_tags"]], on="root_id", how="left")
    path = d / "processed_labels.csv.gz"
    if path.is_file():
        pl = _read(path, ["root_id", "processed_labels"], dtype=ids)
        pl["refined_labels"] = pl["processed_labels"].map(_parse_label_list)
        pl["fbbt"] = pl["refined_labels"].map(fbbt_ids)
        df = df.merge(pl[["root_id", "refined_labels", "fbbt"]], on="root_id", how="left")
    return df
