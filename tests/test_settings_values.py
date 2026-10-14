"""settings.values: the value each field shows and where it comes from (pure)."""

import pytest

from settings.form import config_form
from settings.values import (
    PLACEMENT_DEFAULT,
    FieldValue,
    field_value,
    layout_preview,
    lookup,
    monitor_names,
    new_panel_entry,
    panel_ops,
    unique_name,
)
from shell.config.models import ConfigError
from shell.outputs import Output
from shell.registry import validate_widgets

USER = {
    "theme": {"accent": "#112233", "border": {"width": 3}},
    "monitors": {
        "HDMI-A-1": {
            "shell": "edge",
            "theme": {"accent": "#d3a68f"},
            "panels": [
                {
                    "panel": "edge",
                    "name": "dock",
                    "widget": "dock",
                    "depth": 80,
                    "handle": {"shape": "bar"},
                },
                {"panel": "edge", "name": "bar", "widget": "bar", "interaction": {"hover": False}},
            ],
        }
    },
}


@pytest.fixture
def config(make_config, fake_registry):
    return make_config(theme=USER["theme"], monitors=USER["monitors"])


def test_lookup():
    assert lookup(USER, ("theme", "accent")) == (True, "#112233")
    assert lookup(USER, ("monitors", "HDMI-A-1", "panels", 1, "widget")) == (True, "bar")
    assert lookup(USER, ("monitors", "HDMI-A-1", "panels", 5, "widget")) == (False, None)
    assert lookup(USER, ("theme", "accent", "x")) == (False, None)
    assert lookup({}, ("layout", "gap")) == (False, None)


def test_global_theme(config):
    assert field_value(config, USER, ("theme", "accent")) == FieldValue(
        "#112233", True, "your config"
    )
    assert field_value(config, USER, ("theme", "frame")) == FieldValue("#0b0c0d", False, "default")
    assert field_value(config, USER, ("theme", "border", "width")).value == 3
    assert field_value(config, USER, ("theme", "border", "enabled")) == FieldValue(
        False, False, "default"
    )
    assert field_value(config, USER, ("layout", "gap")) == FieldValue(8, False, "default")


def test_monitor_mode(config):
    assert field_value(config, USER, ("monitors", "HDMI-A-1", "shell")).value == "edge"
    assert field_value(config, USER, ("monitors", "DP-1", "shell")) == FieldValue(
        "plasma", False, "default"
    )


def test_monitor_theme_override_inherits_the_global_theme(config):
    mon = ("monitors", "HDMI-A-1", "theme")
    assert field_value(config, USER, (*mon, "accent")) == FieldValue("#d3a68f", True, "your config")
    assert field_value(config, USER, (*mon, "border", "width")) == FieldValue(
        3, False, "global theme"
    )
    assert field_value(config, USER, ("monitors", "HDMI-A-1", "layout", "gap")) == FieldValue(
        8, False, "global layout"
    )


def test_panel_keys_fall_back_to_the_widget_defaults(config):
    p0 = ("monitors", "HDMI-A-1", "panels", 0)
    p1 = ("monitors", "HDMI-A-1", "panels", 1)
    assert field_value(config, USER, (*p0, "depth")) == FieldValue(80, True, "your config")
    assert field_value(config, USER, (*p0, "edge")) == FieldValue("bottom", False, "widget default")
    length = field_value(config, USER, (*p0, "length"))
    assert (length.value, length.default) == (560, 560)
    assert field_value(config, USER, (*p1, "state")).value == "collapsed"
    assert field_value(config, USER, (*p1, "pos")) == FieldValue(600, False, "widget default")
    assert field_value(config, USER, (*p0, "min_length")) == FieldValue(None, False, "not set")
    assert field_value(config, USER, (*p0, "widget")) == FieldValue("dock", True, "your config")


