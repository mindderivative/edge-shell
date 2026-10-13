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
        def __init__(self, store, **kwargs):
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
        def __init__(self, store, **kwargs):
            pass

        def run(self):
            return 1

    monkeypatch.setattr(app_mod, "EdgeShellApp", FakeApp)
    assert main_mod.main(["--config", str(cfg)]) == 1


def test_stats_seconds_reach_the_app(tmp_path, monkeypatch):
    cfg = tmp_path / "c.toml"
    cfg.write_text("")
    got = {}

    class FakeApp:
        def __init__(self, store, stats_seconds=None):
            got["stats"] = stats_seconds

        def run(self):
            return 0

    monkeypatch.setattr(app_mod, "EdgeShellApp", FakeApp)
    assert main_mod.main(["--config", str(cfg), "--stats", "7.5"]) == 0
    assert got["stats"] == 7.5
    assert main_mod.main(["--config", str(cfg)]) == 0
    assert got["stats"] is None


@pytest.mark.parametrize("value", ["0", "10.5", "-1", "abc"])
def test_stats_is_capped_at_ten_seconds(value):
    with pytest.raises(SystemExit) as exc:
        main_mod.main(["--stats", value])
    assert exc.value.code == 2
