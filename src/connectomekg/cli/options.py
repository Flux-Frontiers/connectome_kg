"""Shared Click options and the ``open_kg`` helper for connkg commands."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import click

from connectomekg.datasets import dataset_dir, resolve_dataset
from connectomekg.module import ConnectomeKG
from connectomekg.readers.synthetic import SYNTHETIC
from connectomekg.schema import FAFB_783, DatasetInfo

#: Provenance records for the dataset ids connkg knows by name.
_KNOWN_DATASETS = {d.dataset_id: d for d in (FAFB_783, SYNTHETIC)}

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
    dataset: str | None = None,
    building: bool = False,
    data_dir: str | None = None,
    source: str = "codex",
    n: int = 1000,
    seed: int = 1,
    min_syn: int = 1,
    connections_file: str | None = None,
    embed_neurons: bool = False,
    progress: Callable[[str], None] | None = None,
) -> ConnectomeKG:
    """Construct a ConnectomeKG from ``--root`` and :func:`source_options`, for
    use as ``with open_kg(...) as kg:`` so ``close()`` always runs.

    The graph lives in ``<root>/connectomes/<dataset>/.connectomekg/``; see
    :func:`connectomekg.datasets.resolve_dataset` for how an omitted
    ``dataset`` is chosen.

    :param root: Directory holding ``connectomes/``.
    :param dataset: Dataset id, the ``--dataset`` option.
    :param building: The caller is ``connkg build``, so an omitted dataset
        defaults from ``source`` rather than from what is already built.
    :param data_dir: Codex release directory.
    :param source: ``"codex"`` or ``"synthetic"``.
    :param n: Synthetic neuron count.
    :param seed: Synthetic seed.
    :param min_syn: Drop connections below this synapse count.
    :param connections_file: Connections table name inside ``data_dir``.
    :param embed_neurons: Also embed neuron nodes.
    :param progress: Called with a message at each extraction stage.
    :return: A new ``ConnectomeKG``.
    :raises click.UsageError: When the dataset id is invalid or cannot be chosen.
    """
    with usage_errors():
        dataset_id = resolve_dataset(root, dataset, build_source=source if building else None)
    return ConnectomeKG(
        dataset_dir(root, dataset_id),
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


def _dataset(dataset_id: str) -> DatasetInfo:
    if dataset_id in _KNOWN_DATASETS:
        return _KNOWN_DATASETS[dataset_id]
    return DatasetInfo(
        dataset_id=dataset_id,
        name=dataset_id,
        version="",
        organism="",
        license="",
        url="",
        citation="",
    )
