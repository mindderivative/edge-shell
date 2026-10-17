"""Display-free tests for MonitorShell bookkeeping (windows are fakes)."""

from types import SimpleNamespace

import pytest

pytest.importorskip("gi")
pytest.importorskip("fabric")

import shell.monitors as mon_mod  # noqa: E402
from shell.config.diff import Change  # noqa: E402
from shell.panel_spec import PanelDefaults  # noqa: E402
from shell.widget import Widget, WidgetProps  # noqa: E402


class FakeWindow:
    def __init__(self, *args, raises=False, **kwargs):
        self.args, self.kwargs = args, kwargs
        self.destroyed = False
        self.raises = raises
        self.raised = 0
        self.title = "w"
        self.themes = []
        self.states = []
        self.handles = []
        self.natural = 200
        self.measured = 0
        self.opacity = []  # every set_opacity value (spec 21)
        self.inputs = []  # every set_input_enabled value

    def set_opacity(self, value):
        self.opacity.append(value)

    def set_input_enabled(self, enabled):
        self.inputs.append(enabled)

    def destroy(self):
        self.destroyed = True
        if self.raises:
            raise RuntimeError("already gone")

    def raise_to_top(self):
        self.raised += 1

    def apply_theme(self, theme):
        self.themes.append(theme)

    def set_state(self, state):
        self.states.append(state)

    def set_handle(self, handle, interaction):
        self.handles.append((handle, interaction))

    def get_title(self):
        return self.title

    def natural_length(self):
        self.measured += 1
        return self.natural


class FakeCanvas(FakeWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.shapes = {}
        self.depths = []

    def set_theme(self, theme):
        self.themes.append(theme)

    def add_panel(self, key, shape):
        self.shapes[key] = shape

    def remove_panel(self, key):
        self.shapes.pop(key, None)

    def set_depth(self, key, d):
        self.depths.append((key, d))


class FakeMonitor:
    """A Gdk.Monitor stand-in: geometry, plus the notify::geometry connection."""

    def __init__(self, width=1920, height=1080):
        self.width, self.height = width, height
        self.scale = 1
        self.handlers = {}
        self.disconnect_raises = False

    def get_geometry(self):
        return SimpleNamespace(x=0, y=0, width=self.width, height=self.height)

    def connect(self, signal, fn):
        self.handlers[len(self.handlers) + 1] = (signal, fn)
        return len(self.handlers)

    def get_scale_factor(self):
        return self.scale

    def disconnect(self, handler):
        if self.disconnect_raises:
            raise RuntimeError("monitor gone")
        del self.handlers[handler]


MONITOR = FakeMonitor()


def bare_shell(windows, panels=(), unregister=None):
    shell = mon_mod.MonitorShell.__new__(mon_mod.MonitorShell)
    shell.name = "HDMI-A-1"
    shell.windows = list(windows)
    shell.panels = list(panels)
    shell._resolved = [None] * len(shell.panels)
    shell._handles = [None] * len(shell.panels)
    shell._contents = [None] * len(shell.panels)
    shell._failed = {}
    shell.canvas = FakeCanvas()
    shell.strips = []
    shell._closed = False
    shell._unregister = unregister or (lambda _w: None)
    shell.monitor = FakeMonitor()
    shell._monitor_handlers = []
    shell._measure_id = shell._relayout_id = shell._reserve_id = 0
    shell._fade = None
    shell._raises_pending = shell._ready_id = 0
    shell._detached = False
    return shell


def test_close_unregisters_then_destroys_every_window():
    seen = []
    wins = [FakeWindow(), FakeWindow()]

    def unregister(w):
        seen.append((w, w.destroyed))

    shell = bare_shell(wins, unregister=unregister)
    shell.close()
    assert [w for w, _ in seen] == wins
    assert all(not destroyed for _, destroyed in seen)  # unregistered before destroy
    assert all(w.destroyed for w in wins)
    assert shell.windows == [] and shell.panels == []


def test_destroy_panel_unregisters_it():
    panel = FakeWindow()
    gone = []
    shell = bare_shell([panel], [panel], unregister=gone.append)
    shell._destroy(panel)
    assert gone == [panel] and panel.destroyed
    assert shell.windows == []


def test_unregister_failure_does_not_block_destroy():
    def boom(_w):
        raise ValueError("not in list")

    win = FakeWindow()
    shell = bare_shell([win], unregister=boom)
    shell.close()
    assert win.destroyed


def test_destroy_error_is_contained():
    shell = bare_shell([FakeWindow(raises=True), FakeWindow()])
    shell.close()  # must not raise
    assert shell.windows == []


def test_raise_panels_raises_only_live_panels():
    a, b = FakeWindow(), FakeWindow()
    shell = bare_shell([a, b], [a, None, b])  # None = a panel hidden by the layout rules
    assert shell._raise_panels() is False  # one-shot GLib source
    assert (a.raised, b.raised) == (1, 1)


def test_raise_one_skips_a_panel_that_was_removed():
    a, b = FakeWindow(), FakeWindow()
    shell = bare_shell([a, b], [a])  # b was rebuilt or removed during the delay
    assert shell._raise_one(b) is False and b.raised == 0
    assert shell._raise_one(a) is False and a.raised == 1


# ---- building a monitor (fakes for every window) ------------------------------------


@pytest.fixture
def build(monkeypatch, make_config, fake_registry):
    """build(monitors, theme=None) -> (shell, tracked windows, timers)."""
    monkeypatch.delenv("EDGE_SHELL_RAISE_MS", raising=False)
    monkeypatch.setattr(mon_mod, "ShapeCanvas", FakeCanvas)
    monkeypatch.setattr(mon_mod, "FrameEdge", FakeWindow)
    real_panel_class = mon_mod.panel_class

    def fake_panel_class(geo):
        # a fake named after the real window class: which class a geometry gets stays testable
        return type(real_panel_class(geo).__name__, (FakeWindow,), {})

    monkeypatch.setattr(mon_mod, "panel_class", fake_panel_class)
    monkeypatch.setattr(mon_mod.MonitorShell, "_check_monitor", lambda self, w: None)
    timers, idles, removed = [], [], []
    monkeypatch.setattr(
        mon_mod.GLib, "timeout_add", lambda ms, fn, *a: timers.append((ms, fn, a)) or len(timers)
    )
    monkeypatch.setattr(mon_mod.GLib, "idle_add", lambda fn: idles.append(fn) or 100 + len(idles))
    monkeypatch.setattr(mon_mod.GLib, "source_remove", removed.append)

    def _build(monitors, theme=None, monitor=None, on_layout=None, on_error=None, on_settings=None):
        tracked = []
        cfg = make_config(monitors=monitors, theme=theme)
        shell = mon_mod.MonitorShell(
            "HDMI-A-1",
            monitor or FakeMonitor(),
            cfg,
            tracked.append,
            on_layout=on_layout,
            on_error=on_error,
            on_settings=on_settings,
        )
        shell.test_idles, shell.test_removed = idles, removed
        return shell, tracked, timers

    return _build


def edge(*panels, theme=None):
    return {"HDMI-A-1": {"shell": "edge", "panels": list(panels), "theme": theme or {}}}


def test_every_panel_gets_the_settings_opener(build):
    def opener():
        return None

    shell, _, _ = build(
        edge(
            {"panel": "edge", "name": "dock", "widget": "dock"},
            {"panel": "edge", "name": "clock", "widget": "clock"},
        ),
        on_settings=opener,
    )
    assert [p.kwargs["on_settings"] for p in shell.panels] == [opener, opener]
    shell, _, _ = build(edge({"panel": "edge", "name": "dock", "widget": "dock"}))
    assert shell.panels[0].kwargs["on_settings"] is None


def test_a_corner_panel_gets_the_settings_opener(build, corner_registry):
    def opener():
        return None

    shell, _, _ = build(
        edge(
            {"panel": "corner", "name": "box", "widget": "box"},
            {"panel": "edge", "name": "dock", "widget": "dock"},
        ),
        on_settings=opener,
    )
    assert [p.kwargs["on_settings"] for p in shell.panels] == [opener, opener]
    assert [type(p).__name__ for p in shell.panels] == ["CornerPanel", "EdgePanel"]


def test_canvas_first_then_strips_then_panels(build):
    shell, tracked, _ = build(edge({"panel": "edge", "name": "dock", "widget": "dock"}))
    assert tracked[0] is shell.canvas
    assert [type(w) for w in tracked[1:5]] == [FakeWindow] * 4
    assert tracked[5] is shell.panels[0] and type(tracked[5]).__name__ == "EdgePanel"


def test_panels_get_a_resolved_pos_a_scene_shape_and_a_depth_callback(build):
    shell, _, _ = build(
        edge(
            {"panel": "edge", "name": "dock", "widget": "dock"},
            {"panel": "edge", "name": "bar", "widget": "bar"},
        )
    )
    dock, bar = shell.panels
    assert dock.args[0].pos == 680 and bar.args[0].pos == 600  # centred dock resolved to 680
    assert {s.edge for s in shell.canvas.shapes.values()} == {"bottom", "right"}
    dock.kwargs["on_depth"](12.5)
    assert shell.canvas.depths == [(dock.scene_key, 12.5)]


def test_two_centred_panels_on_one_edge_are_both_shown(build):
    shell, _, _ = build(
        edge(
            {"panel": "edge", "name": "dock", "widget": "dock"},
            {"panel": "edge", "name": "dock 2", "widget": "dock", "length": 300},
        )
    )
    a, b = shell.panels
    assert a.args[0].pos + 560 + 14 + 14 + 8 == b.args[0].pos  # packed: joins + default gap
    assert shell.layout_warnings == [] and len(shell.canvas.shapes) == 2


def test_panel_that_breaks_the_layout_rules_is_hidden_and_reported(build):
    shell, _, _ = build(
        edge(
            {"panel": "edge", "name": "dock", "widget": "dock"},
            {"panel": "edge", "name": "dock 2", "widget": "dock", "pos": 700},
        )
    )
    assert shell.panels[1] is None and len(shell.canvas.shapes) == 1
    assert "monitors.HDMI-A-1.panels.1 (dock): overlaps" in shell.layout_warnings[0]


def test_init_schedules_primary_and_fallback_raise(build):
    shell, _, timers = build(edge({"panel": "edge", "name": "dock", "widget": "dock"}))
    assert [ms for ms, _, _ in timers] == [mon_mod.RAISE_DELAY_MS, mon_mod.RAISE_FALLBACK_MS]
    panel = shell.panels[0]
    for _, fn, a in timers:
        assert fn(*a) is False
    assert panel.raised == 2
    shell.close()
    for _, fn, a in timers:
        fn(*a)
    assert panel.raised == 2  # no work after close


def test_init_without_panels_schedules_no_raise(build):
    _, _, timers = build(edge())
    assert timers == []


def test_raise_switch_off_schedules_nothing(build, monkeypatch):
    monkeypatch.setenv("EDGE_SHELL_RAISE_MS", "0")
    _, _, timers = build(edge({"panel": "edge", "name": "dock", "widget": "dock"}))
    assert timers == []


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({}, (500, 2000)),
        ({"EDGE_SHELL_RAISE_MS": "0"}, ()),
        ({"EDGE_SHELL_RAISE_MS": "x"}, (500, 2000)),
    ],
)
def test_raise_delays_switch(env, expected):
    assert mon_mod.raise_delays(env) == expected


