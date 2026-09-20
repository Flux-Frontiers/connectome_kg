"""connectomekg.viz3d -- imports, and that the window can actually be built.

The window is constructed offscreen rather than shown. That is worth doing
even though no human sees it: `connkg viz3d` shipped broken in 0.4.0 because
``BrainSceneWindow.__init__`` aimed the camera before anything had given the
render window a size, and `frame_and_focus` divides by that height. Nothing
caught it, because until the fix the only test here was an import.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="module")
def qapp():
    """One offscreen QApplication for the module, or a skip if Qt is absent."""
    pytest.importorskip("PyQt5")
    pytest.importorskip("pyvistaqt")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication  # noqa: PLC0415 - after importorskip

    yield QApplication.instance() or QApplication([])


def test_module_imports_with_pyqt5_and_pyvistaqt_present():
    pytest.importorskip("PyQt5")
    pytest.importorskip("pyvistaqt")
    import connectomekg.viz3d  # noqa: F401, PLC0415 - the point of the test


def test_the_window_builds_and_its_render_window_has_a_size(qapp, kg):
    """The regression: a zero-height render window made aiming the camera divide by zero."""
    from connectomekg.viz3d import DEFAULT_WINDOW_SIZE, BrainSceneWindow  # noqa: PLC0415

    window = BrainSceneWindow(kg, ["GRN_sugar"], cloud=False, neuropils=False)
    try:
        assert tuple(window.plotter.window_size) == DEFAULT_WINDOW_SIZE
        assert all(n > 0 for n in window.plotter.window_size)
        assert "circuit=" in window.windowTitle()
    finally:
        window.close()


def test_an_explicit_size_reaches_the_render_window(qapp, kg):
    from connectomekg.viz3d import BrainSceneWindow  # noqa: PLC0415

    window = BrainSceneWindow(
        kg, ["GRN_sugar"], cloud=False, neuropils=False, width=640, height=480
    )
    try:
        assert tuple(window.plotter.window_size) == (640, 480)
    finally:
        window.close()


def test_a_pick_on_a_drawn_neuron_describes_it(qapp, kg):
    from connectomekg.viz3d import BrainSceneWindow  # noqa: PLC0415

    window = BrainSceneWindow(kg, ["GRN_sugar"], cloud=False, neuropils=False)
    try:
        picks = window._picks
        assert len(picks.neuron_ids) > 0
        point = picks.points[picks.owner == 0][0]
        window._on_pick(point)
        shown = window._info_panel.toPlainText()
        node = kg.describe(picks.neuron_ids[0])
        assert node["qualname"] in shown
        assert "Inputs:" in shown and "Outputs:" in shown
    finally:
        window.close()


def test_a_pick_far_from_everything_reports_a_miss(qapp, kg):
    from connectomekg.viz3d import BrainSceneWindow  # noqa: PLC0415

    window = BrainSceneWindow(kg, ["GRN_sugar"], cloud=False, neuropils=False)
    try:
        window._on_pick(window._picks.points[0] + 1000.0)
        assert "No neuron there" in window._info_panel.toPlainText()
    finally:
        window.close()


def test_the_flow_view_hides_the_pick_panel(qapp, kg):
    from connectomekg.viz3d import BrainSceneWindow  # noqa: PLC0415

    window = BrainSceneWindow(kg, [], view="flow", cloud=False, neuropils=False)
    try:
        assert len(window._picks) == 0
        assert window._dock.isHidden()
        assert "nothing to pick" in window._info_panel.toPlainText()
    finally:
        window.close()
