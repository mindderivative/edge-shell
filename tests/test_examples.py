"""Every example config loads with the real widgets (panel/widget spec 3.6)."""

from pathlib import Path

import pytest

pytest.importorskip("gi")
pytest.importorskip("fabric")

import widgets  # noqa: E402, F401  (registers the built-in widgets)
from shell.config.loader import load_config  # noqa: E402
from shell.config.store import ConfigStore  # noqa: E402

EXAMPLES = sorted((Path(__file__).resolve().parents[1] / "examples").glob("*.toml"))


def test_there_are_examples():
    assert len(EXAMPLES) >= 9


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_every_example_is_valid(path):
    config = ConfigStore(path, required=True).config  # the loader plus validate_widgets
    for monitor in config.monitors.values():
        names = [p.name for p in monitor.panels]
        assert len(names) == len(set(names)), path.name
        assert all(p.panel in ("edge", "corner") for p in monitor.panels), path.name


def test_the_default_config_has_no_panels():
    assert all(not m.panels for m in load_config(None).monitors.values())
