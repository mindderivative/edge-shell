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
