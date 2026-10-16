"""settings.screens: the toolbar's mode checkboxes, the desktop's name and monitor detection
(pure; kscreen-doctor never runs)."""

import subprocess
import sys

import pytest

from settings import screens
from settings.screens import (
    NATIVE_FALLBACK,
    DetectError,
    desktop_label,
    detect_outputs,
    mode_flags,
    mode_of,
)
from shell.config.models import ShellMode

KSCREEN = (
    '{"outputs": [{"name": "HDMI-A-1", "enabled": true, "scale": 1, '
    '"pos": {"x": 0, "y": 0}, "size": {"width": 1920, "height": 1080}}]}'
)


@pytest.mark.parametrize(
    "mode, flags",
    [
        ("edge", (True, False)),
        ("plasma", (False, True)),
        ("both", (True, True)),
        ("none", (False, False)),
    ],
)
def test_the_checkboxes_map_onto_the_four_shell_values(mode, flags):
    assert mode_flags(mode) == flags
    assert mode_of(*flags) == mode


def test_every_shell_value_has_its_checkboxes():
    from typing import get_args

    assert {mode_of(*mode_flags(m)) for m in get_args(ShellMode)} == set(get_args(ShellMode))


def test_an_unknown_shell_value_is_an_error():
    with pytest.raises(KeyError):
        mode_flags("sideways")


@pytest.mark.parametrize(
    "value, label",
    [
        ("KDE", "KDE Plasma"),
        ("KDE:plasma", "KDE Plasma"),
        ("kde", "KDE Plasma"),
        ("Hyprland", "Hyprland"),
        ("GNOME:GNOME-Classic", "GNOME"),
        ("X-Cinnamon", "Cinnamon"),
        ("SomethingNew", NATIVE_FALLBACK),
        ("", NATIVE_FALLBACK),
        (" : ", NATIVE_FALLBACK),
    ],
)
def test_the_native_checkbox_is_labelled_with_the_desktop(value, label):
    assert desktop_label({"XDG_CURRENT_DESKTOP": value}) == label


def test_no_desktop_variable_is_the_fallback():
    assert desktop_label({}) == NATIVE_FALLBACK == "Native desktop"


def test_the_label_reads_the_environment_by_default(monkeypatch):
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "Hyprland")
    assert desktop_label() == "Hyprland"


def test_detect_reads_the_monitors():
    outputs = detect_outputs(lambda: KSCREEN)
    assert [(o.name, o.width, o.height) for o in outputs] == [("HDMI-A-1", 1920, 1080)]


@pytest.mark.parametrize(
    "error",
    [
        OSError("No such file or directory: 'kscreen-doctor'"),
        subprocess.TimeoutExpired(["kscreen-doctor", "-j"], 5),
        subprocess.CalledProcessError(1, ["kscreen-doctor", "-j"]),
    ],
)
def test_a_failed_detection_raises_with_the_reason(error):
    def read():
        raise error

    with pytest.raises(DetectError, match="kscreen-doctor failed"):
        detect_outputs(read)


def test_unexpected_output_raises():
    with pytest.raises(DetectError, match="kscreen-doctor failed"):
        detect_outputs(lambda: "not json")


def test_the_default_reader_is_looked_up_when_called(monkeypatch):
    """No test ever runs kscreen-doctor: the default reader can be replaced."""
    monkeypatch.setattr(screens, "read_kscreen_json", lambda: KSCREEN)
    assert [o.name for o in detect_outputs()] == ["HDMI-A-1"]


@pytest.mark.parametrize("module", ["settings.screens", "settings.pages"])
def test_the_pure_modules_import_no_gtk(module):
    code = f"import sys, {module}; print(any(m.startswith(('gi', 'fabric')) for m in sys.modules))"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"
