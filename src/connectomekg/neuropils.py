"""FlyWire neuropil vocabulary: abbreviation, side, full name."""

from __future__ import annotations

#: Full names for the FlyWire neuropil abbreviations (side suffix stripped).
NEUROPIL_NAMES: dict[str, str] = {
    "AL": "antennal lobe",
    "AME": "accessory medulla",
    "AMMC": "antennal mechanosensory and motor center",
    "AOTU": "anterior optic tubercle",
    "ATL": "antler",
    "AVLP": "anterior ventrolateral protocerebrum",
    "BU": "bulb",
    "CAN": "cantle",
    "CRE": "crepine",
    "EB": "ellipsoid body",
    "EPA": "epaulette",
    "FB": "fan-shaped body",
    "FLA": "flange",
    "GA": "gall",
    "GNG": "gnathal ganglia (subesophageal zone)",
    "GOR": "gorget",
    "IB": "inferior bridge",
    "ICL": "inferior clamp",
    "IPS": "inferior posterior slope",
    "LA": "lamina",
    "LAL": "lateral accessory lobe",
    "LH": "lateral horn",
    "LO": "lobula",
    "LOP": "lobula plate",
    "MB_CA": "mushroom body calyx",
    "MB_ML": "mushroom body medial lobe",
    "MB_PED": "mushroom body pedunculus",
    "MB_VL": "mushroom body vertical lobe",
    "ME": "medulla",
    "NO": "noduli",
    "OCG": "ocellar ganglion",
    "PB": "protocerebral bridge",
    "PLP": "posterior lateral protocerebrum",
    "PRW": "prow",
    "PVLP": "posterior ventrolateral protocerebrum",
    "SAD": "saddle",
    "SCL": "superior clamp",
    "SIP": "superior intermediate protocerebrum",
    "SLP": "superior lateral protocerebrum",
    "SMP": "superior medial protocerebrum",
    "SPS": "superior posterior slope",
    "VES": "vest",
    "WED": "wedge",
}

#: Brain regions that group the neuropils, after the supercategories of the
#: systematic nomenclature FlyWire's neuropils follow (Ito et al. 2014,
#: *Neuron* 81, 755-765). ``OCG`` and ``UNASGD`` are outside that hierarchy
#: and get regions of their own.
REGION_NAMES: dict[str, str] = {
    "OL": "optic lobe",
    "MB": "mushroom body",
    "CX": "central complex",
    "LX": "lateral complex",
    "VLNP": "ventrolateral neuropils",
    "LH": "lateral horn",
    "SNP": "superior neuropils",
    "INP": "inferior neuropils",
    "VMNP": "ventromedial neuropils",
    "AL": "antennal lobe",
    "PENP": "periesophageal neuropils",
    "GNG": "gnathal ganglia",
    "OCG": "ocellar ganglion",
    "UNASGD": "unassigned",
}

#: Region for each neuropil base (side suffix stripped).
NEUROPIL_REGION: dict[str, str] = {
    **dict.fromkeys(("LA", "ME", "AME", "LO", "LOP"), "OL"),
    **dict.fromkeys(("MB_CA", "MB_PED", "MB_VL", "MB_ML"), "MB"),
    **dict.fromkeys(("FB", "EB", "PB", "NO"), "CX"),
    **dict.fromkeys(("BU", "LAL", "GA"), "LX"),
    **dict.fromkeys(("AOTU", "AVLP", "PVLP", "PLP", "WED"), "VLNP"),
    "LH": "LH",
    **dict.fromkeys(("SLP", "SIP", "SMP"), "SNP"),
    **dict.fromkeys(("CRE", "SCL", "ICL", "IB", "ATL"), "INP"),
    **dict.fromkeys(("VES", "EPA", "GOR", "SPS", "IPS"), "VMNP"),
    "AL": "AL",
    **dict.fromkeys(("SAD", "AMMC", "FLA", "CAN", "PRW"), "PENP"),
    "GNG": "GNG",
    "OCG": "OCG",
    "UNASGD": "UNASGD",
}

#: Midline neuropils that carry no side suffix in FlyWire.
UNPAIRED = frozenset({"EB", "FB", "PB", "NO", "GNG", "PRW", "SAD", "OCG"})


def split_neuropil(abbrev: str) -> tuple[str, str]:
    """Split ``AL_R`` into ``("AL", "R")``; unpaired names get side ``"M"``.

    :param abbrev: FlyWire neuropil abbreviation, with or without side suffix.
    :return: ``(base, side)`` where side is ``L``, ``R``, or ``M``.
    """
    if abbrev.endswith(("_L", "_R")):
        return abbrev[:-2], abbrev[-1]
    return abbrev, "M"


def neuropil_region(abbrev: str) -> str | None:
    """The brain region a neuropil belongs to.

    :param abbrev: FlyWire abbreviation, with or without side suffix, such as
        ``LO_R`` or ``FB``.
    :return: A key of :data:`REGION_NAMES`, or ``None`` for an unknown base.
    """
    base, _ = split_neuropil(abbrev)
    return NEUROPIL_REGION.get(base)


def neuropil_full_name(abbrev: str) -> str:
    """Human name for a neuropil abbreviation, side included.

    :param abbrev: FlyWire abbreviation such as ``LH_L``.
    :return: For example ``"lateral horn (left)"``.
    """
    base, side = split_neuropil(abbrev)
    name = NEUROPIL_NAMES.get(base, base)
    if side == "M":
        return name
    return f"{name} ({'left' if side == 'L' else 'right'})"
