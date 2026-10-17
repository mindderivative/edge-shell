"""Easing and a frame-clock driven Tween. Pure: the widget is duck-typed."""

from __future__ import annotations

from collections.abc import Callable

Easing = Callable[[float], float]


def cubic_bezier(x1: float, y1: float, x2: float, y2: float) -> Easing:
    """CSS-style cubic-bezier easing, solved by bisection (x1, x2 within [0, 1])."""

    def axis(a: float, b: float, s: float) -> float:
        return 3 * (1 - s) ** 2 * s * a + 3 * (1 - s) * s**2 * b + s**3

    def ease(t: float) -> float:
        if t <= 0:
            return 0.0
        if t >= 1:
            return 1.0
        lo, hi = 0.0, 1.0
        for _ in range(40):
            mid = (lo + hi) / 2
            if axis(x1, x2, mid) < t:
                lo = mid
            else:
                hi = mid
        return axis(y1, y2, (lo + hi) / 2)

    return ease


EASE_OUT = cubic_bezier(0.2, 0.8, 0.2, 1.0)


def linear(t: float) -> float:
    """No easing (the shell fade: equal opacity steps per frame)."""
    return t


class Tween:
    def __init__(
        self,
        widget,
        on_value: Callable[[float], None],
        duration_ms: int = 280,
        delay_ms: int = 0,
        easing: Easing = EASE_OUT,
    ):
        self._widget = widget
        self._on_value = on_value
        self._duration_us = duration_ms * 1000
        self._delay_us = delay_ms * 1000
        self._easing = easing
        self.value = 0.0
        self._from = self._to = 0.0
        self._start_us: int | None = None
        self._tick_id = 0

    @property
    def running(self) -> bool:
        return bool(self._tick_id)

    def jump_to(self, target: float) -> None:
        if self._tick_id:
            self._widget.remove_tick_callback(self._tick_id)
            self._tick_id = 0
        self.value = self._from = self._to = float(target)
        self._on_value(self.value)

    def stop(self) -> None:
        """Stop where it is, without a last on_value (its widget may be about to go)."""
        if self._tick_id:
            self._widget.remove_tick_callback(self._tick_id)
            self._tick_id = 0
        self._from = self._to = self.value

    def animate_to(self, target: float) -> None:
        target = float(target)
        if self._tick_id:
            if target == self._to:
                return
        elif abs(target - self.value) < 1e-9:
            return
        # Retargeting mid-flight starts from the current value, so there is never a jump.
        # The delay restarts on every retarget; use jump_to or another tween to reverse instantly.
        self._from, self._to, self._start_us = self.value, target, None
        if not self._tick_id:
            self._tick_id = self._widget.add_tick_callback(self._tick)

    def _tick(self, _widget, clock) -> bool:
        now = clock.get_frame_time()
        if self._start_us is None:
            self._start_us = now
        elapsed = now - self._start_us - self._delay_us
        if self._duration_us <= 0:
            t = 1.0 if elapsed >= 0 else 0.0
        else:
            t = 0.0 if elapsed <= 0 else min(1.0, elapsed / self._duration_us)
        self.value = self._from + (self._to - self._from) * self._easing(t)
        done = t >= 1.0
        if done:
            # Clear before on_value so a re-entrant animate_to/jump_to registers a
            # fresh callback that survives this one being removed (return False).
            self._tick_id = 0
        self._on_value(self.value)
        return not done
