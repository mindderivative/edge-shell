"""ShapeCanvas methods called on stand-ins: no window is ever created (that would draw)."""

from types import SimpleNamespace

import cairo
import pytest

pytest.importorskip("gi")
pytest.importorskip("fabric")

from shell.canvas.canvas import ShapeCanvas  # noqa: E402
from shell.canvas.painter import CanvasPainter  # noqa: E402
from shell.canvas.scene import PanelShape, Scene  # noqa: E402
from shell.canvas.style import style_for  # noqa: E402


class FakeArea:
    def __init__(self):
        self.calls = []

    def queue_draw(self):
        self.calls.append("all")

    def queue_draw_area(self, x, y, w, h):
        self.calls.append((x, y, w, h))


def stand_in(make_config, size=(400, 300), monitor_size=None):
    area = FakeArea()
    s = SimpleNamespace(area=area, _size_warned=False)
    s.live = monitor_size or size  # the monitor's live geometry; tests may change it
    s._monitor = SimpleNamespace(
        get_geometry=lambda: SimpleNamespace(width=s.live[0], height=s.live[1])
    )
    s._invalidate = lambda box: ShapeCanvas._invalidate(s, box)
    s._check_size = lambda: ShapeCanvas._check_size(s)
    s.painter = CanvasPainter(Scene(*size, 10, 14), style_for(make_config().theme), s._invalidate)
    return s


def test_invalidate_maps_boxes_to_queue_draw_area(make_config):
    s = stand_in(make_config)
    ShapeCanvas._invalidate(s, None)
    ShapeCanvas._invalidate(s, (10, 20, 110, 70))
    assert s.area.calls == ["all", (10, 20, 100, 50)]


def test_depth_change_queues_only_the_damaged_box(make_config):
    s = stand_in(make_config)
    ShapeCanvas.add_panel(s, 1, PanelShape("bottom", 100, 200, 64))
    s.area.calls.clear()
    ShapeCanvas.set_depth(s, 1, 30.0)
    assert s.area.calls == [(100 - 14, 300 - 10 - 30, 200 + 28, 10 + 30)]


def test_set_theme_queues_a_full_redraw_and_grows_the_pad(make_config):
    s = stand_in(make_config)
    ShapeCanvas.set_theme(s, make_config(theme={"shadow": {"enabled": True}}).theme)
    assert s.area.calls == ["all"] and s.painter.scene.pad == 24


def test_remove_panel_queues_its_footprint(make_config):
    s = stand_in(make_config)
    ShapeCanvas.add_panel(s, "k", PanelShape("top", 100, 100, 40))
    s.area.calls.clear()
    ShapeCanvas.remove_panel(s, "k")
    assert s.area.calls == [(86, 0, 128, 10)]  # collapsed footprint (depth 0)


def test_allocation_resizes_the_scene(make_config):
    s = stand_in(make_config)
    ShapeCanvas._on_allocate(s, None, SimpleNamespace(width=640, height=480))
    assert (s.painter.scene.width, s.painter.scene.height) == (640, 480)


def test_draw_handler_uses_the_cairo_clip_and_survives_errors(make_config, caplog):
    s = stand_in(make_config)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 400, 300)
    cr = cairo.Context(surface)
    assert ShapeCanvas._on_draw(s, None, cr) is False  # first draw: full
    surface.flush()
    assert surface.get_data()[3] == 255  # top-left pixel is frame

    def boom(_cr, _clip):
        raise RuntimeError("draw broke")

    s.painter.draw = boom
    assert ShapeCanvas._on_draw(s, None, cr) is False
    assert "shape canvas draw failed" in caplog.text


def test_size_mismatch_is_warned_once(make_config, caplog):
    s = stand_in(make_config, size=(400, 300), monitor_size=(1920, 1080))
    ShapeCanvas._check_size(s)
    ShapeCanvas._check_size(s)
    assert caplog.text.count("panels may be misaligned") == 1


def test_canvas_window_setup():
    from shell.canvas.canvas import CANVAS_WINDOW

    assert CANVAS_WINDOW == {
        "layer": "top",
        "anchor": "top left bottom right",
        "exclusivity": "none",  # then set_exclusive_zone(-1) in __init__
        "keyboard_mode": "none",
        "pass_through": True,
    }


def test_a_resolution_change_does_not_warn_once_the_allocation_matches(make_config, caplog):
    s = stand_in(make_config, size=(1920, 1080))
    s.live = (1280, 720)  # the monitor changed; the allocation has not arrived yet
    ShapeCanvas._on_allocate(s, None, SimpleNamespace(width=1280, height=720))
    ShapeCanvas._check_size(s)
    assert caplog.text.count("panels may be misaligned") == 0


def test_an_allocation_that_differs_from_the_live_monitor_warns_once(make_config, caplog):
    s = stand_in(make_config, size=(1920, 1080))
    s.live = (1280, 720)
    ShapeCanvas._on_allocate(s, None, SimpleNamespace(width=1000, height=700))
    ShapeCanvas._check_size(s)
    ShapeCanvas._check_size(s)
    assert caplog.text.count("panels may be misaligned") == 1


def test_a_changed_allocation_rearms_the_size_warning(make_config):
    s = stand_in(make_config, size=(1920, 1080))
    s._size_warned = True
    ShapeCanvas._on_allocate(s, None, SimpleNamespace(width=1920, height=1080))
    assert s._size_warned is True  # same size: stays latched
    ShapeCanvas._on_allocate(s, None, SimpleNamespace(width=1280, height=720))
    assert s._size_warned is False
