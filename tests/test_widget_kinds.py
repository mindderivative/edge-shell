"""The built-in widgets are Widgets (content), never panel windows; the panel window class
comes from the panel kind (panel/widget spec 3.4-3.5)."""

from types import SimpleNamespace

import pytest

pytest.importorskip("gi")
pytest.importorskip("fabric")

import shell.edge_panel as ep  # noqa: E402
import shell.monitors as mon_mod  # noqa: E402
import widgets  # noqa: E402,F401  (registers the built-in widgets)
from shell import registry  # noqa: E402
from shell.corner_panel import CornerPanel  # noqa: E402
from shell.panel_spec import CornerGeometry, PanelGeometry  # noqa: E402
from shell.widget import NO_PROPS, Widget, WidgetProps  # noqa: E402

BUILT_IN = {
    "clock": ("Clock", ("edge",)),
    "dock": ("Dock", ("edge",)),
    "summary": ("Summary", ("corner",)),
    "system_bar": ("System bar", ("edge",)),
}


def test_the_built_in_widgets_and_their_kinds():
    assert {
        n: (registry.widget_title(n), registry.supported_kinds(n)) for n in registry.widget_names()
    } == BUILT_IN


def test_every_widget_is_a_widget_not_a_panel_window():
    for name in registry.widget_names():
        cls = registry.widget_class(name)
        assert issubclass(cls, Widget) and not issubclass(cls, ep.EdgePanel), name


def test_the_window_class_follows_the_panel_kind():
    edge = PanelGeometry("dock", "bottom", 680, 560, 64, "extended", "dock")
    corner = CornerGeometry("summary", "bottom-left", "bottom", 300, 290, 380, "extended", "s")
    assert mon_mod.panel_class(edge) is ep.EdgePanel
    assert mon_mod.panel_class(corner) is CornerPanel


class Recorder(Widget):
    def __init__(self):
        self.built, self.destroyed = [], 0

    def build(self, props):
        self.built.append(props)
        return "content"

    def destroy(self):
        self.destroyed += 1


def test_the_panel_builds_its_widget_with_the_props():
    class Own(WidgetProps):
        text: str = "x"

    w, props = Recorder(), Own(text="y")  # not NO_PROPS: dropping the props must show
    panel = SimpleNamespace(_widget=w, _props=props)
    assert ep.EdgePanel.build_content(panel) == "content" and w.built == [props]


def test_a_panel_without_a_widget_is_empty():
    content = ep.EdgePanel.build_content(SimpleNamespace(_widget=None, _props=NO_PROPS))
    assert content.get_children() == []


def test_destroying_the_panel_destroys_its_widget_once():
    w = Recorder()
    panel = SimpleNamespace(_widget=w)
    ep.EdgePanel._on_destroy(panel)
    ep.EdgePanel._on_destroy(panel)  # GTK may emit destroy more than once
    assert w.destroyed == 1 and panel._widget is None


def test_the_destroy_handler_is_connected_before_the_content_is_built():
    # a build that fails half way must still have its timers stopped when the window goes;
    # building a real panel would map a window on Phil's screen, so check the source order
    import inspect

    src = inspect.getsource(ep.EdgePanel.__init__)
    assert src.index('self.connect("destroy", self._on_destroy)') < src.index(
        "self.build_content()"
    )


def test_a_build_that_fails_destroys_the_half_built_window():
    # EdgePanel.__init__ creates the window before the content; a widget that raises in
    # build() must not leave that window behind (MonitorShell then skips the panel)
    import inspect

    src = inspect.getsource(ep.EdgePanel.__init__)
    build = src.index("inner = self.build_content()")
    assert src.rindex("try:", 0, build) > src.rindex("super().__init__(", 0, build)
    assert src.index("self.destroy()", build) < src.index("raise", build)
