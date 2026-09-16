# Getting the FlyWire FAFB v783 release

The build reads the Codex export files. They are free for non-commercial use
under CC BY-NC-SA 4.0 and Codex requires a **Google** sign-in to fetch them,
so this is a manual step. Under 100 MB for the files the build reads.

## The portal lists labels, not file names

This is the thing that trips everyone. The download page shows friendly labels;
what lands on disk is a different name, and that name is what the reader looks
for. The file you most need, `neurons.csv.gz`, is listed as "Neurotransmitter
Type Predictions".

`connectome-kg files` prints this table at any time.

| portal label | downloads as | size | needed |
|---|---|---|---|
| Neurotransmitter Type Predictions | `neurons.csv.gz` | 1,680 KB | **required** |
| Classification / Hierarchical Annotations | `classification.csv.gz` | 934 KB | **required** |
| Connections (Filtered) | `connections_princeton.csv.gz` | 68 MB | **required** |
| Cell Types | `consolidated_cell_types.csv.gz` | 902 KB | optional |
| Marked Neuron Coordinates | `coordinates.csv.gz` | 5,315 KB | optional |
| Community Labels (Raw) | `labels.csv.gz` | 4,771 KB | optional |
| Cell Size Measurements | `cell_stats.csv.gz` | 2,527 KB | optional |

Three required files, about 71 MB. The optional ones add cell type names,
3D positions, community annotations with attribution, and morphometrics.

Deliberately not downloaded:

| portal label | size | why not |
|---|---|---|
| Connections (Unfiltered) | 277 MB | millions of single-synapse rows, mostly detection noise |
| Synapse Table | 2,695 MB | the graph is at neuron resolution, it uses synapse counts |
| Neuron Skeletons | 13 GB | coordinates give one position per neuron instead |
| Proofread Cell Names And Groups | 1,182 KB | cell types carry the identity the graph uses |
| Community Labels (Refined) | 1,018 KB | the raw labels carry the attribution the graph records |
| Visual Neuron Annotations / Columns | 1,095 KB | not yet wired in |
| Connectivity Tags | 638 KB | not yet wired in |
| Anything marked "prior to July 2025" | varies | superseded; mixing detectors is not valid |

The connections table has also shipped as `connections.csv.gz` in other
exports. `find_connections_file()` takes whichever variant is present,
preferring the filtered Princeton table, and `--connections-file` overrides it.
The reader accepts column-name variants too (`pre_root_id` or `pre_pt_root_id`
or `pre`, `syn_count` or `weight`) and names the column it could not find when
a file is not what it expects.

## The portal is live, not a snapshot

Codex says its downloads are "synchronized with the live Codex database",
continually updated, and "may differ from the static snapshot released at the
time of the FlyWire package publication in October 2024". Two consequences:

**Checksums drift, and that is not corruption.** The digests in
`connectomekg/manifest.py` fingerprint one August 2026 download. `verify`
reports a difference as drift and still says "ready to build"; only a missing
required file is a hard failure. The real check is the counts the build prints:
139,255 neurons and 3,732,460 connected pairs.

**A reproducible build wants the published snapshot**, which the portal itself
points at:

| what | where |
|---|---|
| connectivity, Dorkenwald et al. 2024 | https://zenodo.org/records/10676866 |
| annotations, Schlegel et al. 2024 | https://github.com/flyconnectome/flywire_annotations |
| supplemental, Schlegel et al. 2024 | https://zenodo.org/records/10877326 |
| visual system cell types, Matsliah et al. 2024 | https://github.com/murthylab/visual-system-parts-list |

Those need no sign-in. A dated KG index built from a moving target cannot be
reproduced later, so for anything citable, prefer them and record which you
used on the dataset node.

## Steps

1. Go to https://codex.flywire.ai and sign in with a Google account. The first
   visit asks you to accept the FlyWire citation guidelines and principles.
2. Check the dataset selector reads **FAFB v783**.
3. Open "Download Data", or go to
   https://codex.flywire.ai/api/download?dataset=fafb
4. Tick the agreement checkbox, then download at least the three required
   files from the table above, into one directory.

5. Verify the directory against the manifest, then build:

   ```bash
   connectome-kg verify --data-dir /path/to/fafb_v783
   connectome-kg --root . build --data-dir /path/to/fafb_v783 --dataset-id fafb783 --no-index
   connectome-kg --root . analyze --dataset-id fafb783
   ```

   `verify` hashes every file against the SHA-256 values recorded in
   `connectomekg/manifest.py`, which were taken from an independent August 2026
   download and are expectations rather than authority. A mismatch usually means
   Codex re-exported the file. Check the counts the build prints against the
   published 139,255 neurons and 3.73 M connected pairs, and if those are right,
   update the manifest. `--no-checksums` skips the hashing while you sort names
   out.

   `--no-index` builds the SQLite graph only. Drop it (with the `semantic`
   extra installed) to also embed the cell types, neuropils, labels and taxa;
   that is about 20k short texts and takes a few minutes on CPU.

6. Expected footprint: about 4 minutes and 2 GB of SQLite for the graph. That
   is extrapolated from a 2.5 M edge synthetic build, not measured on the real
   release; time the first real build and correct this number.

## If Codex offers something other than what you expected

The portal's file set has changed over time, and there are public mirrors of
the same v783 release that need no sign-in (a Zenodo record accompanies the
annotation paper, and `flyconnectome/flywire_annotations` on GitHub carries the
annotation tables). Any of them work as long as the directory ends up with a
neurons table, a classification table and a connections table whose columns the
reader recognises. Run `connectome-kg verify --data-dir <dir> --no-checksums`
to see what it detects before building.

## Licence reminder

The built index over FlyWire data is a derived work under CC BY-NC-SA 4.0.
Keep the download and the `.connectomekg/` directory out of the repository
(`.gitignore` already does) and out of anything commercial. Cite
Dorkenwald et al. 2024, Schlegel et al. 2024 and Eckstein et al. 2024 for
the data.
