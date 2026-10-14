import pytest

from shell.config.loader import load_config
from shell.config.models import ConfigError


def write(path, text):
    path.write_text(text)
    return path


def test_defaults_only_matches_test_theme(make_config):
    assert load_config(None).theme == make_config().theme


def test_missing_user_file_uses_defaults(tmp_path, make_config):
    assert load_config(tmp_path / "nope.toml").theme == make_config().theme


def test_user_overlay_changes_only_given_keys(tmp_path):
    cfg = load_config(write(tmp_path / "c.toml", '[theme]\naccent = "#112233"\n'))
    assert cfg.theme.accent == "#112233"
    assert cfg.theme.frame == "#0b0c0d"


def test_monitor_panels_load_in_order(tmp_path):
    cfg = load_config(
        write(
            tmp_path / "c.toml",
            '[monitors.HDMI-A-1]\nshell = "edge"\n'
            '[[monitors.HDMI-A-1.panels]]\npanel = "edge"\nname = "dock"\nwidget = "dock"\n'
            '[[monitors.HDMI-A-1.panels]]\npanel = "edge"\nname = "clock"\nwidget = "clock"\n'
            "depth = 50\n",
        )
    )
    panels = cfg.monitor("HDMI-A-1").panels
    assert [p.widget for p in panels] == ["dock", "clock"]
    assert panels[1].depth == 50


def test_invalid_toml_names_the_file(tmp_path):
    path = write(tmp_path / "c.toml", "[theme\n")
    with pytest.raises(ConfigError) as exc:
        load_config(path)
    assert str(path) in str(exc.value)


def test_unknown_key_reports_path(tmp_path):
    with pytest.raises(ConfigError) as exc:
        load_config(write(tmp_path / "c.toml", "[theme]\nbogus = 1\n"))
    assert "theme.bogus" in str(exc.value)


def test_bad_color_reports_path(tmp_path):
    with pytest.raises(ConfigError) as exc:
        load_config(write(tmp_path / "c.toml", '[theme]\nframe = "red"\n'))
    assert "theme.frame" in str(exc.value)


def test_panel_bound_reports_full_key_path(tmp_path):
    text = (
        '[monitors.HDMI-A-1]\nshell = "edge"\n'
        '[[monitors.HDMI-A-1.panels]]\npanel = "edge"\nname = "dock"\nwidget = "dock"\nlength = 0\n'
    )
    with pytest.raises(ConfigError) as exc:
        load_config(write(tmp_path / "c.toml", text))
    assert "monitors.HDMI-A-1.panels[0].length" in str(exc.value)


def test_unreadable_user_path_is_config_error(tmp_path):
    directory = tmp_path / "c.toml"
    directory.mkdir()
    with pytest.raises(ConfigError) as exc:
        load_config(directory)
    assert str(directory) in str(exc.value)


def test_invalid_utf8_is_config_error(tmp_path):
    path = tmp_path / "c.toml"
    path.write_bytes(b'[theme]\naccent = "\xff\xfe"\n')
    with pytest.raises(ConfigError) as exc:
        load_config(path)
    assert str(path) in str(exc.value)


def test_missing_user_file_is_an_error_when_required(tmp_path):
    missing = tmp_path / "nope.toml"
    with pytest.raises(ConfigError, match="nope.toml"):
        load_config(missing, required=True)


def test_unreadable_user_file_is_an_error_not_defaults(tmp_path):
    import os

    path = write(tmp_path / "c.toml", "[theme]\n")
    path.chmod(0)
    try:
        if os.access(path, os.R_OK):
            pytest.skip("permissions not enforced (running as root)")
        with pytest.raises(ConfigError, match="c.toml"):
            load_config(path)  # exists() would have said False and used defaults
    finally:
        path.chmod(0o600)


def test_an_entry_without_panel_names_the_new_format(tmp_path):
    path = write(
        tmp_path / "old.toml",
        "# the old format: entries with only a widget\n"
        '[[monitors.HDMI-A-1.panels]]\nwidget = "dock"\n\n[[monitors.HDMI-A-1.panels]]\n'
        'widget = "clock"\n',
    )
    with pytest.raises(ConfigError) as exc:
        load_config(path)
    lines = str(exc.value).splitlines()
    assert 'monitors.HDMI-A-1.panels[0].panel: missing; use "edge", "corner" or "float"' in lines
    assert 'monitors.HDMI-A-1.panels[1].panel: missing; use "edge", "corner" or "float"' in lines
    assert "monitors.HDMI-A-1.panels[0].name: Field required" in lines
    assert len([line for line in lines if "the old format" in line]) == 1  # once per file


def test_panel_name_and_widget_are_required():
    from shell.config.models import Config

    panel = Config.model_json_schema()["$defs"]["PanelConfig"]
    assert {"panel", "name", "widget"} <= set(panel["required"])


def test_a_panel_index_is_written_in_brackets():
    from shell.config.loader import key_path

    assert key_path(("monitors", "X", "panels", 2, "handle", "size")) == (
        "monitors.X.panels[2].handle.size"
    )
    assert key_path(("theme", "font", 0)) == "theme.font.0"  # other lists keep their dots
    assert key_path(()) == "config"
