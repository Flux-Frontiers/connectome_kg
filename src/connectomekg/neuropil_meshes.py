"""Neuropil surface meshes: fetched once from FlyWire's public bucket, cached per dataset.

FAFB v783 synapses are assigned to neuropils by volumes mapped from the JFRC2
template brain into FlyWire space (Ito et al. 2014, *Neuron* 81, 755-765). The
surfaces of those volumes are published as legacy Neuroglancer precomputed
meshes at ``gs://flywire_neuropil_meshes/neuropils/neuropil_mesh_v141_v6``:
one manifest and one binary fragment per integer id, with no names.

:data:`FAFB_783_MESH_NAMES` names them. It was derived by matching every v6
fragment, vertex set for vertex set, against the named PLY copies fafbseg
packages from the same source (``fafbseg/data/JFRC2NP.surf.fw.zip``, whose
README records the v6 origin): 78 of 78 exact, 78 distinct names. The one
v783 neuropil without a mesh is ``UNASGD``, the synapses no volume claimed.
Do not substitute ``fafbseg/data/volume_name_dict.json``: it numbers the
synapse-assignment volume, not these meshes, and matches none of them.

Vertices are nanometres in FlyWire (FAFB14.1) space, the same frame as the
graph's neuron coordinates, so a mesh goes through
:meth:`connectomekg.scene.WorldFrame.to_world` unchanged.
"""

from __future__ import annotations

import io
import struct
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Final

import numpy as np

__all__ = [
    "FAFB_783_MESH_NAMES",
    "MESH_CACHE",
    "decode_fragment",
    "fetch_neuropil_meshes",
    "has_mesh_source",
    "load_neuropil_meshes",
    "neuropil_mesh_path",
]

#: Cache file name inside a dataset's ``.connectomekg/`` directory.
MESH_CACHE: Final = "neuropil_meshes.npz"

_FAFB_783_MESH_URL: Final = (
    "https://storage.googleapis.com/flywire_neuropil_meshes/neuropils/neuropil_mesh_v141_v6/mesh"
)

#: v6 mesh id to FlyWire neuropil name; see the module docstring for how it was derived.
FAFB_783_MESH_NAMES: Final[dict[int, str]] = {
    0: "SCL_R", 1: "SMP_R", 2: "ME_R", 3: "CAN_L", 4: "MB_VL_L", 5: "FLA_R", 6: "LOP_L",
    7: "IPS_L", 8: "EPA_L", 9: "PLP_R", 10: "MB_ML_L", 11: "BU_R", 12: "GOR_L", 13: "SPS_L",
    14: "LO_R", 15: "SCL_L", 16: "GA_R", 17: "IB_R", 18: "ATL_L", 19: "CRE_R", 20: "LH_L",
    21: "MB_CA_R", 22: "AOTU_L", 23: "ATL_R", 24: "AOTU_R", 25: "LAL_R", 26: "GNG", 27: "AL_R",
    28: "MB_PED_R", 29: "AME_R", 30: "CRE_L", 31: "ICL_L", 32: "GOR_R", 33: "ICL_R",
    34: "GA_L", 35: "EB", 36: "LOP_R", 37: "PVLP_R", 38: "IPS_R", 39: "PVLP_L", 40: "VES_R",
    41: "MB_ML_R", 42: "SMP_L", 43: "ME_L", 44: "VES_L", 45: "AMMC_L", 46: "LAL_L",
    47: "SLP_R", 48: "MB_PED_L", 49: "AVLP_R", 50: "WED_L", 51: "LO_L", 52: "EPA_R", 53: "PRW",
    54: "LH_R", 55: "MB_VL_R", 56: "AME_L", 57: "AL_L", 58: "NO", 59: "PLP_L", 60: "WED_R",
    61: "CAN_R", 62: "SLP_L", 63: "SIP_R", 64: "SPS_R", 65: "FB", 66: "MB_CA_L", 67: "IB_L",
    68: "PB", 69: "AVLP_L", 70: "SAD", 71: "AMMC_R", 72: "SIP_L", 73: "BU_L", 74: "FLA_L",
    75: "LA_R", 76: "LA_L", 77: "OCG",
}  # fmt: skip

#: Mesh source per dataset id: (fragment base URL, id -> name).
_SOURCES: Final[dict[str, tuple[str, dict[int, str]]]] = {
    "fafb783": (_FAFB_783_MESH_URL, FAFB_783_MESH_NAMES),
}

