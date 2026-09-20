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
        assert "Nothing here to pick" in window._info_panel.toPlainText()
    finally:
        window.close()


def test_the_filter_box_redraws_for_a_new_spec(qapp, kg):
    from connectomekg.viz3d import BrainSceneWindow  # noqa: PLC0415

    window = BrainSceneWindow(kg, ["GRN_sugar"], cloud=False, neuropils=False)
    try:
        window._filter_box.setText("MN9")
        window._apply_filter()
        assert set(window._picks.neuron_ids) == set(kg.neurons_of("MN9"))
        # Cast must follow the filter, not the specs the window opened with.
        assert window._specs == ["MN9"]
        # And picking still resolves, without the callback being re-registered.
        point = window._picks.points[window._picks.owner == 0][0]
        window._on_pick(point)
        assert "Inputs:" in window._info_panel.toPlainText()
    finally:
        window.close()


def test_several_specs_are_unioned(qapp, kg):
    from connectomekg.viz3d import BrainSceneWindow  # noqa: PLC0415

    window = BrainSceneWindow(kg, ["GRN_sugar"], cloud=False, neuropils=False)
    try:
        window._filter_box.setText("GRN_sugar MN9")
        window._apply_filter()
        expected = set(kg.neurons_of("GRN_sugar")) | set(kg.neurons_of("MN9"))
        assert set(window._picks.neuron_ids) == expected
    finally:
        window.close()


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("NoSuchType", "NoSuchType"),
        # One good spec does not excuse a typo beside it: drawing GRN_sugar
        # alone would look like a scene containing both.
        ("GRN_sugar NoSuchType", "NoSuchType"),
    ],
)
def test_a_spec_matching_nothing_is_refused_and_the_scene_kept(qapp, kg, text, expected):
    from connectomekg.viz3d import BrainSceneWindow  # noqa: PLC0415

    window = BrainSceneWindow(kg, ["GRN_sugar"], cloud=False, neuropils=False)
    try:
        before_ids, before_title = list(window._picks.neuron_ids), window.windowTitle()
        window._filter_box.setText(text)
        window._apply_filter()
        assert window._picks.neuron_ids == before_ids
        assert window.windowTitle() == before_title
        assert window._specs == ["GRN_sugar"]
        shown = window._info_panel.toPlainText()
        assert "Cannot show that" in shown and expected in shown
    finally:
        window.close()


def test_a_spec_over_the_neuron_cap_is_refused_and_the_scene_kept(qapp, kg, monkeypatch):
    from connectomekg import scene as render3d  # noqa: PLC0415
    from connectomekg.viz3d import BrainSceneWindow  # noqa: PLC0415

    window = BrainSceneWindow(kg, ["GRN_sugar"], cloud=False, neuropils=False)
    try:
        before_ids = list(window._picks.neuron_ids)
        # The fixture has no type over the real cap, so lower the cap instead
        # of inventing a type: what is under test is the refusal, not the number.
        monkeypatch.setattr(render3d, "MAX_SCENE_NEURONS", 1)
        window._filter_box.setText("GRN_sugar")
        window._apply_filter()
        assert window._picks.neuron_ids == before_ids
        assert "over the cap" in window._info_panel.toPlainText()
    finally:
        window.close()


def test_clearing_the_box_draws_the_brain_alone(qapp, kg):
    from connectomekg.viz3d import BrainSceneWindow  # noqa: PLC0415

    window = BrainSceneWindow(kg, ["GRN_sugar"], cloud=False, neuropils=False)
    try:
        window._filter_box.setText("")
        window._apply_filter()
        assert len(window._picks) == 0
        assert window._specs == []
    finally:
        window.close()


def test_the_show_box_takes_an_answer(qapp, kg):
    from connectomekg.viz3d import BrainSceneWindow  # noqa: PLC0415

    window = BrainSceneWindow(kg, ["GRN_sugar"], cloud=False, neuropils=False)
    try:
        window._filter_box.setText("path:GRN_sugar>MN9")
        window._apply_filter()
        assert "path GRN_sugar to MN9" in window.windowTitle()
        # Hop-coloured, not type-coloured: the actors are named for the hops.
        names = set(window.plotter.renderer.actors)
        assert any("hop 0" in n for n in names) and any("hop 1" in n for n in names)
        # And the answer is still pickable.
        assert len(window._picks.neuron_ids) >= 2
    finally:
        window.close()


def test_the_show_box_goes_back_to_plain_specs(qapp, kg):
    from connectomekg.viz3d import BrainSceneWindow  # noqa: PLC0415

    window = BrainSceneWindow(kg, ["GRN_sugar"], cloud=False, neuropils=False)
    try:
        window._filter_box.setText("path:GRN_sugar>MN9")
        window._apply_filter()
        assert window._answer is not None
        window._filter_box.setText("MN9")
        window._apply_filter()
        assert window._answer is None, "a plain spec clears the answer"
        assert "path" not in window.windowTitle()
        assert set(window._picks.neuron_ids) == set(kg.neurons_of("MN9"))
    finally:
        window.close()


def test_an_unreachable_answer_keeps_the_scene(qapp, kg):
    from connectomekg.viz3d import BrainSceneWindow  # noqa: PLC0415

    window = BrainSceneWindow(kg, ["GRN_sugar"], cloud=False, neuropils=False)
    try:
        before = list(window._picks.neuron_ids)
        window._filter_box.setText("path:GRN_sugar>NoSuchType")
        window._apply_filter()
        assert window._picks.neuron_ids == before
        assert "no path" in window._info_panel.toPlainText()
    finally:
        window.close()


def test_the_window_can_open_on_an_answer(qapp, kg):
    from connectomekg.answers import answer_groups  # noqa: PLC0415
    from connectomekg.viz3d import BrainSceneWindow  # noqa: PLC0415

    answer = answer_groups(kg, "cone:GRN_sugar>1")
    window = BrainSceneWindow(kg, ["cone:GRN_sugar>1"], cloud=False, neuropils=False, answer=answer)
    try:
        assert "cone GRN_sugar down 1" in window.windowTitle()
        assert len(window._picks.neuron_ids) == len(answer)
    finally:
        window.close()