def test_placement_defaults_once_align_or_offset_is_set(make_config, fake_registry):
    """Placement is taken as a whole: setting align on the bar drops its default pos 600 (as
    setting align on system_bar drops its offset 142); the rows say why."""
    user = {
        "monitors": {
            "M": {"panels": [{"panel": "edge", "name": "bar", "widget": "bar", "align": "end"}]}
        }
    }
    config = make_config(monitors=user["monitors"])
    p = ("monitors", "M", "panels", 0)
    assert field_value(config, user, (*p, "align")) == FieldValue("end", True, "your config")
    assert field_value(config, user, (*p, "offset")) == FieldValue(0, False, PLACEMENT_DEFAULT)
    assert field_value(config, user, (*p, "pos")) == FieldValue(None, False, PLACEMENT_DEFAULT)
    assert PLACEMENT_DEFAULT == "placement default (align/offset set)"


CORNERS_USER = {
    "monitors": {
        "M": {
            "panels": [
                {"panel": "corner", "name": "box", "widget": "box"},
                {
                    "panel": "corner",
                    "name": "box 2",
                    "widget": "box",
                    "corner": "top-right",
                    "width": 200,
                    "handle": {"size": 9},
                },
                {"panel": "edge", "name": "dock", "widget": "dock"},
            ]
        }
    }
}


@pytest.fixture
def corners(make_config, corner_registry):
    return make_config(monitors=CORNERS_USER["monitors"])


def test_corner_panel_values(corners):
    p0, p1 = ("monitors", "M", "panels", 0), ("monitors", "M", "panels", 1)
    u = CORNERS_USER
    assert field_value(corners, u, (*p0, "corner")) == FieldValue(
        "bottom-left", False, "widget default"
    )
    assert field_value(corners, u, (*p0, "edge")) == FieldValue("bottom", False, "corner default")
    assert field_value(corners, u, (*p0, "height")) == FieldValue(390, False, "widget default")
    assert field_value(corners, u, (*p0, "state")).value == "extended"
    assert field_value(corners, u, (*p1, "corner")) == FieldValue("top-right", True, "your config")
    assert field_value(corners, u, (*p1, "edge")) == FieldValue("top", False, "corner default")
    assert field_value(corners, u, (*p1, "width")) == FieldValue(200, True, "your config")
    assert field_value(corners, u, (*p1, "handle", "size")) == FieldValue(9, True, "your config")
    assert field_value(corners, u, (*p0, "align")) == FieldValue(
        None, False, "not used by corner panels"
    )
    assert field_value(corners, u, ("monitors", "M", "panels", 2, "width")) == FieldValue(
        None, False, "not used by edge panels"
    )


def test_every_panel_form_field_has_a_value(corners):
    """Every row of both panel sections, on every entry of either kind: a value, no KeyError
    (the view refreshes every row it built)."""
    form = config_form(("bar", "box", "clock", "dock"), corner_widgets=("box",))

    def paths(section, prefix):
        for spec in section.fields:
            yield (*prefix, spec.key)
        for sub in section.sections:
            yield from paths(sub, (*prefix, sub.key))

    for index in range(3):
        for kind in ("edge", "corner"):
            for path in paths(form.panel_for(kind), ("monitors", "M", "panels", index)):
                assert isinstance(field_value(corners, CORNERS_USER, path), FieldValue), path


@pytest.mark.parametrize(
    "entry, key, value, ops",
    [
        ({"panel": "edge", "name": "dock", "widget": "dock"}, "depth", 80, [("set", "depth", 80)]),
        (  # an edge widget becomes a corner widget: its edge-only keys go in the same edit
            {
                "panel": "edge",
                "name": "dock",
                "widget": "dock",
                "align": "end",
                "length": 300,
                "edge": "left",
                "state": "collapsed",
            },
            "widget",
            "box",
            [
                ("set", "widget", "box"),
                ("set", "panel", "corner"),
                ("unset", "align", None),
                ("unset", "length", None),
            ],
        ),
        (  # ... and its edge too, when that is not an edge of the corner it lands in
            {"panel": "edge", "name": "dock", "widget": "dock", "edge": "top"},
            "widget",
            "box",
            [("set", "widget", "box"), ("set", "panel", "corner"), ("unset", "edge", None)],
        ),
        (  # a corner widget becomes an edge widget
            {
                "panel": "corner",
                "name": "box",
                "widget": "box",
                "corner": "top-left",
                "width": 200,
                "edge": "left",
            },
            "widget",
            "dock",
            [
                ("set", "widget", "dock"),
                ("set", "panel", "edge"),
                ("unset", "corner", None),
                ("unset", "width", None),
            ],
        ),
        (  # a new corner without the entry's edge
            {"panel": "corner", "name": "box", "widget": "box", "edge": "left"},
            "corner",
            "top-right",
            [("set", "corner", "top-right"), ("unset", "edge", None)],
        ),
        (
            {"panel": "corner", "name": "box", "widget": "box", "edge": "left"},
            "corner",
            "top-left",
            [("set", "corner", "top-left")],
        ),
    ],
)
def test_panel_ops_keep_the_entry_valid(corner_registry, entry, key, value, ops):
    assert panel_ops(entry, key, value) == ops


