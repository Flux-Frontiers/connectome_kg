"""Neuroglancer links: a spec's neurons as meshes, in a browser, with no login.

A link is a Neuroglancer state serialised into the URL fragment
(``<viewer>/#!<quoted JSON>``), the same form Codex's 3-D button and fafbseg's
``encode_url`` produce. It selects root ids on the dataset's public flat
segmentation, so the viewer fetches FlyWire's own meshes and nothing is
rendered here.

Only datasets with a public, anonymous segmentation get a link. For FAFB v783
that is ``gs://flywire_v141_m783``, the flat v783 segmentation fafbseg calls
``flat_783``; the EM image and the brain outline are the layers of the
community's public v783 scene (``tinyurl.com/flywire783``). All three are
Google Cloud buckets readable without credentials.
"""

from __future__ import annotations

import json
from typing import Any, Final
from urllib.parse import quote

__all__ = ["NEUROGLANCER_VIEWER", "SPEC_COLORS", "has_public_source", "neuroglancer_url"]

#: The public Neuroglancer build the flyconnectome links open in.
NEUROGLANCER_VIEWER: Final = "https://neuroglancer-demo.appspot.com"

#: Color per spec, in the order given: Okabe-Ito without black, which
#: vanishes on Neuroglancer's black background.
SPEC_COLORS: Final = (
    "#E69F00",
    "#56B4E9",
    "#009E73",
    "#F0E442",
    "#0072B2",
    "#D55E00",
    "#CC79A7",
)

_FAFB_783: Final[dict[str, Any]] = {
    "segmentation": "precomputed://gs://flywire_v141_m783",
    "image": "precomputed://gs://flywire_em/aligned/v1",
    "brain": "precomputed://gs://flywire_neuropil_meshes/whole_neuropil/brain_mesh_v141.surf",
    # Voxel size in nanometres, and the brain's center in voxels: the mean
    # marked point of all 139,255 v783 neurons.
    "voxel_nm": (4, 4, 40),
    "center": (130267, 64604, 4106),
}

#: Public sources per dataset id.
_SOURCES: Final[dict[str, dict[str, Any]]] = {"fafb783": _FAFB_783}


def has_public_source(dataset_id: str) -> bool:
    """Whether a dataset has a public segmentation to link to.

    :param dataset_id: Dataset id, e.g. ``"fafb783"``.
    :return: ``True`` if :func:`neuroglancer_url` accepts it.
    """
    return dataset_id in _SOURCES


def _meshes_only(url: str) -> dict[str, Any]:
    """A segmentation source with only its meshes, without the volume's bounds box."""
    return {
        "url": url,
        "subsources": {"default": True, "mesh": True},
        "enableDefaultSubsources": False,
    }


def neuroglancer_url(dataset_id: str, groups: list[list[int]]) -> str:
    """A Neuroglancer URL showing groups of neurons, one color per group.

    :param dataset_id: Dataset id, e.g. ``"fafb783"``.
    :param groups: Root ids per group; group ``i`` is drawn in
        ``SPEC_COLORS[i]``. A root id in two groups takes the later color.
    :return: The URL.
    :raises ValueError: If the dataset has no public source, or there are more
        groups than colors.
    """
    src = _SOURCES.get(dataset_id)
    if src is None:
        known = ", ".join(sorted(_SOURCES))
        raise ValueError(f"no public Neuroglancer source for dataset {dataset_id!r}; have {known}")
    if len(groups) > len(SPEC_COLORS):
        raise ValueError(f"at most {len(SPEC_COLORS)} specs per link, got {len(groups)}")
    colors = {str(rid): SPEC_COLORS[i] for i, ids in enumerate(groups) for rid in ids}
    x, y, z = (v * 1e-9 for v in src["voxel_nm"])
    state = {
        "dimensions": {"x": [x, "m"], "y": [y, "m"], "z": [z, "m"]},
        "position": list(src["center"]),
        "projectionScale": 1e5,
        "layers": [
            {"type": "image", "source": src["image"], "name": "em", "visible": False},
            {
                "type": "segmentation",
                "source": _meshes_only(src["segmentation"]),
                "segments": sorted(colors, key=int),
                "segmentColors": colors,
                "name": "neurons",
            },
            {
                "type": "segmentation",
                "source": _meshes_only(src["brain"]),
                "segments": ["1"],
                "segmentColors": {"1": "#808080"},
                "objectAlpha": 0.1,
                "ignoreSegmentInteractions": True,
                "name": "brain",
            },
        ],
        "showAxisLines": False,
        "layout": "3d",
    }
    return f"{NEUROGLANCER_VIEWER}/#!{quote(json.dumps(state, separators=(',', ':')))}"
