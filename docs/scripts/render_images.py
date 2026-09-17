"""Regenerate the images in docs/images/ from a built FAFB v783 graph.

Run from the repository root, with the viz3d extra installed and the skeleton
download in fafb_v783/:

    poetry run python docs/scripts/render_images.py

Every image goes through the same steps as ``connkg quilt --still``:
``build_brain_scene``, ``aim_camera``, optionally ``add_floor``, then a
one-view ``render_quilt``. The flow images also carry neuropil name labels,
which ``connkg quilt`` does not draw: neuropil colours repeat (a 15-colour
palette over more neuropil types), so the docs key relies on the names.
Images are written 1600 x 900 and quantized to 256 colours to stay under the
repository's 1 MB file limit.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pyvista as pv
from PIL import Image
from quiltwright import QUILT_PRESETS, render_quilt

from connectomekg import ConnectomeKG
from connectomekg.scene import (
    FLOOR_ELEVATION,
    add_floor,
    aim_camera,
    build_brain_scene,
    neuropil_flow,
    world_frame,
)

OUT = Path("docs/images")
SPEC = QUILT_PRESETS["16-landscape"].still(height=900)  # 1600 x 900
FOV = 14.0

#: (file stem, build_brain_scene options, floor, label neuropils)
IMAGES = [
    ("circuit_dnp01", {"specs": ["DNp01"], "data_dir": "fafb_v783"}, False, False),
    ("flow_all", {"view": "flow", "top": 100}, False, True),
    ("flow_lc4", {"view": "flow", "specs": ["LC4"]}, False, True),
    (
        "floor_lplc2_dnp01",
        {"specs": ["LPLC2", "DNp01"], "data_dir": "fafb_v783", "tubes": True},
        True,
        False,
    ),
]


def label_active_neuropils(plotter: pv.Plotter, kg: ConnectomeKG, options: dict) -> None:
    """Label every neuropil that has a drawn flow tube with its abbreviation."""
    neuron_ids = None
    if options.get("specs"):
        neuron_ids = {n for spec in options["specs"] for n in kg.neurons_of(spec)}
    flow = neuropil_flow(kg.store, neuron_ids)
    index = {name: i for i, name in enumerate(flow.names)}
    drawn = flow.pairs[: options.get("top", 100)]
    active = sorted({name for a, b, _ in drawn for name in (a, b)})
    frame = world_frame(kg.store)
    points = frame.to_world(np.asarray([flow.centroids_nm[index[n]] for n in active]))
    plotter.add_point_labels(
        points,
        active,
        font_size=11,
        text_color="white",
        shape_color="#2B2D31",
        shape_opacity=0.6,
        show_points=False,
        always_visible=True,
        name="neuropil-labels",
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    kg = ConnectomeKG(".")
    try:
        for stem, options, floor, labels in IMAGES:
            plotter = pv.Plotter(off_screen=True)
            info = build_brain_scene(plotter, kg, **options)
            aim_camera(
                plotter,
                info.points,
                fov=FOV,
                elevation=FLOOR_ELEVATION if floor else 0.0,
                spec=SPEC,
            )
            if floor:
                add_floor(plotter)
            if labels:
                label_active_neuropils(plotter, kg, options)
            image = render_quilt(plotter, SPEC, fov=None)
            plotter.close()
            path = OUT / f"{stem}.png"
            Image.fromarray(image).quantize(
                colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE
            ).save(path, optimize=True)
            print(f"{path}  {path.stat().st_size // 1024} KB  {info.title}")
    finally:
        kg.close()


if __name__ == "__main__":
    main()
