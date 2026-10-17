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

    def _build(monitors, fade_ms=50, theme=None, reserve_now=True):
        faded, reserved = [], []
        shell = mon_mod.MonitorShell(
            "HDMI-A-1",
            FakeMonitor(),
            make_config(monitors=monitors, theme=theme),
            lambda _w: None,
            fade_ms=fade_ms,
            on_fade_in=faded.append,
            reserve_now=reserve_now,
            on_reserved=reserved.append,
        )
        clock = FakeClock()

        def frames(n):
            for _ in range(n):
                clock.now_us += FRAME_US
                shell.canvas.ticker.run(clock)

        shell.frames, shell.faded, shell.config_for = frames, faded, make_config
        shell.reserved = reserved
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
    assert shell.fade_state == "fading-out" and len(shell.strips) == 4  # kept
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
    # the zones stay until the frame is gone: a window must not grow into the fading frame
    assert shell.strips == strips and not any(s.destroyed for s in strips)
    assert panel.inputs[-1] is False and not canvas.destroyed  # clicks go through it now
    shell.frames(2)
    assert not any(s.destroyed for s in strips) and set(strips) <= set(shell.windows)
    shell.frames(2)
    out = canvas.opacity[-4:]
    assert out == pytest.approx(list(reversed(THIRDS)), abs=1e-3)  # from 1 down to 0
    assert panel.opacity[-4:] == out  # the same frames for every window
    assert canvas.destroyed and panel.destroyed and done == [shell]
    assert shell.fade_state == "done" and not canvas.ticker._callbacks
    assert all(s.destroyed for s in strips) and shell.strips == []  # gone with the frame
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


def test_finish_fade_completes_only_a_fade_in(build, loop):
    shell = build(edge(DOCK))
    shell.finish_fade()  # waiting: nothing to complete (it may never be shown)
    assert shell.fade_state == "waiting" and shell.canvas.opacity == [0.0]
    loop.run_idles()
    loop.fire(500)
    shell.frames(2)
    shell.finish_fade()
    assert shell.fade_state == "shown" and all(w.opacity[-1] == 1.0 for w in shell.windows)
    assert not shell.canvas.ticker._callbacks
    shell.finish_fade()  # shown: nothing
    assert shell.fade_state == "shown"


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

    assert old.strips == []  # a fresh enable: the zones come 100 ms after the fade-in starts
    vsync(4, old)
    assert old.fade_state == "shown"
    loop.fire(mon_mod.RESERVE_DELAY_MS)
    old_strips = list(old.strips)
    assert len(old_strips) == 4
    store.pending = make_config(monitors=edge(DOCK), theme={"thickness": 12})
    app.reload()
    new = app.shells["HDMI-A-1"]
    assert new is not old and app._leaving == {"HDMI-A-1": old}
    # the held shell keeps its zone: the window must not shrink before the new frame appears
    assert old.strips == old_strips and not any(s.destroyed for s in old_strips)
    assert new.strips == []
    assert old.canvas.opacity[-1] == 1.0 and new.canvas.opacity == [0.0]  # old still shown
    assert old.panels[0].inputs == [False, True]  # the held shell keeps its input
    loop.run_idles()
    loop.fire(500)  # the new shell is ready: the crossfade starts
    assert new.strips == [] and not any(s.destroyed for s in old_strips)  # still the old zone
    loop.fire(mon_mod.RESERVE_DELAY_MS)  # 100 ms after the new frame starts to appear
    live = [x for x in (*old_strips, *new.strips) if not x.destroyed]
    assert len(live) == 4 and live == new.strips  # handed over: exactly one set
    assert all(s.destroyed for s in old_strips) and old.strips == []
    assert new.panels[0].inputs == [False, True] and old.panels[0].inputs[-1] is False
    old_canvas = old.canvas
    vsync(4, new, old)
    assert new.canvas.opacity[-4:] == pytest.approx(THIRDS, abs=1e-3)
    assert old_canvas.opacity[-4:] == pytest.approx(list(reversed(THIRDS)), abs=1e-3)
    assert old_canvas.destroyed and old.panels == [] and app._leaving == {}
    assert not new.canvas.destroyed and new.fade_state == "shown"


