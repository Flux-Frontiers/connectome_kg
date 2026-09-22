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
        assert window._inspector.isHidden()
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
        panel = window._examples.widget()
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
        panel = window._examples.widget()
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


def test_a_cast_keeps_the_viewport_s_view_angle(qapp, kg, monkeypatch):
    """The cast must be framed like the viewport, not at VTK's default 30 degrees.

    ``camera_position`` is (position, focal point, view up) and carries no
    view angle, so a fresh off-screen plotter keeps 30 while the viewport sits
    at the angle ``aim_camera`` framed with. That put the subject
    tan(15)/tan(7) = 2.2x too small on the panel. This drives the same
    sequence the cast helper does -- build, then assign ``camera_position`` --
    and checks the angle survives it.
    """
    import pyvista as pv  # noqa: PLC0415
    from kg_utils.viz3d.qt import CastResult  # noqa: PLC0415
    from PyQt5.QtWidgets import QMessageBox  # noqa: PLC0415

    from connectomekg import viz3d as mod  # noqa: PLC0415
    from connectomekg.viz3d import BrainSceneWindow  # noqa: PLC0415

    captured: dict[str, object] = {}

    def fake_cast(build, camera_position, out_stem, spec, **kwargs):
        captured["build"] = build
        captured["camera_position"] = camera_position
        return CastResult(path=None, error="not cast in tests", elapsed=0.0, message="ok")

    monkeypatch.setattr(mod, "cast_scene_to_looking_glass", fake_cast)
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))

    window = BrainSceneWindow(kg, ["GRN_sugar"], cloud=False, neuropils=False, floor=True)
    try:
        expected = window.plotter.camera.view_angle
        window._cast()
        offscreen = pv.Plotter(off_screen=True)
        try:
            assert offscreen.camera.view_angle != expected, "fixture must differ from the default"
            captured["build"](offscreen)
            offscreen.camera_position = captured["camera_position"]
            assert offscreen.camera.view_angle == expected
        finally:
            offscreen.close()
    finally:
        window.close()


def test_reset_view_reframes_after_an_orbit(qapp, kg):
    """Reset view re-aims at the scene, however far the camera has been dragged."""
    import numpy as np  # noqa: PLC0415

    from connectomekg.viz3d import BrainSceneWindow  # noqa: PLC0415

    window = BrainSceneWindow(kg, ["GRN_sugar"], cloud=False, neuropils=False)
    try:
        framed = np.asarray(window.plotter.camera_position[0], dtype=float)
        window.plotter.camera.azimuth = 55
        window.plotter.camera.zoom(3)
        moved = np.asarray(window.plotter.camera_position[0], dtype=float)
        assert not np.allclose(framed, moved), "the orbit must actually move the camera"

        window._reset_view()
        back = np.asarray(window.plotter.camera_position[0], dtype=float)
        assert np.allclose(back, framed, rtol=1e-6, atol=1e-6)
    finally:
        window.close()


def test_reset_view_says_so_when_there_is_nothing_framed(qapp, kg):
    from connectomekg.viz3d import BrainSceneWindow  # noqa: PLC0415

    window = BrainSceneWindow(kg, ["GRN_sugar"], cloud=False, neuropils=False)
    try:
        window._points = None
        window._reset_view()
        assert "Nothing to frame" in window.statusBar().currentMessage()
    finally:
        window.close()


def test_a_slow_step_shows_a_wait_cursor_and_always_restores_it(qapp, kg):
    """An override cursor that outlives its operation leaves the app looking hung."""
    import pytest  # noqa: PLC0415
    from PyQt5.QtCore import Qt  # noqa: PLC0415
    from PyQt5.QtWidgets import QApplication  # noqa: PLC0415

    from connectomekg.viz3d import BrainSceneWindow  # noqa: PLC0415

    window = BrainSceneWindow(kg, ["GRN_sugar"], cloud=False, neuropils=False)
    try:
        assert QApplication.overrideCursor() is None
        with window._busy("working..."):
            cursor = QApplication.overrideCursor()
            assert cursor is not None
            assert cursor.shape() == Qt.CursorShape.WaitCursor
            assert "working..." in window.statusBar().currentMessage()
        assert QApplication.overrideCursor() is None

        # And restored even when the slow step raises.
        with pytest.raises(RuntimeError), window._busy("failing..."):
            raise RuntimeError("boom")
        assert QApplication.overrideCursor() is None
    finally:
        window.close()