# ---- reload ------------------------------------------------------------------------


def test_restyle_redraws_the_canvas_with_the_monitor_theme(build, make_config):
    shell, _, _ = build(edge({"panel": "edge", "name": "dock", "widget": "dock"}))
    new = make_config(
        theme={"shadow": {"enabled": True}},
        monitors=edge(
            {"panel": "edge", "name": "dock", "widget": "dock"}, theme={"shadow": {"elevation": 90}}
        ),
    )
    shell.apply(new, [Change("restyle", "HDMI-A-1")])
    (theme,) = shell.canvas.themes
    assert theme.shadow.enabled and theme.shadow.elevation == 90
    assert shell.panels[0].themes == [theme]


def test_restyle_resizes_the_strips_in_place_with_the_monitor_theme(build, make_config):
    shell, tracked, _ = build(edge({"panel": "edge", "name": "dock", "widget": "dock"}))
    strips = list(shell.strips)
    assert len(strips) == 4 and all(s in tracked for s in strips)
    new = make_config(
        theme={"border": {"enabled": True, "width": 3}},
        monitors=edge(
            {"panel": "edge", "name": "dock", "widget": "dock"}, theme={"border": {"width": 4}}
        ),
    )
    shell.apply(new, [Change("restyle", "HDMI-A-1")])
    assert shell.strips == strips and not any(s.destroyed for s in strips)  # no rebuild
    assert all(len(s.themes) == 1 and s.themes[0].border.width == 4 for s in strips)


def test_state_change_retargets_without_rebuilding(build, make_config):
    shell, _, _ = build(edge({"panel": "edge", "name": "dock", "widget": "dock"}))
    dock = shell.panels[0]
    shell.apply(
        make_config(
            monitors=edge({"panel": "edge", "name": "dock", "widget": "dock", "state": "collapsed"})
        ),
        [Change("panel-state", "HDMI-A-1", 0)],
    )
    assert shell.panels[0] is dock and dock.states == ["collapsed"] and not dock.destroyed


