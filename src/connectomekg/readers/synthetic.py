"""A seeded synthetic connectome shaped like FlyWire, for tests and demos.

Population shares, degree tails, synapse-count histogram, transmitter shares and
reciprocity follow statistics measured on the real v783 connectivity. On top of the sampled wiring a
few named circuits are planted with the real cell-type names, so the classic
queries have something to find:

- feeding: ``GRN_sugar`` and ``GRN_bitter`` -> ``SEZ_IN1`` / ``SEZ_INb`` -> ``MN9``
- escape: ``LC4`` and ``LPLC2`` -> ``DNp01``
- grooming: ``JO-CE`` -> ``AMMC_IN`` -> ``aDN1``

:func:`write_codex_dir` emits the tables in Codex file format so the Codex
reader is exercised end to end without the real download.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from connectomekg.schema import (
    CONNECTION_COLUMNS,
    LABEL_COLUMNS,
    NEURON_COLUMNS,
    NT_SCORE_COLUMNS,
    ConnectomeTables,
    DatasetInfo,
    fbbt_ids,
)

SYNTHETIC = DatasetInfo(
    dataset_id="synthetic",
    name="Synthetic connectome",
    version="1",
    organism="none (generated)",
    license="Elastic-2.0",
    url="connectomekg.readers.synthetic",
    citation="statistics from FlyWire FAFB v783, see FLY_CONNECTOME_MODEL_PLAN.md",
)

# super class -> (share, home neuropils, transmitter distribution)
_SUPER = {
    "optic": (
        0.55,
        ["ME", "LO", "LOP", "LA"],
        {"ACH": 0.55, "GLUT": 0.25, "GABA": 0.15, "DA": 0.05},
    ),
    "central": (
        0.23,
        ["SMP", "SLP", "LH", "MB_CA", "MB_ML", "FB", "EB", "LAL", "AVLP", "PLP", "GNG", "AL"],
        {"ACH": 0.50, "GABA": 0.25, "GLUT": 0.15, "DA": 0.05, "SER": 0.03, "OCT": 0.02},
    ),
    "sensory": (0.08, ["AL", "GNG", "AMMC", "LA"], {"ACH": 0.92, "GLUT": 0.05, "GABA": 0.03}),
    "visual_projection": (0.05, ["LO", "PLP", "PVLP"], {"ACH": 0.80, "GLUT": 0.20}),
    "visual_centrifugal": (0.01, ["ME", "LO"], {"GABA": 0.5, "ACH": 0.3, "OCT": 0.2}),
    "descending": (0.03, ["GNG", "LAL", "PLP"], {"ACH": 0.70, "GABA": 0.20, "GLUT": 0.10}),
    "ascending": (0.02, ["GNG"], {"ACH": 0.8, "GABA": 0.2}),
    "motor": (0.02, ["GNG"], {"ACH": 1.0}),
    "endocrine": (0.01, ["PRW"], {"DA": 0.4, "OCT": 0.3, "SER": 0.3}),
}
_TYPE_PREFIX = {
    "optic": "Mi",
    "central": "CB",
    "sensory": "SN",
    "visual_projection": "LC",
    "visual_centrifugal": "VC",
    "descending": "DN",
    "ascending": "AN",
    "motor": "MN",
    "endocrine": "EN",
}
# A few neuropil-to-neuropil flows so wiring is not purely local.
_PARTNERS = {
    "LA": "ME",
    "ME": "LO",
    "LO": "PLP",
    "LOP": "PLP",
    "AL": "LH",
    "LH": "SMP",
    "MB_CA": "MB_ML",
    "MB_ML": "SMP",
    "SMP": "LAL",
    "SLP": "SMP",
    "FB": "LAL",
    "EB": "FB",
    "LAL": "GNG",
    "AVLP": "GNG",
    "PLP": "GNG",
    "PVLP": "GNG",
    "AMMC": "GNG",
    "GNG": "GNG",
    "PRW": "GNG",
}
_UNPAIRED = {"FB", "EB", "GNG", "PRW"}
# Empirical synapses-per-connection histogram for counts 1..19 (v783), tail geometric.
_SYN_HIST = np.array(
    [
        0.4967,
        0.1776,
        0.0914,
        0.0554,
        0.0370,
        0.0261,
        0.0192,
        0.0146,
        0.0114,
        0.0091,
        0.0073,
        0.0061,
        0.0051,
        0.0043,
        0.0037,
        0.0033,
        0.0028,
        0.0025,
        0.0022,
    ]
)
_NEUROPIL_CENTER_UM = {
    "LA": (390, 200, 100),
    "ME": (330, 200, 120),
    "LO": (270, 200, 140),
    "LOP": (250, 200, 100),
    "AL": (90, 260, 120),
    "LH": (150, 190, 120),
    "MB_CA": (140, 150, 160),
    "MB_ML": (100, 150, 130),
    "SMP": (90, 130, 140),
    "SLP": (140, 130, 150),
    "FB": (0, 170, 140),
    "EB": (0, 190, 120),
    "LAL": (60, 220, 110),
    "AVLP": (170, 230, 100),
    "PLP": (180, 200, 170),
    "PVLP": (170, 240, 130),
    "AMMC": (100, 290, 90),
    "GNG": (0, 330, 110),
    "PRW": (0, 300, 60),
}


#: Planted circuits: (super class, cell type, count, home neuropil, transmitter, label).
#: These overwrite sampled neurons so the classic queries have something to find.
PLANTS: tuple[tuple[str, str, int, str, str, str], ...] = (
    ("sensory", "GRN_sugar", 6, "GNG", "ACH", "sugar gustatory receptor neuron"),
    ("sensory", "GRN_bitter", 4, "GNG", "ACH", "bitter gustatory receptor neuron"),
    ("sensory", "JO-CE", 10, "AMMC", "ACH", "Johnston's organ neuron JO-C/E"),
    ("central", "SEZ_IN1", 3, "GNG", "ACH", "second-order sugar interneuron"),
    ("central", "SEZ_INb", 1, "GNG", "GABA", "second-order bitter neuron"),
    ("central", "AMMC_IN", 3, "AMMC", "ACH", "antennal grooming interneuron"),
    ("motor", "MN9", 2, "GNG", "ACH", "proboscis motor neuron MN9"),
    ("visual_projection", "LC4", 8, "LO", "ACH", "lobula columnar LC4, looming"),
    ("visual_projection", "LPLC2", 10, "LO", "ACH", "lobula plate lobula columnar LPLC2"),
    ("descending", "DNp01", 2, "GNG", "ACH", "giant fiber descending neuron"),
    ("descending", "aDN1", 2, "GNG", "ACH", "antennal grooming descending neuron aDN1"),
)


def min_neurons() -> int:
    """Smallest ``n_neurons`` whose super-class shares fit every planted circuit.

    A super class gets ``share * n`` neurons, and the planted circuits claim a
    fixed number from each, so a small ``n`` would silently shrink a circuit and
    make the fixture's tests meaningless.

    :return: The minimum neuron count :func:`synthetic_tables` accepts.
    """
    need: dict[str, int] = {}
    for sc, _, k, _, _, _ in PLANTS:
        need[sc] = need.get(sc, 0) + k
    # +1 guards the rounding in the share-to-count conversion.
    return max(int(np.ceil(k / _SUPER[sc][0])) + 1 for sc, k in need.items())


def _draw_syn_counts(rng: np.random.Generator, n: int) -> np.ndarray:
    p = np.append(_SYN_HIST, 1.0 - _SYN_HIST.sum())
    k = rng.choice(len(p), size=n, p=p) + 1
    tail = k == len(p)
    k[tail] = 20 + rng.geometric(0.03, size=int(tail.sum()))
    return np.minimum(k, 2405).astype(np.int32)


def _neuropil(base: str, side: str) -> str:
    return base if base in _UNPAIRED else f"{base}_{side}"


def synthetic_tables(n_neurons: int = 1000, seed: int = 1) -> ConnectomeTables:
    """Generate a synthetic connectome.

    :param n_neurons: Number of neurons, including the planted circuits. Must be
        at least :func:`min_neurons` so every planted circuit fits its super class.
    :param seed: Random seed; the output is a deterministic function of it.
    :return: Validated :class:`ConnectomeTables`.
    :raises ValueError: When ``n_neurons`` is below :func:`min_neurons`.
    """
    floor = min_neurons()
    if n_neurons < floor:
        raise ValueError(
            f"n_neurons={n_neurons} is too small for the planted circuits; the minimum is {floor}"
        )
    rng = np.random.default_rng(seed)
    supers = list(_SUPER)
    shares = np.array([_SUPER[s][0] for s in supers])
    shares /= shares.sum()
    counts = np.round(shares * n_neurons).astype(int)
    counts[-1] += n_neurons - counts.sum()

    rows: list[dict] = []
    root0 = 720_575_940_000_000_000 + int(rng.integers(1, 10**9))
    for sc, n in zip(supers, counts, strict=True):
        _, homes, nts = _SUPER[sc]
        # Zipf-like type sizes: optic types are large, central types small.
        n_types = max(1, n // (8 if sc == "optic" else 2))
        type_idx = rng.zipf(1.6, size=n) % n_types
        nt_names, nt_p = list(nts), np.array(list(nts.values()))
        for i in range(n):
            base = homes[int(type_idx[i]) % len(homes)]
            side = rng.choice(["L", "R"])
            rows.append(
                {
                    "root_id": root0 + len(rows),
                    "side": side,
                    "flow": {
                        "sensory": "afferent",
                        "descending": "efferent",
                        "motor": "efferent",
                    }.get(sc, "intrinsic"),
                    "super_class": sc,
                    "class": f"{sc}_{base}",
                    "sub_class": "",
                    "cell_type": f"{_TYPE_PREFIX[sc]}{int(type_idx[i]):03d}",
                    "hemilineage": f"HL{int(type_idx[i]) % 12:02d}" if sc == "central" else "",
                    "nerve": "AN" if sc == "sensory" else "",
                    "nt_type": nt_names[int(rng.choice(len(nt_p), p=nt_p / nt_p.sum()))],
                    "nt_score": float(rng.uniform(0.5, 0.99)),
                    "_home": base,
                }
            )
    df = pd.DataFrame(rows)

    used: dict[str, int] = {}
    planted: dict[str, list[int]] = {}
    labels: list[dict] = []
    for sc, ctype, n, home, nt, label in PLANTS:
        idx = df.index[df["super_class"] == sc][used.get(sc, 0) : used.get(sc, 0) + n]
        used[sc] = used.get(sc, 0) + n
        if len(idx) != n:  # min_neurons() should make this unreachable
            raise ValueError(
                f"only {len(idx)} of {n} {sc} neurons left for {ctype}; raise n_neurons"
            )
        df.loc[idx, ["cell_type", "_home", "nt_type", "class"]] = [ctype, home, nt, f"{sc}_{home}"]
        df.loc[idx, "side"] = [("L", "R")[i % 2] for i in range(n)]
        planted[ctype] = df.loc[idx, "root_id"].tolist()
        for rid in planted[ctype]:
            labels.append(
                {
                    "root_id": rid,
                    "text": label,
                    "user": "synthetic",
                    "affiliation": "connectomekg fixture",
                    "date": "2026-09-16",
                }
            )

    df["neuropil"] = [_neuropil(b, s) for b, s in zip(df["_home"], df["side"], strict=True)]
    centers = np.array([_NEUROPIL_CENTER_UM[b] for b in df["_home"]], dtype=float)
    centers[:, 0] *= np.where(df["side"].to_numpy() == "L", -1.0, 1.0)
    xyz = (centers + rng.normal(0, 15, size=centers.shape)) * 1000.0 + np.array([450e3, 0, 0])
    df["x"], df["y"], df["z"] = xyz[:, 0], xyz[:, 1], xyz[:, 2]

    # Sampled wiring: degree-corrected, neuropil-local with partner flows.
    n = len(df)
    # Mean out-degree scales with size toward the real 109, floored so small
    # fixtures still have enough wiring to walk.
    k_mean = max(12.0 if n >= 500 else 4.0, 109.0 * min(1.0, n / 139_000))
    sigma = 1.1
    out_deg = rng.lognormal(np.log(k_mean) - sigma**2 / 2, sigma, size=n)
    out_deg = np.clip(np.round(out_deg), 0, n // 4).astype(int)
    by_np: dict[str, np.ndarray] = {
        str(k): g.index.to_numpy() for k, g in df.groupby("neuropil", sort=False)
    }
    homes = df["_home"].to_numpy()
    sides = df["side"].to_numpy()
    pre_l, post_l = [], []
    for i in range(n):
        k = int(out_deg[i])
        if k == 0:
            continue
        partner = _PARTNERS.get(homes[i], "GNG")
        pools = [
            (0.7, by_np.get(_neuropil(homes[i], sides[i]), np.empty(0, int))),
            (0.2, by_np.get(_neuropil(partner, sides[i]), np.empty(0, int))),
            (0.1, np.arange(n)),
        ]
        chosen: set[int] = set()
        for share, pool in pools:
            m = int(round(k * share))
            if m == 0 or len(pool) == 0:
                continue
            pick = rng.choice(pool, size=min(m, len(pool)), replace=False)
            chosen.update(int(j) for j in pick if j != i)
        pre_l.extend([i] * len(chosen))
        post_l.extend(sorted(chosen))
    pre = np.array(pre_l, dtype=int)
    post = np.array(post_l, dtype=int)
    # Reciprocity: about a quarter of pairs are reciprocal in v783.
    flip = rng.random(len(pre)) < 0.10
    pre = np.concatenate([pre, post[flip]])
    post = np.concatenate([post, pre[: len(flip)][flip]])
    pairs = pd.DataFrame({"pre_i": pre, "post_i": post}).drop_duplicates()
    pairs = pairs[pairs["pre_i"] != pairs["post_i"]]
    syn = _draw_syn_counts(rng, len(pairs))
    con = pd.DataFrame(
        {
            "pre": df["root_id"].to_numpy()[pairs["pre_i"].to_numpy()],
            "post": df["root_id"].to_numpy()[pairs["post_i"].to_numpy()],
            "neuropil": df["neuropil"].to_numpy()[pairs["post_i"].to_numpy()],
            "syn_count": syn,
            "nt_type": df["nt_type"].to_numpy()[pairs["pre_i"].to_numpy()],
        }
    )

    # Planted edges, strong enough to dominate the sampled background.
    nt_of = dict(zip(df["root_id"], df["nt_type"], strict=True))
    np_of = dict(zip(df["root_id"], df["neuropil"], strict=True))
    extra: list[tuple[int, int, int]] = []

    def fan(a: str, b: str, lo: int, hi: int) -> None:
        for s in planted[a]:
            for t in planted[b]:
                extra.append((s, t, int(rng.integers(lo, hi + 1))))

    fan("GRN_sugar", "SEZ_IN1", 20, 40)
    fan("SEZ_IN1", "MN9", 40, 80)
    fan("GRN_bitter", "SEZ_INb", 20, 30)
    fan("SEZ_INb", "MN9", 25, 35)
    fan("SEZ_INb", "SEZ_IN1", 10, 20)
    fan("LC4", "DNp01", 10, 20)
    fan("LPLC2", "DNp01", 8, 14)
    fan("JO-CE", "AMMC_IN", 10, 25)
    fan("AMMC_IN", "aDN1", 30, 50)
    planted_df = pd.DataFrame(extra, columns=["pre", "post", "syn_count"])
    planted_df["neuropil"] = planted_df["post"].map(np_of)
    planted_df["nt_type"] = planted_df["pre"].map(nt_of)
    con = pd.concat([con, planted_df[list(CONNECTION_COLUMNS)]], ignore_index=True)
    con = con.groupby(["pre", "post", "neuropil"], as_index=False, sort=False).agg(
        syn_count=("syn_count", "sum"), nt_type=("nt_type", "first")
    )
    con = con.reindex(columns=list(CONNECTION_COLUMNS))

    # Generic labels on a tenth of the unplanted neurons.
    unplanted = df[~df["cell_type"].isin(planted)]
    for rid, ct in zip(unplanted["root_id"], unplanted["cell_type"], strict=True):
        if rng.random() < 0.1:
            labels.append(
                {
                    "root_id": rid,
                    "text": f"putative {ct}",
                    "user": "synthetic",
                    "affiliation": "connectomekg fixture",
                    "date": "2026-09-16",
                }
            )

    df = _annotate(df, [p[1] for p in PLANTS])
    neurons = df.drop(columns=["_home", "neuropil"]).reindex(columns=list(NEURON_COLUMNS))
    lab = pd.DataFrame(labels, columns=list(LABEL_COLUMNS))
    tables = ConnectomeTables(dataset=SYNTHETIC, neurons=neurons, connections=con, labels=lab)
    tables.validate()
    return tables


#: Visual system annotation by super class: (family, subsystem, category). The
#: centrifugal family has no subsystem, as 36 real v783 families do not.
_VISUAL = {
    "optic": ("Medulla Intrinsic", "Motion", "intrinsic"),
    "visual_projection": ("Lobula Columnar", "Object", "boundary"),
    "visual_centrifugal": ("Visual Centrifugal", None, "boundary"),
}


def _annotate(df: pd.DataFrame, planted: list[str]) -> pd.DataFrame:
    """Fill the optional annotation columns from values already in ``df``.

    Nothing here draws from the random generator, so adding annotations cannot
    move the sampled wiring or the planted circuits.

    :param df: Neurons with types, classes, sides and transmitters assigned.
    :param planted: Planted cell type names, in :data:`PLANTS` order.
    :return: A copy with every optional :data:`NEURON_COLUMNS` entry filled.
    """
    df = df.copy()
    rid = df["root_id"].astype("int64")
    tnum = df["cell_type"].str.extract(r"(\d+)$")[0].fillna("0").astype(int)
    df["sub_class"] = [
        f"{cls}_{t % 3}" if sc in ("optic", "central") else ""
        for sc, cls, t in zip(df["super_class"], df["class"], tnum, strict=True)
    ]
    for col in NT_SCORE_COLUMNS:
        nt = col.removeprefix("score_").upper()
        df[col] = np.where(df["nt_type"] == nt, df["nt_score"], ((1 - df["nt_score"]) / 5).round(3))
    df["length_nm"] = (200_000 + (rid % 997) * 1_000).astype(float)
    df["area_nm2"] = df["length_nm"] * 2_000
    df["volume_nm3"] = df["length_nm"] * 150_000

    vis = df["super_class"].map(_VISUAL)
    for i, col in enumerate(("visual_family", "visual_subsystem", "visual_category")):
        df[col] = [v[i] if isinstance(v, tuple) else None for v in vis]

    # Optic neurons sit in one of 20 columns per hemisphere; column ids repeat
    # across hemispheres, as they do in v783.
    optic = df["super_class"] == "optic"
    cid = (rid % 20 + 1).astype(float)
    df["column_hemisphere"] = np.where(df["side"] == "R", "right", "left")
    df["column_hemisphere"] = df["column_hemisphere"].where(optic)
    df["column_id"] = cid.where(optic)
    df["column_x"] = (cid % 5 - 2).where(optic)
    df["column_y"] = (cid // 5 - 2).where(optic)
    df["column_p"] = df["column_x"] + df["column_y"]
    df["column_q"] = df["column_y"] - df["column_x"]

    tags = []
    for r, ct in zip(rid, df["cell_type"], strict=True):
        t = {"feedforward_loop_participant"}
        if r % 2:
            t.add("reciprocal")
        if r % 50 == 0:
            t.add("nsrn")
        if ct == "LC4":
            t.add("broadcaster")
        if ct == "DNp01":
            t.add("integrator")
        tags.append(tuple(sorted(t)))
    df["connectivity_tags"] = tags

    # FBbt-shaped ids outside the real ontology's range. The first is spelled
    # "Fbbt_" because Codex spells the prefix both ways.
    ids = {ct: f"{'Fbbt' if k == 0 else 'FBbt'}_99{k:06d}" for k, ct in enumerate(planted)}
    refined = []
    for ct in df["cell_type"]:
        if ct in ids:
            refined.append((f"{ct}; synthetic {ct} neuron; {ids[ct]}",))
        elif ct.startswith("Mi"):
            refined.append((ct,))
        else:
            refined.append(())
    df["refined_labels"] = refined
    df["fbbt"] = [fbbt_ids(r) for r in refined]
    return df


def write_codex_dir(tables: ConnectomeTables, out_dir: str | Path) -> Path:
    """Write the tables as a Codex-format release directory.

    :param tables: Tables to write.
    :param out_dir: Directory to create.
    :return: The directory path.
    """
    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    n = tables.neurons
    pd.DataFrame(
        {
            "root_id": n["root_id"],
            "group": "",
            "nt_type": n["nt_type"],
            "nt_type_score": n["nt_score"],
            **{f"{c.removeprefix('score_')}_avg": n[c] for c in NT_SCORE_COLUMNS},
        }
    ).to_csv(d / "neurons.csv.gz", index=False)
    # Codex classification carries no cell_type column: consolidated_cell_types
    # below is where the type lives. Keep the fixture faithful to that.
    n[
        [
            "root_id",
            "flow",
            "super_class",
            "class",
            "sub_class",
            "hemilineage",
            "side",
            "nerve",
        ]
    ].assign(hemibrain_type="").to_csv(d / "classification.csv.gz", index=False)
    pd.DataFrame(
        {"root_id": n["root_id"], "primary_type": n["cell_type"], "additional_type(s)": ""}
    ).to_csv(d / "consolidated_cell_types.csv.gz", index=False)
    pos = [f"[{x:.0f} {y:.0f} {z:.0f}]" for x, y, z in zip(n["x"], n["y"], n["z"], strict=True)]
    pd.DataFrame({"root_id": n["root_id"], "position": pos, "supervoxel_id": 0}).to_csv(
        d / "coordinates.csv.gz", index=False
    )
    c = tables.connections
    pd.DataFrame(
        {
            "pre_root_id": c["pre"],
            "post_root_id": c["post"],
            "neuropil": c["neuropil"],
            "syn_count": c["syn_count"],
            "nt_type": c["nt_type"],
        }
    ).to_csv(d / "connections_princeton.csv.gz", index=False)
    pd.DataFrame(
        {
            "root_id": n["root_id"],
            "length_nm": n["length_nm"],
            "area_nm": n["area_nm2"],
            "size_nm": n["volume_nm3"],
        }
    ).to_csv(d / "cell_stats.csv.gz", index=False)
    v = n[n["visual_family"].notna()]
    pd.DataFrame(
        {
            "root_id": v["root_id"],
            "type": v["cell_type"],
            "family": v["visual_family"],
            "subsystem": v["visual_subsystem"],
            "category": v["visual_category"],
            "side": v["side"].map({"L": "left", "R": "right"}),
        }
    ).to_csv(d / "visual_neuron_types.csv.gz", index=False)
    cols = n[n["column_id"].notna()]
    pd.DataFrame(
        {
            "root_id": cols["root_id"],
            "hemisphere": cols["column_hemisphere"],
            "type": cols["cell_type"],
            **{k: cols[f"column_{k}"].astype(int) for k in ("id", "x", "y", "p", "q")},
        }
    ).rename(columns={"id": "column_id"}).to_csv(d / "column_assignment.csv.gz", index=False)
    tagged = n[n["connectivity_tags"].map(len) > 0]
    pd.DataFrame(
        {
            "root_id": tagged["root_id"],
            "connectivity_tag": tagged["connectivity_tags"].map(",".join),
        }
    ).to_csv(d / "connectivity_tags.csv.gz", index=False)
    refined = n[n["refined_labels"].map(len) > 0]
    pd.DataFrame(
        {
            "root_id": refined["root_id"],
            "processed_labels": refined["refined_labels"].map(list).map(str),
        }
    ).to_csv(d / "processed_labels.csv.gz", index=False)
    lab = tables.labels
    pd.DataFrame(
        {
            "root_id": lab["root_id"],
            "label": lab["text"],
            "user_id": 0,
            "position": "",
            "supervoxel_id": 0,
            "label_id": range(len(lab)),
            "date_created": lab["date"],
            "user_name": lab["user"],
            "user_affiliation": lab["affiliation"],
        }
    ).to_csv(d / "labels.csv.gz", index=False)
    return d
