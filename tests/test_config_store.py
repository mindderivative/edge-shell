# tests/test_config_store.py
import pytest

from shell.config.models import ConfigError
from shell.config.store import ConfigStore

GOOD = '[monitors.HDMI-A-1]\nshell = "edge"\n[[monitors.HDMI-A-1.panels]]\nwidget = "dock"\n'


def test_initial_load_and_failure(tmp_path, fake_registry):
    path = tmp_path / "c.toml"
    path.write_text(GOOD)
    assert ConfigStore(path).config.monitor("HDMI-A-1").shell == "edge"
    path.write_text("[theme\n")
    with pytest.raises(ConfigError):
        ConfigStore(path)


def test_reload_returns_old_and_new(tmp_path, fake_registry):
    path = tmp_path / "c.toml"
    path.write_text(GOOD)
    store = ConfigStore(path)
    path.write_text(GOOD + '[theme]\naccent = "#112233"\n')
    old, new = store.reload()
    assert old.theme.accent == "#8fd3b6" and new.theme.accent == "#112233"
    assert store.config is new and store.last_error is None


def test_reload_unchanged_returns_none(tmp_path, fake_registry):
    path = tmp_path / "c.toml"
    path.write_text(GOOD)
    store = ConfigStore(path)
    assert store.reload() is None and store.last_error is None


@pytest.mark.parametrize(
    "bad",
    [
        "[theme\n",  # invalid TOML (editor saved mid-edit)
        "[theme]\nbogus = 1\n",  # unknown key
        '[theme]\nframe = "red"\n',  # bad color
        '[monitors.HDMI-A-1]\n[[monitors.HDMI-A-1.panels]]\nwidget = "ghost"\n',  # unknown widget
    ],
)
def test_bad_edit_keeps_last_good_config(tmp_path, fake_registry, bad):
    path = tmp_path / "c.toml"
    path.write_text(GOOD)
    store = ConfigStore(path)
    before = store.config
    path.write_text(bad)
    assert store.reload() is None
    assert store.config is before
    assert store.last_error
    path.write_text(GOOD + '[theme]\naccent = "#112233"\n')  # fixing the file recovers
    assert store.reload() is not None and store.last_error is None