def test_geometry_change_rebuilds_and_moves_the_scene_shape(build, make_config):
    shell, _, timers = build(edge({"panel": "edge", "name": "dock", "widget": "dock"}))
    old = shell.panels[0]
    shell.apply(
        make_config(
            monitors=edge({"panel": "edge", "name": "dock", "widget": "dock", "length": 300})
        ),
        [Change("panel-rebuild", "HDMI-A-1", 0)],
    )
    new = shell.panels[0]
    assert old.destroyed and new is not old
    assert list(shell.canvas.shapes) == [new.scene_key]
    assert shell.canvas.shapes[new.scene_key].length == 300
    assert timers[-1][0] == mon_mod.RAISE_DELAY_MS  # the rebuilt panel is re-raised once


def test_add_and_remove_keep_canvas_and_panels_in_step(build, make_config):
    shell, _, _ = build(edge({"panel": "edge", "name": "dock", "widget": "dock"}))
    shell.apply(
        make_config(
            monitors=edge(
                {"panel": "edge", "name": "dock", "widget": "dock"},
                {"panel": "edge", "name": "clock", "widget": "clock"},
            )
        ),
        [],
    )
    assert [p.args[0].widget for p in shell.panels] == ["dock", "clock"]
    assert len(shell.canvas.shapes) == 2
    clock = shell.panels[1]
    shell.apply(make_config(monitors=edge({"panel": "edge", "name": "dock", "widget": "dock"})), [])
    assert clock.destroyed and len(shell.panels) == 1 and len(shell.canvas.shapes) == 1


def test_a_neighbour_change_rebuilds_the_panel_it_unhides(build, make_config):
    shell, _, _ = build(
        edge(
            {"panel": "edge", "name": "dock", "widget": "dock"},
            {"panel": "edge", "name": "dock 2", "widget": "dock", "pos": 700},
        )
    )
    assert shell.panels[1] is None
    shell.apply(
        make_config(
            monitors=edge(
                {"panel": "edge", "name": "dock", "widget": "dock", "align": "end"},
                {"panel": "edge", "name": "dock 2", "widget": "dock", "pos": 700},
            )
        ),
        [Change("panel-rebuild", "HDMI-A-1", 0)],
    )
    assert shell.panels[1] is not None and shell.layout_warnings == []
    assert len(shell.canvas.shapes) == 2


def test_a_panel_that_fails_to_build_is_left_out_and_named(build, make_config, monkeypatch, caplog):
    """Spec 4: a widget build failure is logged and that panel skipped (no window, no scene
    shape); the monitor and its other panels stay; the failure names the panel."""
    shell, tracked, _ = build(edge({"panel": "edge", "name": "Dock", "widget": "dock"}))
    dock = shell.panels[0]

    def explode(*a, **k):
        raise RuntimeError("widget broke")

    real = mon_mod.widget_class
    monkeypatch.setattr(mon_mod, "widget_class", lambda w: explode if w == "clock" else real(w))
    shell.apply(
        make_config(
            monitors=edge(
                {"panel": "edge", "name": "Dock", "widget": "dock"},
                {"panel": "edge", "name": "Top clock", "widget": "clock"},
            )
        ),
        [Change("panel-add", "HDMI-A-1", 1)],
    )
    assert shell.panels == [dock, None] and not dock.destroyed
    assert len(shell.canvas.shapes) == 1  # the failed panel left no shape behind
    assert shell.build_failures == [
        "HDMI-A-1: panel 'Top clock' (clock) could not be built and is not shown: widget broke"
    ]
    assert "building panel 1 'Top clock' (clock) on HDMI-A-1 failed" in caplog.text
    assert "RuntimeError: widget broke" in caplog.text  # with the traceback
    monkeypatch.setattr(mon_mod, "widget_class", real)
    same = edge(
        {"panel": "edge", "name": "Dock", "widget": "dock"},
        {"panel": "edge", "name": "Top clock", "widget": "clock"},
    )
    shell.apply(make_config(monitors=same), [])  # the same entry: not tried again
    assert shell.panels[1] is None and len(shell.build_failures) == 1
    renamed = edge(
        {"panel": "edge", "name": "Dock", "widget": "dock"},
        {"panel": "edge", "name": "Clock", "widget": "clock"},
    )
    shell.apply(make_config(monitors=renamed), [])  # the entry changed: tried again
    assert shell.panels[1] is not None and shell.build_failures == []


def test_a_failure_while_the_monitor_is_built_keeps_the_frame(
    make_config, monkeypatch, fake_registry
):
    def explode(*a, **k):
        raise RuntimeError("panel broke")

    monkeypatch.setattr(mon_mod, "ShapeCanvas", FakeCanvas)
    monkeypatch.setattr(mon_mod, "FrameEdge", FakeWindow)
    monkeypatch.setattr(mon_mod, "panel_class", lambda _geo: FakeWindow)
    monkeypatch.setattr(mon_mod, "widget_class", lambda _w: explode)
    monkeypatch.setattr(mon_mod.MonitorShell, "_check_monitor", lambda self, w: None)
    monkeypatch.setattr(mon_mod.GLib, "timeout_add", lambda *a: 1)
    monkeypatch.setattr(mon_mod.GLib, "idle_add", lambda *a: 1)
    registered = []
    cfg = make_config(monitors=edge({"panel": "edge", "name": "Dock", "widget": "dock"}))
    shell = mon_mod.MonitorShell("HDMI-A-1", MONITOR, cfg, registered.append)
    assert len(registered) == 5 and shell.panels == [None]  # canvas + 4 strips, no panel
    assert shell.build_failures and "'Dock'" in shell.build_failures[0]


def test_failed_construction_closes_everything_already_built(
    make_config, monkeypatch, fake_registry
):
    def explode(*a, **k):
        raise RuntimeError("layout broke")

    monkeypatch.setattr(mon_mod, "ShapeCanvas", FakeCanvas)
    monkeypatch.setattr(mon_mod, "FrameEdge", FakeWindow)
    monkeypatch.setattr(mon_mod, "panel_class", lambda _geo: FakeWindow)
    monkeypatch.setattr(mon_mod, "layout_monitor", explode)  # not a widget: nothing contains it
    monkeypatch.setattr(mon_mod.MonitorShell, "_check_monitor", lambda self, w: None)
    monkeypatch.setattr(mon_mod.GLib, "timeout_add", lambda *a: 1)
    monkeypatch.setattr(mon_mod.GLib, "idle_add", lambda *a: 1)
    registered, unregistered = [], []
    cfg = make_config(monitors=edge({"panel": "edge", "name": "dock", "widget": "dock"}))
    with pytest.raises(RuntimeError, match="layout broke"):
        mon_mod.MonitorShell("HDMI-A-1", MONITOR, cfg, registered.append, unregistered.append)
    assert len(registered) == 5  # canvas + 4 strips were on screen
    assert unregistered == registered
    assert all(w.destroyed for w in registered)


# ---- EdgePanel.raise_to_top (plain function called on a stand-in) --------------------


