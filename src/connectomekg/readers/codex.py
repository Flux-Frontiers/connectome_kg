"""Read a FlyWire Codex release directory into the normalized tables.

Codex exports releases in two layouts. BANC v888 and MCNS v1.0 come as one
consolidated neuron-attributes table with display-name columns (``Root ID``,
``Super Class``, ...) beside the connections table; see
:data:`ATTRIBUTE_COLUMNS`. That export carries no coordinates, so those two
releases take soma positions from a Feather table each project publishes
itself; see :data:`SOMA_POSITION_SOURCES`. FAFB v783 is split across the
files below.

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
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.feather as feather

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
    :raises ValueError: When a required column has no recognized spelling.
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


#: Codex per-transmitter averages in neurons.csv.gz, to the normalized score columns.
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


#: Soma-position tables the attribute-export releases can be given, as
#: ``(id column, position column, nanometres per position unit)``. Codex
#: exports no coordinates for BANC or MCNS, so a build from its files alone
#: has nothing for the 3-D views to place; both projects publish positions
#: beside their own downloads, and dropping either Feather table into the
#: release directory fills them in. Matched on columns, not file name, since
#: neither name is stable across releases. See ``docs/DOWNLOAD.md``.
SOMA_POSITION_SOURCES: tuple[tuple[str, str, float], ...] = (
    # Male CNS v1.0 body annotations: ``somaLocation`` is an ``[x y z]`` array
    # in 8 nm EM voxels, keyed by ``bodyId``.
    ("bodyId", "somaLocation", 8.0),
    # BANC v888 compiled metadata: ``root_position_nm`` is "x, y, z" already in
    # nanometres. Key on ``root_888``, the v888 root id; the table's own
    # ``root_id`` is a later snapshot and matches 13,600 fewer of this build's
    # neurons.
    ("root_888", "root_position_nm", 1.0),
)


def _feather_columns(path: Path) -> list[str]:
    """Column names of a Feather table, without reading a row of it.

    :param path: The table.
    :return: Its column names, or ``[]`` when the file is not Feather v2.
    """
    try:
        return pa.ipc.open_file(path).schema.names
    except pa.ArrowInvalid:
        return []


def _match_position_source(d: Path) -> tuple[Path, tuple[str, str, float]] | None:
    """The first table in *d* whose columns match a :data:`SOMA_POSITION_SOURCES` entry."""
    for path in sorted(d.glob("*.feather")):
        names = set(_feather_columns(path))
        for source in SOMA_POSITION_SOURCES:
            if {source[0], source[1]} <= names:
                return path, source
    return None


def soma_position_table(data_dir: str | Path) -> Path | None:
    """The soma-position table a release directory holds, if any.

    :param data_dir: Release directory.
    :return: The matching Feather table, or None when there is none. Used by
        ``connkg verify`` to report whether a build will have coordinates.
    """
    found = _match_position_source(Path(data_dir))
    return found[0] if found else None


def _read_soma_positions(d: Path) -> pd.DataFrame | None:
    """Read soma positions from a project's own metadata table, when present.

    :param d: Release directory, searched for any table whose columns match
        one of :data:`SOMA_POSITION_SOURCES`.
    :return: ``root_id``, ``x``, ``y``, ``z`` in nanometres for the neurons
        the table positions, or None when the directory holds no such table.
    """
    found = _match_position_source(d)
    if found is None:
        return None
    path, (id_col, pos_col, nm_per_unit) = found
    raw = feather.read_table(path, columns=[id_col, pos_col]).to_pandas()
    raw = raw[raw[id_col].notna() & raw[pos_col].notna()]
    xyz = _parse_positions(raw[pos_col]) * nm_per_unit
    out = pd.DataFrame(
        {
            "root_id": raw[id_col].to_numpy().astype(np.int64),
            "x": xyz[:, 0],
            "y": xyz[:, 1],
            "z": xyz[:, 2],
        }
    )
    return out.drop_duplicates("root_id", keep="first")


#: Header of the consolidated "neuron attributes" export that Codex offers for
#: BANC and MCNS, mapped to the normalized columns. That one file carries what
#: the FAFB release splits across neurons, classification, cell types, cell
#: stats and labels, under display names.
ATTRIBUTE_COLUMNS: dict[str, str] = {
    "Root ID": "root_id",
    "Predicted NT type": "nt_type",
    "Predicted NT confidence": "nt_score",
    "Flow": "flow",
    "Super Class": "super_class",
    "Class": "class",
    "Sub Class": "sub_class",
    "Hemilineage": "hemilineage",
    "Nerve": "nerve",
    "Soma side": "side",
    "Primary Cell Type": "cell_type",
    "Cable length (nm)": "length_nm",
    "Surface area (nm^2)": "area_nm2",
    "Volume (nm^3)": "volume_nm3",
}
_COMMUNITY_LABELS = "Community labels"

#: MCNS community-label keys left out of the labels table. Every distinct
#: label text becomes a graph node, and these are not anatomy: ``statusLabel``
#: is proofreading status, and ``mancBodyid`` is a per-neuron id that would
#: add one single-use node per neuron (18,572 of them).
DROPPED_LABEL_KEYS = frozenset({"statusLabel", "mancBodyid"})
_LABEL_KEY = re.compile(r"^(\w+):\s")

#: Super classes spelled differently across releases, to FAFB's spelling.
#: BANC and MCNS name the intrinsic classes by region (``optic_lobe_intrinsic``,
#: ``ol_intrinsic``) and MCNS also splits sensory, motor, efferent and
#: endocrine by region, where FAFB has one class each. A value not listed is
#: kept as it is, including MCNS's ``*_tbc`` (to be confirmed) classes.
SUPER_CLASS_ALIASES: dict[str, str] = {
    "optic_lobe_intrinsic": "optic",
    "central_brain_intrinsic": "central",
    "ventral_nerve_cord_intrinsic": "ventral_nerve_cord",
    "ol_intrinsic": "optic",
    "cb_intrinsic": "central",
    "vnc_intrinsic": "ventral_nerve_cord",
    "ol_sensory": "sensory",
    "cb_sensory": "sensory",
    "vnc_sensory": "sensory",
    "ascending_neuron": "ascending",
    "descending_neuron": "descending",
    "cb_motor": "motor",
    "vnc_motor": "motor",
    "cb_efferent": "efferent",
    "vnc_efferent": "efferent",
    "cb_endocrine": "endocrine",
    "vnc_endocrine": "endocrine",
}


def is_attribute_export(data_dir: str | Path) -> bool:
    """Whether a download holds the consolidated neuron-attributes export.

    :param data_dir: Directory holding the Codex files.
    :return: True when ``neurons.csv.gz`` has the display-name header
        (``Root ID``, ...) of the BANC and MCNS exports rather than FAFB's
        ``root_id``.
    """
    path = Path(data_dir) / "neurons.csv.gz"
    return path.is_file() and "Root ID" in _header(path)


def _split_community_labels(raw: object) -> list[str]:
    """One consolidated ``Community labels`` cell, as separate label texts.

    :param raw: The cell: comma-separated phrases (BANC) or ``key: value``
        pairs (MCNS).
    :return: The labels, minus :data:`DROPPED_LABEL_KEYS`.
    """
    if not isinstance(raw, str):
        return []
    out = []
    for item in raw.split(","):
        text = item.strip()
        key = _LABEL_KEY.match(text)
        if text and not (key and key.group(1) in DROPPED_LABEL_KEYS):
            out.append(text)
    return out


def _read_attribute_export(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read the consolidated neuron-attributes file.

    :param path: Its ``neurons.csv.gz``. Soma positions are read from any
        table beside it matching :data:`SOMA_POSITION_SOURCES`, since the
        export itself carries no coordinates.
    :return: ``(neurons, labels)``: neurons with whichever normalized columns
        the export fills, and one label row per community label. The export
        carries no label attribution, so ``user``, ``affiliation`` and ``date``
        are empty.
    """
    have = _header(path)
    usecols = [c for c in (*ATTRIBUTE_COLUMNS, _COMMUNITY_LABELS) if c in have]
    raw = _read(path, usecols, dtype=_STR)
    df = raw.drop(columns=[_COMMUNITY_LABELS], errors="ignore").rename(columns=ATTRIBUTE_COLUMNS)
    df["root_id"] = df["root_id"].astype(np.int64)
    for col in ("nt_score", "length_nm", "area_nm2", "volume_nm3"):
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "super_class" in df:
        df["super_class"] = df["super_class"].map(
            lambda v: SUPER_CLASS_ALIASES.get(v, v) if isinstance(v, str) else v
        )
    pos = _read_soma_positions(path.parent)
    if pos is None:
        df["x"] = df["y"] = df["z"] = np.nan
    else:
        df = df.merge(pos, on="root_id", how="left")

    rows = [
        (rid, text)
        for rid, cell in zip(df["root_id"], raw.get(_COMMUNITY_LABELS, []), strict=False)
        for text in _split_community_labels(cell)
    ]
    lab = pd.DataFrame(rows, columns=["root_id", "text"])
    for col in ("user", "affiliation", "date"):
        lab[col] = ""
    return df, lab


