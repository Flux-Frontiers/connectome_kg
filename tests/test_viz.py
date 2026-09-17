"""2-D views: the partner network and the partners chart."""

from __future__ import annotations

import json
import re

import pytest
from click.testing import CliRunner

pytest.importorskip("pyvis")
pytest.importorskip("plotly")

from connectomekg import viz  # noqa: E402 - after the importorskip guards
from connectomekg.cli import cli  # noqa: E402


def test_network_centres_the_type_and_labels_edges_with_counts(kg):
    html = viz.type_network_html(kg, "LC4", limit=5)
    assert html.lstrip().lower().startswith("<html") or "<!doctype html" in html.lower()
    partners = kg.type_partners("LC4", direction="down", limit=5)
    assert partners and all(p["cell_type"] in html for p in partners)
    top = partners[0]
    assert f"{top['syn_count']:,} {top['nt_type']}" in html
    assert viz.SIGN_COLOR[1] in html  # the planted escape circuit is cholinergic


def _drawn_edges(html: str) -> set[tuple[str, str]]:
    match = re.search(r"edges = new vis\.DataSet\((\[.*?\])\);", html, re.S)
    assert match, "no vis.js edge dataset in the page"
    return {(e["from"], e["to"]) for e in json.loads(match.group(1))}


def test_network_drops_partner_edges_weaker_than_the_ring(kg):
    downs = kg.type_partners("LC4", direction="down", limit=3)
    ups = kg.type_partners("LC4", direction="up", limit=3)
    floor = min(p["syn_count"] for p in downs + ups)
    drawn = _drawn_edges(viz.type_network_html(kg, "LC4", limit=3))

    prefix = "connectome:synthetic:t:"
    center = prefix + "LC4"
    shown = {prefix + p["cell_type"] for p in downs + ups} | {center}
    expected, dropped = set(), set()
    for e in kg.store.edges_within(shown):
        if e["rel"] != "TYPE_SYNAPSES_TO":
            continue
        ev = e["evidence"] if isinstance(e["evidence"], dict) else json.loads(e["evidence"])
        pair = (e["src"], e["dst"])
        if center in pair or ev["syn_count"] >= floor:
            expected.add(pair)
        else:
            dropped.add(pair)
    assert dropped, "fixture has no weak partner edge, so this test would check nothing"
    assert drawn == expected
    assert (prefix + "LC4", prefix + downs[0]["cell_type"]) in drawn
    assert not drawn & dropped


def test_partners_chart_puts_inputs_left_and_outputs_right(kg):
    figure = viz.partners_figure(kg, "LC4", limit=5)
    inputs, outputs = figure.data
    assert all(x < 0 for x in inputs.x) and all(x > 0 for x in outputs.x)
    assert any("DNp01" in label for label in outputs.y)


def test_unknown_type_is_an_error_that_suggests_near_names(kg):
    with pytest.raises(ValueError, match="no cell type named 'LC'.*LC4"):
        viz.type_network_html(kg, "LC")


@pytest.mark.parametrize("view", ["network", "partners"])
def test_cli_writes_a_self_contained_file(kg, tmp_path, view):
    out = tmp_path / f"lc4_{view}.html"
    res = CliRunner().invoke(
        cli, ["--root", str(kg.repo_root), "viz", "LC4", "--view", view, "-o", str(out)]
    )
    assert res.exit_code == 0, res.output
    assert out.stat().st_size > 10_000 and "LC4" in out.read_text()


def test_cli_reports_an_unknown_type_as_a_usage_error(kg, tmp_path):
    res = CliRunner().invoke(
        cli, ["--root", str(kg.repo_root), "viz", "NOPE", "-o", str(tmp_path / "x.html")]
    )
    assert res.exit_code == 2 and "no cell type named 'NOPE'" in res.output