def _panel_stub(dragging=False, hovered=True):
    calls = []
    return SimpleNamespace(
        _dragging=dragging,
        _hovered=hovered,
        _d=3.0,
        _last_rect=(1, 2, 3, 4),
        hide=lambda: calls.append("hide"),
        show_all=lambda: calls.append("show_all"),
        _update_input_region=lambda d: calls.append(("region", d)),
        calls=calls,
    )


def test_raise_to_top_remaps_resets_hover_and_reapplies_region():
    from shell.edge_panel import EdgePanel

    p = _panel_stub()
    EdgePanel.raise_to_top(p)
    assert p.calls == ["hide", "show_all", ("region", 3.0)]
    assert p._hovered is False and p._last_rect is None


def test_raise_to_top_never_interrupts_a_drag():
    from shell.edge_panel import EdgePanel

    p = _panel_stub(dragging=True)
    EdgePanel.raise_to_top(p)
    assert p.calls == []


def test_the_monitor_gap_spaces_slotted_panels(build):
    mons = edge(
        {"panel": "edge", "name": "clock", "widget": "clock", "align": "start"},
        {"panel": "edge", "name": "clock 2", "widget": "clock", "align": "start"},
    )
    mons["HDMI-A-1"]["layout"] = {"gap": 30}
    shell, _, _ = build(mons)
    a, b = (p.args[0] for p in shell.panels)
    assert b.pos - (a.pos + a.length) == 14 + 14 + 30


def test_a_gap_change_moves_the_neighbours(build, make_config):
    two = edge(
        {"panel": "edge", "name": "clock", "widget": "clock", "align": "start"},
        {"panel": "edge", "name": "clock 2", "widget": "clock", "align": "start"},
    )
    shell, _, _ = build(two)
    first, second = shell.panels
    wider = edge(
        {"panel": "edge", "name": "clock", "widget": "clock", "align": "start"},
        {"panel": "edge", "name": "clock 2", "widget": "clock", "align": "start"},
    )
    wider["HDMI-A-1"]["layout"] = {"gap": 40}
    shell.apply(make_config(monitors=wider), [Change("relayout", "HDMI-A-1")])
    assert shell.panels[0] is first and not first.destroyed  # did not move: kept
    assert second.destroyed and shell.panels[1].args[0].pos == second.args[0].pos + 32


# ---- "content" measurement ----------------------------------------------------------


def test_content_panels_are_measured_when_idle_then_laid_out_again(build):
    reports = []
    shell, _, _ = build(
        edge({"panel": "edge", "name": "dock", "widget": "dock", "length": "content"}),
        on_layout=reports.append,
    )
    first = shell.panels[0]
    assert first.args[0].length == 560  # the widget's default until measured
    assert len(shell.test_idles) == 1 and reports == []
    first.natural = 300
    assert shell.test_idles[0]() is False  # one-shot
    rebuilt = shell.panels[0]
    assert first.destroyed and rebuilt.args[0].length == 300
    assert reports == [shell]
    rebuilt.natural = 300
    assert len(shell.test_idles) == 2  # the rebuilt panel is measured again
    assert shell.test_idles[1]() is False
    assert shell.panels[0] is rebuilt  # same size: nothing rebuilt
    assert reports == [shell, shell]  # but every measurement reports the layout


def test_no_measurement_without_content_panels(build):
    shell, _, _ = build(
        edge(
            {"panel": "edge", "name": "dock", "widget": "dock"},
            {"panel": "edge", "name": "clock", "widget": "clock", "length": "fill"},
        )
    )
    assert shell.test_idles == []


def test_a_measurement_belongs_to_its_widget(build, make_config):
    shell, _, _ = build(
        edge({"panel": "edge", "name": "dock", "widget": "dock", "length": "content"})
    )
    shell.panels[0].natural = 300
    shell.test_idles[0]()
    shell.apply(
        make_config(
            monitors=edge(
                {"panel": "edge", "name": "clock", "widget": "clock", "length": "content"}
            )
        ),
        [],
    )
    assert shell.panels[0].args[0].length == 168  # the clock's default, not the dock's 300


def test_measuring_after_close_does_nothing(build):
    shell, _, _ = build(
        edge({"panel": "edge", "name": "dock", "widget": "dock", "length": "content"})
    )
    pending = shell.test_idles[0]
    shell.close()
    assert 101 in shell.test_removed  # the pending idle was cancelled
    assert pending() is False


def test_only_panels_built_since_the_last_measurement_are_measured(build, make_config):
    dock = {"panel": "edge", "name": "dock", "widget": "dock", "length": "content"}
    clock = {"panel": "edge", "name": "clock", "widget": "clock", "length": "content"}
    shell, _, _ = build(edge(dock, clock))
    shell.test_idles[0]()  # both measured at 200 px: both rebuilt
    shell.test_idles[1]()  # the rebuilt pair is measured once: nothing changes
    kept = shell.panels[0]
    seen = kept.measured
    shell.apply(
        make_config(monitors=edge(dock, {**clock, "min_length": 250})),
        [Change("panel-rebuild", "HDMI-A-1", 1)],
    )
    assert shell.panels[0] is kept and len(shell.test_idles) == 3
    assert shell.test_idles[2]() is False
    assert kept.measured == seen  # not rebuilt: not measured again
    assert shell.panels[1].measured == 1 and shell.panels[1].args[0].length == 250


def test_a_restyle_measures_every_content_panel_again(build, make_config):
    panels = (
        {"panel": "edge", "name": "dock", "widget": "dock", "length": "content"},
        {"panel": "edge", "name": "clock", "widget": "clock"},
    )
    shell, _, _ = build(edge(*panels))
    shell.test_idles[0]()  # measured: rebuilt at 200 px
    shell.test_idles[1]()  # settled
    kept = shell.panels[0]
    kept.natural = 260  # the new theme's font is larger
    shell.apply(
        make_config(theme={"accent": "#112233"}, monitors=edge(*panels)),
        [Change("restyle", "HDMI-A-1")],
    )
    assert shell.panels[0] is kept and len(shell.test_idles) == 3
    shell.test_idles[2]()
    assert kept.destroyed and shell.panels[0].args[0].length == 260


def test_a_measurement_that_changes_nothing_still_reports_the_layout(build, make_config):
    panels = (
        {"panel": "edge", "name": "dock", "widget": "dock", "length": "content"},
        {"panel": "edge", "name": "clock", "widget": "clock"},
    )
    reports = []
    shell, _, _ = build(edge(*panels), on_layout=reports.append)
    shell.test_idles[0]()  # measured: rebuilt
    shell.test_idles[1]()  # settled
    kept = shell.panels[0]
    reports.clear()
    shell.apply(
        make_config(theme={"accent": "#112233"}, monitors=edge(*panels)),
        [Change("restyle", "HDMI-A-1")],
    )
    assert len(shell.test_idles) == 3
    shell.test_idles[2]()  # same natural size as before
    assert shell.panels[0] is kept and reports == [shell]


