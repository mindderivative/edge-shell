"""The built-in widgets build with the names the theme CSS targets, and the timers they start
(no window: a widget's build() returns a Gtk tree). Nothing else in the suite references these
widget names, so a CSS id or a Box name drifting from the other would go unnoticed."""

import re

import pytest

gi = pytest.importorskip("gi")
pytest.importorskip("fabric")
gi.require_version("Gtk", "3.0")

from gi.repository import Gtk  # noqa: E402

if not Gtk.init_check()[0]:
    pytest.skip("no display", allow_module_level=True)

import widgets.clock as ck  # noqa: E402
import widgets.dock as dk  # noqa: E402
import widgets.summary as sm  # noqa: E402
import widgets.system_bar as sb  # noqa: E402
from shell import registry  # noqa: E402
from shell.theme import to_css  # noqa: E402

# registered name -> (module, root Box name, the repeater period or None, ids the CSS targets)
BUILT_IN = {
    "dock": (dk, "dock", None, set()),
    "clock": (ck, "clock", 1000, {"clock-time"}),
    "system_bar": (sb, "system-bar", 2000, set()),
    "summary": (sm, "summary", 1000, {"summary-time"}),
}


def names_in(widget) -> set[str]:
    found = {widget.get_name()}
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            found |= names_in(child)
    return found


def css_ids(make_config) -> set[str]:
    css = to_css(make_config().theme, "scope")
    return set(re.findall(r"\s#([A-Za-z][\w-]*)\s*\{", css)) - {"handle"}  # handle: the panel's


@pytest.fixture
def built(monkeypatch):
    """build(name) -> (the tree, [(period, callback)] the widget started)."""

    def build(name):
        module = BUILT_IN[name][0]
        repeaters = []

        def fake_repeater(period, callback):
            repeaters.append((period, callback))
            return len(repeaters)

        monkeypatch.setattr(module, "invoke_repeater", fake_repeater, raising=False)
        cpu = iter([(0, 0)] + [(100, 50)] * 10)  # (total, idle) jiffies: 50 % busy since build
        monkeypatch.setattr(module, "read_cpu_times", lambda: next(cpu), raising=False)
        monkeypatch.setattr(module, "read_meminfo_percent", lambda: 40.0, raising=False)
        widget = registry.widget_class(name)()
        return widget.build(registry.widget_props_model(name)()), repeaters

    return build


@pytest.mark.parametrize("name", list(BUILT_IN))
def test_a_built_in_widget_builds_the_names_it_is_known_by(built, name):
    _, box, _, ids = BUILT_IN[name]
    tree, _ = built(name)
    assert tree.get_name() == box
    assert ids <= names_in(tree)


def test_every_id_the_theme_css_targets_is_built_by_a_widget(built, make_config):
    ids = css_ids(make_config)
    assert ids == {"clock-time", "summary-time"}  # a new #id here needs a widget to build it
    built_names = set()
    for name in BUILT_IN:
        built_names |= names_in(built(name)[0])
    assert ids <= built_names


@pytest.mark.parametrize("name", list(BUILT_IN))
def test_a_built_in_widget_starts_its_repeater_with_its_period(built, name):
    period = BUILT_IN[name][2]
    _, repeaters = built(name)
    assert [p for p, _ in repeaters] == ([] if period is None else [period])


def test_the_summary_reads_the_stats_on_every_second_tick(built):
    tree, ((_, refresh),) = built("summary")

    def stats():
        return [c.get_label() for c in tree.get_children()][2:]

    assert stats() == ["CPU --%", "RAM --%"]
    assert refresh() is True
    assert stats() == ["CPU --%", "RAM --%"]  # the first tick: time only
    assert refresh() is True
    assert stats() == ["CPU 50%", "RAM 40%"]