def test_composing_leaves_no_override_cursor_behind(qapp, kg):
    from PyQt5.QtWidgets import QApplication  # noqa: PLC0415

    from connectomekg.viz3d import BrainSceneWindow  # noqa: PLC0415

    window = BrainSceneWindow(kg, ["GRN_sugar"], cloud=False, neuropils=False)
    try:
        assert QApplication.overrideCursor() is None
        window._draw_example("MN9")
        assert QApplication.overrideCursor() is None
    finally:
        window.close()


def test_a_cast_reports_its_stages_in_the_status_bar(qapp, kg, monkeypatch):
    """The cast runs on the GUI thread, so it has to say what it is doing."""
    from kg_utils.viz3d.qt import CastResult  # noqa: PLC0415
    from PyQt5.QtWidgets import QMessageBox  # noqa: PLC0415

    from connectomekg import viz3d as mod  # noqa: PLC0415
    from connectomekg.viz3d import BrainSceneWindow  # noqa: PLC0415

    seen: list[str] = []

    def fake_cast(build, camera_position, out_stem, spec, *, progress=None, **kwargs):
        assert progress is not None, "the viewer must pass a progress sink"
        progress(1, 4, "building scene...")
        progress(4, 4, "handing to Bridge...")
        seen.append("called")
        return CastResult(path=None, error="not cast in tests", elapsed=0.0, message="done")

    monkeypatch.setattr(mod, "cast_scene_to_looking_glass", fake_cast)
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))

    window = BrainSceneWindow(kg, ["GRN_sugar"], cloud=False, neuropils=False)
    try:
        window._cast()
        assert seen == ["called"]
        assert window.statusBar().currentMessage() == "done"
    finally:
        window.close()


def test_reset_view_frames_the_subject_not_the_floor(qapp, kg):
    """aim_camera measures plotter.bounds, and the floor is a 120-unit plane.

    Framing with it in place fits the floor, and the subject shrinks to a
    speck -- so the floor comes off for the reframe and goes back after.
    """
    import numpy as np  # noqa: PLC0415

    from connectomekg.viz3d import BrainSceneWindow  # noqa: PLC0415

    window = BrainSceneWindow(kg, ["GRN_sugar"], cloud=False, neuropils=False, floor=True)
    try:
        framed = np.asarray(window.plotter.camera_position[0], dtype=float)
        focus = np.asarray(window.plotter.camera_position[1], dtype=float)
        subject_distance = float(np.linalg.norm(framed - focus))

        window.plotter.camera.azimuth = 40
        window._reset_view()

        back = np.asarray(window.plotter.camera_position[0], dtype=float)
        after = float(np.linalg.norm(back - np.asarray(window.plotter.camera_position[1])))
        assert after == pytest.approx(subject_distance, rel=1e-6), (
            "reset pulled the camera back to fit the floor"
        )
        assert np.allclose(back, framed, rtol=1e-6, atol=1e-6)
        assert "floor" in window.plotter.renderer.actors, "the floor must come back"
    finally:
        window.close()


def test_show_button_updates_scene_summary(qapp, kg):
    from connectomekg.viz3d import BrainSceneWindow  # noqa: PLC0415

    window = BrainSceneWindow(kg, ["GRN_sugar"], cloud=False, neuropils=False)
    try:
        window._filter_box.setText("MN9")
        window._show_button.click()
        assert window._specs == ["MN9"]
        assert window._scene_title.text() == "MN9"
        assert f"{len(kg.neurons_of('MN9'))} circuit neurons" in window._scene_stats.text()
        before = window._scene_stats.text()
        window._filter_box.setText("NoSuchType")
        window._show_button.click()
        assert window._scene_title.text() == "MN9"
        assert window._scene_stats.text() == before
    finally:
        window.close()


def test_collapsed_inspector_stays_closed_until_a_pick_or_error(qapp, kg):
    from connectomekg.viz3d import BrainSceneWindow  # noqa: PLC0415

    window = BrainSceneWindow(kg, ["GRN_sugar"], cloud=False, neuropils=False)
    try:
        window._inspect_button.click()
        assert window._inspector.isHidden()
        window._draw_example("MN9")
        assert window._inspector.isHidden()
        window._on_pick(window._picks.points[0])
        assert not window._inspector.isHidden()
        assert window._inspect_button.isChecked()
        window._inspect_button.click()
        window._draw_example("NoSuchType")
        assert not window._inspector.isHidden()
        assert window._inspect_button.isChecked()
        assert "Cannot show that" in window._info_panel.toPlainText()
    finally:
        window.close()


