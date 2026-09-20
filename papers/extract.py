"""Turn the source papers' PDFs into the text DocKG indexes.

Run from the repository root, with the PDFs in ``papers/``:

    poetry run python papers/extract.py
    poetry run dockg build --repo papers

DocKG reads ``.md`` and ``.txt``, not PDF, so the papers have to be extracted
first. Two things happen here that a plain text dump does not do, and both
were measured rather than assumed:

* **The hard wrapping is undone.** A two-column PDF breaks a sentence across
  a dozen short lines. Left alone, chunk boundaries fall mid-clause and the
  retrieved excerpt reads as fragments.
* **The reference list is cut.** Neither PDF carries a "References" heading in
  its extracted text, so the anchor is the first numbered citation, which
  begins a run of about 120. Left in, the bibliography is more than half the
  corpus -- 176,000 of 335,000 characters -- and it retrieves: a query for
  looming visual projection neurons returned a bibliography entry rather than
  any prose.

The PDFs and the text are both gitignored. They are open access, but the
publishers' files are theirs to distribute rather than ours, and the text is
derived from them. This script and ``papers/README.md`` are what is tracked,
so the corpus can be rebuilt from the DOIs.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pymupdf

#: Human citations for papers already in the corpus, keyed by DOI. Everything
#: else -- the title, the DOI itself -- is read from the PDF, so adding a paper
#: is dropping its file in this directory and running this script. A paper with
#: no entry here is still extracted; it just carries no citation line.
CITATIONS: dict[str, str] = {
    "10.1038/s41586-024-07558-y": "Dorkenwald, S. et al. (2024). Nature 634, 124-138.",
    "10.1038/s41586-024-07686-5": "Schlegel, P. et al. (2024). Nature 634, 139-152.",
    "10.1038/s41586-024-07981-1": "Matsliah, A. et al. (2024). Nature 634, 166-180.",
    "10.1038/s41586-024-07763-9": "Shiu, P. K. et al. (2024). Nature 634, 210-219.",
    "10.1016/j.cell.2024.03.016": "Eckstein, N. et al. (2024). Cell 187, 2574-2594.e23.",
    "10.7554/eLife.57443": "Scheffer, L. K. et al. (2020). eLife 9, e57443.",
    "10.7554/eLife.34272": "Namiki, S. et al. (2018). eLife 7, e34272.",
    "10.7554/eLife.57685": "Morimoto, M. M. et al. (2020). eLife 9, e57685.",
}

#: A DOI anywhere. A paper repeats its own in every page footer, so the one
#: that appears most often in its text is the paper's.
_DOI = re.compile(r"10\.\d{4,9}/[^\s,;)\]]+")

#: A newline that is not after sentence-ending punctuation and not before a
#: blank line or a bullet: the hard wrapping of a justified column.
_WRAP = re.compile(r"(?<![.!?:;])\n(?![\n\u2022])")

#: Where a reference list starts. Nature prints no heading in its extracted
#: text, so its first numbered citation is the anchor; eLife and Cell do print
#: one, in their own case.
_REFERENCE_ANCHORS = (
    re.compile(r"\bREFERENCES\b"),
    re.compile(r"\bReferences\b"),
    re.compile(r"\n1\.\s+[A-Z][a-zA-Z\-]+,\s+[A-Z]\."),
)
#: What a citation looks like wherever it appears: a printed DOI, or a year in
#: parentheses, or a year ending a sentence as author-date styles do.
_CITATION_MARK = re.compile(r"doi\.org/|\(\d{4}\)|\.\s\d{4}\.")
#: eLife prints a DOI for every figure and figure supplement, inline in the
#: body: "Figure 2 continued DOI: https://doi.org/10.7554/eLife.34272.003".
#: One paper carried 105 of them after its reference list was cut. They are
#: not citations and they are not prose; they just break up chunks.
_PRINTED_DOI = re.compile(r"\s*DOI:\s*https?://(?:dx\.)?doi\.org/\S+")

#: One numbered reference entry, e.g. ``12. Cook, S.J.,``.
_NUMBERED_ENTRY = re.compile(r"(?:\n|\s)(\d{1,3})\.\s+[A-Z][a-zA-Z\-]+,\s*[A-Z]\.")

#: A numbered run this long is a reference list, not a stray enumeration.
_MIN_NUMBERED_ENTRIES = 10
#: How far past a candidate heading to look for citations, and how many must
#: be there for it to be the reference list rather than a mention of one.
_ANCHOR_WINDOW = 3000
_MIN_CITATION_MARKS = 5
#: Characters to keep for the final entry when the list ends the document.
_ENTRY_TAIL = 600

HERE = Path(__file__).parent
TEXT_DIR = HERE / "text"


def describe(pdf: Path) -> tuple[str, str]:
    """A paper's title and DOI, read from the PDF itself.

    :param pdf: The PDF to inspect.
    :return: ``(title, doi)``; either may fall back to the file's stem.
    """
    document = pymupdf.open(pdf)
    try:
        metadata = document.metadata or {}
    finally:
        document.close()
    title = (metadata.get("title") or "").strip() or pdf.stem
    fields = " ".join(str(metadata.get(k) or "") for k in ("subject", "keywords", "title"))
    found = _DOI.search(fields)
    if found:
        return title, found.group(0)
    # eLife's PDFs carry no DOI in their metadata, but print it in every page
    # footer, so the most frequent DOI in the text is the paper's own -- the
    # ones it cites appear once each.
    document = pymupdf.open(pdf)
    try:
        head = "\n".join(page.get_text("text") for page in document)
    finally:
        document.close()
    counts = Counter(d.rstrip(".") for d in _DOI.findall(head))
    return title, counts.most_common(1)[0][0] if counts else pdf.stem


def reference_span(body: str) -> tuple[int, int] | None:
    """Where the reference list starts and ends, if there is one.

    A span rather than a tail, because journals differ in what follows it.
    eLife ends with its references, so the span runs to the end; Cell prints
    90,000 further characters of methods after them, and cutting to the end
    would throw that away.

    A numbered list bounds itself: its entries are sequential, so the span
    ends just past the last one. An author-date list (eLife) has no such
    marker, and in the papers seen it is the last thing in the document.

    :param body: The de-wrapped text.
    :return: ``(start, end)``, or ``None`` when no reference list is found.
    """
    # A heading alone is not enough: "References" occurs in prose too. An
    # anchor counts only when citations crowd in behind it, which is what
    # distinguishes the list from a mention of it.
    candidates = sorted(m.start() for pattern in _REFERENCE_ANCHORS for m in pattern.finditer(body))
    start = next(
        (
            position
            for position in candidates
            if len(_CITATION_MARK.findall(body[position : position + _ANCHOR_WINDOW]))
            >= _MIN_CITATION_MARKS
        ),
        None,
    )
    if start is None:
        return None
    entries = list(_NUMBERED_ENTRY.finditer(body, start))
    if len(entries) >= _MIN_NUMBERED_ENTRIES:
        last = entries[-1].start()
        # To the end of that final entry: the next blank line, or a generous
        # single-entry length when the list runs to the end of the document.
        break_at = body.find("\n\n", last)
        end = break_at if break_at != -1 else min(len(body), last + _ENTRY_TAIL)
        return start, end
    return start, len(body)


def extract(pdf: Path, title: str, citation: str, doi: str) -> tuple[Path, int, int]:
    """Write one paper's body text as Markdown.

    :param pdf: The PDF to read.
    :param title: The paper's title, used as the document's only heading.
    :param citation: A human citation line, or empty.
    :param doi: The DOI; its last segment names the output file.
    :return: ``(path, characters kept, characters dropped as references)``.
    """
    document = pymupdf.open(pdf)
    try:
        body = "\n\n".join(page.get_text("text") for page in document)
    finally:
        document.close()
    body = _WRAP.sub(" ", body)
    body = re.sub(r"\n{3,}", "\n\n", body)

    body = _PRINTED_DOI.sub("", body)
    span = reference_span(body)
    dropped = 0
    if span:
        start, end = span
        dropped = end - start
        body = body[:start] + body[end:]

    out = TEXT_DIR / f"{doi.split('/')[-1]}.md"
    header = f"# {title}\n\n"
    if citation:
        header += f"{citation}\n\n"
    header += f"DOI: https://doi.org/{doi}\n\n"
    out.write_text(header + body + "\n", encoding="utf-8")
    return out, len(body), dropped


def main() -> None:
    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(HERE.glob("*.pdf"))
    if not pdfs:
        raise SystemExit(
            f"no PDFs in {HERE}. See papers/README.md for which papers and their DOIs; "
            "they are not in the repository."
        )
    for pdf in pdfs:
        title, doi = describe(pdf)
        out, kept, dropped = extract(pdf, title, CITATIONS.get(doi, ""), doi)
        note = "" if doi in CITATIONS else "   (no citation line; add one to CITATIONS)"
        print(f"{out.name:<28} kept {kept:>8,}  dropped {dropped:>7,} refs{note}")


if __name__ == "__main__":
    main()
