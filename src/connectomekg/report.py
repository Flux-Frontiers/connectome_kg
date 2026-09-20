"""Run reports: one Markdown record per long pass that writes something.

Two commands write one, each into ``<root>/reports/``, following the per-run
ingest reports gutenberg_kg writes:

* ``connkg build`` -- ``build_<UTC timestamp>.md``, via :func:`write_build_report`.
* ``connkg skeletons`` -- ``skeletons_<UTC timestamp>.md``, via
  :func:`write_skeletons_report`.

A report is provenance, not a log: what ran (package versions, git commit,
options), on what (the inputs, with digests where there is a manifest to
check them against), where (host, platform, Python), and what came out
(counts, sizes, timings, peak memory). A pass that fails still gets one,
marked FAILED.

``connkg skeletons`` earns one for a reason ``connkg build`` does not: it
writes somas into an *already built* ``graph.sqlite``, so the graph a snapshot
measures afterwards is not the one the build report describes. Its report is
the only record of which download those somas came from, and at which step.

Reports are not tracked by default; keep a run worth keeping with
``git add -f reports/<name>.md``.
"""

from __future__ import annotations

import importlib.metadata
import os
import platform
import resource
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kg_utils.specs import BuildStats

from connectomekg.manifest import FAFB_783_FILES, sha256_of
from connectomekg.readers.codex import find_connections_file
from connectomekg.schema import DatasetInfo
from connectomekg.skeleton_cache import CacheReport
from connectomekg.skeletons import SKELETON_SUBDIR


@dataclass
class BuildRun:
    """Context and stage timings for one build, filled in while it runs.

    :param root: Directory that owns ``.connectomekg/``; reports go in its ``reports/``.
    :param options: The build options as given, recorded verbatim.
    """

    root: Path
    options: dict[str, Any]
    started: datetime = field(default_factory=lambda: datetime.now(UTC))
    stages: list[tuple[str, float]] = field(default_factory=list)
    _t0: float = field(default_factory=time.perf_counter, repr=False)

    def stage(self, message: str) -> None:
        """Record a progress message and when it arrived; usable as a ``progress`` callback.

        :param message: The extractor's progress message.
        """
        self.stages.append((message, time.perf_counter() - self._t0))

    @property
    def elapsed(self) -> float:
        """Seconds since the run started."""
        return time.perf_counter() - self._t0


def peak_rss_bytes() -> int:
    """Peak resident set size of this process and its finished children, in bytes.

    Children count because ``connkg skeletons -j`` does its reading in a pool:
    reporting the parent alone would say 230 MB for a pass whose real
    footprint was several gigabytes. ``RUSAGE_CHILDREN`` covers only children
    already reaped, which is every worker by the time a report is written, and
    is the peak of any one of them rather than their sum -- so this is the
    high-water mark of the largest single process, not of the machine.

    ``ru_maxrss`` is reported in bytes on macOS and in kilobytes on Linux.
    """
    usage = max(
        resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
    )
    return usage if sys.platform == "darwin" else usage * 1024