def test_flow_errors_can_be_read_and_dismissed(qapp, kg):
    from connectomekg.viz3d import BrainSceneWindow  # noqa: PLC0415

    window = BrainSceneWindow(kg, [], view="flow", cloud=False, neuropils=False)
    try:
        assert "flow arcs" in window._scene_stats.text()
        window._draw_example("NoSuchType")
        assert not window._inspector.isHidden()
        assert not window._inspect_button.isHidden()
        window._inspect_button.click()
        assert window._inspector.isHidden()
    finally:
        window.close()


def test_automatic_cloud_survives_other_display_edits(qapp, kg):
    from PyQt5.QtCore import Qt  # noqa: PLC0415

    from connectomekg.viz3d import BrainSceneWindow  # noqa: PLC0415

    window = BrainSceneWindow(kg, ["GRN_sugar"], cloud=None, neuropils=False)
    try:
        assert window._toggles["cloud"].checkState() == Qt.CheckState.PartiallyChecked
        assert any(name.startswith("context") for name in window.plotter.renderer.actors)
        window._toggles["tubes"].setChecked(True)
        assert window._cloud is None
        assert any(name.startswith("context") for name in window.plotter.renderer.actors)
        window._toggles["cloud"].setCheckState(Qt.CheckState.Unchecked)
        assert window._cloud is False
        assert not any(name.startswith("context") for name in window.plotter.renderer.actors)
    finally:
        window.close()


def test_stride_edit_applies_once_and_keeps_camera(qapp, kg, monkeypatch):
    from connectomekg.viz3d import BrainSceneWindow  # noqa: PLC0415

    window = BrainSceneWindow(kg, ["GRN_sugar"], cloud=False, neuropils=False)
    try:
        calls = []
        monkeypatch.setattr(window, "_compose", lambda *a, **kw: calls.append(kw))
        window._stride.setValue(9)
        window._stride.editingFinished.emit()
        assert window._skeleton_step == 9
        assert calls == [{"keep_camera": True}]
        window._stride.editingFinished.emit()
        assert len(calls) == 1
    finally:
        window.close()


def test_busy_disables_scene_actions_and_restores_them_on_error(qapp, kg):
    from connectomekg.viz3d import BrainSceneWindow  # noqa: PLC0415

    window = BrainSceneWindow(kg, ["GRN_sugar"], cloud=False, neuropils=False)
    try:
        with pytest.raises(RuntimeError), window._busy("working"):
            assert not window._show_button.isEnabled()
            assert not window._cast_button.isEnabled()
            assert not window._save_button.isEnabled()
            assert not window._reset_button.isEnabled()
            assert not window.plotter.isEnabled()
            raise RuntimeError("test failure")
        assert window._show_button.isEnabled()
        assert window._cast_button.isEnabled()
        assert window._reset_button.isEnabled()
        assert window.plotter.isEnabled()
    finally:
        window.close()


def test_laptop_layout_keeps_actions_visible_and_examples_scrollable(qapp, kg):
    from PyQt5.QtCore import QPoint  # noqa: PLC0415

    from connectomekg.viz3d import BrainSceneWindow  # noqa: PLC0415

    window = BrainSceneWindow(
        kg, ["GRN_sugar"], cloud=False, neuropils=False, width=1024, height=640
    )
    try:
        window.show()
        qapp.processEvents()
        assert window.width() == 1024
        assert window.height() == 640
        assert window.plotter.width() > window._controls_panel.width() * 2
        assert window.plotter.height() > 250
        for widget in (
            window._filter_box,
            window._show_button,
            window._cast_button,
            window._reset_button,
            window._inspect_button,
        ):
            top_left = widget.mapTo(window, QPoint(0, 0))
            bottom_right = widget.mapTo(window, widget.rect().bottomRight())
            assert window.rect().contains(top_left)
            assert window.rect().contains(bottom_right)
            assert widget.isVisible()
        scrollbar = window._examples.verticalScrollBar()
        assert scrollbar.maximum() > 0
        scrollbar.setValue(scrollbar.maximum())
        assert window._cast_button.isVisible()
    finally:
        window.close()


