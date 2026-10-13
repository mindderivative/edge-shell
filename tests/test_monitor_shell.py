"""Display-free tests for MonitorShell bookkeeping (windows are fakes)."""

from types import SimpleNamespace

import pytest

pytest.importorskip("gi")
pytest.importorskip("fabric")

import shell.monitors as mon_mod  # noqa: E402
from shell.config.diff import Change  # noqa: E402


class FakeWindow:
    def __init__(self, *args, raises=False, **kwargs):
        self.args, self.kwargs = args, kwargs
        self.destroyed = False
        self.raises = raises
        self.raised = 0
        self.title = "w"
        self.themes = []
        self.states = []

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

    def get_title(self):
        return self.title


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


MONITOR = SimpleNamespace(get_geometry=lambda: SimpleNamespace(x=0, y=0, width=1920, height=1080))


def bare_shell(windows, panels=(), unregister=None):
    shell = mon_mod.MonitorShell.__new__(mon_mod.MonitorShell)
    shell.name = "HDMI-A-1"
    shell.windows = list(windows)
    shell.panels = list(panels)
    shell._resolved = [None] * len(shell.panels)
    shell.canvas = FakeCanvas()
    shell.strips = []
    shell._closed = False
    shell._unregister = unregister or (lambda _w: None)
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
    monkeypatch.setattr(mon_mod, "widget_class", lambda _w: FakeWindow)
    monkeypatch.setattr(mon_mod.MonitorShell, "_check_monitor", lambda self, w: None)
    timers = []
    monkeypatch.setattr(
        mon_mod.GLib, "timeout_add", lambda ms, fn, *a: timers.append((ms, fn, a)) or len(timers)
    )

    def _build(monitors, theme=None):
        tracked = []
        cfg = make_config(monitors=monitors, theme=theme)
        shell = mon_mod.MonitorShell("HDMI-A-1", MONITOR, cfg, tracked.append)
        return shell, tracked, timers

    return _build


def edge(*panels, theme=None):
    return {"HDMI-A-1": {"shell": "edge", "panels": list(panels), "theme": theme or {}}}


def test_canvas_first_then_strips_then_panels(build):
    shell, tracked, _ = build(edge({"widget": "dock"}))
    assert tracked[0] is shell.canvas
    assert [type(w) for w in tracked[1:5]] == [FakeWindow] * 4
    assert tracked[5] is shell.panels[0]


def test_panels_get_a_resolved_pos_a_scene_shape_and_a_depth_callback(build):
    shell, _, _ = build(edge({"widget": "dock"}, {"widget": "bar"}))
    dock, bar = shell.panels
    assert dock.args[0].pos == 680 and bar.args[0].pos == 600  # centred dock resolved to 680
    assert {s.edge for s in shell.canvas.shapes.values()} == {"bottom", "right"}
    dock.kwargs["on_depth"](12.5)
    assert shell.canvas.depths == [(dock.scene_key, 12.5)]


def test_two_centred_panels_on_one_edge_are_both_shown(build):
    shell, _, _ = build(edge({"widget": "dock"}, {"widget": "dock", "length": 300}))
    a, b = shell.panels
    assert a.args[0].pos + 560 + 14 + 14 + 8 == b.args[0].pos  # packed: joins + default gap
    assert shell.layout_warnings == [] and len(shell.canvas.shapes) == 2


def test_panel_that_breaks_the_layout_rules_is_hidden_and_reported(build):
    shell, _, _ = build(edge({"widget": "dock"}, {"widget": "dock", "pos": 700}))
    assert shell.panels[1] is None and len(shell.canvas.shapes) == 1
    assert "monitors.HDMI-A-1.panels.1 (dock): overlaps" in shell.layout_warnings[0]


def test_init_schedules_primary_and_fallback_raise(build):
    shell, _, timers = build(edge({"widget": "dock"}))
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
    _, _, timers = build(edge({"widget": "dock"}))
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
    shell, _, _ = build(edge({"widget": "dock"}))
    new = make_config(
        theme={"shadow": {"enabled": True}},
        monitors=edge({"widget": "dock"}, theme={"shadow": {"elevation": 90}}),
    )
    shell.apply(new, [Change("restyle", "HDMI-A-1")])
    (theme,) = shell.canvas.themes
    assert theme.shadow.enabled and theme.shadow.elevation == 90
    assert shell.panels[0].themes == [theme]


def test_restyle_resizes_the_strips_in_place_with_the_monitor_theme(build, make_config):
    shell, tracked, _ = build(edge({"widget": "dock"}))
    strips = list(shell.strips)
    assert len(strips) == 4 and all(s in tracked for s in strips)
    new = make_config(
        theme={"border": {"enabled": True, "width": 3}},
        monitors=edge({"widget": "dock"}, theme={"border": {"width": 4}}),
    )
    shell.apply(new, [Change("restyle", "HDMI-A-1")])
    assert shell.strips == strips and not any(s.destroyed for s in strips)  # no rebuild
    assert all(len(s.themes) == 1 and s.themes[0].border.width == 4 for s in strips)