def test_a_measurement_with_nothing_to_measure_still_reports_the_layout(build):
    reports = []
    shell, _, _ = build(
        edge({"panel": "edge", "name": "dock", "widget": "dock", "length": "content"}),
        on_layout=reports.append,
    )
    shell._to_measure = lambda: []  # e.g. the panels were hidden in between
    assert shell._measure() is False
    assert reports == [shell]


def test_a_failing_measurement_is_logged_and_reported(build, monkeypatch, caplog):
    errors, reports = [], []
    shell, _, _ = build(
        edge({"panel": "edge", "name": "dock", "widget": "dock", "length": "content"}),
        on_layout=reports.append,
        on_error=errors.append,
    )
    shell.panels[0].natural = 300

    def explode(*a, **k):
        raise RuntimeError("layout broke")

    monkeypatch.setattr(mon_mod, "layout_monitor", explode)  # the re-layout raises
    assert shell.test_idles[0]() is False  # never raises into the main loop
    assert errors == [shell] and reports == []
    assert "layout broke" in caplog.text


def test_a_failing_error_handler_does_not_escape_the_measurement(build, monkeypatch, caplog):
    def bad_handler(_shell):
        raise RuntimeError("handler broke")

    shell, _, _ = build(
        edge({"panel": "edge", "name": "dock", "widget": "dock", "length": "content"}),
        on_error=bad_handler,
    )
    shell.panels[0].natural = 300

    def explode(*a, **k):
        raise RuntimeError("layout broke")

    monkeypatch.setattr(mon_mod, "layout_monitor", explode)
    assert shell.test_idles[0]() is False
    assert "handler broke" in caplog.text
    assert shell.measure_pending is False


# ---- monitor geometry ---------------------------------------------------------------


def test_a_resolution_change_relayouts_once_it_settles(build):
    reports = []
    monitor = FakeMonitor()
    shell, _, timers = build(
        edge({"panel": "edge", "name": "dock", "widget": "dock"}),
        monitor=monitor,
        on_layout=reports.append,
    )
    dock = shell.panels[0]
    assert dock.args[0].pos == 680
    ((signal, handler),) = monitor.handlers.values()
    assert signal == "notify::geometry"
    monitor.width, monitor.height = 1280, 720
    handler(monitor, None)
    handler(monitor, None)  # a burst: the first timer is replaced
    relayouts = [t for t in timers if t[0] == mon_mod.RELAYOUT_DELAY_MS]
    assert len(relayouts) == 2 and len(shell.test_removed) == 1
    assert relayouts[-1][1]() is False
    assert dock.destroyed and shell.panels[0].args[0].pos == (1280 - 560) // 2  # re-centred
    assert reports == [shell]


def test_a_relayout_is_logged(build, caplog):
    caplog.set_level("DEBUG")
    monitor = FakeMonitor()
    shell, _, timers = build(
        edge({"panel": "edge", "name": "dock", "widget": "dock"}), monitor=monitor
    )
    ((_, handler),) = monitor.handlers.values()
    monitor.width, monitor.height = 1280, 720
    handler(monitor, None)
    timers[-1][1]()
    assert "re-laying out HDMI-A-1 for 1280x720" in caplog.text


def test_close_disconnects_from_the_monitor(build):
    monitor = FakeMonitor()
    shell, _, _ = build(edge({"panel": "edge", "name": "dock", "widget": "dock"}), monitor=monitor)
    assert len(monitor.handlers) == 1
    shell.close()
    assert monitor.handlers == {}


def test_close_cancels_a_pending_relayout(build):
    reports = []
    monitor = FakeMonitor()
    shell, _, timers = build(
        edge({"panel": "edge", "name": "dock", "widget": "dock"}),
        monitor=monitor,
        on_layout=reports.append,
    )
    dock = shell.panels[0]
    ((_, handler),) = monitor.handlers.values()
    monitor.width, monitor.height = 1280, 720
    handler(monitor, None)
    timer_id = len(timers)
    pending = timers[-1][1]
    shell.close()
    assert timer_id in shell.test_removed
    assert pending() is False
    assert shell.panels == [] and reports == [] and dock.destroyed


def test_close_destroys_every_window_even_if_the_monitor_disconnect_raises(build):
    monitor = FakeMonitor()
    shell, tracked, _ = build(
        edge({"panel": "edge", "name": "dock", "widget": "dock"}), monitor=monitor
    )
    monitor.disconnect_raises = True
    shell.close()
    assert tracked and all(w.destroyed for w in tracked)


def test_a_zero_geometry_is_ignored(build, caplog):
    caplog.set_level("DEBUG")
    reports = []
    monitor = FakeMonitor()
    shell, _, timers = build(
        edge({"panel": "edge", "name": "dock", "widget": "dock"}),
        monitor=monitor,
        on_layout=reports.append,
    )
    dock = shell.panels[0]
    ((_, handler),) = monitor.handlers.values()
    monitor.width = monitor.height = 0  # what an unplugged monitor reports
    handler(monitor, None)
    assert timers[-1][0] == mon_mod.RELAYOUT_DELAY_MS and timers[-1][1]() is False
    assert shell.panels[0] is dock and not dock.destroyed  # no 0 px layout, no warnings
    assert shell.layout_warnings == [] and reports == []
    assert "ignoring 0x0 geometry of HDMI-A-1" in caplog.text


def test_a_zero_geometry_blocks_every_layout_path(build, make_config):
    reports = []
    monitor = FakeMonitor()
    shell, _, _ = build(
        edge(
            {"panel": "edge", "name": "dock", "widget": "dock", "length": "content"},
            {"panel": "edge", "name": "clock", "widget": "clock"},
        ),
        monitor=monitor,
        on_layout=reports.append,
    )
    before = list(shell.panels)
    monitor.width = monitor.height = 0  # unplugged, the hot-plug sync has not closed us yet
    shell.panels[0].natural = 300
    assert shell.test_idles[0]() is False  # a pending measurement
    shell.apply(
        make_config(
            monitors=edge(
                {"panel": "edge", "name": "dock", "widget": "dock"},
                {"panel": "edge", "name": "clock", "widget": "clock"},
            )
        ),
        [],
    )
    assert shell.panels == before and not any(p.destroyed for p in before)
    assert shell.layout_warnings == []


def test_a_failing_relayout_is_logged_and_reported(build, monkeypatch, caplog):
    errors, reports = [], []
    monitor = FakeMonitor()
    shell, _, timers = build(
        edge({"panel": "edge", "name": "dock", "widget": "dock"}),
        monitor=monitor,
        on_layout=reports.append,
        on_error=errors.append,
    )
    ((_, handler),) = monitor.handlers.values()

    def explode(*a, **k):
        raise RuntimeError("layout broke")

    monkeypatch.setattr(mon_mod, "layout_monitor", explode)  # the re-layout raises
    monitor.width, monitor.height = 1280, 720
    handler(monitor, None)
    assert timers[-1][1]() is False  # never raises into the main loop
    assert errors == [shell] and reports == []
    assert "layout broke" in caplog.text


