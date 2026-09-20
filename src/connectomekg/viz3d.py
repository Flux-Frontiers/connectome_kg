"""connectomekg/viz3d.py

Interactive 3-D viewer for a connectome scene: a ``QMainWindow`` wrapping a
``pyvistaqt.QtInteractor``, showing what
:func:`connectomekg.scene.build_brain_scene` composes -- the whole-brain
context cloud plus a spec's circuit skeletons, or the neuropil flow.

Small by design, mirroring ``genealogy_kg``'s own ``viz3d.py``.
``QtInteractor`` supplies orbit/zoom/pan for free via VTK's default
interactor style, and Cast to Looking Glass is wired straight to
``kg_utils.viz3d.qt.cast_scene_to_looking_glass``, which does the entire cast
on the GUI thread.

Picking is bound to **P**, not to a left click. A left click is where VTK
begins a rotation, so picking on it would re-answer the question on every
orbit; ``pyvista``'s own default is the key, and the status bar says so. The
click resolves to a neuron through :class:`connectomekg.picking.PickTargets`
rather than through the actor that was hit, because a whole cell type shares
one actor -- see that module for why.

Author: Eric G. Suchanek, PhD
License: Elastic 2.0
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from kg_utils.viz3d.qt import DEFAULT_QUILT_PRESET, cast_scene_to_looking_glass
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAction,
    QDockWidget,
    QMainWindow,
    QMessageBox,
    QTextEdit,
    QToolBar,
)
from pyvistaqt import QtInteractor

from connectomekg import scene as render3d
from connectomekg.cli.cmd_viz3d import QUILTS_DIR, scene_stem
from connectomekg.cli.options import open_kg
from connectomekg.module import ConnectomeKG
from connectomekg.picking import pick_summary

#: How far from a neuron's own geometry a pick may land and still count, in
#: world units (1 unit is 100,000 nm, so this is 25 microns). A pick that hits
#: a neuropil shell or the context cloud rather than a circuit neuron lands
#: much further away than this, and is better reported as a miss than as
#: whichever neuron happened to be nearest.
PICK_RADIUS = 0.25

#: Default window size, in pixels. Also the render window's size, which has to
#: be set before the camera is aimed -- see :class:`BrainSceneWindow`.
DEFAULT_WINDOW_SIZE = (1400, 900)


class BrainSceneWindow(QMainWindow):
    """Main window: whole-brain context plus a circuit or flow, orbit/zoom/pan, one Cast action.

    :param kg: An open ``ConnectomeKG``.
    :param specs: Specs resolved into the circuit view (view B), or restricting
        the flow view (view C).
    :param view: ``"circuit"`` or ``"flow"``.
    :param data_dir: Skeleton download root, or ``None`` for marked-point
        fallback spheres on every circuit neuron.
    :param color_by: Context cloud colouring, ``"super_class"`` or ``"sign"``.
    :param skeleton_step: Skeleton simplification stride.
    :param tubes: Draw circuit skeletons as tubes instead of lines.
    :param top: Flow arcs drawn, strongest first.
    :param neuropils: Draw the neuropil surface meshes, when cached.
    :param cloud: Draw the whole-brain context cloud; ``None`` draws it
        only when no neuropil meshes are.
    :param floor: Stand the scene over a floor lit from above, with shadows.
    :param elevation: Degrees to tilt the camera up from the front view.
    :param preset: Quilt preset name for the Cast action.
    :param width: Window width in pixels; also the render window's width,
        which the camera framing divides by and so cannot be left at zero.
    :param height: Window height in pixels, likewise.
    """

    def __init__(
        self,
        kg: ConnectomeKG,
        specs: Sequence[str],
        *,
        view: str = "circuit",
        data_dir: str | Path | None = None,
        color_by: str = "super_class",
        skeleton_step: int = 4,
        tubes: bool = False,
        top: int = 100,
        neuropils: bool = True,
        cloud: bool | None = None,
        floor: bool = False,
        elevation: float = 0.0,
        preset: str = DEFAULT_QUILT_PRESET,
        width: int = DEFAULT_WINDOW_SIZE[0],
        height: int = DEFAULT_WINDOW_SIZE[1],
    ) -> None:
        super().__init__()
        self._kg = kg
        self._specs = specs
        self._view = view
        self._data_dir = data_dir
        self._color_by = color_by
        self._skeleton_step = skeleton_step
        self._tubes = tubes
        self._top = top
        self._neuropils = neuropils
        self._cloud = cloud
        self._floor = floor
        self._preset = preset

        self.plotter = QtInteractor(self)
        self.setCentralWidget(self.plotter)
        # Size the render window before composing, because aiming the camera
        # reads it: quiltwright's frame_and_focus divides by the window height
        # to get the horizontal half-angle. A QtInteractor reports (0, 0) until
        # it has been shown, and the caller cannot show it first -- the scene
        # has to exist before there is anything to frame. Setting it here is
        # what keeps that division finite.
        self.resize(width, height)
        self.plotter.window_size = [width, height]

        info = render3d.build_brain_scene(
            self.plotter,
            kg,
            specs=specs,
            view=view,
            data_dir=data_dir,
            color_by=color_by,
            skeleton_step=skeleton_step,
            tubes=tubes,
            top=top,
            neuropils=neuropils,
            cloud=cloud,
        )
        self.setWindowTitle(f"ConnectomeKG viz3d -- {info.title}")

        render3d.aim_camera(self.plotter, info.points, elevation=elevation)
        if floor:
            render3d.add_floor(self.plotter)

        toolbar = QToolBar("Actions", self)
        self.addToolBar(toolbar)
        cast_action = QAction("Cast to Looking Glass", self)
        cast_action.triggered.connect(self._cast)
        toolbar.addAction(cast_action)

        self._picks = info.picks
        self._info_panel = QTextEdit(self)
        self._info_panel.setReadOnly(True)
        self._info_panel.setLineWrapMode(QTextEdit.WidgetWidth)
        dock = QDockWidget("Neuron", self)
        dock.setWidget(self._info_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        self._dock = dock

        if len(self._picks):
            self._info_panel.setPlainText(
                f"{len(self._picks.neuron_ids)} neurons drawn.\n\n"
                "Point at one and press P to identify it."
            )
            # show_message=False: the hint belongs in the status bar, which
            # does not sit on top of the scene or end up in a cast quilt.
            self.plotter.enable_point_picking(
                callback=self._on_pick, show_message=False, show_point=False
            )
            status = self.statusBar()
            if status is not None:
                status.showMessage("Point at a neuron and press P to identify it.")
        else:
            self._info_panel.setPlainText(
                "No circuit in this view, so there is nothing to pick.\n\n"
                "The flow view draws neuropils rather than neurons."
            )
            dock.hide()

    def _on_pick(self, point, *_: object) -> None:
        """Resolve a picked position to a neuron and describe it in the panel.

        :param point: The picked position, in world coordinates.
        """
        node_id = self._picks.nearest(point, within=PICK_RADIUS)
        if node_id is None:
            self._info_panel.setPlainText(
                "No neuron there.\n\nThe pick landed more than "
                f"{PICK_RADIUS * render3d.NM_PER_WORLD_UNIT / 1000:.0f} microns from any "
                "drawn neuron -- a neuropil surface or the context cloud, most likely."
            )
            return
        try:
            self._info_panel.setPlainText(pick_summary(self._kg, node_id))
        except Exception as exc:  # noqa: BLE001 - a bad pick must not kill the viewer
            self._info_panel.setPlainText(f"{node_id}\n\nCould not describe it: {exc}")

    def _cast(self) -> None:
        """Render the current view off-screen and push it to Looking Glass Bridge."""
        from quiltwright import QUILT_PRESETS  # noqa: PLC0415 - viz3d-only import

        spec = QUILT_PRESETS[self._preset]
        kg, specs, view = self._kg, self._specs, self._view
        data_dir, color_by = self._data_dir, self._color_by
        skeleton_step, tubes, top = self._skeleton_step, self._tubes, self._top
        floor, neuropils, cloud = self._floor, self._neuropils, self._cloud

        def build(plotter) -> None:
            render3d.build_brain_scene(
                plotter,
                kg,
                specs=specs,
                view=view,
                data_dir=data_dir,
                color_by=color_by,
                skeleton_step=skeleton_step,
                tubes=tubes,
                top=top,
                neuropils=neuropils,
                cloud=cloud,
            )
            if floor:
                render3d.add_floor(plotter)

        out_stem = QUILTS_DIR / f"{scene_stem(view, tuple(specs))}_cast"
        result = cast_scene_to_looking_glass(build, self.plotter.camera_position, out_stem, spec)
        box = QMessageBox.information if result.path else QMessageBox.warning
        box(self, "Cast to Looking Glass", result.message)


def launch(
    root: str | Path,
    specs: Sequence[str],
    *,
    view: str = "circuit",
    data_dir: str | Path | None = None,
    color_by: str = "super_class",
    skeleton_step: int = 4,
    tubes: bool = False,
    top: int = 100,
    neuropils: bool = True,
    cloud: bool | None = None,
    floor: bool = False,
    elevation: float = 0.0,
    preset: str = DEFAULT_QUILT_PRESET,
    dataset: str | None = None,
    width: int = DEFAULT_WINDOW_SIZE[0],
    height: int = DEFAULT_WINDOW_SIZE[1],
) -> None:
    """Open the interactive viewer for SPEC(s)' circuit or the neuropil flow.

    :param root: Directory holding ``connectomes/``.
    :param specs: Specs resolved into the circuit view, or restricting the flow view.
    :param view: ``"circuit"`` or ``"flow"``.
    :param data_dir: Skeleton download root, or ``None`` for marked-point
        fallback spheres.
    :param color_by: Context cloud colouring, ``"super_class"`` or ``"sign"``.
    :param skeleton_step: Skeleton simplification stride.
    :param tubes: Draw circuit skeletons as tubes instead of lines.
    :param top: Flow arcs drawn, strongest first.
    :param neuropils: Draw the neuropil surface meshes, when cached.
    :param cloud: Draw the whole-brain context cloud; ``None`` draws it
        only when no neuropil meshes are.
    :param floor: Stand the scene over a floor lit from above, with shadows.
    :param elevation: Degrees to tilt the camera up from the front view.
    :param preset: Quilt preset name for the Cast action.
    :param dataset: Dataset id, or ``None`` for the only built dataset.
    :param width: Window width in pixels.
    :param height: Window height in pixels.
    :raises ValueError: Propagated from ``ConnectomeKG`` / ``build_brain_scene``,
        e.g. a spec over ``MAX_SCENE_NEURONS``.
    """
    from PyQt5.QtWidgets import QApplication  # noqa: PLC0415 - viz3d-only import

    with open_kg(str(root), dataset=dataset) as kg:
        app = QApplication.instance() or QApplication([])
        window = BrainSceneWindow(
            kg,
            specs,
            view=view,
            data_dir=data_dir,
            color_by=color_by,
            skeleton_step=skeleton_step,
            tubes=tubes,
            top=top,
            neuropils=neuropils,
            cloud=cloud,
            floor=floor,
            elevation=elevation,
            preset=preset,
            width=width,
            height=height,
        )
        window.show()
        app.exec_()


__all__ = ["BrainSceneWindow", "launch"]