# ---- the zone strips: 100 ms after a fade-in starts, until a fade-out ends (Phil's gate) ----


def started(shell, loop):
    """Run a fresh (late-reserving) build up to the start of its fade-in."""
    loop.run_idles()
    loop.fire(mon_mod.RAISE_DELAY_MS)
    assert shell.fade_state == "fading-in"


def test_a_fresh_enable_builds_no_strips_with_the_shell(build, loop):
    shell = build(edge(DOCK), reserve_now=False)
    assert shell.strips == [] and len(shell.windows) == 2  # canvas, panel
    assert mon_mod.RESERVE_DELAY_MS not in loop.delays()  # nothing is armed before the fade-in
    loop.run_idles()
    assert shell.strips == [] and mon_mod.RESERVE_DELAY_MS not in loop.delays()


def test_the_strips_come_100_ms_after_the_fade_in_starts_and_not_before(build, loop):
    assert mon_mod.RESERVE_DELAY_MS == 100
    shell = build(edge(DOCK, CLOCK), reserve_now=False)
    started(shell, loop)
    assert shell.faded == [shell] and shell.strips == []  # the frame appears first
    assert loop.delays().count(100) == 1
    shell.frames(1)
    assert shell.strips == []
    loop.fire(100)
    assert len(shell.strips) == 4 and len(shell.windows) == 7
    assert [s.args[0] for s in shell.strips] == list(mon_mod.EDGES)
    assert all(s in shell.windows for s in shell.strips)
    assert all(s.opacity == [pytest.approx(shell._fade.value)] for s in shell.strips)
    shell.frames(4)
    assert all(s.opacity[-1] == 1.0 for s in shell.strips) and shell.fade_state == "shown"
    assert 100 not in loop.delays()


def test_the_late_strips_take_the_shells_current_theme(build, loop):
    shell = build(edge(DOCK), reserve_now=False, theme={"thickness": 8})
    started(shell, loop)
    config = shell.config_for(monitors=edge(DOCK), theme={"thickness": 12})
    shell.apply(config, [Change("restyle", "HDMI-A-1")])  # before the strips exist
    loop.fire(100)
    assert [s.args[2].thickness for s in shell.strips] == [12] * 4


def test_the_late_strips_are_not_built_when_the_shell_closes_first(build, loop):
    shell = build(edge(DOCK), reserve_now=False)
    started(shell, loop)
    (source,) = [i for i, (ms, _, _) in loop.timers.items() if ms == 100]
    shell.close()
    assert 100 not in loop.delays() and source in loop.removed
    assert shell.strips == [] and shell.windows == []


def test_the_late_strips_are_not_built_when_the_shell_is_detached_first(build, loop):
    shell = build(edge(DOCK), reserve_now=False)
    started(shell, loop)
    shell.detach()
    assert 100 not in loop.delays() and shell.strips == []
    shell.close()


def test_a_disable_right_after_the_enable_never_builds_the_strips(build, loop):
    shell = build(edge(DOCK), reserve_now=False)
    started(shell, loop)
    done = []
    shell.fade_out(50, done.append)
    assert 100 not in loop.delays() and shell.strips == []
    shell.frames(5)
    assert done == [shell] and shell.strips == []


def test_a_timer_that_fires_late_on_a_closed_shell_builds_nothing(build, loop):
    shell = build(edge(DOCK), reserve_now=False)
    started(shell, loop)
    (_, fn, _args), *_ = [t for t in loop.timers.values() if t[0] == 100]
    shell.close()
    assert fn() is False and shell.strips == [] and shell.windows == []


def test_reserve_now_builds_the_strips_in_the_build_without_a_timer(build, loop):
    shell = build(edge(DOCK), reserve_now=True)
    assert len(shell.strips) == 4 and len(shell.windows) == 6
    started(shell, loop)
    assert 100 not in loop.delays()  # no timer, and no second set
    assert len(shell.strips) == 4 and len(shell.windows) == 6 and shell.reserved == []


