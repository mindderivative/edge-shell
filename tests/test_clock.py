from datetime import datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

gi = pytest.importorskip("gi")
pytest.importorskip("fabric")

import widgets.clock as ck  # noqa: E402
import widgets.system_bar as sb  # noqa: E402
from shell import registry  # noqa: E402
from shell.config.models import ConfigError  # noqa: E402
from shell.theme import label_font_css  # noqa: E402
from widgets.clock import REFRESH_MS, ClockProps, format_time  # noqa: E402


def test_format_is_24h_zero_padded():
    assert format_time(datetime(2026, 1, 2, 3, 4, 59)) == "03:04"
    assert format_time(datetime(2026, 1, 2, 23, 59, 0)) == "23:59"


def test_refresh_is_fast_enough_for_minute_rollover():
    assert REFRESH_MS <= 1000


@pytest.mark.parametrize("module, cls", [(ck, "ClockWidget"), (sb, "SystemBarWidget")])
def test_destroy_stops_the_timer_once(monkeypatch, module, cls):
    removed = []
    monkeypatch.setattr(module.GLib, "source_remove", removed.append)
    widget = getattr(module, cls)()
    widget._repeater_id = 9
    widget.destroy()
    widget.destroy()
    assert removed == [9] and widget._destroyed
    assert widget._refresh() is False  # a refresh already queued does nothing


# ---- properties (panel/widget spec 3.4) ---------------------------------------------


def test_the_clock_registers_its_properties():
    assert registry.widget_props_model("clock") is ClockProps
    assert ClockProps() == ClockProps(format="HH:mm", font=None, font_size=None)


@pytest.mark.parametrize(
    ("keys", "words"),
    [
        ({"format": "%Y"}, "unknown token 'Y'"),
        ({"format": ""}, "at least 1 character"),
        ({"font": 'Hack"; } * { color: red'}, "must not contain a double quote"),
        ({"font": ""}, "at least 1 character"),
        ({"font_size": 5}, "greater than or equal to 6"),
        ({"font_size": 97}, "less than or equal to 96"),
    ],
)
def test_bad_properties_are_refused(keys, words):
    with pytest.raises(ValidationError, match=words):
        ClockProps(**keys)


def test_the_length_limits_are_inclusive():
    ClockProps(format="H" * 64, font="x" * 100)
    for keys, words in (({"format": "H" * 65}, "at most 64"), ({"font": "x" * 101}, "at most 100")):
        with pytest.raises(ValidationError, match=words):
            ClockProps(**keys)


def test_bad_properties_name_the_key_path_in_a_config(make_config):
    entry = {"panel": "edge", "name": "Clock", "widget": "clock", "format": "HH:MM:SS"}
    with pytest.raises(ConfigError) as exc:
        registry.validate_widgets(make_config(monitors={"HDMI-A-1": {"panels": [entry]}}))
    assert "monitors.HDMI-A-1.panels[0].format: Value error, unknown token 'S'" in str(exc.value)


def test_the_label_font_css():
    assert label_font_css(None, None) == ""
    assert label_font_css("Hack", None) == 'label { font-family: "Hack"; }'
    assert label_font_css(None, 14) == "label { font-size: 14pt; }"  # points
    assert label_font_css("monospace", 9) == "label { font-family: monospace; font-size: 9pt; }"


def test_the_refresh_uses_the_format(monkeypatch):
    monkeypatch.setattr(ck, "datetime", SimpleNamespace(now=lambda: datetime(2026, 1, 2, 21, 7)))
    w = ck.ClockWidget()
    w._parts = ck.parse_clock_format("h:mm a")
    w._time = SimpleNamespace(text="", get_label=lambda: "", set_label=lambda t: sets.append(t))
    sets = []
    assert w._refresh() is True and sets == ["9:07 PM"]


# ---- the built label (plain Gtk widgets, no window) ---------------------------------


@pytest.fixture
def gtk():
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk

    if not Gtk.init_check()[0]:
        pytest.skip("no display")
    return Gtk


def build(monkeypatch, props):
    monkeypatch.setattr(ck, "datetime", SimpleNamespace(now=lambda: datetime(2026, 1, 2, 9, 5, 7)))
    widget = ck.ClockWidget()
    box = widget.build(props)
    widget.destroy()  # no timer left behind
    return box, widget._time


def test_the_built_label_shows_the_format(gtk, monkeypatch):
    _box, label = build(monkeypatch, ClockProps(format="ddd HH:mm:ss"))
    assert label.get_label() == "Fri 09:05:07"


def test_font_and_size_reach_the_label(gtk, monkeypatch):
    _box, label = build(monkeypatch, ClockProps(font="Hack Nerd Font Mono", font_size=30))
    from gi.repository import Pango

    font = label.get_style_context().get_property("font", gtk.StateFlags.NORMAL)
    assert font.get_family() == "Hack Nerd Font Mono"
    assert font.get_size() / Pango.SCALE == 30  # points


def test_without_font_properties_the_label_keeps_the_theme_font(gtk, monkeypatch):
    added = []
    monkeypatch.setattr(
        gtk.StyleContext, "add_provider", lambda self, p, prio: added.append(prio), raising=True
    )
    build(monkeypatch, ClockProps())
    assert added == []
    build(monkeypatch, ClockProps(font_size=12))
    assert added == [ck.FONT_PRIORITY] and ck.FONT_PRIORITY > gtk.STYLE_PROVIDER_PRIORITY_USER