def _resize(monitor, handler, timers, width, height):
    monitor.width, monitor.height = width, height
    handler(monitor, None)
    return timers[-1][1]


def test_shrinking_hides_a_panel_and_growing_brings_it_back(build):
    reports = []
    monitor = FakeMonitor()
    shell, _, timers = build(
        edge(
            {"panel": "edge", "name": "dock", "widget": "dock"},
            {"panel": "edge", "name": "dock 2", "widget": "dock", "pos": 1300},
        ),
        monitor=monitor,
        on_layout=reports.append,
    )
    ((_, handler),) = monitor.handlers.values()
    first = shell.panels[1]
    assert first is not None and shell.layout_warnings == []
    _resize(monitor, handler, timers, 1000, 700)()
    assert shell.panels[1] is None and first.destroyed
    assert shell.layout_warnings and len(reports) == 1
    _resize(monitor, handler, timers, 1920, 1080)()
    assert shell.panels[1] is not None and shell.panels[1] is not first
    assert shell.layout_warnings == [] and reports == [shell, shell]


def test_a_start_aligned_panel_is_not_rebuilt_by_a_resize(build):
    monitor = FakeMonitor()
    shell, _, timers = build(
        edge(
            {
                "panel": "edge",
                "name": "dock",
                "widget": "dock",
                "edge": "top",
                "align": "start",
                "length": 400,
            }
        ),
        monitor=monitor,
    )
    ((_, handler),) = monitor.handlers.values()
    panel = shell.panels[0]
    _resize(monitor, handler, timers, 1280, 720)()
    assert shell.panels[0] is panel and not panel.destroyed


def test_a_resize_during_a_measurement_does_not_report_before_it(build):
    reports = []
    monitor = FakeMonitor()
    shell, _, timers = build(
        edge({"panel": "edge", "name": "dock", "widget": "dock", "length": "content"}),
        monitor=monitor,
        on_layout=reports.append,
    )
    ((_, handler),) = monitor.handlers.values()
    assert shell.measure_pending
    _resize(monitor, handler, timers, 1280, 720)()
    assert reports == []  # the pending measurement reports afterwards
    shell.test_idles[-1]()
    assert reports == [shell]


def test_a_scaled_monitor_warns_once_per_shell(build, caplog):
    monitor = FakeMonitor()
    shell, _, timers = build(
        edge({"panel": "edge", "name": "dock", "widget": "dock"}), monitor=monitor
    )
    ((_, handler),) = monitor.handlers.values()
    monitor.scale = 2
    _resize(monitor, handler, timers, 1280, 720)()
    _resize(monitor, handler, timers, 1024, 768)()
    assert caplog.text.count("scale 2 is not supported") == 1


def test_a_geometry_signal_on_a_closed_shell_is_ignored(build):
    monitor = FakeMonitor()
    shell, _, timers = build(
        edge({"panel": "edge", "name": "dock", "widget": "dock"}), monitor=monitor
    )
    before = len(timers)
    shell._closed = True
    shell._on_geometry()
    assert len(timers) == before


# ---- handle and interaction (spec 15): in place, never a rebuild ---------------------


def test_panels_get_their_handle_and_interaction(build):
    from shell.panel_spec import HandleSpec, Interaction

    shell, _, _ = build(
        edge(
            {
                "panel": "edge",
                "name": "dock",
                "widget": "dock",
                "handle": {"shape": "bar", "offset": 20},
            },
            {"panel": "edge", "name": "clock", "widget": "clock", "interaction": {"hover": False}},
        )
    )
    dock, clock = shell.panels
    assert dock.kwargs["handle"] == HandleSpec(shape="bar", offset=20)
    assert dock.kwargs["interaction"] == Interaction()
    assert clock.kwargs["handle"] == HandleSpec()
    assert clock.kwargs["interaction"] == Interaction(hover=False)


def test_a_handle_change_updates_the_live_panel(build, make_config):
    from shell.panel_spec import HandleSpec, Interaction

    shell, _, timers = build(
        edge(
            {"panel": "edge", "name": "dock", "widget": "dock"},
            {"panel": "edge", "name": "clock", "widget": "clock"},
        )
    )
    dock, clock = shell.panels
    before = len(timers)
    new = make_config(
        monitors=edge(
            {
                "panel": "edge",
                "name": "dock",
                "widget": "dock",
                "handle": {"shape": "chevron"},
                "interaction": {"drag": False},
            },
            {"panel": "edge", "name": "clock", "widget": "clock"},
        )
    )
    shell.apply(new, [Change("panel-handle", "HDMI-A-1", 0)])
    assert shell.panels == [dock, clock] and not dock.destroyed
    assert dock.handles == [(HandleSpec(shape="chevron"), Interaction(drag=False))]
    assert clock.handles == []  # unchanged panels are not touched
    assert len(timers) == before  # no rebuild, so no re-raise
    shell.apply(new, [])  # the same config again: nothing to do
    assert len(dock.handles) == 1


def test_a_handle_and_state_change_does_both_in_place(build, make_config):
    shell, _, _ = build(edge({"panel": "edge", "name": "dock", "widget": "dock"}))
    dock = shell.panels[0]
    new = make_config(
        monitors=edge(
            {
                "panel": "edge",
                "name": "dock",
                "widget": "dock",
                "state": "collapsed",
                "handle": {"size": 30},
            }
        )
    )
    shell.apply(new, [Change("panel-handle", "HDMI-A-1", 0)])
    assert shell.panels[0] is dock and dock.states == ["collapsed"]
    assert dock.handles[0][0].size == 30


def test_a_rebuilt_panel_gets_the_new_handle(build, make_config):
    shell, _, _ = build(edge({"panel": "edge", "name": "dock", "widget": "dock"}))
    old = shell.panels[0]
    shell.apply(
        make_config(
            monitors=edge(
                {
                    "panel": "edge",
                    "name": "dock",
                    "widget": "dock",
                    "depth": 80,
                    "handle": {"shape": "bar"},
                }
            )
        ),
        [Change("panel-rebuild", "HDMI-A-1", 0)],
    )
    new = shell.panels[0]
    assert old.destroyed and new is not old
    assert new.kwargs["handle"].shape == "bar" and new.handles == []


def test_a_theme_handle_style_change_restyles_in_place(build, make_config):
    shell, _, _ = build(edge({"panel": "edge", "name": "dock", "widget": "dock"}))
    dock = shell.panels[0]
    new = make_config(
        theme={"handle_style": {"shape": "bar"}},
        monitors=edge({"panel": "edge", "name": "dock", "widget": "dock"}),
    )
    shell.apply(new, [Change("restyle", "HDMI-A-1")])
    assert shell.panels[0] is dock and not dock.destroyed
    assert dock.themes[0].handle_style.shape == "bar" and dock.handles == []