def test_without_a_fade_the_strips_are_built_at_once_whatever_is_asked(build, loop):
    shell = build(edge(DOCK), fade_ms=0, reserve_now=False)
    assert len(shell.strips) == 4 and 100 not in loop.delays()
    loop.fire(500)
    assert len(shell.strips) == 4 and 100 not in loop.delays()
    assert all(w.opacity == [] for w in shell.windows)


def test_a_plain_disable_keeps_the_strips_until_the_fade_out_ends(build, loop):
    shell = build(edge(DOCK), reserve_now=False)
    started(shell, loop)
    loop.fire(100)
    shell.frames(4)
    strips = list(shell.strips)
    done = []
    shell.fade_out(50, done.append)
    for _ in range(3):  # the whole fade-out but its last frame: the frame is still partly there
        shell.frames(1)
        assert shell.canvas.opacity[-1] > 0 and not any(s.destroyed for s in strips)
        assert shell.strips == strips and set(strips) <= set(shell.windows)
    shell.frames(1)
    assert done == [shell] and all(s.destroyed for s in strips) and shell.strips == []
    assert shell.windows == []


def test_detach_keeps_the_strips_only_when_asked(build, loop):
    kept = build(edge(DOCK))
    strips = list(kept.strips)
    kept.detach(keep_strips=True)
    assert kept.strips == strips and not any(s.destroyed for s in strips)
    kept.detach()  # once only: the second call changes nothing
    assert kept.strips == strips and not any(s.destroyed for s in strips)
    kept.close()
    assert all(s.destroyed for s in strips) and kept.strips == [] and kept.windows == []
    plain = build(edge(DOCK))
    strips = list(plain.strips)
    plain.detach()
    assert plain.strips == [] and all(s.destroyed for s in strips)
    assert all(s not in plain.windows for s in strips)


def test_a_quit_in_the_middle_of_a_fade_out_leaves_no_strip_behind(build, loop):
    shell = build(edge(DOCK), reserve_now=False)
    started(shell, loop)
    loop.fire(100)
    shell.frames(4)
    strips = list(shell.strips)
    shell.fade_out(50, lambda _s: None)
    shell.frames(1)
    shell.close()  # the quit status: everything goes now
    assert all(s.destroyed for s in strips) and shell.strips == [] and shell.windows == []
    assert not shell.canvas.ticker._callbacks and 100 not in loop.delays()


def test_a_failing_late_strip_is_logged_and_the_shell_closes_cleanly(
    build, loop, monkeypatch, caplog
):
    shell = build(edge(DOCK), reserve_now=False)
    started(shell, loop)
    real, built = mon_mod.FrameEdge, []

    def flaky(edge_name, *args):
        if edge_name == "left":
            raise RuntimeError("no strip")
        built.append(real(edge_name, *args))
        return built[-1]

    monkeypatch.setattr(mon_mod, "FrameEdge", flaky)
    loop.fire(100)  # a GLib callback: never raises into the main loop
    assert "reserving the edges" in caplog.text
    shell.close()
    assert all(s.destroyed for s in built) and shell.windows == [] and shell.strips == []


def test_disabling_a_monitor_keeps_its_strips_until_the_frame_is_gone_end_to_end(
    build, loop, monkeypatch, make_config
):
    """The app's own path: Enable unticked -> _close_shell -> fade_out (Phil's finding 3)."""
    monitor = FakeMonitor()
    monkeypatch.setattr(app_mod, "monitors_by_name", lambda: {"HDMI-A-1": monitor})
    monkeypatch.setattr(app_mod.subprocess, "Popen", lambda *_a, **_k: None)
    store = Store(make_config(monitors=edge(DOCK)))
    app = app_mod.EdgeShellApp(store)
    app.sync_monitors()
    shell = app.shells["HDMI-A-1"]
    assert shell.strips == []  # a fresh enable
    loop.run_idles()
    loop.fire(500)
    loop.fire(mon_mod.RESERVE_DELAY_MS)
    clock = FakeClock()

    def frames(n):
        for _ in range(n):
            clock.now_us += FRAME_US
            shell.canvas.ticker.run(clock)

    frames(4)
    strips = list(shell.strips)
    assert len(strips) == 4
    store.pending = make_config(monitors={"HDMI-A-1": {"shell": "plasma"}})
    app.reload()
    assert "HDMI-A-1" not in app.shells and app._leaving == {"HDMI-A-1": shell}
    assert not any(s.destroyed for s in strips)  # the window must not grow into the frame yet
    frames(2)
    assert not any(s.destroyed for s in strips) and shell.canvas.opacity[-1] > 0
    frames(2)
    assert all(s.destroyed for s in strips) and app._leaving == {}


