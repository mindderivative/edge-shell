import pytest

from shell.config.loader import load_config, load_config_text
from shell.config.models import ConfigError

USER = '[theme]\naccent = "#112233"\n[monitors.HDMI-A-1]\nshell = "edge"\n'


def test_load_config_text_matches_load_config(tmp_path):
    path = tmp_path / "c.toml"
    path.write_text(USER)
    assert load_config_text(USER) == load_config(path)


def test_load_config_text_of_nothing_is_the_defaults():
    assert load_config_text("") == load_config(None)


def test_load_config_text_syntax_error():
    with pytest.raises(ConfigError, match="TOML syntax error"):
        load_config_text("[theme\n")


def test_load_config_text_names_the_bad_key():
    with pytest.raises(ConfigError, match="theme.thickness"):
        load_config_text("[theme]\nthickness = 1\n")