#: A mesh as ``(vertices_nm (n, 3) float32, faces (m, 3) uint32)``.
Mesh = tuple[np.ndarray, np.ndarray]


def has_mesh_source(dataset_id: str) -> bool:
    """Whether a dataset has published neuropil meshes to fetch.

    :param dataset_id: Dataset id, e.g. ``"fafb783"``.
    :return: ``True`` if :func:`fetch_neuropil_meshes` accepts it.
    """
    return dataset_id in _SOURCES


def neuropil_mesh_path(db_path: str | Path) -> Path:
    """Where a dataset's neuropil mesh cache lives: beside its graph.

    :param db_path: The dataset's ``graph.sqlite``.
    :return: ``<dataset dir>/.connectomekg/neuropil_meshes.npz``, which may not exist.
    """
    return Path(db_path).parent / MESH_CACHE


def decode_fragment(data: bytes) -> Mesh:
    """Decode one legacy Neuroglancer precomputed mesh fragment.

    The format is a little-endian ``uint32`` vertex count, that many ``float32``
    ``x y z`` triples, then ``uint32`` vertex-index triangles to the end.

    :param data: The fragment's bytes.
    :return: ``(vertices, faces)``.
    :raises ValueError: If the bytes are not a well-formed fragment.
    """
    if len(data) < 4:
        raise ValueError("mesh fragment is shorter than its header")
    (n,) = struct.unpack_from("<I", data)
    rest = len(data) - 4 - 12 * n
    if rest < 0 or rest % 12:
        raise ValueError(f"mesh fragment of {len(data)} bytes does not hold {n} vertices")
    vertices = np.frombuffer(data, "<f4", 3 * n, 4).reshape(n, 3)
    faces = np.frombuffer(data, "<u4", offset=4 + 12 * n).reshape(-1, 3)
    if faces.size and int(faces.max()) >= n:
        raise ValueError("mesh fragment has a face index beyond its vertices")
    return vertices, faces


def _http_get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310 - fixed https URL
        return response.read()


def fetch_neuropil_meshes(
    dataset_id: str,
    dest: str | Path,
    *,
    fetch: Callable[[str], bytes] = _http_get,
    progress: Callable[[str], None] | None = None,
) -> Path:
    """Download a dataset's neuropil meshes and cache them as one ``.npz``.

    :param dataset_id: Dataset id, e.g. ``"fafb783"``.
    :param dest: The cache file to write, usually
        ``<dataset dir>/.connectomekg/neuropil_meshes.npz``.
    :param fetch: Returns the bytes at a URL; the default is a plain HTTPS GET.
    :param progress: Called with a short message every 20 meshes.
    :return: ``dest``.
    :raises ValueError: If the dataset has no mesh source or a fragment is malformed.
    """
    if dataset_id not in _SOURCES:
        known = ", ".join(sorted(_SOURCES))
        raise ValueError(f"no neuropil meshes published for dataset {dataset_id!r}; have {known}")
    base, names = _SOURCES[dataset_id]
    arrays: dict[str, np.ndarray] = {}
    for i, (mesh_id, name) in enumerate(sorted(names.items()), 1):
        vertices, faces = decode_fragment(fetch(f"{base}/{mesh_id}:0:0"))
        arrays[f"{name}/vertices"] = vertices
        arrays[f"{name}/faces"] = faces
        if progress is not None and (i % 20 == 0 or i == len(names)):
            progress(f"fetched {i} of {len(names)} neuropil meshes")
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Written whole, then renamed, so an interrupted fetch leaves no partial cache.
    buffer = io.BytesIO()
    np.savez_compressed(buffer, **arrays)  # ty: ignore[invalid-argument-type]
    partial = dest.with_suffix(".part")
    partial.write_bytes(buffer.getvalue())
    partial.replace(dest)
    return dest


def load_neuropil_meshes(path: str | Path) -> dict[str, Mesh]:
    """Read a cache written by :func:`fetch_neuropil_meshes`.

    :param path: The ``.npz`` cache.
    :return: ``{neuropil name: (vertices_nm, faces)}``.
    """
    with np.load(path) as npz:
        names = sorted({key.rsplit("/", 1)[0] for key in npz.files})
        return {n: (npz[f"{n}/vertices"], npz[f"{n}/faces"]) for n in names}