def test_a_timer_that_fires_late_on_a_detached_shell_builds_nothing(build, loop):
    shell = build(edge(DOCK), reserve_now=False)
    started(shell, loop)
    (_, fn, _args), *_ = [t for t in loop.timers.values() if t[0] == 100]
    shell.detach()
    assert fn() is False and shell.strips == []
    shell.close()


# ---- a held shell keeps its zone until its successor has its own (Phil's re-check) ----


def test_on_reserved_is_called_once_the_late_strips_exist(build, loop):
    shell = build(edge(DOCK), reserve_now=False)
    started(shell, loop)
    assert shell.reserved == []
    loop.fire(100)
    assert shell.reserved == [shell] and len(shell.strips) == 4


def test_a_failing_on_reserved_is_logged_and_the_strips_stay(build, loop, caplog):
    shell = build(edge(DOCK), reserve_now=False)
    started(shell, loop)

    def boom(_shell):
        raise RuntimeError("callback failed")

    shell._on_reserved = boom
    loop.fire(100)
    assert len(shell.strips) == 4 and "the reserve callback of HDMI-A-1 failed" in caplog.text


def test_drop_strips_destroys_them_once_and_close_still_works(build, loop):
    shell = build(edge(DOCK))
    strips = list(shell.strips)
    shell.drop_strips()
    assert shell.strips == [] and all(s.destroyed for s in strips)
    assert all(s not in shell.windows for s in strips) and len(shell.windows) == 2
    shell.drop_strips()  # nothing left
    shell.close()
    assert shell.windows == []


def test_a_held_shell_keeps_its_strips_through_detach_and_a_late_release_fades_with_them(
    build, loop
):
    shell = build(edge(DOCK))
    shown(shell, loop)
    strips = list(shell.strips)
    shell.detach(keep_strips=True)  # held for a crossfade
    done = []
    shell.fade_out(50, done.append)  # its successor never came
    shell.frames(2)
    assert shell.strips == strips and not any(s.destroyed for s in strips)
    shell.frames(2)
    assert done == [shell] and all(s.destroyed for s in strips) and shell.strips == []


def test_reserve_pending_now_builds_the_strips_when_the_timer_is_pending(build, loop):
    shell = build(edge(DOCK), reserve_now=False)
    started(shell, loop)
    (source,) = [i for i, (ms, _, _) in loop.timers.items() if ms == 100]
    shell.reserve_pending_now()
    assert len(shell.strips) == 4 and source in loop.removed and 100 not in loop.delays()
    assert shell.reserved == [shell]
    shell.reserve_pending_now()  # nothing pending now
    assert len(shell.strips) == 4 and shell.reserved == [shell]


def test_reserve_pending_now_does_nothing_without_a_pending_timer(build, loop):
    shell = build(edge(DOCK), reserve_now=False)
    shell.reserve_pending_now()  # still waiting for its fade-in
    assert shell.strips == [] and shell.reserved == []
    started(shell, loop)
    shell.close()
    shell.reserve_pending_now()
    assert shell.strips == [] and shell.windows == []


