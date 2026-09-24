# Getting the data

ConnectomeKG builds three releases, each into its own store: FlyWire **FAFB
v783** (the female brain), **BANC v888** (female brain and ventral nerve cord)
and the FlyEM **Male CNS v1.0** (male brain and nerve cord). Most of this page
is FAFB, which has the most files and the most traps; [BANC v888 and MCNS
v1.0](#banc-v888-and-mcns-v10) covers the other two, and [soma
positions](#soma-positions-for-banc-and-mcns) the one file they each need for
the 3-D views.

The build reads the Codex export files. FAFB's are free for non-commercial use
under CC BY-NC-SA 4.0 and Codex requires a **Google** sign-in to fetch them,
so this is a manual step. Under 100 MB for the files the build reads.

## Skipping the download

Nothing here is needed to try the tool. `connkg fixture` writes a synthetic
connectome in the same Codex format, with feeding, escape and grooming
circuits planted in it, and the build reads that exactly as it reads the real
release:

```bash
connkg fixture --out /tmp/fake --n 2000
connkg --root /tmp/kg --dataset synthetic build --source synthetic --n 2000
```

The synthetic graph answers the same commands with the same grammar. Its cell
type names are its own, though -- `GRN_sugar` and `MN9` exist there and not in
v783 -- so an example written against one does not run against the other.

For real anatomy, carry on.

## The portal lists labels, not file names

This is the thing that trips everyone. The download page shows friendly labels;
what lands on disk is a different name, and that name is what the reader looks
for. The file you most need, `neurons.csv.gz`, is listed as "Neurotransmitter
Type Predictions".

`connkg files` prints this table, less the last column, at any time.

The last column records what the reference download holds: the September
2026 `fafb_v783/` in which every file below was checked against the portal.

| portal label | downloads as | size | needed | reference download |
|---|---|---|---|---|
| Neurotransmitter Type Predictions | `neurons.csv.gz` | 1,680 KB | **required** | yes |
| Classification / Hierarchical Annotations | `classification.csv.gz` | 934 KB | **required** | yes |
| Connections (Filtered) | `connections_princeton.csv.gz` | 68 MB | **required** | yes |
| Cell Types | `consolidated_cell_types.csv.gz` | 902 KB | optional | yes |
| Marked Neuron Coordinates | `coordinates.csv.gz` | 5,315 KB | optional | yes |
| Community Labels (Raw) | `labels.csv.gz` | 4,771 KB | optional | yes |
| Cell Size Measurements | `cell_stats.csv.gz` | 2,527 KB | optional | yes |
| Visual Neuron Annotations | `visual_neuron_types.csv.gz` | 632 KB | optional | yes |
| Visual Neuron Columns | `column_assignment.csv.gz` | 463 KB | optional | yes |
| Connectivity Tags | `connectivity_tags.csv.gz` | 638 KB | optional | yes |
| Community Labels (Refined) | `processed_labels.csv.gz` | 1,018 KB | optional | yes |

Three required files, about 71 MB. The optional ones add cell type names,
3D positions, community annotations with attribution, cable length, area and
volume, visual families and subsystems, retinotopic columns, connectivity
tags, and Fly Anatomy Ontology (FBbt) ids from the refined labels. Each is
read when present and skipped when not.

Two things about the optional files that are easy to get wrong:

- `column_assignment.csv.gz` numbers columns separately in each optic lobe,
  so a column is a hemisphere plus an id: 796 ids, 1,581 columns.
- `connectivity_tags.csv.gz` holds comma-separated tags. The portal's
  "28 unique values" counts combinations of 8 tags. Four of the 8 are on 44%
  to 95% of all neurons, so only `broadcaster`, `integrator`, `nsrn` and
  `highly_reciprocal_neuron` get graph nodes; every tag stays in neuron
  metadata.

### Safari strips the `.gz` without decompressing

The portal serves gzip, but Safari saves these as `neurons.csv`,
`labels.csv` and so on: it drops the `.gz` and leaves the bytes compressed.
Download a second copy and you get `labels.csv.csv`. Either way the reader
will not find the file, because it looks for `labels.csv.gz`.

Check what you actually have before renaming anything:

```bash
file *.csv*          # "gzip compressed data" means it is still compressed
gzip -t *.csv.gz     # silence means every archive is intact
```

The name recorded inside the gzip header is the real one, and `file` prints
it (`was "labels.csv"`). Rename to that plus `.gz`:

```bash
mv labels.csv.csv labels.csv.gz
```

Do not gunzip them. The reader hands the `.csv.gz` path to pandas, which
decompresses on the fly, and unpacking these costs about 340 MB and loses
the checksums `verify` matches against.

Not read by the build. Downloading any of these is harmless; the build
ignores them. "not checked" means nobody has downloaded that one to confirm
the name it lands under, and the manifest's names are not a reliable guide:
it lists the Synapse Table as `synapse_table.csv.gz`.

| portal label | lands as | size | why the build skips it | reference download |
|---|---|---|---|---|
| Synapse Table | `fafb_v783_princeton_synapse_table.csv.gz` | 2,695 MB | the graph is at neuron resolution, it uses synapse counts | yes |
| Neuron Skeletons | `sk_lod1_783_healed/` | 13 GB zipped, 31 GB unpacked | coordinates give one position per neuron instead | yes |
| Connections (Unfiltered) | not checked | 277 MB | millions of single-synapse rows, mostly detection noise | no |
| Proofread Cell Names And Groups | not checked | 1,182 KB | cell types carry the identity the graph uses | no |
| Synapse Coordinates / Attachment Rates | not checked | varies | per-synapse detail the neuron-level graph does not use | no |
| Anything marked "prior to July 2025" | not checked | varies | superseded; mixing detectors is not valid | no |

The skeleton archive unpacks to 139,273 `.swc` files, one per neuron, named by
root id. The Synapse Table and Neuron Skeletons are the two downloads that
time out: Safari reports `NSURLErrorDomain -1001` and leaves a `.download`
bundle that does not resume. Restart the download rather than waiting.

Once the graph is built, read the skeletons in with
`connkg skeletons --data-dir fafb_v783 -j 12`. It writes the 2.5 GB cache the
3-D circuit view draws from and gives every neuron its soma, and it is the
only thing that needs those 31 GB -- 2m 39s across twelve cores, or 19m 30s
on one if `-j` is left at its default. See
[Rendering in 3-D](rendering.md#the-skeleton-cache).

### Classification no longer carries `cell_type`

Current exports of `classification.csv.gz` have no `cell_type` column; the
type moved to `consolidated_cell_types.csv.gz` as `primary_type`. The reader
asks only for the columns a download actually has, so both old and new
exports load. The practical consequence is that `consolidated_cell_types.csv.gz`
is optional only in the sense that a build succeeds without it: skip it on a
current export and every neuron's cell type is empty. Download it.

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

5. Verify the directory against the manifest, then build. The `connkg`
   script exists only after `pip install -e .`; from a bare clone use
   `PYTHONPATH=src python -m connectomekg` instead, and with Poetry prefix
   `poetry run`.

   ```bash
   connkg verify --data-dir /path/to/fafb_v783
   connkg --root . --dataset fafb783 build --data-dir /path/to/fafb_v783
   connkg --root . analyze
   ```

   `verify` hashes every file against the SHA-256 values recorded in
   `connectomekg/manifest.py`, which were taken from an independent August 2026
   download and are expectations rather than authority. A mismatch usually means
   Codex re-exported the file. Check the counts the build prints against the
   published 139,255 neurons and 3.73 M connected pairs, and if those are right,
   update the manifest. `--no-checksums` skips the hashing while you sort names
   out.

   `build` reports each extraction stage on stderr, and a running count every
   250,000 synaptic pairs, then ends with "writing to SQLite". The write that
   follows has no progress of its own and is most of the run; to watch it,
   follow the write-ahead log in another shell with
   `while sleep 2; do ls -lh connectomes/fafb783/.connectomekg/graph.sqlite-wal; done`. Use
   `--wipe` when restarting after an interrupted build, or the new graph is
   written on top of the partial one.

   After the graph, `build` embeds the cell types, neuropils, labels, taxa and
   the other named nodes into the vector index that `connkg query` searches:
   16,861 short texts, 25 seconds and 29 MB on an Apple M5 Max (September
   2026). This needs the `semantic` extra; without it `build` stops before
   doing anything and says so. `--no-index` builds the SQLite graph only.

   `--no-index` does not delete an index from an earlier build, so `build`
   warns when it leaves one in place. That index was built from the previous
   graph and may not match the new one; rebuild without `--no-index` to
   refresh it.

6. Measured footprint, `--no-index` on the real v783 release with every
   optional file present (Apple silicon, September 2026): **3 minutes 57
   seconds and 2.1 GB** of SQLite for 157,698 nodes and 5,072,285 edges.

   Keep about 4 GB free rather than 2. The whole build lands in one
   transaction, so `graph.sqlite` stays near 100 MB while the write-ahead log
   grows to roughly 2 GB, and both exist at once during the checkpoint that
   ends the build.

   Every build writes `reports/build_<timestamp>.md`: versions and git commit,
   the options, each input file's SHA-256 against the manifest, time per
   extraction stage, the counts written, and peak resident memory. `connkg
   skeletons` writes `reports/skeletons_<timestamp>.md` the same way. Both are
   gitignored; `git add -f` the ones worth keeping. `connkg snapshot save`
   records the built graph's metrics in
   `connectomes/fafb783/.connectomekg/snapshots/`, which is tracked -- take a
   snapshot after a skeletons pass as well as after a build, since the soma
   back-fill changes the graph the snapshot measures.

## If Codex offers something other than what you expected

The portal's file set has changed over time, and there are public mirrors of
the same v783 release that need no sign-in (a Zenodo record accompanies the
annotation paper, and `flyconnectome/flywire_annotations` on GitHub carries the
annotation tables). Any of them work as long as the directory ends up with a
neurons table, a classification table and a connections table whose columns the
reader recognizes. Run `connkg verify --data-dir <dir> --no-checksums`
to see what it detects before building.

## BANC v888 and MCNS v1.0

Codex serves two more releases that the same reader builds:

| dataset id | release | neurons | pairs kept | license |
|---|---|---|---|---|
| `banc888` | BANC v888, adult female brain and ventral nerve cord | 158,262 | 1,528,585 | CC BY 4.0 |
| `mcns1` | FlyEM Male CNS v1.0, adult male brain and ventral nerve cord | 166,700 | 6,242,085 | CC BY 4.0 |

Their download is shorter than FAFB's. Switch the Codex dataset selector to
the release, open "Download Data", and take two files: **Neuron Attributes**,
which lands as `neurons.csv.gz`, and the connections table,
`connections_princeton.csv.gz`. Put each release in its own directory:

```bash
connkg verify --data-dir banc_v888 --no-checksums
connkg --root . --dataset banc888 build --data-dir banc_v888
connkg --root . --dataset mcns1 build --data-dir mcns_v1
```

Measured on Apple silicon, September 2026, vector index included: BANC in
1 minute 22 seconds to a 1.2 GB graph (174,014 nodes, 2,695,592 edges), MCNS
in 3 minutes 20 seconds to 2.8 GB (188,546 nodes, 8,122,640 edges).

Neuron Attributes is one consolidated table with display-name columns
(`Root ID`, `Super Class`, `Primary Cell Type`, ...) in place of FAFB's
split files. The reader recognizes it by its header and needs no
classification file. What differs from FAFB:

- **Pairs are thresholded at 5 synapses.** BANC's connections table keeps
  pairs of 3 or more; the reader drops any pair whose synapses, summed over
  its neuropils, come to fewer than 5, as FAFB's filtered table and MCNS
  already do. Half of BANC's 3,037,361 pairs fall below. The threshold is
  `min_pair_syn` on the dataset record.
- **Super classes take FAFB's spelling.** BANC's `optic_lobe_intrinsic` and
  MCNS's `ol_intrinsic` both become `optic`; the nerve cord's intrinsic
  neurons become `ventral_nerve_cord`. MCNS's `*_tbc` (to be confirmed)
  classes are kept as given.
- **Connection transmitters come from the presynaptic neuron.** Both
  exports leave the connections table's `nt_type` empty.
- **Histamine is inhibitory** (sign -1), as it is at the photoreceptor
  synapse; FAFB's predictions have no histamine class. BANC's tyramine
  neurons stay unresolved (0).
- **Community labels are split into one label each.** MCNS's are
  `key: value` pairs; `flywireType: Tm33` names the matching FAFB type. Two
  keys are left out: `statusLabel`, which is proofreading status, and
  `mancBodyid`, a per-neuron id.
- **The export has no soma positions or cell sizes.** Its coordinate and
  size columns are empty. Cell sizes stay empty; positions come from one
  extra file per release, below.
- **The nerve cord's neuropils and nerves** have names and regions of their
  own (`LegNp_T1_L`, `IntTct`, `ADMN_L`, `cervical_connective`, ...); the
  neuropil surface meshes are FAFB's only.

The nerve cord is what these releases add. In BANC, the giant fiber's
(`DNp01`) outputs reach the jump motor neuron `TTMn`, `PSI` and the `GFC2`,
`GFC3` and `GFC4` interneurons in the intermediate tectulum, where FAFB's
graph stops at the neck. The counts are small, 8 to 13 synapses per partner,
because the giant fiber drives TTMn and PSI mostly through electrical
synapses, which EM synapse detection does not record. A cone over it needs a
low `--min-syn`: `connkg --dataset banc888 cone DNp01 --min-syn 5`.

Cite Bates et al. 2026 (*Nature*, doi:10.1038/s41586-026-10735-w) and the
BANC data deposit (doi:10.7910/DVN/7WTH1N) for BANC, and the Male CNS
connectome paper (bioRxiv, doi:10.1101/2025.10.09.680999) for MCNS.

## Soma positions for BANC and MCNS

Codex exports no coordinates for either release, and without them the 3-D
views have nothing to place: no cell-body cloud, no circuit view, and no flow
view either, since neuropil centres are derived from the positions of the
neurons in them. Both projects publish the positions themselves, outside
Codex. Each is one file, and the build picks it up from the release directory
automatically.

| release | file | size | download from |
|---|---|---|---|
| BANC v888 | `banc_888_meta.feather` | 55 MB | `https://storage.googleapis.com/lee-lab_brain-and-nerve-cord-fly-connectome/compiled_data/banc_888/banc_888_meta.feather` |
| MCNS v1.0 | `body-annotations-male-cns-v1.0-minconf-0.5.feather` | 13 MB | `https://storage.googleapis.com/flyem-male-cns/v1.0/connectome-data/flat-connectome/body-annotations-male-cns-v1.0-minconf-0.5.feather` |

```bash
curl -L -o banc_v888/banc_888_meta.feather \
  https://storage.googleapis.com/lee-lab_brain-and-nerve-cord-fly-connectome/compiled_data/banc_888/banc_888_meta.feather

curl -L -o mcns_v1/body-annotations-male-cns-v1.0-minconf-0.5.feather \
  https://storage.googleapis.com/flyem-male-cns/v1.0/connectome-data/flat-connectome/body-annotations-male-cns-v1.0-minconf-0.5.feather
```

`connkg verify` reports which table it found, or that it found none, so the
build never silently produces a graph the 3-D views cannot draw:

```
note     : consolidated neuron-attributes export (the BANC and MCNS layout)
note     : soma positions from body-annotations-male-cns-v1.0-minconf-0.5.feather
```

Both are matched on their columns rather than their names, so a renamed or
re-released file still works; the reader holds one entry per layout in
`SOMA_POSITION_SOURCES`. BANC's `root_position_nm` is already in nanometres
and is keyed on `root_888`, the v888 root id -- the table's own `root_id` is a
later snapshot and matches 13,600 fewer of this build's neurons. MCNS's
`somaLocation` is an `[x y z]` array in 8 nm EM voxels, scaled on read.

Coverage is lower than FAFB's 96.7%, because a neuron whose soma was never
located gets no position and is left out of the cloud:

| release | positioned | of | coverage |
|---|---:|---:|---:|
| BANC v888 | 140,304 | 158,262 | 88.7% |
| MCNS v1.0 | 139,662 | 166,700 | 83.8% |

Both files are CC BY 4.0, like the releases they describe. Neither is needed
to build a graph or to run any query -- they matter only for what gets drawn.

## License reminder

The built index over FlyWire FAFB data is a derived work under CC BY-NC-SA
4.0. BANC and MCNS are CC BY 4.0, which allows commercial use with
attribution. Keep every download and the built graphs
(`connectomes/*/.connectomekg/*.sqlite`) out of the repository (`.gitignore`
already does), and keep FAFB out of anything commercial. Cite Dorkenwald et
al. 2024, Schlegel et al. 2024 and Eckstein et al. 2024 for the FAFB data.
