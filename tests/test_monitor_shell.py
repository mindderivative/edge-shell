"""Display-free tests for MonitorShell bookkeeping (windows are fakes)."""

from types import SimpleNamespace

import pytest

pytest.importorskip("gi")
pytest.importorskip("fabric")

import shell.monitors as mon_mod  # noqa: E402


class FakeWindow:
    def __init__(self, *args, raises=False, **kwargs):
        self.destroyed = False
        self.raises = raises
        self.raised = 0
        self.title = "w"
        self.themes = []

    def set_theme(self, theme):
        self.themes.append(theme)

    def apply_theme(self, theme):
        self.themes.append(theme)

    def destroy(self):
        self.destroyed = True
        if self.raises:
            raise RuntimeError("already gone")

    def raise_to_top(self):
        self.raised += 1

    def get_title(self):
        return self.title


def bare_shell(windows, panels=(), unregister=None):
    shell = mon_mod.MonitorShell.__new__(mon_mod.MonitorShell)
    shell.name = "HDMI-A-1"
    shell.windows = list(windows)
    shell.panels = list(panels)
    shell.canvas = FakeWindow()
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


# ---- raise timers -------------------------------------------------------------------


def test_raise_panels_raises_live_panels():
    a, b = FakeWindow(), FakeWindow()
    shell = bare_shell([a, b], [a, b])
    assert shell._raise_panels() is False  # one-shot GLib source
    assert (a.raised, b.raised) == (1, 1)


def test_raise_panels_skips_panels_that_were_removed():
    a, b = FakeWindow(), FakeWindow()
    shell = bare_shell([a, b], [a, b])
    shell.panels.remove(b)
    shell._raise_panels()
    assert (a.raised, b.raised) == (1, 0)


def test_raise_is_a_noop_after_close():
    a = FakeWindow()
    shell = bare_shell([a], [a])
    shell.close()
    shell.panels.append(a)  # even if something kept a stale reference
    assert shell._raise_panels() is False
    assert a.raised == 0


def test_init_schedules_primary_and_fallback_raise(monkeypatch, make_config, fake_registry):
    monkeypatch.delenv("EDGE_SHELL_RAISE_MS", raising=False)
    timers = []
    monkeypatch.setattr(mon_mod, "FrameEdge", FakeWindow)
    monkeypatch.setattr(mon_mod, "ShapeCanvas", FakeWindow)
    monkeypatch.setattr(mon_mod, "widget_class", lambda _w: FakeWindow)
    monkeypatch.setattr(mon_mod.MonitorShell, "_check_monitor", lambda self, w: None)
    monkeypatch.setattr(
        mon_mod.GLib, "timeout_add", lambda ms, fn, *a: timers.append((ms, fn, a)) or len(timers)
    )
    cfg = make_config(monitors={"HDMI-A-1": {"shell": "edge", "panels": [{"widget": "dock"}]}})
    shell = mon_mod.MonitorShell("HDMI-A-1", object(), cfg, lambda w: None)
    assert [ms for ms, _, _ in timers] == [mon_mod.RAISE_DELAY_MS, mon_mod.RAISE_FALLBACK_MS]
    assert mon_mod.RAISE_FALLBACK_MS > mon_mod.RAISE_DELAY_MS
    panel = shell.panels[0]
    for _, fn, a in timers:
        assert fn(*a) is False
    assert panel.raised == 2
    shell.close()
    for _, fn, a in timers:
        fn(*a)
    assert panel.raised == 2  # no work after close


def test_init_without_panels_schedules_no_raise(monkeypatch, make_config):
    timers = []
    monkeypatch.setattr(mon_mod, "FrameEdge", FakeWindow)
    monkeypatch.setattr(mon_mod, "ShapeCanvas", FakeWindow)
    monkeypatch.setattr(mon_mod.MonitorShell, "_check_monitor", lambda self, w: None)
    monkeypatch.setattr(mon_mod.GLib, "timeout_add", lambda *a: timers.append(a) or 1)
    cfg = make_config(monitors={"HDMI-A-1": {"shell": "edge"}})
    mon_mod.MonitorShell("HDMI-A-1", object(), cfg, lambda w: None)
    assert timers == []


# ---- shape canvas -------------------------------------------------------------------


class Built(FakeWindow):
    def __init__(self, *args, **kwargs):
        super().__init__()
        self.kind = kwargs.get("kind")


def build(monkeypatch, make_config, monitors):
    monkeypatch.setattr(mon_mod, "ShapeCanvas", lambda *a, **k: Built(kind="canvas"))
    monkeypatch.setattr(mon_mod, "FrameEdge", lambda *a, **k: Built(kind="strip"))
    monkeypatch.setattr(mon_mod, "widget_class", lambda _w: lambda *a, **k: Built(kind="panel"))
    monkeypatch.setattr(mon_mod.MonitorShell, "_check_monitor", lambda self, w: None)
    monkeypatch.setattr(mon_mod.GLib, "timeout_add", lambda *a: 1)
    cfg = make_config(monitors=monitors)
    tracked = []
    shell = mon_mod.MonitorShell("HDMI-A-1", object(), cfg, tracked.append)
    return shell, cfg, tracked


def test_canvas_is_created_first_then_strips_then_panels(monkeypatch, make_config, fake_registry):
    _, _, tracked = build(
        monkeypatch, make_config, {"HDMI-A-1": {"shell": "edge", "panels": [{"widget": "dock"}]}}
    )
    assert [w.kind for w in tracked] == ["canvas"] + ["strip"] * 4 + ["panel"]


def test_restyle_redraws_the_canvas_with_the_monitor_theme(monkeypatch, make_config):
    from shell.config.diff import Change

    shell, _, _ = build(monkeypatch, make_config, {"HDMI-A-1": {"shell": "edge"}})
    new = make_config(
        theme={"shadow": {"enabled": True}},
        monitors={"HDMI-A-1": {"shell": "edge", "theme": {"shadow": {"elevation": 90}}}},
    )
    shell.apply(new, [Change("restyle", "HDMI-A-1")])
    (theme,) = shell.canvas.themes
    assert theme.shadow.enabled and theme.shadow.elevation == 90


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
