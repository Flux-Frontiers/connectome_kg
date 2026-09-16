# Getting the FlyWire FAFB v783 release

The build reads the Codex export files. They are free for non-commercial use
under CC BY-NC-SA 4.0 and need a Codex account to fetch, so this is a manual
step. About 1.5 GB for the files the build reads.

## Steps

1. Go to https://codex.flywire.ai and sign in (create a free account if you
   have none; the first visit asks you to accept the FlyWire data terms).
2. Make sure the selected dataset is **FAFB, version 783** (the dataset picker
   is at the top of the app; 783 is the public release).
3. Open the download portal: https://codex.flywire.ai/api/download
   (also reachable from the app as "Download Data").
4. Download these files into one directory, keeping their names:

   | file | needed | size |
   |---|---|---|
   | `neurons.csv.gz` | yes | 1.7 MB |
   | `classification.csv.gz` | yes | 0.9 MB |
   | `connections_princeton.csv.gz` | yes | 68 MB |
   | `consolidated_cell_types.csv.gz` | recommended | 0.9 MB |
   | `coordinates.csv.gz` | recommended | 5.3 MB |
   | `labels.csv.gz` | recommended | 4.8 MB |
   | `cell_stats.csv.gz` | optional | 2.5 MB |

   Skip `connections_princeton_no_threshold.csv.gz` (276 MB, single-synapse
   edges), the per-synapse table (2.7 GB) and the skeleton archive (14 GB);
   the graph is at neuron resolution and does not read them.

5. Verify the directory against the manifest, then build:

   ```bash
   connectome-kg verify --data-dir /path/to/fafb_v783
   connectome-kg --root . build --data-dir /path/to/fafb_v783 --dataset-id fafb783 --no-index
   connectome-kg --root . analyze --dataset-id fafb783
   ```

   `verify` hashes every file against the SHA-256 values recorded in
   `connectomekg/manifest.py`. A mismatch on one file usually means Codex
   re-exported it; check the row count the build prints against the published
   139,255 neurons and 3.73 M connected pairs before trusting it, and update
   the manifest if the counts are right.

   `--no-index` builds the SQLite graph only. Drop it (with the `semantic`
   extra installed) to also embed the cell types, neuropils, labels and taxa;
   that is about 20k short texts and takes a few minutes on CPU.

6. Expected footprint: about 4 minutes and 2 GB of SQLite for the graph
   (measured by extrapolation from a 2.5 M edge synthetic build; the first
   real build should be timed and this number corrected).

## Licence reminder

The built index over FlyWire data is a derived work under CC BY-NC-SA 4.0.
Keep the download and the `.connectomekg/` directory out of the repository
(`.gitignore` already does) and out of anything commercial. Cite
Dorkenwald et al. 2024, Schlegel et al. 2024 and Eckstein et al. 2024 for
the data.
