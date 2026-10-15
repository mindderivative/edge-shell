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
        ({"panel": "edge", "name": "dock", "widget": "dock", "length": 0}, "length"),
        ({"panel": "edge", "name": "dock", "widget": "dock", "depth": -5}, "depth"),
        ({"panel": "edge", "name": "dock", "widget": "dock", "length": 999999}, "length"),
        ({"panel": "edge", "name": "dock", "widget": "dock", "state": "open"}, "state"),
        ({"panel": "edge", "name": "dock", "widget": "dock", "edge": "middle"}, "edge"),
    ],
)
def test_panel_bounds_report_key_path(make_config, panel, field):
    with pytest.raises(ValidationError) as exc:
        make_config(monitors={"HDMI-A-1": {"shell": "edge", "panels": [panel]}})
    assert exc.value.errors()[0]["loc"][:5] == ("monitors", "HDMI-A-1", "panels", 0, field)


def test_pos_accepts_int_and_center_only():
    assert PanelConfig(panel="edge", name="dock", widget="dock", pos=600).pos == 600
    assert PanelConfig(panel="edge", name="dock", widget="dock", pos="center").pos == "center"
    with pytest.raises(ValidationError):
        PanelConfig(panel="edge", name="dock", widget="dock", pos="middle")


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


@pytest.mark.parametrize("bad", ["Hack\nNerd", "a\tb", "a\x00b", "a\x7fb", "a\x1fb"])
def test_font_names_with_control_characters_rejected(make_config, bad):
    with pytest.raises(ValidationError) as exc:
        make_config(theme={"font": ["Hack", bad]})
    assert "control character" in str(exc.value)


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


@pytest.mark.parametrize("length", [60, 4000, "fill", "content", "1%", "50%", "12.5%", "100%"])
def test_length_modes_accepted(length):
    assert PanelConfig(panel="edge", name="dock", widget="dock", length=length).length == length


@pytest.mark.parametrize("length", [59, 4001, "0%", "101%", "half", "560", "50 %", True])
def test_bad_length_names_the_key_path(make_config, length):
    with pytest.raises(ValidationError) as exc:
        make_config(
            monitors={
                "HDMI-A-1": {
                    "panels": [
                        {"panel": "edge", "name": "dock", "widget": "dock", "length": length}
                    ]
                }
            }
        )
    (error,) = exc.value.errors()
    assert error["loc"] == ("monitors", "HDMI-A-1", "panels", 0, "length")
    assert '"fill", "content" or a percentage' in error["msg"]


def test_align_offset_order_and_bounds():
    p = PanelConfig(
        panel="edge",
        name="dock",
        widget="dock",
        align="end",
        offset=12,
        order=3,
        min_length=100,
        max_length=900,
    )
    assert (p.align, p.offset, p.order, p.min_length, p.max_length) == ("end", 12, 3, 100, 900)
    assert (
        PanelConfig(panel="edge", name="dock", widget="dock", offset=-40).offset == -40
    )  # center may shift either way


@pytest.mark.parametrize(
    ("panel", "message"),
    [
        ({"pos": 10, "align": "end"}, "pos cannot be combined with align or offset"),
        ({"pos": 5, "offset": 3}, 'pos = N is align = "start", offset = N - 38'),
        ({"pos": "center", "offset": 3}, "drop pos; center is the default align"),
        ({"align": "end", "offset": -4}, 'a negative offset only works with align = "center"'),
        ({"min_length": 300, "max_length": 200}, "min_length must not be larger than max_length"),
    ],
)
def test_placement_conflicts_name_the_panel(make_config, panel, message):
    with pytest.raises(ValidationError) as exc:
        make_config(
            monitors={
                "HDMI-A-1": {
                    "panels": [{"panel": "edge", "name": "dock", "widget": "dock", **panel}]
                }
            }
        )
    (error,) = exc.value.errors()
    assert error["loc"] == ("monitors", "HDMI-A-1", "panels", 0)
    assert message in error["msg"]


@pytest.mark.parametrize(
    ("panel", "field", "kind"),
    [
        (
            {"panel": "edge", "name": "dock", "widget": "dock", "align": "middle"},
            "align",
            "literal_error",
        ),
        (
            {"panel": "edge", "name": "dock", "widget": "dock", "order": -1},
            "order",
            "greater_than_equal",
        ),
        (
            {"panel": "edge", "name": "dock", "widget": "dock", "offset": 20001},
            "offset",
            "less_than_equal",
        ),
        (
            {"panel": "edge", "name": "dock", "widget": "dock", "min_length": 10},
            "min_length",
            "greater_than_equal",
        ),
    ],
)
def test_new_panel_keys_report_key_path(make_config, panel, field, kind):
    with pytest.raises(ValidationError) as exc:
        make_config(monitors={"HDMI-A-1": {"shell": "edge", "panels": [panel]}})
    (error,) = exc.value.errors()
    assert error["loc"] == ("monitors", "HDMI-A-1", "panels", 0, field)
    # the bound itself, not "extra_forbidden" (what every new key gives before this task)
    assert error["type"] == kind


def test_layout_gap_default_override_and_bounds(make_config):
    cfg = make_config(monitors={"A": {"layout": {"gap": 20}}, "B": {}})
    assert (cfg.layout.gap, cfg.layout_for("A").gap, cfg.layout_for("B").gap) == (8, 20, 8)
    assert cfg.layout_for("not-configured").gap == 8
    with pytest.raises(ValidationError, match=r"monitors\.A\.layout: gap"):
        make_config(monitors={"A": {"layout": {"gap": -1}}})
    with pytest.raises(ValidationError) as exc:
        make_config(monitors={"A": {"layout": {"gapp": 1}}})
    assert exc.value.errors()[0]["loc"] == ("monitors", "A", "layout", "gapp")
