"""Shared Click options and the ``open_kg`` helper for connkg commands."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import click

from connectomekg.module import ConnectomeKG
from connectomekg.schema import FAFB_783, DatasetInfo

#: Starting bounds from the fleet boundary-validation standard; widen if a real
#: query needs more.
MAX_K = 100
MAX_HOP = 5

_SOURCE_OPTIONS = (
    click.option(
        "--data-dir",
        default=None,
        type=click.Path(file_okay=False),
        help="Codex release directory (--source codex).",
    ),
    click.option(
        "--source",
        default="codex",
        show_default=True,
        type=click.Choice(["codex", "synthetic"]),
    ),
    click.option("--dataset-id", default=None, help="Dataset id; fafb783 selects FAFB v783."),
    click.option(
        "--n",
        default=1000,
        show_default=True,
        type=click.IntRange(min=1),
        help="Neurons (--source synthetic).",
    ),
    click.option("--seed", default=1, show_default=True, type=int, help="Synthetic seed."),
    click.option(
        "--min-syn",
        default=1,
        show_default=True,
        type=click.IntRange(min=1),
        help="Drop connections below this synapse count.",
    ),
    click.option(
        "--connections-file",
        default=None,
        help="Connections table inside --data-dir (default: auto-detect).",
    ),
    click.option("--embed-neurons", is_flag=True, help="Also embed neuron nodes."),
)


def source_options[F: Callable[..., Any]](fn: F) -> F:
    """Attach the options that say which release a command reads."""
    for option in reversed(_SOURCE_OPTIONS):
        fn = option(fn)
    return fn


@contextmanager
def usage_errors() -> Iterator[None]:
    """Report ``ConnectomeKG``'s boundary validation as a usage error, not a traceback.

    Validation lives in the module's methods so the CLI and the MCP server share
    it; this is the CLI's translation of the ``ValueError`` those methods raise.
    """
    try:
        yield
    except ValueError as exc:
        raise click.UsageError(str(exc)) from exc


def open_kg(
    root: str,
    *,
    data_dir: str | None = None,
    source: str = "codex",
    dataset_id: str | None = None,
    n: int = 1000,
    seed: int = 1,
    min_syn: int = 1,
    connections_file: str | None = None,
    embed_neurons: bool = False,
    progress: Callable[[str], None] | None = None,
) -> ConnectomeKG:
    """Construct a ConnectomeKG from ``--root`` and :func:`source_options`, for
    use as ``with open_kg(...) as kg:`` so ``close()`` always runs.

    :param root: Directory that owns ``.connectomekg/``.
    :param data_dir: Codex release directory.
    :param source: ``"codex"`` or ``"synthetic"``.
    :param dataset_id: Dataset id; ``"fafb783"`` selects the FAFB v783 record.
    :param n: Synthetic neuron count.
    :param seed: Synthetic seed.
    :param min_syn: Drop connections below this synapse count.
    :param connections_file: Connections table name inside ``data_dir``.
    :param embed_neurons: Also embed neuron nodes.
    :param progress: Called with a message at each extraction stage.
    :return: A new ``ConnectomeKG``.
    """
    return ConnectomeKG(
        root,
        data_dir=data_dir,
        source=source,
        dataset=_dataset(dataset_id),
        n_neurons=n,
        seed=seed,
        embed_neurons=embed_neurons,
        min_syn=min_syn,
        connections_file=connections_file,
        progress=progress,
    )


def _dataset(dataset_id: str | None) -> DatasetInfo | None:
    if not dataset_id:
        return None
    if dataset_id == "fafb783":
        return FAFB_783
    return DatasetInfo(
        dataset_id=dataset_id,
        name=dataset_id,
        version="",
        organism="",
        licence="",
        url="",
        citation="",
    )
