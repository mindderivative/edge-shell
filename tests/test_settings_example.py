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


def test_the_real_widgets_make_a_form_and_the_clock_has_its_widget_rows():
    from settings.form import config_form, registry_widgets

    form = config_form(registry_widgets())
    widget = form.edge_panel.field("widget")
    assert widget.labels == ("Clock", "Dock", "Summary", "System bar")
    clock = form.widget_props("clock")
    assert [(f.key, f.kind) for f in clock.fields] == [
        ("format", "text"),
        ("font", "text"),
        ("font_size", "int"),
    ]
    assert (clock.field("font_size").minimum, clock.field("font_size").maximum) == (6, 96)
    assert clock.field("format").hint.startswith("HH mm ss")
    assert clock.field("font_size").hint.startswith("pt")  # the size is in points
    assert all(form.widget_props(w) is None for w in ("dock", "summary", "system_bar"))
