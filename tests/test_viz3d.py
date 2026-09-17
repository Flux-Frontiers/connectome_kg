"""connectomekg.viz3d -- import only. No window opens in CI."""

from __future__ import annotations

import pytest


def test_module_imports_with_pyqt5_and_pyvistaqt_present():
    pytest.importorskip("PyQt5")
    pytest.importorskip("pyvistaqt")
    import connectomekg.viz3d  # noqa: F401, PLC0415 - the point of the test
