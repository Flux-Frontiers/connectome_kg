# SQL recipes for the ConnectomeKG store

Query the store directly when the CLI has no command for the question. It is
SQLite with JSON1 in WAL mode. Open it plainly and run only SELECTs, never
while a build is writing:

```bash
sqlite3 .connectomekg/graph.sqlite
```

Not `sqlite3 -readonly`: with no other connection open there is no `-shm`
file, a read-only open cannot create one, and it fails with "unable to open
database file".

Ids use the prefix `connectome:fafb783`; see graph-model.md. The tables are
`nodes(id, kind, name, qualname, docstring, metadata)` and
`edges(src, rel, dst, evidence)`, indexed on `kind`, `name`, `src`, `dst` and
`rel`. Filter on those before any `json_extract` over neurons: there are
139,255 of them and 3.7 M synapse edges.

## Contents

- A cell type's partners
- Neurons of a type, with metadata
- Types in a neuropil, column, family or nerve
- Ontology terms
- Labels and who made them
- Transmitter uncertainty

## A cell type's partners

Strongest downstream types of LC4 (type level, already aggregated):

```sql
SELECT b.name, json_extract(e.evidence,'$.syn_count') AS syn,
       json_extract(e.evidence,'$.n_pairs') AS pairs, json_extract(e.evidence,'$.nt_type') AS nt
FROM edges e JOIN nodes b ON b.id = e.dst
WHERE e.src = 'connectome:fafb783:t:LC4' AND e.rel = 'TYPE_SYNAPSES_TO'
ORDER BY syn DESC LIMIT 15;
```

Swap `e.src`/`e.dst` and join `b` on `e.src` for upstream.

## Neurons of a type, with metadata

```sql
SELECT n.id, json_extract(n.metadata,'$.side') AS side,
       json_extract(n.metadata,'$.n_out_syn') AS out_syn,
       json_extract(n.metadata,'$.length_nm') AS cable_nm
FROM edges e JOIN nodes n ON n.id = e.src
WHERE e.dst = 'connectome:fafb783:t:DNp01' AND e.rel = 'INSTANCE_OF';
```

Synapses between two specific neurons, with the neuropil breakdown:

```sql
SELECT evidence FROM edges
WHERE rel = 'SYNAPSES_TO' AND src = 'connectome:fafb783:n:<pre root id>'
  AND dst = 'connectome:fafb783:n:<post root id>';
```

## Types in a neuropil, column, family or nerve

```sql
-- types innervating the right lobula, by synapses
SELECT t.name, json_extract(e.evidence,'$.syn_count') AS syn
FROM edges e JOIN nodes t ON t.id = e.src
WHERE e.dst = 'connectome:fafb783:np:LO_R' AND e.rel = 'INNERVATES'
ORDER BY syn DESC LIMIT 20;

-- what sits in one retinotopic column
SELECT json_extract(n.metadata,'$.cell_type') AS type, COUNT(*)
FROM edges e JOIN nodes n ON n.id = e.src
WHERE e.dst = 'connectome:fafb783:col:right/97' AND e.rel = 'IN_COLUMN'
GROUP BY type ORDER BY 2 DESC;

-- cell types in a visual family
SELECT t.name FROM edges e JOIN nodes t ON t.id = e.dst
WHERE e.src = 'connectome:fafb783:v:family/T4 Neuron' AND e.rel = 'CONTAINS';

-- neurons entering or leaving through the antennal nerve, by type
SELECT json_extract(n.metadata,'$.cell_type') AS type, COUNT(*)
FROM edges e JOIN nodes n ON n.id = e.src
WHERE e.dst = 'connectome:fafb783:nv:AN' AND e.rel = 'VIA_NERVE'
GROUP BY type ORDER BY 2 DESC LIMIT 20;
```

List what exists before guessing a name:
`SELECT name FROM nodes WHERE kind = 'nerve';` (or `column`,
`connectivity_tag`, `neuropil`; for families,
`WHERE kind = 'taxon' AND id LIKE '%:v:family/%'`).

## Ontology terms

```sql
-- a type's Fly Anatomy Ontology terms
SELECT o.name, o.qualname, json_extract(e.evidence,'$.n_neurons')
FROM edges e JOIN nodes o ON o.id = e.dst
WHERE e.src = 'connectome:fafb783:t:T4b' AND e.rel = 'MAPS_TO';

-- types for a term
SELECT t.name FROM edges e JOIN nodes t ON t.id = e.src
WHERE e.dst = 'connectome:fafb783:fbbt:FBbt_00003733' AND e.rel = 'MAPS_TO';
```

## Labels and who made them

```sql
SELECT l.qualname, json_extract(e.evidence,'$.user') AS who,
       json_extract(e.evidence,'$.affiliation') AS lab, json_extract(e.evidence,'$.date') AS date
FROM edges e JOIN nodes l ON l.id = e.dst
WHERE e.src = 'connectome:fafb783:n:<root id>' AND e.rel = 'LABELED';
```

## Transmitter uncertainty

Neurons of a type whose winning transmitter score is weak. Exclude neurons
with no prediction first: 19,658 v783 neurons have `nt_type` `""`, score 0.0
and six zero `nt_scores`, and a bare `nt_score < 0.6` returns those, not
uncertain calls.

```sql
SELECT n.id, json_extract(n.metadata,'$.nt_type'), json_extract(n.metadata,'$.nt_score'),
       json_extract(n.metadata,'$.nt_scores')
FROM edges e JOIN nodes n ON n.id = e.src
WHERE e.dst = 'connectome:fafb783:t:Dm4' AND e.rel = 'INSTANCE_OF'
  AND json_extract(n.metadata,'$.nt_type') != ''
  AND json_extract(n.metadata,'$.nt_score') < 0.6;
```
