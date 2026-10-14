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
        self.focused = False
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

    def has_focus(self):
        return self.focused


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
    s._input_rects = lambda d: ep.EdgePanel._input_rects(s, d)
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


@pytest.mark.parametrize(
    ("edge", "d", "key", "inset"),
    [
        ("bottom", 0.0, "margin_bottom", 50),  # 64 - 14: the box ends on the band's inner edge
        ("bottom", 64.0, "margin_bottom", 114),  # 64 + 64 - 14: on the body's inner edge
        ("top", 32.0, "margin_top", 82),
        ("left", 0.0, "margin_start", 50),
        ("right", 64.0, "margin_end", 114),
    ],
)
def test_place_handle_on_a_thick_frame(make_config, edge, d, key, inset):
    # Gate B (thickness 64): a 14 px target at the body's inner edge, not the whole band
    s = stub(make_config, edge=edge, _theme=make_config(theme={"thickness": 64}).theme)
    ep.EdgePanel._size_handle(s)
    along_first = edge in ("top", "bottom")
    assert s._handle.set["size_request"] == ((44, 14) if along_first else (14, 44))
    ep.EdgePanel._place_handle(s, d)
    assert s._handle.set[key] == (inset,)


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


@pytest.mark.parametrize("thickness", [10, 64])
@pytest.mark.parametrize(("shape", "weight"), [("dots", 3), ("chevron", 3), ("chevron", 8)])
@pytest.mark.parametrize(
    ("edge", "d", "w", "h"), [("left", 32.0, 14, 44), ("bottom", 64.0, 44, 14)]
)
def test_the_draw_call_is_pinned(make_config, edge, d, w, h, thickness, shape, weight):
    """_on_handle_draw must pass exactly the look, morph, centre and shape room to draw_handle."""
    handle = HandleSpec(shape=shape, weight=weight)
    theme = make_config(theme={"thickness": thickness}).theme
    s = stub(make_config, edge=edge, handle=handle, _d=d, _theme=theme)
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
        hd.shape_room(t.thickness),
    )
    want.flush()
    assert bytes(got.get_data()) == bytes(want.get_data())
    assert any(bytes(want.get_data()))  # something was drawn


@pytest.mark.parametrize("edge", ["top", "bottom", "left", "right"])
def test_a_thick_frame_draws_like_the_default_extended(make_config, edge):
    # Gate B: collapsed on a 64 px frame the box sits on the band's inner edge, extended on
    # the body's; the shape inside it is the default frame's extended handle, byte for byte
    # (dots: no morph, so collapsed and extended draw the same shape)
    w, h = (44, 14) if edge in ("top", "bottom") else (14, 44)
    thick = make_config(theme={"thickness": 64}).theme
    default = draw(stub(make_config, edge=edge, _d=64.0), w, h)
    assert any(bytes(default.get_data()))
    for d in (0.0, 32.0, 64.0):
        got = draw(stub(make_config, edge=edge, _d=d, _theme=thick), w, h)
        assert bytes(got.get_data()) == bytes(default.get_data()), d


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


# ---- input region -------------------------------------------------------------------


def test_with_hover_the_input_region_is_unchanged(make_config):
    s = stub(make_config)
    ep.EdgePanel._update_input_region(s, 0.0)
    assert [rects_of(r) for r in s.regions] == [[(14, 48, 560, 26)]]  # body + hover zone
    ep.EdgePanel._update_input_region(s, 0.0)
    assert len(s.regions) == 1  # unchanged: not re-applied


def test_without_hover_only_the_hit_target_takes_input(make_config):
    s = stub(make_config, interaction=Interaction(hover=False))
    ep.EdgePanel._update_input_region(s, 0.0)
    assert rects_of(s.regions[-1]) == [(272, 60, 44, 14)]


def test_with_every_interaction_off_a_collapsed_panel_is_click_through(make_config):
    s = stub(make_config, interaction=Interaction(click=False, hover=False, drag=False))
    ep.EdgePanel._update_input_region(s, 0.0)
    assert rects_of(s.regions[-1]) == []
    ep.EdgePanel._update_input_region(s, 64.0)
    assert rects_of(s.regions[-1]) == [(14, 0, 560, 74)]  # the content still takes input