def write_build_report(
    run: BuildRun,
    *,
    stats: BuildStats | None,
    dataset: DatasetInfo | None,
    db_path: Path | None,
    error: BaseException | None = None,
) -> Path:
    """Write the report for a finished or failed build.

    :param run: The run's context and stage timings.
    :param stats: What the build wrote, or ``None`` if it failed first.
    :param dataset: Provenance record of the release built, if it was loaded.
    :param db_path: The graph database path, if known.
    :param error: The exception that ended the build, if any.
    :return: Path of the report written.
    """
    elapsed = run.elapsed
    peak = peak_rss_bytes()
    reports = run.root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    path = reports / f"build_{run.started.strftime('%Y-%m-%d_%H%M%S')}.md"

    status = "SUCCESS" if error is None else f"FAILED: {type(error).__name__}: {error}"
    lines = [
        "# ConnectomeKG Build Report",
        "",
        f"**Date:** {run.started.strftime('%Y-%m-%d %H:%M:%S')} UTC  ",
        f"**Elapsed:** {_duration(elapsed)}  ",
        f"**Peak memory:** {_bytes(peak)} resident  ",
        f"**Status:** {status}  ",
        f"**Host:** {socket.gethostname()} / {platform.system()} {platform.release()}"
        f" / {platform.machine()}  ",
        f"**Python:** {sys.version.split()[0]}  ",
        f"**connectome-kg:** {_version('connectome-kg')}{_git_suffix()}  ",
        f"**kgmodule-utils:** {_version('kgmodule-utils')}",
        "",
        "## Options",
        "",
        "| option | value |",
        "|---|---|",
    ]
    lines += [f"| {k} | `{v}` |" for k, v in run.options.items()]

    if dataset is not None:
        lines += [
            "",
            "## Dataset",
            "",
            f"{dataset.name}"
            + (f" version {dataset.version}" if dataset.version else "")
            + f" (`{dataset.dataset_id}`)"
            + (f", {dataset.organism}" if dataset.organism else "")
            + ".",
        ]
        if dataset.license:
            lines.append(f"License {dataset.license}.")
        if dataset.citation:
            lines += ["", f"Cite: {dataset.citation}"]

    lines += ["", "## Inputs", ""]
    data_dir = run.options.get("data_dir")
    if run.options.get("source") == "synthetic" or not data_dir:
        lines.append(
            f"Synthetic connectome, {run.options.get('n')} neurons, seed {run.options.get('seed')}."
        )
    else:
        lines += _input_rows(Path(data_dir), run.options.get("connections_file"))

    lines += ["", "## Stages", "", "| stage | started | took |", "|---|---:|---:|"]
    # Indented messages are counters inside a stage, not stages of their own.
    marks = [(m, t) for m, t in run.stages if not m.startswith(" ")]
    for i, (message, t) in enumerate(marks):
        end = marks[i + 1][1] if i + 1 < len(marks) else elapsed
        lines.append(f"| {message} | {_duration(t)} | {_duration(end - t)} |")

    if stats is not None:
        lines += [
            "",
            "## Output",
            "",
            f"Database `{db_path}`"
            + (f", {_bytes(db_path.stat().st_size)}" if db_path and db_path.exists() else "")
            + ".",
            "",
            f"{stats.total_nodes:,} nodes, {stats.total_edges:,} edges"
            + (f", {stats.indexed_rows:,} rows embedded" if stats.indexed_rows else "")
            + ".",
            "",
            "| node kind | count |",
            "|---|---:|",
        ]
        lines += [f"| {k} | {v:,} |" for k, v in sorted(stats.node_counts.items())]
        lines += ["", "| relation | count |", "|---|---:|"]
        lines += [f"| {k} | {v:,} |" for k, v in sorted(stats.edge_counts.items())]

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_skeletons_report(
    run: BuildRun,
    *,
    cache: CacheReport | None,
    cache_path: Path | None,
    db_path: Path | None,
    n_somas_written: int | None,
    error: BaseException | None = None,
) -> Path:
    """Write the report for a finished or failed ``connkg skeletons`` pass.

    :param run: The run's context; its ``options`` are recorded verbatim.
    :param cache: What the pass read and wrote, or ``None`` if it failed first.
    :param cache_path: The Parquet cache written, if it got that far.
    :param db_path: The graph the somas went into, if known.
    :param n_somas_written: Neuron nodes back-filled, or ``None`` when the
        graph was left alone (``--no-somas``, or a failure before that point).
    :param error: The exception that ended the pass, if any.
    :return: Path of the report written.
    """
    elapsed = run.elapsed
    peak = peak_rss_bytes()
    reports = run.root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    path = reports / f"skeletons_{run.started.strftime('%Y-%m-%d_%H%M%S')}.md"

    status = "SUCCESS" if error is None else f"FAILED: {type(error).__name__}: {error}"
    lines = [
        "# ConnectomeKG Skeleton Cache Report",
        "",
        f"**Date:** {run.started.strftime('%Y-%m-%d %H:%M:%S')} UTC  ",
        f"**Elapsed:** {_duration(elapsed)}  ",
        f"**Peak memory:** {_bytes(peak)} resident  ",
        f"**Status:** {status}  ",
        f"**Host:** {socket.gethostname()} / {platform.system()} {platform.release()}"
        f" / {platform.machine()}  ",
        f"**Python:** {sys.version.split()[0]}  ",
        f"**connectome-kg:** {_version('connectome-kg')}{_git_suffix()}  ",
        f"**kgmodule-utils:** {_version('kgmodule-utils')}",
        "",
        "## Options",
        "",
        "| option | value |",
        "|---|---|",
    ]
    lines += [f"| {k} | `{v}` |" for k, v in run.options.items()]

    lines += ["", "## Input", ""]
    data_dir = run.options.get("data_dir")
    lines += _skeleton_input_rows(Path(data_dir)) if data_dir else ["No skeleton directory given."]

    lines += ["", "## Output", ""]
    if cache is None:
        lines.append("Nothing was written.")
    else:
        rate = cache.n_cached / elapsed if elapsed > 0 else 0.0
        lines += [
            f"Cache `{cache_path}`"
            + (f", {_bytes(cache.bytes_written)}" if cache.bytes_written else "")
            + f", simplified at step {cache.step}.",
            "",
            "| measure | count |",
            "|---|---:|",
            f"| neurons cached | {cache.n_cached:,} |",
            f"| points kept | {cache.n_points:,} |",
            f"| with a real soma (SWC label 1) | {cache.n_soma:,} |",
            f"| fell back to a root point | {cache.n_cached - cache.n_soma:,} |",
            f"| no skeleton file | {cache.n_missing:,} |",
            f"| unreadable skeleton file | {cache.n_unreadable:,} |",
            f"| shards written | {cache.n_shards:,} |",
            "",
            f"{rate:.0f} skeletons per second.",
        ]

    lines += ["", "## Graph", ""]
    if n_somas_written is None:
        lines.append(
            f"Graph `{db_path}` was not modified"
            + (" (--no-somas)." if run.options.get("no_somas") else ".")
        )
    else:
        lines += [
            f"Graph `{db_path}`"
            + (f", {_bytes(db_path.stat().st_size)}" if db_path and db_path.exists() else "")
            + ".",
            "",
            f"{n_somas_written:,} neuron nodes gained `soma_x`, `soma_y`, `soma_z` and "
            "`has_soma`, written alongside the marked point in `x`/`y`/`z` rather than "
            "over it.",
            "",
            "Snapshots taken before this pass measured a graph without those keys.",
        ]

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _skeleton_input_rows(data_dir: Path) -> list[str]:
    """Describe the SWC download read, without a manifest to check it against.

    The skeleton download has no recorded digests -- ``FAFB_783_FILES`` covers
    the CSV tables only -- and hashing 31 GB would cost more than the pass
    itself. The file count and total size are what can honestly be recorded.
    """
    directory = data_dir / SKELETON_SUBDIR
    if not directory.is_dir():
        return [f"No skeleton directory at `{directory.resolve()}`."]
    n = total = 0
    with os.scandir(directory) as entries:
        for entry in entries:
            if entry.is_file() and entry.name.endswith(".swc"):
                n += 1
                total += entry.stat().st_size
    return [
        f"Skeleton directory `{directory.resolve()}`.",
        "",
        f"{n:,} `.swc` files, {_bytes(total)} total. No digests: the download has no "
        "recorded checksums, and hashing it would cost more than reading it.",
    ]


