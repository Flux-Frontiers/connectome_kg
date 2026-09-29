# Release Notes -- v0.8.1

> Released: 2026-09-29

This is a maintenance release. ConnectomeKG now uses the shared query validators from kgmodule-utils instead of its own copies, and the fleet dependency floors are raised to the latest releases. No commands, options or graph contents change.

## What changed

**Shared query validation.** The local `bounded_int` and `require_query` helpers are removed. They were the originals that kgmodule-utils lifted and hardened in 0.25.0, so the two copies had started to diverge. `query()` and `pack()` now validate through the base class, still before the missing-index check, and the 500-character query cap is set as a class attribute. The `MAX_K` and `MAX_MAX_NODES` constants, which only those checks used, are gone with them.

**Newer dependency floors.** `kgmodule-utils` is now `>=0.26.0` and `quiltwright` is `>=0.16.0`, and the lock file is refreshed.

## Upgrading

Nothing to do. No graph needs a rebuild: the extractor is unchanged, and the FAFB, BANC and MCNS graphs built with 0.8.0 stay valid. Code that imported `bounded_int`, `require_query`, `MAX_K` or `MAX_MAX_NODES` from `connectomekg.validation` should import the validators from `kg_utils.validation` instead.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
