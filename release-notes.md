# Release Notes -- v0.3.1

> Released: 2026-09-18

ConnectomeKG is on PyPI. `pip install "connectome-kg[semantic]"` replaces cloning the repository.

## What changed

**Published to PyPI.** Every tagged release now uploads the same wheel and sdist that are attached to its GitHub Release, using trusted publishing, so the repository stores no PyPI token. kg-rag's connectome adapter needed a versioned dependency to point at, which is why this is happening now.

**The README works on PyPI.** Its links to the download guide, the rendering guide, the changelog and the licence were relative, and PyPI serves the README without those files. They now point at GitHub. The project page also links the documentation site, the issue tracker and the changelog.

No code changed since 0.3.0.

## Upgrading

Nothing to do for an existing clone. A new install can use pip: `pip install "connectome-kg[semantic]"`, with `[viz3d]` for the 3-D views.

---

_Full changelog: [CHANGELOG.md](https://github.com/Flux-Frontiers/connectome_kg/blob/main/CHANGELOG.md)_