def test_geometry_counts_mesh_instances_but_not_hidden_meshes_or_text(qapp, kg, monkeypatch):
    import pyvista as pv  # noqa: PLC0415

    from connectomekg.viz3d import BrainSceneWindow  # noqa: PLC0415

    window = BrainSceneWindow(kg, [], cloud=False, neuropils=False)
    try:
        window.plotter.clear()
        triangle = pv.PolyData([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)], [3, 0, 1, 2])
        window.plotter.add_mesh(triangle, name="skeleton:first")
        window.plotter.add_mesh(triangle, name="skeleton:second")
        window.plotter.add_mesh(pv.Line(), name="flow:line")
        hidden = window.plotter.add_mesh(pv.Sphere(), name="hidden")
        hidden.visibility = False
        window.plotter.add_text("Not geometry", name="annotation")
        monkeypatch.setattr("connectomekg.viz3d.perf_counter", lambda: 102.5)
        window._update_geometry_stats(100.0)
        assert window._geometry_stats.text() == (
            "Geometry: 3 meshes  |  8 points  |  3 cells  |  Scene build: 2.50 s"
        )
        detail = window._geometry_stats.toolTip()
        assert "skeleton: 2 meshes, 6 points, 2 cells" in detail
        assert "flow: 1 meshes, 2 points, 1 cells" in detail
        assert "hidden:" not in detail
        assert "annotation:" not in detail
    finally:
        window.close()


def test_geometry_summary_follows_overlays_and_survives_rejected_specs(qapp, kg):
    from connectomekg.viz3d import BrainSceneWindow  # noqa: PLC0415

    window = BrainSceneWindow(kg, ["GRN_sugar"], cloud=False, neuropils=False)
    try:
        initial = window._geometry_stats.text().split("Scene build:")[0]
        window._toggles["cloud"].setChecked(True)
        assert window._geometry_stats.text().split("Scene build:")[0] != initial
        assert "context:" in window._geometry_stats.toolTip()
        window._toggles["floor"].setChecked(True)
        assert "floor:" in window._geometry_stats.toolTip()
        before = window._geometry_stats.text()
        window._draw_example("NoSuchType")
        assert window._geometry_stats.text() == before
        window._toggles["cloud"].setChecked(False)
        window._toggles["floor"].setChecked(False)
        assert window._geometry_stats.text().split("Scene build:")[0] == initial
        assert "context:" not in window._geometry_stats.toolTip()
        assert "floor:" not in window._geometry_stats.toolTip()
    finally:
        window.close()


@pytest.mark.parametrize("typed", ["label:giant fib", '"label:giant fib"', r"label:giant\s+fib"])
def test_label_specs_reach_the_resolver_intact(qapp, kg, monkeypatch, typed):
    from connectomekg.viz3d import BrainSceneWindow  # noqa: PLC0415

    window = BrainSceneWindow(kg, ["GRN_sugar"], cloud=False, neuropils=False)
    try:
        expected = typed.strip('"')
        real_resolver = kg.neurons_of
        calls = []

        def resolve(spec):
            calls.append(spec)
            return real_resolver("GRN_sugar") if spec == expected else []

        monkeypatch.setattr(kg, "neurons_of", resolve)
        window._draw_example(typed)
        assert window._specs == [expected]
        assert set(calls) == {expected}
    finally:
        window.close()


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", []),
        ("LC4 DNp01", ["LC4", "DNp01"]),
        ("label:giant fib", ["label:giant fib"]),
        ("label:Kenyon's cell", ["label:Kenyon's cell"]),
        ('"label:giant fib" DNp01', ["label:giant fib", "DNp01"]),
        (r'LC4 "label:\bgiant\s+fib"', ["LC4", r"label:\bgiant\s+fib"]),
        ('"label:neuron #1" LC4', ["label:neuron #1", "LC4"]),
    ],
)
def test_show_input_preserves_regexes_and_supports_quoted_unions(qapp, text, expected):
    from connectomekg.viz3d import _split_specs  # noqa: PLC0415

    assert _split_specs(text) == expected


def test_unfinished_quote_keeps_scene_and_explains_the_error(qapp, kg):
    from connectomekg.viz3d import BrainSceneWindow  # noqa: PLC0415

    window = BrainSceneWindow(kg, ["GRN_sugar"], cloud=False, neuropils=False)
    try:
        window._draw_example('"label:giant fib')
        assert window._specs == ["GRN_sugar"]
        assert "quotation" in window._info_panel.toPlainText()
    finally:
        window.close()


def test_initial_specs_with_label_spaces_round_trip_through_show(qapp, kg, monkeypatch):
    from connectomekg.viz3d import BrainSceneWindow  # noqa: PLC0415

    real_resolver = kg.neurons_of
    monkeypatch.setattr(
        kg, "neurons_of", lambda s: real_resolver("GRN_sugar" if s == "label:giant fib" else s)
    )
    window = BrainSceneWindow(kg, ["label:giant fib", "MN9"], cloud=False, neuropils=False)
    try:
        before = set(window._picks.neuron_ids)
        window._show_button.click()
        assert window._specs == ["label:giant fib", "MN9"]
        assert set(window._picks.neuron_ids) == before
    finally:
        window.close()


