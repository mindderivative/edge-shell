"""CornerPanel (spec 19) and EdgePanel's geometry hooks, called on stand-ins (no window)."""

from types import SimpleNamespace

import pytest

pytest.importorskip("gi")
pytest.importorskip("fabric")

import shell.corner_panel as cp  # noqa: E402
import shell.edge_panel as ep  # noqa: E402
from shell import handle as hd  # noqa: E402
from shell.panel_spec import CornerGeometry, HandleSpec, Interaction, PanelGeometry  # noqa: E402
from shell.widget import Widget, WidgetProps  # noqa: E402
from tests.test_edge_panel_handle import FakeHandleWidget, rects_of  # noqa: E402

MONITOR = SimpleNamespace(get_geometry=lambda: SimpleNamespace(width=1920, height=1080))
BOX = CornerGeometry("box", "bottom-left", "bottom", 300, 290, 380, "extended", "box")


def stub(make_config, spec=BOX, interaction=None, handle=None, d=0.0):
    theme = make_config().theme
    interaction = interaction or Interaction()
    handle = handle or HandleSpec()
    s = SimpleNamespace(
        spec=spec,
        _theme=theme,
        _interaction=interaction,
        _look=hd.resolve_handle(handle, interaction, theme),
        _d=d,
        _last_rect=None,
        _handle=FakeHandleWidget(),
        _handle_area=SimpleNamespace(draws=0),
        _content=FakeHandleWidget(),
        regions=[],
    )
    s._handle_area.queue_draw = lambda: setattr(s._handle_area, "draws", s._handle_area.draws + 1)
    s.input_shape_combine_region = s.regions.append
    s._hit = lambda: ep.EdgePanel._hit(s)
    s._input_rects = lambda dd: cp.CornerPanel._input_rects(s, dd)
    return s


def test_a_corner_panel_is_an_edge_panel():
    assert issubclass(cp.CornerPanel, ep.EdgePanel)


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        (
            PanelGeometry("dock", "bottom", 680, 560, 64, "extended", "dock"),
            ("bottom left", "0px 0px 0px 666px", (588, 74)),
        ),
        (  # clamped: the surface (length + 2R) must stay on a 1920 px edge
            PanelGeometry("dock", "bottom", 1800, 560, 64, "extended", "dock"),
            ("bottom left", "0px 0px 0px 1332px", (588, 74)),
        ),
        (  # a vertical edge, measured on the 1080 px height
            PanelGeometry("dock", "left", 100, 400, 50, "extended", "dock"),
            ("left top", "86px 0px 0px 0px", (60, 428)),
        ),
        (  # a vertical edge, clamped
            PanelGeometry("dock", "right", 1000, 400, 50, "extended", "dock"),
            ("right top", "652px 0px 0px 0px", (60, 428)),
        ),
    ],
    ids=["bottom", "bottom-clamped", "left", "right-clamped"],
)
def test_the_edge_panel_surface_is_unchanged(make_config, spec, expected):
    assert ep.EdgePanel.surface_layout(spec, make_config().theme, MONITOR) == expected


def test_init_takes_its_surface_from_the_subclass(make_config, monkeypatch):
    """EdgePanel.__init__ must call type(self).surface_layout, not EdgePanel's own."""

    class Stop(Exception):
        pass

    def fake_init(_self, **kwargs):
        raise Stop(kwargs)

    monkeypatch.setattr(ep.WaylandWindow, "__init__", fake_init)
    monkeypatch.setattr(ep, "monitor_index", lambda _m: 0)
    spec = CornerGeometry("w", "top-right", "right", 200, 190, 150, "collapsed", "w")
    with pytest.raises(Stop) as caught:
        cp.CornerPanel(spec, make_config().theme, MONITOR, 0, "s")
    kwargs = caught.value.args[0]
    assert kwargs["anchor"] == "top right"
    assert kwargs["margin"] == "0px 0px 0px 0px"
    assert kwargs["layer"] == "top"
    assert kwargs["exclusivity"] == "none"
    assert kwargs["keyboard_mode"] == "none"


