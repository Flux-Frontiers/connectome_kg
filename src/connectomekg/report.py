"""Build reports: one Markdown record per ``connkg build`` run.

Each run writes ``<root>/reports/build_<UTC timestamp>.md``, following the
per-run ingest reports gutenberg_kg writes. The report is provenance, not a
log: what ran (package versions, git commit, options), on what (each input
file with its SHA-256 and whether it matches the manifest), where (host,
platform, Python), and what came out (counts, database size, time per stage,
peak memory). A failed build still gets one, marked FAILED.

Reports are not tracked by default; keep a run worth keeping with
``git add -f reports/build_<timestamp>.md``.
"""

from __future__ import annotations

import importlib.metadata
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
    """Peak resident set size of this process so far, in bytes.

    ``ru_maxrss`` is reported in bytes on macOS and in kilobytes on Linux.
    """
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return rss if sys.platform == "darwin" else rss * 1024


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
        if dataset.licence:
            lines.append(f"Licence {dataset.licence}.")
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
