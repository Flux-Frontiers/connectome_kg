"""Neuroglancer links: the URL's state, the module method, and ``connkg link``."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import unquote

import pytest
from click.testing import CliRunner

from connectomekg import ConnectomeKG
from connectomekg.cli import cli
from connectomekg.datasets import dataset_dir
from connectomekg.neuroglancer import (
    NEUROGLANCER_VIEWER,
    SPEC_COLORS,
    has_public_source,
    neuroglancer_url,
)
from connectomekg.readers.synthetic import synthetic_tables
from connectomekg.schema import FAFB_783


def state_of(url: str) -> dict:
    """Decode the Neuroglancer state in a link's fragment."""
    head, _, frag = url.partition("#!")
    assert head == NEUROGLANCER_VIEWER + "/"
    return json.loads(unquote(frag))


def neurons_layer(state: dict) -> dict:
    return next(layer for layer in state["layers"] if layer["name"] == "neurons")


@pytest.fixture(scope="module")
def fafb_root(tmp_path_factory) -> Path:
    """A ``--root`` holding a small synthetic graph labeled as FAFB v783.

    Fresh tables, not the session ``tables`` fixture, since this relabels them.
    """
    root = tmp_path_factory.mktemp("ngl")
    tables = synthetic_tables(400, seed=5)
    tables.dataset = FAFB_783
    with ConnectomeKG(dataset_dir(root, "fafb783"), tables=tables) as kg:
        kg.build_graph(wipe=True)
    return root


@pytest.fixture
def fafb_kg(fafb_root):
    with ConnectomeKG(dataset_dir(fafb_root, "fafb783")) as kg:
        yield kg


def test_url_selects_root_ids_on_the_public_v783_segmentation():
    state = state_of(neuroglancer_url("fafb783", [[3, 1], [2]]))
    layer = neurons_layer(state)
    assert layer["source"]["url"] == "precomputed://gs://flywire_v141_m783"
    assert layer["segments"] == ["1", "2", "3"]
    assert layer["segmentColors"] == {"1": SPEC_COLORS[0], "3": SPEC_COLORS[0], "2": SPEC_COLORS[1]}
    assert state["layout"] == "3d"
    assert state["dimensions"]["z"] == [pytest.approx(4e-8), "m"]


def test_url_refuses_a_dataset_without_a_public_source():
    assert has_public_source("fafb783") and not has_public_source("synthetic")
    with pytest.raises(ValueError, match="no public Neuroglancer source"):
        neuroglancer_url("synthetic", [[1]])
    with pytest.raises(ValueError, match="at most 7 specs"):
        neuroglancer_url("fafb783", [[i] for i in range(len(SPEC_COLORS) + 1)])


def test_link_colours_each_spec_and_counts_its_neurons(fafb_kg):
    res = fafb_kg.neuroglancer_link(["LC4", "DNp01"])
    lc4, dnp01 = res["specs"]
    assert (lc4["spec"], lc4["count"], lc4["shown"], lc4["color"]) == ("LC4", 8, 8, SPEC_COLORS[0])
    assert dnp01["color"] == SPEC_COLORS[1] and dnp01["count"] >= 1
    layer = neurons_layer(state_of(res["url"]))
    roots = {nid.rsplit(":", 1)[1] for nid in fafb_kg.neurons_of("LC4")}
    assert roots <= set(layer["segments"])
    assert len(layer["segments"]) == lc4["shown"] + dnp01["shown"]


def test_link_limit_caps_the_neurons_shown_not_the_count(fafb_kg):
    (lc4,) = fafb_kg.neuroglancer_link(["LC4"], limit=3)["specs"]
    assert lc4["count"] == 8 and lc4["shown"] == 3


@pytest.mark.parametrize(
    ("specs", "limit", "message"),
    [
        ([], 200, "non-empty list"),
        ("LC4", 200, "non-empty list"),
        (["LC4"] * 8, 200, "specs must be between 1 and 7"),
        (["LC4"], 0, "limit must be between 1 and 500"),
        (["NOPE"], 200, "no neurons match NOPE"),
    ],
)
def test_link_rejects_bad_arguments(fafb_kg, specs, limit, message):
    with pytest.raises(ValueError, match=message):
        fafb_kg.neuroglancer_link(specs, limit=limit)


def test_link_on_a_dataset_without_a_public_source(kg):
    with pytest.raises(ValueError, match="no public Neuroglancer source for dataset 'synthetic'"):
        kg.neuroglancer_link(["LC4"])


def test_cli_link_prints_only_the_url_on_stdout(fafb_root):
    res = CliRunner().invoke(cli, ["--root", str(fafb_root), "link", "LC4", "--limit", "2"])
    assert res.exit_code == 0, res.output
    assert neurons_layer(state_of(res.stdout.strip()))["segments"]
    assert "LC4: 8 neurons, first 2 shown" in res.stderr


def test_cli_link_reports_no_match_as_a_usage_error(fafb_root):
    res = CliRunner().invoke(cli, ["--root", str(fafb_root), "link", "NOPE"])
    assert res.exit_code == 2 and "no neurons match NOPE" in res.output
