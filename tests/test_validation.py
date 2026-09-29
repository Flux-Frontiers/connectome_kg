"""Boundary validation shared by the CLI, the MCP server and the Python API."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from connectomekg.cli import cli
from connectomekg.validation import (
    MAX_LABEL_PATTERN,
    MAX_QUERY_LEN,
    normalize_node_id,
    normalize_spec,
    require_choice,
)


@pytest.mark.parametrize("method", ["query", "pack"])
def test_search_bounds_come_from_the_sdk_with_connectomes_query_cap(kg, method):
    """Bad arguments are reported before a missing vector index."""
    search = getattr(kg, method)
    with pytest.raises(ValueError, match=f"at most {MAX_QUERY_LEN}"):
        search("x" * (MAX_QUERY_LEN + 1))
    with pytest.raises(ValueError, match="must not be empty"):
        search("   ")
    with pytest.raises(ValueError, match="k must be an integer"):
        search("giant fiber", k=True)
    with pytest.raises(ValueError, match="hop must be between 0 and 5"):
        search("giant fiber", hop=6)
    with pytest.raises(ValueError, match="max_nodes must be between 1 and 500"):
        search("giant fiber", max_nodes=501)


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