def test_init_keeps_its_props_and_builds_the_widget_with_them(make_config, monkeypatch):
    """The props given to EdgePanel(...) must reach widget.build (the panel stores them)."""

    class Stop(Exception):
        pass

    class Own(WidgetProps):
        text: str = "x"

    class Recorder(Widget):
        def build(self, props):
            raise Stop(props)

    monkeypatch.setattr(ep.WaylandWindow, "__init__", lambda _self, **_kw: None)
    monkeypatch.setattr(ep.GtkLayerShell, "set_exclusive_zone", lambda *_a: None)
    monkeypatch.setattr(ep.EdgePanel, "connect", lambda *_a, **_k: 0)
    monkeypatch.setattr(ep.EdgePanel, "destroy", lambda _self: None)  # the failed-build cleanup
    monkeypatch.setattr(ep, "monitor_index", lambda _m: 0)
    spec = PanelGeometry("dock", "bottom", 680, 560, 64, "extended", "dock")
    props = Own(text="y")  # not NO_PROPS: dropping the props must show
    with pytest.raises(Stop) as caught:
        ep.EdgePanel(spec, make_config().theme, MONITOR, 0, "s", widget=Recorder(), props=props)
    assert caught.value.args[0] is props


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        (BOX, ("bottom left", "0px 0px 0px 0px", (300, 390))),
        (
            CornerGeometry("w", "top-right", "right", 200, 190, 150, "collapsed", "w"),
            ("top right", "0px 0px 0px 0px", (160, 200)),
        ),
    ],
)
def test_the_corner_window_is_a_rectangle_anchored_in_its_corner(make_config, spec, expected):
    assert cp.CornerPanel.surface_layout(spec, make_config().theme, MONITOR) == expected


def test_the_input_region_is_the_body_plus_the_hover_zone(make_config):
    s = stub(make_config)
    ep.EdgePanel._update_input_region(s, 0.0)
    assert rects_of(s.regions[-1]) == [(0, 364, 300, 26)]
    ep.EdgePanel._update_input_region(s, 380.0)
    assert rects_of(s.regions[-1]) == [(0, 0, 300, 390)]


def test_without_hover_a_collapsed_corner_panel_takes_only_the_hit_target(make_config):
    s = stub(make_config, interaction=Interaction(hover=False))
    ep.EdgePanel._update_input_region(s, 0.0)
    assert rects_of(s.regions[-1]) == [(133, 376, 44, 14)]


def test_with_every_interaction_off_it_is_click_through(make_config):
    s = stub(make_config, interaction=Interaction(False, False, False))
    ep.EdgePanel._update_input_region(s, 0.0)
    assert rects_of(s.regions[-1]) == []


def test_the_content_sits_past_both_frame_bands(make_config):
    s = stub(make_config)
    cp.CornerPanel._place_content(s)
    assert s._content.set == {
        "size_request": (290, 380),
        "halign": (cp.Gtk.Align.START,),
        "valign": (cp.Gtk.Align.START,),
        "margin_start": (10,),
        "margin_top": (0,),
        "margin_end": (0,),
        "margin_bottom": (0,),
    }


@pytest.mark.parametrize(
    ("d", "offset", "x", "y"),
    [(0.0, 0, 133, 376), (380.0, 0, 133, 0), (100.0, 30, 163, 280), (0.0, 9999, 256, 376)],
)
def test_the_handle_rides_the_body_edge_centred_past_the_band(make_config, d, offset, x, y):
    s = stub(make_config, handle=HandleSpec(offset=offset))
    cp.CornerPanel._place_handle(s, d)
    assert (s._handle.set["margin_start"], s._handle.set["margin_top"]) == ((x,), (y,))
    assert s._handle.set["halign"] == (cp.Gtk.Align.START,)
    assert s._handle_area.draws == 1


def test_the_handle_size_follows_the_opening_edge(make_config):
    s = stub(make_config)
    ep.EdgePanel._size_handle(s)
    assert s._handle.set["size_request"] == (44, 14)
    side = CornerGeometry("w", "top-right", "right", 200, 190, 150, "extended", "w")
    s = stub(make_config, spec=side)
    ep.EdgePanel._size_handle(s)
    assert s._handle.set["size_request"] == (14, 44)


def test_corner_panels_report_their_spec_length(make_config):
    assert cp.CornerPanel.natural_length(stub(make_config)) == 290


def test_the_corner_input_region_is_reapplied_after_the_parent_allocate(make_config, monkeypatch):
    s = stub(make_config)
    order = []

    def parent(_self, _alloc):
        order.append("parent")
        s.regions.append(None)  # Fabric resets the shape to the whole surface

    monkeypatch.setattr(ep.WaylandWindow, "do_size_allocate", parent)
    s._update_input_region = lambda d: ep.EdgePanel._update_input_region(s, d)
    s.regions.clear()
    real = s.input_shape_combine_region
    s.input_shape_combine_region = lambda region: (order.append("region"), real(region))
    ep.EdgePanel.do_size_allocate(s, None)
    assert order == ["parent", "region"]
    assert s.regions[0] is None and rects_of(s.regions[-1]) == [(0, 364, 300, 26)]
