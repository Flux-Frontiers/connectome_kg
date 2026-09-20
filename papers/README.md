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

## Worth adding

Every citation below was taken from the reference lists of the two papers
above, not from memory. Ordered by what each buys.

### Explains a field the graph already carries

| paper | DOI | why |
|---|---|---|
| Eckstein, N. et al. (2024). *Neurotransmitter classification from electron microscopy images at synaptic sites in Drosophila melanogaster.* Cell 187, 2574-2594.e23. | [10.1016/j.cell.2024.03.016](https://doi.org/10.1016/j.cell.2024.03.016) | the source of `nt_type`, `nt_score` and therefore every `sign` on every edge |
| Matsliah, A. et al. (2024). *Neuronal parts list and wiring diagram for a visual system.* Nature. | [10.1038/s41586-024-07981-1](https://doi.org/10.1038/s41586-024-07981-1) | the optic lobe: where LC4, LPLC2 and the visual families come from |
| Namiki, S. et al. (2018). *The functional organization of descending sensory-motor pathways in Drosophila.* eLife 7, e34272. | [10.7554/eLife.34272](https://doi.org/10.7554/eLife.34272) | where the DNp nomenclature comes from, DNp01 included |

### Answers circuit questions

| paper | DOI | why |
|---|---|---|
| Morimoto, M. M. et al. (2020). *Spatial readout of visual looming in the central brain of Drosophila.* eLife 9, e57685. | [10.7554/eLife.57685](https://doi.org/10.7554/eLife.57685) | what the looming detectors compute |
| Kim, H. et al. (2020). *Wiring patterns from auditory sensory neurons to the escape and song-relay pathways in fruit flies.* J. Comp. Neurol. 528, 2068-2098. | [10.1002/cne.24877](https://doi.org/10.1002/cne.24877) | the escape pathway, from the auditory side |

### For work not yet started

| paper | DOI | for |
|---|---|---|
| Shiu, P. K. et al. (2024). *A Drosophila computational brain model reveals sensorimotor processing.* Nature. | [10.1038/s41586-024-07763-9](https://doi.org/10.1038/s41586-024-07763-9) | the LIF contract, if the simulation is ever built |
| Scheffer, L. K. et al. (2020). *A connectome and analysis of the adult Drosophila central brain.* eLife 9, e57443. | [10.7554/eLife.57443](https://doi.org/10.7554/eLife.57443) | hemibrain, if a second dataset is added |

The first three are the ones to fetch if only three are fetched: each explains
something the graph asserts but cannot justify on its own.

## Rebuild

Put the PDFs in this directory -- any file name; the title and DOI are read
from the PDF itself -- then:

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
they describe the resource, not what any particular circuit does. A question like "what does the
giant fibre do" needs the papers that study it, which are listed under
[Worth adding](#worth-adding).

Worth knowing before relying on it.
