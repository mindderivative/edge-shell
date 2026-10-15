"""settings.fileops: leaving a config with unsaved changes (pure; the question is a callable)."""

from pathlib import Path

import pytest

from settings.fileops import Answer, leave, unsaved_question

USER = '[monitors.HDMI-A-1]\nshell = "edge"\n'
SHELL = ("monitors", "HDMI-A-1", "shell")


@pytest.fixture
def session(tmp_path, fake_registry):
    pytest.importorskip("tomlkit")
    from settings.session import SettingsSession

    path = tmp_path / "config.toml"
    path.write_text(USER)
    return SettingsSession(path)


def asker(answer):
    asked = []

    def ask():
        asked.append(answer)
        return answer

    ask.asked = asked
    return ask


def test_a_clean_config_is_left_without_a_question(session):
    ask = asker(Answer.CANCEL)
    assert leave(session, ask) is True and ask.asked == []


def test_cancel_stays_and_changes_nothing(session):
    session.apply(lambda d: d.set(SHELL, "both"))
    ask = asker(Answer.CANCEL)
    assert leave(session, ask) is False and ask.asked == [Answer.CANCEL]
    assert session.dirty and 'shell = "both"' in session.path.read_text()


def test_save_keeps_the_changes_as_the_saved_point(session):
    session.apply(lambda d: d.set(SHELL, "both"))
    assert leave(session, asker(Answer.SAVE)) is True
    assert not session.dirty and 'shell = "both"' in session.path.read_text()
    assert 'shell = "both"' in session.path.with_name("config.toml.bak").read_text()


def test_discard_puts_the_saved_file_back(session):
    session.apply(lambda d: d.set(SHELL, "both"))
    assert leave(session, asker(Answer.DISCARD)) is True
    assert session.path.read_text() == USER and not session.dirty


def test_a_hand_edit_met_by_discard_raises_and_is_kept(session):
    from settings.session import ChangedOutside

    session.apply(lambda d: d.set(SHELL, "both"))
    session.path.write_text(USER + "# by hand\n")
    with pytest.raises(ChangedOutside):
        leave(session, asker(Answer.DISCARD))
    assert session.path.read_text().endswith("# by hand\n")
    assert leave(session, asker(Answer.DISCARD)) is True  # now clean: no question


def test_the_question_names_the_file():
    primary, secondary = unsaved_question(Path("/home/p/.config/edge-shell/config.toml"))
    assert primary == "Save the changes to config.toml?"
    assert "/home/p/.config/edge-shell/config.toml" in secondary and "Discard" in secondary
