# The source papers, as a searchable corpus

The graph says LC4 makes 1,401 synapses onto DNp01. It does not say how the
synapses were detected, how the cell types were assigned, or what a
neurotransmitter prediction is worth. The papers do, and this puts them a
query away.

[DocKG](https://github.com/Flux-Frontiers/doc_kg) indexes them beside the
connectome, so the same session can ask the graph a wiring question and the
papers a provenance one.

## What is here

| file | tracked | what |
|---|---|---|
| `README.md`, `extract.py` | yes | how to rebuild the corpus |
| `*.pdf` | no | the papers, downloaded by hand |
| `text/*.md` | no | their body text, written by `extract.py` |
| `.dockg/` | no | the graph and vector index |

The PDFs are open access under CC BY, but the publishers' files are theirs to
distribute rather than ours, and the text is derived from them. Both stay out
of the repository; the DOIs below are enough to rebuild.

## The papers

| paper | DOI |
|---|---|
| Dorkenwald, S. et al. (2024). *Neuronal wiring diagram of an adult brain.* Nature 634, 124-138. | [10.1038/s41586-024-07558-y](https://doi.org/10.1038/s41586-024-07558-y) |
| Schlegel, P. et al. (2024). *Whole-brain annotation and multi-connectome cell typing of Drosophila.* Nature 634, 139-152. | [10.1038/s41586-024-07686-5](https://doi.org/10.1038/s41586-024-07686-5) |

These two are the source of the data the graph is built from: the first
reconstructed the wiring, the second annotated it.

## Rebuild

Put the PDFs in this directory under the file names in `extract.py`, then:

```bash
poetry run python papers/extract.py
poetry run dockg build --repo papers
```

Six seconds, 1,747 vectors. `--repo papers` keeps this corpus in
`papers/.dockg/`, separate from the repository's own documentation graph in
`.dockg/`.

## Ask it

```bash
poetry run dockg pack --repo papers "how were neurotransmitters predicted"
poetry run dockg query --repo papers "what is a hemilineage"
```

## What it can and cannot answer

**It answers how the dataset was made.** Proofreading, synapse detection,
neurotransmitter prediction, cell typing, hemilineages, the annotation
process, what the coverage figures mean. Asked how neurotransmitters were
predicted it returns the passage describing the six small-molecule
predictions and warning that any single synapse may be wrong -- which is
exactly the caveat behind every `sign` the graph carries.

**It does not answer circuit questions.** `DNp01`, `LC4` and `LPLC2` appear
**zero times** in either paper. These are the dataset and cell-typing papers;
they describe the resource, not what any particular circuit does. A question
like "what does the giant fibre do" needs the papers that study it -- von Reyn
et al. on the giant fibre escape, Ache et al. on looming -- which are not in
this corpus.

Worth knowing before relying on it, and worth adding those papers if circuit
questions are what you want answered.