def test_a_widget_for_both_kinds_keeps_the_entrys_kind(corner_registry):
    from shell.panel_spec import CornerDefaults, PanelDefaults
    from shell.widget import Widget

    corner_registry.register_widget(
        "both",
        title="Both",
        edge=PanelDefaults(edge="top", length=100, depth=40, label="both"),
        corner=CornerDefaults(corner="top-left", width=200, height=100, label="both"),
    )(type("Both", (Widget,), {}))
    corner = {"panel": "corner", "name": "x", "widget": "box"}
    edge = {"panel": "edge", "name": "x", "widget": "dock"}
    assert panel_ops(corner, "widget", "both") == [("set", "widget", "both")]
    assert panel_ops(edge, "widget", "both") == [("set", "widget", "both")]
    assert new_panel_entry({}, "M", "both")["panel"] == "edge"  # edge before corner


def test_layout_preview_reports_corner_panels(make_config, corner_registry):
    two = make_config(
        monitors={
            "M": {
                "panels": [
                    {"panel": "corner", "name": "box", "widget": "box"},
                    {"panel": "corner", "name": "box 2", "widget": "box"},
                ]
            }
        }
    )
    (warning,) = layout_preview(two, "M", 1920, 1080)
    assert "the bottom-left corner already holds monitors.M.panels.0" in warning
    wide = make_config(
        monitors={
            "M": {"panels": [{"panel": "corner", "name": "box", "widget": "box", "width": 2000}]}
        }
    )
    (warning,) = layout_preview(wide, "M", 1920, 1080)
    assert "width 2000 px does not fit the bottom edge; shrunk to" in warning


def test_panel_handle_and_interaction(config):
    p0 = ("monitors", "HDMI-A-1", "panels", 0)
    p1 = ("monitors", "HDMI-A-1", "panels", 1)
    assert field_value(config, USER, (*p0, "handle", "shape")) == FieldValue(
        "bar", True, "your config"
    )
    assert field_value(config, USER, (*p0, "handle", "size")) == FieldValue(15, False, "theme")
    # the panel's monitor theme (accent override does not touch the handle colours)
    assert field_value(config, USER, (*p0, "handle", "color")) == FieldValue(
        "#7b7f84", False, "theme"
    )
    assert field_value(config, USER, (*p0, "handle", "hover_color")).value == "#e6e8ea"
    assert field_value(config, USER, (*p0, "handle", "offset")) == FieldValue(
        0, False, "widget default"
    )
    assert field_value(config, USER, (*p1, "interaction", "hover")) == FieldValue(
        False, True, "your config"
    )
    assert field_value(config, USER, (*p1, "interaction", "click")) == FieldValue(
        True, False, "default"
    )


def test_unknown_paths_are_errors(config):
    with pytest.raises(KeyError):
        field_value(config, USER, ("nope",))
    with pytest.raises(KeyError):
        field_value(config, USER, ("monitors", "HDMI-A-1", "nope"))


def test_monitor_names_lists_connected_then_configured(make_config):
    config = make_config(monitors={"eDP-1": {"shell": "edge"}, "HDMI-A-1": {"shell": "edge"}})
    outputs = [Output("HDMI-A-1", 0, 0, 1920, 1080), Output("DP-1", 0, 1080, 1920, 1080)]
    assert monitor_names(config, outputs) == [
        ("HDMI-A-1", True),
        ("DP-1", True),
        ("eDP-1", False),
    ]
    assert monitor_names(config, []) == [("HDMI-A-1", False), ("eDP-1", False)]


