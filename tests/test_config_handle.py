"""Config keys for handle customization and per-interaction toggles (spec 15)."""

import pytest
from pydantic import ValidationError

from shell.config.loader import load_config, parse_config
from shell.config.models import (
    HANDLE_SHAPES,
    Config,
    ConfigError,
    HandleConfig,
    InteractionConfig,
    PanelConfig,
)


def one_panel(**entry):
    return {
        "HDMI-A-1": {
            "shell": "edge",
            "panels": [{"panel": "edge", "name": "dock", "widget": "dock", **entry}],
        }
    }


def test_defaults_change_nothing(make_config):
    cfg = make_config()
    style = cfg.theme.handle_style
    assert (style.shape, style.size, style.weight) == ("auto", 15, 3)
    panel = PanelConfig(panel="edge", name="dock", widget="dock")
    assert panel.handle == HandleConfig() and panel.interaction == InteractionConfig()
    assert all(v is None for v in panel.handle.model_dump().values())
    assert all(v is None for v in panel.interaction.model_dump().values())


def test_shapes_offered_to_the_settings_window():
    assert HANDLE_SHAPES == ("auto", "dots", "bar", "chevron", "none")


def test_a_full_handle_and_interaction_entry(make_config):
    cfg = make_config(
        monitors=one_panel(
            handle={
                "shape": "chevron",
                "size": 24,
                "weight": 4,
                "offset": -120,
                "color": "#FF8800",
                "hover_color": "#ffffff80",
            },
            interaction={"click": True, "hover": False, "drag": False},
        )
    )
    panel = cfg.monitor("HDMI-A-1").panels[0]
    assert panel.handle.model_dump() == {
        "shape": "chevron",
        "size": 24,
        "weight": 4,
        "offset": -120,
        "color": "#ff8800",  # normalised like every theme colour
        "hover_color": "#ffffff80",
    }
    assert (panel.interaction.click, panel.interaction.hover, panel.interaction.drag) == (
        True,
        False,
        False,
    )


@pytest.mark.parametrize(
    ("table", "key", "value", "kind"),
    [
        ("handle", "shape", "star", "literal_error"),
        ("handle", "size", 3, "greater_than_equal"),
        ("handle", "size", 41, "less_than_equal"),
        ("handle", "weight", 0, "greater_than_equal"),
        ("handle", "weight", 9, "less_than_equal"),
        ("handle", "offset", 2001, "less_than_equal"),
        ("handle", "color", "red", "value_error"),
        ("handle", "hover_color", "#fff", "value_error"),
        ("handle", "colour", "#ffffff", "extra_forbidden"),
        ("interaction", "click", "yes", "bool_type"),
        ("interaction", "drag", 1, "bool_type"),
        ("interaction", "peek", True, "extra_forbidden"),
    ],
)
def test_bad_values_name_the_key_path(make_config, table, key, value, kind):
    with pytest.raises(ValidationError) as exc:
        make_config(monitors=one_panel(**{table: {key: value}}))
    (error,) = exc.value.errors()
    assert error["loc"] == ("monitors", "HDMI-A-1", "panels", 0, table, key)
    assert error["type"] == kind


def test_an_unknown_shape_lists_the_known_ones(make_config):
    data = make_config().model_dump()
    data["monitors"] = one_panel(handle={"shape": "star"})
    with pytest.raises(ConfigError) as exc:
        parse_config(data)
    assert str(exc.value) == (
        "monitors.HDMI-A-1.panels[0].handle.shape: "
        "Input should be 'auto', 'dots', 'bar', 'chevron' or 'none'"
    )


def test_theme_handle_style_per_monitor_merges_key_by_key(make_config):
    cfg = make_config(
        theme={"handle_style": {"shape": "bar", "size": 30}},
        monitors={"A": {"theme": {"handle_style": {"size": 20}}}},
    )
    a, other = cfg.theme_for("A").handle_style, cfg.theme_for("B").handle_style
    assert (a.shape, a.size, a.weight) == ("bar", 20, 3)
    assert (other.shape, other.size, other.weight) == ("bar", 30, 3)
    with pytest.raises(ValidationError, match=r"monitors\.A\.theme: handle_style\.size"):
        make_config(monitors={"A": {"theme": {"handle_style": {"size": 99}}}})


def test_toml_dotted_keys_and_the_default_file(tmp_path):
    user = tmp_path / "config.toml"
    user.write_text(
        "[monitors.HDMI-A-1]\n"
        'shell = "edge"\n'
        "[[monitors.HDMI-A-1.panels]]\n"
        'panel = "edge"\nname = "dock"\nwidget = "dock"\n'
        'handle.shape = "bar"\n'
        'handle.color = "#8fd3b6"\n'
        "interaction.hover = false\n",
        encoding="utf-8",
    )
    cfg = load_config(user, required=True)
    panel = cfg.monitor("HDMI-A-1").panels[0]
    assert (panel.handle.shape, panel.handle.color, panel.handle.size) == ("bar", "#8fd3b6", None)
    assert (panel.interaction.hover, panel.interaction.click) == (False, None)
    style = cfg.theme.handle_style  # from config.default.toml
    assert (style.shape, style.size, style.weight) == ("auto", 15, 3)


def test_the_json_schema_describes_the_new_tables():
    schema = Config.model_json_schema()
    defs = schema["$defs"]
    assert set(defs["HandleConfig"]["properties"]) == {
        "shape",
        "size",
        "weight",
        "offset",
        "color",
        "hover_color",
    }
    assert set(defs["InteractionConfig"]["properties"]) == {"click", "hover", "drag"}
    assert defs["HandleStyle"]["properties"]["shape"]["enum"] == list(HANDLE_SHAPES)
