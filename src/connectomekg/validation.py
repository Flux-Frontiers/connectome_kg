"""Boundary validation for ConnectomeKG's public entry points.

Per FLEET_STANDARDS (boundary validation, settled 2026-08-24), the KGModule
subclass validates once, in its own ``query()`` / ``pack()`` / lookup methods,
rather than separately in the CLI and the MCP server. Both funnel through those
methods, so one set of checks covers both surfaces and nothing drifts.

This matters beyond CLI ergonomics: the MCP server supports the SSE transport
beyond a trusted local environment, so these are real external inputs. An
unbounded ``hops`` walks most of the brain, and a ``label:`` spec is a regular
expression run over every community label.

Bounds follow the reference implementations (genealogy_kg PR #3, swift_kg):
a starting point sized to cover real result sizes while capping the worst
case, not a specification. Out-of-range values raise rather than clamp: a
truncated result that looks complete is worse than an error.
"""

from __future__ import annotations

import re

__all__ = [
    "MAX_FLOW_PAIRS",
    "MAX_HOP",
    "MAX_K",
    "MAX_LABEL_PATTERN",
    "MAX_LIMIT",
    "MAX_MAX_NODES",
    "MAX_MIN_SYN",
    "MAX_QUERY_LEN",
    "MAX_SCENE_NEURONS",
    "MAX_SKELETON_STEP",
    "bounded_int",
    "normalize_node_id",
    "normalize_spec",
    "require_choice",
    "require_query",
]

#: Search seed count for ``query``/``pack``.
MAX_K = 100
#: Graph expansion hops, and cone depth.
MAX_HOP = 5
#: Nodes in a snippet pack.
MAX_MAX_NODES = 500
#: Rows returned by a listing (neurons per cone hop, partners, edges).
MAX_LIMIT = 500
#: Synapse threshold. The strongest v783 pair has 2,633 synapses.
MAX_MIN_SYN = 10_000
#: Natural-language query, node id or spec length, in characters.
MAX_QUERY_LEN = 500
#: A ``label:`` regex. Label texts are short; a long pattern buys nothing.
MAX_LABEL_PATTERN = 100
#: Neurons drawn in one viz3d scene (connkg quilt / connkg viz3d). A hop-2
#: cone of LC4 alone resolves to 5,998 neurons -- far beyond what reads or
#: renders as individual skeletons.
MAX_SCENE_NEURONS = 500
#: Skeleton simplification stride (connectomekg.skeletons.segments' ``step``).
#: Above this a "simplified" skeleton would drop nearly everything but its
#: structural points.
MAX_SKELETON_STEP = 50
#: Neuropil-to-neuropil flow arcs drawn in one viz3d flow scene. FAFB v783 has
#: 5,786 directed pairs; the top 200 already carry two thirds of all flow.
MAX_FLOW_PAIRS = 500


def bounded_int(name: str, value: int, minimum: int, maximum: int) -> int:
    """Return ``value`` if it lies within ``[minimum, maximum]``, else raise.

    :param name: Parameter name, used in the error message.
    :param value: Value to check.
    :param minimum: Smallest accepted value, inclusive.
    :param maximum: Largest accepted value, inclusive.
    :return: The validated value as an ``int``.
    :raises ValueError: If the value is not an integer or is out of range.
    """
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer, got {value!r}")
    try:
        ivalue = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer, got {value!r}") from exc
    if ivalue != value:
        raise ValueError(f"{name} must be an integer, got {value!r}")
    if not minimum <= ivalue <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}, got {ivalue}")
    return ivalue


def require_query(q: str) -> str:
    """Return a stripped, length-capped query string, or raise.

    :param q: Raw query text.
    :return: The stripped query.
    :raises ValueError: If it is not a string, is empty, or exceeds :data:`MAX_QUERY_LEN`.
    """
    if not isinstance(q, str):
        raise ValueError(f"query must be a string, got {type(q).__name__}")
    stripped = q.strip()
    if not stripped:
        raise ValueError("query must not be empty")
    if len(stripped) > MAX_QUERY_LEN:
        raise ValueError(f"query must be at most {MAX_QUERY_LEN} characters, got {len(stripped)}")
    return stripped


def require_choice(name: str, value: str, choices: tuple[str, ...]) -> str:
    """Return ``value`` if it is one of ``choices``, else raise.

    :param name: Parameter name, used in the error message.
    :param value: Value to check.
    :param choices: Accepted values.
    :return: The validated value.
    :raises ValueError: If ``value`` is not one of ``choices``.
    """
    if value not in choices:
        raise ValueError(f"{name} must be one of {', '.join(choices)}, got {value!r}")
    return value


def _unwrap(raw: str, name: str) -> str:
    if not isinstance(raw, str):
        raise ValueError(f"{name} must be a string, got {type(raw).__name__}")
    # Callers paste ids out of Markdown reports and JSON with the quoting on.
    value = raw.strip().strip("`").strip("'\"").strip()
    if not value:
        raise ValueError(f"{name} must not be empty")
    if len(value) > MAX_QUERY_LEN:
        raise ValueError(f"{name} must be at most {MAX_QUERY_LEN} characters")
    return value


def normalize_node_id(raw: str) -> str:
    """Return a usable node id from the forms callers actually pass.

    An id arrives copied verbatim from an earlier tool result, wrapped in
    backticks or quotes from a Markdown report, or with stray whitespace. All
    three are the same request.

    :param raw: Node id as supplied, e.g. ``"`connectome:fafb783:t:LC4`"``.
    :return: The normalized id.
    :raises ValueError: If nothing usable remains.
    """
    return _unwrap(raw, "node_id")


def normalize_spec(raw: str) -> str:
    """Return a usable neuron spec, checking a ``label:`` regex before it runs.

    A spec is a cell type name, a root id, a neuron node id, or
    ``label:<regex>``. The regex is matched against every community label, so
    it is length-capped and must compile.

    :param raw: Spec as supplied.
    :return: The normalized spec.
    :raises ValueError: If it is empty, too long, or a ``label:`` pattern is
        empty, longer than :data:`MAX_LABEL_PATTERN` or not a valid regex.
    """
    spec = _unwrap(raw, "spec")
    if spec.startswith("label:"):
        pattern = spec[len("label:") :]
        if not pattern:
            raise ValueError("label: spec needs a pattern, e.g. 'label:giant fib'")
        if len(pattern) > MAX_LABEL_PATTERN:
            raise ValueError(
                f"label: pattern must be at most {MAX_LABEL_PATTERN} characters, got {len(pattern)}"
            )
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueError(f"label: pattern is not a valid regex: {exc}") from exc
    return spec
