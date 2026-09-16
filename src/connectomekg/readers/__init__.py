"""Readers: one per release format, all producing :class:`~connectomekg.schema.ConnectomeTables`."""

from connectomekg.readers.codex import read_codex
from connectomekg.readers.synthetic import synthetic_tables, write_codex_dir

__all__ = ["read_codex", "synthetic_tables", "write_codex_dir"]
