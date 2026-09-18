"""Boundary validation shared by the CLI, the MCP server and the Python API."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from connectomekg.cli import cli
from connectomekg.validation import (
    MAX_LABEL_PATTERN,
    MAX_QUERY_LEN,
    bounded_int,
    normalize_node_id,
    normalize_spec,
    require_choice,
    require_query,
)


def test_bounded_int_accepts_the_range_and_names_it_when_out():
    assert bounded_int("k", 1, 1, 100) == 1 and bounded_int("k", 100, 1, 100) == 100
    with pytest.raises(ValueError, match="k must be between 1 and 100, got 0"):
        bounded_int("k", 0, 1, 100)
    with pytest.raises(ValueError, match="between 1 and 100, got 101"):
        bounded_int("k", 101, 1, 100)


@pytest.mark.parametrize("bad", [True, 2.5, "5", None])
def test_bounded_int_rejects_non_integers(bad):
    with pytest.raises(ValueError, match="must be an integer"):
        bounded_int("k", bad, 1, 100)


def test_require_query_strips_and_caps():
    assert require_query("  giant fibre  ") == "giant fibre"
    with pytest.raises(ValueError, match="must not be empty"):
        require_query("   ")
    with pytest.raises(ValueError, match=f"at most {MAX_QUERY_LEN}"):
        require_query("x" * (MAX_QUERY_LEN + 1))


def test_require_choice():
    assert require_choice("direction", "up", ("down", "up")) == "up"
    with pytest.raises(ValueError, match="direction must be one of down, up"):
        require_choice("direction", "sideways", ("down", "up"))


def test_ids_pasted_with_quoting_are_normalized():
    for raw in (
        "`connectome:fafb783:t:LC4`",
        "'connectome:fafb783:t:LC4'",
        "  connectome:fafb783:t:LC4 ",
    ):
        assert normalize_node_id(raw) == "connectome:fafb783:t:LC4"
    with pytest.raises(ValueError, match="must not be empty"):
        normalize_node_id("``")


def test_label_specs_are_checked_before_they_run():
    assert normalize_spec("label:giant fib") == "label:giant fib"
    assert normalize_spec("LC4") == "LC4"
    with pytest.raises(ValueError, match="needs a pattern"):
        normalize_spec("label:")
    with pytest.raises(ValueError, match="not a valid regex"):
        normalize_spec("label:(")
    with pytest.raises(ValueError, match=f"at most {MAX_LABEL_PATTERN}"):
        normalize_spec("label:" + "a" * (MAX_LABEL_PATTERN + 1))


def test_module_methods_enforce_the_bounds(kg):
    with pytest.raises(ValueError, match="hops must be between 0 and 5"):
        kg.cone("LC4", hops=6)
    with pytest.raises(ValueError, match="direction must be one of"):
        kg.type_partners("LC4", direction="sideways")
    with pytest.raises(ValueError, match="rel must be one of"):
        kg.node_edges("connectome:synthetic:t:LC4", rel="NOT_A_REL")
    with pytest.raises(ValueError, match="kind must be one of"):
        kg.find_nodes("LC", kind="not_a_kind")
    with pytest.raises(ValueError, match="not a valid regex"):
        kg.strongest_path("label:(", "MN9")


def test_cli_reports_a_bad_spec_as_a_usage_error(kg, kg_root):
    res = CliRunner().invoke(
        cli, ["--root", str(kg_root), "path", "--from", "label:(", "--to", "MN9"]
    )
    assert res.exit_code == 2 and "not a valid regex" in res.output
