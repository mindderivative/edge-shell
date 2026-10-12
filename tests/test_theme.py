import pytest

from shell.theme import hex_to_rgba, scope_class, to_css


def test_hex_to_rgba():
    assert hex_to_rgba("#0b0c0d") == (11 / 255, 12 / 255, 13 / 255, 1.0)
    assert hex_to_rgba("#ffffff", 0.5) == (1.0, 1.0, 1.0, 0.5)


@pytest.mark.parametrize(
    ("name", "scope"),
    [("HDMI-A-1", "mon-hdmi-a-1"), ("DP-1", "mon-dp-1"), ("eDP_1", "mon-edp-1")],
)
def test_scope_class(name, scope):
    assert scope_class(name) == scope


def test_css_font_stack_quotes_names_but_not_generics(make_config):
    css = to_css(make_config().theme, "mon-x")
    assert 'font-family: "Hack Nerd Font Mono", "JetBrains Mono", monospace;' in css


def test_css_is_scoped_and_uses_theme_colors(make_config):
    css = to_css(make_config(theme={"frame": "#112233"}).theme, "mon-x")
    assert ".mon-x #frame-strip { background-color: #112233; }" in css
    assert "window.mon-x" in css
    for line in css.splitlines():
        if "{" in line and not line.startswith("}"):
            assert "mon-x" in line, line  # nothing unscoped


def test_two_monitors_do_not_share_rules(make_config):
    cfg = make_config(monitors={"HDMI-A-1": {"theme": {"frame": "#111111"}}})
    a = to_css(cfg.theme_for("HDMI-A-1"), scope_class("HDMI-A-1"))
    b = to_css(cfg.theme_for("DP-1"), scope_class("DP-1"))
    assert "#111111" in a and "#111111" not in b
