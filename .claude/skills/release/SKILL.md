---
name: release
description: >
  Cut a ConnectomeKG release. Runs the generic /release for the spine and adds
  what differs here: the release snapshot measures the FAFB graph, so its
  subject is corpus:fafb783. Use when releasing connectome_kg / connkg, cutting
  a version, or tagging v*.
---

# Release Workflow (connectome_kg / ConnectomeKG)

**Run the generic `/release` command for the spine; this file carries only what
is different here.** The generic (`~/.claude/commands/release.md`) owns the
steps that are the same fleet-wide, including the release snapshot (its Step
5b). Where the two disagree, **this file wins**.

## Step 5b -- Save a release snapshot

Run the generic's Step 5b in its position: after the version bump, before the
commit, so the snapshot file lands in the release commit.

The repo-specific part is the **subject**. `connkg snapshot save` measures the
connectome graph built from a Codex release, not this package's code, so
`repo:connectome-kg` is the wrong subject and `corpus:fafb783` is the right
one. The command defaults to `corpus:<dataset id>`; pass it anyway so the
release record does not depend on which graph happened to be built last.

```bash
poetry install --only-root
connkg --root . --dataset fafb783 build --data-dir fafb_v783 --no-index --wipe
connkg --root . --dataset fafb783 snapshot save <version> --subject corpus:fafb783 --force
ls connectomes/fafb783/.connectomekg/snapshots/<version>.json
```

- **The graph must be the real FAFB v783 build.** A synthetic fixture graph in
  `connectomes/fafb783/` would be recorded as the release. Always pass
  `--dataset fafb783` so another built dataset can never be picked up. The build takes about 4
  minutes; the maintainer runs it and watches it rather than an agent running
  it in the background.
- **Reinstall before snapshotting.** `version` and `tool_version` come from the
  installed distribution, not `pyproject.toml`, so a snapshot taken straight
  after the bump records the previous version inside a file keyed to the new
  one.
- **Use `--force`.** When the graph has not changed since the last release, the
  metrics match and `save_snapshot` takes its dedup path, which renames the
  previous release's entry and deletes its file rather than appending.
- **Pass the version.** Without it the snapshot is keyed on a UTC timestamp,
  which is right between releases and wrong for one. The git tree hash is
  recorded as provenance and is never the key.

`connectomes/fafb783/.connectomekg/snapshots/` is **tracked** (the databases beside it are not),
so stage it with the release in Step 6.
