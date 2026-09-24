"""Readers: one per release format, all producing :class:`~connectomekg.schema.ConnectomeTables`."""

from connectomekg.readers.codex import (
    CONNECTIONS_CANDIDATES,
    find_connections_file,
    is_attribute_export,
    read_codex,
)
from connectomekg.readers.synthetic import min_neurons, synthetic_tables, write_codex_dir

__all__ = [
    "CONNECTIONS_CANDIDATES",
    "find_connections_file",
    "is_attribute_export",
    "min_neurons",
    "read_codex",
    "synthetic_tables",
    "write_codex_dir",
]
