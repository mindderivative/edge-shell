import pytest
from pydantic import ValidationError

from shell.config.models import PanelConfig


def test_valid_minimal(make_config):
    cfg = make_config()
    assert cfg.theme.thickness == 10
    assert cfg.monitors == {}


def test_hex_color_normalized_to_lowercase(make_config):
    assert make_config(theme={"frame": "#0B0C0D"}).theme.frame == "#0b0c0d"


def test_bad_color_rejected_with_key_path(make_config):
    with pytest.raises(ValidationError) as exc:
        make_config(theme={"frame": "red"})
    assert exc.value.errors()[0]["loc"] == ("theme", "frame")


def test_unknown_key_rejected(make_config):
    with pytest.raises(ValidationError) as exc:
        make_config(theme={"bogus": 1})
    assert exc.value.errors()[0]["loc"] == ("theme", "bogus")


@pytest.mark.parametrize(
    ("theme", "field"),
    [
        ({"thickness": 0}, "thickness"),
        ({"radius": 0}, "radius"),
        ({"thickness": 9999}, "thickness"),
        ({"duration_ms": -1}, "duration_ms"),
    ],
)
def test_theme_bounds(make_config, theme, field):
    with pytest.raises(ValidationError) as exc:
        make_config(theme=theme)
    assert exc.value.errors()[0]["loc"] == ("theme", field)


@pytest.mark.parametrize(
    ("panel", "field"),
    [
        ({"widget": "dock", "length": 0}, "length"),
        ({"widget": "dock", "depth": -5}, "depth"),
        ({"widget": "dock", "length": 999999}, "length"),
        ({"widget": "dock", "state": "open"}, "state"),
        ({"widget": "dock", "edge": "middle"}, "edge"),
    ],
)
def test_panel_bounds_report_key_path(make_config, panel, field):
    with pytest.raises(ValidationError) as exc:
        make_config(monitors={"HDMI-A-1": {"shell": "edge", "panels": [panel]}})
    assert exc.value.errors()[0]["loc"][:5] == ("monitors", "HDMI-A-1", "panels", 0, field)


def test_pos_accepts_int_and_center_only():
    assert PanelConfig(widget="dock", pos=600).pos == 600
    assert PanelConfig(widget="dock", pos="center").pos == "center"
    with pytest.raises(ValidationError):
        PanelConfig(widget="dock", pos="middle")


def test_shell_mode_validated(make_config):
    with pytest.raises(ValidationError):
        make_config(monitors={"HDMI-A-1": {"shell": "yes"}})


def test_unlisted_monitor_defaults_to_plasma(make_config):
    assert make_config().monitor("DP-9").shell == "plasma"


def test_monitor_theme_override_merges(make_config):
    cfg = make_config(monitors={"HDMI-A-1": {"shell": "edge", "theme": {"accent": "#d3a68f"}}})
    assert cfg.theme_for("HDMI-A-1").accent == "#d3a68f"
    assert cfg.theme_for("HDMI-A-1").frame == "#0b0c0d"
    assert cfg.theme_for("DP-1").accent == "#8fd3b6"


def test_bad_override_color_fails_at_load(make_config):
    with pytest.raises(ValidationError) as exc:
        make_config(monitors={"HDMI-A-1": {"theme": {"accent": "nope"}}})
    assert "monitors.HDMI-A-1.theme" in str(exc.value)


@pytest.mark.parametrize("bad", ['Evil"Font', "back\\slash", "a{b", "a}b", "a;b"])
def test_font_names_with_css_metacharacters_rejected(make_config, bad):
    with pytest.raises(ValidationError) as exc:
        make_config(theme={"font": ["Hack", bad]})
    assert exc.value.errors()[0]["loc"] == ("theme", "font")
    assert "font name" in str(exc.value)


def test_font_override_with_bad_name_fails_at_load(make_config):
    with pytest.raises(ValidationError, match="monitors.HDMI-A-1.theme"):
        make_config(monitors={"HDMI-A-1": {"theme": {"font": ["a;b"]}}})


def test_ordinary_font_names_accepted(make_config):
    assert make_config(theme={"font": ["JetBrains Mono", "Hack Nerd Font Mono"]})


def test_eight_digit_colour_accepted_and_lowercased(make_config):
    assert make_config(theme={"frame": "#0B0C0D80"}).theme.frame == "#0b0c0d80"


@pytest.mark.parametrize("bad", ["#0b0c0d8", "#0b0c0d800", "0b0c0d80", "#0b0c0g80"])
def test_bad_alpha_colour_rejected_with_key_path(make_config, bad):
    with pytest.raises(ValidationError) as exc:
        make_config(theme={"frame": bad})
    assert exc.value.errors()[0]["loc"] == ("theme", "frame")
    assert "#rrggbbaa" in str(exc.value)


BAD_COLORS = ["#ffffff\n", "#ffffff80\n", " #ffffff", "#ffffff ", "#fff"]


@pytest.mark.parametrize("bad", BAD_COLORS)
@pytest.mark.parametrize(
    ("make_theme", "path"),
    [
        (lambda c: {"frame": c}, ("theme", "frame")),
        (lambda c: {"border": {"color": c}}, ("theme", "border", "color")),
        (lambda c: {"shadow": {"color": c}}, ("theme", "shadow", "color")),
    ],
)
def test_malformed_colors_rejected_in_theme(make_config, bad, make_theme, path):
    with pytest.raises(ValidationError) as exc:
        make_config(theme=make_theme(bad))
    assert exc.value.errors()[0]["loc"] == path


@pytest.mark.parametrize("bad", BAD_COLORS)
@pytest.mark.parametrize("key", ["border", "shadow"])
def test_malformed_override_effect_color_names_key_path(make_config, bad, key):
    with pytest.raises(ValidationError) as exc:
        make_config(monitors={"HDMI-A-1": {"theme": {key: {"color": bad}}}})
    assert "monitors.HDMI-A-1.theme" in str(exc.value)


@pytest.mark.parametrize("good", ["#ffffff", "#FFFFFF80"])
def test_valid_six_and_eight_digit_colors_still_pass(make_config, good):
    cfg = make_config(theme={"border": {"color": good}})
    assert cfg.theme.border.color == good.lower()
