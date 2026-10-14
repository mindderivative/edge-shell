"""Every registered widget builds the panel class its registration kind promises."""

import pytest

pytest.importorskip("gi")
pytest.importorskip("fabric")

import widgets  # noqa: E402,F401  (registers the built-in widgets)
from shell import registry  # noqa: E402
from shell.corner_panel import CornerPanel  # noqa: E402


def test_every_corner_widget_builds_a_corner_panel():
    assert registry.widget_names()
    for name in registry.widget_names():
        is_corner = issubclass(registry.widget_class(name), CornerPanel)
        assert is_corner == (registry.widget_kind(name) == "corner"), name
