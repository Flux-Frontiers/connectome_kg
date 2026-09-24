"""The consolidated neuron-attributes export Codex serves for BANC and MCNS."""

from __future__ import annotations

import gzip
from pathlib import Path

import pytest

from connectomekg import ConnectomeKG
from connectomekg.cli.options import _dataset
from connectomekg.datasets import dataset_dir
from connectomekg.manifest import verify_dir
from connectomekg.neuropils import neuropil_full_name, neuropil_region
from connectomekg.readers.codex import is_attribute_export, read_codex
from connectomekg.readers.synthetic import write_codex_dir
from connectomekg.schema import BANC_888, MCNS_1, DatasetInfo

HEADER = (
    "Root ID,Top in/out region,Community labels,Predicted NT type,"
    "Predicted NT confidence,Verified NT type,Verified Neuropeptide,Body Part,"
    "Function,Flow,Super Class,Class,Sub Class,Hemilineage,Nerve,Soma side,"
    "Primary Cell Type,Alternative Cell Type(s),Cable length (nm),"
    "Surface area (nm^2),Volume (nm^3)"
)

# Rows shaped like the real exports: 1-2 MCNS-style key-value labels, 3 a
# BANC-style phrase list, 4 histamine, 5 tyramine, 6 no prediction.
NEURONS = [
    '1,g1,"flywireType: DNp01,statusLabel: Roughly traced,mancBodyid: 10000",'
    "ACH,0.9,,,,,,descending_neuron,,,,,right,DNp01,DNp01,,,",
    '2,g2,"flywireType: Tm33,hemibrainType: Tm33",GABA,0.8,,,,,,ol_intrinsic,,,,,left,Tm33,Tm33,,,',
    '3,g3,"AMMC B1,CNS neuron,soma in brain",GLUT,0.7,,,,,,central_brain_intrinsic,,,,,left,,,,,',
    "4,g4,,HIST,0.95,,,,,,ol_sensory,,,,,right,R7,R7,,,",
    "5,g5,,TYR,0.6,,,,,,vnc_tbc,,,,,center,,,,,",
    "6,g6,,,,,,,,,ventral_nerve_cord_intrinsic,,,,,left,,,,,",
]

# (pre, post, neuropil, syn_count). Pair 1->2 has 5 over two neuropils and
# survives a pair threshold of 5 though no row reaches it; 3->4 has 4 and is
# dropped; 5->5 is a self-connection.
CONNECTIONS = [
    (1, 2, "LegNp_T1_L", 3),
    (1, 2, "VNC_T2_MesoNm_R", 2),
    (3, 4, "GNG", 4),
    (4, 6, "ME_R", 9),
    (6, 1, "IntTct", 6),
    (5, 5, "ANm", 7),
]


def _write(path: Path, text: str) -> None:
    with gzip.open(path, "wt") as fh:
        fh.write(text)


@pytest.fixture
def export_dir(tmp_path: Path) -> Path:
    d = tmp_path / "banc_v888"
    d.mkdir()
    _write(d / "neurons.csv.gz", "\n".join([HEADER, *NEURONS]) + "\n")
    rows = [f"{a},{b},{n},{s}," for a, b, n, s in CONNECTIONS]
    _write(
        d / "connections_princeton.csv.gz",
        "\n".join(["pre_root_id,post_root_id,neuropil,syn_count,nt_type", *rows]) + "\n",
    )
    return d


def test_the_layout_is_recognized_by_its_header(export_dir, tables, tmp_path):
    assert is_attribute_export(export_dir)
    assert not is_attribute_export(write_codex_dir(tables, tmp_path / "fafb_like"))
    assert not is_attribute_export(tmp_path / "nowhere")


def test_no_classification_file_is_needed(export_dir):
    t = read_codex(export_dir, BANC_888)
    assert len(t.neurons) == 6
    assert t.dataset is BANC_888


def test_columns_map_to_the_normalized_names(export_dir):
    n = read_codex(export_dir, BANC_888).neurons.set_index("root_id")
    assert n.loc[1, "cell_type"] == "DNp01"
    assert n.loc[1, "side"] == "right"
    assert n.loc[1, "nt_type"] == "ACH"
    assert n.loc[1, "nt_score"] == pytest.approx(0.9)
    assert n.loc[6, "nt_type"] == ""
    assert n[["x", "y", "z"]].isna().all().all()
    assert n.loc[1, "connectivity_tags"] == ()


