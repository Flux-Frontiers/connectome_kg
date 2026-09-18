# ConnectomeKG graph model

Read this before writing SQL against `connectomes/<dataset>/.connectomekg/graph.sqlite` or reading
node metadata. Every node id starts with `connectome:<dataset id>`, written
`P` below (`connectome:fafb783` for the real brain, `connectome:synthetic`
for the fixture).

## Contents

- Node kinds and ids
- Relations and their evidence
- Sign convention
- FAFB v783 counts

## Node kinds and ids

| kind | id | notes and metadata |
|---|---|---|
| dataset | `P` | `version`, `organism`, `licence`, `url`, `citation`, `n_neurons`, `n_pairs`, `n_synapses` |
| taxon | `P:c:<super>`, `P:c:<super>/<class>`, `P:c:<super>/<class>/<sub>` | `level` = super_class, class or sub_class; `n_neurons`. A sub class with no class is `P:c:<super>//<sub>` |
| taxon (visual) | `P:v:subsystem/<name>`, `P:v:family/<name>` | `level` = visual_subsystem or visual_family. Families are not a tree under subsystems |
| hemilineage | `P:hl:<name>` | `n_neurons`, `n_types` |
| nerve | `P:nv:<name>` | 8 in v783 (AN, CV, MxLbN, ...); `flow` counts |
| neuropil | `P:np:<abbrev>` | e.g. `P:np:LO_R`; `base`, `side`, `n_neurons`, `n_synapses` |
| column | `P:col:<left or right>/<id>` | column ids repeat across hemispheres; `x`, `y`, `p`, `q` hex position |
| connectivity_tag | `P:tag:<tag>` | only broadcaster, integrator, nsrn, highly_reciprocal_neuron |
| ontology_term | `P:fbbt:FBbt_<8 digits>` | `description`, `n_neurons`, `url`; prefix spelling normalised to `FBbt_` |
| cell_type | `P:t:<name>` | `n_neurons`, `n_left`, `n_right`, `super_class`, `class`, `sub_class`, `nt_type`, `sign`, `hemilineage`, `flow`, `visual_family`, `visual_subsystem`, `fbbt`, `median_length_nm` |
| neuron | `P:n:<root id>` | see below |
| label | `P:l:<12 hex>` | sha1 of the lowercased text; `qualname` is the label text |

Neuron metadata: `root_id`, `side`, `super_class`, `class`, `sub_class`,
`cell_type`, `hemilineage`, `flow`, `nerve`, `nt_type`, `nt_score`,
`nt_scores` (all six transmitters; all 0.0, with `nt_type` `""` and `sign` 0,
for the 19,658 v783 neurons Codex gives no prediction), `sign`, `x`/`y`/`z` (a marked point in nm,
not necessarily the soma), `n_in_syn`, `n_out_syn`, `length_nm`, `area_nm2`,
`volume_nm3`, `visual_family`, `visual_subsystem`, `visual_category`, `column`
(`"right/97"` or `""`), `connectivity_tags` (all 8 kinds), `refined_labels`,
`fbbt` (raw ids, unfiltered).

`name` is the cell type for neurons (root id when untyped) and `qualname` is
`<type>/<side>/<root id>`.

Only these kinds are embedded for `query`/`pack`: cell_type, neuropil,
hemilineage, label, taxon, nerve, ontology_term, connectivity_tag. Neurons
only with `--embed-neurons`; columns never.

## Relations and their evidence

Edge metadata is JSON in `edges.evidence`.

| rel | from -> to | evidence |
|---|---|---|
| SYNAPSES_TO | neuron -> neuron | `syn_count`, `nt_type`, `sign`, `neuropils` {abbrev: synapses} |
| TYPE_SYNAPSES_TO | cell_type -> cell_type | `syn_count`, `n_pairs`, `nt_type` |
| INSTANCE_OF | neuron -> cell_type | `side` |
| IN_NEUROPIL | neuron -> neuropil | `pre`, `post` synapse counts |
| INNERVATES | cell_type -> neuropil | `syn_count`; top 5 neuropils per type |
| CONTAINS | taxon -> taxon, taxon -> cell_type, visual subsystem -> family, family -> cell_type | `n_neurons` on subsystem -> family |
| MEMBER_OF | cell_type -> hemilineage | |
| MAPS_TO | cell_type -> ontology_term | `n_neurons`; kept only when on at least half as many neurons as the type's best-supported term |
| LABELED | neuron -> label | `user`, `affiliation`, `date` |
| MIRROR_OF | left neuron -> right neuron | only for types with exactly one neuron per side |
| VIA_NERVE | neuron -> nerve | |
| IN_COLUMN | neuron -> column | |
| TAGGED | neuron -> connectivity_tag | |
| IN_DATASET | top-level node -> dataset | |

`SYNAPSES_TO` holds one edge per connected pair (5-synapse threshold in the
Codex filtered table), summed over neuropils. A pair that synapses in three
neuropils is one edge whose `neuropils` has three entries.

## Sign convention

From Shiu et al. 2024: ACH, DA, OCT and SER are excitatory (+1); GABA and GLUT
are inhibitory (-1, glutamate via GluCl-alpha); unresolved is 0. A neuron's
`sign` comes from its predicted transmitter; an edge's `sign` is its
presynaptic neuron's.

## FAFB v783 counts

For checking a build, from the September 2026 download with every optional
file present:

| | count |
|---|---:|
| neurons | 139,255 |
| cell types | 8,772 |
| SYNAPSES_TO (pairs) | 3,732,460 |
| synapses | 50,666,648 |
| TYPE_SYNAPSES_TO | 507,287 |
| neuropils | 79 |
| columns / IN_COLUMN | 1,581 / 45,528 |
| ontology terms / MAPS_TO | 235 / 305 |
| nodes / edges | 157,698 / 5,072,285 |

Coverage: cell type 99.3%, resolved sign 85.9%, community label 79.0%, visual
family 68.3%, column 32.7%, ontology term 33.9%.
