# Release Notes -- v0.3.2

> Released: 2026-09-19

A packaging fix. Two dependency floors in 0.3.1 allowed installs that could not work, and this release raises them to the versions the code actually needs.

## What changed

**The `mcp` floor matches the MCP server.** `connkg-mcp` builds its server with `FastMCP`, passing `lifespan=` and `instructions=`. The `mcp` package only accepts both from 1.3.0, and before 1.2.0 it has no `FastMCP` at all, so the old `mcp>=1.0.0` floor let a resolver choose a version where the server fails to start. The floor is now `mcp>=1.3.0,<2`.

**The `numpy` floor matches the supported Pythons.** ConnectomeKG requires Python 3.12 or later, and numpy 1.26.0 is the first release that installs on 3.12. The floor moves from 1.24.0 to 1.26.0.

**The README reflects kg-rag.** The ConnectomeKG adapter shipped in kg-rag 0.16.0, so the status line now points at `pip install "kg-rag[connectome]"` instead of a future release.

No code changed since 0.3.1, and the graph a build produces is unchanged.

## Upgrading

Nothing to do. An environment that already resolved newer `mcp` and `numpy` versions, which is any install made recently, is unaffected. `pip install -U connectome-kg` picks up the corrected metadata.

---

_Full changelog: [CHANGELOG.md](https://github.com/Flux-Frontiers/connectome_kg/blob/main/CHANGELOG.md)_
