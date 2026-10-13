"""EdgePanel's drawn handle and interaction flags, called on stand-in objects (no window)."""

from types import SimpleNamespace

import cairo
import pytest

pytest.importorskip("gi")
pytest.importorskip("fabric")

from gi.repository import Gtk  # noqa: E402

import shell.edge_panel as ep  # noqa: E402
from shell import handle as hd  # noqa: E402
from shell.handle_draw import draw_handle  # noqa: E402
from shell.panel_spec import HandleSpec, Interaction  # noqa: E402

ALL = Interaction()


class FakeHandleWidget:
    """Records what EdgePanel sets on its handle Button."""

    def __init__(self, flags=Gtk.StateFlags.NORMAL):
        self.flags = flags
        self.set = {}
        self.name = None
        accessible = SimpleNamespace(set_name=lambda n: setattr(self, "name", n))
        self.get_accessible = lambda: accessible

    def __getattr__(self, attr):
        if attr.startswith("set_"):
            return lambda *values: self.set.__setitem__(attr[4:], values)
        raise AttributeError(attr)

    def get_state_flags(self):
        return self.flags


def stub(make_config, edge="bottom", interaction=ALL, handle=None, **extra):
    theme = make_config().theme
    handle = handle or HandleSpec()
    s = SimpleNamespace(
        spec=SimpleNamespace(edge=edge, length=560, depth=64, label="dock"),
        _theme=theme,
        _interaction=interaction,
        _handle_spec=handle,
        _look=hd.resolve_handle(handle, interaction, theme),
        _d=0.0,
        _hovered=False,
        _extended=False,
        _last_rect=None,
        _draw_failed=False,
        _handle=FakeHandleWidget(),
        _handle_area=SimpleNamespace(draws=0),
        _content=SimpleNamespace(set_sensitive=lambda v: None),
        regions=[],
        calls=[],
    )
    s._handle_area.queue_draw = lambda: setattr(s._handle_area, "draws", s._handle_area.draws + 1)
    s.input_shape_combine_region = s.regions.append
    s._hit = lambda: ep.EdgePanel._hit(s)
    for key, value in extra.items():
        setattr(s, key, value)
    return s


def rects_of(region):
    out = []
    for i in range(region.num_rectangles()):
        r = region.get_rectangle(i)
        out.append((r.x, r.y, r.width, r.height))
    return out


# ---- in-place restyle -----------------------------------------------------------------


def test_apply_theme_restyles_the_handle(make_config):
    s = stub(make_config)
    s._restyle_handle = lambda: s.calls.append(("restyle", s._theme))
    theme = make_config(theme={"handle_style": {"shape": "bar"}}).theme
    ep.EdgePanel.apply_theme(s, theme)
    assert s.calls == [("restyle", theme)]


def test_restyle_resolves_then_resizes_relabels_replaces_and_reregions(make_config):
    s = stub(make_config, interaction=Interaction(drag=False), _last_rect=((1, 2, 3, 4),))
    s._theme = make_config(theme={"handle_style": {"size": 40}}).theme
    for name in ("_size_handle", "_sync_handle"):
        setattr(s, name, lambda name=name: s.calls.append(name))
    s._place_handle = lambda d: s.calls.append(("place", d))
    s._update_input_region = lambda d: s.calls.append(("region", d, s._last_rect))
    ep.EdgePanel._restyle_handle(s)
    assert (s._look.shape, s._look.size) == ("chevron", 40)  # auto: click only
    assert s.calls == ["_size_handle", "_sync_handle", ("place", 0.0), ("region", 0.0, None)]


@pytest.mark.parametrize(
    ("edge", "size"), [("bottom", (56, 14)), ("top", (56, 14)), ("left", (14, 56))]
)
def test_the_hit_target_size(make_config, edge, size):
    s = stub(make_config, edge=edge, handle=HandleSpec(size=40))
    ep.EdgePanel._size_handle(s)
    assert s._handle.set["size_request"] == size


@pytest.mark.parametrize(
    ("edge", "offset", "d", "expected"),
    [
        ("bottom", 30, 64.0, {"margin_start": (60,), "margin_end": (0,), "margin_bottom": (60,)}),
        ("top", 0, 0.0, {"margin_start": (0,), "margin_end": (0,), "margin_top": (0,)}),
        ("left", -20, 0.0, {"margin_top": (0,), "margin_bottom": (40,), "margin_start": (0,)}),
        ("right", 9999, 64.0, {"margin_top": (516,), "margin_bottom": (0,), "margin_end": (60,)}),
    ],
)
def test_place_handle_offsets_along_and_rides_across(make_config, edge, offset, d, expected):
    s = stub(make_config, edge=edge, handle=HandleSpec(offset=offset))
    ep.EdgePanel._place_handle(s, d)
    for key, value in expected.items():
        assert s._handle.set[key] == value, key
    assert s._handle_area.draws == 1


