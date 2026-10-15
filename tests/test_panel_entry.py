"""A panel entry's own keys (panel/widget spec 3.1-3.2): panel, name and the widget keys."""

import pytest
from pydantic import ValidationError

from shell.config.models import (
    FRAMEWORK_KEYS,
    PANEL_KINDS,
    Config,
    ConfigError,
    PanelConfig,
)


def mon(*panels):
    return {"HDMI-A-1": {"shell": "edge", "panels": list(panels)}}


def problems(registry, make_config, *panels) -> str:
    with pytest.raises(ConfigError) as exc:
        registry.validate_widgets(make_config(monitors=mon(*panels)))
    return str(exc.value)


def test_the_panel_kinds_are_edge_corner_and_float():
    assert PANEL_KINDS == ("edge", "corner", "float")
    assert PanelConfig(panel="corner", name="Box", widget="box").panel == "corner"
    with pytest.raises(ValidationError) as exc:
        PanelConfig(panel="side", name="Box", widget="box")
    assert exc.value.errors()[0]["loc"] == ("panel",)


@pytest.mark.parametrize("name", ["Clock", "x", "C" * 40, "Uhr · oben", "Dock 2"])
def test_a_name_may_be_any_text_of_1_to_40_characters(name):
    assert PanelConfig(panel="edge", name=name, widget="dock").name == name


@pytest.mark.parametrize(
    ("name", "words"),
    [
        ("\u200bClock", "invisible"),  # zero-width space at the start
        ("Clock\u200b", "invisible"),  # ... and at the end
        ("\ufeffClock", "invisible"),  # a byte-order mark
        ("Clock\u202e", "bidirectional"),  # right-to-left override
        ("Cl\u202eock", "bidirectional"),  # ... anywhere
        ("Cl\u2067ock", "bidirectional"),  # an isolate
        ("Clock\u2028x", "line or paragraph separator"),
        ("Clock\u2029x", "line or paragraph separator"),
    ],
)
def test_a_name_rejects_invisible_format_characters(name, words):
    with pytest.raises(ValidationError) as exc:
        PanelConfig(panel="edge", name=name, widget="dock")
    assert words in exc.value.errors()[0]["msg"]


def test_a_zero_width_joiner_in_the_middle_is_fine():
    name = "\U0001f468\u200d\U0001f469 home"  # an emoji sequence
    assert PanelConfig(panel="edge", name=name, widget="dock").name == name


@pytest.mark.parametrize(
    ("name", "words"),
    [
        ("", "at least 1 character"),
        ("C" * 41, "at most 40 characters"),
        ("Clock\n", "control characters"),
        ("a\tb", "control characters"),
        (" Clock", "must not start or end with whitespace"),
        ("Clock ", "must not start or end with whitespace"),
        ("\u00a0Clock", "must not start or end with whitespace"),  # a no-break space too
    ],
)
def test_a_bad_name_names_the_key_path(make_config, name, words):
    with pytest.raises(ValidationError) as exc:
        make_config(monitors=mon({"panel": "edge", "name": name, "widget": "dock"}))
    error = exc.value.errors()[0]
    assert error["loc"] == ("monitors", "HDMI-A-1", "panels", 0, "name")
    assert words in error["msg"]


def test_every_other_key_is_a_widget_key():
    p = PanelConfig.model_validate(
        {"panel": "edge", "name": "Clock", "widget": "clock", "edge": "top", "format": "HH:mm"}
    )
    assert p.widget_props == {"format": "HH:mm"}
    assert (p.edge, p.name) == ("top", "Clock")


def test_a_key_called_widget_props_is_a_widget_key_too():
    p = PanelConfig.model_validate(
        {"panel": "edge", "name": "clock", "widget": "clock", "widget_props": {"format": "HH"}}
    )
    assert p.widget_props == {"widget_props": {"format": "HH"}}


def test_the_widget_bag_is_not_nested_when_built_from_file_data():
    file_shaped = {"panel": "edge", "name": "Clock", "widget": "clock", "format": "HH"}
    p = PanelConfig.model_validate(file_shaped)
    assert p.widget_props == {"format": "HH"}
    # dump-then-validate is not idempotent: the dumped bag is a widget key of the next entry
    again = PanelConfig.model_validate(p.model_dump(exclude_none=True))
    assert "widget_props" in again.widget_props


def test_the_framework_keys_are_the_model_fields():
    assert set(PanelConfig.model_fields) == FRAMEWORK_KEYS | {"widget_props"}


def test_the_schema_offers_panel_and_name():
    props = Config.model_json_schema()["$defs"]["PanelConfig"]["properties"]

    def first(prop):  # an optional key is anyOf [..., null]
        return prop.get("anyOf", [prop])[0]

    assert first(props["panel"])["enum"] == list(PANEL_KINDS)
    name = first(props["name"])
    assert (name["minLength"], name["maxLength"]) == (1, 40)


def test_float_panels_are_rejected_for_now(corner_registry, make_config):
    text = problems(corner_registry, make_config, {"panel": "float", "name": "F", "widget": "box"})
    assert "monitors.HDMI-A-1.panels[0].panel: float panels are not implemented yet" in text


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        (
            {"panel": "corner", "name": "C", "widget": "clock"},
            "monitors.HDMI-A-1.panels[0].panel: clock cannot be shown in a corner panel "
            "(it supports: edge)",
        ),
        (
            {"panel": "edge", "name": "B", "widget": "box"},
            "monitors.HDMI-A-1.panels[0].panel: box cannot be shown in an edge panel "
            "(it supports: corner)",
        ),
    ],
)
def test_a_widget_on_a_kind_it_does_not_support_is_rejected(
    corner_registry, make_config, entry, message
):
    assert message in problems(corner_registry, make_config, entry)


def test_names_must_be_unique_per_monitor(fake_registry, make_config):
    text = problems(
        fake_registry,
        make_config,
        {"panel": "edge", "name": "Clock", "widget": "clock"},
        {"panel": "edge", "name": "Dock", "widget": "dock"},
        {"panel": "edge", "name": "clock", "widget": "clock"},  # case-sensitive: allowed
        {"panel": "edge", "name": "Clock", "widget": "clock", "edge": "bottom"},
    )
    assert (
        "monitors.HDMI-A-1.panels[3].name: names must be unique: 'Clock' is used by "
        "panels[0] and panels[3]"
    ) in text
    assert "panels[2]" not in text


def test_the_same_name_on_two_monitors_is_fine(fake_registry, make_config):
    entry = {"panel": "edge", "name": "Clock", "widget": "clock"}
    monitors = {"A": {"panels": [entry]}, "B": {"panels": [entry]}}
    fake_registry.validate_widgets(make_config(monitors=monitors))


def test_a_widget_key_the_widget_does_not_have_is_rejected(fake_registry, make_config):
    text = problems(
        fake_registry, make_config, {"panel": "edge", "name": "D", "widget": "dock", "format": "x"}
    )
    assert "monitors.HDMI-A-1.panels[0].format: unknown key for widget 'dock'" in text


def test_a_complete_entry_passes(corner_registry, make_config):
    corner_registry.validate_widgets(
        make_config(
            monitors=mon(
                {"panel": "edge", "name": "Dock", "widget": "dock", "align": "end"},
                {"panel": "corner", "name": "Box", "widget": "box", "corner": "top-left"},
            )
        )
    )