def _accept_save(monkeypatch, path):
    """Make the save dialog answer ``path`` and the result boxes stay silent."""
    from PyQt5.QtWidgets import QFileDialog, QMessageBox  # noqa: PLC0415

    boxes: list[str] = []
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(path), "PNG"))
    )
    monkeypatch.setattr(
        QMessageBox, "information", staticmethod(lambda *a, **k: boxes.append("information"))
    )
    monkeypatch.setattr(
        QMessageBox, "warning", staticmethod(lambda *a, **k: boxes.append("warning"))
    )
    return boxes


def test_save_image_writes_a_still_named_by_the_spec(qapp, kg, monkeypatch, tmp_path):
    """Save > Image renders one still the way ``quilt --still`` does, at 4K by default."""
    pytest.importorskip("quiltwright")
    from connectomekg import viz3d as mod  # noqa: PLC0415
    from connectomekg.viz3d import BrainSceneWindow  # noqa: PLC0415

    monkeypatch.setattr(mod, "STILL_HEIGHT", 120)
    boxes = _accept_save(monkeypatch, tmp_path / "scene.png")
    window = BrainSceneWindow(kg, ["GRN_sugar"], cloud=False, neuropils=False)
    try:
        window._save_image()
        written = list(tmp_path.glob("scene_qs1x1a*.png"))
        assert len(written) == 1 and written[0].stat().st_size > 0
        assert window.statusBar().currentMessage() == f"Wrote {written[0]}"
        assert boxes == ["information"]
    finally:
        window.close()


def test_save_quilt_writes_the_preset_s_quilt_without_casting(qapp, kg, monkeypatch, tmp_path):
    """Save > Quilt is the cast's file without the Bridge call; nothing reaches Bridge."""
    quiltwright = pytest.importorskip("quiltwright")
    from kg_utils.viz3d import qt as sdk_qt  # noqa: PLC0415

    from connectomekg.viz3d import BrainSceneWindow  # noqa: PLC0415

    # A 1/20-scale preset keeps the 48 views cheap while staying a real render.
    monkeypatch.setitem(
        quiltwright.QUILT_PRESETS, "tiny", quiltwright.QUILT_PRESETS["16-landscape"].scaled(0.05)
    )
    monkeypatch.setattr(
        sdk_qt, "cast_scene_to_looking_glass", lambda *a, **k: pytest.fail("must not cast")
    )
    boxes = _accept_save(monkeypatch, tmp_path / "out" / "scene.png")
    window = BrainSceneWindow(kg, ["GRN_sugar"], cloud=False, neuropils=False, preset="tiny")
    try:
        window._save_quilt()
        written = list((tmp_path / "out").glob("scene_qs8x6a*.png"))
        assert len(written) == 1 and written[0].stat().st_size > 0
        assert boxes == ["information"]
    finally:
        window.close()


def test_cancelling_the_save_dialog_writes_nothing(qapp, kg, monkeypatch, tmp_path):
    pytest.importorskip("quiltwright")
    from connectomekg.viz3d import BrainSceneWindow  # noqa: PLC0415

    boxes = _accept_save(monkeypatch, "")
    window = BrainSceneWindow(kg, ["GRN_sugar"], cloud=False, neuropils=False)
    try:
        before = window.statusBar().currentMessage()
        window._save_image()
        assert not list(tmp_path.iterdir())
        assert window.statusBar().currentMessage() == before
        assert boxes == []
    finally:
        window.close()


def test_a_failed_save_is_reported_and_leaves_the_viewer_usable(qapp, kg, monkeypatch, tmp_path):
    quiltwright = pytest.importorskip("quiltwright")
    from connectomekg.viz3d import BrainSceneWindow  # noqa: PLC0415

    def boom(*_a, **_k):
        raise RuntimeError("no GPU today")

    monkeypatch.setattr(quiltwright, "render_quilt", boom)
    boxes = _accept_save(monkeypatch, tmp_path / "scene.png")
    window = BrainSceneWindow(kg, ["GRN_sugar"], cloud=False, neuropils=False)
    try:
        window._save_image()
        assert boxes == ["warning"]
        assert "Save failed: no GPU today" in window.statusBar().currentMessage()
        assert window._save_button.isEnabled() and window._cast_button.isEnabled()
        assert not list(tmp_path.glob("*.png"))
    finally:
        window.close()