def test_only_building_a_panel_logs_building_panel(build, make_config, caplog):
    caplog.set_level("DEBUG", logger="shell.monitors")
    shell, _, _ = build(edge({"panel": "edge", "name": "dock", "widget": "dock"}))
    built = [r.getMessage() for r in caplog.records if "building panel" in r.getMessage()]
    assert built == ["building panel 0 'dock' (dock) on HDMI-A-1"]
    caplog.clear()
    shell.apply(
        make_config(
            monitors=edge(
                {"panel": "edge", "name": "dock", "widget": "dock", "handle": {"shape": "bar"}}
            )
        ),
        [Change("panel-handle", "HDMI-A-1", 0)],
    )
    assert "building panel" not in caplog.text  # in place (Gate B item 6 reads this line)
    shell.apply(
        make_config(
            monitors=edge({"panel": "edge", "name": "dock", "widget": "dock", "depth": 80})
        ),
        [Change("panel-rebuild", "HDMI-A-1", 0)],
    )
    assert "building panel 0 'dock' (dock) on HDMI-A-1" in caplog.text


# ---- corner panels (spec 19) ------------------------------------------------------------


def test_a_corner_panel_gets_its_geometry_a_corner_shape_and_a_depth_callback(
    build, corner_registry
):
    from shell.canvas.scene import CornerShape
    from shell.panel_spec import CornerGeometry

    shell, _, _ = build(edge({"panel": "corner", "name": "box", "widget": "box"}))
    (box,) = shell.panels
    assert type(box).__name__ == "CornerPanel"
    assert box.args[0] == CornerGeometry(
        "box", "bottom-left", "bottom", 300, 290, 380, "extended", "box"
    )
    assert list(shell.canvas.shapes.values()) == [CornerShape("bottom-left", "bottom", 300, 380)]
    box.kwargs["on_depth"](40.0)
    assert shell.canvas.depths == [(box.scene_key, 40.0)]


def test_edge_panels_keep_clear_of_a_corner_panel(build, corner_registry):
    shell, _, _ = build(
        edge(
            {"panel": "corner", "name": "box", "widget": "box"},
            {"panel": "edge", "name": "dock", "widget": "dock", "align": "start"},
        )
    )
    assert shell.panels[1].args[0].pos == 336  # 300 + 14 + 8 + 14
    assert shell.layout_warnings == []


def test_a_second_corner_panel_in_one_corner_is_hidden_and_reported(build, corner_registry):
    shell, _, _ = build(
        edge(
            {"panel": "corner", "name": "box", "widget": "box"},
            {"panel": "corner", "name": "box 2", "widget": "box", "edge": "left"},
        )
    )
    assert shell.panels[1] is None and len(shell.canvas.shapes) == 1
    assert "the bottom-left corner already holds" in shell.layout_warnings[0]


def test_corner_panels_are_raised_like_edge_panels(build, corner_registry):
    shell, _, timers = build(edge({"panel": "corner", "name": "box", "widget": "box"}))
    for _, fn, a in timers:
        fn(*a)
    assert shell.panels[0].raised == 2


def test_corner_panels_are_never_measured(build, corner_registry):
    shell, _, _ = build(
        edge(
            {"panel": "corner", "name": "box", "widget": "box"},
            {"panel": "edge", "name": "dock", "widget": "dock", "length": "content"},
        )
    )
    box, dock = shell.panels
    shell.test_idles[-1]()  # the idle measurement
    assert dock.measured == 1 and box.measured == 0
    assert shell.panels[0] is box  # a "content" neighbour's measurement never rebuilds it


def test_a_corner_size_change_rebuilds_only_that_panel(build, corner_registry, make_config):
    shell, _, _ = build(
        edge(
            {"panel": "corner", "name": "box", "widget": "box"},
            {"panel": "edge", "name": "clock", "widget": "clock"},
        )
    )
    box, clock = shell.panels
    shell.apply(
        make_config(
            monitors=edge(
                {"panel": "corner", "name": "box", "widget": "box", "width": 320},
                {"panel": "edge", "name": "clock", "widget": "clock"},
            )
        ),
        [Change("panel-rebuild", "HDMI-A-1", 0)],
    )
    assert box.destroyed and shell.panels[0].args[0].along == 320
    assert shell.panels[1] is clock and not clock.destroyed


def test_a_corner_handle_change_is_applied_in_place(build, corner_registry, make_config):
    from shell.panel_spec import HandleSpec, Interaction

    shell, _, timers = build(edge({"panel": "corner", "name": "box", "widget": "box"}))
    (box,) = shell.panels
    before = len(timers)
    shell.apply(
        make_config(
            monitors=edge(
                {"panel": "corner", "name": "box", "widget": "box", "handle": {"shape": "bar"}}
            )
        ),
        [Change("panel-handle", "HDMI-A-1", 0)],
    )
    assert shell.panels == [box] and not box.destroyed
    assert box.handles == [(HandleSpec(shape="bar"), Interaction())]
    assert len(timers) == before


def test_a_corner_state_change_retargets_in_place(build, corner_registry, make_config):
    shell, _, _ = build(edge({"panel": "corner", "name": "box", "widget": "box"}))
    (box,) = shell.panels
    shell.apply(
        make_config(
            monitors=edge({"panel": "corner", "name": "box", "widget": "box", "state": "collapsed"})
        ),
        [Change("panel-state", "HDMI-A-1", 0)],
    )
    assert shell.panels == [box] and box.states == ["collapsed"]


def test_a_smaller_monitor_shrinks_the_corner_panel(build, corner_registry):
    monitor = FakeMonitor()
    shell, _, timers = build(
        edge({"panel": "corner", "name": "box", "widget": "box"}), monitor=monitor
    )
    (box,) = shell.panels
    monitor.width, monitor.height = 320, 720
    ((_signal, handler),) = monitor.handlers.values()
    handler(monitor, None)
    relayout = [t for t in timers if t[0] == mon_mod.RELAYOUT_DELAY_MS][-1]
    assert relayout[1]() is False
    assert box.destroyed and shell.panels[0].args[0].along == 282  # 320 - (10 + 14) - 14
    assert "width 300 px does not fit the bottom edge; shrunk to 282" in shell.layout_warnings[0]


# ---- the widget a panel shows (panel/widget spec 3.5) --------------------------------


class Big(WidgetProps):
    size: int = 10


@pytest.fixture
def big(fake_registry):
    """A widget with one property: a change of it must rebuild the panel."""
    fake_registry.register_widget(
        "big",
        title="Big",
        props=Big,
        edge=PanelDefaults(edge="top", length=200, depth=50, label="big"),
    )(type("BigWidget", (Widget,), {}))
    return fake_registry


