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


def test_the_window_builds_with_pyvista_off_screen_set(qapp, kg, monkeypatch):
    """A window with no interactor still builds, and can still be asked a pick.

    ``pyvista.OFF_SCREEN`` leaves ``QtInteractor.iren`` as ``None``, and
    ``enable_point_picking`` raises on it. CI runs in exactly that state --
    pyvista's headless-display action exports ``PYVISTA_OFF_SCREEN`` -- and a
    developer's machine does not, so 21 tests passed locally and failed there.
    """
    pyvista = pytest.importorskip("pyvista")
    from connectomekg.viz3d import BrainSceneWindow  # noqa: PLC0415

    monkeypatch.setattr(pyvista, "OFF_SCREEN", True)
    window = BrainSceneWindow(kg, ["GRN_sugar"], cloud=False, neuropils=False)
    try:
        assert window.plotter.iren is None
        point = window._picks.points[window._picks.owner == 0][0]
        window._on_pick(point)
        assert "Inputs:" in window._info_panel.toPlainText()
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
        # Hop-colored, not type-colored: the actors are named for the hops.
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


def test_the_controls_toggle_what_the_scene_draws(qapp, kg):
    from connectomekg.viz3d import BrainSceneWindow  # noqa: PLC0415

    window = BrainSceneWindow(kg, ["GRN_sugar"], cloud=False, neuropils=False)
    try:

        def kinds():
            return {name.split(":")[0] for name in window.plotter.renderer.actors}

        assert "context" not in kinds()
        window._toggles["cloud"].setChecked(True)
        assert "context" in kinds(), "the cloud is composed, not merely shown"
        window._toggles["cloud"].setChecked(False)
        assert "context" not in kinds()

        window._toggles["floor"].setChecked(True)
        assert "floor" in kinds()
        window._toggles["floor"].setChecked(False)
        assert "floor" not in kinds()
    finally:
        window.close()


def test_the_stride_control_zero_means_automatic(qapp, kg):
    from connectomekg.scene import auto_skeleton_step  # noqa: PLC0415
    from connectomekg.viz3d import BrainSceneWindow  # noqa: PLC0415

    window = BrainSceneWindow(kg, ["GRN_sugar"], cloud=False, neuropils=False)
    try:
        assert window._stride.value() == 0
        assert window._skeleton_step is None
        window._stride.setValue(9)
        window._on_toggle()
        assert window._skeleton_step == 9
        window._stride.setValue(0)
        window._on_toggle()
        assert window._skeleton_step is None
        # And the automatic choice is the one the scene would make.
        assert auto_skeleton_step(len(window._picks.neuron_ids)) >= 4
    finally:
        window.close()


def test_min_syn_narrows_a_cone_answer(qapp, kg, monkeypatch):
    from connectomekg import answers as answers_mod  # noqa: PLC0415
    from connectomekg.viz3d import BrainSceneWindow  # noqa: PLC0415

    window = BrainSceneWindow(kg, ["GRN_sugar"], cloud=False, neuropils=False)
    try:
        # A cap the cone exceeds at min_syn 1 (78 neurons) but not once it is
        # raised (6, the seed alone), so min_syn is what brings it back under.
        monkeypatch.setattr(answers_mod, "MAX_SCENE_NEURONS", 10)
        window._filter_box.setText("cone:GRN_sugar>1")
        window._apply_filter()
        assert "over the cap of 10" in window._info_panel.toPlainText()

        window._min_syn.setValue(10_000)
        window._apply_filter()
        assert "cone GRN_sugar down 1" in window.windowTitle()
    finally:
        window.close()