def test_a_held_shell_whose_waiting_successor_is_disabled_keeps_a_zone_while_it_fades(
    build, loop, monkeypatch, make_config
):
    """Gate item 7 on the real shells: rebuild, then untick Enable before the new frame
    appears: the held old shell fades out, and a maximized window must not grow under it."""
    monitor = FakeMonitor()
    monkeypatch.setattr(app_mod, "monitors_by_name", lambda: {"HDMI-A-1": monitor})
    monkeypatch.setattr(app_mod.subprocess, "Popen", lambda *_a, **_k: None)
    store = Store(make_config(monitors=edge(DOCK)))
    app = app_mod.EdgeShellApp(store)
    app.sync_monitors()
    old = app.shells["HDMI-A-1"]
    loop.run_idles()
    loop.fire(500)
    loop.fire(mon_mod.RESERVE_DELAY_MS)
    clock = FakeClock()

    def vsync(n, *shells):
        for _ in range(n):
            clock.now_us += FRAME_US
            for shell in shells:
                shell.canvas.ticker.run(clock)

    vsync(4, old)
    strips = list(old.strips)
    assert len(strips) == 4
    store.pending = make_config(monitors=edge(DOCK), theme={"thickness": 12})
    app.reload()
    new = app.shells["HDMI-A-1"]
    assert old.strips == strips and new.fade_state == "waiting"  # held with its zone
    store.pending = make_config(monitors={"HDMI-A-1": {"shell": "plasma"}})
    app.reload()  # the waiting successor is closed; the held one fades out
    assert old.fading_out and new.fade_state == "done" and new.strips == []
    assert old.strips == strips and not any(s.destroyed for s in strips)
    vsync(2, old)
    assert not any(s.destroyed for s in strips) and old.canvas.opacity[-1] > 0
    vsync(2, old)
    assert all(s.destroyed for s in strips) and app._leaving == {}


def test_a_second_reload_while_the_first_successor_fades_in_hands_its_zone_over(
    build, loop, monkeypatch, make_config
):
    """Rebuild, then rebuild again after the new frame started but before its zone (100 ms):
    the older held shell goes at once, so the first successor builds its strips first."""
    monitor = FakeMonitor()
    monkeypatch.setattr(app_mod, "monitors_by_name", lambda: {"HDMI-A-1": monitor})
    monkeypatch.setattr(app_mod.subprocess, "Popen", lambda *_a, **_k: None)
    store = Store(make_config(monitors=edge(DOCK)))
    app = app_mod.EdgeShellApp(store)
    app.sync_monitors()
    first = app.shells["HDMI-A-1"]
    loop.run_idles()
    loop.fire(500)
    loop.fire(mon_mod.RESERVE_DELAY_MS)
    first_strips = list(first.strips)
    store.pending = make_config(monitors=edge(DOCK), theme={"thickness": 12})
    app.reload()
    second = app.shells["HDMI-A-1"]
    loop.run_idles()
    loop.fire(500)  # the second shell's frame starts; its zone is due in 100 ms
    assert second.strips == [] and not any(s.destroyed for s in first_strips)
    store.pending = make_config(monitors=edge(DOCK), theme={"thickness": 14})
    app.reload()  # replaced before its zone came: first goes now, second keeps a zone
    third = app.shells["HDMI-A-1"]
    assert app._leaving == {"HDMI-A-1": second} and first.fade_state == "done"
    assert len(second.strips) == 4 and not any(s.destroyed for s in second.strips)
    assert all(s.destroyed for s in first_strips) and third.strips == []
    loop.run_idles()
    loop.fire(500)
    assert 100 in loop.delays()  # the third one's zone is due
    loop.fire(100)
    assert len(third.strips) == 4 and all(s.destroyed for s in second.strips)


