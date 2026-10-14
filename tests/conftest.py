import pytest

from shell.config.models import Config

THEME = {
    "frame": "#0b0c0d",
    "text": "#e6e8ea",
    "text_secondary": "#9ba0a6",
    "accent": "#8fd3b6",
    "handle": "#7b7f84",
    "handle_hover": "#e6e8ea",
    "surface_hover": "#1d2024",
    "thickness": 10,
    "radius": 14,
    "peek": 14,
    "hover_zone": 16,
    "duration_ms": 280,
    "font": ["Hack Nerd Font Mono", "JetBrains Mono", "monospace"],
}


@pytest.fixture
def make_config():
    def _make(monitors=None, theme=None) -> Config:
        return Config.model_validate(
            {"theme": {**THEME, **(theme or {})}, "monitors": monitors or {}}
        )

    return _make


from shell import registry
from shell.panel_spec import PanelDefaults


@pytest.fixture
def fake_registry(monkeypatch):
    monkeypatch.setattr(registry, "_WIDGETS", {})
    monkeypatch.setattr(registry, "_DEFAULTS", {})
    registry.register("dock", PanelDefaults(edge="bottom", length=560, depth=64, label="dock"))(
        type("Dock", (), {})
    )
    registry.register("clock", PanelDefaults(edge="top", length=168, depth=46, label="clock"))(
        type("Clock", (), {})
    )
    registry.register(
        "bar",
        PanelDefaults(edge="right", length=300, depth=56, pos=600, label="bar", state="collapsed"),
    )(type("Bar", (), {}))
    return registry


@pytest.fixture
def corner_registry(fake_registry):
    """fake_registry plus a corner widget "box" (spec 19): bottom-left, 300 x 390, opening from
    the bottom edge (its default), extended."""
    from shell.panel_spec import CornerDefaults

    fake_registry.register(
        "box", CornerDefaults(corner="bottom-left", width=300, height=390, label="box")
    )(type("Box", (), {}))
    return fake_registry
