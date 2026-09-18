# Release Notes -- v0.2.1

> Released: 2026-09-17

Casting a scene to the Looking Glass now sweeps a 35-degree view cone instead of the panel's full cone.

## What changed

**Cast to Looking Glass fuses cleanly.** The `kgmodule-utils` floor moves to 0.22.0, which routes the Cast button through `quiltwright.quilt.resolve_view_cone`. The 16" landscape preset's native cone is 50 degrees -- wider than reliably fuses -- so casts previously showed ghosting the CLI's own renders never had. No code in this repo changed; the fix arrives through the shared `cast_scene_to_looking_glass` helper.

## Upgrading

`poetry update kgmodule-utils` (or `pip install -U kgmodule-utils`). No config or API changes.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
