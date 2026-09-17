"""Entry point for ``python -m connectomekg``.

The ``connkg`` script exists only after an install. Running the package
directly works from a clone with nothing installed, which is the first thing
anyone tries.
"""

from __future__ import annotations

from connectomekg.cli import cli

if __name__ == "__main__":
    cli()
