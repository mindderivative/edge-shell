"""Entry point behaviour that needs no display."""

import pytest

pytest.importorskip("gi")
pytest.importorskip("fabric")

import main as main_mod  # noqa: E402
import shell.app as app_mod  # noqa: E402


def test_explicit_missing_config_is_exit_2_naming_the_path(tmp_path, capsys):
    missing = tmp_path / "nope.toml"
    assert main_mod.main(["--config", str(missing)]) == 2
    assert "nope.toml" in capsys.readouterr().err


def test_default_config_path_may_be_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(main_mod, "USER_PATH", tmp_path / "absent.toml")
    ran = []

    class FakeApp:
        def __init__(self, store):
            ran.append(store.required)

        def run(self):
            return 0

    monkeypatch.setattr(app_mod, "EdgeShellApp", FakeApp)
    assert main_mod.main([]) == 0
    assert ran == [False]


def test_main_returns_the_run_exit_code(tmp_path, monkeypatch):
    cfg = tmp_path / "c.toml"
    cfg.write_text("")

    class FakeApp:
        def __init__(self, store):
            pass

        def run(self):
            return 1

    monkeypatch.setattr(app_mod, "EdgeShellApp", FakeApp)
    assert main_mod.main(["--config", str(cfg)]) == 1