@pytest.mark.parametrize(
    "interaction", [ALL, Interaction(click=False, hover=False, drag=False)], ids=["all", "all-off"]
)
def test_the_input_region_is_reapplied_after_the_parent_allocate(
    make_config, monkeypatch, interaction
):
    s = stub(make_config, interaction=interaction)
    order = []

    def parent(_self, _alloc):
        order.append("parent")
        s.regions.append(None)  # Fabric resets the shape to the whole surface

    monkeypatch.setattr(ep.WaylandWindow, "do_size_allocate", parent)
    s._update_input_region = lambda d: ep.EdgePanel._update_input_region(s, d)
    ep.EdgePanel._update_input_region(s, 0.0)
    primed = s._last_rect
    assert primed is not None
    s.regions.clear()
    real = s.input_shape_combine_region
    s.input_shape_combine_region = lambda region: (order.append("region"), real(region))
    ep.EdgePanel.do_size_allocate(s, None)
    assert order == ["parent", "region"]
    expected = hd.input_rects(
        "bottom", 560, 64, 0.0, s._theme.thickness, s._theme.radius, s._theme.hover_zone,
        interaction, s._hit(), s._look.offset,
    )  # fmt: skip
    assert s.regions[0] is None and rects_of(s.regions[-1]) == [tuple(r) for r in expected]
    assert s._last_rect == primed


# ---- interaction flags --------------------------------------------------------------


def test_a_press_starts_no_drag_without_drag(make_config):
    s = stub(make_config, interaction=Interaction(drag=False), _press=None)
    event = SimpleNamespace(button=1, x_root=5.0, y_root=5.0)
    assert ep.EdgePanel._on_press(s, None, event) is False
    assert s._press is None
    s._interaction = ALL
    s._dragging = s._suppress_click = False
    ep.EdgePanel._on_press(s, None, event)
    assert s._press == (5.0, 5.0)


def test_a_click_toggles_only_with_click(make_config):
    toggles = []
    s = stub(make_config, interaction=Interaction(click=False), _suppress_click=False)
    s.toggle = lambda: toggles.append(1)
    ep.EdgePanel._on_clicked(s)
    assert toggles == []
    s._interaction = ALL
    ep.EdgePanel._on_clicked(s)
    assert toggles == [1]


def test_entering_does_not_peek_without_hover(make_config):
    s = stub(make_config, interaction=Interaction(hover=False), _dragging=False)
    s._retarget = lambda: s.calls.append("retarget")
    ep.EdgePanel._on_enter(s)
    assert s._hovered is False and s.calls == []
    s._interaction = ALL
    ep.EdgePanel._on_enter(s)
    assert s._hovered is True and s.calls == ["retarget"]


# ---- in-place updates ---------------------------------------------------------------


def test_set_handle_updates_in_place_and_drops_a_peek(make_config):
    s = stub(make_config, _hovered=True)
    s._restyle_handle = lambda: s.calls.append("restyle")
    s._retarget = lambda: s.calls.append(("retarget", s._hovered))
    new = (HandleSpec(shape="bar"), Interaction(hover=False))
    ep.EdgePanel.set_handle(s, *new)
    assert (s._handle_spec, s._interaction) == new
    assert s.calls == ["restyle", ("retarget", False)]


def test_set_handle_keeps_a_peek_that_hover_still_allows(make_config):
    s = stub(make_config, _hovered=True)
    s._restyle_handle = lambda: s.calls.append("restyle")
    s._retarget = lambda: s.calls.append("retarget")
    ep.EdgePanel.set_handle(s, HandleSpec(shape="bar"), ALL)
    assert s.calls == ["restyle"] and s._hovered is True


def test_turning_drag_off_mid_drag_lets_that_drag_finish(make_config, monkeypatch):
    monkeypatch.setattr(ep.GLib, "idle_add", lambda fn: None)
    depths = []
    s = stub(make_config, _dragging=True, _press=(100.0, 500.0), _press_depth=0.0)
    s._suppress_click = True
    s._tween = SimpleNamespace(jump_to=depths.append)
    s._fade = SimpleNamespace(jump_to=lambda value: None)
    s._clear_suppress = lambda: None
    s._finish_drag = lambda: ep.EdgePanel._finish_drag(s)
    s._restyle_handle = lambda: s.calls.append("restyle")
    s._retarget = lambda: s.calls.append(("retarget", s._dragging))
    ep.EdgePanel.set_handle(s, HandleSpec(), Interaction(drag=False))
    assert s.calls == ["restyle"]  # no retarget: the drag owns the depth until release
    event = SimpleNamespace(state=ep.Gdk.ModifierType.BUTTON1_MASK, x_root=100.0, y_root=450.0)
    assert ep.EdgePanel._on_motion(s, None, event) is True  # the drag goes on
    assert depths == [50.0]
    s._d = depths[-1]
    ep.EdgePanel._finish_drag(s)  # the release: 50 of 64 px snaps open
    assert (s._extended, s._dragging, s._press) == (True, False, None)
    assert s.calls == ["restyle", ("retarget", False)]


