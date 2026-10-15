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
    panel = SimpleNamespace(_widget=w, _props=props, _theme=SimpleNamespace(font=["f"]))
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


@pytest.mark.parametrize("returns", [None, "a string", "raises"])
def test_a_widget_that_misbehaves_in_build_destroys_the_half_built_window(
    make_config, monkeypatch, returns
):
    """EdgePanel.__init__ creates the window before the content: whatever goes wrong after it
    (build() raising, returning None or a non-widget) destroys the window once, and with it
    the widget and any timer its build() started; the error reaches MonitorShell."""
    destroyed = []

    class Bad(Widget):
        def __init__(self):
            self.stopped = 0

        def build(self, props):
            if returns == "raises":
                raise RuntimeError("widget broke")
            return returns

        def destroy(self):
            self.stopped += 1

    def destroy(self):  # what Gtk does: the "destroy" signal reaches _on_destroy
        destroyed.append(self)
        ep.EdgePanel._on_destroy(self)

    monitor = SimpleNamespace(get_geometry=lambda: SimpleNamespace(width=1920, height=1080))
    monkeypatch.setattr(ep.WaylandWindow, "__init__", lambda _self, **_kw: None)
    monkeypatch.setattr(ep.GtkLayerShell, "set_exclusive_zone", lambda *_a: None)
    monkeypatch.setattr(ep.EdgePanel, "connect", lambda *_a, **_k: 0)
    monkeypatch.setattr(ep.EdgePanel, "destroy", destroy)
    monkeypatch.setattr(ep, "monitor_index", lambda _m: 0)
    spec = PanelGeometry("dock", "bottom", 680, 560, 64, "extended", "dock")
    widget = Bad()
    with pytest.raises((RuntimeError, AttributeError)):
        ep.EdgePanel(spec, make_config().theme, monitor, 0, "s", widget=widget, props=NO_PROPS)
    assert len(destroyed) == 1 and widget.stopped == 1
