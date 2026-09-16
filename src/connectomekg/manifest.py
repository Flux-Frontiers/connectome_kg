"""The FlyWire FAFB v783 Codex release: which files a build reads, and their checksums.

The Codex download portal (https://codex.flywire.ai/api/download) needs a free
account, so fetching is a documented manual step. This module lets a build
refuse a directory that does not look like the release it claims to be.

The SHA-256 values were recorded from an independent v783 download in August
2026 (vaibhavkedarisetti/fruit-fly-lab, DATA_SOURCES.md). They are expected
values, not authority: :func:`verify_dir` reports mismatches, and only raises
when asked to be strict.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ReleaseFile:
    """One file of a Codex release.

    :param name: File name inside the download directory.
    :param role: What the build uses it for.
    :param required: Whether a build can proceed without it.
    :param sha256: Expected digest, or ``None`` when not recorded.
    """

    name: str
    role: str
    required: bool
    sha256: str | None = None


FAFB_783_FILES: tuple[ReleaseFile, ...] = (
    ReleaseFile(
        "neurons.csv.gz",
        "root ids, neurotransmitter prediction and score",
        True,
        "6a6b3759e635f0f35a677d169052362131ec61d95f55919298b55c43fce4e719",
    ),
    ReleaseFile(
        "classification.csv.gz",
        "flow, super class, class, sub class, cell type, hemilineage, side, nerve",
        True,
        "e946b552f4056dfc977707be0674609832c3f64332a22d69dc0d9615e7aae663",
    ),
    ReleaseFile(
        "connections_princeton.csv.gz",
        "edges: (pre, post, neuropil) rows with syn_count and nt_type, 5-synapse threshold",
        True,
        "445f996bf6c4b1803b9ba186189138a3061ff8623aa94c0abcf38af30a5bd48b",
    ),
    ReleaseFile(
        "consolidated_cell_types.csv.gz",
        "primary cell type per neuron",
        False,
        "8aba246d71dc40361677493629972ce3883048c3d02010adc42bda22962a1a2d",
    ),
    ReleaseFile(
        "coordinates.csv.gz",
        "one anchor position per neuron, nanometres",
        False,
        "14337121f451f98c2576cee72c24409ada5aaf7948b7c7ca8de9040296840e05",
    ),
    ReleaseFile(
        "labels.csv.gz",
        "free-text community annotations with attribution",
        False,
        "bdd4eafab2bfe30540256c84ea1513e4b1877c0c4cf03f919204b4eafae5868e",
    ),
    ReleaseFile(
        "cell_stats.csv.gz",
        "cable length, area, volume per neuron",
        False,
        "bd5879e1b5df964bea2f3ca5316348d4276ce2ccaac283f0e36583c04fbd3d8e",
    ),
)

#: Published counts for v783, asserted by the reader when it sees a real release.
FAFB_783_EXPECTED = {"neurons": 139_255, "synapses": 50_666_648, "pairs": 3_732_460}


@dataclass
class ManifestReport:
    """Outcome of :func:`verify_dir`.

    :param present: Files found with a matching or unrecorded checksum.
    :param missing: Required or optional files not found.
    :param mismatched: Files found whose digest differs from the recorded one.
    """

    present: list[str]
    missing: list[str]
    mismatched: list[str]

    @property
    def ok(self) -> bool:
        """True when every required file is present and nothing mismatched."""
        required = {f.name for f in FAFB_783_FILES if f.required}
        return not (required & set(self.missing)) and not self.mismatched

    def __str__(self) -> str:
        lines = [f"present   : {len(self.present)}"]
        if self.missing:
            lines.append(f"missing   : {', '.join(self.missing)}")
        if self.mismatched:
            lines.append(f"mismatched: {', '.join(self.mismatched)}")
        return "\n".join(lines)


def sha256_of(path: Path, chunk: int = 1 << 20) -> str:
    """Hex SHA-256 of a file, streamed.

    :param path: File to hash.
    :param chunk: Read size in bytes.
    :return: Lowercase hex digest.
    """
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def verify_dir(
    data_dir: Path,
    files: tuple[ReleaseFile, ...] = FAFB_783_FILES,
    *,
    checksums: bool = True,
    strict: bool = False,
) -> ManifestReport:
    """Check a download directory against the release manifest.

    :param data_dir: Directory holding the Codex files.
    :param files: Manifest to check against.
    :param checksums: Hash the files (slow on the 68 MB connections file).
    :param strict: Raise instead of reporting when the report is not ok.
    :return: :class:`ManifestReport`.
    :raises FileNotFoundError: In strict mode when a required file is missing.
    :raises ValueError: In strict mode when a checksum mismatches.
    """
    data_dir = Path(data_dir)
    present, missing, mismatched = [], [], []
    for f in files:
        p = data_dir / f.name
        if not p.is_file():
            missing.append(f.name)
            continue
        if checksums and f.sha256 and sha256_of(p) != f.sha256:
            mismatched.append(f.name)
            continue
        present.append(f.name)
    report = ManifestReport(present, missing, mismatched)
    if strict and not report.ok:
        required_missing = [n for n in missing if any(f.name == n and f.required for f in files)]
        if required_missing:
            raise FileNotFoundError(f"required release files missing: {required_missing}")
        raise ValueError(f"release files with unexpected checksum: {mismatched}")
    return report