def test_a_panel_gets_a_new_instance_of_its_widget_and_the_props(build, big):
    shell, _, _ = build(
        edge(
            {"panel": "edge", "name": "A", "widget": "big", "size": 20},
            {"panel": "edge", "name": "B", "widget": "big"},
        )
    )
    a, b = shell.panels
    assert type(a.kwargs["widget"]).__name__ == "BigWidget"
    assert a.kwargs["widget"] is not b.kwargs["widget"]
    assert (a.kwargs["props"], b.kwargs["props"]) == (Big(size=20), Big())


@pytest.mark.parametrize(
    "change",
    [{"name": "Renamed"}, {"size": 30}],
    ids=["name", "property"],
)
def test_a_name_or_property_change_rebuilds_the_panel_in_the_same_place(
    build, big, make_config, change
):
    entry = {"panel": "edge", "name": "A", "widget": "big"}
    shell, _, _ = build(edge(entry))
    (old,) = shell.panels
    shell.apply(make_config(monitors=edge({**entry, **change})), [])
    (new,) = shell.panels
    assert new is not old and old.destroyed
    assert new.args[0] == old.args[0]  # the same geometry: only the content changed
    if "size" in change:
        assert new.kwargs["props"] == Big(size=30)


def test_an_unchanged_entry_is_not_rebuilt(build, big, make_config):
    entry = {"panel": "edge", "name": "A", "widget": "big", "size": 12}
    shell, _, _ = build(edge(entry))
    (old,) = shell.panels
    shell.apply(make_config(monitors=edge(entry)), [])
    assert shell.panels == [old] and not old.destroyed


def test_a_failed_panel_is_not_retried_by_a_relayout_only_by_an_entry_change(
    build, make_config, monkeypatch
):
    calls = []

    def explode(*a, **k):
        calls.append(1)
        raise RuntimeError("widget broke")

    monitor = FakeMonitor()
    monkeypatch.setattr(mon_mod, "widget_class", lambda _w: explode)
    entry = {"panel": "edge", "name": "Dock", "widget": "dock", "length": "content"}
    shell, _, timers = build(edge(entry), monitor=monitor)
    assert calls == [1] and shell.panels == [None]
    ((_, handler),) = monitor.handlers.values()
    monitor.width, monitor.height = 1280, 720  # a resolution change re-lays out the monitor
    handler(monitor, None)
    assert timers[-1][1]() is False
    shell.apply(make_config(monitors=edge(entry)), [])  # an unrelated reload
    assert calls == [1] and len(shell.build_failures) == 1  # never tried again
    for change in ({"depth": 80}, {"widget": "clock"}, {"panel": "edge", "name": "Dock 2"}):
        shell.apply(make_config(monitors=edge({**entry, **change})), [])
    assert len(calls) == 3  # depth alone is a move: not retried; widget and name changes are


def test_a_failed_panel_is_tried_again_when_its_properties_change(
    build, big, make_config, monkeypatch
):
    calls = []

    def explode(*a, **k):
        calls.append(1)
        raise RuntimeError("widget broke")

    monkeypatch.setattr(mon_mod, "widget_class", lambda _w: explode)
    entry = {"panel": "edge", "name": "A", "widget": "big", "size": 20}
    shell, _, _ = build(edge(entry))
    shell.apply(make_config(monitors=edge(entry)), [])
    assert len(calls) == 1  # the same entry: not tried again
    shell.apply(make_config(monitors=edge({**entry, "size": 30})), [])
    assert len(calls) == 2 and len(shell.build_failures) == 1


def test_a_removed_failed_panel_is_forgotten_so_a_new_entry_there_is_tried(
    build, big, make_config, monkeypatch
):
    calls = []

    def explode(*a, **k):
        calls.append(1)
        raise RuntimeError("widget broke")

    monkeypatch.setattr(mon_mod, "widget_class", lambda _w: explode)
    entry = {"panel": "edge", "name": "A", "widget": "big"}
    shell, _, _ = build(edge(entry))
    shell.apply(make_config(monitors=edge()), [])  # the panel is removed
    assert shell.panels == [] and shell.build_failures == []
    shell.apply(make_config(monitors=edge(entry)), [])  # the same entry added again
    assert len(calls) == 2


def test_a_failed_panel_whose_kind_changes_is_tried_again(
    build, corner_registry, make_config, monkeypatch
):
    from shell.panel_spec import CornerDefaults

    corner_registry.register_widget(
        "both",
        title="Both",
        edge=PanelDefaults(edge="bottom", length=300, depth=50, label="both"),
        corner=CornerDefaults(corner="bottom-left", width=300, height=390, label="both"),
    )(type("Both", (Widget,), {}))
    calls = []

    def explode(*a, **k):
        calls.append(1)
        raise RuntimeError("widget broke")

    monkeypatch.setattr(mon_mod, "widget_class", lambda _w: explode)
    shell, _, _ = build(edge({"panel": "edge", "name": "A", "widget": "both"}))
    shell.apply(make_config(monitors=edge({"panel": "edge", "name": "A", "widget": "both"})), [])
    assert len(calls) == 1  # the same entry: not tried again
    shell.apply(make_config(monitors=edge({"panel": "corner", "name": "A", "widget": "both"})), [])
    assert len(calls) == 2  # only the kind changed (name, widget and properties are the same)


def test_a_failed_name_that_is_used_again_after_a_rename_is_tried_again(
    build, make_config, monkeypatch
):
    calls = []

    def explode(*a, **k):
        calls.append(1)
        raise RuntimeError("widget broke")

    real = mon_mod.widget_class

    def entry(name):
        return edge({"panel": "edge", "name": name, "widget": "clock"})

    monkeypatch.setattr(mon_mod, "widget_class", lambda _w: explode)
    shell, _, _ = build(entry("Clock"))
    assert len(calls) == 1
    monkeypatch.setattr(mon_mod, "widget_class", real)
    shell.apply(make_config(monitors=entry("Clock 2")), [])  # renamed: builds
    assert shell.panels[0] is not None and shell.build_failures == []
    monkeypatch.setattr(mon_mod, "widget_class", lambda _w: explode)
    shell.apply(make_config(monitors=entry("Clock")), [])  # renamed back: not skipped as failed
    assert len(calls) == 2 and shell.panels == [None]
    assert "panel 'Clock'" in shell.build_failures[0] and len(shell.build_failures) == 1


def test_a_build_failure_without_a_message_still_names_its_cause(build, monkeypatch):
    def explode(*a, **k):
        raise ValueError

    monkeypatch.setattr(mon_mod, "widget_class", lambda _w: explode)
    shell, _, _ = build(edge({"panel": "edge", "name": "Dock", "widget": "dock"}))
    assert shell.build_failures == [
        "HDMI-A-1: panel 'Dock' (dock) could not be built and is not shown: ValueError"
    ]
