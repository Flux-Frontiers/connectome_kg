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
from pathlib import Path

import pymupdf

#: ``pdf file name -> (title, citation, DOI)``. The DOI's last segment is the
#: output stem, so the text file is traceable to the paper without opening it.
PAPERS: dict[str, tuple[str, str, str]] = {
    "s41586-024-07558-y.pdf": (
        "Neuronal wiring diagram of an adult brain",
        "Dorkenwald, S. et al. (2024). Nature 634, 124-138.",
        "10.1038/s41586-024-07558-y",
    ),
    "s41586-024-07686-5.pdf": (
        "Whole-brain annotation and multi-connectome cell typing of Drosophila",
        "Schlegel, P. et al. (2024). Nature 634, 139-152.",
        "10.1038/s41586-024-07686-5",
    ),
}

#: A newline that is not after sentence-ending punctuation and not before a
#: blank line or a bullet: the hard wrapping of a justified column.
_WRAP = re.compile(r"(?<![.!?:;])\n(?![\n•])")
#: The first numbered citation, which starts the reference list.
_REFERENCES = re.compile(r"\n1\.\s+[A-Z][a-zA-Z\-]+,\s+[A-Z]\.")

HERE = Path(__file__).parent
TEXT_DIR = HERE / "text"


def extract(pdf: Path, title: str, citation: str, doi: str) -> tuple[Path, int, int]:
    """Write one paper's body text as Markdown.

    :param pdf: The PDF to read.
    :param title: The paper's title, used as the document's only heading.
    :param citation: A human citation line.
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

    cut = _REFERENCES.search(body)
    dropped = 0
    if cut:
        dropped = len(body) - cut.start()
        body = body[: cut.start()]

    out = TEXT_DIR / f"{doi.split('/')[-1]}.md"
    out.write_text(
        f"# {title}\n\n{citation}\n\nDOI: https://doi.org/{doi}\n\n{body}\n", encoding="utf-8"
    )
    return out, len(body), dropped


def main() -> None:
    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    missing = [name for name in PAPERS if not (HERE / name).is_file()]
    if missing:
        raise SystemExit(
            f"missing from {HERE}: {', '.join(missing)}\n"
            "See papers/README.md for the DOIs; the PDFs are not in the repository."
        )
    for name, (title, citation, doi) in PAPERS.items():
        out, kept, dropped = extract(HERE / name, title, citation, doi)
        print(f"{out.name}  kept {kept:>8,}  dropped {dropped:>7,} chars of references")


if __name__ == "__main__":
    main()