def test_layout_preview_reports_what_the_shell_would(make_config, fake_registry):
    clean = make_config(
        monitors={
            "HDMI-A-1": {
                "shell": "edge",
                "panels": [{"panel": "edge", "name": "dock", "widget": "dock"}],
            }
        }
    )
    assert layout_preview(clean, "HDMI-A-1", 1920, 1080) == []
    too_long = make_config(
        monitors={
            "HDMI-A-1": {
                "shell": "edge",
                "panels": [{"panel": "edge", "name": "dock", "widget": "dock", "length": 3000}],
            }
        }
    )
    warnings = layout_preview(too_long, "HDMI-A-1", 1920, 1080)
    assert len(warnings) == 1 and warnings[0].startswith("monitors.HDMI-A-1")
    assert layout_preview(too_long, "HDMI-A-1", 3840, 2160) == []


def _applied(entry, ops):
    """The entry after the ops (what the document would hold)."""
    out = dict(entry)
    for op, key, value in ops:
        if op == "set":
            out[key] = value
        else:
            out.pop(key, None)
    return out


def _valid(make_config, entry):
    validate_widgets(make_config(monitors={"M": {"panels": [entry]}}))


def test_every_edge_only_key_goes_when_the_widget_becomes_a_corner_widget(
    make_config, corner_registry
):
    full = {
        "panel": "edge",
        "name": "dock",
        "widget": "dock",
        "align": "end",
        "offset": 4,
        "order": 1,
        "length": 300,
        "min_length": 100,
        "max_length": 900,
        "depth": 80,
    }
    result = _applied(full, panel_ops(full, "widget", "box"))
    assert result == {"panel": "corner", "name": "dock", "widget": "box"}  # the name stays
    _valid(make_config, result)
    pos = {"panel": "edge", "name": "dock", "widget": "dock", "pos": 300, "edge": "left"}
    result = _applied(pos, panel_ops(pos, "widget", "box"))
    assert result == {
        "panel": "corner",
        "name": "dock",
        "widget": "box",
        "edge": "left",
    }  # left is an edge of bottom-left
    _valid(make_config, result)


def test_corner_keys_go_when_the_widget_becomes_an_edge_widget(make_config, corner_registry):
    full = {
        "panel": "corner",
        "name": "box",
        "widget": "box",
        "corner": "top-left",
        "width": 200,
        "height": 100,
        "edge": "left",
    }
    result = _applied(full, panel_ops(full, "widget", "dock"))
    assert result == {"panel": "edge", "name": "box", "widget": "dock", "edge": "left"}
    _valid(make_config, result)


def test_an_unknown_widget_is_a_plain_set_for_the_session_to_reject(corner_registry):
    assert panel_ops(
        {"panel": "edge", "name": "dock", "widget": "dock", "depth": 80}, "widget", "nope"
    ) == [("set", "widget", "nope")]


RESET = """\
[monitors.M]
shell = "edge"

[[monitors.M.panels]]
panel = "corner"
name = "box"
widget = "box"
corner = "top-right"
edge = "right"
"""


def test_resetting_a_corner_keeps_the_entry_valid(tmp_path, corner_registry):
    pytest.importorskip("tomlkit")
    from settings.session import SettingsSession

    path = tmp_path / "config.toml"
    path.write_text(RESET)
    session = SettingsSession(path)
    entry = session.user["monitors"]["M"]["panels"][0]
    ops = panel_ops(entry, "corner", None)
    assert ops == [("unset", "corner", None), ("unset", "edge", None)]
    base = ("monitors", "M", "panels", 0)

    def edit(doc) -> None:
        for op, key, value in ops:
            doc.unset((*base, key)) if op == "unset" else doc.set((*base, key), value)

    config = session.apply(edit)
    assert len(session.history) == 1 and path.read_text() == session.text
    assert session.user["monitors"]["M"]["panels"] == [
        {"panel": "corner", "name": "box", "widget": "box"}
    ]
    assert field_value(config, session.user, (*base, "corner")) == FieldValue(
        "bottom-left", False, "widget default"
    )
    edge = field_value(config, session.user, (*base, "edge"))
    assert (edge.value, edge.is_set, edge.source) == ("bottom", False, "corner default")


