"""The fade of one monitor's Edge Shell windows (spec 21): built transparent, faded in once the
monitor is ready, faded out before the windows go. One Tween on one frame clock sets the
opacity of every window of the monitor in the same frame. Pure: the frame-clock widget, the
opacity setter and the timers are given (shell.monitors passes the canvas window, a setter
over all its windows and GLib's timeout_add / source_remove)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Literal

from shell.anim import Tween, linear

log = logging.getLogger(__name__)

# Fade in at the latest this long after the build, ready or not: a build that never reports
# ready must not leave the monitor invisible. Above shell.monitors.RAISE_DELAY_MS (500 ms, the
# re-raise the monitor normally waits for), so it only fires when something is stuck.
READY_TIMEOUT_MS = 1000
# A fade still running this long after its duration is finished at once: its Tween runs only
# while the canvas gets frames, and a canvas that is never mapped gets none.
FINISH_MARGIN_MS = 300

State = Literal["waiting", "fading-in", "shown", "fading-out", "done"]


class Fade:
    """waiting -> fading-in -> shown -> fading-out -> done (`state`).

    `ticker` is the widget whose frame clock drives the Tween (add_tick_callback /
    remove_tick_callback), `set_opacity(v)` sets every window. With `duration_ms` 0 the fade is
    "shown" from the start and never calls set_opacity or arms a timer: the windows behave as
    without a fade. `on_start()` is called when the fade-in starts (the monitor's input and a
    crossfade's old shell follow it)."""

    def __init__(
        self,
        ticker,
        set_opacity: Callable[[float], None],
        duration_ms: int,
        timeout_add: Callable[[int, Callable[[], bool]], int],
        source_remove: Callable[[int], object],
        on_start: Callable[[], None] | None = None,
    ):
        self._ticker = ticker
        self._set_opacity = set_opacity
        self._timeout_add = timeout_add
        self._source_remove = source_remove
        self._on_start = on_start
        self._on_done: Callable[[], None] | None = None
        self._timer = 0
        self.duration_ms = max(0, duration_ms)
        self._tween = Tween(ticker, self._on_value, self.duration_ms, easing=linear)
        self.value = 1.0  # the opacity the windows have (what a window added now gets)
        if self.duration_ms == 0:
            self.state: State = "shown"
            return
        self.state = "waiting"
        self._tween.jump_to(0.0)
        self._arm(READY_TIMEOUT_MS, self._ready_timeout)

    # ---- phases -----------------------------------------------------------------------
    def ready(self) -> None:
        """The monitor is ready: fade in (once; only while waiting)."""
        if self.state != "waiting":
            return
        self.state = "fading-in"
        self._tween.animate_to(1.0)
        self._arm(self.duration_ms + FINISH_MARGIN_MS, self._finish_timeout)
        self._call(self._on_start)

    def fade_out(self, duration_ms: int, on_done: Callable[[], None]) -> None:
        """Fade out over `duration_ms` from the current opacity (no jump), then on_done().
        Done at once when nothing is visible yet (waiting), with 0 ms (the opacity is not
        touched) or when already done. A second call while fading out is ignored: the running
        fade keeps its callback."""
        if self.state == "fading-out":
            return
        if self.state in ("waiting", "done") or duration_ms <= 0:
            self._stop()
            self.state = "done"
            self._call(on_done)
            return
        self._tween.stop()
        self.state = "fading-out"
        self._on_done = on_done
        self._tween = Tween(self._ticker, self._on_value, duration_ms, easing=linear)
        self._tween.jump_to(self.value)
        self._tween.animate_to(0.0)
        if self.state == "fading-out":  # not settled by the jump (a value already at 0)
            self._arm(duration_ms + FINISH_MARGIN_MS, self._finish_timeout)

    def finish(self) -> None:
        """Complete the current phase now: waiting or fading in -> shown, fading out -> done
        (and its on_done). Shown and done stay as they are."""
        if self.state == "waiting":
            self.ready()
        if self.state == "fading-in":
            self._tween.jump_to(1.0)
        elif self.state == "fading-out":
            self._tween.jump_to(0.0)

    def cancel(self) -> None:
        """Stop without another opacity or callback (the windows are being destroyed now)."""
        self._stop()
        self._on_done = None
        self.state = "done"

    # ---- internals --------------------------------------------------------------------
    def _on_value(self, value: float) -> None:
        self.value = value
        self._set_opacity(value)
        if self._tween.running:
            return
        if self.state == "fading-in" and value >= 1.0:
            self.state = "shown"
            self._disarm()
        elif self.state == "fading-out" and value <= 0.0:
            self.state = "done"
            self._disarm()
            done, self._on_done = self._on_done, None
            self._call(done)

    def _stop(self) -> None:
        self._tween.stop()
        self._disarm()

    def _arm(self, ms: int, fn: Callable[[], bool]) -> None:
        self._disarm()
        self._timer = self._timeout_add(ms, fn)

    def _disarm(self) -> None:
        if self._timer:
            self._source_remove(self._timer)
            self._timer = 0

    def _ready_timeout(self) -> bool:
        self._timer = 0  # fired: GLib removes it when this returns False
        log.debug("not ready after %d ms: fading in anyway", READY_TIMEOUT_MS)
        self.ready()
        return False

    def _finish_timeout(self) -> bool:
        self._timer = 0
        log.warning("a fade did not finish in time (no frames?): finishing it now")
        self.finish()
        return False

    @staticmethod
    def _call(fn: Callable[[], None] | None) -> None:
        """Run a callback; it runs inside a frame-clock tick or a GLib timer, so an exception
        is logged, never raised into the main loop (the fade's own state is already final)."""
        if fn is None:
            return
        try:
            fn()
        except Exception:
            log.exception("a fade callback failed")
