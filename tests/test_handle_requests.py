"""Handle and interaction choices travel from the config entry (over the widget's defaults)
into the PanelRequest; changing them is an in-place reload, never a rebuild (spec 15)."""

import pytest

from shell.config.diff import Change, diff_configs
from shell.config.models import PanelConfig
from shell.panel_layout import layout_monitor
from shell.panel_spec import HandleSpec, Interaction, PanelDefaults
from shell.widget import Widget


@pytest.fixture
def grip(fake_registry):
    """A widget whose defaults set a handle and turn hover off."""
    fake_registry.register_widget(
        "grip",
        title="Grip",
        edge=PanelDefaults(
            edge="left",
            length=200,
            depth=40,
            label="grip",
            handle=HandleSpec(shape="bar", size=30, color="#112233"),
            interaction=Interaction(hover=False),
        ),
    )(type("Grip", (Widget,), {}))
    return fake_registry


def test_requests_default_to_the_theme_and_every_interaction(fake_registry):
    req = fake_registry.request_for(PanelConfig(panel="edge", name="dock", widget="dock"))
    assert req.handle == HandleSpec() and req.interaction == Interaction()
    assert (req.interaction.click, req.interaction.hover, req.interaction.drag) == (
        True,
        True,
        True,
    )


def test_entry_keys_win_over_the_widget_defaults_key_by_key(grip):
    req = grip.request_for(
        PanelConfig(
            panel="edge",
            name="grip",
            widget="grip",
            handle={"size": 20, "offset": -30, "hover_color": "#ffffff"},
            interaction={"click": False},
        )
    )
    assert req.handle == HandleSpec(
        shape="bar", size=20, weight=None, offset=-30, color="#112233", hover_color="#ffffff"
    )
    assert req.interaction == Interaction(click=False, hover=False, drag=True)
    plain = grip.request_for(PanelConfig(panel="edge", name="grip", widget="grip"))
    assert plain.handle == HandleSpec(shape="bar", size=30, color="#112233")
    assert plain.interaction == Interaction(hover=False)


def test_the_layout_ignores_the_handle(fake_registry):
    a = fake_registry.request_for(PanelConfig(panel="edge", name="dock", widget="dock"))
    b = fake_registry.request_for(
        PanelConfig(
            panel="edge",
            name="dock",
            widget="dock",
            handle={"shape": "chevron"},
            interaction={"drag": False},
        )
    )
    one = layout_monitor([a], 1920, 1080, 10, 14, 8).panels
    two = layout_monitor([b], 1920, 1080, 10, 14, 8).panels
    assert one == two


def mon(*panels, theme=None):
    return {"HDMI-A-1": {"shell": "edge", "panels": list(panels), "theme": theme or {}}}


@pytest.mark.parametrize(
    "entry",
    [
        {"handle": {"shape": "bar"}},
        {"handle": {"offset": 40}},
        {"handle": {"color": "#ff0000"}},
        {"interaction": {"hover": False}},
        {"interaction": {"click": False, "drag": False}},
        {"handle": {"size": 30}, "state": "collapsed"},
    ],
)
def test_handle_and_interaction_changes_update_in_place(fake_registry, make_config, entry):
    old = make_config(
        monitors=mon(
            {"panel": "edge", "name": "dock", "widget": "dock"},
            {"panel": "edge", "name": "clock", "widget": "clock"},
        )
    )
    new = make_config(
        monitors=mon(
            {"panel": "edge", "name": "dock", "widget": "dock"},
            {"panel": "edge", "name": "clock", "widget": "clock", **entry},
        )
    )
    assert diff_configs(old, new) == [Change("panel-handle", "HDMI-A-1", 1)]


def test_a_handle_change_with_a_geometry_change_rebuilds(fake_registry, make_config):
    old = make_config(monitors=mon({"panel": "edge", "name": "dock", "widget": "dock"}))
    new = make_config(
        monitors=mon(
            {
                "panel": "edge",
                "name": "dock",
                "widget": "dock",
                "depth": 80,
                "handle": {"shape": "bar"},
            }
        )
    )
    assert diff_configs(old, new) == [Change("panel-rebuild", "HDMI-A-1", 0)]


@pytest.mark.parametrize(
    "theme",
    [
        {"handle_style": {"shape": "chevron"}},
        {"handle_style": {"weight": 5}},
        {"handle": "#ff0000"},
        {"handle_hover": "#00ff00"},
    ],
)
def test_theme_handle_changes_are_a_restyle(fake_registry, make_config, theme):
    old = make_config(monitors=mon({"panel": "edge", "name": "dock", "widget": "dock"}))
    new = make_config(
        monitors=mon({"panel": "edge", "name": "dock", "widget": "dock"}), theme=theme
    )
    assert diff_configs(old, new) == [Change("restyle", "HDMI-A-1")]


@pytest.mark.parametrize(
    "bad",
    [
        {"handle": HandleSpec(shape="star")},
        {"handle": HandleSpec(size=99)},
        {"handle": HandleSpec(color="red")},
        {"interaction": Interaction(click="yes")},
    ],
)
def test_bad_widget_defaults_fail_at_registration(fake_registry, bad):
    defaults = PanelDefaults(edge="left", length=200, depth=40, label="bad", **bad)
    with pytest.raises(ValueError, match="widget 'bad': invalid handle or interaction default"):
        fake_registry.register_widget("bad", title="Bad", edge=defaults)
    assert "bad" not in fake_registry.widget_names()


def test_all_off_paths_list_the_panels_only_state_opens(grip, make_config):
    off = {"click": False, "hover": False, "drag": False}
    cfg = make_config(
        monitors=mon(
            {"panel": "edge", "name": "dock", "widget": "dock"},
            {"panel": "edge", "name": "clock", "widget": "clock", "interaction": off},
            {
                "panel": "edge",
                "name": "grip",
                "widget": "grip",
                "interaction": {"click": False, "drag": False},
            },  # hover: widget
            {
                "panel": "edge",
                "name": "grip 2",
                "widget": "grip",
                "interaction": {"click": False},
            },  # drag still on
        )
    )
    assert grip.all_off_paths(cfg) == ["monitors.HDMI-A-1.panels.1", "monitors.HDMI-A-1.panels.2"]
    assert (
        grip.all_off_paths(
            make_config(monitors=mon({"panel": "edge", "name": "dock", "widget": "dock"}))
        )
        == []
    )


@pytest.fixture
def mute(fake_registry):
    """A widget whose defaults turn every interaction off."""
    fake_registry.register_widget(
        "mute",
        title="Mute",
        edge=PanelDefaults(
            edge="left",
            length=200,
            depth=40,
            label="mute",
            interaction=Interaction(click=False, hover=False, drag=False),
        ),
    )(type("Mute", (Widget,), {}))
    return fake_registry


def test_all_off_paths_skip_an_entry_that_re_enables_a_flag(mute, make_config):
    cfg = make_config(
        monitors=mon(
            {"panel": "edge", "name": "mute", "widget": "mute", "interaction": {"click": True}}
        )
    )
    assert mute.all_off_paths(cfg) == []


def test_all_off_paths_list_a_widget_that_is_all_off_by_default(mute, make_config):
    cfg = make_config(monitors=mon({"panel": "edge", "name": "mute", "widget": "mute"}))
    assert mute.all_off_paths(cfg) == ["monitors.HDMI-A-1.panels.0"]


def test_all_off_paths_skip_an_unknown_widget(fake_registry, make_config):
    cfg = make_config(monitors=mon({"panel": "edge", "name": "nope", "widget": "nope"}))
    assert fake_registry.all_off_paths(cfg) == []