def _input_rows(data_dir: Path, connections_file: str | None) -> list[str]:
    try:
        con = (data_dir / connections_file) if connections_file else find_connections_file(data_dir)
    except FileNotFoundError:
        con = None
    lines = [
        f"Release directory `{data_dir.resolve()}`.",
        "",
        "| file | size | SHA-256 | against the manifest |",
        "|---|---:|---|---|",
    ]
    for f in FAFB_783_FILES:
        name, recorded = f.name, f.sha256
        if name == "connections_princeton.csv.gz" and con is not None and con.name != name:
            name, recorded = con.name, None
        p = data_dir / name
        if not p.is_file():
            lines.append(f"| {name} | | | absent |")
            continue
        digest = sha256_of(p)
        if recorded is None:
            verdict = "no recorded digest"
        elif digest == recorded:
            verdict = "matches"
        else:
            verdict = "differs (portal drift)"
        lines.append(f"| {name} | {_bytes(p.stat().st_size)} | `{digest}` | {verdict} |")
    return lines


def _version(package: str) -> str:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return "not installed"


def _git_suffix() -> str:
    """Branch and commit of the source tree this code runs from, if it is a git checkout."""
    src = Path(__file__).resolve().parent

    def git(*args: str) -> str:
        try:
            out = subprocess.run(
                ["git", *args], cwd=src, capture_output=True, text=True, check=True, timeout=5
            )
        except (OSError, subprocess.SubprocessError):
            return ""
        return out.stdout.strip()

    commit = git("rev-parse", "--short", "HEAD")
    if not commit:
        return ""
    dirty = ", uncommitted changes" if git("status", "--porcelain") else ""
    return f" ({git('rev-parse', '--abbrev-ref', 'HEAD')} @ {commit}{dirty})"


def _duration(seconds: float) -> str:
    m, s = divmod(int(round(seconds)), 60)
    return f"{m}m {s:02d}s" if m else f"{seconds:.1f}s"


def _bytes(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} GB"
