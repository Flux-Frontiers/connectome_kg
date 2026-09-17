"""connectomekg/viz3d.py

Interactive 3-D viewer for a connectome scene: a ``QMainWindow`` wrapping a
``pyvistaqt.QtInteractor``, showing what
:func:`connectomekg.scene.build_brain_scene` composes -- the whole-brain
context cloud plus a spec's circuit skeletons.

Deliberately small, mirroring ``genealogy_kg``'s own ``viz3d.py`` (~140
lines): no custom picking, no info popups, no filter toggles.
``QtInteractor`` supplies orbit/zoom/pan for free via VTK's default
interactor style. One toolbar action, Cast to Looking Glass, wired straight
to ``kg_utils.viz3d.qt.cast_scene_to_looking_glass``, which does the entire
cast on the GUI thread.

Author: Eric G. Suchanek, PhD
License: Elastic 2.0
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from kg_utils.viz3d import frame_tree
from kg_utils.viz3d.qt import DEFAULT_QUILT_PRESET, cast_scene_to_looking_glass
from PyQt5.QtWidgets import QAction, QMainWindow, QMessageBox, QToolBar
from pyvistaqt import QtInteractor

from connectomekg import scene as render3d
from connectomekg.cli.cmd_viz3d import QUILTS_DIR, sanitize_specs
from connectomekg.cli.options import open_kg
from connectomekg.module import ConnectomeKG


class BrainSceneWindow(QMainWindow):
    """Main window: whole-brain context plus a circuit, orbit/zoom/pan, one Cast action.

    :param kg: An open ``ConnectomeKG``.
    :param specs: Specs resolved into the circuit view (view B).
    :param data_dir: Skeleton download root, or ``None`` for marked-point
        fallback spheres on every circuit neuron.
    :param color_by: Context cloud colouring, ``"super_class"`` or ``"sign"``.
    :param skeleton_step: Skeleton simplification stride.
    :param tubes: Draw circuit skeletons as tubes instead of lines.
    :param preset: Quilt preset name for the Cast action.
    """

    def __init__(
        self,
        kg: ConnectomeKG,
        specs: Sequence[str],
        *,
        data_dir: str | Path | None = None,
        color_by: str = "super_class",
        skeleton_step: int = 4,
        tubes: bool = False,
        preset: str = DEFAULT_QUILT_PRESET,
    ) -> None:
        super().__init__()
        self._kg = kg
        self._specs = specs
        self._data_dir = data_dir
        self._color_by = color_by
        self._skeleton_step = skeleton_step
        self._tubes = tubes
        self._preset = preset

        self.plotter = QtInteractor(self)
        self.setCentralWidget(self.plotter)

        info = render3d.build_brain_scene(
            self.plotter,
            kg,
            specs=specs,
            data_dir=data_dir,
            color_by=color_by,
            skeleton_step=skeleton_step,
            tubes=tubes,
        )
        self.setWindowTitle(f"ConnectomeKG viz3d -- {info.title}")

        frame = frame_tree(info.points)
        self.plotter.camera.position = frame.position
        self.plotter.camera.focal_point = frame.focal_point
        self.plotter.camera.up = frame.up
        self.plotter.reset_camera()

        toolbar = QToolBar("Actions", self)
        self.addToolBar(toolbar)
        cast_action = QAction("Cast to Looking Glass", self)
        cast_action.triggered.connect(self._cast)
        toolbar.addAction(cast_action)

    def _cast(self) -> None:
        """Render the current view off-screen and push it to Looking Glass Bridge."""
        from quiltwright import QUILT_PRESETS  # noqa: PLC0415 - viz3d-only import

        spec = QUILT_PRESETS[self._preset]
        kg, specs = self._kg, self._specs
        data_dir, color_by = self._data_dir, self._color_by
        skeleton_step, tubes = self._skeleton_step, self._tubes

        def build(plotter) -> None:
            render3d.build_brain_scene(
                plotter,
                kg,
                specs=specs,
                data_dir=data_dir,
                color_by=color_by,
                skeleton_step=skeleton_step,
                tubes=tubes,
            )

        out_stem = QUILTS_DIR / f"{sanitize_specs(tuple(specs))}_cast"
        result = cast_scene_to_looking_glass(build, self.plotter.camera_position, out_stem, spec)
        box = QMessageBox.information if result.path else QMessageBox.warning
        box(self, "Cast to Looking Glass", result.message)


def launch(
    root: str | Path,
    specs: Sequence[str],
    *,
    data_dir: str | Path | None = None,
    color_by: str = "super_class",
    skeleton_step: int = 4,
    tubes: bool = False,
    preset: str = DEFAULT_QUILT_PRESET,
    dataset_id: str | None = None,
    width: int = 1400,
    height: int = 900,
) -> None:
    """Open the interactive viewer for SPEC(s)' circuit inside the whole-brain context.

    :param root: Directory that owns ``.connectomekg/``.
    :param specs: Specs resolved into the circuit view.
    :param data_dir: Skeleton download root, or ``None`` for marked-point
        fallback spheres.
    :param color_by: Context cloud colouring, ``"super_class"`` or ``"sign"``.
    :param skeleton_step: Skeleton simplification stride.
    :param tubes: Draw circuit skeletons as tubes instead of lines.
    :param preset: Quilt preset name for the Cast action.
    :param dataset_id: Dataset id; ``"fafb783"`` selects the FAFB v783 record.
    :param width: Window width in pixels.
    :param height: Window height in pixels.
    :raises ValueError: Propagated from ``ConnectomeKG`` / ``build_brain_scene``,
        e.g. a spec over ``MAX_SCENE_NEURONS``.
    """
    from PyQt5.QtWidgets import QApplication  # noqa: PLC0415 - viz3d-only import

    with open_kg(str(root), dataset_id=dataset_id) as kg:
        app = QApplication.instance() or QApplication([])
        window = BrainSceneWindow(
            kg,
            specs,
            data_dir=data_dir,
            color_by=color_by,
            skeleton_step=skeleton_step,
            tubes=tubes,
            preset=preset,
        )
        window.resize(width, height)
        window.show()
        app.exec_()


__all__ = ["BrainSceneWindow", "launch"]
