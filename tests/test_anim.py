import pytest

from shell.anim import EASE_OUT, Tween, cubic_bezier, linear


class FakeClock:
    now = 0

    def get_frame_time(self):
        return self.now


class FakeWidget:
    def __init__(self):
        self.callbacks = {}
        self._next = 1
        self.clock = FakeClock()

    def add_tick_callback(self, cb):
        cid, self._next = self._next, self._next + 1
        self.callbacks[cid] = cb
        return cid

    def remove_tick_callback(self, cid):
        self.callbacks.pop(cid, None)

    def frame(self, advance_ms):
        self.clock.now += int(advance_ms * 1000)
        for cid, cb in list(self.callbacks.items()):
            if not cb(self, self.clock):
                self.callbacks.pop(cid, None)


def test_easing_endpoints_and_fast_out():
    assert EASE_OUT(0) == 0 and EASE_OUT(1) == 1
    assert EASE_OUT(0.5) == pytest.approx(0.946, abs=0.02)  # fast out of the frame
    xs = [i / 50 for i in range(51)]
    ys = [EASE_OUT(x) for x in xs]
    assert ys == sorted(ys)  # monotonic


def test_linear_bezier_is_identity():
    linear = cubic_bezier(0, 0, 1, 1)
    assert linear(0.3) == pytest.approx(0.3, abs=1e-3)


def test_linear_is_the_identity_on_0_to_1():
    assert [linear(t) for t in (0.0, 0.25, 0.5, 1.0)] == [0.0, 0.25, 0.5, 1.0]


def test_animate_reaches_target_and_stops():
    w, seen = FakeWidget(), []
    t = Tween(w, seen.append, duration_ms=280)
    t.animate_to(100)
    w.frame(0)  # first tick starts the clock
    w.frame(140)
    assert seen[-1] == pytest.approx(94.6, abs=2)
    w.frame(200)
    assert seen[-1] == 100 and t.value == 100
    assert not w.callbacks and not t.running


def test_retarget_midflight_starts_from_current_value():
    w = FakeWidget()
    t = Tween(w, lambda v: None, duration_ms=280)
    t.animate_to(100)
    w.frame(0)
    w.frame(100)
    mid = t.value
    t.animate_to(0)
    w.frame(0)  # first tick of the new tween: no jump
    assert t.value == pytest.approx(mid)
    w.frame(300)
    assert t.value == 0


def test_jump_cancels_and_sets():
    w, seen = FakeWidget(), []
    t = Tween(w, seen.append)
    t.animate_to(50)
    t.jump_to(7)
    assert t.value == 7 and seen[-1] == 7 and not w.callbacks


def test_delay_holds_value_then_animates():
    w = FakeWidget()
    t = Tween(w, lambda v: None, duration_ms=100, delay_ms=100)
    t.animate_to(1.0)
    w.frame(0)
    w.frame(50)
    assert t.value == 0  # still inside the delay
    w.frame(100)  # 150 ms in: 50 ms into the animation
    assert 0 < t.value < 1
    w.frame(100)
    assert t.value == 1


def test_animate_to_current_value_is_a_noop():
    w = FakeWidget()
    t = Tween(w, lambda v: None)
    t.animate_to(0)
    assert not w.callbacks


def test_zero_duration_snaps():
    w = FakeWidget()
    t = Tween(w, lambda v: None, duration_ms=0)
    t.animate_to(10)
    w.frame(0)
    assert t.value == 10 and not w.callbacks


def test_on_value_retarget_on_final_frame_keeps_running():
    w = FakeWidget()
    holder = []

    def on_value(v):
        if v == 100:
            holder[0].animate_to(0)

    t = Tween(w, on_value, duration_ms=100)
    holder.append(t)
    t.animate_to(100)
    w.frame(0)
    w.frame(200)  # final frame: on_value retargets
    assert len(w.callbacks) == 1 and t.running
    w.frame(0)  # first tick of the new tween
    w.frame(200)
    assert t.value == 0 and not w.callbacks and not t.running


def test_on_value_jump_then_animate_on_final_frame_registers_one_callback():
    w = FakeWidget()
    holder = []

    def on_value(v):
        if v == 100:
            holder[0].jump_to(7)
            holder[0].animate_to(50)

    t = Tween(w, on_value, duration_ms=100)
    holder.append(t)
    t.animate_to(100)
    w.frame(0)
    w.frame(200)
    assert len(w.callbacks) == 1 and t.running
    w.frame(0)
    w.frame(200)
    assert t.value == 50 and not w.callbacks and not t.running


def test_stop_freezes_without_a_last_value():
    """A fade stops its tween before its windows are destroyed: no on_value after stop."""
    w, seen = FakeWidget(), []
    t = Tween(w, seen.append, duration_ms=100)
    t.animate_to(1.0)
    w.frame(0)
    w.frame(50)
    seen_before, value = list(seen), t.value
    t.stop()
    assert not w.callbacks and not t.running and seen == seen_before and t.value == value
    w.frame(50)
    assert seen == seen_before
    t.stop()  # stopping a stopped tween is fine
    t.animate_to(0.0)  # and it can run again, from where it stopped
    w.frame(0)
    assert seen[-1] == pytest.approx(value)
