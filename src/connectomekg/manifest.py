"""The FlyWire FAFB v783 Codex release: what the portal offers and what a build needs.

Two things about the portal make a naive manifest misleading, and both are
encoded here.

**The portal lists display names, not file names.** The file the reader calls
``neurons.csv.gz`` appears as "Neurotransmitter Type Predictions", and
``connections_princeton.csv.gz`` as "Connections (Filtered)". Every entry below
carries the portal's own label so a download can be matched to it by eye.

**The portal is live, not a snapshot.** It states that its files are
"synchronized with the live Codex database", continually updated and curated,
and "may differ from the static snapshot released at the time of the FlyWire
package publication in October 2024". So a checksum difference is ordinarily
*drift*, not corruption, and :func:`verify_dir` reports it as such rather than
failing. The recorded digests come from an independent August 2026 download
(vaibhavkedarisetti/fruit-fly-lab, DATA_SOURCES.md); they are a fingerprint of
that download, not an authority over yours.

For a build that must be reproducible, prefer the static archives the portal
itself points at: see :data:`STATIC_ARCHIVES`.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from connectomekg.readers.codex import (
    find_connections_file,
    is_attribute_export,
    soma_position_table,
)

#: Where to get the October 2024 published snapshot, as the portal itself
#: recommends for reproducibility. The live portal is a moving target.
STATIC_ARCHIVES: dict[str, str] = {
    "connectivity (Dorkenwald et al. 2024)": "https://zenodo.org/records/10676866",
    "annotations (Schlegel et al. 2024)": "https://github.com/flyconnectome/flywire_annotations",
    "supplemental (Schlegel et al. 2024)": "https://zenodo.org/records/10877326",
    "visual system cell types (Matsliah et al. 2024)": (
        "https://github.com/murthylab/visual-system-parts-list"
    ),
}


@dataclass(frozen=True)
class ReleaseFile:
    """One file of a Codex release.

    :param name: File name inside the download directory.
    :param display: How the download portal labels it, which is not the file name.
    :param role: What the build uses it for.
    :param required: Whether a build can proceed without it.
    :param size: Approximate size as the portal reports it, for recognition.
    :param sha256: Digest of the August 2026 download, or ``None`` when not recorded.
    """

    name: str
    display: str
    role: str
    required: bool
    size: str = ""
    sha256: str | None = None


FAFB_783_FILES: tuple[ReleaseFile, ...] = (
    ReleaseFile(
        "neurons.csv.gz",
        "Neurotransmitter Type Predictions",
        "root ids, neurotransmitter prediction and score",
        True,
        "1,680 KB",
        "6a6b3759e635f0f35a677d169052362131ec61d95f55919298b55c43fce4e719",
    ),
    ReleaseFile(
        "classification.csv.gz",
        "Classification / Hierarchical Annotations",
        "flow, super class, class, sub class, cell type, hemilineage, side, nerve",
        True,
        "934 KB",
        "e946b552f4056dfc977707be0674609832c3f64332a22d69dc0d9615e7aae663",
    ),
    ReleaseFile(
        "connections_princeton.csv.gz",
        "Connections (Filtered)",
        "edges: (pre, post, neuropil) rows with syn_count and nt_type, 5-synapse threshold",
        True,
        "68 MB",
        "445f996bf6c4b1803b9ba186189138a3061ff8623aa94c0abcf38af30a5bd48b",
    ),
    ReleaseFile(
        "consolidated_cell_types.csv.gz",
        "Cell Types",
        "primary cell type per neuron",
        False,
        "902 KB",
        "8aba246d71dc40361677493629972ce3883048c3d02010adc42bda22962a1a2d",
    ),
    ReleaseFile(
        "coordinates.csv.gz",
        "Marked Neuron Coordinates",
        "one anchor position per neuron, nanometres",
        False,
        "5,315 KB",
        "14337121f451f98c2576cee72c24409ada5aaf7948b7c7ca8de9040296840e05",
    ),
    ReleaseFile(
        "labels.csv.gz",
        "Community Labels (Raw)",
        "free-text community annotations with attribution",
        False,
        "4,771 KB",
        "bdd4eafab2bfe30540256c84ea1513e4b1877c0c4cf03f919204b4eafae5868e",
    ),
    ReleaseFile(
        "cell_stats.csv.gz",
        "Cell Size Measurements",
        "cable length, area, volume per neuron",
        False,
        "2,527 KB",
        "bd5879e1b5df964bea2f3ca5316348d4276ce2ccaac283f0e36583c04fbd3d8e",
    ),
    ReleaseFile(
        "visual_neuron_types.csv.gz",
        "Visual Neuron Annotations",
        "visual families and subsystems (Motion, Color, ...) for optic lobe types",
        False,
        "632 KB",
        "4bcc6a2f98b86e6c3fb7eaddb49736f3d81ab65bda35da8f740641201a1e379f",
    ),
    ReleaseFile(
        "column_assignment.csv.gz",
        "Visual Neuron Columns",
        "retinotopic column and hex position per columnar neuron",
        False,
        "463 KB",
        "bdf4ce7f62cc63493d53eefad3816ff2dfd08b190e97b35a492e0e453df2f0f6",
    ),
    ReleaseFile(
        "connectivity_tags.csv.gz",
        "Connectivity Tags",
        "network-analysis tags such as broadcaster and integrator",
        False,
        "638 KB",
        "68c69cec13810fa543c600a5b9973d10718b449740e010834662be1dc1b8696c",
    ),
    # No digest: the September 2026 copy was re-compressed locally, so its
    # bytes are not the portal's.
    ReleaseFile(
        "processed_labels.csv.gz",
        "Community Labels (Refined)",
        "cleaned labels, carrying the Fly Anatomy Ontology (FBbt) ids",
        False,
        "1,018 KB",
    ),
)

#: Portal assets the build does not read, recorded so a report can say why.
FAFB_783_UNUSED: tuple[ReleaseFile, ...] = (
    ReleaseFile(
        "connections_princeton_no_threshold.csv.gz",
        "Connections (Unfiltered)",
        "unthresholded edges; millions of single-synapse rows that are mostly noise",
        False,
        "277 MB",
    ),
    ReleaseFile(
        "synapse_table.csv.gz",
        "Synapse Table",
        "per-synapse rows; the graph is at neuron resolution",
        False,
        "2,695 MB",
    ),
    ReleaseFile(
        "skeleton_swc_files.zip",
        "Neuron Skeletons",
        "morphology meshes; coordinates give a position per neuron instead",
        False,
        "13 GB",
    ),
    ReleaseFile(
        "names.csv.gz",
        "Proofread Cell Names And Groups",
        "display names; cell types carry the identity the graph uses",
        False,
        "1,182 KB",
    ),
)

#: The consolidated export Codex offers for BANC and MCNS: one neuron-attributes
#: table in place of FAFB's split files, plus the same connections table. No
#: digests are recorded; the counts the build prints are the check.
ATTRIBUTE_EXPORT_FILES: tuple[ReleaseFile, ...] = (
    ReleaseFile(
        "neurons.csv.gz",
        "Neuron Attributes",
        "root ids, transmitter prediction, taxonomy, cell type, community labels",
        True,
    ),
    ReleaseFile(
        "connections_princeton.csv.gz",
        "Connections",
        "synapse counts per neuron pair per neuropil",
        True,
    ),
)

#: Published counts for v783, the check that actually matters on a live portal.
FAFB_783_EXPECTED = {"neurons": 139_255, "synapses": 50_666_648, "pairs": 3_732_460}


@dataclass
class ManifestReport:
    """Outcome of :func:`verify_dir`.

    :param present: Files found whose digest matched, or was not checked.
    :param missing: Manifest files not found in the directory.
    :param drifted: Files found whose digest differs from the recorded one. On a
        live portal this is expected and is not by itself a problem.
    :param notes: Human-readable remarks, such as the connections variant found.
    :param required: Names of the files a build cannot do without.
    """

    present: list[str]
    missing: list[str]
    drifted: list[str]
    notes: list[str] = field(default_factory=list)
    required: frozenset[str] = frozenset(f.name for f in FAFB_783_FILES if f.required)

    @property
    def missing_required(self) -> list[str]:
        """Required files that are absent, which is the only hard failure."""
        return [n for n in self.missing if n in self.required]

    @property
    def ok(self) -> bool:
        """True when every required file is present.

        Checksum drift does not make a directory unusable: the portal updates
        its files continually, so the counts the build prints are the real
        check. See :attr:`drifted`.
        """
        return not self.missing_required

    def __str__(self) -> str:
        lines = [f"present  : {len(self.present)} file(s)"]
        for n in self.notes:
            lines.append(f"note     : {n}")
        if self.missing_required:
            lines.append(f"MISSING  : {', '.join(self.missing_required)}  (required)")
        optional_missing = [n for n in self.missing if n not in self.missing_required]
        if optional_missing:
            lines.append(f"absent   : {', '.join(optional_missing)}  (optional)")
        if self.drifted:
            lines.append(
                f"drifted  : {', '.join(self.drifted)}\n"
                "           These differ from the August 2026 download this manifest\n"
                "           records. The portal updates continually, so that is\n"
                "           expected. Check the counts the build prints against\n"
                f"           {FAFB_783_EXPECTED['neurons']:,} neurons and "
                f"{FAFB_783_EXPECTED['pairs']:,} pairs."
            )
        lines.append("ready to build" if self.ok else "NOT ready: a required file is missing")
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


def _connections_present(data_dir: Path) -> str | None:
    """Name of the connections table found, whatever Codex called it."""
    try:
        return find_connections_file(data_dir).name
    except FileNotFoundError:
        return None


def verify_dir(
    data_dir: Path,
    files: tuple[ReleaseFile, ...] = FAFB_783_FILES,
    *,
    checksums: bool = True,
    strict: bool = False,
) -> ManifestReport:
    """Check a download directory against the release manifest.

    A directory holding the consolidated neuron-attributes export (BANC, MCNS)
    is checked against :data:`ATTRIBUTE_EXPORT_FILES` instead of the default
    FAFB manifest.

    :param data_dir: Directory holding the Codex files.
    :param files: Manifest to check against.
    :param checksums: Hash the files (slow on the 68 MB connections table).
    :param strict: Raise instead of reporting when a required file is missing.
    :return: :class:`ManifestReport`.
    :raises FileNotFoundError: In strict mode when a required file is missing.
    """
    data_dir = Path(data_dir)
    found_con = _connections_present(data_dir)
    present: list[str] = []
    missing: list[str] = []
    drifted: list[str] = []
    notes: list[str] = []
    if files is FAFB_783_FILES and is_attribute_export(data_dir):
        files = ATTRIBUTE_EXPORT_FILES
        notes.append("consolidated neuron-attributes export (the BANC and MCNS layout)")
        # The export has no coordinates; a project's own table supplies them.
        positions = soma_position_table(data_dir)
        notes.append(
            f"soma positions from {positions.name}"
            if positions
            else "no soma-position table, so the 3-D views have nothing to place"
        )
    for f in files:
        p = data_dir / f.name
        if not p.is_file():
            # Codex renames the connections table between exports; any variant
            # satisfies the requirement, and the report names the one found.
            if f.name == "connections_princeton.csv.gz" and found_con:
                present.append(found_con)
                notes.append(f"connections table is {found_con}")
                continue
            missing.append(f.name)
            continue
        if checksums and f.sha256 and sha256_of(p) != f.sha256:
            drifted.append(f.name)
            continue
        present.append(f.name)
    report = ManifestReport(
        present, missing, drifted, notes, frozenset(f.name for f in files if f.required)
    )
    if strict and report.missing_required:
        raise FileNotFoundError(f"required release files missing: {report.missing_required}")
    return report


def portal_guide() -> str:
    """The portal's display names beside the file names, as a Markdown table.

    The portal lists no file names, which makes a download hard to match against
    a manifest by eye. This renders the mapping.

    :return: Markdown table text.
    """
    rows = [
        "| portal label | file | size | needed |",
        "|---|---|---|---|",
    ]
    for f in FAFB_783_FILES:
        rows.append(
            f"| {f.display} | `{f.name}` | {f.size} | "
            f"{'**required**' if f.required else 'optional'} |"
        )
    rows.append("")
    rows.append("Not read by the build:")
    rows.append("")
    rows.append("| portal label | size | why not |")
    rows.append("|---|---|---|")
    for f in FAFB_783_UNUSED:
        rows.append(f"| {f.display} | {f.size} | {f.role.split(';')[-1].strip()} |")
    return "\n".join(rows)
