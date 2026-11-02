# Release Notes -- v0.10.1

> Released: 2026-11-02

A security release for the 3-D extra. A pip install of
`connectome-kg[viz3d]` could resolve an older quiltwright and, through it,
Pillow 12.3.0 and its 41 advisories, some of them critical. The extra now
floors quiltwright at 0.17.0, the first release that floors Pillow at
13.0.0. The graph, the queries and the tools do not change.

## What changed

**quiltwright 0.17.0 is the floor in `viz3d`.** The floor moves from 0.16.0
to 0.17.0, which carries `pillow>=13.0.0` in its own metadata, so the
extra always gets the patched Pillow. The lock moves quiltwright to 0.17.0.

**The lock is refreshed.** Pillow 13.0.0, certifi, filelock, setuptools and
virtualenv move to patched releases.

## Upgrading

`pip install -U "connectome-kg[viz3d]"`. No rebuild: the FAFB v783 graph and
its somas are unchanged.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