def test_resetting_a_corner_that_holds_the_edge_unsets_only_the_corner(corner_registry):
    entry = {
        "panel": "corner",
        "name": "box",
        "widget": "box",
        "corner": "top-right",
        "edge": "top",
    }
    assert panel_ops(entry, "corner", None) == [("unset", "corner", None), ("unset", "edge", None)]
    entry = {
        "panel": "corner",
        "name": "box",
        "widget": "box",
        "corner": "top-right",
        "edge": "left",
    }  # bottom-left has left
    assert panel_ops(entry, "corner", None) == [("unset", "corner", None)]


def test_an_unknown_widget_row_is_rejected_by_the_session(tmp_path, corner_registry):
    pytest.importorskip("tomlkit")
    from settings.session import SettingsSession

    path = tmp_path / "config.toml"
    path.write_text(RESET)
    session = SettingsSession(path)
    ops = panel_ops(session.user["monitors"]["M"]["panels"][0], "widget", "nope")
    with pytest.raises(ConfigError):
        session.apply(lambda doc: doc.set(("monitors", "M", "panels", 0, "widget"), "nope"))
    assert ops == [("set", "widget", "nope")] and session.text == RESET


def test_order_is_labelled_default_and_has_no_widget_default(make_config, fake_registry):
    config = make_config(
        monitors={"M": {"panels": [{"panel": "edge", "name": "dock", "widget": "dock"}]}}
    )
    p = ("monitors", "M", "panels", 0)
    assert field_value(config, {}, (*p, "order")) == FieldValue(0, False, "default")
    assert field_value(config, {}, (*p, "order")).default is None


def test_handle_shape_with_every_interaction_off_says_nothing_is_drawn(make_config, fake_registry):
    user = {
        "monitors": {
            "M": {
                "panels": [
                    {
                        "panel": "edge",
                        "name": "dock",
                        "widget": "dock",
                        "interaction": {"click": False, "hover": False, "drag": False},
                    }
                ]
            }
        }
    }
    config = make_config(monitors=user["monitors"])
    p = ("monitors", "M", "panels", 0)
    shape = field_value(config, user, (*p, "handle", "shape"))
    assert shape.value == "auto" and shape.source == "none (all interactions off)"
    # another handle key keeps the plain theme label
    assert field_value(config, user, (*p, "handle", "size")).source == "theme"


def test_pos_center_shows_what_the_file_says(make_config, fake_registry):
    user = {
        "monitors": {
            "M": {"panels": [{"panel": "edge", "name": "bar", "widget": "bar", "pos": "center"}]}
        }
    }
    config = make_config(monitors=user["monitors"])
    p = ("monitors", "M", "panels", 0)
    assert field_value(config, user, (*p, "pos")) == FieldValue("center", True, "your config")


def test_unique_name_numbers_a_taken_name():
    assert unique_name("Clock", []) == "Clock"
    assert unique_name("Clock", ["Clock"]) == "Clock 2"
    assert unique_name("Clock", ["Clock", "Clock 2", "Clock 4"]) == "Clock 3"
    assert unique_name("Clock", ["clock"]) == "Clock"  # names are case-sensitive


def test_a_new_panel_entry_has_its_kind_and_a_free_name(corner_registry):
    user = {
        "monitors": {
            "M": {
                "panels": [
                    {"panel": "edge", "name": "dock", "widget": "dock"},
                    {"panel": "edge", "name": "dock 2", "widget": "dock"},
                ]
            }
        }
    }
    assert new_panel_entry(user, "M", "dock") == {
        "panel": "edge",
        "name": "dock 3",
        "widget": "dock",
    }
    assert new_panel_entry(user, "M", "box") == {"panel": "corner", "name": "box", "widget": "box"}
    assert new_panel_entry(user, "N", "dock")["name"] == "dock"  # another monitor: free
    assert new_panel_entry({}, "M", "nope") == {"panel": "edge", "name": "nope", "widget": "nope"}
