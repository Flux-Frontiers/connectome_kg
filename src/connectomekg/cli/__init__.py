"""connkg -- Click entry points.

The root group is importable as ``from connectomekg.cli import cli``; importing
this package registers every command on it.
"""

from connectomekg.cli import (  # noqa: F401
    cmd_analyze,
    cmd_build,
    cmd_data,
    cmd_query,
    cmd_snapshot,
    cmd_viz,
)
from connectomekg.cli.group import cli

__all__ = ["cli"]
