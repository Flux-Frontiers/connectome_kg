"""Color constants shared by the 2-D and 3-D views of a connectome.

Split out of :mod:`connectomekg.viz` so that :mod:`connectomekg.scene` (the
viz3d scene builder) can use the same palette without importing ``viz.py`` --
which imports ``plotly`` at module scope, a dependency of the ``viz`` extra,
not ``viz3d``. This mirrors ``genealogy_kg`` keeping its palette in
``theme.py`` rather than ``viz.py`` for the identical reason. Nothing here
needs any extra at all.
"""

from __future__ import annotations

from typing import Final

#: Color per super class. Okabe-Ito first, for the classes most types belong to.
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
    "ventral_nerve_cord": "#117733",
}

#: Fallback color for a super class not in :data:`SUPER_CLASS_COLOR`.
UNKNOWN_COLOR: Final = "#9AA3AB"

#: Color per transmitter sign: excitatory warm, inhibitory cool, unknown gray.
SIGN_COLOR: Final[dict[int, str]] = {1: "#C8553D", -1: "#2E6F9E", 0: "#9AA3AB"}

#: Sequential ramp for *ordered* groups -- the hops of a path or a cone, where
#: 0 is the source and the last is as far as the answer reaches. The Okabe-Ito
#: sets above are categorical and carry no order, so reading "which hop is
#: this" off them means consulting a key; these are the viridis anchors, which
#: rise monotonically in luminance. That is what makes the order legible to a
#: color-blind reader too: the sequence survives as light-to-dark even when
#: the hues do not separate.
HOP_RAMP: Final[tuple[str, ...]] = ("#440154", "#3B528B", "#21918C", "#5EC962", "#FDE725")


def hop_color(hop: int, n_hops: int) -> str:
    """The color for one hop of an ordered sequence.

    :param hop: Which hop, from 0.
    :param n_hops: How many there are; 1 draws the first anchor.
    :return: A ``#RRGGBB`` color from :data:`HOP_RAMP`, interpolated between
        anchors so any number of hops spans the whole ramp.
    """
    if n_hops <= 1:
        return HOP_RAMP[0]
    position = max(0.0, min(1.0, hop / (n_hops - 1))) * (len(HOP_RAMP) - 1)
    low = int(position)
    if low >= len(HOP_RAMP) - 1:
        return HOP_RAMP[-1]
    t = position - low
    a, b = HOP_RAMP[low], HOP_RAMP[low + 1]
    channels = (
        round(int(a[i : i + 2], 16) * (1 - t) + int(b[i : i + 2], 16) * t) for i in (1, 3, 5)
    )
    return "#" + "".join(f"{c:02X}" for c in channels)


#: Color per brain region (keys of ``connectomekg.neuropils.REGION_NAMES``),
#: for neuropil spheres and flow tubes. Only the eight saturated Okabe-Ito
#: colors, which stay distinguishable under the common forms of color
#: blindness; no pastels. Sixteen regions do not fit in eight colors, so
#: regions that neighbour each other in the brain share one: the central and
#: lateral complexes, the lateral horn and superior neuropils, the inferior and
#: ventromedial neuropils, and the antennal lobe with the periesophageal
#: neuropils and gnathal ganglia. The ventral nerve cord (BANC and MCNS only)
#: takes sky blue, shared with the ventrolateral neuropils at the other end of
#: the animal; its nerves and the cervical connective, which hold few
#: synapses, go black with the ocellar ganglion. Neuropil labels tell them
#: apart.
REGION_COLOR: Final[dict[str, str]] = {
    "OL": "#E69F00",  # orange
    "VLNP": "#56B4E9",  # sky blue
    "MB": "#D55E00",  # vermillion
    "CX": "#CC79A7",  # reddish purple
    "LX": "#CC79A7",
    "LH": "#F0E442",  # yellow
    "SNP": "#F0E442",
    "INP": "#0072B2",  # blue
    "VMNP": "#0072B2",
    "AL": "#009E73",  # bluish green
    "PENP": "#009E73",
    "GNG": "#009E73",
    "OCG": "#000000",  # black
    "UNASGD": "#000000",
    "VNC": "#56B4E9",
    "NERVE": "#000000",
    "CV": "#000000",
}

__all__ = ["REGION_COLOR", "SIGN_COLOR", "SUPER_CLASS_COLOR", "UNKNOWN_COLOR"]
