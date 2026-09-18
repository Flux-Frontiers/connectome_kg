"""One knowledge graph per connectome release, each in its own directory.

Follows GutenbergKG's corpus layout (``corpus/<genre>/<book>/.dockg/``): every
dataset owns a complete store, so releases never share a graph, a vector index
or a snapshot history::

    <root>/
      connectomes/
        fafb783/
          .connectomekg/
            graph.sqlite
            vectors.sqlite
            snapshots/
        synthetic/
          .connectomekg/...

A :class:`~connectomekg.module.ConnectomeKG` is opened on a dataset directory,
``<root>/connectomes/<dataset_id>``, which is its ``repo_root``.
"""

from __future__ import annotations

import re
from pathlib import Path

#: Directory under ``--root`` that holds one subdirectory per dataset.
DATASETS_DIR = "connectomes"
#: Store directory inside each dataset directory.
STORE_DIR = ".connectomekg"
#: Dataset a codex build writes to when none is named.
DEFAULT_CODEX_DATASET = "fafb783"
#: Dataset a synthetic build writes to when none is named.
DEFAULT_SYNTHETIC_DATASET = "synthetic"

_DATASET_ID = re.compile(r"[a-z0-9][a-z0-9_.-]{0,63}")


def validate_dataset_id(dataset_id: str) -> str:
    """Check a dataset id is safe to use as a directory name.

    :param dataset_id: Candidate id, e.g. ``fafb783``.
    :return: The id unchanged.
    :raises ValueError: When it is not 1-64 lowercase letters, digits, ``_``,
        ``.`` or ``-``, starting with a letter or digit.
    """
    if not _DATASET_ID.fullmatch(dataset_id):
        raise ValueError(
            f"invalid dataset id {dataset_id!r}: use 1-64 lowercase letters, digits, "
            "'_', '.' or '-', starting with a letter or digit"
        )
    return dataset_id


def dataset_dir(root: str | Path, dataset_id: str) -> Path:
    """The directory that owns one dataset's ``.connectomekg/``.

    :param root: Directory holding ``connectomes/``.
    :param dataset_id: Dataset id.
    :return: ``<root>/connectomes/<dataset_id>``.
    """
    return Path(root) / DATASETS_DIR / validate_dataset_id(dataset_id)


def graph_path(root: str | Path, dataset_id: str) -> Path:
    """Path to one dataset's graph database.

    :param root: Directory holding ``connectomes/``.
    :param dataset_id: Dataset id.
    :return: ``<root>/connectomes/<dataset_id>/.connectomekg/graph.sqlite``.
    """
    return dataset_dir(root, dataset_id) / STORE_DIR / "graph.sqlite"


def scan_datasets(root: str | Path) -> list[str]:
    """Ids of every dataset under ``root`` that has a built graph, sorted.

    :param root: Directory holding ``connectomes/``.
    :return: Dataset ids; empty when nothing is built.
    """
    base = Path(root) / DATASETS_DIR
    if not base.is_dir():
        return []
    return sorted(
        d.name
        for d in base.iterdir()
        if d.is_dir()
        and _DATASET_ID.fullmatch(d.name)
        and (d / STORE_DIR / "graph.sqlite").is_file()
    )


def resolve_dataset(
    root: str | Path, dataset_id: str | None = None, *, build_source: str | None = None
) -> str:
    """Pick the dataset a command works on.

    A named dataset is used as given. A build without one writes to the
    source's default (``fafb783`` for codex, ``synthetic`` for synthetic).
    Anything else uses the only built dataset, and refuses to guess between
    several.

    :param root: Directory holding ``connectomes/``.
    :param dataset_id: Dataset named by the caller, or ``None``.
    :param build_source: The build's ``--source`` when building, else ``None``.
    :return: A validated dataset id.
    :raises ValueError: When no dataset is named and none, or more than one, is built.
    """
    if dataset_id:
        return validate_dataset_id(dataset_id)
    if build_source is not None:
        return DEFAULT_SYNTHETIC_DATASET if build_source == "synthetic" else DEFAULT_CODEX_DATASET
    built = scan_datasets(root)
    if len(built) == 1:
        return built[0]
    if built:
        raise ValueError(
            f"{len(built)} datasets are built under {Path(root) / DATASETS_DIR}: "
            f"{', '.join(built)}; name one with --dataset"
        )
    legacy = Path(root) / STORE_DIR
    dest = dataset_dir(root, DEFAULT_CODEX_DATASET) / STORE_DIR
    hint = (
        f"; a graph from before per-dataset stores is in {legacy}. Move it with:\n"
        f"  mkdir -p {dest} && mv {legacy}/*.sqlite* {dest}/"
        if (legacy / "graph.sqlite").is_file()
        else "; run `connkg build` first"
    )
    raise ValueError(f"no dataset is built under {Path(root) / DATASETS_DIR}{hint}")