def test_a_re_enable_during_a_fade_out_swaps_the_zone_when_the_new_one_has_its_own(
    build, loop, monkeypatch, make_config
):
    monitor = FakeMonitor()
    monkeypatch.setattr(app_mod, "monitors_by_name", lambda: {"HDMI-A-1": monitor})
    monkeypatch.setattr(app_mod.subprocess, "Popen", lambda *_a, **_k: None)
    store = Store(make_config(monitors=edge(DOCK)))
    app = app_mod.EdgeShellApp(store)
    app.sync_monitors()
    first = app.shells["HDMI-A-1"]
    loop.run_idles()
    loop.fire(500)
    loop.fire(mon_mod.RESERVE_DELAY_MS)
    first_strips = list(first.strips)
    clock = FakeClock()
    for _ in range(2):  # the frame is partly there
        clock.now_us += FRAME_US
        first.canvas.ticker.run(clock)
    store.pending = make_config(monitors={"HDMI-A-1": {"shell": "plasma"}})
    app.reload()  # disabled: fading out with its zone
    store.pending = make_config(monitors=edge(DOCK))
    app.reload()  # enabled again right away
    again = app.shells["HDMI-A-1"]
    assert again.strips == [] and not any(s.destroyed for s in first_strips)
    loop.run_idles()
    loop.fire(500)
    loop.fire(mon_mod.RESERVE_DELAY_MS)
    assert len(again.strips) == 4 and all(s.destroyed for s in first_strips)


def rebuild_probe(loop, monkeypatch, make_config, fade_ms):
    """Real shells: a rebuild with a maximized window. Returns the live-strip counts seen on
    every frame while a frame is visible, and the app."""
    monitor = FakeMonitor()
    monkeypatch.setattr(app_mod, "monitors_by_name", lambda: {"HDMI-A-1": monitor})
    monkeypatch.setattr(app_mod.subprocess, "Popen", lambda *_a, **_k: None)
    theme = {"fade_ms": fade_ms}
    store = Store(make_config(monitors=edge(DOCK), theme=theme))
    app = app_mod.EdgeShellApp(store)
    app.sync_monitors()
    old = app.shells["HDMI-A-1"]
    clock = FakeClock()

    def vsync(*shells):
        clock.now_us += FRAME_US
        for shell in shells:
            if not shell.canvas.destroyed:
                shell.canvas.ticker.run(clock)

    loop.run_idles()
    loop.fire(500)
    loop.fire(mon_mod.RESERVE_DELAY_MS)
    for _ in range(40):
        vsync(old)
    assert old.fade_state == "shown" and len(old.strips) == 4
    store.pending = make_config(monitors=edge(DOCK), theme={**theme, "thickness": 12})
    app.reload()
    new = app.shells["HDMI-A-1"]
    loop.run_idles()
    loop.fire(500)  # the new frame starts to appear, the old one fades out
    seen, fired = [], False
    for frame in range(60):
        vsync(new, old)
        if fade_ms > mon_mod.RESERVE_DELAY_MS and frame == 6 and not fired:
            loop.fire(mon_mod.RESERVE_DELAY_MS)  # its own timer, about 100 ms in
            fired = True
        live = [s for sh in (old, new) for s in sh.strips if not s.destroyed]
        seen.append(len(live))
        if app._leaving == {} and new.fade_state == "shown":
            break
    return seen, app, old, new


@pytest.mark.parametrize("fade_ms", [50, 80, 100, 200])
def test_a_rebuild_never_leaves_the_zone_empty_whatever_the_fade_length(
    build, loop, monkeypatch, make_config, fade_ms
):
    seen, app, old, new = rebuild_probe(loop, monkeypatch, make_config, fade_ms)
    assert seen and set(seen) == {4}, seen  # one full set on every frame, never none, never two
    assert app._leaving == {} and old.strips == [] and len(new.strips) == 4
    assert mon_mod.RESERVE_DELAY_MS not in loop.delays()  # the timer was consumed or fired


def test_a_rebuild_within_100_ms_of_a_fresh_enable_keeps_the_held_frames_zone(
    build, loop, monkeypatch, make_config
):
    monitor = FakeMonitor()
    monkeypatch.setattr(app_mod, "monitors_by_name", lambda: {"HDMI-A-1": monitor})
    monkeypatch.setattr(app_mod.subprocess, "Popen", lambda *_a, **_k: None)
    store = Store(make_config(monitors=edge(DOCK)))
    app = app_mod.EdgeShellApp(store)
    app.sync_monitors()
    first = app.shells["HDMI-A-1"]
    loop.run_idles()
    loop.fire(500)  # its frame starts to appear; its zone is due in 100 ms
    assert first.strips == []
    store.pending = make_config(monitors=edge(DOCK), theme={"thickness": 12})
    app.reload()  # the rebuild comes first: the held frame must have its zone
    assert app._leaving == {"HDMI-A-1": first} and len(first.strips) == 4
    assert not any(s.destroyed for s in first.strips)


