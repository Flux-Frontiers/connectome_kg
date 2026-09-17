"""Colour constants shared by the 2-D and 3-D views of a connectome.

Split out of :mod:`connectomekg.viz` so that :mod:`connectomekg.scene` (the
viz3d scene builder) can use the same palette without importing ``viz.py`` --
which imports ``plotly`` at module scope, a dependency of the ``viz`` extra,
not ``viz3d``. This mirrors ``genealogy_kg`` keeping its palette in
``theme.py`` rather than ``viz.py`` for the identical reason. Nothing here
needs any extra at all.
"""

from __future__ import annotations

from typing import Final

#: Colour per super class. Okabe-Ito first, for the classes most types belong to.
SUPER_CLASS_COLOR: Final[dict[str, str]] = {
    "central": "#0072B2",
    "optic": "#009E73",
    "visual_projection": "#56B4E9",
    "visual_centrifugal": "#CC79A7",
    "sensory": "#E69F00",
    "sensory_ascending": "#F0E442",
    "ascending": "#D55E00",
    "descending": "#882255",
    "motor": "#332288",
    "endocrine": "#999933",
}

#: Fallback colour for a super class not in :data:`SUPER_CLASS_COLOR`.
UNKNOWN_COLOR: Final = "#9AA3AB"

#: Colour per transmitter sign: excitatory warm, inhibitory cool, unknown grey.
SIGN_COLOR: Final[dict[int, str]] = {1: "#C8553D", -1: "#2E6F9E", 0: "#9AA3AB"}

__all__ = ["SIGN_COLOR", "SUPER_CLASS_COLOR", "UNKNOWN_COLOR"]
