"""MonitorShell's fade (spec 21), display-free: fake windows, the canvas as a fake frame clock
(shell.canvas.simulate), fake GLib timers and idles."""

import pytest

pytest.importorskip("gi")
pytest.importorskip("fabric")

import shell.app as app_mod  # noqa: E402
import shell.monitors as mon_mod  # noqa: E402
from shell.canvas.simulate import FRAME_US, FakeClock, FakeTicker  # noqa: E402
from shell.config.diff import Change  # noqa: E402
from shell.fade import FINISH_MARGIN_MS, READY_TIMEOUT_MS  # noqa: E402
from tests.test_monitor_shell import FakeCanvas, FakeMonitor, FakeWindow, edge  # noqa: E402

DOCK = {"panel": "edge", "name": "dock", "widget": "dock"}
CLOCK = {"panel": "edge", "name": "clock", "widget": "clock"}
THIRDS = [0.0, 1 / 3, 2 / 3, 1.0]  # a 50 ms fade at 60 Hz: the first frame starts the clock


class TickCanvas(FakeCanvas):
    """The canvas as the fade's frame clock: FakeTicker's two methods, run by `frames`."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ticker = FakeTicker()
        self.add_tick_callback = self.ticker.add_tick_callback
        self.remove_tick_callback = self.ticker.remove_tick_callback


class Loop:
    """GLib.timeout_add / idle_add / source_remove stand-ins, run by hand."""

    def __init__(self):
        self.timers: dict[int, tuple] = {}
        self.idles: dict[int, tuple] = {}
        self.removed: list[int] = []
        self._next = 1

    def _id(self):
        source, self._next = self._next, self._next + 1
        return source

    def timeout_add(self, ms, fn, *args):
        source = self._id()
        self.timers[source] = (ms, fn, args)
        return source

    def idle_add(self, fn, *args):
        source = self._id()
        self.idles[source] = (fn, args)
        return source

    def source_remove(self, source):
        assert source in self.timers or source in self.idles, "removed a source that is gone"
        self.timers.pop(source, None)
        self.idles.pop(source, None)
        self.removed.append(source)

    def delays(self):
        return sorted(ms for ms, _, _ in self.timers.values())

    def fire(self, ms):
        """Every pending timer of that delay, oldest first (one-shot: a False return)."""
        for source in sorted(s for s, (d, _, _) in self.timers.items() if d == ms):
            if source in self.timers:
                _, fn, args = self.timers.pop(source)
                assert fn(*args) is False

    def run_idles(self):
        while self.idles:
            source = min(self.idles)
            fn, args = self.idles.pop(source)
            assert fn(*args) is False


@pytest.fixture
def loop(monkeypatch):
    loop = Loop()
    monkeypatch.setattr(mon_mod.GLib, "timeout_add", loop.timeout_add)
    monkeypatch.setattr(mon_mod.GLib, "idle_add", loop.idle_add)
    monkeypatch.setattr(mon_mod.GLib, "source_remove", loop.source_remove)
    return loop


@pytest.fixture
def build(monkeypatch, make_config, fake_registry, loop):
    """build(monitors, fade_ms=50) -> a MonitorShell on fakes, with `frames(n)`, `faded`
    (its on_fade_in calls) and `config_for(monitors, theme)`."""
    monkeypatch.delenv("EDGE_SHELL_RAISE_MS", raising=False)
    monkeypatch.setattr(mon_mod, "ShapeCanvas", TickCanvas)
    monkeypatch.setattr(mon_mod, "FrameEdge", FakeWindow)
    real_panel_class = mon_mod.panel_class
    monkeypatch.setattr(
        mon_mod,
        "panel_class",
        lambda geo: type(real_panel_class(geo).__name__, (FakeWindow,), {}),
    )
    monkeypatch.setattr(mon_mod.MonitorShell, "_check_monitor", lambda self, w: None)

    def _build(monitors, fade_ms=50, theme=None):
        faded = []
        shell = mon_mod.MonitorShell(
            "HDMI-A-1",
            FakeMonitor(),
            make_config(monitors=monitors, theme=theme),
            lambda _w: None,
            fade_ms=fade_ms,
            on_fade_in=faded.append,
        )
        clock = FakeClock()

        def frames(n):
            for _ in range(n):
                clock.now_us += FRAME_US
                shell.canvas.ticker.run(clock)

        shell.frames, shell.faded, shell.config_for = frames, faded, make_config
        return shell

    return _build


def shown(shell, loop):
    """Run the build to the end of its fade-in."""
    loop.run_idles()
    loop.fire(mon_mod.RAISE_DELAY_MS)
    shell.frames(4)
    assert shell._fade.state == "shown"


def test_without_a_fade_no_window_gets_an_opacity_and_nothing_waits(build, loop):
    shell = build(edge(DOCK), fade_ms=0)
    assert all(w.opacity == [] and w.inputs == [] for w in shell.windows)
    assert loop.idles == {} and loop.delays() == [500, 2000]  # only the re-raises, as before
    loop.fire(500)
    shell.frames(5)
    assert all(w.opacity == [] for w in shell.windows) and shell.faded == []


def test_every_window_is_built_transparent_and_its_panels_take_no_input(build):
    shell = build(edge(DOCK, CLOCK))
    assert len(shell.windows) == 7  # canvas, 4 strips, 2 panels
    assert all(w.opacity == [0.0] for w in shell.windows)
    assert [p.inputs for p in shell.panels] == [[False], [False]]
    assert shell._fade.state == "waiting"


def test_it_fades_in_after_the_first_re_raise_every_window_in_the_same_frames(build, loop):
    shell = build(edge(DOCK, CLOCK))
    assert loop.delays() == [500, READY_TIMEOUT_MS, 2000]
    loop.run_idles()
    assert shell._fade.state == "waiting"  # the first re-raise (a re-map: a blink) is pending
    loop.fire(500)
    assert [p.raised for p in shell.panels] == [1, 1]
    assert shell._fade.state == "fading-in" and shell.faded == [shell]
    assert [p.inputs for p in shell.panels] == [[False, True], [False, True]]
    shell.frames(4)
    for window in shell.windows:
        assert window.opacity == pytest.approx([0.0, *THIRDS], abs=1e-3)
    assert shell._fade.state == "shown" and not shell.canvas.ticker._callbacks
    assert loop.delays() == [2000]  # the ready timeout and the finish timeout are gone
    loop.fire(2000)  # the fallback re-raise is not waited for and changes nothing
    assert shell._fade.state == "shown" and shell.faded == [shell]


def test_a_monitor_without_panels_fades_in_once_the_build_returns_to_the_loop(build, loop):
    shell = build(edge())
    assert shell._fade.state == "waiting"  # never inside the constructor
    loop.run_idles()
    assert shell._fade.state == "fading-in" and shell.faded == [shell]


def test_a_content_panel_is_measured_and_rebuilt_before_the_fade_in(build, loop):
    shell = build(edge({**DOCK, "length": "content"}))
    first = shell.panels[0]
    loop.run_idles()  # measured at 200 px: rebuilt, and the new window is re-raised later
    rebuilt = shell.panels[0]
    assert rebuilt is not first and first.destroyed
    assert rebuilt.opacity == [0.0] and rebuilt.inputs == [False]
    assert shell._fade.state == "waiting" and shell._raises_pending == 2
    loop.fire(500)
    assert shell._fade.state == "fading-in" and rebuilt.inputs == [False, True]


def test_the_ready_timeout_fades_in_when_nothing_reports_ready(build, loop):
    shell = build(edge(DOCK))
    loop.fire(READY_TIMEOUT_MS)
    assert shell._fade.state == "fading-in" and shell.faded == [shell]
    loop.fire(500)  # the late re-raise changes nothing
    assert shell.faded == [shell]


def test_with_the_re_raise_switched_off_it_fades_in_at_the_first_idle(build, loop, monkeypatch):
    monkeypatch.setenv("EDGE_SHELL_RAISE_MS", "0")
    shell = build(edge(DOCK))
    loop.run_idles()
    assert shell._fade.state == "fading-in"


def test_the_end_of_the_last_measurement_starts_the_fade_in(build, loop, monkeypatch):
    """No re-raise: the measurement rebuilds the panel and measures it again; only the end
    of that second measurement may start the fade, never the first."""
    monkeypatch.setenv("EDGE_SHELL_RAISE_MS", "0")
    shell = build(edge({**DOCK, "length": "content"}))
    first_measure = min(loop.idles)
    fn, args = loop.idles.pop(first_measure)
    fn(*args)  # measured: rebuilt at 200 px, so measured again
    assert shell._fade.state == "waiting" and shell.measure_pending
    loop.run_idles()  # the ready check, then the second measurement (no change)
    assert shell._fade.state == "fading-in" and shell.faded == [shell]


def test_a_fade_without_frames_is_finished_by_its_timeout(build, loop):
    """A canvas that is never mapped gets no frames: the windows are made opaque anyway."""
    shell = build(edge(DOCK))
    loop.run_idles()
    loop.fire(500)
    loop.fire(50 + FINISH_MARGIN_MS)
    assert all(w.opacity[-1] == 1.0 for w in shell.windows)
    assert shell._fade.state == "shown"


def test_close_mid_fade_leaves_no_tick_callback_timer_or_idle(build, loop):
    shell = build(edge(DOCK))
    canvas = shell.canvas
    loop.run_idles()
    loop.fire(500)
    shell.frames(2)
    shell.close()
    assert not canvas.ticker._callbacks
    assert loop.delays() == [2000]  # only the re-raise, a no-op after close
    seen = [list(w.opacity) for w in (canvas, *shell.strips)]
    shell.frames(3)
    assert [list(w.opacity) for w in (canvas, *shell.strips)] == seen


def test_close_while_waiting_removes_the_ready_check_and_timeout(build, loop):
    shell = build(edge(DOCK))
    shell.close()
    assert loop.idles == {} and loop.delays() == [500, 2000]
    loop.fire(500)
    assert shell._fade.state == "done" and shell.faded == []


def test_a_panel_added_after_the_fade_in_is_opaque_and_takes_input(build, loop):
    shell = build(edge(DOCK))
    shown(shell, loop)
    config = shell.config_for(monitors=edge(DOCK, CLOCK))
    shell.apply(config, [Change("panel-add", "HDMI-A-1", 1)])
    added = shell.panels[1]
    assert added.opacity == [] and added.inputs == []


def test_a_panel_built_during_the_fade_in_starts_at_the_current_opacity(build, loop):
    shell = build(edge(DOCK))
    loop.run_idles()
    loop.fire(500)
    shell.frames(2)  # the start, then 1/3
    config = shell.config_for(monitors=edge(DOCK, CLOCK))
    shell.apply(config, [Change("panel-add", "HDMI-A-1", 1)])
    added = shell.panels[1]
    assert added.opacity == pytest.approx([1 / 3], abs=1e-3)
    assert added.inputs == []  # input follows the fade-in, which has started
    shell.frames(2)
    assert added.opacity[-1] == 1.0 == shell.canvas.opacity[-1]


def test_a_restyle_never_fades(build, loop):
    shell = build(edge(DOCK))
    shown(shell, loop)
    seen = [len(w.opacity) for w in shell.windows]
    config = shell.config_for(monitors=edge(DOCK), theme={"accent": "#112233"})
    shell.apply(config, [Change("restyle", "HDMI-A-1")])
    shell.frames(5)
    assert [len(w.opacity) for w in shell.windows] == seen and shell._fade.state == "shown"


def test_one_window_failing_its_opacity_does_not_stop_the_others(build, loop):
    shell = build(edge(DOCK))

    def gone(_value):
        raise RuntimeError("window destroyed")

    shell.strips[0].set_opacity = gone
    loop.run_idles()
    loop.fire(500)
    shell.frames(4)
    assert shell.canvas.opacity[-1] == 1.0 and shell.panels[0].opacity[-1] == 1.0
    assert shell._fade.state == "shown"


def test_one_panel_failing_its_input_does_not_leave_the_others_without_input(build, loop, caplog):
    shell = build(edge(DOCK, CLOCK))

    def gone(_enabled):
        raise RuntimeError("panel destroyed")

    shell.panels[0].set_input_enabled = gone
    loop.run_idles()
    loop.fire(500)
    shell.frames(4)
    assert shell.panels[1].inputs[-1] is True  # still restored
    assert len(shell.faded) == 1 and "input" in caplog.text  # on_fade_in still ran


def test_a_panel_that_cannot_drop_its_input_does_not_stop_the_fade_out(build, loop, caplog):
    shell = build(edge(DOCK, CLOCK))
    shown(shell, loop)

    def gone(_enabled):
        raise RuntimeError("panel destroyed")

    shell.panels[0].set_input_enabled = gone
    done = []
    shell.fade_out(50, done.append)
    assert shell.panels[1].inputs[-1] is False and "input" in caplog.text  # the others dropped
    assert shell.fade_state == "fading-out" and shell.strips == []
    shell.frames(5)
    assert shell.canvas.destroyed and done == [shell] and shell.fade_state == "done"


def test_a_build_that_fails_after_the_canvas_leaves_no_fade_behind(build, loop, monkeypatch):
    def bad_strip(*_args, **_kwargs):
        raise RuntimeError("strip failed")

    monkeypatch.setattr(mon_mod, "FrameEdge", bad_strip)
    canvases = []

    def canvas(*args, **kwargs):
        canvases.append(TickCanvas(*args, **kwargs))
        return canvases[-1]

    monkeypatch.setattr(mon_mod, "ShapeCanvas", canvas)
    with pytest.raises(RuntimeError, match="strip failed"):
        build(edge(DOCK))
    assert canvases[0].opacity == [0.0] and canvases[0].destroyed  # never left invisible
    assert loop.timers == {} and loop.idles == {}  # the ready timeout went with it
    assert not canvases[0].ticker._callbacks


# ---- fade-out (Task 4) ----------------------------------------------------------------


def test_fade_out_fades_every_window_then_closes_and_calls_back_once(build, loop):
    shell = build(edge(DOCK))
    shown(shell, loop)
    canvas, panel, strips = shell.canvas, shell.panels[0], list(shell.strips)
    done = []
    shell.fade_out(50, done.append)
    assert all(s.destroyed for s in strips) and shell.strips == []  # the zones go at once
    assert panel.inputs[-1] is False and not canvas.destroyed  # clicks go through it now
    shell.frames(4)
    out = canvas.opacity[-4:]
    assert out == pytest.approx(list(reversed(THIRDS)), abs=1e-3)  # from 1 down to 0
    assert panel.opacity[-4:] == out  # the same frames for every window
    assert canvas.destroyed and panel.destroyed and done == [shell]
    assert shell.fade_state == "done" and not canvas.ticker._callbacks
    shell.frames(3)
    assert done == [shell]


def test_fade_out_with_zero_ms_closes_at_once_as_before(build, loop):
    shell = build(edge(DOCK))
    shown(shell, loop)
    panel, seen = shell.panels[0], len(shell.canvas.opacity)
    done = []
    shell.fade_out(0, done.append)
    assert panel.destroyed and shell.canvas.destroyed and done == [shell]
    assert len(shell.canvas.opacity) == seen and panel.inputs == [False, True]


def test_a_shell_that_was_never_visible_is_closed_at_once(build, loop):
    shell = build(edge(DOCK))  # still waiting for its fade-in
    done = []
    shell.fade_out(50, done.append)
    assert shell.canvas.destroyed and done == [shell] and shell.faded == []
    assert loop.idles == {} and loop.delays() == [500, 2000]  # only no-op re-raises left


def test_fade_out_mid_fade_in_goes_down_from_where_it_is(build, loop):
    shell = build(edge(DOCK))
    loop.run_idles()
    loop.fire(500)
    shell.frames(2)  # the start, then 1/3
    now = shell.canvas.opacity[-1]
    shell.fade_out(50, lambda _s: None)
    shell.frames(6)
    after = shell.canvas.opacity[shell.canvas.opacity.index(now) + 1 :]
    assert max(after) <= now + 1e-9 and after[-1] == 0.0  # never a jump up
    assert shell.canvas.destroyed


def test_a_second_fade_out_is_ignored(build, loop):
    shell = build(edge(DOCK))
    shown(shell, loop)
    first, second = [], []
    shell.fade_out(50, first.append)
    shell.fade_out(50, second.append)
    shell.frames(5)
    assert first == [shell] and second == []


def test_a_shell_built_without_a_fade_still_fades_out_when_asked(build, loop):
    """fade_ms went from 0 to 50 between the monitor's start and its turn-off."""
    shell = build(edge(DOCK), fade_ms=0)
    loop.fire(500)
    done = []
    shell.fade_out(50, done.append)
    shell.frames(4)
    # from the opacity it has (1: never set before) down to 0; the start is not set twice
    assert shell.canvas.opacity == pytest.approx(list(reversed(THIRDS)), abs=1e-3)
    assert shell.canvas.destroyed and done == [shell]


