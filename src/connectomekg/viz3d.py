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

The toolbar's Show box re-resolves specs and redraws in place, so exploring
does not mean restarting. It refuses a spec that matches nothing, or one over
``MAX_SCENE_NEURONS``, and leaves the scene as it was -- including when only
one spec of several is bad, since drawing the rest would look like a scene
that contained them all.

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
    QCheckBox,
    QDockWidget,
    QFrame,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QSpinBox,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)
from pyvistaqt import QtInteractor

from connectomekg import scene as render3d
from connectomekg.answers import ANSWER_SYNTAX, Answer, answer_groups, is_answer, spec_help
from connectomekg.cli.cmd_viz3d import QUILTS_DIR, scene_stem
from connectomekg.cli.options import open_kg
from connectomekg.module import ConnectomeKG
from connectomekg.picking import PickTargets, pick_summary
from connectomekg.validation import MAX_MIN_SYN, MAX_SKELETON_STEP

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
    :param answer: A resolved path or cone to open on, drawn hop-coloured
        instead of by cell type.
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
        skeleton_step: int | None = None,
        tubes: bool = False,
        top: int = 100,
        neuropils: bool = True,
        cloud: bool | None = None,
        floor: bool = False,
        elevation: float = 0.0,
        preset: str = DEFAULT_QUILT_PRESET,
        width: int = DEFAULT_WINDOW_SIZE[0],
        height: int = DEFAULT_WINDOW_SIZE[1],
        answer: Answer | None = None,
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

        self._elevation = elevation
        self._answer: Answer | None = None
        self._picks = PickTargets.empty()

        self._info_panel = QTextEdit(self)
        self._info_panel.setReadOnly(True)
        self._info_panel.setLineWrapMode(QTextEdit.WidgetWidth)
        self._dock = QDockWidget("Neuron", self)
        self._dock.setWidget(self._info_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._dock)
        self._build_controls()

        toolbar = QToolBar("Actions", self)
        self.addToolBar(toolbar)
        cast_action = QAction("Cast to Looking Glass", self)
        cast_action.triggered.connect(self._cast)
        toolbar.addAction(cast_action)
        toolbar.addSeparator()
        toolbar.addWidget(QLabel(" Show: ", self))
        self._filter_box = QLineEdit(self)
        self._filter_box.setPlaceholderText(
            "spec, space-separated -- LC4 DNp01, a root id, or label:giant fib"
        )
        self._filter_box.setText(" ".join(specs))
        self._filter_box.setClearButtonEnabled(True)
        self._filter_box.returnPressed.connect(self._apply_filter)
        self._filter_box.setMinimumWidth(360)
        toolbar.addWidget(self._filter_box)

        # Enabled once, not per scene: the callback reads self._picks when it
        # fires, so re-filtering swaps the targets without re-registering.
        # show_message=False keeps the hint out of the scene and out of a cast.
        #
        # Picking is an interactor event, and a QtInteractor built while
        # pyvista.OFF_SCREEN is set has no interactor at all -- iren is None,
        # and enable_point_picking raises on it. That is the state CI runs in,
        # since pyvista's headless-display action exports PYVISTA_OFF_SCREEN.
        # Nothing is lost by skipping it there: an off-screen window is one
        # nobody can point at. _on_pick stays callable either way, which is
        # how the picking tests drive it.
        if self.plotter.iren is not None:
            self.plotter.enable_point_picking(
                callback=self._on_pick, show_message=False, show_point=False
            )
        self._compose(specs, answer)

    def _build_controls(self) -> None:
        """A dock of toggles for everything the scene can draw or leave out.

        The fleet's other viewers (``gutenberg_kg``, ``pycode_kg``,
        ``Metabo_kg``) put their controls in a panel like this; only
        ``genealogy_kg``, which this file was modelled on, has none. A
        connectome scene has more to turn on and off than a family tree does,
        so it follows the majority.

        Each toggle redraws, because the overlays are composed rather than
        merely hidden: the cloud is one glyph per neuron and the surfaces are
        78 merged meshes, and keeping both around to toggle visibility would
        cost more than rebuilding the scene without them.
        """
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setSpacing(6)

        layout.addWidget(self._heading("Overlays"))
        self._toggles: dict[str, QCheckBox] = {}
        for key, text, checked in (
            ("cloud", "Whole-brain cloud", bool(self._cloud)),
            ("neuropils", "Neuropil surfaces", self._neuropils),
            ("floor", "Floor and shadow", self._floor),
            ("tubes", "Skeletons as tubes", self._tubes),
        ):
            box = QCheckBox(text, panel)
            box.setChecked(checked)
            box.stateChanged.connect(self._on_toggle)
            layout.addWidget(box)
            self._toggles[key] = box

        layout.addWidget(self._separator())
        layout.addWidget(self._heading("Detail"))
        layout.addWidget(QLabel("Skeleton stride (0 = automatic)", panel))
        self._stride = QSpinBox(panel)
        self._stride.setRange(0, MAX_SKELETON_STEP)
        self._stride.setValue(self._skeleton_step or 0)
        self._stride.setToolTip(
            "0 lets the stride follow the neuron count, so a large answer stays drawable."
        )
        layout.addWidget(self._stride)

        layout.addWidget(QLabel("Minimum synapses (cone)", panel))
        self._min_syn = QSpinBox(panel)
        self._min_syn.setRange(1, MAX_MIN_SYN)
        self._min_syn.setValue(1)
        self._min_syn.setToolTip(
            "Raise this to bring a multi-hop cone under the scene cap; it only affects "
            "cone: answers."
        )
        layout.addWidget(self._min_syn)

        layout.addWidget(self._separator())
        layout.addWidget(self._heading("Examples"))
        examples = QTextEdit(panel)
        examples.setReadOnly(True)
        examples.setPlainText(spec_help())
        examples.setLineWrapMode(QTextEdit.NoWrap)
        layout.addWidget(examples, stretch=1)

        dock = QDockWidget("Controls", self)
        dock.setWidget(panel)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        self._controls_dock = dock

    def _heading(self, text: str) -> QLabel:
        label = QLabel(text, self)
        label.setStyleSheet("font-weight: bold;")
        return label

    def _separator(self) -> QFrame:
        line = QFrame(self)
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        return line

    def _on_toggle(self) -> None:
        """Apply the toggles by redrawing whatever the view currently shows."""
        self._cloud = self._toggles["cloud"].isChecked()
        self._neuropils = self._toggles["neuropils"].isChecked()
        self._floor = self._toggles["floor"].isChecked()
        self._tubes = self._toggles["tubes"].isChecked()
        self._skeleton_step = self._stride.value() or None
        self._compose(self._specs, self._answer, keep_camera=True)

    def _compose(
        self, specs: Sequence[str], answer: Answer | None = None, *, keep_camera: bool = False
    ) -> None:
        """Draw a scene for *specs*, or for an answer, replacing whatever is there.

        :param specs: The specs to draw; empty draws the brain alone.
        :param answer: A resolved path or cone, drawn hop-coloured instead of
            by cell type.
        :param keep_camera: Leave the camera where the viewer put it. A toggle
            changes what is drawn, not what is being looked at, so re-aiming
            would throw away the rotation the viewer had chosen; a new subject
            is re-framed because the old camera may not contain it.
        """
        camera = self.plotter.camera_position if keep_camera else None
        self.plotter.clear()
        info = render3d.build_brain_scene(
            self.plotter,
            self._kg,
            specs=() if answer else specs,
            groups=answer.groups if answer else None,
            view=self._view,
            data_dir=self._data_dir,
            color_by=self._color_by,
            skeleton_step=self._skeleton_step,
            tubes=self._tubes,
            top=self._top,
            neuropils=self._neuropils,
            cloud=self._cloud,
        )
        self._specs = list(specs)
        self._answer = answer
        self._picks = info.picks
        title = f"{answer.title} | {info.title}" if answer else info.title
        self.setWindowTitle(f"ConnectomeKG viz3d -- {title}")
        if camera is None:
            render3d.aim_camera(self.plotter, info.points, elevation=self._elevation)
        else:
            self.plotter.camera_position = camera
        if self._floor:
            render3d.add_floor(self.plotter)

        if len(self._picks):
            drawn = f"{len(self._picks.neuron_ids)} neurons drawn."
            self._info_panel.setPlainText(
                f"{drawn}\n\nPoint at one and press P to identify it."
                f"\n\nShow also takes an answer:\n{ANSWER_SYNTAX}"
            )
            self._dock.show()
            self._say("Point at a neuron and press P to identify it.")
        else:
            self._info_panel.setPlainText(
                "Nothing here to pick.\n\n"
                "The flow view draws neuropils rather than neurons, and a "
                "circuit view needs a spec that resolves to some."
            )
            self._dock.setVisible(self._view != "flow")
            self._say("No neurons drawn.")

    def _say(self, message: str) -> None:
        """Put a line in the status bar, which QMainWindow types as optional."""
        status = self.statusBar()
        if status is not None:
            status.showMessage(message)

    def _apply_filter(self) -> None:
        """Redraw for whatever the filter box holds, or explain why it cannot.

        The specs are resolved *before* the old scene is torn down, so a typo
        or a spec over ``MAX_SCENE_NEURONS`` leaves the view as it was rather
        than emptying it.
        """
        text = self._filter_box.text().strip()
        if is_answer(text):
            try:
                answer = answer_groups(self._kg, text, min_syn=self._min_syn.value())
            except ValueError as exc:
                self._reject(str(exc))
                return
            self._compose([text], answer)
            return

        specs = text.split()
        try:
            # An unknown name is not an error to `neurons_of`, it is an empty
            # result, so emptiness has to be checked for rather than caught --
            # and per spec, not over the union. "LC4 NoSuchType" resolves to
            # LC4's neurons, and drawing those silently would look like a
            # scene that contains both.
            empty = [spec for spec in specs if not self._kg.neurons_of(spec)]
            if specs and not empty:
                render3d.circuit_neurons(self._kg, specs)  # raises over the cap
        except ValueError as exc:
            self._reject(str(exc))
            return
        if empty:
            self._reject(f"No neuron matches {', '.join(empty)}. Specs are case-sensitive.")
            return
        self._compose(specs)

    def _reject(self, message: str) -> None:
        """Explain why a filter was not applied, leaving the scene as it was.

        :param message: What was wrong with the spec.
        """
        self._info_panel.setPlainText(f"Cannot show that.\n\n{message}")
        self._say(message)

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

        answer = self._answer

        def build(plotter) -> None:
            render3d.build_brain_scene(
                plotter,
                kg,
                specs=() if answer else specs,
                groups=answer.groups if answer else None,
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
    skeleton_step: int | None = None,
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
        answer = None
        if len(specs) == 1 and is_answer(specs[0]):
            answer = answer_groups(kg, specs[0])
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
            answer=answer,
        )
        window.show()
        app.exec_()


__all__ = ["BrainSceneWindow", "launch"]
