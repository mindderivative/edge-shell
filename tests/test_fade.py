"""shell.fade.Fade: the fade of one monitor's windows, on a fake frame clock and fake timers
(pure: no GTK)."""

import logging

import pytest

from shell.canvas.simulate import FRAME_US, FakeClock, FakeTicker
from shell.fade import FINISH_MARGIN_MS, READY_TIMEOUT_MS, Fade


class FakeTimers:
    """GLib.timeout_add / GLib.source_remove stand-ins; `fire(ms)` runs the pending timer of
    that delay as the main loop would (a False return removes it)."""

    def __init__(self):
        self.pending: dict[int, tuple[int, object]] = {}
        self.removed: list[int] = []
        self._next = 1

    def add(self, ms, fn):
        timer, self._next = self._next, self._next + 1
        self.pending[timer] = (ms, fn)
        return timer

    def remove(self, timer):
        assert timer in self.pending, "removed a timer that is not pending (GLib warns)"
        del self.pending[timer]
        self.removed.append(timer)

    def delays(self):
        return sorted(ms for ms, _ in self.pending.values())

    def fire(self, ms):
        timer = next(t for t, (d, _) in self.pending.items() if d == ms)
        _, fn = self.pending.pop(timer)
        assert fn() is False  # a one-shot GLib source


class Rig:
    """One Fade with everything it is given recorded."""

    def __init__(self, duration_ms=50):
        self.clock, self.ticker, self.timers = FakeClock(), FakeTicker(), FakeTimers()
        self.values, self.started, self.done = [], 0, 0
        self.frame = 0
        self.fade = Fade(
            self.ticker,
            self.values.append,
            duration_ms,
            self.timers.add,
            self.timers.remove,
            on_start=self._start,
        )

    def _start(self):
        self.started += 1

    def on_done(self):
        self.done += 1

    def frames(self, n):
        for _ in range(n):
            self.clock.now_us = self.frame * FRAME_US
            self.frame += 1
            self.ticker.run(self.clock)

    @property
    def ticking(self):
        return bool(self.ticker._callbacks)


def test_zero_ms_is_shown_from_the_start_and_does_no_fade_work():
    rig = Rig(0)
    assert rig.fade.state == "shown" and rig.fade.value == 1.0
    rig.fade.ready()
    rig.fade.finish()
    rig.frames(5)
    assert rig.values == [] and rig.timers.pending == {} and not rig.ticking
    assert rig.started == 0  # nothing waits for a fade that never runs
    rig.fade.fade_out(0, rig.on_done)
    assert rig.done == 1 and rig.fade.state == "done" and rig.values == []


def test_it_starts_transparent_and_waits_for_ready():
    rig = Rig()
    assert rig.values == [0.0] and rig.fade.state == "waiting"
    assert rig.timers.delays() == [READY_TIMEOUT_MS]
    rig.frames(10)  # frames alone never start it
    assert rig.values == [0.0] and not rig.ticking


def test_ready_fades_in_linearly_over_the_duration_on_the_frame_clock():
    rig = Rig(50)
    rig.fade.ready()
    assert rig.fade.state == "fading-in" and rig.started == 1
    assert rig.timers.delays() == [50 + FINISH_MARGIN_MS]  # the ready timeout is gone
    rig.frames(5)
    # the first frame still shows 0: the start is the frame time of the first tick; a 50 ms
    # fade is 3 frames at 60 Hz
    assert rig.values[:2] == [0.0, 0.0]
    assert rig.values[2:] == pytest.approx([1 / 3, 2 / 3, 1.0], abs=1e-3)
    assert rig.values[-1] == 1.0  # exactly: no group-alpha left after the fade
    assert rig.fade.state == "shown" and rig.fade.value == 1.0
    assert rig.timers.pending == {} and not rig.ticking


def test_ready_twice_is_one_fade():
    rig = Rig()
    rig.fade.ready()
    rig.fade.ready()
    assert rig.started == 1 and len(rig.ticker._callbacks) == 1
    assert len(rig.timers.pending) == 1


def test_the_ready_timeout_fades_in_anyway():
    rig = Rig()
    rig.timers.fire(READY_TIMEOUT_MS)
    assert rig.fade.state == "fading-in" and rig.started == 1
    rig.frames(5)
    assert rig.fade.state == "shown"


def test_a_fade_without_frames_is_finished_by_its_timeout():
    """The canvas never maps (no frames): the shell must not stay invisible."""
    rig = Rig()
    rig.fade.ready()
    rig.timers.fire(50 + FINISH_MARGIN_MS)
    assert rig.values[-1] == 1.0 and rig.fade.state == "shown"
    assert rig.timers.pending == {} and not rig.ticking


