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
