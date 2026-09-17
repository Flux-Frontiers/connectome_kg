# Rendered output

Output, not source. Everything here regenerates from `.connectomekg/graph.sqlite`
plus `connkg quilt` / `connkg viz3d` -- see
[docs/rendering.md](../docs/rendering.md). Layout follows
[quiltwright](https://github.com/Flux-Frontiers/quiltwright)'s own `renders/`.

| Directory | Contents | Kept |
|---|---|---|
| `stills/` | Working renders: `connkg quilt --still` images and `--preview` PNGs | local scratch, never committed |
| `quilts/` | Looking Glass quilts, `connkg quilt --out` default | never committed -- one 16" landscape quilt is tens of MB; regenerate with `connkg quilt` |
| `views/` | Per-view captures or test frames, if produced | local scratch, never committed |
| `reports/` | Reserved for a per-render provenance record (scene, commit, camera, counts) | tracked, once a report writer exists -- none is built yet |

A quilt's filename carries its own metadata (`{stem}_qs{cols}x{rows}a{aspect}.png`,
e.g. `DNp01_qs8x6a1.77778.png`), which is why `.gitignore` matches that
pattern at every depth rather than just under `renders/quilts/` -- a quilt is
ignored wherever it lands.