# ---- drawing ------------------------------------------------------------------------


def draw(s, w=44, h=14):
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    area = SimpleNamespace(get_allocation=lambda: SimpleNamespace(width=w, height=h))
    assert ep.EdgePanel._on_handle_draw(s, area, cairo.Context(surface)) is False
    surface.flush()
    return surface


def centre_pixel(surface):
    # bottom edge, collapsed, T = 10: the middle dot is centred on (22.5, 8.5), 5.5 px from the
    # screen edge, and covers pixel (22, 8) fully
    off = 8 * surface.get_stride() + 22 * 4
    return tuple(surface.get_data()[off : off + 4])


def test_the_handle_draws_the_rest_colour(make_config):
    assert centre_pixel(draw(stub(make_config))) == (0x84, 0x7F, 0x7B, 255)  # #7b7f84


def test_pointer_on_the_handle_draws_the_hover_colour(make_config):
    s = stub(make_config)
    s._handle.flags = Gtk.StateFlags.PRELIGHT
    assert centre_pixel(draw(s)) == (0xEA, 0xE8, 0xE6, 255)  # #e6e8ea


def test_a_peek_draws_the_hover_colour(make_config):
    s = stub(make_config, _hovered=True)
    assert centre_pixel(draw(s)) == (0xEA, 0xE8, 0xE6, 255)


def test_a_draw_error_is_logged_not_raised(make_config, caplog):
    s = stub(make_config)
    s._look = None
    draw(s)
    assert "drawing the handle of dock failed" in caplog.text


@pytest.mark.parametrize(
    ("edge", "d", "w", "h"), [("left", 32.0, 14, 44), ("bottom", 64.0, 44, 14)]
)
def test_the_draw_call_is_pinned(make_config, edge, d, w, h):
    """_on_handle_draw must pass exactly the look, morph, centre and band room to draw_handle."""
    handle = HandleSpec(shape="chevron")
    s = stub(make_config, edge=edge, handle=handle, _d=d)
    got = draw(s, w, h)
    t, look = s._theme, s._look
    want = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    draw_handle(
        cairo.Context(want),
        look.shape,
        look.size,
        look.weight,
        look.rgba,
        hd.morph(d, 64),
        edge,
        *hd.shape_centre(edge, w, h, t.thickness, d),
        hd.band_room(t.thickness),
    )
    want.flush()
    assert bytes(got.get_data()) == bytes(want.get_data())
    assert any(bytes(want.get_data()))  # something was drawn


def test_a_draw_error_is_logged_once_per_look(make_config, caplog):
    s = stub(make_config)
    s._look = None
    draw(s)
    draw(s)
    assert caplog.text.count("drawing the handle of dock failed") == 1
    s._restyle_handle = lambda: None
    s._size_handle = s._sync_handle = lambda: None
    s._place_handle = s._update_input_region = lambda d: None
    ep.EdgePanel._restyle_handle(s)  # a new look: errors are reported again
    assert s._draw_failed is False
    s._look = None
    draw(s)
    assert caplog.text.count("drawing the handle of dock failed") == 2


def test_the_handle_is_a_button_drawing_with_cairo(make_config):
    if not Gtk.init_check()[0]:
        pytest.skip("no display")
    s = stub(make_config)
    for name in ("_on_clicked", "_on_press", "_on_motion", "_on_release", "_on_handle_draw"):
        setattr(s, name, lambda *a: False)
    button = ep.EdgePanel._build_handle(s)
    assert isinstance(button, Gtk.Button) and button.get_name() == "handle"
    assert isinstance(button.get_child(), Gtk.DrawingArea)
    assert s._handle_area is button.get_child()
    area = button.get_child()
    assert not area.get_has_window()  # no GdkWindow of its own
    area.set_size_request(44, 14)  # sizing still works for a windowless area
    area.show()  # preferred size is 0 for an invisible widget
    assert area.get_preferred_width()[0] == 44
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 44, 14)
    assert area.emit("draw", cairo.Context(surface)) is False  # the panel's draw handler runs


def test_a_bad_look_fails_before_the_window_exists(make_config):
    # monitor=None: had __init__ reached the window code first, this would be an
    # AttributeError; the look is resolved before it, so the bad colour fails first
    spec = SimpleNamespace(edge="bottom", pos=680, length=560, depth=64, label="dock")
    with pytest.raises(ValueError, match="invalid colour 'red'"):
        ep.EdgePanel.__init__(
            SimpleNamespace(),
            spec,
            make_config().theme,
            None,
            0,
            "mon-x",
            handle=HandleSpec(color="red"),
        )
