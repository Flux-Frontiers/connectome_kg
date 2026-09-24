"""connectomekg/viz3d.py

Interactive 3-D viewer for a connectome scene: a ``QMainWindow`` wrapping a
``pyvistaqt.QtInteractor``, showing what
:func:`connectomekg.scene.build_brain_scene` composes -- the whole-brain
context cloud plus a spec's circuit skeletons, or the neuropil flow.

The workspace follows ``gutenberg_kg``'s control-rail and viewport layout.
``QtInteractor`` supplies orbit/zoom/pan for free via VTK's default
interactor style, and Cast to Looking Glass is wired straight to
``kg_utils.viz3d.qt.cast_scene_to_looking_glass``, which does the entire cast
on the GUI thread.

The control rail's Dataset and View boxes switch connectome and view in place;
switching dataset keeps the Show box's specs where they resolve in the new
graph, and falls back to the opening scene where they do not.

The control rail's Show box re-resolves specs and redraws in place, so exploring
does not mean restarting. It refuses a spec that matches nothing, or one over
``MAX_SCENE_NEURONS``, and leaves the scene as it was -- including when only
one spec of several is bad, since drawing the rest would look like a scene
that contained them all. The Explore tab lists every documented spec,
answer and named circuit as a button that fills the Show box and applies it,
so the grammar can be explored without being retyped.

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

import shlex
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from functools import partial
from pathlib import Path
from time import perf_counter
from typing import Any

from kg_utils.viz3d.qt import DEFAULT_QUILT_PRESET, cast_scene_to_looking_glass
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from pyvista import Actor
from pyvistaqt import QtInteractor

from connectomekg import __version__
from connectomekg import scene as render3d
from connectomekg.answers import (
    ANSWER_EXAMPLES,
    ANSWER_SYNTAX,
    SPEC_EXAMPLES,
    Answer,
    answer_groups,
    circuit_examples,
    is_answer,
)
from connectomekg.cli.cmd_viz3d import (
    QUILTS_DIR,
    STILL_HEIGHT,
    STILLS_DIR,
    opening_specs,
    scene_stem,
)
from connectomekg.cli.options import open_kg
from connectomekg.datasets import scan_datasets
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

# Gutenberg's three surface levels, green headings and blue cast action.
DARK_STYLESHEET = """
    QMainWindow { background: #11151e; }
    QWidget { background: #1a2030; color: #e6e9ef; font-size: 13px; }
    QLabel { background: transparent; }
    QLabel[role="heading"] { color: #90ee90; font-weight: bold;
        border-bottom: 1px solid #3a4358; padding: 6px 0; }
    QLabel[role="muted"] { color: #9aa4b8; }
    QLabel#brand { font-size: 20px; font-weight: bold; }
    QLabel#scene-title { font-size: 17px; font-weight: bold; }
    QLineEdit, QSpinBox, QTextEdit { background: #232b3d;
        border: 1px solid #3a4358; border-radius: 4px; padding: 6px;
        selection-background-color: #2e8b57; }
    QLineEdit:focus, QSpinBox:focus, QTextEdit:focus { border-color: #5fa8d3; }
    QPushButton { background: #232b3d; border: 1px solid #3a4358;
        border-radius: 4px; padding: 7px 10px; }
    QPushButton:hover { background: #2b3448; border-color: #5fa8d3; }
    QPushButton:focus { border-color: #90ee90; }
    QPushButton:pressed, QPushButton:checked { background: #35465e; }
    QPushButton#show-scene { background: #2e8b57; font-weight: bold; }
    QPushButton#cast-scene { background: #3e5f8a; font-weight: bold; }
    QPushButton:disabled { color: #788297; background: #1a2030; }
    QComboBox { background: #232b3d; border: 1px solid #3a4358;
        border-radius: 4px; padding: 5px 8px; }
    QComboBox:focus { border-color: #5fa8d3; }
    QComboBox QAbstractItemView { background: #232b3d;
        selection-background-color: #35465e; }
    QTabWidget::pane { border: 0; }
    QTabBar::tab { padding: 9px 16px; color: #9aa4b8; border: none;
        border-bottom: 2px solid transparent; }
    QTabBar::tab:selected { color: #90ee90; border-bottom: 2px solid #90ee90; }
    QCheckBox { spacing: 8px; padding: 5px 0; }
    QSplitter::handle { background: #11151e; }
    QScrollBar:vertical { background: #1a2030; width: 12px; }
    QScrollBar::handle:vertical { background: #3a4358; min-height: 24px; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    QStatusBar { background: #11151e; color: #9aa4b8; }
    QMenu { background: #232b3d; border: 1px solid #3a4358; padding: 4px 0; }
    QMenu::item { padding: 6px 18px; }
    QMenu::item:selected { background: #35465e; }
"""


def _split_specs(text: str) -> list[str]:
    """Split Show input while preserving label spaces and regex backslashes.

    A leading unquoted ``label:`` consumes the whole field. Quote the full
    label spec to combine it with other specs, e.g. ``"label:giant fib" LC4``.

    :param text: Trimmed Show input (answers are handled before this).
    :raises ValueError: On an unterminated quote.
    """
    if text.startswith("label:"):
        return [text]
    lexer = shlex.shlex(text, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    lexer.escape = ""  # Backslashes belong to label regexes, not shell escapes.
    return list(lexer)


def _dataset_id(kg: ConnectomeKG) -> str:
    """The id of *kg*'s dataset: its directory under ``connectomes/``."""
    return Path(kg.db_path).parents[1].name


class BrainSceneWindow(QMainWindow):
    """Main window: whole-brain context plus a circuit or flow, orbit/zoom/pan, one Cast action.

    :param kg: An open ``ConnectomeKG``.
    :param specs: Specs resolved into the circuit view (view B), or restricting
        the flow view (view C).
    :param view: ``"circuit"`` or ``"flow"``.
    :param data_dir: Skeleton download root, or ``None`` for marked-point
        fallback spheres on every circuit neuron.
    :param color_by: Context cloud coloring, ``"super_class"`` or ``"sign"``.
    :param skeleton_step: Skeleton simplification stride.
    :param tubes: Draw circuit skeletons as tubes instead of lines.
    :param top: Flow arcs drawn, strongest first.
    :param neuropils: Draw the neuropil surface meshes, when cached.
    :param cloud: Draw the whole-brain context cloud; ``None`` draws it
        only when no neuropil meshes are.
    :param floor: Stand the scene over a floor lit from above, with shadows.
    :param elevation: Degrees to tilt the camera up from the front view.
    :param preset: Quilt preset name for the Cast action.
    :param answer: A resolved path or cone to open on, drawn hop-colored
        instead of by cell type.
    :param background: Scene background, ``#RRGGBB``.
    :param root: Directory holding ``connectomes/``; enables the Dataset box,
        which lists every dataset built there. ``None`` hides it.
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
        background: str = render3d.BACKGROUND,
        root: str | Path | None = None,
    ) -> None:
        super().__init__()
        self._kg = kg
        self._root = root
        self._background = background
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
        # The composed scene's world points, kept so Reset view can re-aim at
        # the same framing the scene was first given.
        self._points: object = None

        self.setStyleSheet(DARK_STYLESHEET)
        self._build_workspace(specs)

        # Enabled once, not per scene: the callback reads the current targets.
        # Off-screen QtInteractors have no interactor, so CI skips registration.
        if self.plotter.iren is not None:
            self.plotter.enable_point_picking(
                callback=self._on_pick, show_message=False, show_point=False
            )
        self._compose(specs, answer)

    def _build_workspace(self, specs: Sequence[str]) -> None:
        """Build a bounded control rail and a viewport with a lower inspector."""
        self._controls_panel = QWidget(self)
        self._controls_panel.setMinimumWidth(280)
        self._controls_panel.setMaximumWidth(380)
        rail = QVBoxLayout(self._controls_panel)
        rail.setContentsMargins(14, 12, 14, 12)
        rail.setSpacing(10)
        brand = QLabel("ConnectomeKG", self)
        brand.setObjectName("brand")
        brand_row = QHBoxLayout()
        brand_row.addWidget(brand)
        self._version_label = QLabel(f"v{__version__}", self)
        self._version_label.setProperty("role", "muted")
        brand_row.addWidget(self._version_label)
        brand_row.addStretch(1)
        rail.addLayout(brand_row)
        subtitle = QLabel("3D CONNECTOME EXPLORER", self)
        subtitle.setProperty("role", "muted")
        rail.addWidget(subtitle)
        rail.addLayout(self._build_pickers())
        rail.addWidget(self._heading("Show"))
        self._filter_box = QLineEdit(self)
        self._filter_box.setPlaceholderText("LC4 DNp01, circuit:compass, path:...")
        self._filter_box.setToolTip(
            "Enter space-separated specs, a root id, or an answer.\n"
            "A label may contain spaces: label:giant fib.\n"
            'To combine it with another spec: "label:giant fib" LC4.\n'
            "Clear the box to show the brain alone.\n" + ANSWER_SYNTAX
        )
        self._filter_box.setText(specs[0] if len(specs) == 1 else shlex.join(specs))
        self._filter_box.setClearButtonEnabled(True)
        self._filter_box.returnPressed.connect(self._apply_filter)
        self._filter_box.setAccessibleName("Scene specification")
        rail.addWidget(self._filter_box)
        self._show_button = QPushButton("Show scene", self)
        self._show_button.setObjectName("show-scene")
        self._show_button.setMinimumHeight(38)
        self._show_button.clicked.connect(self._apply_filter)
        rail.addWidget(self._show_button)

        self._tabs = QTabWidget(self)
        self._examples = self._example_buttons(self._tabs)
        self._tabs.addTab(self._examples, "Explore")
        self._tabs.addTab(self._build_controls(), "Display")
        rail.addWidget(self._tabs, stretch=1)
        self._save_button = QPushButton("Save scene...", self)
        self._save_button.setMinimumHeight(36)
        self._save_button.setToolTip(
            "Write the current scene and camera to disk, without casting.\n"
            "Image: one 4K still, as `connkg quilt --still` renders.\n"
            f"Quilt: the {self._preset} quilt Cast would send."
        )
        save_menu = QMenu(self._save_button)
        save_menu.addAction("Image...", self._save_image)
        save_menu.addAction("Quilt...", self._save_quilt)
        self._save_button.setMenu(save_menu)
        rail.addWidget(self._save_button)
        self._cast_button = QPushButton("Cast to Looking Glass", self)
        self._cast_button.setObjectName("cast-scene")
        self._cast_button.setMinimumHeight(36)
        self._cast_button.setToolTip("Cast the current scene and camera using " + self._preset)
        self._cast_button.clicked.connect(self._cast)
        rail.addWidget(self._cast_button)

        viewport = QWidget(self)
        vis = QVBoxLayout(viewport)
        vis.setContentsMargins(12, 12, 12, 8)
        vis.setSpacing(8)
        self._scene_title = QLabel(self)
        self._scene_title.setObjectName("scene-title")
        self._scene_title.setTextFormat(Qt.TextFormat.PlainText)
        self._scene_title.setWordWrap(True)
        self._scene_title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        vis.addWidget(self._scene_title)
        self._scene_stats = QLabel(self)
        self._scene_stats.setProperty("role", "muted")
        self._scene_stats.setWordWrap(True)
        vis.addWidget(self._scene_stats)
        self._geometry_stats = QLabel(self)
        self._geometry_stats.setProperty("role", "muted")
        self._geometry_stats.setWordWrap(True)
        self._geometry_stats.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        vis.addWidget(self._geometry_stats)

        self._inspector = QWidget(self)
        details = QVBoxLayout(self._inspector)
        details.setContentsMargins(0, 0, 0, 0)
        details.addWidget(self._heading("Neuron inspector"))
        self._info_panel = QTextEdit(self)
        self._info_panel.setReadOnly(True)
        self._info_panel.setLineWrapMode(QTextEdit.WidgetWidth)
        self._info_panel.setAccessibleName("Neuron details")
        details.addWidget(self._info_panel)
        self._viewport_splitter = QSplitter(Qt.Orientation.Vertical, self)
        self._viewport_splitter.setChildrenCollapsible(False)
        self._viewport_splitter.addWidget(self.plotter)
        self._viewport_splitter.addWidget(self._inspector)
        self._viewport_splitter.setStretchFactor(0, 1)
        self._viewport_splitter.setStretchFactor(1, 0)
        self._viewport_splitter.setSizes([650, 160])
        vis.addWidget(self._viewport_splitter, stretch=1)

        actions = QHBoxLayout()
        self._reset_button = QPushButton("Reset view", self)
        self._reset_button.setToolTip("Frame the current scene again, undoing any orbit or zoom.")
        self._reset_button.clicked.connect(self._reset_view)
        actions.addWidget(self._reset_button)
        self._inspect_button = QPushButton("Neuron details", self)
        self._inspect_button.setCheckable(True)
        self._inspect_button.setChecked(True)
        self._inspect_button.toggled.connect(self._inspector.setVisible)
        actions.addWidget(self._inspect_button)
        hint = QLabel("Drag to orbit  |  Scroll to zoom  |  P to pick", self)
        hint.setProperty("role", "muted")
        hint.setWordWrap(True)
        actions.addWidget(hint, stretch=1)
        vis.addLayout(actions)

        self._workspace = QSplitter(Qt.Orientation.Horizontal, self)
        self._workspace.setChildrenCollapsible(False)
        self._workspace.addWidget(self._controls_panel)
        self._workspace.addWidget(viewport)
        self._workspace.setStretchFactor(0, 0)
        self._workspace.setStretchFactor(1, 1)
        self._workspace.setSizes([310, 1090])
        self.setCentralWidget(self._workspace)

    def _build_controls(self) -> QScrollArea:
        """Scrollable display settings; overlay toggles rebuild the scene."""
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
            if key == "cloud":
                box.setTristate(True)
                if self._cloud is None:
                    box.setCheckState(Qt.CheckState.PartiallyChecked)
                box.setToolTip(
                    "Partially checked = automatic (cloud when no surfaces are available).\n"
                    "Checked = always show. Unchecked = hide."
                )
            box.stateChanged.connect(self._on_toggle)
            layout.addWidget(box)
            self._toggles[key] = box

        layout.addWidget(QLabel("Background", panel))
        self._background_box = QComboBox(panel)
        for name, color in render3d.BACKGROUNDS.items():
            self._background_box.addItem(name.capitalize(), color)
        self._background_box.addItem("Custom...", None)
        self._show_background(self._background)
        self._background_box.setToolTip(
            "Scene background. Saved images, quilts and casts use it too."
        )
        self._background_box.activated.connect(self._on_background)
        layout.addWidget(self._background_box)

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
        self._stride.editingFinished.connect(self._apply_stride)

        layout.addWidget(QLabel("Minimum synapses (cone)", panel))
        self._min_syn = QSpinBox(panel)
        self._min_syn.setRange(1, MAX_MIN_SYN)
        self._min_syn.setValue(1)
        self._min_syn.setToolTip(
            "Raise this to bring a multi-hop cone under the scene cap; it only affects "
            "cone: answers."
        )
        layout.addWidget(self._min_syn)
        note = QLabel("Minimum synapses applies when you next choose Show scene.", panel)
        note.setWordWrap(True)
        note.setProperty("role", "muted")
        layout.addWidget(note)
        layout.addStretch(1)
        area = QScrollArea(self)
        area.setWidget(panel)
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        return area

    def _build_pickers(self) -> QHBoxLayout:
        """The Dataset and View boxes at the top of the rail.

        The Dataset box lists every dataset built under ``root``, and is
        hidden when the window was given no root or there is only one.
        """
        row = QHBoxLayout()
        column = QVBoxLayout()
        column.addWidget(QLabel("Dataset", self))
        self._dataset_box = QComboBox(self)
        self._dataset_box.setToolTip("Switch connectome without restarting.")
        self._dataset_box.setAccessibleName("Dataset")
        ids = scan_datasets(self._root) if self._root is not None else []
        self._dataset_box.addItems(ids)
        current = _dataset_id(self._kg)
        if current in ids:
            self._dataset_box.setCurrentIndex(ids.index(current))
        self._dataset_box.activated.connect(self._on_dataset)
        column.addWidget(self._dataset_box)
        dataset_widget = QWidget(self)
        dataset_widget.setLayout(column)
        dataset_widget.setVisible(len(ids) > 1)
        row.addWidget(dataset_widget, stretch=1)

        column = QVBoxLayout()
        column.addWidget(QLabel("View", self))
        self._view_box = QComboBox(self)
        self._view_box.addItems(render3d.VIEWS)
        self._view_box.setCurrentIndex(list(render3d.VIEWS).index(self._view))
        self._view_box.setToolTip(
            "circuit: the Show box's neurons as skeletons.\n"
            "flow: signal flow between neuropils, carried by the Show box's neurons if any."
        )
        self._view_box.setAccessibleName("View")
        self._view_box.activated.connect(self._on_view)
        column.addWidget(self._view_box)
        row.addLayout(column, stretch=1)
        return row

    @property
    def kg(self) -> ConnectomeKG:
        """The graph currently shown; the window closes any it replaces."""
        return self._kg

    def _on_dataset(self, index: int) -> None:
        """Open the chosen dataset and redraw the Show box's scene in it.

        The specs are kept when they resolve in the new graph. Cell type
        names differ between connectomes, so when they do not, the scene
        falls back to what the viewer opens on, rather than refusing the
        switch.

        :param index: The chosen row of the Dataset box.
        """
        dataset = self._dataset_box.itemText(index)
        if self._root is None or dataset == _dataset_id(self._kg):
            return
        with self._busy(f"Opening {dataset}..."):
            try:
                kg = open_kg(str(self._root), dataset=dataset)
            except Exception as exc:  # noqa: BLE001 - a bad dataset must not kill the viewer
                self._dataset_box.setCurrentText(_dataset_id(self._kg))
                self._reject(f"Could not open {dataset}: {exc}")
                return
        previous, self._kg = self._kg, kg
        previous.close()
        try:
            specs, answer = self._resolve(self._filter_box.text().strip())
        except ValueError:
            specs, answer = opening_specs(kg, [], self._view), None
            self._filter_box.setText(shlex.join(specs))
        self._compose(specs, answer)

    def _on_view(self, index: int) -> None:
        """Redraw the current specs in the chosen view, framed afresh.

        :param index: The chosen row of the View box.
        """
        view = self._view_box.itemText(index)
        if view == self._view:
            return
        self._view = view
        self._compose(self._specs, self._answer)

    def _show_background(self, color: str) -> None:
        """Select *color*'s row in the Background box, or Custom for any other."""
        index = self._background_box.findData(color.upper())
        custom = self._background_box.count() - 1
        self._background_box.setCurrentIndex(custom if index < 0 else index)
        self._background_box.setItemText(
            custom, f"Custom ({color.upper()})..." if index < 0 else "Custom..."
        )

    def _on_background(self, index: int) -> None:
        """Apply the chosen background, asking for a color on Custom.

        :param index: The chosen row of the Background box.
        """
        color = self._background_box.itemData(index)
        if color is None:
            picked = QColorDialog.getColor(QColor(self._background), self, "Scene background")
            if not picked.isValid():
                self._show_background(self._background)
                return
            color = picked.name().upper()
        self._show_background(color)
        if color != self._background:
            self._background = color
            self._compose(self._specs, self._answer, keep_camera=True)

    def _example_buttons(self, parent: QWidget) -> QScrollArea:
        """Every documented spec, answer and circuit as a button that draws it.

        The panel used to show :func:`connectomekg.answers.spec_help` as
        text to be retyped into
        the Show box. The grammar is the same list either way, so the buttons
        are built from it rather than from a second list that could drift:
        each one puts its example in the Show box and applies it, which is
        the path a typed spec takes, refusals included.

        Circuits come first, and an example already shown is not repeated:
        ``circuit:compass`` is in the spec grammar to document the *form* and
        in the circuit list as one of the circuits, which is two lines of
        help but should not be two buttons.

        :param parent: The controls panel.
        :return: A scroll area of buttons, grouped as the help text is.
        """
        inner = QWidget(parent)
        column = QVBoxLayout(inner)
        column.setSpacing(2)
        seen: set[str] = set()
        for title, examples in (
            ("Circuits", circuit_examples()),
            ("Specs", SPEC_EXAMPLES),
            ("Answers", ANSWER_EXAMPLES),
        ):
            fresh = [(e, m) for e, m in examples if e not in seen]
            if not fresh:
                continue
            label = QLabel(title, inner)
            label.setProperty("role", "heading")
            column.addWidget(label)
            for example, meaning in fresh:
                seen.add(example)
                button = QPushButton(example, inner)
                button.setToolTip(meaning)
                button.setStyleSheet("text-align: left; padding: 7px 6px;")
                button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
                # default=False keeps Return in the Show box out of these.
                button.setAutoDefault(False)
                button.clicked.connect(partial(self._draw_example, example))
                column.addWidget(button)
        column.addStretch(1)
        area = QScrollArea(parent)
        area.setWidget(inner)
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        return area

    def _draw_example(self, example: str) -> None:
        """Draw a clicked example, exactly as typing it would.

        :param example: The spec, answer or circuit on the button.
        """
        self._filter_box.setText(example)
        self._apply_filter()

    def _heading(self, text: str) -> QLabel:
        label = QLabel(text, self)
        label.setProperty("role", "heading")
        return label

    def _separator(self) -> QFrame:
        line = QFrame(self)
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        return line

    def _on_toggle(self) -> None:
        """Apply the toggles by redrawing whatever the view currently shows."""
        cloud_state = self._toggles["cloud"].checkState()
        self._cloud = (
            None
            if cloud_state == Qt.CheckState.PartiallyChecked
            else cloud_state == Qt.CheckState.Checked
        )
        self._neuropils = self._toggles["neuropils"].isChecked()
        self._floor = self._toggles["floor"].isChecked()
        self._tubes = self._toggles["tubes"].isChecked()
        self._skeleton_step = self._stride.value() or None
        self._compose(self._specs, self._answer, keep_camera=True)

    def _apply_stride(self) -> None:
        """Apply an edited stride once, without rebuilding on an unchanged focus loss."""
        if (self._stride.value() or None) != self._skeleton_step:
            self._on_toggle()

    def _compose(
        self, specs: Sequence[str], answer: Answer | None = None, *, keep_camera: bool = False
    ) -> None:
        """Draw a scene for *specs*, or for an answer, replacing whatever is there.

        :param specs: The specs to draw; empty draws the brain alone.
        :param answer: A resolved path or cone, drawn hop-colored instead of
            by cell type.
        :param keep_camera: Leave the camera where the viewer put it. A toggle
            changes what is drawn, not what is being looked at, so re-aiming
            would throw away the rotation the viewer had chosen; a new subject
            is re-framed because the old camera may not contain it.
        """
        started = perf_counter()
        camera = self.plotter.camera_position if keep_camera else None
        with self._busy("Composing the scene..."):
            info = self._build(specs, answer)
        self._specs = list(specs)
        self._answer = answer
        self._picks = info.picks
        self._points = info.points
        title = f"{answer.title} | {info.title}" if answer else info.title
        self.setWindowTitle(f"ConnectomeKG v{__version__} viz3d -- {title}")
        self._scene_title.setText(
            answer.title
            if answer
            else " + ".join(specs) or ("Neuropil flow" if self._view == "flow" else "Whole brain")
        )
        self._scene_stats.setText(
            f"{info.view.capitalize()} view  |  {info.n_circuit:,} circuit neurons  |  "
            f"{info.n_context:,} context neurons  |  {info.n_neuropil_meshes:,} neuropil surfaces"
            + (
                f"  |  {info.n_flow_pairs:,} flow arcs"
                if info.view == "flow"
                else f"  |  {info.n_skeletons:,} skeletons"
            )
        )
        self._scene_stats.setToolTip(info.title)
        if camera is None:
            render3d.aim_camera(self.plotter, info.points, elevation=self._elevation)
        else:
            self.plotter.camera_position = camera
        if self._floor:
            render3d.add_floor(self.plotter, self._background)
        self._update_geometry_stats(started)
        self._describe_scene()

    def _update_geometry_stats(self, started: float) -> None:
        """Count expanded mesh geometry without copying or traversing its arrays.

        Counts are per visible actor, including off-camera geometry. Cells
        include polygons, polylines and strips; they are not GPU triangles.
        Glyphs and tubes have already expanded into their rendered meshes.

        :param started: ``perf_counter`` timestamp at the start of composition;
            the displayed duration includes framing and pending mesh updates,
            not a frame-rate benchmark or a cast duration.
        """
        groups: dict[str, list[int]] = {}
        for name, actor in self.plotter.renderer.actors.items():
            if not isinstance(actor, Actor) or not actor.visibility:
                continue
            # Some mapper inputs are lazy filters and remain empty until
            # updated, especially before the window's first render.
            if actor.mapper is None:
                continue
            actor.mapper.Update()
            mesh = getattr(actor.mapper, "dataset", None)
            if mesh is None:
                continue
            counts = groups.setdefault(name.split(":", 1)[0], [0, 0, 0])
            counts[0] += 1
            counts[1] += mesh.n_points
            counts[2] += mesh.n_cells
        meshes, points, cells = (sum(row[i] for row in groups.values()) for i in range(3))
        self._geometry_stats.setText(
            f"Geometry: {meshes:,} meshes  |  {points:,} points  |  {cells:,} cells"
            f"  |  Scene build: {perf_counter() - started:.2f} s"
        )
        rows = [
            f"{name}: {n:,} meshes, {p:,} points, {c:,} cells"
            for name, (n, p, c) in sorted(groups.items(), key=lambda item: item[1][2], reverse=True)
        ]
        self._geometry_stats.setToolTip(
            "Scene geometry after glyph and tube expansion, including the floor.\n"
            "Cells are mesh faces, lines, vertices or strips; not neurons or GPU triangles.\n"
            "Counted per visible mesh, including geometry outside the camera view.\n\n"
            + "\n".join(rows)
            + "\n\nFor lighter scenes: hide the cloud or surfaces, turn off tubes, "
            "or increase skeleton stride.\nScene build measures setup on this machine, not FPS."
        )

    def _build(self, specs: Sequence[str], answer: Answer | None):
        """Compose the scene into the live plotter.

        :param specs: The specs to draw.
        :param answer: A resolved path or cone, or ``None``.
        :return: The ``SceneInfo`` the scene reports.
        """
        return render3d.build_brain_scene(
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
            background=self._background,
        )

    def _describe_scene(self) -> None:
        """Say what was drawn and whether there is anything to pick in it."""
        if len(self._picks):
            drawn = f"{len(self._picks.neuron_ids)} neurons drawn."
            self._info_panel.setPlainText(
                f"{drawn}\n\nPoint at one and press P to identify it."
                f"\n\nShow also takes an answer:\n{ANSWER_SYNTAX}"
            )
            self._say("Point at a neuron and press P to identify it.")
        else:
            self._info_panel.setPlainText(
                "Nothing here to pick.\n\n"
                "The flow view draws neuropils rather than neurons, and a "
                "circuit view needs a spec that resolves to some."
            )
            self._say(
                "Neuropil flow; neuron picking is unavailable."
                if self._view == "flow"
                else "Choose a spec or example to explore neurons."
            )
        self._inspect_button.setVisible(self._view != "flow")
        self._inspector.setVisible(self._view != "flow" and self._inspect_button.isChecked())

    @contextmanager
    def _busy(self, message: str) -> Iterator[None]:
        """Show *message* under a wait cursor while a slow step runs.

        Composing a scene reads skeletons and glyphs 139k somas, and a cast
        renders 48 views; both take seconds on the GUI thread, during which
        the window is unresponsive and, without this, silent. The cursor is
        the part that reads as "working" rather than "hung".

        Restored in a ``finally``: an override cursor that outlives its
        operation leaves the whole application looking busy for good.

        :param message: What is happening, for the status bar.
        """
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        # processEvents also delivers clicks: prevent another composition or
        # cast from starting while this one owns the scene.
        controls = (self._controls_panel, self._reset_button, self.plotter)
        enabled = [widget.isEnabled() for widget in controls]
        for widget in controls:
            widget.setEnabled(False)
        self._say(message)
        QApplication.processEvents()
        try:
            yield
        finally:
            for widget, was_enabled in zip(controls, enabled, strict=True):
                widget.setEnabled(was_enabled)
            QApplication.restoreOverrideCursor()
            QApplication.processEvents()

    def _reset_view(self) -> None:
        """Frame the current scene again, undoing an orbit or a zoom.

        Re-aims rather than restoring a saved camera, so it lands where the
        scene was first framed however far the view has been dragged since.

        The floor comes off first and goes back after. ``aim_camera`` frames
        ``plotter.bounds``, and the floor is a 120-unit plane around a brain
        about 8 across, so framing with it in place fits the floor and the
        subject shrinks to nothing -- which is why ``_compose`` aims before
        it adds the floor, and why this has to put it back the same way.
        """
        if self._points is None:
            self._say("Nothing to frame.")
            return
        if self._floor:
            self.plotter.remove_actor("floor")
        render3d.aim_camera(self.plotter, self._points, elevation=self._elevation)
        if self._floor:
            render3d.add_floor(self.plotter, self._background)
        self.plotter.render()
        self._say("View reset.")

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
        try:
            specs, answer = self._resolve(self._filter_box.text().strip())
        except ValueError as exc:
            self._reject(str(exc))
            return
        self._compose(specs, answer)

    def _resolve(self, text: str) -> tuple[list[str], Answer | None]:
        """Resolve Show box *text* against the current graph.

        :param text: Specs or one answer; empty is the brain alone.
        :return: ``(specs, answer)``, the answer ``None`` for plain specs.
        :raises ValueError: Saying why *text* cannot be drawn.
        """
        if is_answer(text):
            return [text], answer_groups(self._kg, text, min_syn=self._min_syn.value())
        specs = _split_specs(text)
        # An unknown name is not an error to `neurons_of`, it is an empty
        # result, so emptiness has to be checked for rather than caught --
        # and per spec, not over the union. "LC4 NoSuchType" resolves to
        # LC4's neurons, and drawing those silently would look like a
        # scene that contains both.
        empty = [spec for spec in specs if not self._kg.neurons_of(spec)]
        if empty:
            raise ValueError(f"No neuron matches {', '.join(empty)}. Specs are case-sensitive.")
        if specs:
            render3d.circuit_neurons(self._kg, specs)  # raises over the cap
        return specs, None

    def _reject(self, message: str) -> None:
        """Explain why a filter was not applied, leaving the scene as it was.

        :param message: What was wrong with the spec.
        """
        self._info_panel.setPlainText(f"Cannot show that.\n\n{message}")
        self._inspect_button.show()
        self._inspector.show()
        self._inspect_button.setChecked(True)
        self._say(message)

    def _on_pick(self, point, *_: object) -> None:
        """Resolve a picked position to a neuron and describe it in the panel.

        :param point: The picked position, in world coordinates.
        """
        self._inspect_button.setChecked(True)
        self._inspector.show()
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

    def _scene_builder(self) -> Callable[[Any], None]:
        """A function that composes the current scene into a fresh plotter.

        Everything a cast or a save renders is captured here, so the three
        share one definition of "the current scene": the specs or answer,
        every display setting, the floor, and the viewport's view angle.

        PyVista's ``camera_position`` is (position, focal point, view up) and
        carries no view angle, so a fresh off-screen plotter keeps VTK's
        default 30 degrees while the viewport is at the 14 that ``aim_camera``
        framed with. The subject then lands tan(15)/tan(7) = 2.2x too small,
        which is eight scroll-wheel steps to undo by hand. The angle is set
        inside the builder, before the caller assigns ``camera_position``,
        which does not disturb it.

        :return: A callable taking the plotter to compose into.
        """
        kg, specs, view = self._kg, self._specs, self._view
        data_dir, color_by = self._data_dir, self._color_by
        skeleton_step, tubes, top = self._skeleton_step, self._tubes, self._top
        floor, neuropils, cloud = self._floor, self._neuropils, self._cloud
        answer, background = self._answer, self._background
        view_angle = self.plotter.camera.view_angle

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
                background=background,
            )
            if floor:
                render3d.add_floor(plotter, background)
            plotter.camera.view_angle = view_angle

        return build

    def _cast(self) -> None:
        """Render the current view off-screen and push it to Looking Glass Bridge."""
        from quiltwright import QUILT_PRESETS  # noqa: PLC0415 - viz3d-only import

        spec = QUILT_PRESETS[self._preset]

        def step(n: int, total: int, message: str) -> None:
            """Report a cast stage, pumping the event loop so it is seen.

            The cast runs on the GUI thread, so without this the window is
            frozen from the click to the dialog -- some seconds, all of it
            silent.

            :param n: Stage number.
            :param total: How many stages there are.
            :param message: What is happening now.
            """
            self._say(f"Cast {n}/{total} -- {message}")
            QApplication.processEvents()

        out_stem = QUILTS_DIR / f"{scene_stem(self._view, tuple(self._specs))}_cast"
        with self._busy("Casting to Looking Glass..."):
            result = cast_scene_to_looking_glass(
                self._scene_builder(), self.plotter.camera_position, out_stem, spec, progress=step
            )
        self._say(result.message)
        box = QMessageBox.information if result.path else QMessageBox.warning
        box(self, "Cast to Looking Glass", result.message)

    def _save_image(self) -> None:
        """Save the current view as one 4K still, framed as ``quilt --still`` frames it."""
        from quiltwright import QUILT_PRESETS  # noqa: PLC0415 - viz3d-only import

        spec = QUILT_PRESETS[self._preset].still(height=STILL_HEIGHT)
        self._save_scene(spec, STILLS_DIR, "image")

    def _save_quilt(self) -> None:
        """Save the quilt Cast would send, without sending it."""
        from quiltwright import QUILT_PRESETS  # noqa: PLC0415 - viz3d-only import
        from quiltwright.quilt import resolve_view_cone  # noqa: PLC0415

        spec, _ = resolve_view_cone(QUILT_PRESETS[self._preset], None)
        self._save_scene(spec, QUILTS_DIR, "quilt")

    def _save_scene(self, spec: Any, out_dir: Path, what: str) -> None:
        """Ask where, render the current scene off-screen at ``spec``, and write it.

        The file is named the way ``connkg quilt`` names its output: the
        chosen name is the stem, and quiltwright appends the spec suffix
        (``_qs1x1a1.77778`` for a still, ``_qs8x6a1.77778`` for a quilt) that
        Looking Glass readers and the render scripts rely on. The path actually
        written is reported in the status bar and the dialog.

        :param spec: The quilt spec to render at; a still is a one-view spec.
        :param out_dir: Where the dialog opens, under ``renders/``.
        :param what: ``"image"`` or ``"quilt"``, for the dialog and messages.
        """
        import pyvista as pv  # noqa: PLC0415 - viz3d-only import
        from quiltwright import render_quilt, save_quilt  # noqa: PLC0415

        default = out_dir / f"{scene_stem(self._view, tuple(self._specs))}.png"
        chosen, _ = QFileDialog.getSaveFileName(
            self, f"Save {what}", str(default), "PNG image (*.png)"
        )
        if not chosen:
            return
        stem = Path(chosen).with_suffix("")
        stem.parent.mkdir(parents=True, exist_ok=True)
        with self._busy(f"Rendering {what}..."):
            offscreen = pv.Plotter(off_screen=True)
            try:
                self._scene_builder()(offscreen)
                offscreen.camera_position = self.plotter.camera_position
                written = save_quilt(render_quilt(offscreen, spec), stem, spec)
            except Exception as exc:  # noqa: BLE001 - a failed save must not take the viewer
                self._say(f"Save failed: {exc}")
                QMessageBox.warning(self, f"Save {what}", f"Could not save the {what}: {exc}")
                return
            finally:
                offscreen.close()
        self._say(f"Wrote {written}")
        QMessageBox.information(self, f"Save {what}", f"Wrote {written}")


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
    background: str = render3d.BACKGROUND,
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
    :param color_by: Context cloud coloring, ``"super_class"`` or ``"sign"``.
    :param skeleton_step: Skeleton simplification stride.
    :param tubes: Draw circuit skeletons as tubes instead of lines.
    :param top: Flow arcs drawn, strongest first.
    :param neuropils: Draw the neuropil surface meshes, when cached.
    :param cloud: Draw the whole-brain context cloud; ``None`` draws it
        only when no neuropil meshes are.
    :param floor: Stand the scene over a floor lit from above, with shadows.
    :param elevation: Degrees to tilt the camera up from the front view.
    :param background: Scene background, ``#RRGGBB``.
    :param preset: Quilt preset name for the Cast action.
    :param dataset: Dataset id, or ``None`` for the only built dataset.
    :param width: Window width in pixels.
    :param height: Window height in pixels.
    :raises ValueError: Propagated from ``ConnectomeKG`` / ``build_brain_scene``,
        e.g. a spec over ``MAX_SCENE_NEURONS``.
    """
    from PyQt5.QtWidgets import QApplication  # noqa: PLC0415 - viz3d-only import

    # Not a `with`: the Dataset box replaces the graph, and the window closes
    # each one it replaces, so what is left to close is the window's.
    kg = open_kg(str(root), dataset=dataset)
    window: BrainSceneWindow | None = None
    try:
        specs = opening_specs(kg, specs, view)
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
            background=background,
            root=root,
        )
        window.show()
        app.exec_()
    finally:
        (window.kg if window is not None else kg).close()


__all__ = ["BrainSceneWindow", "launch"]
