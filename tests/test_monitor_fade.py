"""MonitorShell's fade (spec 21), display-free: fake windows, the canvas as a fake frame clock
(shell.canvas.simulate), fake GLib timers and idles."""

import pytest

pytest.importorskip("gi")
pytest.importorskip("fabric")

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