def test_state_change_retargets_without_rebuilding(build, make_config):
    shell, _, _ = build(edge({"widget": "dock"}))
    dock = shell.panels[0]
    shell.apply(
        make_config(monitors=edge({"widget": "dock", "state": "collapsed"})),
        [Change("panel-state", "HDMI-A-1", 0)],
    )
    assert shell.panels[0] is dock and dock.states == ["collapsed"] and not dock.destroyed


def test_geometry_change_rebuilds_and_moves_the_scene_shape(build, make_config):
    shell, _, timers = build(edge({"widget": "dock"}))
    old = shell.panels[0]
    shell.apply(
        make_config(monitors=edge({"widget": "dock", "length": 300})),
        [Change("panel-rebuild", "HDMI-A-1", 0)],
    )
    new = shell.panels[0]
    assert old.destroyed and new is not old
    assert list(shell.canvas.shapes) == [new.scene_key]
    assert shell.canvas.shapes[new.scene_key].length == 300
    assert timers[-1][0] == mon_mod.RAISE_DELAY_MS  # the rebuilt panel is re-raised once


def test_add_and_remove_keep_canvas_and_panels_in_step(build, make_config):
    shell, _, _ = build(edge({"widget": "dock"}))
    shell.apply(make_config(monitors=edge({"widget": "dock"}, {"widget": "clock"})), [])
    assert [p.args[0].widget for p in shell.panels] == ["dock", "clock"]
    assert len(shell.canvas.shapes) == 2
    clock = shell.panels[1]
    shell.apply(make_config(monitors=edge({"widget": "dock"})), [])
    assert clock.destroyed and len(shell.panels) == 1 and len(shell.canvas.shapes) == 1


def test_a_neighbour_change_rebuilds_the_panel_it_unhides(build, make_config):
    shell, _, _ = build(edge({"widget": "dock"}, {"widget": "dock", "pos": 700}))
    assert shell.panels[1] is None
    shell.apply(
        make_config(
            monitors=edge({"widget": "dock", "align": "end"}, {"widget": "dock", "pos": 700})
        ),
        [Change("panel-rebuild", "HDMI-A-1", 0)],
    )
    assert shell.panels[1] is not None and shell.layout_warnings == []
    assert len(shell.canvas.shapes) == 2


def test_failed_panel_construction_leaves_no_scene_shape(build, make_config, monkeypatch):
    shell, _, _ = build(edge())

    def explode(*a, **k):
        raise RuntimeError("widget broke")

    monkeypatch.setattr(mon_mod, "widget_class", lambda _w: explode)
    with pytest.raises(RuntimeError):
        shell.apply(make_config(monitors=edge({"widget": "dock"})), [])
    assert shell.canvas.shapes == {}


def test_failed_construction_closes_everything_already_built(make_config, monkeypatch):
    def explode(*a, **k):
        raise RuntimeError("panel broke")

    monkeypatch.setattr(mon_mod, "ShapeCanvas", FakeCanvas)
    monkeypatch.setattr(mon_mod, "FrameEdge", FakeWindow)
    monkeypatch.setattr(mon_mod, "widget_class", lambda _w: explode)
    monkeypatch.setattr(mon_mod.MonitorShell, "_check_monitor", lambda self, w: None)
    monkeypatch.setattr(mon_mod.GLib, "timeout_add", lambda *a: 1)
    registered, unregistered = [], []
    cfg = make_config(monitors=edge({"widget": "dock"}))
    with pytest.raises(RuntimeError, match="panel broke"):
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
    mons = edge({"widget": "clock", "align": "start"}, {"widget": "clock", "align": "start"})
    mons["HDMI-A-1"]["layout"] = {"gap": 30}
    shell, _, _ = build(mons)
    a, b = (p.args[0] for p in shell.panels)
    assert b.pos - (a.pos + a.length) == 14 + 14 + 30


def test_a_gap_change_moves_the_neighbours(build, make_config):
    two = edge({"widget": "clock", "align": "start"}, {"widget": "clock", "align": "start"})
    shell, _, _ = build(two)
    first, second = shell.panels
    wider = edge({"widget": "clock", "align": "start"}, {"widget": "clock", "align": "start"})
    wider["HDMI-A-1"]["layout"] = {"gap": 40}
    shell.apply(make_config(monitors=wider), [Change("relayout", "HDMI-A-1")])
    assert shell.panels[0] is first and not first.destroyed  # did not move: kept
    assert second.destroyed and shell.panels[1].args[0].pos == second.args[0].pos + 32