def _read_split_release(d: Path) -> pd.DataFrame:
    """Read the neuron tables of a release split across files, as FAFB is.

    :param d: Release directory.
    :return: Neurons with every column the directory supplies.
    """
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
    return df.rename(columns={"nt_type_score": "nt_score"})


def _read_labels_file(d: Path) -> pd.DataFrame:
    """Read ``labels.csv.gz`` when the release has one.

    :param d: Release directory.
    :return: Label rows in :data:`LABEL_COLUMNS` order; empty when absent.
    """
    lab_path = d / "labels.csv.gz"
    if not lab_path.is_file():
        return pd.DataFrame(columns=list(LABEL_COLUMNS))
    return _read(
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


def read_codex(
    data_dir: str | Path,
    dataset: DatasetInfo = FAFB_783,
    *,
    connections_file: str | None = None,
) -> ConnectomeTables:
    """Load a Codex release directory.

    Reads either layout Codex exports: FAFB's, split across ``neurons``,
    ``classification`` and optional annotation files, or the consolidated
    neuron-attributes export of BANC and MCNS (see
    :func:`is_attribute_export`). Connections are the same in both.

    Two normalizations apply to every release. A connection row with no
    transmitter takes its presynaptic neuron's, since BANC and MCNS leave the
    column empty. And pairs with fewer than ``dataset.min_pair_syn`` synapses,
    summed over neuropils, are dropped.

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
    attribute_export = is_attribute_export(d)
    required = (
        ("neurons.csv.gz",) if attribute_export else ("neurons.csv.gz", "classification.csv.gz")
    )
    for name in required:
        if not (d / name).is_file():
            raise FileNotFoundError(f"{name} not found in {d}")
    con_path = (d / connections_file) if connections_file else find_connections_file(d)
    if not con_path.is_file():
        raise FileNotFoundError(f"{con_path.name} not found in {d}")

    if attribute_export:
        df, lab = _read_attribute_export(d / "neurons.csv.gz")
    else:
        df, lab = _read_split_release(d), _read_labels_file(d)

    df["nt_type"] = df["nt_type"].fillna("").astype(str).str.upper()
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
    con = con[con["pre"] != con["post"]]
    blank = con["nt_type"] == ""
    if blank.any():
        pre_nt = df.set_index("root_id")["nt_type"]
        con.loc[blank, "nt_type"] = con.loc[blank, "pre"].map(pre_nt).fillna("")
    if dataset.min_pair_syn > 1:
        pair_total = con.groupby(["pre", "post"], sort=False)["syn_count"].transform("sum")
        con = con[pair_total >= dataset.min_pair_syn]
    con = con.reset_index(drop=True).reindex(columns=list(CONNECTION_COLUMNS))

    lab["text"] = lab["text"].astype(str).str.strip()
    lab = lab[lab["root_id"].isin(known) & (lab["text"] != "")]
    lab = lab.reindex(columns=list(LABEL_COLUMNS)).reset_index(drop=True)

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
