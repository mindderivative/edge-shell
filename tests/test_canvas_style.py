import pytest

from shell.canvas.style import CanvasStyle, reserved_px, style_for


def test_effects_off_by_default(make_config):
    style = style_for(make_config().theme)
    assert style == CanvasStyle(mass=(11 / 255, 12 / 255, 13 / 255, 1.0), border=None, shadow=None)
    assert style.pad == 0


def test_enabled_effects_carry_width_elevation_and_rgba(make_config):
    theme = make_config(
        theme={"border": {"enabled": True}, "shadow": {"enabled": True, "elevation": 100}}
    ).theme
    style = style_for(theme)
    assert style.border[0] == 2
    assert style.border[1] == pytest.approx((0x8F / 255, 0xD3 / 255, 0xB6 / 255, 1.0))
    assert style.shadow[0] == 100
    assert style.shadow[1] == pytest.approx((0.0, 0.0, 0.0, 0x80 / 255))
    assert style.pad == 48 + 2


def test_reserved_covers_the_frame_plus_the_outer_border(make_config):
    assert reserved_px(make_config().theme) == 10
    on = make_config(theme={"border": {"enabled": True, "width": 4}}).theme
    assert reserved_px(on) == 14
    off = make_config(theme={"border": {"enabled": False, "width": 4}}).theme
    assert reserved_px(off) == 10


def test_zero_elevation_means_no_shadow(make_config):
    theme = make_config(theme={"shadow": {"enabled": True, "elevation": 0}}).theme
    assert style_for(theme).shadow is None


def test_translucent_frame_colour_reaches_the_mass(make_config):
    style = style_for(make_config(theme={"frame": "#0b0c0d80"}).theme)
    assert style.mass[3] == pytest.approx(0x80 / 255)


def test_pad_at_default_elevation(make_config):
    theme = make_config(theme={"shadow": {"enabled": True}}).theme
    assert style_for(theme).pad == 24  # 50 % of 48 px