def test_a_detached_shell_no_longer_re_raises_re_lays_out_or_measures(build, loop):
    shell = build(edge({**DOCK, "length": "content"}))
    monitor, panel = shell.monitor, shell.panels[0]
    shell.detach()
    assert loop.idles == {}  # the measurement and the ready check are dropped
    assert monitor.handlers == {}  # the geometry is no longer watched
    loop.fire(500)
    loop.fire(2000)
    assert panel.raised == 0 and not panel.destroyed  # never re-mapped: a re-map blinks
    assert shell._fade.state == "waiting"  # never shown by the late re-raise either
    shell.detach()  # once only
    shell.close()
    assert panel.destroyed


def test_a_failing_fade_out_callback_is_logged_and_the_shell_is_closed(build, loop, caplog):
    shell = build(edge(DOCK))
    shown(shell, loop)

    def boom(_shell):
        raise RuntimeError("callback failed")

    shell.fade_out(50, boom)
    shell.frames(5)
    assert shell.canvas.destroyed and "the fade-out callback of HDMI-A-1 failed" in caplog.text


def test_a_panel_added_before_the_detach_is_not_re_raised_by_its_pending_timers(build, loop):
    shell = build(edge(DOCK))
    shown(shell, loop)
    config = shell.config_for(monitors=edge(DOCK, CLOCK))
    shell.apply(config, [Change("panel-add", "HDMI-A-1", 1)])
    added = shell.panels[1]
    shell.detach()
    loop.fire(500)
    loop.fire(2000)
    assert added.raised == 0  # a re-map of a leaving window blinks