def test_on_closing_runs_once_when_the_fade_out_ends_before_the_windows_go(build, loop):
    shell = build(edge(DOCK))
    shown(shell, loop)
    seen = []
    shell._on_closing = lambda s: seen.append(([x.destroyed for x in s.strips], s.canvas.destroyed))
    shell.fade_out(50, lambda _s: None)
    shell.frames(3)
    assert seen == []  # not while the frame is still there
    shell.frames(2)
    assert seen == [([False] * 4, False)] and shell.canvas.destroyed


def test_a_failing_on_closing_is_logged_and_the_shell_still_closes(build, loop, caplog):
    shell = build(edge(DOCK))
    shown(shell, loop)

    def boom(_shell):
        raise RuntimeError("callback failed")

    shell._on_closing = boom
    done = []
    shell.fade_out(50, done.append)
    shell.frames(5)
    assert shell.canvas.destroyed and done == [shell]
    assert "the closing callback of HDMI-A-1 failed" in caplog.text


# ---- a strip that fails to build leaves no earlier strip behind ----------------------


class FlakyEdges:
    """FrameEdge stand-in: the `fail_on`-th strip asked for raises, the others are FakeWindows."""

    def __init__(self, fail_on):
        self.fail_on, self.calls, self.made = fail_on, 0, []

    def __call__(self, *args, **kwargs):
        self.calls += 1
        if self.calls == self.fail_on:
            raise RuntimeError("strip broke")
        strip = FakeWindow(*args, **kwargs)
        self.made.append(strip)
        return strip


@pytest.fixture
def flaky(build, make_config, monkeypatch):
    """flaky(fail_on, **kwargs) -> (shell or None, edges, registered, unregistered, error)."""

    def _flaky(fail_on, **kwargs):
        edges = FlakyEdges(fail_on)
        monkeypatch.setattr(mon_mod, "FrameEdge", edges)
        registered, unregistered = [], []
        shell = error = None
        try:
            shell = mon_mod.MonitorShell(
                "HDMI-A-1",
                FakeMonitor(),
                make_config(monitors=edge(DOCK)),
                registered.append,
                unregistered.append,
                **kwargs,
            )
        except RuntimeError as exc:
            error = exc
        return shell, edges, registered, unregistered, error

    return _flaky


@pytest.mark.parametrize("kwargs", [{"fade_ms": 0}, {"fade_ms": 50, "reserve_now": True}])
def test_a_strip_failing_in_the_build_releases_the_earlier_strips(flaky, kwargs):
    shell, edges, registered, unregistered, error = flaky(3, **kwargs)
    assert shell is None and error is not None and len(edges.made) == 2
    assert all(s in registered for s in edges.made)  # they were on screen
    assert registered and all(w.destroyed for w in registered)  # none keeps reserving space
    assert {id(w) for w in unregistered} == {id(w) for w in registered}


def test_a_strip_failing_late_is_logged_and_close_releases_the_earlier_strips(flaky, loop, caplog):
    shell, edges, registered, unregistered, error = flaky(3, fade_ms=50, reserve_now=False)
    assert error is None and shell is not None
    started(shell, loop)
    loop.fire(100)
    assert "reserving the edges of HDMI-A-1 failed" in caplog.text
    assert len(edges.made) == 2 and shell.strips == edges.made  # partial, but tracked
    assert all(s in shell.windows and s in registered for s in edges.made)
    shell.close()
    assert shell.strips == [] and shell.windows == []
    assert all(w.destroyed for w in registered)  # canvas, panel and both strips
    assert all(s in unregistered for s in edges.made)
