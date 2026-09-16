# Getting the FlyWire FAFB v783 release

The build reads the Codex export files. They are free for non-commercial use
under CC BY-NC-SA 4.0 and Codex requires a **Google** sign-in to fetch them,
so this is a manual step. Under 100 MB for the files the build reads.

## What the build actually needs

Only three tables are required. Everything else enriches the graph:

| our name for it | required | what it gives the graph |
|---|---|---|
| neurons | yes | root ids, neurotransmitter prediction and score |
| classification | yes | super class, class, cell type, side, hemilineage, nerve |
| connections | yes | the edges: pre, post, neuropil, synapse count |
| consolidated cell types | no | better cell type names |
| coordinates | no | 3D position per neuron |
| labels | no | community annotations with attribution |
| cell stats | no | cable length, area, volume (reference only) |

**The file names vary between Codex exports.** The connections table has
shipped as `connections_princeton.csv.gz` and as `connections.csv.gz`;
`find_connections_file()` takes whichever one your directory holds, preferring
the 5-synapse thresholded Princeton table, and `--connections-file` overrides
it. The reader also accepts several column spellings (`pre_root_id` or
`pre_pt_root_id` or `pre`, `syn_count` or `weight`, and so on) and tells you
exactly which column it could not find if the file is not what it expects.

Skip any file with `no_threshold` in the name (hundreds of MB of
single-synapse edges that are mostly detection noise), the per-synapse table
(gigabytes) and the skeleton archive (tens of gigabytes). The graph is at
neuron resolution and reads none of them.

## Steps

1. Go to https://codex.flywire.ai and sign in with a Google account. The first
   visit asks you to accept the FlyWire data terms.
2. Make sure the selected dataset is **FAFB v783**, the public release
   (the dataset picker is at the top of the app).
3. Open the "Download Data" app, or go straight to
   https://codex.flywire.ai/api/download?dataset=fafb
4. Download the tables above into one directory, keeping whatever names Codex
   gives them. If the list you see does not match the names above, download the
   neurons, classification and connections tables and let the reader work out
   the rest; it reports what it found.
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