def test_fade_out_from_shown_reaches_zero_then_calls_back_once():
    rig = Rig()
    rig.fade.ready()
    rig.frames(5)
    rig.fade.fade_out(50, rig.on_done)
    assert rig.fade.state == "fading-out" and rig.done == 0
    out_start = len(rig.values)
    rig.frames(5)
    out = rig.values[out_start:]
    assert out == sorted(out, reverse=True) and out[-1] == 0.0
    assert rig.done == 1 and rig.fade.state == "done"
    assert rig.timers.pending == {} and not rig.ticking
    rig.frames(3)
    assert rig.done == 1


def test_fade_out_mid_fade_in_starts_from_the_current_value():
    rig = Rig()
    rig.fade.ready()
    rig.frames(2)  # the start, then 1/3
    now = rig.fade.value
    assert 0.3 < now < 0.4
    out_start = len(rig.values)
    rig.fade.fade_out(50, rig.on_done)
    rig.frames(6)
    out = rig.values[out_start:]
    assert max(out) <= now + 1e-9  # never a jump up
    assert out[-1] == 0.0 and rig.done == 1


def test_fade_out_while_waiting_is_done_at_once():
    """Nothing was visible yet: there is nothing to fade."""
    rig = Rig()
    rig.fade.fade_out(50, rig.on_done)
    assert rig.done == 1 and rig.fade.state == "done"
    assert rig.values == [0.0] and rig.timers.pending == {} and not rig.ticking


def test_fade_out_with_zero_ms_is_done_at_once_without_touching_the_opacity():
    rig = Rig()
    rig.fade.ready()
    rig.frames(5)
    seen = len(rig.values)
    rig.fade.fade_out(0, rig.on_done)
    assert rig.done == 1 and rig.fade.state == "done" and len(rig.values) == seen
    assert rig.timers.pending == {} and not rig.ticking


def test_fade_out_takes_its_own_duration():
    rig = Rig(50)
    rig.fade.ready()
    rig.frames(5)
    rig.fade.fade_out(300, rig.on_done)
    assert rig.timers.delays() == [300 + FINISH_MARGIN_MS]
    rig.frames(18)  # 300 ms is 18 frames: the first one starts the clock
    assert rig.done == 0
    rig.frames(1)
    assert rig.done == 1


def test_a_second_fade_out_keeps_the_running_one():
    rig = Rig()
    rig.fade.ready()
    rig.frames(5)
    rig.fade.fade_out(50, rig.on_done)
    other = []
    rig.fade.fade_out(50, lambda: other.append(1))
    rig.frames(6)
    assert rig.done == 1 and other == [] and len(rig.ticker._callbacks) == 0


def test_fade_out_after_done_calls_back_at_once():
    rig = Rig()
    rig.fade.fade_out(50, rig.on_done)
    rig.fade.fade_out(50, rig.on_done)
    assert rig.done == 2


def test_finish_completes_each_phase_at_once():
    rig = Rig()
    rig.fade.finish()  # waiting: shown at once (and the start is announced)
    assert rig.fade.state == "shown" and rig.values[-1] == 1.0 and rig.started == 1
    assert rig.timers.pending == {} and not rig.ticking
    rig.fade.fade_out(50, rig.on_done)
    rig.frames(2)
    rig.fade.finish()
    assert rig.fade.state == "done" and rig.values[-1] == 0.0 and rig.done == 1
    assert rig.timers.pending == {} and not rig.ticking


def test_cancel_stops_everything_without_callbacks():
    rig = Rig()
    rig.fade.ready()
    rig.frames(2)
    rig.fade.fade_out(50, rig.on_done)
    seen = len(rig.values)
    rig.fade.cancel()
    rig.frames(5)
    assert len(rig.values) == seen and rig.done == 0  # no opacity on windows being destroyed
    assert rig.fade.state == "done" and rig.timers.pending == {} and not rig.ticking
    rig.fade.cancel()  # twice is fine


def test_cancel_while_waiting_removes_the_ready_timeout():
    rig = Rig()
    rig.fade.cancel()
    assert rig.timers.pending == {} and rig.fade.state == "done"
    rig.fade.ready()
    assert rig.started == 0 and not rig.ticking


def test_a_failing_callback_never_breaks_the_fade(caplog):
    rig = Rig()

    def boom():
        raise RuntimeError("callback failed")

    rig.fade._on_start = boom
    with caplog.at_level(logging.ERROR, logger="shell.fade"):
        rig.fade.ready()
        rig.frames(5)
        assert rig.fade.state == "shown"
        rig.fade.fade_out(50, boom)
        rig.frames(5)
    assert rig.fade.state == "done" and rig.timers.pending == {} and not rig.ticking
    failed = [r for r in caplog.records if r.name == "shell.fade" and r.exc_info]
    assert [str(r.exc_info[1]) for r in failed] == ["callback failed", "callback failed"]
