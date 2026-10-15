"""The gate example config is valid with the real widgets and edits keep its comments."""

from pathlib import Path

import pytest

pytest.importorskip("gi")
pytest.importorskip("fabric")
pytest.importorskip("tomlkit")

import widgets  # noqa: E402, F401  (registers the built-in panels)
from settings.document import UserDocument  # noqa: E402
from settings.session import check_text  # noqa: E402

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "settings-test.toml"


def test_the_settings_example_is_valid_and_keeps_its_comments():
    text = EXAMPLE.read_text()
    config = check_text(text)
    assert [p.widget for p in config.monitor("HDMI-A-1").panels] == [
        "dock",
        "clock",
        "system_bar",
    ]
    assert config.monitor("DP-1").shell == "plasma"  # never edge (Phil tests on HDMI-A-1)
    doc = UserDocument(text)
    doc.set(("theme", "accent"), "#d3a68f")
    assert "# mint" in doc.text and 'accent = "#d3a68f"' in doc.text
