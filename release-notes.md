# Release Notes -- v0.3.0

> Released: 2026-09-18

Each connectome now gets its own knowledge graph. A second release -- another FAFB version, MANC, hemibrain -- is built beside the first instead of on top of it. A built graph can also be queried without the 34 GB Codex download it came from.

## What changed

**One graph per connectome.** Graphs live in `<root>/connectomes/<dataset_id>/.connectomekg/`, each with its own vector index and snapshot history. This is the layout GutenbergKG uses for books. `--dataset ID` goes before the command and picks one. A build without it writes to `fafb783`, and every other command uses the only built dataset, or stops and lists them when there are several. `connkg-mcp` takes the same option, and `connkg datasets` lists what is built. KGRAG's registry scan finds each dataset as a separate KG.

**`--dataset` replaces `--dataset-id`.** This breaks scripts that passed `--dataset-id`, which is why this is a minor release rather than a patch.

**Querying a built graph no longer needs the source data.** `connkg query`, and anything else that opened an existing graph, including kg-rag's connectome adapter, failed with `source='codex' needs data_dir` unless the Codex release was on hand. The tables now load only when a build needs them.

## Upgrading

Move a graph built by an earlier version into the new layout, from the directory you pass as `--root`:

```bash
mkdir -p connectomes/fafb783/.connectomekg
mv .connectomekg/*.sqlite* connectomes/fafb783/.connectomekg/
```

Until you do, commands stop and print that command. Replace `--dataset-id X` in scripts with `--dataset X`, placed before the command. A KGRAG registry entry that points at the old path needs registering again.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
