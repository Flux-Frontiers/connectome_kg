"""Neuropil vocabulary across the Codex releases: abbreviation, side, full name.

FAFB's brain neuropils follow Ito et al. 2014. BANC and MCNS add the ventral
nerve cord (VNC), its nerves and the cervical connective, named after the VNC
nomenclature of Court et al. 2020 (*Neuron* 107, 1071-1079). The two nerve-cord
releases partition the VNC differently -- MCNS by leg neuropil, tectulum and
nerve, BANC mostly by thoracic neuromere under a ``VNC_`` prefix -- so both
sets of names are here.
"""

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
    # Brain, MCNS only
    "AB": "asymmetric body",
    # Ventral nerve cord, MCNS spelling
    "LegNp_T1": "prothoracic leg neuropil",
    "LegNp_T2": "mesothoracic leg neuropil",
    "LegNp_T3": "metathoracic leg neuropil",
    "mVAC_T1": "prothoracic medial ventral association center",
    "mVAC_T2": "mesothoracic medial ventral association center",
    "mVAC_T3": "metathoracic medial ventral association center",
    "Ov": "ovoid",
    "IntTct": "intermediate tectulum",
    "LTct": "lower tectulum",
    "NTct_UTct_T1": "neck tectulum (upper tectulum, T1)",
    "WTct_UTct_T2": "wing tectulum (upper tectulum, T2)",
    "HTct_UTct_T3": "haltere tectulum (upper tectulum, T3)",
    "ANm": "abdominal neuromeres",
    # Ventral nerve cord, BANC spelling
    "VNC_T1_ProNm": "prothoracic neuromere",
    "VNC_T2_MesoNm": "mesothoracic neuromere",
    "VNC_T3_MetaNm": "metathoracic neuromere",
    "VNC_T2_mVAC": "mesothoracic medial ventral association center",
    "VNC_AMNp": "accessory mesothoracic neuropil",
    "VNC_NTct": "neck tectulum",
    "VNC_WTct": "wing tectulum",
    "VNC_HTct": "haltere tectulum",
    "Tct": "tectulum",
    "ABDNM": "abdominal neuromeres",
    # Nerves
    "CvN": "cervical nerve",
    "ProAN": "prothoracic accessory nerve",
    "ProLN": "prothoracic leg nerve",
    "DProN": "dorsal prothoracic nerve",
    "VProN": "ventral prothoracic nerve",
    "PrN": "prosternal nerve",
    "ADMN": "anterior dorsal mesothoracic nerve",
    "PDMN": "posterior dorsal mesothoracic nerve",
    "MesoAN": "mesothoracic accessory nerve",
    "MesoLN": "mesothoracic leg nerve",
    "DMetaN": "dorsal metathoracic nerve",
    "MetaLN": "metathoracic leg nerve",
    "AbN1": "first abdominal nerve",
    "AbN2": "second abdominal nerve",
    "AbN3": "third abdominal nerve",
    "AbN4": "fourth abdominal nerve",
    "AbNT": "abdominal nerve trunk",
    "cervical_connective": "cervical connective",
    # Synapses no volume claimed, by part of the nervous system
    "CB_UNASGD": "unassigned, central brain",
    "OL_UNASGD": "unassigned, optic lobe",
    "CV_UNASGD": "unassigned, cervical connective",
    "VNC_UNASGD": "unassigned, ventral nerve cord",
}

#: Brain regions that group the neuropils, after the supercategories of the
#: systematic nomenclature FlyWire's neuropils follow (Ito et al. 2014,
#: *Neuron* 81, 755-765). ``OCG`` and ``UNASGD`` are outside that hierarchy
#: and get regions of their own, as do the nerve-cord releases' ventral nerve
#: cord, nerves and cervical connective.
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
    "VNC": "ventral nerve cord",
    "NERVE": "nerves",
    "CV": "cervical connective",
}

#: Region for each neuropil base (side suffix stripped).
NEUROPIL_REGION: dict[str, str] = {
    **dict.fromkeys(("LA", "ME", "AME", "LO", "LOP"), "OL"),
    **dict.fromkeys(("MB_CA", "MB_PED", "MB_VL", "MB_ML"), "MB"),
    **dict.fromkeys(("FB", "EB", "PB", "NO", "AB"), "CX"),
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
    **dict.fromkeys(("CB_UNASGD", "OL_UNASGD", "CV_UNASGD", "VNC_UNASGD"), "UNASGD"),
    **dict.fromkeys(
        (
            "LegNp_T1",
            "LegNp_T2",
            "LegNp_T3",
            "mVAC_T1",
            "mVAC_T2",
            "mVAC_T3",
            "Ov",
            "IntTct",
            "LTct",
            "NTct_UTct_T1",
            "WTct_UTct_T2",
            "HTct_UTct_T3",
            "ANm",
            "VNC_T1_ProNm",
            "VNC_T2_MesoNm",
            "VNC_T3_MetaNm",
            "VNC_T2_mVAC",
            "VNC_AMNp",
            "VNC_NTct",
            "VNC_WTct",
            "VNC_HTct",
            "Tct",
            "ABDNM",
        ),
        "VNC",
    ),
    **dict.fromkeys(
        (
            "CvN",
            "ProAN",
            "ProLN",
            "DProN",
            "VProN",
            "PrN",
            "ADMN",
            "PDMN",
            "MesoAN",
            "MesoLN",
            "DMetaN",
            "MetaLN",
            "AbN1",
            "AbN2",
            "AbN3",
            "AbN4",
            "AbNT",
        ),
        "NERVE",
    ),
    "cervical_connective": "CV",
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