# ---- crossfade, end to end with the real app (Task 5) -----------------------------------


class Store:
    """A ConfigStore stand-in: `pending` is what the next reload reads."""

    def __init__(self, config):
        self.config, self.pending, self.path, self.last_error = config, None, None, None

    def reload(self):
        old, self.config = self.config, self.pending
        return old, self.config


def test_a_rebuild_crossfades_two_real_shells_in_the_same_frames(
    build, loop, monkeypatch, make_config
):
    """`build` installs the window fakes; the app builds the real MonitorShells on them."""
    monitor = FakeMonitor()
    monkeypatch.setattr(app_mod, "monitors_by_name", lambda: {"HDMI-A-1": monitor})
    monkeypatch.setattr(app_mod.subprocess, "Popen", lambda *_a, **_k: None)
    store = Store(make_config(monitors=edge(DOCK)))
    app = app_mod.EdgeShellApp(store)
    app.sync_monitors()
    old = app.shells["HDMI-A-1"]
    loop.run_idles()
    loop.fire(500)
    clock = FakeClock()

    def vsync(n, *shells):  # one output: both canvases get the same frame times
        for _ in range(n):
            clock.now_us += FRAME_US
            for shell in shells:
                shell.canvas.ticker.run(clock)

    vsync(4, old)
    assert old.fade_state == "shown"
    old_strips = list(old.strips)
    store.pending = make_config(monitors=edge(DOCK), theme={"thickness": 12})
    app.reload()
    new = app.shells["HDMI-A-1"]
    assert new is not old and app._leaving == {"HDMI-A-1": old}
    assert all(s.destroyed for s in old_strips)  # the edges are reserved once: by the new ones
    assert old.canvas.opacity[-1] == 1.0 and new.canvas.opacity == [0.0]  # old still shown
    assert old.panels[0].inputs == [False, True]  # the held shell keeps its input
    loop.run_idles()
    loop.fire(500)  # the new shell is ready: the crossfade starts
    assert new.panels[0].inputs == [False, True] and old.panels[0].inputs[-1] is False
    old_canvas = old.canvas
    vsync(4, new, old)
    assert new.canvas.opacity[-4:] == pytest.approx(THIRDS, abs=1e-3)
    assert old_canvas.opacity[-4:] == pytest.approx(list(reversed(THIRDS)), abs=1e-3)
    assert old_canvas.destroyed and old.panels == [] and app._leaving == {}
    assert not new.canvas.destroyed and new.fade_state == "shown"
