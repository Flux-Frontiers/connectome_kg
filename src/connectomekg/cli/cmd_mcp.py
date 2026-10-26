"""``connkg mcp`` -- the fleet's standard MCP command, from :mod:`kg_utils.mcp`.

::

    connkg [--root DIR] [--dataset ID] mcp [--repo DIR] [--db FILE]
           [--vectors FILE] [--model NAME]
           [--transport stdio|streamable-http] [--host H] [--port N] [--manifest]

The dataset is connkg's own ``--dataset`` (or ``$CONNKG_DATASET``, or the only
one built). ``--repo`` defaults to connkg's ``--root``; it may also name a
dataset directory itself. Registering the command imports neither ``mcp`` nor
the server module, so every other ``connkg`` command starts as fast as before.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import click
from kg_utils.mcp import add_mcp_command

from connectomekg.cli.group import cli

if TYPE_CHECKING:
    from kg_utils.mcp import KGServer


def _build_server(repo: Path, db: Path | None, vectors: Path | None, model: str | None) -> KGServer:
    from connectomekg.mcp_server import build_server  # noqa: PLC0415 -- keep mcp lazy

    ctx = click.get_current_context(silent=True)
    obj = (ctx.find_root().obj if ctx else None) or {}
    root = obj.get("root")
    if root and root != "." and repo == Path(".").resolve():
        repo = Path(root).resolve()
    return build_server(repo, db, vectors, model, dataset=obj.get("dataset"))


mcp_command = add_mcp_command(cli, _build_server)