@pytest.mark.parametrize(
    ("root_id", "expected"),
    [
        (1, "descending"),  # MCNS descending_neuron
        (2, "optic"),  # MCNS ol_intrinsic
        (3, "central"),  # BANC central_brain_intrinsic
        (4, "sensory"),  # MCNS ol_sensory
        (5, "vnc_tbc"),  # to be confirmed: kept as given
        (6, "ventral_nerve_cord"),  # BANC ventral_nerve_cord_intrinsic
    ],
)
def test_super_classes_take_fafbs_spelling(export_dir, root_id, expected):
    n = read_codex(export_dir, BANC_888).neurons.set_index("root_id")
    assert n.loc[root_id, "super_class"] == expected


def test_community_labels_split_and_drop_non_anatomy_keys(export_dir):
    lab = read_codex(export_dir, BANC_888).labels
    by = lab.groupby("root_id")["text"].apply(list).to_dict()
    assert by[1] == ["flywireType: DNp01"]
    assert by[2] == ["flywireType: Tm33", "hemibrainType: Tm33"]
    assert by[3] == ["AMMC B1", "CNS neuron", "soma in brain"]
    assert not lab["text"].str.startswith(("statusLabel", "mancBodyid")).any()
    assert (lab[["user", "affiliation", "date"]] == "").all().all()


def test_pairs_are_thresholded_on_their_total_across_neuropils(export_dir):
    con = read_codex(export_dir, BANC_888).connections
    pairs = set(zip(con["pre"], con["post"], strict=True))
    assert (1, 2) in pairs  # 3 + 2 = 5 over two neuropils
    assert (3, 4) not in pairs  # 4 < 5
    assert (5, 5) not in pairs  # self-connection
    assert len(con[(con["pre"] == 1) & (con["post"] == 2)]) == 2


def test_a_threshold_of_one_keeps_every_pair(export_dir):
    loose = DatasetInfo("banc888", "BANC", "888", "", "", "", "")
    con = read_codex(export_dir, loose).connections
    assert (3, 4) in set(zip(con["pre"], con["post"], strict=True))


def test_blank_connection_transmitters_come_from_the_presynaptic_neuron(export_dir):
    con = read_codex(export_dir, BANC_888).connections.set_index(["pre", "post"])
    assert set(con.loc[(1, 2), "nt_type"]) == {"ACH"}
    assert con.loc[(4, 6), "nt_type"].iloc[0] == "HIST"
    assert con.loc[(6, 1), "nt_type"].iloc[0] == ""  # neuron 6 has no prediction


def test_histamine_is_inhibitory_and_tyramine_unresolved(export_dir):
    sign = read_codex(export_dir, BANC_888).sign_of()
    assert sign[4] == -1
    assert sign[5] == 0
    assert sign[1] == 1


def test_verify_checks_the_export_against_its_own_manifest(export_dir):
    report = verify_dir(export_dir, checksums=True)
    assert report.ok
    assert any("neuron-attributes" in n for n in report.notes)
    (export_dir / "connections_princeton.csv.gz").unlink()
    assert verify_dir(export_dir, checksums=False).missing_required == [
        "connections_princeton.csv.gz"
    ]


def test_the_export_builds_a_graph(export_dir, tmp_path):
    kg = ConnectomeKG(
        dataset_dir(tmp_path / "kg", "banc888"),
        data_dir=export_dir,
        source="codex",
        dataset=BANC_888,
    )
    try:
        kg.build_graph(wipe=True)
        stats = kg.stats()
        assert stats["n_neurons"] == 6
        assert stats["n_pairs"] == 3
    finally:
        kg.close()


@pytest.mark.parametrize("dataset", [BANC_888, MCNS_1])
def test_the_cli_knows_both_releases(dataset):
    assert _dataset(dataset.dataset_id) is dataset
    assert dataset.license == "CC-BY-4.0"
    assert dataset.min_pair_syn == 5


@pytest.mark.parametrize(
    ("abbrev", "region", "name"),
    [
        ("LegNp_T1_L", "VNC", "prothoracic leg neuropil (left)"),
        ("VNC_T2_MesoNm_R", "VNC", "mesothoracic neuromere (right)"),
        ("IntTct", "VNC", "intermediate tectulum"),
        ("ADMN_L", "NERVE", "anterior dorsal mesothoracic nerve (left)"),
        ("cervical_connective", "CV", "cervical connective"),
        ("OL_UNASGD_R", "UNASGD", "unassigned, optic lobe (right)"),
        ("AB_L", "CX", "asymmetric body (left)"),
    ],
)
def test_nerve_cord_neuropils_have_names_and_regions(abbrev, region, name):
    assert neuropil_region(abbrev) == region
    assert neuropil_full_name(abbrev) == name
