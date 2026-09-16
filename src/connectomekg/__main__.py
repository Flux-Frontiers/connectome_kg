"""Entry point for ``python -m connectomekg``.

The ``connectome-kg`` script exists only after an install. Running the package
directly works from a clone with nothing installed, which is the first thing
anyone tries.
"""

from __future__ import annotations

import sys

from connectomekg.cli import main

if __name__ == "__main__":
    sys.exit(main())
