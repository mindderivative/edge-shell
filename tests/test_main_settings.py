"""main.py --settings and --restore-config (no window: run_settings is replaced)."""

import pytest

pytest.importorskip("gi")
pytest.importorskip("fabric")

import main as main_mod  # noqa: E402
import settings.app as settings_app  # noqa: E402


@pytest.fixture(autouse=True)  # autouse: set up before any monkeypatch, so checked after its undo
def portal_env_restored():
    """main(["--settings"]) sets GTK_USE_PORTAL for the settings process; a test must not leave
    it in the test process."""
    import os

    before = os.environ.get("GTK_USE_PORTAL")
    yield
    assert os.environ.get("GTK_USE_PORTAL") == before


@pytest.fixture
def opened(monkeypatch):
    # start unset (main sets it); the setenv makes monkeypatch undo whatever main then sets
    monkeypatch.setenv("GTK_USE_PORTAL", "")
    monkeypatch.delenv("GTK_USE_PORTAL")
    calls = []
    monkeypatch.setattr(settings_app, "run_settings", lambda path: calls.append(path) or 0)
    return calls


def test_settings_opens_the_window_on_the_given_config(tmp_path, opened):
    cfg = tmp_path / "c.toml"
    assert main_mod.main(["--settings", "--config", str(cfg)]) == 0
    assert opened == [cfg]  # need not exist: the window creates it on the first change


def test_settings_defaults_to_the_user_config(tmp_path, monkeypatch, opened):
    monkeypatch.setattr(main_mod, "USER_PATH", tmp_path / "config.toml")
    assert main_mod.main(["--settings"]) == 0
    assert opened == [tmp_path / "config.toml"]


def test_settings_opens_even_when_the_config_is_invalid(tmp_path, opened):
    cfg = tmp_path / "c.toml"
    cfg.write_text("[theme\n")
    assert main_mod.main(["--settings", "--config", str(cfg)]) == 0
    assert opened == [cfg]


def test_settings_asks_gtk_for_the_native_file_dialogs(tmp_path, opened, monkeypatch):
    import os

    cfg = str(tmp_path / "c.toml")
    monkeypatch.setenv("GTK_USE_PORTAL", "0")  # a user's own choice wins
    main_mod.main(["--settings", "--config", cfg])
    assert os.environ["GTK_USE_PORTAL"] == "0"
    monkeypatch.delenv("GTK_USE_PORTAL")
    main_mod.main(["--settings", "--config", cfg])
    assert os.environ["GTK_USE_PORTAL"] == "1"


def test_restore_config_puts_the_backup_back(tmp_path, capsys):
    cfg = tmp_path / "c.toml"
    cfg.write_text("broken\n")
    (tmp_path / "c.toml.bak").write_text("good\n")
    assert main_mod.main(["--restore-config", "--config", str(cfg)]) == 0
    assert cfg.read_text() == "good\n"
    assert "restored" in capsys.readouterr().out


def test_restore_config_without_a_backup_fails(tmp_path, capsys):
    assert main_mod.main(["--restore-config", "--config", str(tmp_path / "c.toml")]) == 1
    assert "no backup" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv",
    [
        ["--settings", "--list-outputs"],
        ["--settings", "--restore-config"],
        ["--settings", "--stats", "5"],
        ["--restore-config", "--stats", "5"],
    ],
)
def test_modes_do_not_combine(argv):
    with pytest.raises(SystemExit) as exc:
        main_mod.main(argv)
    assert exc.value.code == 2


def test_restore_config_reports_an_unreadable_backup_like_a_config_error(tmp_path, capsys):
    cfg = tmp_path / "c.toml"
    (tmp_path / "c.toml.bak").mkdir()  # exists, but reading it raises IsADirectoryError
    assert main_mod.main(["--restore-config", "--config", str(cfg)]) == 1
    assert capsys.readouterr().err.strip()


def test_settings_does_not_build_the_config_store(tmp_path, monkeypatch, opened):
    def boom(*_a, **_k):
        raise AssertionError("ConfigStore built before the settings window")

    monkeypatch.setattr(main_mod, "ConfigStore", boom)
    assert main_mod.main(["--settings", "--config", str(tmp_path / "c.toml")]) == 0


def test_settings_does_not_import_the_widgets_itself(tmp_path, monkeypatch, opened):
    """The window process imports them only when it is the first instance (run_settings)."""
    import sys

    monkeypatch.delitem(sys.modules, "widgets", raising=False)
    assert main_mod.main(["--settings", "--config", str(tmp_path / "c.toml")]) == 0
    assert "widgets" not in sys.modules