def test_the_controls_offer_every_example_as_a_button(qapp, kg):
    from PyQt5.QtWidgets import QPushButton  # noqa: PLC0415

    from connectomekg.answers import (  # noqa: PLC0415
        ANSWER_EXAMPLES,
        SPEC_EXAMPLES,
        circuit_examples,
    )
    from connectomekg.viz3d import BrainSceneWindow  # noqa: PLC0415

    window = BrainSceneWindow(kg, ["GRN_sugar"], cloud=False, neuropils=False)
    try:
        panel = window._controls_dock.widget()
        texts = [b.text() for b in panel.findChildren(QPushButton)]
        buttons = {b.text(): b for b in panel.findChildren(QPushButton)}
        documented = (*circuit_examples(), *SPEC_EXAMPLES, *ANSWER_EXAMPLES)
        for example, _ in documented:
            assert example in buttons, example
        # circuit:compass documents the form in the spec grammar and is also
        # one of the circuits; that is two lines of help but one button.
        assert len(texts) == len(set(texts)), "an example was offered twice"
        for example, button in buttons.items():
            meanings = {m for e, m in documented if e == example}
            # The meaning is not lost by dropping the help text: it is the tooltip.
            assert button.toolTip() in meanings, example
    finally:
        window.close()


def test_clicking_an_example_fills_the_box_and_applies_it(qapp, kg):
    """A button takes the typed path, refusals included.

    Every documented example names v783 cell types, which the synthetic
    fixture does not have, so the click is expected to be refused -- and the
    refusal is the proof that the button went through ``_apply_filter``
    rather than drawing something on its own.
    """
    from PyQt5.QtWidgets import QPushButton  # noqa: PLC0415

    from connectomekg.viz3d import BrainSceneWindow  # noqa: PLC0415

    window = BrainSceneWindow(kg, ["GRN_sugar"], cloud=False, neuropils=False)
    try:
        before_title = window.windowTitle()
        panel = window._controls_dock.widget()
        button = next(b for b in panel.findChildren(QPushButton) if b.text() == "circuit:compass")
        button.click()
        assert window._filter_box.text() == "circuit:compass"
        assert window.windowTitle() == before_title  # scene kept
        assert "Cannot show that" in window._info_panel.toPlainText()
    finally:
        window.close()


def test_an_example_that_resolves_is_drawn(qapp, kg):
    """The same path with a spec the fixture does have actually redraws."""
    from connectomekg.viz3d import BrainSceneWindow  # noqa: PLC0415

    window = BrainSceneWindow(kg, ["GRN_sugar"], cloud=False, neuropils=False)
    try:
        window._draw_example("MN9")
        assert window._filter_box.text() == "MN9"
        assert window._specs == ["MN9"]
        assert set(window._picks.neuron_ids) == set(kg.neurons_of("MN9"))
    finally:
        window.close()


def test_a_toggle_keeps_the_camera_where_the_viewer_put_it(qapp, kg):
    """Toggling an overlay changes what is drawn, not what is being looked at."""
    import numpy as np  # noqa: PLC0415

    from connectomekg.viz3d import BrainSceneWindow  # noqa: PLC0415

    window = BrainSceneWindow(kg, ["GRN_sugar"], cloud=False, neuropils=False)
    try:
        window.plotter.camera.azimuth = 55
        window.plotter.camera.elevation = 20
        rotated = np.array(window.plotter.camera_position.to_list())

        for key in ("floor", "neuropils", "cloud", "tubes"):
            window._toggles[key].setChecked(not window._toggles[key].isChecked())
            now = np.array(window.plotter.camera_position.to_list())
            assert np.allclose(now, rotated), f"{key} moved the camera"
    finally:
        window.close()


def test_a_new_subject_is_reframed(qapp, kg):
    """A camera framed on one spec may not contain the next, so it is re-aimed."""
    import numpy as np  # noqa: PLC0415

    from connectomekg.viz3d import BrainSceneWindow  # noqa: PLC0415

    window = BrainSceneWindow(kg, ["GRN_sugar"], cloud=False, neuropils=False)
    try:
        window.plotter.camera.azimuth = 55
        rotated = np.array(window.plotter.camera_position.to_list())
        window._filter_box.setText("MN9")
        window._apply_filter()
        assert not np.allclose(np.array(window.plotter.camera_position.to_list()), rotated)
    finally:
        window.close()