@pytest.mark.parametrize(
    ("interaction", "tooltip", "name", "focus"),
    [
        (ALL, "Expand dock", "Expand dock", True),
        (Interaction(click=False), "Drag to expand dock", "Drag to expand dock", False),
        (Interaction(click=False, drag=False), None, "dock handle", False),
    ],
)
def test_labels_and_keyboard_follow_click(make_config, interaction, tooltip, name, focus):
    s = stub(make_config, interaction=interaction)
    ep.EdgePanel._sync_handle(s)
    assert s._handle.set["tooltip_text"] == (tooltip,)
    assert s._handle.name == name
    assert s._handle.set["can_focus"] == (focus,)
    assert s._handle_area.draws == 1


def test_turning_drag_off_under_a_held_press_starts_no_drag(make_config):
    s = stub(
        make_config,
        interaction=Interaction(drag=False),
        _dragging=False,
        _press=(100.0, 500.0),
        _press_depth=0.0,
    )
    s._tween = SimpleNamespace(jump_to=lambda v: s.calls.append(("jump", v)))
    event = SimpleNamespace(state=ep.Gdk.ModifierType.BUTTON1_MASK, x_root=100.0, y_root=300.0)
    assert ep.EdgePanel._on_motion(s, None, event) is False  # far past the click threshold
    assert s._press is None and s._dragging is False and s.calls == []


def test_losing_click_drops_the_handle_focus(make_config):
    s = stub(make_config)
    s._restyle_handle = lambda: None
    s.set_focus = lambda w: s.calls.append(("focus", w))
    s._handle.focused = True
    ep.EdgePanel.set_handle(s, HandleSpec(), ALL)  # click kept: focus untouched
    assert s.calls == []
    s._handle.focused = False
    ep.EdgePanel.set_handle(s, HandleSpec(), Interaction(click=False))  # nothing to drop
    assert s.calls == []
    s._handle.focused = True
    ep.EdgePanel.set_handle(s, HandleSpec(), Interaction(click=False))  # focused: dropped
    assert s.calls == [("focus", None)]


def test_leaving_with_hover_off_still_settles(make_config):
    s = stub(make_config, interaction=Interaction(hover=False), _dragging=False, _hovered=True)
    s._retarget = lambda: s.calls.append(("retarget", s._hovered))
    ep.EdgePanel._on_leave(s, None, SimpleNamespace(detail=ep.Gdk.NotifyType.ANCESTOR))
    assert s._hovered is False and s.calls == [("retarget", False)]


def test_drag_off_and_click_on_one_press_toggles(make_config):
    toggles = []
    s = stub(
        make_config,
        interaction=Interaction(drag=False),
        _press=None,
        _dragging=False,
        _suppress_click=False,
    )
    s.toggle = lambda: toggles.append(1)
    press = SimpleNamespace(button=1, x_root=5.0, y_root=5.0)
    assert ep.EdgePanel._on_press(s, None, press) is False
    move = SimpleNamespace(state=ep.Gdk.ModifierType.BUTTON1_MASK, x_root=5.0, y_root=400.0)
    assert ep.EdgePanel._on_motion(s, None, move) is False  # no press tracked: no drag
    s._finish_drag = lambda: ep.EdgePanel._finish_drag(s)
    assert ep.EdgePanel._on_release(s, None, SimpleNamespace(button=1)) is False
    ep.EdgePanel._on_clicked(s)
    assert toggles == [1] and s._dragging is False and s._suppress_click is False


def test_set_state_on_an_all_off_panel_still_works(make_config):
    s = stub(make_config, interaction=Interaction(click=False, hover=False, drag=False))
    s._dragging = False
    s._retarget = lambda: s.calls.append(("retarget", s._extended))
    ep.EdgePanel.set_state(s, "extended")
    assert s.calls == [("retarget", True)]
    ep.EdgePanel.set_state(s, "collapsed")
    assert s.calls[-1] == ("retarget", False)
