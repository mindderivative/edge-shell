# Shell Fade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A monitor's Edge Shell fades in when it is turned on, starts or is fully rebuilt (built invisible, faded in once it is complete, so it never blinks or grows into place), fades out when it is turned off or the shell quits, and a full rebuild crossfades from the old shell to the new one; `[theme] fade_ms` (default 50 ms, 0 = off) sets the time.

**Architecture:** A pure state machine, `shell/fade.py` (`Fade`: waiting -> fading-in -> shown -> fading-out -> done), drives one `shell.anim.Tween` on the canvas window's frame clock; its single callback sets `Gtk.Widget.set_opacity` on every window of the monitor in the same frame. `MonitorShell` builds every window at opacity 0 with its panels' input off, reports "ready" when the first re-raise has run and no "content" measurement is pending, and gains `detach`, `fade_out` and `finish_fade`. `EdgeShellApp` keeps leaving shells in `_leaving` (out of `shells`), holds the old shell during a rebuild until the new one starts fading in (crossfade), fades out on turn-off and on SIGINT/SIGTERM (GLib's Unix signal source), and closes at once whatever sits on an unplugged monitor. With `fade_ms = 0` nothing changes: no opacity is ever set, nothing waits.

**Tech Stack:** Python 3.14 (>=3.12), PyGObject 3.50.0 (`<3.52`), GTK 3.24.52 (`Gtk.Widget.set_opacity`, `add_tick_callback`, frame clock), GLib 2.90.1 (`GLibUnix.signal_add`, `GLib.timeout_add`, `GLib.idle_add`), gtk-layer-shell via Fabric 0.0.2 (`WaylandWindow`), KDE Plasma 6 / KWin on Wayland, pydantic 2, pytest, ruff 0.17.0.

**Spec:** No separate design doc: Phil's request and the decisions taken with him (both verbatim below) are the spec, with the decisions in this plan; Task 7 records the result as section 21 of `docs/superpowers/specs/2026-10-11-edge-shell-design.md`. Background the executor needs: that spec's sections 5 (surfaces per monitor), 6 (live reload table) and 15 (the delayed re-raise, Gate B item 11), and `docs/superpowers/specs/2026-10-14-panel-widget-model-design.md` section 7 (the settings window's tabs and the slider rule, `settings.form.SLIDER_MAX_SPAN`).

**Phil's request (verbatim):** "I was wondering if we could make the shell fade-in when enabled or requires a full redraw. Have it draw off screen or something, then set the overall opacity to 0 and have it fade-in over 50ms instead of having it blink or just appear. It seems right now on enable it blinks in then expands to the edges. On disable have it fade out instead of just disappear instantly. This is a quality of life effect and would be obvious that it is intentional so any random blinking would be an error of some kind."

**Decided with Phil:** (1) a theme setting `[theme] fade_ms = 50`, 0 turns the fade off, per-monitor override through the existing `ThemeOverride`, a slider in the settings window (span within the slider rule); (2) on a full rebuild of a monitor's shell, CROSSFADE: the new shell is built at opacity 0 while the old one stays up, then both are cross-faded over `fade_ms` (new 0 -> 1, old 1 -> 0) and the old one is destroyed when done; (3) built in this branch (`feat/input-styles`). The design sketch approved in chat: every window of a `MonitorShell` built at opacity 0; shown and faded in when the canvas has drawn and the panels have their final sizes; a timeout fades in anyway; fade-out on disable and on a normal quit with a bounded wait; no fade work at `fade_ms == 0`.

**Date:** 2026-10-16. **Size:** 8 tasks: 6 with code and tests (1-6), Task 7 the docs and the gate checklist (Phil runs the gate), Task 8 recording the gate results. Riskiest: Task 3 (the readiness rule decides when every monitor appears), Task 5 (two shells of one monitor alive at once), Task 4 (the quit path replaces Ctrl+C's instant death).

## How the blink arises today (read from the code; what KWin shows is Phil's)

Turning a monitor on is a `rebuild-monitor` change (`shell/config/diff.py`: the mode moved between "has windows" and "has none"): `EdgeShellApp._reload` closes nothing, `sync_monitors` opens a `MonitorShell`, and `MonitorShell._build` (`shell/monitors.py`) creates, in one main-loop callback: the `ShapeCanvas` (`show_all` in its constructor: mapped, drawing the frame, the screen corners and every panel body), the four `FrameEdge` strips (bottom layer, exclusive zones: KWin re-arranges maximized windows to make room), then every panel window (`EdgePanel`/`CornerPanel`, `show_all` in the constructor, depth jumped to its state). Each surface gets its first configure and first frame separately, so for a frame or more the canvas's frame and panel bodies are on screen without the panels' content and handles. Then:

1. **The first idle:** a `length = "content"` panel is measured (`_measure`) and, if its natural length differs from the default, destroyed and rebuilt at the measured length: the panel body on the canvas jumps to a new length, a new window maps.
2. **500 ms (`RAISE_DELAY_MS`):** `_raise_panels` hides and re-shows every panel window (`EdgePanel.raise_to_top`: `hide()` + `show_all()`) so KWin stacks them above the canvas (needed: spec 15, Gate B item 11, "All hidden, content and handles" without it). An unmap and a re-map: the content and handles vanish for a frame and come back: a blink. A panel built after startup (the content rebuild) gets its own re-raise 500 ms after it was built.
3. **2000 ms (`RAISE_FALLBACK_MS`):** the same re-map again, a safety net for a slow compositor.
4. **The strips' zones:** maximized windows shrink to the frame when the strips map ("expands to the edges" may be this, or the content rebuild of 1.).

A full rebuild (a thickness change) is `_close_shell` (every window destroyed) then a new `MonitorShell` in the same callback: the old frame is gone at once and the new one appears piece by piece as above. Turning a monitor off destroys every window at once. Ctrl+C is `SIG_DFL`: the process dies and the compositor drops the surfaces.

**What the fade covers:** items 1-2 happen while the new windows are at opacity 0 (the fade waits for both), the first configures and first frames too. Item 3 is after the fade (open question 2). Item 4 is the compositor's re-arrangement of other windows; it cannot be faded (open question 6 offers moving it to the fade's start). **What only Phil can see:** whether any of it still blinks (gate items 2-5).

## Decisions (each *default pending Phil* unless marked decided; alternatives and their cost)

1. **`[theme] fade_ms`: an int 0-500, default 50, 0 = no fade.** *Decided (key, default, 0, per-monitor, slider); the bound is this plan's.* `Theme.fade_ms: Annotated[int, Field(ge=0, le=500)] = 50` and `fade_ms = 50` in `config.default.toml`. **Bound rule:** the settings window's slider rule (`uses_slider`: both bounds and `maximum - minimum <= SLIDER_MAX_SPAN`, 500) takes 0-500 (exactly the span), so the row is a slider with its spin button (0-1000 would keep a spin button); 500 ms is already ten times the default and a fade longer than that reads as lag. A model default (not only the defaults file) keeps every test config valid (`tests/conftest.py` has no `fade_ms`). Per monitor: `[monitors.X.theme] fade_ms`; `ThemeOverride` is generated from `Theme` (`_override_of`), so nothing is added there; a bad override fails at load with `monitors.X.theme: fade_ms: ...` (`Config._check_overrides`). **A change is a restyle**, never a rebuild: `fade_ms` is not in `diff._STRUCTURAL`, so an old/new pair that differs only there is `Change("restyle")`, applied in place (it redraws, nothing fades); the app reads `fade_ms` from the config in effect at each fade (`EdgeShellApp._fade_ms`), so a change applies from the next fade on. **Settings:** label "Fade", hint "ms; 0 turns the fade off", on the General tab (the default tab for a theme key: `THEME_TAB_OF` names none for it), a slider by the rule. `--stats` never fades (`_fade_ms` returns 0 while measuring), so its numbers stay comparable; `shell.canvas.simulate` does not use `MonitorShell` and is untouched.
2. **The mechanism: `Gtk.Widget.set_opacity` on every toplevel of the monitor.** *Default pending Phil's gate (items 2-3).* GTK 3.24 (`gtk/gtkwidget.c`: `gtk_widget_update_alpha`, `gtk_widget_draw_internal`) paints a toplevel's opacity itself when the window's visual is the screen's RGBA visual: it draws the window into a group and paints the group with that alpha; only for a non-RGBA toplevel does it call `gdk_window_set_opacity` (a no-op on Wayland). On GDK's Wayland backend the screen has one visual, 32-bit, both the system and the RGBA visual, and Fabric's `WaylandWindow` keeps it: so the whole surface (the canvas's cairo drawing, panel content, handles) is multiplied, in the client, and the compositor composites a translucent ARGB buffer as it already does for these windows. *Not verifiable headless:* creating a window to measure it would open one; it is gate item 2. **Alternatives:** (A) draw the fade into the canvas only (`CanvasPainter` alpha): the panels' own windows (content, handles) would not fade, and the panels would need a second mechanism; (B) CSS `opacity` on each window's content: the canvas (a `Gtk.DrawingArea` drawn with cairo) would need (A) anyway, and a CSS change restyles every widget of the window; (C) a compositor-side alpha (`wp_alpha_modifier_v1`): GTK 3 has no binding. **Contingency (if gate item 2 shows no fade, the windows appearing at full opacity after the wait):** set the opacity on each window's child instead (`window.get_child().set_opacity(v)`: a non-toplevel widget always gets the group alpha in GTK 3, provided it has no native window), one line in `MonitorShell._apply_opacity` plus one test; nothing else depends on which widget gets it.
3. **Built at opacity 0, mapped as before: not hidden, not drawn off screen.** *Default pending Phil.* The windows are created, shown and configured as today, at opacity 0 (set before the main loop draws their first frame: `MonitorShell._track` applies the fade's current value to every window as it is added, and the canvas gets 0 from the `Fade` constructor, all before the build callback returns). So every first configure, first frame, content rebuild and re-raise happens invisibly. *Rejected:* building the windows hidden and showing them at the start of the fade (the first map, first configure and stacking would then happen at fade start: the blink moves, it does not go; and the re-raise workaround depends on a mapped canvas); drawing off screen (a layer surface has no off-screen state; an offscreen GTK window is not the surface KWin shows).
4. **Ready = the first re-raise has run and no "content" measurement is pending; a 1000 ms timeout fades in anyway.** *Default pending Phil (open question 1).* `MonitorShell` counts its pending first re-raises (`_raises_pending`: the 500 ms one of the build and the one of every panel built later; the 2000 ms fallback is not waited for) and checks after each re-raise, after each measurement and once after the build returns to the main loop (an idle: never inside the constructor, so the app has stored the shell before any callback). So a monitor appears about 0.5 s after it is turned on, fully built. `READY_TIMEOUT_MS = 1000` (`shell/fade.py`): ready or not, it fades in then, so a stuck build never leaves a monitor invisible; above the 500 ms re-raise, so it only fires when something is stuck (the sketch said about 300 ms: that would start most fades before the re-raise and bring its blink back). `FINISH_MARGIN_MS = 300`: a fade still running 300 ms after its duration (its Tween runs only while the canvas gets frames; a canvas that is never mapped gets none) is finished at once (opacity 1, or 0 and closed). `EDGE_SHELL_RAISE_MS=0` (no re-raise) fades in at the first idle. *Alternative:* start the fade at the first frame and accept the 0.5 s re-raise blink (the request calls any blink an error).
5. **One Tween per monitor, linear, on the canvas's frame clock.** *Default pending Phil.* `Fade` owns one `Tween(canvas, on_value, fade_ms, easing=linear)`: one tick callback per frame sets every window of the monitor (`MonitorShell._set_opacity`, a loop over `self.windows`), so no window is ever a frame ahead of another. The first tick only starts the clock (opacity 0 on the first frame drawn), and the last value is exactly 1.0 (GTK stops grouping at 255). A 50 ms fade is 3 frames at 60 Hz (values 1/3, 2/3, 1), visibly a fade and short; 300 ms (18 frames) makes it easy to judge (gate). Linear: equal steps per frame; an ease-out would spend two of the three frames near 1. A failing `set_opacity` on one window (being destroyed) is logged at debug and never stops the others.
6. **Input follows visibility.** *Default pending Phil.* A monitor's panels take no input while it is invisible (built with `EdgePanel.set_input_enabled(False)`: an empty input region, kept across every re-allocate and depth frame, a hover peek dropped) and take it from the start of the fade-in; a fading-out shell's panels take none from the start of its fade. The canvas and strips are click-through already. So a click during the 0.5 s wait goes to the old shell (still visible) or the desktop, never to an invisible panel.
7. **Fade out: turned off -> fade, then destroy; unplugged -> destroy now.** *Default pending Phil.* `MonitorShell.fade_out(ms, on_done)` detaches the shell (no re-layout, measurement or re-raise: a re-map would blink; the monitor's geometry no longer watched; the strips destroyed at once, so the reserved zone goes at the start), turns its panels' input off, fades from the opacity it has (never a jump), then closes and calls `on_done(shell)`. With 0 ms, or a shell still waiting (never visible), it closes at once. The app fades a shell out when its monitor is still connected (`sync_monitors`: `connected[name] is shell.monitor`; a reload's turn-off) and closes it at once when the monitor is gone or replaced by a new Gdk monitor (a hot-plug: no fade on a dead output, no frames will come).
8. **Crossfade on a full rebuild.** *Decided (crossfade); the details are this plan's.* `_reload` holds the old shell (`_leave_shell`: out of `shells`, into `_leaving`, `detach()`ed: its strips go, so the new strips reserve the edges alone and maximized windows re-arrange once), then `sync_monitors` builds the new one at opacity 0 above it (later-mapped surfaces of a layer stack above earlier ones; the old canvas is below everything new). The old shell stays fully visible and keeps its input until the new one is ready; when the new one starts its fade-in (`on_fade_in` -> `EdgeShellApp._faded_in`) the old one starts `fade_out` over the same `fade_ms`: new 0 -> 1, old 1 -> 0, and the old one is destroyed at the end. Two Tweens on two canvases: both canvases are on the same output, so KWin's frame callbacks come at the same vblank and both fades step in the same frames (the end-to-end test drives both from one clock). *Known effect:* where both shells draw the same opaque frame, two linear half-transparent layers cover 1 - 0.5 x 0.5 = 75 % at the midpoint, a slight dim for one frame at 50 ms, visible at 300 ms (gate item 5; open question 3 offers holding the old one at 1). The old shell's CSS-styled content (text, fonts) takes the new theme at once (the app has one stylesheet per monitor scope); its frame is drawn by its own canvas and keeps the old look until it is gone.
9. **No stacking: at most one leaving shell per monitor; a reload during a fade finishes it.** *Default pending Phil.* `_leave_shell` and `_fade_away` first `_retire` an older leaving shell of that monitor (closed at once); a shell replaced in the middle of its fade-in is finished (`finish_fade`: fully shown, then held); a shell replaced or turned off before it was ever visible (`fade_state == "waiting"`) is simply closed, and the shell it was replacing stays held (a rebuild) or fades out (a turn-off). A held shell whose successor fails to build fades out on its own (`_release_held` in a `finally`), so no shell is ever held forever. A hot-plug that removes or replaces a monitor closes its leaving shell at once. Tween callbacks are never leaked: `close()` cancels the fade (`Fade.cancel`: the tick callback and its timer removed, no further opacity) before the canvas is destroyed.
10. **Quit: SIGINT and SIGTERM fade every monitor out, bounded.** *Default pending Phil (open question 4).* `run()` keeps `signal.signal(SIGINT, SIG_DFL)` (so PyGObject's `Gio.Application.run` installs no SIGINT fallback of its own: it only does when Python's handler is `default_int_handler`; that fallback would quit without a fade) and adds `GLibUnix.signal_add(PRIORITY_HIGH, SIGINT/SIGTERM, ...)` (GLib 2.80+; the older `GLib.unix_signal_add` as fallback; verified headless here: both signals arrive in the main loop with the signal number). The handler fades every shell out and quits when the last one is gone, at the latest the longest `fade_ms` + `QUIT_MARGIN_MS` (250) later; a second signal quits at once; reloads and hot-plug syncs are ignored while quitting. Exit status: 128 + the signal (130 for Ctrl+C, 143 for SIGTERM: what a shell reports today). Side effect: `--stats` interrupted by Ctrl+C now prints its report (the run returns instead of dying).
11. **Not faded.** A restyle (`apply` in place), panel adds, removes and rebuilds, state and handle changes, a resolution change (`_relayout` re-lays out in place: there is no full rebuild on a geometry change), and the failure rebuilds (an in-place apply that raised, `_relayout_failed`: the broken shell is closed at once as before; its replacement still fades in). The panels' own open/close Tweens animate depth and the content's opacity (`EdgePanel._fade`, a child widget), never the window's opacity, so they compose with the shell fade without interference.
12. **Bookkeeping unchanged elsewhere.** Leaving shells are not in `shells`: `css()`, `_report_layout`, `_forget_reports` (called when a shell leaves, as before), the monitor-name check, the "Panels adjusted" / "Panel not shown" notifications and `_relayout_failed`'s identity check only see live shells. Every window stays registered with Fabric's `Application` until the shell that owns it closes (`_release` unregisters, then destroys), so two shells of one monitor are two sets of registered windows for the length of a crossfade.
13. **Performance.** A fade costs, per frame, a full redraw of each window (`set_opacity` queues one) plus GTK's group: the canvas's full draw measured at 1.6 ms without effects (spec 16, Gate B) and about 15 ms with border and shadow at 1920x1080 (spec 19, Gate B), so with effects on a 50 ms fade may drop one of its three frames. Nothing is drawn after the fade (opacity 1.0 exactly ends the grouping). Blending translucent layer surfaces is the compositor's work, as it already is for these ARGB windows.

## Out of scope / found on the way

- Building the strips at the start of the fade-in instead of with the canvas (the reserved zone and the frame would then appear together): open question 6.
- **Pre-existing, not fixed here:** `MonitorShell._build` builds the four strips in one list comprehension before tracking any; if the 2nd to 4th `FrameEdge` constructor raises, the strips already built are never tracked, so `close()` cannot destroy them (an invisible strip keeps reserving its zone). Found while writing Task 3's failure test (which therefore makes the first strip fail). A follow-up: track each strip as it is built (about 3 lines and a test); open question 5.
- Float panels, Plasma panel hide/show, HiDPI (unchanged).

## Prerequisites

- Branch `feat/input-styles` at `7527b58` (input styles done; Phil decided to fold this work into this branch), in the worktree `/home/phil/Projects/pyDev/projects/myShell/.claude/worktrees/feat-edge-shell-core`.
- Baseline before Task 1: `scripts/py -m pytest -q` prints `2724 passed` (0 skipped; warnings are normal); `scripts/py -m ruff check .` prints `All checks passed!`; `scripts/py -m ruff format --check .` prints `157 files already formatted`. With GTK blocked (below): `1936 passed, 37 skipped`.
- GLib's Unix signal source is importable: `scripts/py -c 'import gi; gi.require_version("GLibUnix", "2.0"); from gi.repository import GLibUnix; print(GLibUnix.signal_add)'` prints a function. If it fails, the code falls back to `GLib.unix_signal_add`; check `scripts/py -c 'from gi.repository import GLib; print(GLib.unix_signal_add)'` instead, and STOP and report if neither exists. Nobody installs packages.
- **How the code steps are written.** Every code step is a unified diff made from the measured prototype (each task applied in order with `git apply` on a fresh copy of `7527b58`, `ruff format` run, the suite run after each; the totals below are those runs). Save a step's diff block to a file (for example `/tmp/claude-1000/step.diff`) and apply it from the worktree root with `git apply --whitespace=nowarn /tmp/claude-1000/step.diff`; a new file appears in full (`new file mode`). Apply a task's test diff (Step 1) before its implementation diff (Step 3). If a diff does not apply, STOP and report: do not hand-merge silently. Stage files by name, never `git add -A` or `git add .`.

## Global Constraints

- Python only through `scripts/py` (shared venv `/home/phil/Projects/pyDev/pyEnvs/global-base`). **PyGObject must stay `<3.52`** (Fabric 0.0.2 breaks on 3.52+).
- **Pure modules import no GTK / `gi`:** the new `shell/fade.py` (imports only `shell.anim`), and as before `shell/anim.py`, `shell/plan.py`, `shell/config/*`, `settings/form.py`. Its tests (`tests/test_fade.py`) run on the CI runner (no `gi`).
- **`fade_ms = 0` is today's behaviour exactly:** no `set_opacity` call, no input change, no extra timer or idle, a rebuild closes then opens, a turn-off closes at once (pinned by tests in Tasks 3, 4 and 5). The only differences at 0: Ctrl+C exits through GLib (status 130, the windows destroyed by the shell instead of by the process's death).
- **Never a blink of our own making:** no `hide()`/`show()` beyond the existing re-raise, no window mapped at full opacity before the fade, a leaving shell never re-mapped (`detach`).
- **Every GLib or frame-clock callback returns `False`/`SOURCE_REMOVE` (one-shot) or `SOURCE_CONTINUE` (the signal handler), and never raises into the main loop** (`Fade._call`, `MonitorShell._call_done`, `_faded_out`, `_apply_opacity` log instead).
- **Tests.** CI installs only pycairo, pydantic, pytest, ruff and tomlkit: tests importing `gi` or Fabric start with `pytest.importorskip("gi")` / `pytest.importorskip("fabric")` at module level. Tests **never create or show a window, never call the compositor, never install a real signal handler or spawn a process**: the windows are the repo's fakes (`tests/test_monitor_shell.py` `FakeWindow`, `FakeCanvas`, `FakeMonitor`; `tests/test_app_sync.py` `FakeShell`), time is a fake frame clock (`shell.canvas.simulate.FakeClock` / `FakeTicker`), timers and idles are recorded fakes (`tests/test_fade.py` `FakeTimers`, `tests/test_monitor_fade.py` `Loop`), and `unix_signal_add` is replaced in the one test that installs handlers.
- **Lint.** `ruff` 0.17.0, line length 100, rules E, F, I, UP, B; excludes `docs/` and `*.md`.
- **VERIFY** (before every commit): `scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q`. The suite must be green at the end of EVERY task (0 failed, 0 skipped) with exactly the total in the File Structure table. At the end of Task 6 also run it with GTK blocked, as the CI runner has no `gi`: `mkdir -p /tmp/claude-1000/nogi/gi`, write `raise ModuleNotFoundError("No module named gi (blocked)", name="gi")` into `/tmp/claude-1000/nogi/gi/__init__.py`, then `PYTHONPATH=/tmp/claude-1000/nogi scripts/py -m pytest -q` prints `1961 passed, 38 skipped` (only skips, no error).
- **Git.** Plain separate git commands run from the worktree (no `cd … && git`, no command substitution around git). Stage files by name. **Never push.** Every commit message ends with a second `-m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`.
- **Live runs.** Phil is the only visual tester, on `HDMI-A-1` only. **Never touch `DP-1`** (it holds the Plasma panel; never set it to `edge` or `both`, in a file or in the window; never click its checkboxes). Subagents executing tasks never launch the shell or the settings window (`main.py` without `--list-outputs`, including `--settings`), never open a window or a dialog, never send a signal to a running shell; headless commands are fine (`pytest`, `scripts/py -c` checks). The gate (Task 7's checklist) is run by Phil.

## Review Focus

The five failure modes most likely to bite Phil that the request implies but a happy-path test would not catch, each pinned by tests in the owning task (Task 6 holds the most):

1. **A reload arriving during a fade** (two quick thickness changes; a turn-off while the rebuilt shell is still invisible): expected no stacked fades, no shell left behind or held forever, the visible shell never vanishing without a fade. Pinned by `test_a_second_rebuild_mid_crossfade_never_stacks_fades`, `test_a_rebuild_while_the_new_shell_is_still_invisible_keeps_the_held_one`, `test_turning_a_monitor_off_while_its_new_shell_waits_fades_the_held_one` (Task 6) and `test_a_held_shell_whose_successor_fails_to_build_fades_out` (Task 5); live by gate item 7.
2. **A build that never reports ready, or a canvas that gets no frames**, leaving the monitor invisible: expected it fades in after `READY_TIMEOUT_MS` anyway and a fade without frames is finished. Pinned by `test_the_ready_timeout_fades_in_when_nothing_reports_ready`, `test_a_fade_without_frames_is_finished_by_its_timeout`, `test_a_build_that_fails_after_the_canvas_leaves_no_fade_behind` (Task 3) and `test_a_fade_without_frames_is_finished_by_its_timeout` in `tests/test_fade.py` (Task 2).
3. **Ctrl+C with mixed fades** (one monitor at `fade_ms = 0`, another at 50) or a fade that never finishes: expected the quit waits for the last fade and never longer than the longest fade + 250 ms; a second Ctrl+C quits at once. Pinned by `test_a_monitor_without_a_fade_never_cuts_the_others_fade_short`, `test_the_quit_waits_at_most_the_fade_plus_the_margin`, `test_a_second_quit_signal_quits_at_once` (Task 4); live by gate item 9.
4. **A monitor unplugged or replugged during a fade:** expected its shells (live, fading out or held) closed at once, no fade on a dead output, the new monitor's shell opening normally. Pinned by `test_an_unplugged_or_replaced_monitor_is_closed_at_once_without_a_fade` (Task 4), `test_unplugging_a_monitor_mid_fade_closes_its_leaving_shell_at_once` and `test_a_replaced_monitor_drops_the_held_shell_and_the_new_one_opens` (Task 6).
5. **`fade_ms = 0` changing anything** (Phil's off switch must be exactly the old shell): expected no opacity, no input change, no extra timer, a rebuild closing and opening at once. Pinned by `test_without_a_fade_no_window_gets_an_opacity_and_nothing_waits` (Task 3), `test_fade_out_with_zero_ms_closes_at_once_as_before`, `test_with_fade_0_a_disabled_monitor_closes_at_once_as_before`, `test_without_any_fade_a_quit_signal_quits_at_once` (Task 4), `test_reload_rebuild_monitor_closes_and_reopens_without_apply` (Task 5, now with `fade_ms = 0`) and `test_zero_ms_is_shown_from_the_start_and_does_no_fade_work` (Task 2); live by gate item 9.

## File Structure

```
shell/fade.py                   # CREATE (T2): READY_TIMEOUT_MS, FINISH_MARGIN_MS, State, Fade (pure)
shell/anim.py                   # MODIFY (T2): linear, Tween.stop
shell/config/models.py          # MODIFY (T1): Theme.fade_ms
config.default.toml             # MODIFY (T1): fade_ms = 50
settings/form.py                # MODIFY (T1): HINTS / LABELS for fade_ms, the slider comment
shell/edge_panel.py             # MODIFY (T3): EdgePanel._input_off, set_input_enabled
shell/monitors.py               # MODIFY: fade-in wiring (T3); fade_state, fading_out, detach,
                                #   fade_out (T4); finish_fade (T6)
shell/plan.py                   # MODIFY (T4): has_windows
shell/app.py                    # MODIFY: _leaving, _close_shell(fade), _fade_away, _retire, _gone,
                                #   _fade_ms, quit signals (T4); _leave_shell, _faded_in,
                                #   _release_held (T5); the waiting / hot-plug rules (T6)
README.md, docs/superpowers/specs/2026-10-11-edge-shell-design.md   # MODIFY (T7, T8)
tests/test_fade.py              # CREATE (T2)
tests/test_monitor_fade.py      # CREATE (T3; T4, T5, T6 add tests)
tests/test_config_models.py, tests/test_config_loader.py, tests/test_config_diff.py,
tests/test_settings_form.py, tests/test_settings_tabs.py, tests/test_anim.py,
tests/test_monitor_shell.py, tests/test_edge_panel_handle.py, tests/test_corner_panel.py,
tests/test_plan.py, tests/test_app_sync.py   # MODIFY
```

| After task | Suite (`scripts/py -m pytest -q`) | Delta | Tests added (modified) |
|---|---|---|---|
| baseline `7527b58` | 2724 passed | | |
| 1 config key | 2729 passed | +5 | models +2, loader +1, diff +1, form +1 (form 1, tabs 1 modified) |
| 2 Fade | 2748 passed | +19 | fade +17 (new file), anim +2 |
| 3 fade-in | 2768 passed | +20 | monitor_fade +16 (new file), edge_panel_handle +3, corner_panel +1 (monitor_shell helpers) |
| 4 fade-out, quit | 2789 passed | +21 | monitor_fade +8, app_sync +12 (1 modified), plan +1 (monitor_shell helper) |
| 5 crossfade | 2794 passed | +5 | app_sync +4 (1 modified), monitor_fade +1 |
| 6 edge cases | 2801 passed | +7 | app_sync +6, monitor_fade +1 |
| 7 docs | 2801 passed | 0 | |
| 6 with GTK blocked | 1961 passed, 38 skipped | | baseline 1936 passed, 37 skipped (+25: T1, T2, plan; `test_monitor_fade.py` skips) |

---

### Task 1: The `fade_ms` theme key (model, defaults file, reload kind, settings row)

**Files:**
- Modify: `shell/config/models.py` (`Theme`, after `duration_ms`), `config.default.toml` (`[theme]`, after `duration_ms`), `settings/form.py` (`HINTS`, `LABELS`, the comment above `SLIDER_MAX_SPAN`)
- Test: `tests/test_config_models.py`, `tests/test_config_loader.py`, `tests/test_config_diff.py`, `tests/test_settings_form.py`, `tests/test_settings_tabs.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `Theme.fade_ms: int` (0-500, default 50; `Config.theme_for(name).fade_ms` resolves a monitor's override). No change to `shell/config/diff.py`: a `fade_ms` change is `Change("restyle", name)`.

- [ ] **Step 1: Apply the test diff**

```diff
diff --git a/tests/test_config_diff.py b/tests/test_config_diff.py
index 2d56b2b..74b1bef 100644
--- a/tests/test_config_diff.py
+++ b/tests/test_config_diff.py
@@ -29,6 +29,15 @@ def test_structural_theme_change_rebuilds_monitor(fake_registry, make_config):
     assert diff_configs(old, new) == [Change("rebuild-monitor", "HDMI-A-1")]
 
 
+def test_a_fade_change_is_a_restyle_never_a_rebuild(fake_registry, make_config):
+    """fade_ms only changes the next fade: the windows stay (spec 21)."""
+    old = make_config(monitors={"HDMI-A-1": mon(), "DP-1": mon("plasma")})
+    new = make_config(theme={"fade_ms": 300}, monitors={"HDMI-A-1": mon(), "DP-1": mon("plasma")})
+    assert diff_configs(old, new) == [Change("restyle", "HDMI-A-1")]
+    one = make_config(monitors={"HDMI-A-1": mon(theme={"fade_ms": 0})})
+    assert diff_configs(old, one) == [Change("restyle", "HDMI-A-1")]
+
+
 def test_mode_changes(fake_registry, make_config):
     def cfg(shell):
         return make_config(monitors={"HDMI-A-1": mon(shell)})
diff --git a/tests/test_config_loader.py b/tests/test_config_loader.py
index d5f00f9..67aec02 100644
--- a/tests/test_config_loader.py
+++ b/tests/test_config_loader.py
@@ -1,6 +1,6 @@
 import pytest
 
-from shell.config.loader import OLD_FORMAT, load_config
+from shell.config.loader import DEFAULT_PATH, OLD_FORMAT, load_config
 from shell.config.models import ConfigError
 
 
@@ -13,6 +13,11 @@ def test_defaults_only_matches_test_theme(make_config):
     assert load_config(None).theme == make_config().theme
 
 
+def test_the_defaults_file_lists_the_fade():
+    assert load_config(None).theme.fade_ms == 50
+    assert "\nfade_ms = 50 " in DEFAULT_PATH.read_text(encoding="utf-8")  # listed, not implied
+
+
 def test_missing_user_file_uses_defaults(tmp_path, make_config):
     assert load_config(tmp_path / "nope.toml").theme == make_config().theme
 
diff --git a/tests/test_config_models.py b/tests/test_config_models.py
index 45610f2..7462d1d 100644
--- a/tests/test_config_models.py
+++ b/tests/test_config_models.py
@@ -80,6 +80,24 @@ def test_monitor_theme_override_merges(make_config):
     assert cfg.theme_for("DP-1").accent == "#8fd3b6"
 
 
+def test_fade_ms_defaults_to_50_and_is_bounded_0_to_500(make_config):
+    assert make_config().theme.fade_ms == 50
+    assert make_config(theme={"fade_ms": 0}).theme.fade_ms == 0  # 0: no fade
+    assert make_config(theme={"fade_ms": 500}).theme.fade_ms == 500
+    for bad in (-1, 501):
+        with pytest.raises(ValidationError) as exc:
+            make_config(theme={"fade_ms": bad})
+        assert exc.value.errors()[0]["loc"] == ("theme", "fade_ms")
+
+
+def test_fade_ms_has_a_per_monitor_override(make_config):
+    cfg = make_config(monitors={"HDMI-A-1": {"shell": "edge", "theme": {"fade_ms": 300}}})
+    assert cfg.theme_for("HDMI-A-1").fade_ms == 300
+    assert cfg.theme_for("DP-1").fade_ms == 50
+    with pytest.raises(ValidationError, match="monitors.HDMI-A-1.theme: fade_ms"):
+        make_config(monitors={"HDMI-A-1": {"shell": "edge", "theme": {"fade_ms": 501}}})
+
+
 def test_bad_override_color_fails_at_load(make_config):
     with pytest.raises(ValidationError) as exc:
         make_config(monitors={"HDMI-A-1": {"theme": {"accent": "nope"}}})
diff --git a/tests/test_settings_form.py b/tests/test_settings_form.py
index f2f6a12..5c9e1d6 100644
--- a/tests/test_settings_form.py
+++ b/tests/test_settings_form.py
@@ -57,6 +57,14 @@ def test_theme_numbers_take_their_bounds_from_the_schema(form):
     assert form.theme.field("thickness").hint == "px"
 
 
+def test_the_fade_is_a_0_to_500_ms_slider_with_its_hint(form):
+    fade = form.theme.field("fade_ms")
+    assert (fade.kind, fade.minimum, fade.maximum) == ("int", 0, 500)
+    assert uses_slider(fade)  # 500 is SLIDER_MAX_SPAN: the slider rule takes it
+    assert fade.label == "Fade"
+    assert fade.hint == "ms; 0 turns the fade off"
+
+
 def test_theme_font_is_a_font_list(form):
     assert form.theme.field("font").kind == "fonts"
 
@@ -466,6 +474,7 @@ def test_a_bounded_whole_number_with_a_short_range_is_a_slider():
         ("theme", "radius"),
         ("theme", "peek"),
         ("theme", "hover_zone"),
+        ("theme", "fade_ms"),
         ("border", "width"),
         ("shadow", "elevation"),
         ("handle_style", "size"),
diff --git a/tests/test_settings_tabs.py b/tests/test_settings_tabs.py
index c2dadac..d559d88 100644
--- a/tests/test_settings_tabs.py
+++ b/tests/test_settings_tabs.py
@@ -52,6 +52,7 @@ def test_each_theme_key_is_on_its_tab():
     general = keys(tabs["General"])
     assert ("theme", "accent") in general and ("theme", "thickness") in general
     assert ("theme", "font") in general and ("theme", "handle") not in general
+    assert ("theme", "fade_ms") in general  # no tab of its own: General
     assert keys(tabs["Borders"]) == [
         ("theme", "border", "enabled"),
         ("theme", "border", "width"),
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `scripts/py -m pytest -q tests/test_config_models.py tests/test_config_loader.py tests/test_config_diff.py tests/test_settings_form.py tests/test_settings_tabs.py`
Expected: `7 failed, 194 passed` (`fade_ms` is an unknown key, the defaults file lacks it, the form has no such row).

- [ ] **Step 3: Apply the implementation diff**

```diff
diff --git a/config.default.toml b/config.default.toml
index d127d58..5745ccb 100644
--- a/config.default.toml
+++ b/config.default.toml
@@ -14,6 +14,7 @@ radius = 14         # R, px
 peek = 14           # hover peek depth, px
 hover_zone = 16     # invisible hover target past the frame, px
 duration_ms = 280
+fade_ms = 50        # fade in/out of a monitor's Edge Shell, 0-500 ms; 0 = no fade
 font = ["Hack Nerd Font Mono", "JetBrains Mono", "monospace"]
 
 # Border around the outside of the frame and panel outline (spec section 18). Opt-in.
diff --git a/settings/form.py b/settings/form.py
index 63620bb..9031d76 100644
--- a/settings/form.py
+++ b/settings/form.py
@@ -46,6 +46,7 @@ HINTS = {
     ("Theme", "peek"): "px",
     ("Theme", "hover_zone"): "px",
     ("Theme", "duration_ms"): "ms",
+    ("Theme", "fade_ms"): "ms; 0 turns the fade off",
     ("Border", "width"): "px",
     ("Shadow", "elevation"): "% (100 % = 48 px)",
     ("HandleStyle", "size"): "px along the edge",
@@ -68,6 +69,7 @@ HINTS = {
 # Row labels; any other key reads "Some key" (pydantic's own titles read "Duration Ms").
 LABELS = {
     "duration_ms": "Duration",
+    "fade_ms": "Fade",
     "text_secondary": "Secondary text",
     "surface_hover": "Surface (hover)",
     "handle_hover": "Handle (hover)",
@@ -90,9 +92,9 @@ KIND_LABELS = {"edge": "Edge", "corner": "Corner", "float": "Float (coming soon)
 LEAD_ROWS = ("name", "widget", "panel")  # every panel section starts with these
 # A whole number with both bounds gets a slider (Phil: "If a numeric has a minimum and maximum
 # use sliders instead of number spinners") when its range is at most this wide: on a 160 px
-# slider that is at most 3 values per pixel. Wider ranges (an offset of +-20000, a corner
-# width of 60-4000 px, a duration of 0-5000 ms, a depth of 16-2000 px, an order of 0-1000)
-# keep the spin button, whose arrows step by one.
+# slider that is at most 3 values per pixel (the fade, 0-500 ms, is the widest slider). Wider
+# ranges (an offset of +-20000, a corner width of 60-4000 px, a duration of 0-5000 ms, a depth
+# of 16-2000 px, an order of 0-1000) keep the spin button, whose arrows step by one.
 SLIDER_MAX_SPAN = 500
 CORNER_ROWS = (*LEAD_ROWS, "corner", "edge", "width", "height", "state")  # a corner panel
 
diff --git a/shell/config/models.py b/shell/config/models.py
index c7ab211..f0d6e4b 100644
--- a/shell/config/models.py
+++ b/shell/config/models.py
@@ -132,6 +132,9 @@ class Theme(_Strict):
     peek: Annotated[int, Field(ge=1, le=64)]
     hover_zone: Annotated[int, Field(ge=1, le=64)]
     duration_ms: Annotated[int, Field(ge=0, le=5000)]
+    # The fade in and out of a monitor's windows (spec 21); 0 = none. At most 500, so the
+    # settings window shows a slider (settings.form.SLIDER_MAX_SPAN).
+    fade_ms: Annotated[int, Field(ge=0, le=500)] = 50
     font: Annotated[list[str], Field(min_length=1)]
     border: Border = Field(default_factory=Border)
     shadow: Shadow = Field(default_factory=Shadow)
```

- [ ] **Step 4: Run the tests to see them pass**

Run: the command of Step 2. Expected: `201 passed`.

- [ ] **Step 5: VERIFY** (Global Constraints). Expected: `2729 passed`.

- [ ] **Step 6: Reviewer mutations** (each must make a test fail; measured): `le=500` -> `le=5000` (`test_fade_ms_defaults_to_50_and_is_bounded_0_to_500`); model default 50 -> 0 (same test); `"fade_ms"` added to `diff._STRUCTURAL` (`test_a_fade_change_is_a_restyle_never_a_rebuild`); the `HINTS` entry removed (`test_the_fade_is_a_0_to_500_ms_slider_with_its_hint`); `fade_ms = 50` commented out in `config.default.toml` (`test_the_defaults_file_lists_the_fade`).

- [ ] **Step 7: Commit**

```bash
git add shell/config/models.py config.default.toml settings/form.py tests/test_config_models.py tests/test_config_loader.py tests/test_config_diff.py tests/test_settings_form.py tests/test_settings_tabs.py
git commit -m "feat(config): theme fade_ms, the time of the shell fade (0 turns it off)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: A pure `Fade` controller on the frame clock

**Files:**
- Create: `shell/fade.py`
- Modify: `shell/anim.py` (`linear` after `EASE_OUT`; `Tween.stop` before `animate_to`)
- Test: `tests/test_fade.py` (new), `tests/test_anim.py`

**Interfaces:**
- Consumes: `shell.anim.Tween(widget, on_value, duration_ms, delay_ms=0, easing=EASE_OUT)` (`widget` has `add_tick_callback(fn) -> int` and `remove_tick_callback(id)`); `shell.canvas.simulate.FakeClock`, `FakeTicker`, `FRAME_US` in the tests.
- Produces:
  - `shell.anim.linear(t: float) -> float`; `Tween.stop() -> None` (removes the tick callback, keeps `value`, no last `on_value`).
  - `shell.fade.READY_TIMEOUT_MS = 1000`, `FINISH_MARGIN_MS = 300`, `State = Literal["waiting", "fading-in", "shown", "fading-out", "done"]`.
  - `shell.fade.Fade(ticker, set_opacity: Callable[[float], None], duration_ms: int, timeout_add: Callable[[int, Callable[[], bool]], int], source_remove: Callable[[int], object], on_start: Callable[[], None] | None = None)` with attributes `state: State`, `value: float` (the opacity the windows have), `duration_ms: int` and methods `ready() -> None`, `fade_out(duration_ms: int, on_done: Callable[[], None]) -> None`, `finish() -> None`, `cancel() -> None`. With `duration_ms` 0 it is `"shown"` from the start and never calls `set_opacity` or `timeout_add`.

- [ ] **Step 1: Apply the test diff**

```diff
diff --git a/tests/test_anim.py b/tests/test_anim.py
index c7db887..e553222 100644
--- a/tests/test_anim.py
+++ b/tests/test_anim.py
@@ -1,6 +1,6 @@
 import pytest
 
-from shell.anim import EASE_OUT, Tween, cubic_bezier
+from shell.anim import EASE_OUT, Tween, cubic_bezier, linear
 
 
 class FakeClock:
@@ -44,6 +44,10 @@ def test_linear_bezier_is_identity():
     assert linear(0.3) == pytest.approx(0.3, abs=1e-3)
 
 
+def test_linear_is_the_identity_on_0_to_1():
+    assert [linear(t) for t in (0.0, 0.25, 0.5, 1.0)] == [0.0, 0.25, 0.5, 1.0]
+
+
 def test_animate_reaches_target_and_stops():
     w, seen = FakeWidget(), []
     t = Tween(w, seen.append, duration_ms=280)
@@ -143,3 +147,21 @@ def test_on_value_jump_then_animate_on_final_frame_registers_one_callback():
     w.frame(0)
     w.frame(200)
     assert t.value == 50 and not w.callbacks and not t.running
+
+
+def test_stop_freezes_without_a_last_value():
+    """A fade stops its tween before its windows are destroyed: no on_value after stop."""
+    w, seen = FakeWidget(), []
+    t = Tween(w, seen.append, duration_ms=100)
+    t.animate_to(1.0)
+    w.frame(0)
+    w.frame(50)
+    seen_before, value = list(seen), t.value
+    t.stop()
+    assert not w.callbacks and not t.running and seen == seen_before and t.value == value
+    w.frame(50)
+    assert seen == seen_before
+    t.stop()  # stopping a stopped tween is fine
+    t.animate_to(0.0)  # and it can run again, from where it stopped
+    w.frame(0)
+    assert seen[-1] == pytest.approx(value)
diff --git a/tests/test_fade.py b/tests/test_fade.py
new file mode 100644
index 0000000..57bf337
--- /dev/null
+++ b/tests/test_fade.py
@@ -0,0 +1,259 @@
+"""shell.fade.Fade: the fade of one monitor's windows, on a fake frame clock and fake timers
+(pure: no GTK)."""
+
+import logging
+
+import pytest
+
+from shell.canvas.simulate import FRAME_US, FakeClock, FakeTicker
+from shell.fade import FINISH_MARGIN_MS, READY_TIMEOUT_MS, Fade
+
+
+class FakeTimers:
+    """GLib.timeout_add / GLib.source_remove stand-ins; `fire(ms)` runs the pending timer of
+    that delay as the main loop would (a False return removes it)."""
+
+    def __init__(self):
+        self.pending: dict[int, tuple[int, object]] = {}
+        self.removed: list[int] = []
+        self._next = 1
+
+    def add(self, ms, fn):
+        timer, self._next = self._next, self._next + 1
+        self.pending[timer] = (ms, fn)
+        return timer
+
+    def remove(self, timer):
+        assert timer in self.pending, "removed a timer that is not pending (GLib warns)"
+        del self.pending[timer]
+        self.removed.append(timer)
+
+    def delays(self):
+        return sorted(ms for ms, _ in self.pending.values())
+
+    def fire(self, ms):
+        timer = next(t for t, (d, _) in self.pending.items() if d == ms)
+        _, fn = self.pending.pop(timer)
+        assert fn() is False  # a one-shot GLib source
+
+
+class Rig:
+    """One Fade with everything it is given recorded."""
+
+    def __init__(self, duration_ms=50):
+        self.clock, self.ticker, self.timers = FakeClock(), FakeTicker(), FakeTimers()
+        self.values, self.started, self.done = [], 0, 0
+        self.frame = 0
+        self.fade = Fade(
+            self.ticker,
+            self.values.append,
+            duration_ms,
+            self.timers.add,
+            self.timers.remove,
+            on_start=self._start,
+        )
+
+    def _start(self):
+        self.started += 1
+
+    def on_done(self):
+        self.done += 1
+
+    def frames(self, n):
+        for _ in range(n):
+            self.clock.now_us = self.frame * FRAME_US
+            self.frame += 1
+            self.ticker.run(self.clock)
+
+    @property
+    def ticking(self):
+        return bool(self.ticker._callbacks)
+
+
+def test_zero_ms_is_shown_from_the_start_and_does_no_fade_work():
+    rig = Rig(0)
+    assert rig.fade.state == "shown" and rig.fade.value == 1.0
+    rig.fade.ready()
+    rig.fade.finish()
+    rig.frames(5)
+    assert rig.values == [] and rig.timers.pending == {} and not rig.ticking
+    assert rig.started == 0  # nothing waits for a fade that never runs
+    rig.fade.fade_out(0, rig.on_done)
+    assert rig.done == 1 and rig.fade.state == "done" and rig.values == []
+
+
+def test_it_starts_transparent_and_waits_for_ready():
+    rig = Rig()
+    assert rig.values == [0.0] and rig.fade.state == "waiting"
+    assert rig.timers.delays() == [READY_TIMEOUT_MS]
+    rig.frames(10)  # frames alone never start it
+    assert rig.values == [0.0] and not rig.ticking
+
+
+def test_ready_fades_in_linearly_over_the_duration_on_the_frame_clock():
+    rig = Rig(50)
+    rig.fade.ready()
+    assert rig.fade.state == "fading-in" and rig.started == 1
+    assert rig.timers.delays() == [50 + FINISH_MARGIN_MS]  # the ready timeout is gone
+    rig.frames(5)
+    # the first frame still shows 0: the start is the frame time of the first tick; a 50 ms
+    # fade is 3 frames at 60 Hz
+    assert rig.values[:2] == [0.0, 0.0]
+    assert rig.values[2:] == pytest.approx([1 / 3, 2 / 3, 1.0], abs=1e-3)
+    assert rig.values[-1] == 1.0  # exactly: no group-alpha left after the fade
+    assert rig.fade.state == "shown" and rig.fade.value == 1.0
+    assert rig.timers.pending == {} and not rig.ticking
+
+
+def test_ready_twice_is_one_fade():
+    rig = Rig()
+    rig.fade.ready()
+    rig.fade.ready()
+    assert rig.started == 1 and len(rig.ticker._callbacks) == 1
+    assert len(rig.timers.pending) == 1
+
+
+def test_the_ready_timeout_fades_in_anyway():
+    rig = Rig()
+    rig.timers.fire(READY_TIMEOUT_MS)
+    assert rig.fade.state == "fading-in" and rig.started == 1
+    rig.frames(5)
+    assert rig.fade.state == "shown"
+
+
+def test_a_fade_without_frames_is_finished_by_its_timeout():
+    """The canvas never maps (no frames): the shell must not stay invisible."""
+    rig = Rig()
+    rig.fade.ready()
+    rig.timers.fire(50 + FINISH_MARGIN_MS)
+    assert rig.values[-1] == 1.0 and rig.fade.state == "shown"
+    assert rig.timers.pending == {} and not rig.ticking
+
+
+def test_fade_out_from_shown_reaches_zero_then_calls_back_once():
+    rig = Rig()
+    rig.fade.ready()
+    rig.frames(5)
+    rig.fade.fade_out(50, rig.on_done)
+    assert rig.fade.state == "fading-out" and rig.done == 0
+    out_start = len(rig.values)
+    rig.frames(5)
+    out = rig.values[out_start:]
+    assert out == sorted(out, reverse=True) and out[-1] == 0.0
+    assert rig.done == 1 and rig.fade.state == "done"
+    assert rig.timers.pending == {} and not rig.ticking
+    rig.frames(3)
+    assert rig.done == 1
+
+
+def test_fade_out_mid_fade_in_starts_from_the_current_value():
+    rig = Rig()
+    rig.fade.ready()
+    rig.frames(2)  # the start, then 1/3
+    now = rig.fade.value
+    assert 0.3 < now < 0.4
+    out_start = len(rig.values)
+    rig.fade.fade_out(50, rig.on_done)
+    rig.frames(6)
+    out = rig.values[out_start:]
+    assert max(out) <= now + 1e-9  # never a jump up
+    assert out[-1] == 0.0 and rig.done == 1
+
+
+def test_fade_out_while_waiting_is_done_at_once():
+    """Nothing was visible yet: there is nothing to fade."""
+    rig = Rig()
+    rig.fade.fade_out(50, rig.on_done)
+    assert rig.done == 1 and rig.fade.state == "done"
+    assert rig.values == [0.0] and rig.timers.pending == {} and not rig.ticking
+
+
+def test_fade_out_with_zero_ms_is_done_at_once_without_touching_the_opacity():
+    rig = Rig()
+    rig.fade.ready()
+    rig.frames(5)
+    seen = len(rig.values)
+    rig.fade.fade_out(0, rig.on_done)
+    assert rig.done == 1 and rig.fade.state == "done" and len(rig.values) == seen
+    assert rig.timers.pending == {} and not rig.ticking
+
+
+def test_fade_out_takes_its_own_duration():
+    rig = Rig(50)
+    rig.fade.ready()
+    rig.frames(5)
+    rig.fade.fade_out(300, rig.on_done)
+    assert rig.timers.delays() == [300 + FINISH_MARGIN_MS]
+    rig.frames(18)  # 300 ms is 18 frames: the first one starts the clock
+    assert rig.done == 0
+    rig.frames(1)
+    assert rig.done == 1
+
+
+def test_a_second_fade_out_keeps_the_running_one():
+    rig = Rig()
+    rig.fade.ready()
+    rig.frames(5)
+    rig.fade.fade_out(50, rig.on_done)
+    other = []
+    rig.fade.fade_out(50, lambda: other.append(1))
+    rig.frames(6)
+    assert rig.done == 1 and other == [] and len(rig.ticker._callbacks) == 0
+
+
+def test_fade_out_after_done_calls_back_at_once():
+    rig = Rig()
+    rig.fade.fade_out(50, rig.on_done)
+    rig.fade.fade_out(50, rig.on_done)
+    assert rig.done == 2
+
+
+def test_finish_completes_each_phase_at_once():
+    rig = Rig()
+    rig.fade.finish()  # waiting: shown at once (and the start is announced)
+    assert rig.fade.state == "shown" and rig.values[-1] == 1.0 and rig.started == 1
+    assert rig.timers.pending == {} and not rig.ticking
+    rig.fade.fade_out(50, rig.on_done)
+    rig.frames(2)
+    rig.fade.finish()
+    assert rig.fade.state == "done" and rig.values[-1] == 0.0 and rig.done == 1
+    assert rig.timers.pending == {} and not rig.ticking
+
+
+def test_cancel_stops_everything_without_callbacks():
+    rig = Rig()
+    rig.fade.ready()
+    rig.frames(2)
+    rig.fade.fade_out(50, rig.on_done)
+    seen = len(rig.values)
+    rig.fade.cancel()
+    rig.frames(5)
+    assert len(rig.values) == seen and rig.done == 0  # no opacity on windows being destroyed
+    assert rig.fade.state == "done" and rig.timers.pending == {} and not rig.ticking
+    rig.fade.cancel()  # twice is fine
+
+
+def test_cancel_while_waiting_removes_the_ready_timeout():
+    rig = Rig()
+    rig.fade.cancel()
+    assert rig.timers.pending == {} and rig.fade.state == "done"
+    rig.fade.ready()
+    assert rig.started == 0 and not rig.ticking
+
+
+def test_a_failing_callback_never_breaks_the_fade(caplog):
+    rig = Rig()
+
+    def boom():
+        raise RuntimeError("callback failed")
+
+    rig.fade._on_start = boom
+    with caplog.at_level(logging.ERROR, logger="shell.fade"):
+        rig.fade.ready()
+        rig.frames(5)
+        assert rig.fade.state == "shown"
+        rig.fade.fade_out(50, boom)
+        rig.frames(5)
+    assert rig.fade.state == "done" and rig.timers.pending == {} and not rig.ticking
+    failed = [r for r in caplog.records if r.name == "shell.fade" and r.exc_info]
+    assert [str(r.exc_info[1]) for r in failed] == ["callback failed", "callback failed"]
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `scripts/py -m pytest -q tests/test_fade.py tests/test_anim.py`
Expected: `2 errors` during collection (`ModuleNotFoundError: No module named 'shell.fade'`, `ImportError: cannot import name 'linear'`).

- [ ] **Step 3: Apply the implementation diff**

```diff
diff --git a/shell/anim.py b/shell/anim.py
index 8cec847..25b932a 100644
--- a/shell/anim.py
+++ b/shell/anim.py
@@ -33,6 +33,11 @@ def cubic_bezier(x1: float, y1: float, x2: float, y2: float) -> Easing:
 EASE_OUT = cubic_bezier(0.2, 0.8, 0.2, 1.0)
 
 
+def linear(t: float) -> float:
+    """No easing (the shell fade: equal opacity steps per frame)."""
+    return t
+
+
 class Tween:
     def __init__(
         self,
@@ -63,6 +68,13 @@ class Tween:
         self.value = self._from = self._to = float(target)
         self._on_value(self.value)
 
+    def stop(self) -> None:
+        """Stop where it is, without a last on_value (its widget may be about to go)."""
+        if self._tick_id:
+            self._widget.remove_tick_callback(self._tick_id)
+            self._tick_id = 0
+        self._from = self._to = self.value
+
     def animate_to(self, target: float) -> None:
         target = float(target)
         if self._tick_id:
diff --git a/shell/fade.py b/shell/fade.py
new file mode 100644
index 0000000..f8a4dbd
--- /dev/null
+++ b/shell/fade.py
@@ -0,0 +1,159 @@
+"""The fade of one monitor's Edge Shell windows (spec 21): built transparent, faded in once the
+monitor is ready, faded out before the windows go. One Tween on one frame clock sets the
+opacity of every window of the monitor in the same frame. Pure: the frame-clock widget, the
+opacity setter and the timers are given (shell.monitors passes the canvas window, a setter
+over all its windows and GLib's timeout_add / source_remove)."""
+
+from __future__ import annotations
+
+import logging
+from collections.abc import Callable
+from typing import Literal
+
+from shell.anim import Tween, linear
+
+log = logging.getLogger(__name__)
+
+# Fade in at the latest this long after the build, ready or not: a build that never reports
+# ready must not leave the monitor invisible. Above shell.monitors.RAISE_DELAY_MS (500 ms, the
+# re-raise the monitor normally waits for), so it only fires when something is stuck.
+READY_TIMEOUT_MS = 1000
+# A fade still running this long after its duration is finished at once: its Tween runs only
+# while the canvas gets frames, and a canvas that is never mapped gets none.
+FINISH_MARGIN_MS = 300
+
+State = Literal["waiting", "fading-in", "shown", "fading-out", "done"]
+
+
+class Fade:
+    """waiting -> fading-in -> shown -> fading-out -> done (`state`).
+
+    `ticker` is the widget whose frame clock drives the Tween (add_tick_callback /
+    remove_tick_callback), `set_opacity(v)` sets every window. With `duration_ms` 0 the fade is
+    "shown" from the start and never calls set_opacity or arms a timer: the windows behave as
+    without a fade. `on_start()` is called when the fade-in starts (the monitor's input and a
+    crossfade's old shell follow it)."""
+
+    def __init__(
+        self,
+        ticker,
+        set_opacity: Callable[[float], None],
+        duration_ms: int,
+        timeout_add: Callable[[int, Callable[[], bool]], int],
+        source_remove: Callable[[int], object],
+        on_start: Callable[[], None] | None = None,
+    ):
+        self._ticker = ticker
+        self._set_opacity = set_opacity
+        self._timeout_add = timeout_add
+        self._source_remove = source_remove
+        self._on_start = on_start
+        self._on_done: Callable[[], None] | None = None
+        self._timer = 0
+        self.duration_ms = max(0, duration_ms)
+        self._tween = Tween(ticker, self._on_value, self.duration_ms, easing=linear)
+        self.value = 1.0  # the opacity the windows have (what a window added now gets)
+        if self.duration_ms == 0:
+            self.state: State = "shown"
+            return
+        self.state = "waiting"
+        self._tween.jump_to(0.0)
+        self._arm(READY_TIMEOUT_MS, self._ready_timeout)
+
+    # ---- phases -----------------------------------------------------------------------
+    def ready(self) -> None:
+        """The monitor is ready: fade in (once; only while waiting)."""
+        if self.state != "waiting":
+            return
+        self.state = "fading-in"
+        self._tween.animate_to(1.0)
+        self._arm(self.duration_ms + FINISH_MARGIN_MS, self._finish_timeout)
+        self._call(self._on_start)
+
+    def fade_out(self, duration_ms: int, on_done: Callable[[], None]) -> None:
+        """Fade out over `duration_ms` from the current opacity (no jump), then on_done().
+        Done at once when nothing is visible yet (waiting), with 0 ms (the opacity is not
+        touched) or when already done. A second call while fading out is ignored: the running
+        fade keeps its callback."""
+        if self.state == "fading-out":
+            return
+        if self.state in ("waiting", "done") or duration_ms <= 0:
+            self._stop()
+            self.state = "done"
+            self._call(on_done)
+            return
+        self._tween.stop()
+        self.state = "fading-out"
+        self._on_done = on_done
+        self._tween = Tween(self._ticker, self._on_value, duration_ms, easing=linear)
+        self._tween.jump_to(self.value)
+        self._tween.animate_to(0.0)
+        if self.state == "fading-out":  # not settled by the jump (a value already at 0)
+            self._arm(duration_ms + FINISH_MARGIN_MS, self._finish_timeout)
+
+    def finish(self) -> None:
+        """Complete the current phase now: waiting or fading in -> shown, fading out -> done
+        (and its on_done). Shown and done stay as they are."""
+        if self.state == "waiting":
+            self.ready()
+        if self.state == "fading-in":
+            self._tween.jump_to(1.0)
+        elif self.state == "fading-out":
+            self._tween.jump_to(0.0)
+
+    def cancel(self) -> None:
+        """Stop without another opacity or callback (the windows are being destroyed now)."""
+        self._stop()
+        self._on_done = None
+        self.state = "done"
+
+    # ---- internals --------------------------------------------------------------------
+    def _on_value(self, value: float) -> None:
+        self.value = value
+        self._set_opacity(value)
+        if self._tween.running:
+            return
+        if self.state == "fading-in" and value >= 1.0:
+            self.state = "shown"
+            self._disarm()
+        elif self.state == "fading-out" and value <= 0.0:
+            self.state = "done"
+            self._disarm()
+            done, self._on_done = self._on_done, None
+            self._call(done)
+
+    def _stop(self) -> None:
+        self._tween.stop()
+        self._disarm()
+
+    def _arm(self, ms: int, fn: Callable[[], bool]) -> None:
+        self._disarm()
+        self._timer = self._timeout_add(ms, fn)
+
+    def _disarm(self) -> None:
+        if self._timer:
+            self._source_remove(self._timer)
+            self._timer = 0
+
+    def _ready_timeout(self) -> bool:
+        self._timer = 0  # fired: GLib removes it when this returns False
+        log.debug("not ready after %d ms: fading in anyway", READY_TIMEOUT_MS)
+        self.ready()
+        return False
+
+    def _finish_timeout(self) -> bool:
+        self._timer = 0
+        log.warning("a fade did not finish in time (no frames?): finishing it now")
+        self.finish()
+        return False
+
+    @staticmethod
+    def _call(fn: Callable[[], None] | None) -> None:
+        """Run a callback; it runs inside a frame-clock tick or a GLib timer, so an exception
+        is logged, never raised into the main loop (the fade's own state is already final)."""
+        if fn is None:
+            return
+        try:
+            fn()
+        except Exception:
+            log.exception("a fade callback failed")
```

- [ ] **Step 4: Run the tests to see them pass**

Run: the command of Step 2. Expected: `29 passed`.

- [ ] **Step 5: VERIFY**. Expected: `2748 passed`.

- [ ] **Step 6: Reviewer mutations** (measured): the constructor's `jump_to(0.0)` removed (`test_it_starts_transparent_and_waits_for_ready`); `ready()` arming no finish timer (`test_ready_fades_in_linearly_over_the_duration_on_the_frame_clock`); `fade_out` without `jump_to(self.value)` (`test_fade_out_from_shown_reaches_zero_then_calls_back_once`); `_call` re-raising (`test_a_failing_callback_never_breaks_the_fade`); the Tween's `easing=linear` dropped (`test_ready_fades_in_linearly_...`); `cancel()` not stopping the Tween (`test_cancel_stops_everything_without_callbacks`); the "already fading out" guard removed (`test_a_second_fade_out_keeps_the_running_one`); `Tween.stop` calling `on_value` (`test_stop_freezes_without_a_last_value`).

- [ ] **Step 7: Commit**

```bash
git add shell/fade.py shell/anim.py tests/test_fade.py tests/test_anim.py
git commit -m "feat(shell): a pure Fade controller on the frame clock" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: A monitor's windows fade in once it is ready

**Files:**
- Modify: `shell/monitors.py` (`MonitorShell.__init__` arguments and state, `_build`, `_measure`, `_new_panel`, `_raise_panels`, `_raise_one`, a new "fade" section, `_track`, `close`), `shell/edge_panel.py` (`_input_off`, `set_input_enabled`, `_update_input_region`)
- Test: `tests/test_monitor_fade.py` (new), `tests/test_monitor_shell.py` (`FakeWindow` records `set_opacity` / `set_input_enabled`; `bare_shell` gets the new attributes), `tests/test_edge_panel_handle.py`, `tests/test_corner_panel.py` (their stubs get `_input_off=False`)

**Interfaces:**
- Consumes: `shell.fade.Fade` (Task 2); `GLib.timeout_add`, `GLib.idle_add`, `GLib.source_remove` (looked up when the shell is built, so the tests' fakes apply).
- Produces:
  - `MonitorShell(name, monitor, config, register_window, unregister_window=None, on_layout=None, on_error=None, on_settings=None, fade_ms: int = 0, on_fade_in: Callable[[MonitorShell], None] | None = None)`; `on_fade_in(shell)` is called when the fade-in starts (never inside the constructor). `fade_ms` 0 (the default): no fade, as before.
  - `MonitorShell._raise_panels(first: bool = False) -> bool` (the build schedules `(500, first=True)` and `(2000, first=False)`), `_raised()`, `_ready_idle() -> bool`, `_check_ready()`, `_faded_in()`, `_set_opacity(value: float)`, `_apply_opacity(window, value: float)`; attributes `_fade: Fade | None`, `_raises_pending: int`, `_ready_id: int`, `_input_live: bool`.
  - `EdgePanel.set_input_enabled(enabled: bool) -> None` (CornerPanel inherits it).
  - Test helpers for later tasks: `tests/test_monitor_fade.py` `TickCanvas`, `Loop` (`timeout_add`, `idle_add`, `source_remove`, `delays()`, `fire(ms)`, `run_idles()`), fixtures `loop` and `build(monitors, fade_ms=50, theme=None)` (the shell gets `frames(n)`, `faded`, `config_for`), helper `shown(shell, loop)`, constants `DOCK`, `CLOCK`, `THIRDS`; `FakeWindow.opacity`, `FakeWindow.inputs`.

- [ ] **Step 1: Apply the test diff**

```diff
diff --git a/tests/test_corner_panel.py b/tests/test_corner_panel.py
index 9ca8846..812bb30 100644
--- a/tests/test_corner_panel.py
+++ b/tests/test_corner_panel.py
@@ -29,6 +29,7 @@ def stub(make_config, spec=BOX, interaction=None, handle=None, d=0.0):
         _look=hd.resolve_handle(handle, interaction, theme),
         _d=d,
         _last_rect=None,
+        _input_off=False,
         _handle=FakeHandleWidget(),
         _handle_area=SimpleNamespace(draws=0),
         _content=FakeHandleWidget(),
@@ -210,6 +211,16 @@ def test_the_corner_input_region_is_reapplied_after_the_parent_allocate(make_con
     assert s.regions[0] is None and rects_of(s.regions[-1]) == [(0, 364, 300, 26)]
 
 
+def test_a_corner_panel_with_input_off_takes_none(make_config):
+    s = stub(make_config)
+    s._hovered = False
+    s._update_input_region = lambda d: ep.EdgePanel._update_input_region(s, d)
+    ep.EdgePanel.set_input_enabled(s, False)
+    assert rects_of(s.regions[-1]) == []
+    ep.EdgePanel.set_input_enabled(s, True)
+    assert rects_of(s.regions[-1]) == [(0, 364, 300, 26)]
+
+
 def test_a_build_that_raises_destroys_the_half_built_window(make_config, monkeypatch):
     """The window exists before its content: a widget that raises in build() (after it may have
     started a timer) must not leave the window, or its widget's timer, behind."""
diff --git a/tests/test_edge_panel_handle.py b/tests/test_edge_panel_handle.py
index 64d0077..4beac1e 100644
--- a/tests/test_edge_panel_handle.py
+++ b/tests/test_edge_panel_handle.py
@@ -54,6 +54,7 @@ def stub(make_config, edge="bottom", interaction=ALL, handle=None, **extra):
         _hovered=False,
         _extended=False,
         _last_rect=None,
+        _input_off=False,
         _draw_failed=False,
         _handle=FakeHandleWidget(),
         _handle_area=SimpleNamespace(draws=0),
@@ -337,6 +338,40 @@ def test_the_input_region_is_reapplied_after_the_parent_allocate(
     assert s._last_rect == primed
 
 
+def test_with_input_off_a_panel_takes_none_at_any_depth_until_it_is_on_again(make_config):
+    """Spec 21: a monitor's panels take no input while it is invisible or fading out."""
+    s = stub(make_config)
+    s._update_input_region = lambda d: ep.EdgePanel._update_input_region(s, d)
+    ep.EdgePanel._update_input_region(s, 0.0)
+    ep.EdgePanel.set_input_enabled(s, False)
+    assert rects_of(s.regions[-1]) == []
+    for d in (0.0, 32.0, 64.0):  # depth frames keep it empty
+        ep.EdgePanel._update_input_region(s, d)
+        assert rects_of(s.regions[-1]) == []
+    ep.EdgePanel.set_input_enabled(s, True)
+    assert rects_of(s.regions[-1]) == [(14, 48, 560, 26)]  # the region of depth 0 again
+
+
+def test_input_off_survives_the_parent_allocate(make_config, monkeypatch):
+    s = stub(make_config)
+    s._update_input_region = lambda d: ep.EdgePanel._update_input_region(s, d)
+    monkeypatch.setattr(ep.WaylandWindow, "do_size_allocate", lambda _s, _a: s.regions.append(None))
+    ep.EdgePanel.set_input_enabled(s, False)
+    s.regions.clear()
+    ep.EdgePanel.do_size_allocate(s, None)  # Fabric resets the shape to the whole surface
+    assert s.regions[0] is None and rects_of(s.regions[-1]) == []
+
+
+def test_turning_input_off_drops_a_hover_peek(make_config):
+    s = stub(make_config, _hovered=True)
+    s._update_input_region = lambda d: ep.EdgePanel._update_input_region(s, d)
+    s._retarget = lambda: s.calls.append(("retarget", s._hovered))
+    ep.EdgePanel.set_input_enabled(s, False)
+    assert s._hovered is False and s.calls == [("retarget", False)]
+    ep.EdgePanel.set_input_enabled(s, True)
+    assert s.calls == [("retarget", False)]  # turning it on retargets nothing
+
+
 # ---- interaction flags --------------------------------------------------------------
 
 
diff --git a/tests/test_monitor_fade.py b/tests/test_monitor_fade.py
new file mode 100644
index 0000000..b1f76dd
--- /dev/null
+++ b/tests/test_monitor_fade.py
@@ -0,0 +1,308 @@
+"""MonitorShell's fade (spec 21), display-free: fake windows, the canvas as a fake frame clock
+(shell.canvas.simulate), fake GLib timers and idles."""
+
+import pytest
+
+pytest.importorskip("gi")
+pytest.importorskip("fabric")
+
+import shell.monitors as mon_mod  # noqa: E402
+from shell.canvas.simulate import FRAME_US, FakeClock, FakeTicker  # noqa: E402
+from shell.config.diff import Change  # noqa: E402
+from shell.fade import FINISH_MARGIN_MS, READY_TIMEOUT_MS  # noqa: E402
+from tests.test_monitor_shell import FakeCanvas, FakeMonitor, FakeWindow, edge  # noqa: E402
+
+DOCK = {"panel": "edge", "name": "dock", "widget": "dock"}
+CLOCK = {"panel": "edge", "name": "clock", "widget": "clock"}
+THIRDS = [0.0, 1 / 3, 2 / 3, 1.0]  # a 50 ms fade at 60 Hz: the first frame starts the clock
+
+
+class TickCanvas(FakeCanvas):
+    """The canvas as the fade's frame clock: FakeTicker's two methods, run by `frames`."""
+
+    def __init__(self, *args, **kwargs):
+        super().__init__(*args, **kwargs)
+        self.ticker = FakeTicker()
+        self.add_tick_callback = self.ticker.add_tick_callback
+        self.remove_tick_callback = self.ticker.remove_tick_callback
+
+
+class Loop:
+    """GLib.timeout_add / idle_add / source_remove stand-ins, run by hand."""
+
+    def __init__(self):
+        self.timers: dict[int, tuple] = {}
+        self.idles: dict[int, tuple] = {}
+        self.removed: list[int] = []
+        self._next = 1
+
+    def _id(self):
+        source, self._next = self._next, self._next + 1
+        return source
+
+    def timeout_add(self, ms, fn, *args):
+        source = self._id()
+        self.timers[source] = (ms, fn, args)
+        return source
+
+    def idle_add(self, fn, *args):
+        source = self._id()
+        self.idles[source] = (fn, args)
+        return source
+
+    def source_remove(self, source):
+        assert source in self.timers or source in self.idles, "removed a source that is gone"
+        self.timers.pop(source, None)
+        self.idles.pop(source, None)
+        self.removed.append(source)
+
+    def delays(self):
+        return sorted(ms for ms, _, _ in self.timers.values())
+
+    def fire(self, ms):
+        """Every pending timer of that delay, oldest first (one-shot: a False return)."""
+        for source in sorted(s for s, (d, _, _) in self.timers.items() if d == ms):
+            if source in self.timers:
+                _, fn, args = self.timers.pop(source)
+                assert fn(*args) is False
+
+    def run_idles(self):
+        while self.idles:
+            source = min(self.idles)
+            fn, args = self.idles.pop(source)
+            assert fn(*args) is False
+
+
+@pytest.fixture
+def loop(monkeypatch):
+    loop = Loop()
+    monkeypatch.setattr(mon_mod.GLib, "timeout_add", loop.timeout_add)
+    monkeypatch.setattr(mon_mod.GLib, "idle_add", loop.idle_add)
+    monkeypatch.setattr(mon_mod.GLib, "source_remove", loop.source_remove)
+    return loop
+
+
+@pytest.fixture
+def build(monkeypatch, make_config, fake_registry, loop):
+    """build(monitors, fade_ms=50) -> a MonitorShell on fakes, with `frames(n)`, `faded`
+    (its on_fade_in calls) and `config_for(monitors, theme)`."""
+    monkeypatch.delenv("EDGE_SHELL_RAISE_MS", raising=False)
+    monkeypatch.setattr(mon_mod, "ShapeCanvas", TickCanvas)
+    monkeypatch.setattr(mon_mod, "FrameEdge", FakeWindow)
+    real_panel_class = mon_mod.panel_class
+    monkeypatch.setattr(
+        mon_mod,
+        "panel_class",
+        lambda geo: type(real_panel_class(geo).__name__, (FakeWindow,), {}),
+    )
+    monkeypatch.setattr(mon_mod.MonitorShell, "_check_monitor", lambda self, w: None)
+
+    def _build(monitors, fade_ms=50, theme=None):
+        faded = []
+        shell = mon_mod.MonitorShell(
+            "HDMI-A-1",
+            FakeMonitor(),
+            make_config(monitors=monitors, theme=theme),
+            lambda _w: None,
+            fade_ms=fade_ms,
+            on_fade_in=faded.append,
+        )
+        clock = FakeClock()
+
+        def frames(n):
+            for _ in range(n):
+                clock.now_us += FRAME_US
+                shell.canvas.ticker.run(clock)
+
+        shell.frames, shell.faded, shell.config_for = frames, faded, make_config
+        return shell
+
+    return _build
+
+
+def shown(shell, loop):
+    """Run the build to the end of its fade-in."""
+    loop.run_idles()
+    loop.fire(mon_mod.RAISE_DELAY_MS)
+    shell.frames(4)
+    assert shell._fade.state == "shown"
+
+
+def test_without_a_fade_no_window_gets_an_opacity_and_nothing_waits(build, loop):
+    shell = build(edge(DOCK), fade_ms=0)
+    assert all(w.opacity == [] and w.inputs == [] for w in shell.windows)
+    assert loop.idles == {} and loop.delays() == [500, 2000]  # only the re-raises, as before
+    loop.fire(500)
+    shell.frames(5)
+    assert all(w.opacity == [] for w in shell.windows) and shell.faded == []
+
+
+def test_every_window_is_built_transparent_and_its_panels_take_no_input(build):
+    shell = build(edge(DOCK, CLOCK))
+    assert len(shell.windows) == 7  # canvas, 4 strips, 2 panels
+    assert all(w.opacity == [0.0] for w in shell.windows)
+    assert [p.inputs for p in shell.panels] == [[False], [False]]
+    assert shell._fade.state == "waiting"
+
+
+def test_it_fades_in_after_the_first_re_raise_every_window_in_the_same_frames(build, loop):
+    shell = build(edge(DOCK, CLOCK))
+    assert loop.delays() == [500, READY_TIMEOUT_MS, 2000]
+    loop.run_idles()
+    assert shell._fade.state == "waiting"  # the first re-raise (a re-map: a blink) is pending
+    loop.fire(500)
+    assert [p.raised for p in shell.panels] == [1, 1]
+    assert shell._fade.state == "fading-in" and shell.faded == [shell]
+    assert [p.inputs for p in shell.panels] == [[False, True], [False, True]]
+    shell.frames(4)
+    for window in shell.windows:
+        assert window.opacity == pytest.approx([0.0, *THIRDS], abs=1e-3)
+    assert shell._fade.state == "shown" and not shell.canvas.ticker._callbacks
+    assert loop.delays() == [2000]  # the ready timeout and the finish timeout are gone
+    loop.fire(2000)  # the fallback re-raise is not waited for and changes nothing
+    assert shell._fade.state == "shown" and shell.faded == [shell]
+
+
+def test_a_monitor_without_panels_fades_in_once_the_build_returns_to_the_loop(build, loop):
+    shell = build(edge())
+    assert shell._fade.state == "waiting"  # never inside the constructor
+    loop.run_idles()
+    assert shell._fade.state == "fading-in" and shell.faded == [shell]
+
+
+def test_a_content_panel_is_measured_and_rebuilt_before_the_fade_in(build, loop):
+    shell = build(edge({**DOCK, "length": "content"}))
+    first = shell.panels[0]
+    loop.run_idles()  # measured at 200 px: rebuilt, and the new window is re-raised later
+    rebuilt = shell.panels[0]
+    assert rebuilt is not first and first.destroyed
+    assert rebuilt.opacity == [0.0] and rebuilt.inputs == [False]
+    assert shell._fade.state == "waiting" and shell._raises_pending == 2
+    loop.fire(500)
+    assert shell._fade.state == "fading-in" and rebuilt.inputs == [False, True]
+
+
+def test_the_ready_timeout_fades_in_when_nothing_reports_ready(build, loop):
+    shell = build(edge(DOCK))
+    loop.fire(READY_TIMEOUT_MS)
+    assert shell._fade.state == "fading-in" and shell.faded == [shell]
+    loop.fire(500)  # the late re-raise changes nothing
+    assert shell.faded == [shell]
+
+
+def test_with_the_re_raise_switched_off_it_fades_in_at_the_first_idle(build, loop, monkeypatch):
+    monkeypatch.setenv("EDGE_SHELL_RAISE_MS", "0")
+    shell = build(edge(DOCK))
+    loop.run_idles()
+    assert shell._fade.state == "fading-in"
+
+
+def test_the_end_of_the_last_measurement_starts_the_fade_in(build, loop, monkeypatch):
+    """No re-raise: the measurement rebuilds the panel and measures it again; only the end
+    of that second measurement may start the fade, never the first."""
+    monkeypatch.setenv("EDGE_SHELL_RAISE_MS", "0")
+    shell = build(edge({**DOCK, "length": "content"}))
+    first_measure = min(loop.idles)
+    fn, args = loop.idles.pop(first_measure)
+    fn(*args)  # measured: rebuilt at 200 px, so measured again
+    assert shell._fade.state == "waiting" and shell.measure_pending
+    loop.run_idles()  # the ready check, then the second measurement (no change)
+    assert shell._fade.state == "fading-in" and shell.faded == [shell]
+
+
+def test_a_fade_without_frames_is_finished_by_its_timeout(build, loop):
+    """A canvas that is never mapped gets no frames: the windows are made opaque anyway."""
+    shell = build(edge(DOCK))
+    loop.run_idles()
+    loop.fire(500)
+    loop.fire(50 + FINISH_MARGIN_MS)
+    assert all(w.opacity[-1] == 1.0 for w in shell.windows)
+    assert shell._fade.state == "shown"
+
+
+def test_close_mid_fade_leaves_no_tick_callback_timer_or_idle(build, loop):
+    shell = build(edge(DOCK))
+    canvas = shell.canvas
+    loop.run_idles()
+    loop.fire(500)
+    shell.frames(2)
+    shell.close()
+    assert not canvas.ticker._callbacks
+    assert loop.delays() == [2000]  # only the re-raise, a no-op after close
+    seen = [list(w.opacity) for w in (canvas, *shell.strips)]
+    shell.frames(3)
+    assert [list(w.opacity) for w in (canvas, *shell.strips)] == seen
+
+
+def test_close_while_waiting_removes_the_ready_check_and_timeout(build, loop):
+    shell = build(edge(DOCK))
+    shell.close()
+    assert loop.idles == {} and loop.delays() == [500, 2000]
+    loop.fire(500)
+    assert shell._fade.state == "done" and shell.faded == []
+
+
+def test_a_panel_added_after_the_fade_in_is_opaque_and_takes_input(build, loop):
+    shell = build(edge(DOCK))
+    shown(shell, loop)
+    config = shell.config_for(monitors=edge(DOCK, CLOCK))
+    shell.apply(config, [Change("panel-add", "HDMI-A-1", 1)])
+    added = shell.panels[1]
+    assert added.opacity == [] and added.inputs == []
+
+
+def test_a_panel_built_during_the_fade_in_starts_at_the_current_opacity(build, loop):
+    shell = build(edge(DOCK))
+    loop.run_idles()
+    loop.fire(500)
+    shell.frames(2)  # the start, then 1/3
+    config = shell.config_for(monitors=edge(DOCK, CLOCK))
+    shell.apply(config, [Change("panel-add", "HDMI-A-1", 1)])
+    added = shell.panels[1]
+    assert added.opacity == pytest.approx([1 / 3], abs=1e-3)
+    assert added.inputs == []  # input follows the fade-in, which has started
+    shell.frames(2)
+    assert added.opacity[-1] == 1.0 == shell.canvas.opacity[-1]
+
+
+def test_a_restyle_never_fades(build, loop):
+    shell = build(edge(DOCK))
+    shown(shell, loop)
+    seen = [len(w.opacity) for w in shell.windows]
+    config = shell.config_for(monitors=edge(DOCK), theme={"accent": "#112233"})
+    shell.apply(config, [Change("restyle", "HDMI-A-1")])
+    shell.frames(5)
+    assert [len(w.opacity) for w in shell.windows] == seen and shell._fade.state == "shown"
+
+
+def test_one_window_failing_its_opacity_does_not_stop_the_others(build, loop):
+    shell = build(edge(DOCK))
+
+    def gone(_value):
+        raise RuntimeError("window destroyed")
+
+    shell.strips[0].set_opacity = gone
+    loop.run_idles()
+    loop.fire(500)
+    shell.frames(4)
+    assert shell.canvas.opacity[-1] == 1.0 and shell.panels[0].opacity[-1] == 1.0
+    assert shell._fade.state == "shown"
+
+
+def test_a_build_that_fails_after_the_canvas_leaves_no_fade_behind(build, loop, monkeypatch):
+    def bad_strip(*_args, **_kwargs):
+        raise RuntimeError("strip failed")
+
+    monkeypatch.setattr(mon_mod, "FrameEdge", bad_strip)
+    canvases = []
+
+    def canvas(*args, **kwargs):
+        canvases.append(TickCanvas(*args, **kwargs))
+        return canvases[-1]
+
+    monkeypatch.setattr(mon_mod, "ShapeCanvas", canvas)
+    with pytest.raises(RuntimeError, match="strip failed"):
+        build(edge(DOCK))
+    assert canvases[0].opacity == [0.0] and canvases[0].destroyed  # never left invisible
+    assert loop.timers == {} and loop.idles == {}  # the ready timeout went with it
+    assert not canvases[0].ticker._callbacks
diff --git a/tests/test_monitor_shell.py b/tests/test_monitor_shell.py
index 3b80975..89f165b 100644
--- a/tests/test_monitor_shell.py
+++ b/tests/test_monitor_shell.py
@@ -25,6 +25,14 @@ class FakeWindow:
         self.handles = []
         self.natural = 200
         self.measured = 0
+        self.opacity = []  # every set_opacity value (spec 21)
+        self.inputs = []  # every set_input_enabled value
+
+    def set_opacity(self, value):
+        self.opacity.append(value)
+
+    def set_input_enabled(self, enabled):
+        self.inputs.append(enabled)
 
     def destroy(self):
         self.destroyed = True
@@ -114,6 +122,8 @@ def bare_shell(windows, panels=(), unregister=None):
     shell.monitor = FakeMonitor()
     shell._monitor_handlers = []
     shell._measure_id = shell._relayout_id = 0
+    shell._fade = None
+    shell._raises_pending = shell._ready_id = 0
     return shell
 
 
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `scripts/py -m pytest -q tests/test_monitor_fade.py tests/test_monitor_shell.py tests/test_edge_panel_handle.py tests/test_corner_panel.py`
Expected: `20 failed, 156 passed` (`MonitorShell` takes no `fade_ms`; `EdgePanel` has no `set_input_enabled`).

- [ ] **Step 3: Apply the implementation diff**

```diff
diff --git a/shell/edge_panel.py b/shell/edge_panel.py
index 1a10748..86253f3 100644
--- a/shell/edge_panel.py
+++ b/shell/edge_panel.py
@@ -76,6 +76,7 @@ class EdgePanel(WaylandWindow):
     """The window of an edge panel; CornerPanel is the corner one. It shows a Widget."""
 
     wants_keyboard = False
+    _input_off = False  # set_input_enabled(False): no input region at all
 
     def __init__(
         self,
@@ -249,6 +250,17 @@ class EdgePanel(WaylandWindow):
         self._last_rect = None
         self._update_input_region(self._d)
 
+    def set_input_enabled(self, enabled: bool) -> None:
+        """Take input or not (spec 21: a monitor's panels take none while it is invisible
+        before its fade-in, nor while it fades out). Kept across every re-allocate and depth
+        frame; a hover peek in progress is dropped."""
+        self._input_off = not enabled
+        if not enabled and self._hovered:
+            self._hovered = False
+            self._retarget()
+        self._last_rect = None
+        self._update_input_region(self._d)
+
     def apply_theme(self, theme: Theme) -> None:
         """A restyle: colours and the theme's handle style are redrawn in place (CSS and the
         canvas repaint the rest); geometry changes rebuild the panel."""
@@ -331,7 +343,7 @@ class EdgePanel(WaylandWindow):
     def _update_input_region(self, d: float) -> None:
         # The body (plus an invisible hover zone while collapsed, or only the handle's hit
         # target when hover is off) takes input: shell.handle.input_rects.
-        rects = tuple(self._input_rects(d))
+        rects = () if self._input_off else tuple(self._input_rects(d))
         if rects == self._last_rect:
             return
         self._last_rect = rects
diff --git a/shell/monitors.py b/shell/monitors.py
index c22264e..ea3af31 100644
--- a/shell/monitors.py
+++ b/shell/monitors.py
@@ -6,6 +6,7 @@ import itertools
 import logging
 import os
 import subprocess
+from collections.abc import Callable
 from dataclasses import replace
 
 import gi
@@ -21,6 +22,7 @@ from shell.config.diff import Change
 from shell.config.models import Config
 from shell.corner_panel import CornerPanel
 from shell.edge_panel import EdgePanel
+from shell.fade import Fade
 from shell.frame import EDGES, FrameEdge
 from shell.outputs import match_geometries, parse_kscreen, read_kscreen_json
 from shell.panel_layout import Layout, layout_monitor
@@ -122,11 +124,18 @@ class MonitorShell:
         on_layout=None,
         on_error=None,
         on_settings=None,
+        fade_ms: int = 0,
+        on_fade_in: Callable[[MonitorShell], None] | None = None,
     ):
         """`on_layout(shell)` is called after a re-layout this shell starts by itself (content
         measured, monitor geometry changed), so the app can report new layout warnings;
         `on_error(shell)` when such a re-layout raised (logged here; the app rebuilds us);
-        `on_settings()` is given to every panel (a right-click on its handle)."""
+        `on_settings()` is given to every panel (a right-click on its handle).
+
+        `fade_ms` > 0 (spec 21): every window is built at opacity 0 and the panels take no
+        input; once the monitor is ready (the first re-raise has run, no "content" measurement
+        is pending) all windows fade in together over `fade_ms`, the panels take input from
+        the start of the fade, and `on_fade_in(shell)` is called. 0: no fade (as before)."""
         self.name = name
         self.monitor = monitor
         self._register = register_window
@@ -163,6 +172,12 @@ class MonitorShell:
         self._relayout_id = 0  # pending geometry re-layout
         self._scale_warned = False
         self._monitor_handlers: list[int] = []
+        self._fade_ms = fade_ms
+        self._on_fade_in = on_fade_in or (lambda _shell: None)
+        self._fade: Fade | None = None  # made in _build, right after the canvas
+        self._input_live = fade_ms <= 0  # the panels take input (from the fade-in on)
+        self._raises_pending = 0  # first re-raises still to run: the monitor is not ready
+        self._ready_id = 0  # pending idle readiness check
         try:
             self._build(config)
         except BaseException:
@@ -175,14 +190,27 @@ class MonitorShell:
         # The canvas first: it draws the frame and corners and must stay below every panel.
         self.canvas = ShapeCanvas(monitor, theme, self._scope)
         self._track(self.canvas)
+        # One Tween on the canvas's frame clock sets every window (0 ms: no fade work at all).
+        self._fade = Fade(
+            self.canvas,
+            self._set_opacity,
+            self._fade_ms,
+            GLib.timeout_add,
+            GLib.source_remove,
+            on_start=self._faded_in,
+        )
         self.strips = [FrameEdge(edge, monitor, theme, self._scope) for edge in EDGES]
         for strip in self.strips:
             self._track(strip)
         self._sync_panels(config, theme, startup=True)
         if self.live_panels():
-            for delay in raise_delays():
-                GLib.timeout_add(delay, self._raise_panels)
+            for i, delay in enumerate(raise_delays()):
+                first = i == 0  # the fallback re-raise is not waited for
+                self._raises_pending += first
+                GLib.timeout_add(delay, self._raise_panels, first)
         self._monitor_handlers.append(monitor.connect("notify::geometry", self._on_geometry))
+        if self._fade.state == "waiting":  # checked once the build has returned to the loop
+            self._ready_id = GLib.idle_add(self._ready_idle)
 
     def live_panels(self) -> list[EdgePanel]:
         return [p for p in self.panels if p is not None]
@@ -320,6 +348,7 @@ class MonitorShell:
                 self._on_error(self)
             except Exception:
                 log.exception("handling the measurement failure of %s failed", self.name)
+        self._check_ready()
         return False
 
     # ---- monitor geometry -----------------------------------------------------------------
@@ -405,9 +434,12 @@ class MonitorShell:
             self._failed[index] = (_entry_key(req), message)
             return None
         panel.scene_key = key
+        if not self._input_live:  # invisible until the fade-in: no input either
+            panel.set_input_enabled(False)
         self._track(panel)
         if raise_later:  # created after startup: re-raise it like the first ones
             for delay in raise_delays()[:1]:
+                self._raises_pending += 1
                 GLib.timeout_add(delay, self._raise_one, panel)
         return panel
 
@@ -417,22 +449,63 @@ class MonitorShell:
         self.canvas.remove_panel(panel.scene_key)
         self._destroy(panel)
 
-    def _raise_panels(self) -> bool:
-        """Re-map the live panels so they stack above the canvas (see RAISE_DELAY_MS)."""
+    def _raise_panels(self, first: bool = False) -> bool:
+        """Re-map the live panels so they stack above the canvas (see RAISE_DELAY_MS). The
+        `first` one is waited for by the fade-in: a re-map is a visible blink."""
         if not self._closed:
             for panel in self.live_panels():
                 panel.raise_to_top()
+        if first:
+            self._raised()
         return False
 
     def _raise_one(self, panel: EdgePanel) -> bool:
         # The panel may have been rebuilt or removed during the delay: only raise live ones.
         if panel in self.panels:
             panel.raise_to_top()
+        self._raised()
+        return False
+
+    # ---- fade (spec 21) -------------------------------------------------------------------
+    def _raised(self) -> None:
+        self._raises_pending = max(0, self._raises_pending - 1)
+        self._check_ready()
+
+    def _ready_idle(self) -> bool:
+        self._ready_id = 0
+        self._check_ready()
         return False
 
+    def _check_ready(self) -> None:
+        """Fade in once nothing that re-maps or resizes a window is pending (Fade.ready only
+        acts while waiting; its own timeout fades in anyway)."""
+        if self._closed or self._fade is None or self._raises_pending or self._measure_id:
+            return
+        self._fade.ready()
+
+    def _faded_in(self) -> None:
+        """The fade-in starts: the panels take input from now on (what is seen is clicked)."""
+        self._input_live = True
+        for panel in self.live_panels():
+            panel.set_input_enabled(True)
+        self._on_fade_in(self)
+
+    def _set_opacity(self, value: float) -> None:
+        """One frame of the fade: every window of the monitor, in the same tick."""
+        for window in self.windows:
+            self._apply_opacity(window, value)
+
+    def _apply_opacity(self, window, value: float) -> None:
+        try:
+            window.set_opacity(value)  # GTK 3 paints a toplevel's opacity as a group alpha
+        except Exception:  # one window going away must not stop the others
+            log.debug("could not set the opacity of a window on %s", self.name, exc_info=True)
+
     # ---- windows --------------------------------------------------------------------------
     def _track(self, window) -> None:
         self.windows.append(window)
+        if self._fade is not None and self._fade.state != "shown":
+            self._apply_opacity(window, self._fade.value)  # before its first frame is drawn
         self._register(window)
         self._check_monitor(window)
 
@@ -479,10 +552,12 @@ class MonitorShell:
 
     def close(self) -> None:
         self._closed = True
-        for source in (self._measure_id, self._relayout_id):
+        if self._fade is not None:
+            self._fade.cancel()  # before the canvas (its frame clock) is destroyed
+        for source in (self._measure_id, self._relayout_id, self._ready_id):
             if source:
                 GLib.source_remove(source)
-        self._measure_id = self._relayout_id = 0
+        self._measure_id = self._relayout_id = self._ready_id = 0
         for handler in self._monitor_handlers:
             try:
                 self.monitor.disconnect(handler)
```

- [ ] **Step 4: Run the tests to see them pass**

Run: the command of Step 2. Expected: `176 passed`.

- [ ] **Step 5: VERIFY**. Expected: `2768 passed`.

- [ ] **Step 6: Reviewer mutations** (measured): `_track` no longer applying the fade's value (`test_every_window_is_built_transparent_and_its_panels_take_no_input`); `_raises_pending += first` -> `+= 1` (waits for the 2000 ms fallback: `test_it_fades_in_after_the_first_re_raise_every_window_in_the_same_frames`); `_measure` without `_check_ready()` (`test_the_end_of_the_last_measurement_starts_the_fade_in`); `_faded_in` not enabling input (`test_it_fades_in_after_the_first_re_raise_...`); `close()` not cancelling the fade (`test_close_mid_fade_leaves_no_tick_callback_timer_or_idle`); `_apply_opacity` catching only `ZeroDivisionError` (`test_one_window_failing_its_opacity_does_not_stop_the_others`); no ready idle after the build (`test_a_monitor_without_panels_fades_in_once_the_build_returns_to_the_loop`); `_new_panel` not turning input off (`test_every_window_is_built_transparent_...`); `_update_input_region` ignoring `_input_off` (`test_with_input_off_a_panel_takes_none_at_any_depth_until_it_is_on_again`).

- [ ] **Step 7: Commit**

```bash
git add shell/monitors.py shell/edge_panel.py tests/test_monitor_fade.py tests/test_monitor_shell.py tests/test_edge_panel_handle.py tests/test_corner_panel.py
git commit -m "feat(shell): a monitor's windows fade in once it is ready" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Fade out when a monitor is turned off, and on Ctrl+C or SIGTERM

**Files:**
- Modify: `shell/monitors.py` (`_detached`; `_on_geometry`, `_raise_panels`, `_raise_one`, `_check_ready` skip a detached shell; `fade_state`, `fading_out`, `detach`, `fade_out`, `_faded_out`, `_call_done`; `close` split into `_cancel_sources` and `_disconnect_monitor`), `shell/plan.py` (`has_windows`), `shell/app.py` (`QUIT_MARGIN_MS`, `unix_signal_add`, the new state, `sync_monitors`, `_close_shell`, `_fade_away`, `_retire`, `_gone`, `_fade_ms`, `_open_shell` passes `fade_ms`, `_sync_once`, `reload`, `_reload`'s rebuild loop, `run`, the quit section)
- Test: `tests/test_monitor_fade.py`, `tests/test_app_sync.py` (`FakeShell` learns the fade; the D-Bus test also replaces `_watch_quit_signals`), `tests/test_plan.py`, `tests/test_monitor_shell.py` (`bare_shell._detached`)

**Interfaces:**
- Consumes: `MonitorShell(..., fade_ms=, on_fade_in=)`, `Fade.fade_out`, `Fade.state` (Tasks 2-3).
- Produces:
  - `MonitorShell.fade_state -> str` ("done" once closed), `MonitorShell.fading_out -> bool`, `MonitorShell.detach() -> None`, `MonitorShell.fade_out(duration_ms: int, on_done: Callable[[MonitorShell], None]) -> None`.
  - `shell.plan.has_windows(config: Config, name: str) -> bool`.
  - `shell.app.QUIT_MARGIN_MS = 250`; `shell.app.unix_signal_add(priority: int, signum: int, handler, data) -> int`.
  - `EdgeShellApp._leaving: dict[str, MonitorShell]`, `_close_shell(name: str, fade: bool = True)`, `_fade_away(name, shell)`, `_retire(name)`, `_gone(shell)`, `_fade_ms(name) -> int`, `_watch_quit_signals()`, `_on_quit_signal(signum: int) -> bool`, `_quit_timeout() -> bool`, `_quit_now()`; `run()` returns `_exit_code` (0, or 128 + the signal).
  - `tests/test_app_sync.py`: `FakeShell(..., fade_ms=0, on_fade_in=None)` with `fade_state`, `fading_out`, `detach()`, `fade_out(ms, on_done)` and the helpers `fade_in()` (the real shell's fade-in starts) and `faded_out()` (its fade-out ended); `FakeShell.faded` records `(name, ms)`; fixture `timers`; class `QuitRecorder`.

- [ ] **Step 1: Apply the test diff**

```diff
diff --git a/tests/test_app_sync.py b/tests/test_app_sync.py
index 5b19886..1da5f1e 100644
--- a/tests/test_app_sync.py
+++ b/tests/test_app_sync.py
@@ -14,6 +14,7 @@ class FakeShell:
     opened: list = []
     closed: list = []
     applied: list = []
+    faded: list = []  # (name, ms) of every fade_out call
     fail_apply: set = set()
     layout_warnings: list = []
     build_failures: list = []
@@ -30,18 +31,55 @@ class FakeShell:
         on_layout=None,
         on_error=None,
         on_settings=None,
+        fade_ms=0,
+        on_fade_in=None,
     ):
         self.name = name
         self.monitor = monitor
         self.on_layout = on_layout
         self.on_error = on_error
         self.on_settings = on_settings
+        self.fade_ms = fade_ms
+        self.on_fade_in = on_fade_in
+        self.fade_state = "waiting" if fade_ms > 0 else "shown"  # as MonitorShell
+        self.on_done = None
+        self.detached = False
         if name in FakeShell.fail_open:
             raise RuntimeError("cannot build")
         FakeShell.opened.append(name)
 
     def close(self):
         FakeShell.closed.append(self.name)
+        self.fade_state = "done"
+
+    @property
+    def fading_out(self):
+        return self.fade_state in ("fading-out", "done")
+
+    def detach(self):
+        self.detached = True
+
+    def fade_out(self, ms, on_done):
+        """MonitorShell.fade_out: closed at once with 0 ms or while still invisible."""
+        FakeShell.faded.append((self.name, ms))
+        if ms <= 0 or self.fade_state in ("waiting", "done"):
+            self.close()
+            on_done(self)
+            return
+        self.detached = True
+        self.fade_state = "fading-out"
+        self.on_done = on_done
+
+    def fade_in(self):
+        """Test helper: the real shell became ready and starts its fade-in."""
+        self.fade_state = "shown"
+        if self.on_fade_in is not None:
+            self.on_fade_in(self)
+
+    def faded_out(self):
+        """Test helper: the real shell's fade-out reached 0 and it closed itself."""
+        self.close()
+        self.on_done(self)
 
     def apply(self, config, changes):
         if self.name in FakeShell.fail_apply:
@@ -56,6 +94,7 @@ def _reset_fake_shell(monkeypatch):
         ("opened", []),
         ("closed", []),
         ("applied", []),
+        ("faded", []),
         ("fail_apply", set()),
         ("fail_open", set()),
         ("layout_warnings", []),
@@ -378,6 +417,7 @@ def test_the_fabric_dbus_client_is_off(env, monkeypatch):
     monkeypatch.setattr(app, "start_watching", lambda: None)
     monkeypatch.setattr(app, "watch_displays", lambda: None)
     monkeypatch.setattr(app_mod.signal, "signal", lambda *_a: None)
+    monkeypatch.setattr(app, "_watch_quit_signals", lambda: None)
     assert app.run() == 0
     ((args, kwargs),) = made
     assert args[0] == app_mod.APP_NAME and kwargs == {"open_client": False}
@@ -1067,3 +1107,180 @@ def test_a_plasma_mode_monitor_that_is_not_connected_is_still_reported(
     mapping["HDMI-A-1"] = object()
     app.sync_monitors()
     assert notes and "config monitors: DP-1" in notes[0][1]
+
+
+# ---- the fade (spec 21) ---------------------------------------------------------------
+
+
+class QuitRecorder:
+    def __init__(self):
+        self.quits = 0
+
+    def quit(self):
+        self.quits += 1
+
+
+@pytest.fixture
+def timers(monkeypatch):
+    """GLib.timeout_add / source_remove of shell.app, recorded: {id: (ms, fn)}."""
+    pending: dict = {}
+    ids = iter(range(100, 1000))
+
+    def add(ms, fn, *args):
+        timer = next(ids)
+        pending[timer] = (ms, fn)
+        return timer
+
+    monkeypatch.setattr(app_mod.GLib, "timeout_add", add)
+    monkeypatch.setattr(app_mod.GLib, "source_remove", lambda t: pending.pop(t))
+    return pending
+
+
+def test_shells_open_with_their_monitors_fade_and_none_while_measuring(env, make_config):
+    app, mapping = env
+    mapping["HDMI-A-1"] = object()
+    app.store.config = make_config(monitors={"HDMI-A-1": {"shell": "edge"}})
+    app.sync_monitors()
+    assert app.shells["HDMI-A-1"].fade_ms == 50  # the default
+    app.store.config = make_config(
+        monitors={"HDMI-A-1": {"shell": "edge", "theme": {"fade_ms": 300}}}
+    )
+    mapping["HDMI-A-1"] = object()  # replugged: reopened with the monitor's own fade
+    app.sync_monitors()
+    assert app.shells["HDMI-A-1"].fade_ms == 300
+    stats = app_mod.EdgeShellApp(app.store, stats_seconds=2)  # --stats: never a fade
+    stats.sync_monitors()
+    assert stats.shells["HDMI-A-1"].fade_ms == 0
+
+
+def test_disabling_a_monitor_fades_it_out_and_closes_it_when_done(renv):
+    app, store, errors, _, make_config = renv
+    shell = app.shells["HDMI-A-1"]
+    shell.fade_in()
+    store.pending = make_config(monitors={"HDMI-A-1": mon("plasma")})
+    app.reload()
+    assert FakeShell.faded == [("HDMI-A-1", 50)] and FakeShell.closed == []
+    assert app.shells == {} and app._leaving == {"HDMI-A-1": shell}
+    shell.faded_out()
+    assert FakeShell.closed == ["HDMI-A-1"] and app._leaving == {} and errors == []
+
+
+def test_the_fade_out_uses_the_fade_of_the_config_that_turns_it_off(renv):
+    app, store, _, _, make_config = renv
+    app.shells["HDMI-A-1"].fade_in()
+    store.pending = make_config(
+        monitors={"HDMI-A-1": {"shell": "plasma", "theme": {"fade_ms": 300}}}
+    )
+    app.reload()
+    assert FakeShell.faded == [("HDMI-A-1", 300)]
+
+
+def test_with_fade_0_a_disabled_monitor_closes_at_once_as_before(renv):
+    app, store, _, _, make_config = renv
+    app.shells["HDMI-A-1"].fade_in()
+    store.pending = make_config(theme={"fade_ms": 0}, monitors={"HDMI-A-1": mon("plasma")})
+    app.reload()
+    assert FakeShell.faded == [("HDMI-A-1", 0)] and FakeShell.closed == ["HDMI-A-1"]
+    assert app.shells == {} and app._leaving == {}
+
+
+def test_an_unplugged_or_replaced_monitor_is_closed_at_once_without_a_fade(env):
+    app, mapping = env
+    mapping["HDMI-A-1"] = object()
+    app.sync_monitors()
+    app.shells["HDMI-A-1"].fade_in()
+    mapping["HDMI-A-1"] = object()  # a new Gdk monitor: the old one is gone
+    app.sync_monitors()
+    assert FakeShell.faded == [] and FakeShell.closed == ["HDMI-A-1"]
+    del mapping["HDMI-A-1"]
+    mapping["DP-1"] = object()  # unplugged (DP-1 keeps the mapping non-empty)
+    app.sync_monitors()
+    assert FakeShell.faded == [] and FakeShell.closed == ["HDMI-A-1", "HDMI-A-1"]
+
+
+def test_run_takes_sigint_and_sigterm_through_glib(env, monkeypatch):
+    app, _ = env
+    added = []
+    monkeypatch.setattr(app_mod, "unix_signal_add", lambda *a: added.append(a))
+    app._watch_quit_signals()
+    high, signals = app_mod.GLib.PRIORITY_HIGH, app_mod.signal
+    sigint, sigterm = signals.SIGINT, signals.SIGTERM
+    assert added == [
+        (high, sigint, app._on_quit_signal, sigint),
+        (high, sigterm, app._on_quit_signal, sigterm),
+    ]
+
+
+def test_a_quit_signal_fades_every_shell_out_then_quits(renv, timers):
+    app, _, _, _, _ = renv
+    app.app = QuitRecorder()
+    shell = app.shells["HDMI-A-1"]
+    shell.fade_in()
+    assert app._on_quit_signal(app_mod.signal.SIGINT) is True  # the handler stays
+    assert FakeShell.faded == [("HDMI-A-1", 50)] and app.app.quits == 0
+    assert [ms for ms, _ in timers.values()] == [50 + app_mod.QUIT_MARGIN_MS]
+    shell.faded_out()
+    assert app.app.quits == 1 and timers == {}  # the bound is dropped
+    assert app._exit_code == 130
+
+
+def test_the_quit_waits_at_most_the_fade_plus_the_margin(renv, timers):
+    app, _, _, _, _ = renv
+    app.app = QuitRecorder()
+    app.shells["HDMI-A-1"].fade_in()
+    app._on_quit_signal(app_mod.signal.SIGTERM)
+    ((_, fn),) = timers.values()
+    assert fn() is False  # the fade never finished (no frames): quit anyway
+    assert app.app.quits == 1 and app._exit_code == 143
+
+
+def test_a_second_quit_signal_quits_at_once(renv, timers):
+    app, _, _, _, _ = renv
+    app.app = QuitRecorder()
+    app.shells["HDMI-A-1"].fade_in()
+    app._on_quit_signal(app_mod.signal.SIGINT)
+    app._on_quit_signal(app_mod.signal.SIGINT)
+    assert app.app.quits == 1 and timers == {}
+
+
+def test_without_any_fade_a_quit_signal_quits_at_once(renv, timers):
+    app, store, _, _, make_config = renv
+    store.config = make_config(theme={"fade_ms": 0}, monitors={"HDMI-A-1": mon()})
+    app.app = QuitRecorder()
+    app.shells["HDMI-A-1"].fade_in()
+    app._on_quit_signal(app_mod.signal.SIGINT)
+    assert FakeShell.closed == ["HDMI-A-1"] and app.app.quits == 1 and timers == {}
+
+
+def test_a_monitor_without_a_fade_never_cuts_the_others_fade_short(env, make_config, timers):
+    """HDMI-A-1 has fade 0 and closes inside the quit loop: the quit must still wait for
+    HDMI-A-2's fade (it is not even started yet when HDMI-A-1 is gone)."""
+    app, mapping = env
+    app.store.config = make_config(
+        monitors={
+            "HDMI-A-1": {"shell": "edge", "theme": {"fade_ms": 0}},
+            "HDMI-A-2": {"shell": "edge"},
+        }
+    )
+    mapping.update({"HDMI-A-1": object(), "HDMI-A-2": object()})
+    app.sync_monitors()
+    for shell in app.shells.values():
+        shell.fade_in()
+    second = app.shells["HDMI-A-2"]
+    app.app = QuitRecorder()
+    app._on_quit_signal(app_mod.signal.SIGINT)
+    assert FakeShell.faded == [("HDMI-A-1", 0), ("HDMI-A-2", 50)] and app.app.quits == 0
+    second.faded_out()
+    assert app.app.quits == 1
+
+
+def test_reloads_and_hot_plug_syncs_are_ignored_while_quitting(renv, timers):
+    app, store, _, mapping, make_config = renv
+    app.app = QuitRecorder()
+    app.shells["HDMI-A-1"].fade_in()
+    app._on_quit_signal(app_mod.signal.SIGINT)
+    store.pending = make_config(monitors={"HDMI-A-1": mon()})
+    app.reload()
+    app._sync_timers = [7]
+    app._sync_once(7)
+    assert FakeShell.opened == [] and app.shells == {}  # nothing reopened
diff --git a/tests/test_monitor_fade.py b/tests/test_monitor_fade.py
index b1f76dd..587b43a 100644
--- a/tests/test_monitor_fade.py
+++ b/tests/test_monitor_fade.py
@@ -306,3 +306,104 @@ def test_a_build_that_fails_after_the_canvas_leaves_no_fade_behind(build, loop,
     assert canvases[0].opacity == [0.0] and canvases[0].destroyed  # never left invisible
     assert loop.timers == {} and loop.idles == {}  # the ready timeout went with it
     assert not canvases[0].ticker._callbacks
+
+
+# ---- fade-out (Task 4) ----------------------------------------------------------------
+
+
+def test_fade_out_fades_every_window_then_closes_and_calls_back_once(build, loop):
+    shell = build(edge(DOCK))
+    shown(shell, loop)
+    canvas, panel, strips = shell.canvas, shell.panels[0], list(shell.strips)
+    done = []
+    shell.fade_out(50, done.append)
+    assert all(s.destroyed for s in strips) and shell.strips == []  # the zones go at once
+    assert panel.inputs[-1] is False and not canvas.destroyed  # clicks go through it now
+    shell.frames(4)
+    out = canvas.opacity[-4:]
+    assert out == pytest.approx(list(reversed(THIRDS)), abs=1e-3)  # from 1 down to 0
+    assert panel.opacity[-4:] == out  # the same frames for every window
+    assert canvas.destroyed and panel.destroyed and done == [shell]
+    assert shell.fade_state == "done" and not canvas.ticker._callbacks
+    shell.frames(3)
+    assert done == [shell]
+
+
+def test_fade_out_with_zero_ms_closes_at_once_as_before(build, loop):
+    shell = build(edge(DOCK))
+    shown(shell, loop)
+    panel, seen = shell.panels[0], len(shell.canvas.opacity)
+    done = []
+    shell.fade_out(0, done.append)
+    assert panel.destroyed and shell.canvas.destroyed and done == [shell]
+    assert len(shell.canvas.opacity) == seen and panel.inputs == [False, True]
+
+
+def test_a_shell_that_was_never_visible_is_closed_at_once(build, loop):
+    shell = build(edge(DOCK))  # still waiting for its fade-in
+    done = []
+    shell.fade_out(50, done.append)
+    assert shell.canvas.destroyed and done == [shell] and shell.faded == []
+    assert loop.idles == {} and loop.delays() == [500, 2000]  # only no-op re-raises left
+
+
+def test_fade_out_mid_fade_in_goes_down_from_where_it_is(build, loop):
+    shell = build(edge(DOCK))
+    loop.run_idles()
+    loop.fire(500)
+    shell.frames(2)  # the start, then 1/3
+    now = shell.canvas.opacity[-1]
+    shell.fade_out(50, lambda _s: None)
+    shell.frames(6)
+    after = shell.canvas.opacity[shell.canvas.opacity.index(now) + 1 :]
+    assert max(after) <= now + 1e-9 and after[-1] == 0.0  # never a jump up
+    assert shell.canvas.destroyed
+
+
+def test_a_second_fade_out_is_ignored(build, loop):
+    shell = build(edge(DOCK))
+    shown(shell, loop)
+    first, second = [], []
+    shell.fade_out(50, first.append)
+    shell.fade_out(50, second.append)
+    shell.frames(5)
+    assert first == [shell] and second == []
+
+
+def test_a_shell_built_without_a_fade_still_fades_out_when_asked(build, loop):
+    """fade_ms went from 0 to 50 between the monitor's start and its turn-off."""
+    shell = build(edge(DOCK), fade_ms=0)
+    loop.fire(500)
+    done = []
+    shell.fade_out(50, done.append)
+    shell.frames(4)
+    # the first value is the fade's start at the opacity it has (1: never set before)
+    assert shell.canvas.opacity == pytest.approx([1.0, *reversed(THIRDS)], abs=1e-3)
+    assert shell.canvas.destroyed and done == [shell]
+
+
+def test_a_detached_shell_no_longer_re_raises_re_lays_out_or_measures(build, loop):
+    shell = build(edge({**DOCK, "length": "content"}))
+    monitor, panel = shell.monitor, shell.panels[0]
+    shell.detach()
+    assert loop.idles == {}  # the measurement and the ready check are dropped
+    assert monitor.handlers == {}  # the geometry is no longer watched
+    loop.fire(500)
+    loop.fire(2000)
+    assert panel.raised == 0 and not panel.destroyed  # never re-mapped: a re-map blinks
+    assert shell._fade.state == "waiting"  # never shown by the late re-raise either
+    shell.detach()  # once only
+    shell.close()
+    assert panel.destroyed
+
+
+def test_a_failing_fade_out_callback_is_logged_and_the_shell_is_closed(build, loop, caplog):
+    shell = build(edge(DOCK))
+    shown(shell, loop)
+
+    def boom(_shell):
+        raise RuntimeError("callback failed")
+
+    shell.fade_out(50, boom)
+    shell.frames(5)
+    assert shell.canvas.destroyed and "the fade-out callback of HDMI-A-1 failed" in caplog.text
diff --git a/tests/test_monitor_shell.py b/tests/test_monitor_shell.py
index 89f165b..50c75e4 100644
--- a/tests/test_monitor_shell.py
+++ b/tests/test_monitor_shell.py
@@ -124,6 +124,7 @@ def bare_shell(windows, panels=(), unregister=None):
     shell._measure_id = shell._relayout_id = 0
     shell._fade = None
     shell._raises_pending = shell._ready_id = 0
+    shell._detached = False
     return shell
 
 
diff --git a/tests/test_plan.py b/tests/test_plan.py
index 4d7d464..40cb464 100644
--- a/tests/test_plan.py
+++ b/tests/test_plan.py
@@ -1,4 +1,17 @@
-from shell.plan import desired_shells, reconcile
+from shell.plan import desired_shells, has_windows, reconcile
+
+
+def test_has_windows_is_edge_or_both(make_config):
+    cfg = make_config(
+        monitors={n: {"shell": n.lower()} for n in ("EDGE", "BOTH", "PLASMA", "NONE")}
+    )
+    assert [has_windows(cfg, n) for n in ("EDGE", "BOTH", "PLASMA", "NONE", "DP-9")] == [
+        True,
+        True,
+        False,
+        False,
+        False,  # unlisted: plasma
+    ]
 
 
 def test_only_connected_edge_monitors(make_config):  # Review Focus 2
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `scripts/py -m pytest -q tests/test_plan.py`
Expected: an `ImportError` (`cannot import name 'has_windows'`).
Run: `scripts/py -m pytest -q tests/test_monitor_fade.py tests/test_app_sync.py tests/test_monitor_shell.py`
Expected: `20 failed, 164 passed`.

- [ ] **Step 3: Apply the implementation diff**

```diff
diff --git a/shell/app.py b/shell/app.py
index aca2cf1..a230439 100644
--- a/shell/app.py
+++ b/shell/app.py
@@ -36,6 +36,20 @@ log = logging.getLogger(__name__)
 
 APP_NAME = "edge-shell"
 EXERCISE_MS = 300  # --stats toggles every panel this often: a 280 ms tween plus a frame
+# A quit signal fades every monitor out first (spec 21), waiting at most the longest fade_ms
+# plus this; a second signal quits at once.
+QUIT_MARGIN_MS = 250
+
+
+def unix_signal_add(priority: int, signum: int, handler, data) -> int:
+    """GLib's Unix signal source: GLibUnix.signal_add (GLib 2.80+; this machine: 2.90), else
+    the older GLib.unix_signal_add. `handler(data)` runs in the main loop."""
+    try:
+        gi.require_version("GLibUnix", "2.0")
+        from gi.repository import GLibUnix
+    except (ValueError, ImportError):
+        return GLib.unix_signal_add(priority, signum, handler, data)
+    return GLibUnix.signal_add(priority, signum, handler, data)
 
 
 def _already_running() -> bool:
@@ -59,6 +73,13 @@ class EdgeShellApp:
         self._relayout_rebuilt: set[str] = set()  # rebuilt after a failed re-layout, until a reload
         self._monitors_reported: list[str] = []  # the unknown configured names last notified
         self._seen_connected: set[str] = set()  # every monitor name connected this session
+        # Shells fading out (spec 21), at most one per monitor: out of `shells`, so nothing
+        # else (reports, CSS, reloads) sees them; closed by their fade or by _retire.
+        self._leaving: dict[str, MonitorShell] = {}
+        self._quitting = False  # a quit signal came: fading out, then quit
+        self._quit_timer = 0
+        self._quit_sent = False
+        self._exit_code = 0
         self._log_deprecated(store.config)
 
     @property
@@ -95,7 +116,8 @@ class EdgeShellApp:
         close, open_ = plan.reconcile(active, desired)
         for name in close:
             log.info("closing Edge Shell on %s", name)
-            self._close_shell(name)
+            # Faded out while its monitor is still there; unplugged or replaced: closed now.
+            self._close_shell(name, fade=connected.get(name) is self.shells[name].monitor)
         for name in open_:
             self._open_shell(name, desired[name])
         if close or open_:
@@ -122,9 +144,44 @@ class EdgeShellApp:
             log.warning("monitor names in the config are not connected (%s)", report)
             self._notify(MONITOR_TITLE, f"{report}\nUse the connected names in the config.")
 
-    def _close_shell(self, name: str) -> None:
+    def _close_shell(self, name: str, fade: bool = True) -> None:
+        """Take `name`'s shell out of `shells`. With `fade` it fades out (spec 21; at once
+        with fade_ms 0) and is closed when done; without (its monitor is gone), now."""
         self._forget_reports(name)
-        self.shells.pop(name).close()
+        shell = self.shells.pop(name)
+        if fade:
+            self._fade_away(name, shell)
+        else:
+            self._retire(name)
+            shell.close()
+
+    def _fade_away(self, name: str, shell: MonitorShell) -> None:
+        self._retire(name)  # at most one leaving shell per monitor: an older one goes now
+        self._leaving[name] = shell
+        shell.fade_out(self._fade_ms(name), self._gone)
+
+    def _retire(self, name: str) -> None:
+        """Close `name`'s leaving shell now (its fade, if any, is dropped)."""
+        shell = self._leaving.pop(name, None)
+        if shell is not None:
+            try:
+                shell.close()
+            except Exception:
+                log.exception("closing the leaving shell of %s failed", name)
+
+    def _gone(self, shell: MonitorShell) -> None:
+        """A leaving shell finished its fade-out and closed itself."""
+        if self._leaving.get(shell.name) is shell:
+            del self._leaving[shell.name]
+        if self._quitting and not self._leaving and not self.shells:
+            self._quit_now()
+
+    def _fade_ms(self, name: str) -> int:
+        """The fade of `name`'s next fade in or out (spec 21): the config in effect now (a
+        change of fade_ms applies from the next fade on). 0 while --stats measures."""
+        if self._stats_seconds:
+            return 0
+        return self.config.theme_for(name).fade_ms
 
     def _forget_reports(self, name: str) -> None:
         """A closed shell's notified lists are stale: the monitor, plugged in again with the
@@ -143,6 +200,7 @@ class EdgeShellApp:
             on_layout=lambda shell, n=name: self._report_layout(n, shell),
             on_error=lambda shell, n=name: self._relayout_failed(n, shell),
             on_settings=self.open_settings,
+            fade_ms=self._fade_ms(name),
         )
         if not shell.measure_pending:  # else the measurement's on_layout reports, with real sizes
             self._report_layout(name, shell)
@@ -171,7 +229,8 @@ class EdgeShellApp:
     def _sync_once(self, timer: int) -> bool:
         if timer in self._sync_timers:
             self._sync_timers.remove(timer)
-        self.sync_monitors()
+        if not self._quitting:  # never reopen what the quit is fading out
+            self.sync_monitors()
         return GLib.SOURCE_REMOVE
 
     def css(self) -> str:
@@ -196,6 +255,8 @@ class EdgeShellApp:
 
     def reload(self) -> None:
         # Runs from a GLib/watcher callback: never let an exception escape half-applied.
+        if self._quitting:  # never reopen what the quit is fading out
+            return
         try:
             self._reload()
         except Exception:
@@ -215,8 +276,9 @@ class EdgeShellApp:
         kinds = ", ".join(c.kind for c in changes) or "none"
         log.info("config reloaded: %d change(s): %s", len(changes), kinds)
         rebuild = {c.monitor for c in changes if c.kind == "rebuild-monitor"}
-        for name in rebuild & set(self.shells):
-            self._close_shell(name)
+        for name in sorted(rebuild & set(self.shells)):
+            # turned off (plasma / none): it fades out; else it is rebuilt from the new config
+            self._close_shell(name, fade=not plan.has_windows(new, name))
         # Shells opened here are built from the new config already: never apply onto them.
         _, opened = self.sync_monitors()
         grouped: dict[str, list] = defaultdict(list)
@@ -382,7 +444,10 @@ class EdgeShellApp:
         self.app.hold()  # stay alive even with no windows (e.g. all monitors set to plasma)
         self.start_watching()
         self.watch_displays()
-        signal.signal(signal.SIGINT, signal.SIG_DFL)  # Ctrl+C quits
+        # Python's own SIGINT handler stays the default, so PyGObject installs no fallback of
+        # its own that would quit without the fade; GLib's handler below takes the signal.
+        signal.signal(signal.SIGINT, signal.SIG_DFL)
+        self._watch_quit_signals()  # Ctrl+C and SIGTERM fade out, then quit
         if self.recorder is not None:
             GLib.timeout_add(EXERCISE_MS, self._exercise)
             GLib.timeout_add(int(self._stats_seconds * 1000), self._stop)
@@ -391,7 +456,50 @@ class EdgeShellApp:
         if self.recorder is not None:
             wall, cpu = time.perf_counter() - wall0, time.process_time() - cpu0
             print("\n".join(self.recorder.report(wall, cpu)))
-        return 0
+        return self._exit_code
+
+    # ---- quit (spec 21) ---------------------------------------------------------------
+    def _watch_quit_signals(self) -> None:
+        for signum in (signal.SIGINT, signal.SIGTERM):
+            unix_signal_add(GLib.PRIORITY_HIGH, signum, self._on_quit_signal, signum)
+
+    def _on_quit_signal(self, signum: int) -> bool:
+        """Fade every monitor out, then quit: when the last fade is done, at the latest the
+        longest fade_ms + QUIT_MARGIN_MS later. A second signal quits at once. The exit status
+        is the shell's usual one for a signal (128 + its number: 130 for Ctrl+C)."""
+        self._exit_code = 128 + signum
+        if self._quitting:
+            log.info("second quit signal: quitting now")
+            self._quit_now()
+            return GLib.SOURCE_CONTINUE
+        self._quitting = True
+        names = sorted({*self.shells, *self._leaving})
+        wait = max((self._fade_ms(name) for name in names), default=0)
+        log.info("quit signal %d: fading out %s", signum, ", ".join(names) or "nothing")
+        for name in sorted(self.shells):
+            try:
+                self._close_shell(name)
+            except Exception:
+                log.exception("fading out %s for the quit failed", name)
+        if self._leaving:
+            self._quit_timer = GLib.timeout_add(wait + QUIT_MARGIN_MS, self._quit_timeout)
+        else:
+            self._quit_now()
+        return GLib.SOURCE_CONTINUE
+
+    def _quit_timeout(self) -> bool:
+        self._quit_timer = 0
+        log.info("the fade-out did not finish in time: quitting")
+        self._quit_now()
+        return GLib.SOURCE_REMOVE
+
+    def _quit_now(self) -> None:
+        if self._quit_timer:
+            GLib.source_remove(self._quit_timer)
+            self._quit_timer = 0
+        if self.app is not None and not self._quit_sent:
+            self._quit_sent = True
+            self.app.quit()
 
     def _exercise(self) -> bool:
         """--stats: keep every panel animating (collapse <-> extend)."""
diff --git a/shell/monitors.py b/shell/monitors.py
index ea3af31..eae189b 100644
--- a/shell/monitors.py
+++ b/shell/monitors.py
@@ -178,6 +178,7 @@ class MonitorShell:
         self._input_live = fade_ms <= 0  # the panels take input (from the fade-in on)
         self._raises_pending = 0  # first re-raises still to run: the monitor is not ready
         self._ready_id = 0  # pending idle readiness check
+        self._detached = False  # leaving (detach): no longer follows the config or monitor
         try:
             self._build(config)
         except BaseException:
@@ -354,7 +355,7 @@ class MonitorShell:
     # ---- monitor geometry -----------------------------------------------------------------
     def _on_geometry(self, *_args) -> None:
         """The monitor's resolution (or position) changed: re-layout once it settles."""
-        if self._closed:
+        if self._closed or self._detached:
             return
         if self._relayout_id:
             GLib.source_remove(self._relayout_id)
@@ -452,7 +453,7 @@ class MonitorShell:
     def _raise_panels(self, first: bool = False) -> bool:
         """Re-map the live panels so they stack above the canvas (see RAISE_DELAY_MS). The
         `first` one is waited for by the fade-in: a re-map is a visible blink."""
-        if not self._closed:
+        if not self._closed and not self._detached:  # a leaving shell is never re-mapped
             for panel in self.live_panels():
                 panel.raise_to_top()
         if first:
@@ -461,7 +462,7 @@ class MonitorShell:
 
     def _raise_one(self, panel: EdgePanel) -> bool:
         # The panel may have been rebuilt or removed during the delay: only raise live ones.
-        if panel in self.panels:
+        if panel in self.panels and not self._detached:
             panel.raise_to_top()
         self._raised()
         return False
@@ -479,7 +480,9 @@ class MonitorShell:
     def _check_ready(self) -> None:
         """Fade in once nothing that re-maps or resizes a window is pending (Fade.ready only
         acts while waiting; its own timeout fades in anyway)."""
-        if self._closed or self._fade is None or self._raises_pending or self._measure_id:
+        if self._closed or self._detached or self._fade is None:
+            return
+        if self._raises_pending or self._measure_id:
             return
         self._fade.ready()
 
@@ -490,6 +493,64 @@ class MonitorShell:
             panel.set_input_enabled(True)
         self._on_fade_in(self)
 
+    @property
+    def fade_state(self) -> str:
+        """The fade's state (shell.fade.State); "done" once closed."""
+        if self._closed:
+            return "done"
+        return "shown" if self._fade is None else self._fade.state
+
+    @property
+    def fading_out(self) -> bool:
+        """True once fade_out has started (or the shell is closed)."""
+        return self.fade_state in ("fading-out", "done")
+
+    def detach(self) -> None:
+        """Stop following the config and the monitor: the shell is leaving (fade_out, or a
+        rebuild replaces it). Pending measurements, re-layouts and readiness checks are
+        dropped, re-raises do nothing (a re-map would blink), the monitor's geometry is no
+        longer watched, and the zone strips are destroyed now, so the edges are reserved by
+        the successor's strips alone (never twice). Everything else stays on screen, as it
+        is, until fade_out or close. Once only."""
+        if self._detached or self._closed:
+            return
+        self._detached = True
+        self._cancel_sources()
+        self._disconnect_monitor()
+        for strip in self.strips:
+            self._destroy(strip)
+        self.strips = []
+
+    def fade_out(self, duration_ms: int, on_done: Callable[[MonitorShell], None]) -> None:
+        """Fade every window out over `duration_ms` from the opacity it has, then close and
+        call on_done(self). From now on the shell is detached and its panels take no input
+        (clicks reach the successor or the desktop). With 0 ms, or when nothing was visible
+        yet (still waiting to fade in), it is closed at once, as close() does. A second call
+        while fading out is ignored (the first on_done runs)."""
+        if self._closed or duration_ms <= 0 or self.fade_state == "waiting":
+            self.close()
+            self._call_done(on_done)
+            return
+        if self.fading_out:
+            return
+        self.detach()
+        for panel in self.live_panels():
+            panel.set_input_enabled(False)
+        self._fade.fade_out(duration_ms, lambda: self._faded_out(on_done))
+
+    def _faded_out(self, on_done: Callable[[MonitorShell], None]) -> None:
+        try:
+            self.close()
+        except Exception:  # in a frame-clock tick: never raise into GTK
+            log.exception("closing %s after its fade-out failed", self.name)
+        self._call_done(on_done)
+
+    def _call_done(self, on_done: Callable[[MonitorShell], None]) -> None:
+        try:
+            on_done(self)
+        except Exception:
+            log.exception("the fade-out callback of %s failed", self.name)
+
     def _set_opacity(self, value: float) -> None:
         """One frame of the fade: every window of the monitor, in the same tick."""
         for window in self.windows:
@@ -550,20 +611,26 @@ class MonitorShell:
             self._remeasure.update(range(len(self.panels)))  # fonts may have changed
         self._sync_panels(config, theme, startup=False)
 
-    def close(self) -> None:
-        self._closed = True
-        if self._fade is not None:
-            self._fade.cancel()  # before the canvas (its frame clock) is destroyed
+    def _cancel_sources(self) -> None:
         for source in (self._measure_id, self._relayout_id, self._ready_id):
             if source:
                 GLib.source_remove(source)
         self._measure_id = self._relayout_id = self._ready_id = 0
+
+    def _disconnect_monitor(self) -> None:
         for handler in self._monitor_handlers:
             try:
                 self.monitor.disconnect(handler)
             except Exception:  # the monitor may be gone already (unplugged)
                 log.debug("could not disconnect from %s", self.name, exc_info=True)
         self._monitor_handlers.clear()
+
+    def close(self) -> None:
+        self._closed = True
+        if self._fade is not None:
+            self._fade.cancel()  # before the canvas (its frame clock) is destroyed
+        self._cancel_sources()
+        self._disconnect_monitor()
         for window in self.windows:
             self._release(window)
         self.windows.clear()
diff --git a/shell/plan.py b/shell/plan.py
index 8d54c68..0e0eb06 100644
--- a/shell/plan.py
+++ b/shell/plan.py
@@ -7,9 +7,14 @@ from collections.abc import Iterable, Mapping
 from shell.config.models import Config
 
 
+def has_windows(config: Config, name: str) -> bool:
+    """True when the monitor's mode builds Edge Shell windows (edge or both)."""
+    return config.monitor(name).shell in ("edge", "both")
+
+
 def desired_shells(config: Config, connected: Iterable[str]) -> list[str]:
     """Connected monitors whose mode builds Edge Shell windows. Unconnected names are ignored."""
-    return sorted(n for n in connected if config.monitor(n).shell in ("edge", "both"))
+    return sorted(n for n in connected if has_windows(config, n))
 
 
 def reconcile(
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `scripts/py -m pytest -q tests/test_plan.py tests/test_monitor_fade.py tests/test_app_sync.py tests/test_monitor_shell.py`
Expected: `190 passed`.

- [ ] **Step 5: VERIFY**. Expected: `2789 passed`.

- [ ] **Step 6: Reviewer mutations** (measured): `detach` keeping the strips (`test_fade_out_fades_every_window_then_closes_and_calls_back_once`); `fade_out` leaving the panels' input on (same test); `sync_monitors` always fading (`test_an_unplugged_or_replaced_monitor_is_closed_at_once_without_a_fade`); `_gone` quitting while shells remain (`test_a_monitor_without_a_fade_never_cuts_the_others_fade_short`); `reload` not ignored while quitting (`test_reloads_and_hot_plug_syncs_are_ignored_while_quitting`); `_fade_ms` fading under `--stats` (`test_shells_open_with_their_monitors_fade_and_none_while_measuring`); the second signal not quitting (`test_a_second_quit_signal_quits_at_once`); a detached shell still re-raised (`test_a_detached_shell_no_longer_re_raises_re_lays_out_or_measures`); `_quit_now` quitting twice (`test_without_any_fade_a_quit_signal_quits_at_once`).

- [ ] **Step 7: Commit**

```bash
git add shell/monitors.py shell/plan.py shell/app.py tests/test_monitor_fade.py tests/test_app_sync.py tests/test_plan.py tests/test_monitor_shell.py
git commit -m "feat(shell): fade out when a monitor is turned off and on Ctrl+C or SIGTERM" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: A full rebuild crossfades from the old shell to the new one

**Files:**
- Modify: `shell/app.py` (`_leave_shell`, `_faded_in`, `_release_held`; `_open_shell` passes `on_fade_in`; `_reload` holds rebuilt shells and releases held ones in a `finally`)
- Test: `tests/test_app_sync.py` (the rebuild test pins `fade_ms = 0`; four crossfade tests), `tests/test_monitor_fade.py` (an end-to-end crossfade of two real `MonitorShell`s inside the real app)

**Interfaces:**
- Consumes: `MonitorShell.detach`, `fade_out`, `fading_out`, `fade_state`, `on_fade_in` (Tasks 3-4); `EdgeShellApp._close_shell`, `_retire`, `_gone`, `_fade_ms`, `_leaving` (Task 4); `plan.has_windows` (Task 4).
- Produces: `EdgeShellApp._leave_shell(name: str) -> None` (hold for a crossfade; closes at once with `fade_ms` 0), `_faded_in(shell: MonitorShell) -> None` (the held shell starts fading out), `_release_held() -> None` (a held shell without a successor fades out); test helpers `thicker(make_config, **theme)` (`tests/test_app_sync.py`), `Store` (`tests/test_monitor_fade.py`).

- [ ] **Step 1: Apply the test diff**

```diff
diff --git a/tests/test_app_sync.py b/tests/test_app_sync.py
index 1da5f1e..8ff7fc6 100644
--- a/tests/test_app_sync.py
+++ b/tests/test_app_sync.py
@@ -303,16 +303,17 @@ def test_opened_shells_get_the_settings_opener(env):
 
 
 def test_reload_rebuild_monitor_closes_and_reopens_without_apply(renv):
+    """With fade_ms 0 a rebuild is what it always was: closed, then opened (spec 21)."""
     app, store, errors, _, make_config = renv
     store.pending = make_config(
-        theme={"thickness": 12},
+        theme={"thickness": 12, "fade_ms": 0},
         monitors={"HDMI-A-1": mon(panels=[{"panel": "edge", "name": "dock", "widget": "dock"}])},
     )
     app.reload()
     assert FakeShell.closed == ["HDMI-A-1"]
     assert FakeShell.opened == ["HDMI-A-1"]
-    assert FakeShell.applied == []
-    assert errors == []
+    assert FakeShell.applied == [] and FakeShell.faded == []
+    assert errors == [] and app._leaving == {}
 
 
 def test_reload_applies_grouped_changes_to_existing_shell(renv):
@@ -1284,3 +1285,67 @@ def test_reloads_and_hot_plug_syncs_are_ignored_while_quitting(renv, timers):
     app._sync_timers = [7]
     app._sync_once(7)
     assert FakeShell.opened == [] and app.shells == {}  # nothing reopened
+
+
+# ---- crossfade on a rebuild (spec 21) -------------------------------------------------
+
+
+def thicker(make_config, **theme):
+    return make_config(
+        theme={"thickness": 12, **theme},
+        monitors={"HDMI-A-1": mon(panels=[{"panel": "edge", "name": "dock", "widget": "dock"}])},
+    )
+
+
+def test_a_rebuild_holds_the_old_shell_until_the_new_one_fades_in(renv):
+    app, store, errors, _, make_config = renv
+    old = app.shells["HDMI-A-1"]
+    old.fade_in()
+    store.pending = thicker(make_config)
+    app.reload()
+    new = app.shells["HDMI-A-1"]
+    assert new is not old and FakeShell.opened == ["HDMI-A-1"]
+    assert old.detached and FakeShell.closed == [] and FakeShell.faded == []  # held, on screen
+    assert app._leaving == {"HDMI-A-1": old} and new.on_fade_in == app._faded_in
+    new.fade_in()  # the new shell is ready: both fade, the old one out
+    assert FakeShell.faded == [("HDMI-A-1", 50)] and old.fading_out
+    old.faded_out()
+    assert FakeShell.closed == ["HDMI-A-1"] and app._leaving == {} and errors == []
+
+
+def test_the_old_shell_fades_out_over_the_new_configs_fade(renv):
+    app, store, _, _, make_config = renv
+    app.shells["HDMI-A-1"].fade_in()
+    store.pending = thicker(make_config, fade_ms=300)
+    app.reload()
+    app.shells["HDMI-A-1"].fade_in()
+    assert FakeShell.faded == [("HDMI-A-1", 300)]
+    assert app.shells["HDMI-A-1"].fade_ms == 300
+
+
+def test_a_held_shell_is_out_of_every_report_and_reload(renv, monkeypatch):
+    app, store, _, _, make_config = renv
+    old = app.shells["HDMI-A-1"]
+    old.fade_in()
+    store.pending = thicker(make_config)
+    app.reload()
+    new = app.shells["HDMI-A-1"]
+    old.on_error(old)  # a stale re-layout failure of the held shell: ignored
+    assert app.shells["HDMI-A-1"] is new and FakeShell.opened == ["HDMI-A-1"]
+    store.pending = thicker(make_config, accent="#112233")
+    app.reload()  # a restyle: applied to the new shell only, never a fade
+    assert FakeShell.applied == [("HDMI-A-1", ["restyle"])] and FakeShell.faded == []
+    assert app._leaving == {"HDMI-A-1": old} and not old.fading_out  # still held
+
+
+def test_a_held_shell_whose_successor_fails_to_build_fades_out(renv):
+    app, store, errors, _, make_config = renv
+    old = app.shells["HDMI-A-1"]
+    old.fade_in()
+    FakeShell.fail_open = {"HDMI-A-1"}
+    store.pending = thicker(make_config)
+    app.reload()  # the new shell raises: reported, and the old one must not stay held
+    assert len(errors) == 1 and "cannot build" in errors[0]
+    assert app.shells == {} and FakeShell.faded == [("HDMI-A-1", 50)] and old.fading_out
+    old.faded_out()
+    assert app._leaving == {}
diff --git a/tests/test_monitor_fade.py b/tests/test_monitor_fade.py
index 587b43a..92ac3e1 100644
--- a/tests/test_monitor_fade.py
+++ b/tests/test_monitor_fade.py
@@ -6,6 +6,7 @@ import pytest
 pytest.importorskip("gi")
 pytest.importorskip("fabric")
 
+import shell.app as app_mod  # noqa: E402
 import shell.monitors as mon_mod  # noqa: E402
 from shell.canvas.simulate import FRAME_US, FakeClock, FakeTicker  # noqa: E402
 from shell.config.diff import Change  # noqa: E402
@@ -407,3 +408,59 @@ def test_a_failing_fade_out_callback_is_logged_and_the_shell_is_closed(build, lo
     shell.fade_out(50, boom)
     shell.frames(5)
     assert shell.canvas.destroyed and "the fade-out callback of HDMI-A-1 failed" in caplog.text
+
+
+# ---- crossfade, end to end with the real app (Task 5) -----------------------------------
+
+
+class Store:
+    """A ConfigStore stand-in: `pending` is what the next reload reads."""
+
+    def __init__(self, config):
+        self.config, self.pending, self.path, self.last_error = config, None, None, None
+
+    def reload(self):
+        old, self.config = self.config, self.pending
+        return old, self.config
+
+
+def test_a_rebuild_crossfades_two_real_shells_in_the_same_frames(
+    build, loop, monkeypatch, make_config
+):
+    """`build` installs the window fakes; the app builds the real MonitorShells on them."""
+    monitor = FakeMonitor()
+    monkeypatch.setattr(app_mod, "monitors_by_name", lambda: {"HDMI-A-1": monitor})
+    monkeypatch.setattr(app_mod.subprocess, "Popen", lambda *_a, **_k: None)
+    store = Store(make_config(monitors=edge(DOCK)))
+    app = app_mod.EdgeShellApp(store)
+    app.sync_monitors()
+    old = app.shells["HDMI-A-1"]
+    loop.run_idles()
+    loop.fire(500)
+    clock = FakeClock()
+
+    def vsync(n, *shells):  # one output: both canvases get the same frame times
+        for _ in range(n):
+            clock.now_us += FRAME_US
+            for shell in shells:
+                shell.canvas.ticker.run(clock)
+
+    vsync(4, old)
+    assert old.fade_state == "shown"
+    old_strips = list(old.strips)
+    store.pending = make_config(monitors=edge(DOCK), theme={"thickness": 12})
+    app.reload()
+    new = app.shells["HDMI-A-1"]
+    assert new is not old and app._leaving == {"HDMI-A-1": old}
+    assert all(s.destroyed for s in old_strips)  # the edges are reserved once: by the new ones
+    assert old.canvas.opacity[-1] == 1.0 and new.canvas.opacity == [0.0]  # old still shown
+    assert old.panels[0].inputs == [False, True]  # the held shell keeps its input
+    loop.run_idles()
+    loop.fire(500)  # the new shell is ready: the crossfade starts
+    assert new.panels[0].inputs == [False, True] and old.panels[0].inputs[-1] is False
+    old_canvas = old.canvas
+    vsync(4, new, old)
+    assert new.canvas.opacity[-4:] == pytest.approx(THIRDS, abs=1e-3)
+    assert old_canvas.opacity[-4:] == pytest.approx(list(reversed(THIRDS)), abs=1e-3)
+    assert old_canvas.destroyed and old.panels == [] and app._leaving == {}
+    assert not new.canvas.destroyed and new.fade_state == "shown"
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `scripts/py -m pytest -q tests/test_monitor_fade.py tests/test_app_sync.py`
Expected: `5 failed, 106 passed` (the rebuild still closes the old shell at once).

- [ ] **Step 3: Apply the implementation diff**

```diff
diff --git a/shell/app.py b/shell/app.py
index a230439..257d16c 100644
--- a/shell/app.py
+++ b/shell/app.py
@@ -155,6 +155,34 @@ class EdgeShellApp:
             self._retire(name)
             shell.close()
 
+    def _leave_shell(self, name: str) -> None:
+        """A full rebuild of `name` (spec 21, crossfade): the old shell stays on screen,
+        detached (held), until its successor starts fading in; then it fades out over the
+        same time (_faded_in). Without a fade it is closed now, as before."""
+        if self._fade_ms(name) <= 0:
+            self._close_shell(name, fade=False)
+            return
+        self._forget_reports(name)
+        shell = self.shells.pop(name)
+        self._retire(name)  # at most one leaving shell per monitor: an older one goes now
+        shell.detach()
+        self._leaving[name] = shell
+
+    def _faded_in(self, shell: MonitorShell) -> None:
+        """`shell` starts fading in: the shell it replaces (held) fades out with it."""
+        if self.shells.get(shell.name) is not shell:
+            return
+        old = self._leaving.get(shell.name)
+        if old is not None and not old.fading_out:
+            old.fade_out(self._fade_ms(shell.name), self._gone)
+
+    def _release_held(self) -> None:
+        """A held shell whose monitor got no successor (its rebuild failed, or it was never
+        opened) fades out on its own."""
+        for name, shell in list(self._leaving.items()):
+            if name not in self.shells and not shell.fading_out:
+                shell.fade_out(self._fade_ms(name), self._gone)
+
     def _fade_away(self, name: str, shell: MonitorShell) -> None:
         self._retire(name)  # at most one leaving shell per monitor: an older one goes now
         self._leaving[name] = shell
@@ -201,6 +229,7 @@ class EdgeShellApp:
             on_error=lambda shell, n=name: self._relayout_failed(n, shell),
             on_settings=self.open_settings,
             fade_ms=self._fade_ms(name),
+            on_fade_in=self._faded_in,
         )
         if not shell.measure_pending:  # else the measurement's on_layout reports, with real sizes
             self._report_layout(name, shell)
@@ -277,10 +306,15 @@ class EdgeShellApp:
         log.info("config reloaded: %d change(s): %s", len(changes), kinds)
         rebuild = {c.monitor for c in changes if c.kind == "rebuild-monitor"}
         for name in sorted(rebuild & set(self.shells)):
-            # turned off (plasma / none): it fades out; else it is rebuilt from the new config
-            self._close_shell(name, fade=not plan.has_windows(new, name))
+            if plan.has_windows(new, name):
+                self._leave_shell(name)  # rebuilt: the old one is held for the crossfade
+            else:
+                self._close_shell(name)  # turned off (plasma / none): it fades out
         # Shells opened here are built from the new config already: never apply onto them.
-        _, opened = self.sync_monitors()
+        try:
+            _, opened = self.sync_monitors()
+        finally:
+            self._release_held()  # e.g. the new shell failed to build: the old one fades out
         grouped: dict[str, list] = defaultdict(list)
         for change in changes:
             if change.monitor not in rebuild:
```

- [ ] **Step 4: Run the tests to see them pass**

Run: the command of Step 2. Expected: `111 passed`.

- [ ] **Step 5: VERIFY**. Expected: `2794 passed`.

- [ ] **Step 6: Reviewer mutations** (measured): `_leave_shell` starting the old shell's fade-out at once instead of holding it (`test_a_rebuild_holds_the_old_shell_until_the_new_one_fades_in`); no `_release_held()` in the `finally` (`test_a_held_shell_whose_successor_fails_to_build_fades_out`); `_open_shell` not passing `on_fade_in` (`test_a_rebuild_holds_...`); `_reload` closing rebuilt shells at once (`test_a_rebuild_holds_...`, `test_a_rebuild_crossfades_two_real_shells_in_the_same_frames`).

- [ ] **Step 7: Commit**

```bash
git add shell/app.py tests/test_app_sync.py tests/test_monitor_fade.py
git commit -m "feat(shell): a full rebuild crossfades from the old shell to the new one" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: A reload or a hot-plug during a fade never stacks fades or leaves a shell behind

**Files:**
- Modify: `shell/monitors.py` (`finish_fade`), `shell/app.py` (`sync_monitors` drops leaving shells of a gone monitor; `_leave_shell` closes a never-visible shell and finishes a fade-in; `_fade_away` closes a never-visible shell and fades the held one)
- Test: `tests/test_app_sync.py` (`FakeShell.finish_fade`, `FakeShell.finished`; six tests), `tests/test_monitor_fade.py` (one test)

**Interfaces:**
- Consumes: everything of Tasks 3-5.
- Produces: `MonitorShell.finish_fade() -> None` (completes a fade-in in progress; nothing in any other state); test helper `held_rebuild(renv) -> (old, new)`.

- [ ] **Step 1: Apply the test diff**

```diff
diff --git a/tests/test_app_sync.py b/tests/test_app_sync.py
index 8ff7fc6..20b8898 100644
--- a/tests/test_app_sync.py
+++ b/tests/test_app_sync.py
@@ -15,6 +15,7 @@ class FakeShell:
     closed: list = []
     applied: list = []
     faded: list = []  # (name, ms) of every fade_out call
+    finished: list = []  # every shell finish_fade was called on
     fail_apply: set = set()
     layout_warnings: list = []
     build_failures: list = []
@@ -59,6 +60,11 @@ class FakeShell:
     def detach(self):
         self.detached = True
 
+    def finish_fade(self):
+        FakeShell.finished.append(self)
+        if self.fade_state == "fading-in":
+            self.fade_state = "shown"
+
     def fade_out(self, ms, on_done):
         """MonitorShell.fade_out: closed at once with 0 ms or while still invisible."""
         FakeShell.faded.append((self.name, ms))
@@ -95,6 +101,7 @@ def _reset_fake_shell(monkeypatch):
         ("closed", []),
         ("applied", []),
         ("faded", []),
+        ("finished", []),
         ("fail_apply", set()),
         ("fail_open", set()),
         ("layout_warnings", []),
@@ -1349,3 +1356,85 @@ def test_a_held_shell_whose_successor_fails_to_build_fades_out(renv):
     assert app.shells == {} and FakeShell.faded == [("HDMI-A-1", 50)] and old.fading_out
     old.faded_out()
     assert app._leaving == {}
+
+
+# ---- a reload or a hot-plug during a fade (spec 21) -----------------------------------
+
+
+def held_rebuild(renv):
+    """The old shell shown, then a rebuild: (old held, new still waiting)."""
+    app, store, _, _, make_config = renv
+    old = app.shells["HDMI-A-1"]
+    old.fade_in()
+    store.pending = thicker(make_config)
+    app.reload()
+    return old, app.shells["HDMI-A-1"]
+
+
+def test_a_second_rebuild_mid_crossfade_never_stacks_fades(renv):
+    app, store, _, _, make_config = renv
+    first, second = held_rebuild(renv)
+    second.fade_in()  # crossfade: the first one fades out
+    assert first.fading_out
+    store.pending = thicker(make_config, radius=16)
+    app.reload()
+    third = app.shells["HDMI-A-1"]
+    assert FakeShell.closed == ["HDMI-A-1"]  # the first one (half faded) goes at once
+    assert FakeShell.finished == [first, second] and second.detached  # held, fully shown
+    assert app._leaving == {"HDMI-A-1": second} and not second.fading_out
+    third.fade_in()
+    assert FakeShell.faded == [("HDMI-A-1", 50), ("HDMI-A-1", 50)] and second.fading_out
+
+
+def test_a_rebuild_while_the_new_shell_is_still_invisible_keeps_the_held_one(renv):
+    app, store, _, _, make_config = renv
+    first, second = held_rebuild(renv)  # the second has not faded in yet
+    store.pending = thicker(make_config, radius=16)
+    app.reload()
+    third = app.shells["HDMI-A-1"]
+    assert FakeShell.closed == ["HDMI-A-1"] and second.fade_state == "done"  # never seen
+    assert app._leaving == {"HDMI-A-1": first} and not first.fading_out  # still on screen
+    third.fade_in()
+    assert FakeShell.faded == [("HDMI-A-1", 50)] and first.fading_out
+
+
+def test_a_rebuild_before_the_first_fade_in_just_replaces_the_invisible_shell(renv):
+    app, store, _, _, make_config = renv
+    store.pending = thicker(make_config)  # the shell from startup has not faded in yet
+    app.reload()
+    assert FakeShell.closed == ["HDMI-A-1"] and FakeShell.opened == ["HDMI-A-1"]
+    assert app._leaving == {} and FakeShell.faded == []
+
+
+def test_turning_a_monitor_off_while_its_new_shell_waits_fades_the_held_one(renv):
+    app, store, _, _, make_config = renv
+    first, second = held_rebuild(renv)
+    store.pending = make_config(monitors={"HDMI-A-1": mon("plasma")})
+    app.reload()
+    assert second.fade_state == "done" and FakeShell.closed == ["HDMI-A-1"]  # never seen
+    assert FakeShell.faded == [("HDMI-A-1", 50)] and first.fading_out  # the visible one fades
+    first.faded_out()
+    assert app.shells == {} and app._leaving == {}
+
+
+def test_unplugging_a_monitor_mid_fade_closes_its_leaving_shell_at_once(renv):
+    app, store, _, mapping, make_config = renv
+    shell = app.shells["HDMI-A-1"]
+    shell.fade_in()
+    store.pending = make_config(monitors={"HDMI-A-1": mon("plasma")})
+    app.reload()
+    assert app._leaving == {"HDMI-A-1": shell} and FakeShell.closed == []
+    del mapping["HDMI-A-1"]
+    mapping["DP-1"] = object()
+    app.sync_monitors()
+    assert FakeShell.closed == ["HDMI-A-1"] and app._leaving == {}  # no fade on a dead output
+
+
+def test_a_replaced_monitor_drops_the_held_shell_and_the_new_one_opens(renv):
+    app, store, _, mapping, make_config = renv
+    first, second = held_rebuild(renv)
+    second.fade_in()
+    mapping["HDMI-A-1"] = object()  # replugged: a new Gdk monitor
+    app.sync_monitors()
+    assert FakeShell.closed == ["HDMI-A-1", "HDMI-A-1"]  # both old shells, at once
+    assert app._leaving == {} and FakeShell.opened[-1] == "HDMI-A-1"
diff --git a/tests/test_monitor_fade.py b/tests/test_monitor_fade.py
index 92ac3e1..5473bf0 100644
--- a/tests/test_monitor_fade.py
+++ b/tests/test_monitor_fade.py
@@ -410,6 +410,20 @@ def test_a_failing_fade_out_callback_is_logged_and_the_shell_is_closed(build, lo
     assert shell.canvas.destroyed and "the fade-out callback of HDMI-A-1 failed" in caplog.text
 
 
+def test_finish_fade_completes_only_a_fade_in(build, loop):
+    shell = build(edge(DOCK))
+    shell.finish_fade()  # waiting: nothing to complete (it may never be shown)
+    assert shell.fade_state == "waiting" and shell.canvas.opacity == [0.0]
+    loop.run_idles()
+    loop.fire(500)
+    shell.frames(2)
+    shell.finish_fade()
+    assert shell.fade_state == "shown" and all(w.opacity[-1] == 1.0 for w in shell.windows)
+    assert not shell.canvas.ticker._callbacks
+    shell.finish_fade()  # shown: nothing
+    assert shell.fade_state == "shown"
+
+
 # ---- crossfade, end to end with the real app (Task 5) -----------------------------------
 
 
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `scripts/py -m pytest -q tests/test_monitor_fade.py tests/test_app_sync.py`
Expected: `6 failed, 112 passed` (`test_a_replaced_monitor_drops_the_held_shell_and_the_new_one_opens` already passes: it pins the replug path).

- [ ] **Step 3: Apply the implementation diff**

```diff
diff --git a/shell/app.py b/shell/app.py
index 257d16c..9f1dca4 100644
--- a/shell/app.py
+++ b/shell/app.py
@@ -110,6 +110,9 @@ class EdgeShellApp:
             self._check_monitor_names(connected)
         except Exception:  # a warning must never break startup or a reload
             log.exception("checking the monitor names failed")
+        for name, shell in list(self._leaving.items()):
+            if connected.get(name) is not shell.monitor:  # unplugged or replaced: no fade on it
+                self._retire(name)
         wanted = plan.desired_shells(self.config, connected)
         desired = {name: connected[name] for name in wanted}
         active = {name: shell.monitor for name, shell in self.shells.items()}
@@ -164,7 +167,12 @@ class EdgeShellApp:
             return
         self._forget_reports(name)
         shell = self.shells.pop(name)
+        if shell.fade_state == "waiting":
+            # never visible: closed now; a shell it was replacing stays held for the next one
+            shell.close()
+            return
         self._retire(name)  # at most one leaving shell per monitor: an older one goes now
+        shell.finish_fade()  # mid fade-in: held fully shown, never two fades at once
         shell.detach()
         self._leaving[name] = shell
 
@@ -184,6 +192,12 @@ class EdgeShellApp:
                 shell.fade_out(self._fade_ms(name), self._gone)
 
     def _fade_away(self, name: str, shell: MonitorShell) -> None:
+        if shell.fade_state == "waiting":
+            # never visible: closed now, and the shell it was replacing (held, on screen)
+            # fades out instead of disappearing
+            shell.close()
+            self._release_held()
+            return
         self._retire(name)  # at most one leaving shell per monitor: an older one goes now
         self._leaving[name] = shell
         shell.fade_out(self._fade_ms(name), self._gone)
diff --git a/shell/monitors.py b/shell/monitors.py
index eae189b..534c9f7 100644
--- a/shell/monitors.py
+++ b/shell/monitors.py
@@ -505,6 +505,12 @@ class MonitorShell:
         """True once fade_out has started (or the shell is closed)."""
         return self.fade_state in ("fading-out", "done")
 
+    def finish_fade(self) -> None:
+        """Complete a fade-in in progress now (fully shown). A shell replaced in the middle of
+        its fade-in (a second reload) is held at full opacity: fades never stack."""
+        if not self._closed and self._fade is not None and self._fade.state == "fading-in":
+            self._fade.finish()
+
     def detach(self) -> None:
         """Stop following the config and the monitor: the shell is leaving (fade_out, or a
         rebuild replaces it). Pending measurements, re-layouts and readiness checks are
```

- [ ] **Step 4: Run the tests to see them pass**

Run: the command of Step 2. Expected: `118 passed`.

- [ ] **Step 5: VERIFY**. Expected: `2801 passed`. Then the GTK-blocked run (Global Constraints): `1961 passed, 38 skipped`.

- [ ] **Step 6: Reviewer mutations** (measured): `_leave_shell` without its "never visible" branch (`test_a_rebuild_while_the_new_shell_is_still_invisible_keeps_the_held_one`); without `finish_fade()` (`test_a_second_rebuild_mid_crossfade_never_stacks_fades`); `_fade_away` without its "never visible" branch (`test_turning_a_monitor_off_while_its_new_shell_waits_fades_the_held_one`); `sync_monitors` not dropping leaving shells (`test_unplugging_a_monitor_mid_fade_closes_its_leaving_shell_at_once`); `finish_fade` doing nothing (`test_finish_fade_completes_only_a_fade_in`).

- [ ] **Step 7: Commit**

```bash
git add shell/monitors.py shell/app.py tests/test_app_sync.py tests/test_monitor_fade.py
git commit -m "fix(shell): a reload or a hot-plug during a fade never stacks fades or leaves a shell behind" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: The docs, and the gate checklist for Phil

**Files:**
- Modify: `README.md` (Features: a Fades bullet; Run: Ctrl+C; the Theme page's General tab names the fade; Known limitations: a fades line), `docs/superpowers/specs/2026-10-11-edge-shell-design.md` (section 6 reload table: two rows and the mode row; a new section 21)

**Interfaces:** none (docs).

- [ ] **Step 1: Apply the docs diff**

```diff
diff --git a/README.md b/README.md
index 36c8f79..3c94495 100644
--- a/README.md
+++ b/README.md
@@ -33,6 +33,11 @@ alongside Plasma and does not replace it.
 - Several panels per edge: align slots (start, center, end) with order and offset, a configurable gap, lengths in px, "fill", "content" or a percentage with optional min/max. Panels keep clear of the rounded screen corners and re-lay out when the monitor's resolution changes.
 - Panel animation, hover peek, click to toggle, drag to open or close with a 50% snap.
 - Live config reload: an invalid edit keeps the last good config and sends a notification.
+- Fades: a monitor's Edge Shell fades in when it is turned on or starts (once it is fully
+  built, so it never blinks or grows into place), fades out when it is turned off or the shell
+  quits, and a full rebuild (a thickness change, for example) crossfades from the old frame to
+  the new one. `[theme] fade_ms` (default 50 ms, 0-500, per monitor too) sets the time; 0
+  turns it off.
 - Monitor hot-plug, and per-monitor theme overrides scoped to that monitor.
 
 ## Requirements
@@ -65,7 +70,9 @@ scripts/py main.py --restore-config                        # put back config.tom
 
 `scripts/py` runs the shared venv; override it with `EDGE_SHELL_PYTHON=/path/to/python`.
 Only one instance can run (Fabric names the app `edge-shell`). Quit a backgrounded copy
-with `fg`, then Ctrl+C.
+with `fg`, then Ctrl+C. Ctrl+C (or SIGTERM) fades every monitor out first and quits when the
+fade is done (at most `fade_ms` + 250 ms later); a second Ctrl+C quits at once. The exit
+status is 130 after Ctrl+C, 143 after SIGTERM.
 
 ## Configure
 
@@ -382,7 +389,7 @@ file.
   (Tab reaches them); the toolbar has the same three. After a Remove the monitor's row is
   selected (and keeps the keyboard focus when the tree had it).
 - **Theme** page, tabs: **General** (colours, fonts, thickness, radius, peek, hover zone,
-  duration; any theme key added later lands here), **Borders**, **Shadows**, **Handle** (the
+  duration, fade; any theme key added later lands here), **Borders**, **Shadows**, **Handle** (the
   handle colours and the handle style) and **Layout** (the gap). A **monitor** page has the same
   tabs under a banner that is always shown: "These values override the Theme for HDMI-A-1. A row
   you have not set here shows the Theme's value." A row not set there reads "global theme".
@@ -586,6 +593,14 @@ that need `gi` or Fabric skip themselves there.
 - The "Panels adjusted" notification is not repeated after an unplug and replug that yields
   identical layout warnings.
 - On a dark wallpaper the border and shadow are faint; raise the shadow alpha or elevation.
+- Fades (spec section 21): a monitor fades in about half a second after it is turned on (it
+  waits for the panels' re-raise, which re-maps them and would blink); the fallback re-raise
+  2 s after the start still re-maps the panels once after the fade; the maximized windows
+  resize when the frame strips appear or go (not faded: the zone is the compositor's); during a
+  crossfade the old shell's text and fonts take the new theme's CSS at once (its frame keeps the
+  old look until it is gone), shapes both shells cover dim slightly half-way (two
+  half-transparent frames over each other); a hot-plug or a quit in the middle of a crossfade
+  drops the old shell at once; `--stats` never fades.
 
 ## Licence
 
diff --git a/docs/superpowers/specs/2026-10-11-edge-shell-design.md b/docs/superpowers/specs/2026-10-11-edge-shell-design.md
index b17325f..cb14a93 100644
--- a/docs/superpowers/specs/2026-10-11-edge-shell-design.md
+++ b/docs/superpowers/specs/2026-10-11-edge-shell-design.md
@@ -189,6 +189,8 @@ shell = "plasma"
   | Change | Reaction |
   | --- | --- |
   | Theme colour, border, shadow or handle style | Regenerate CSS; redraw the canvas (no rebuild) |
+  | Theme `thickness`, `radius`, `peek`, `hover_zone` or `duration_ms` | Rebuild the monitor: the new shell crossfades over the old one (section 21) |
+  | Theme `fade_ms` | Nothing now: the next fade uses it (a restyle, section 21) |
   | Panel `state` | Retarget the tween |
   | Panel `handle` or `interaction` | Update the live panel in place (no rebuild) |
   | Panel `edge`, `pos`, `align`, `offset`, `order`, `length`, `min_length`, `max_length` or `depth` | Rebuild that panel's window, and any panel whose resolved position or visibility changed with it (section 17 rules) |
@@ -196,7 +198,7 @@ shell = "plasma"
   | Panel `panel`, `widget`, `name` or a widget property | Rebuild that panel (section 20) |
   | Layout `gap` (`[layout]`, `[monitors.X.layout]`) | Re-layout the monitor: rebuild only the panels that moved |
   | Panel added or removed | Create or destroy that window |
-  | Monitor `shell` mode | Create or destroy that monitor's windows |
+  | Monitor `shell` mode | Create (fade in) or destroy (fade out) that monitor's windows (section 21) |
   | Invalid config | Keep the old config; report the error |
 
 ## 7. Plasma integration
@@ -547,3 +549,61 @@ Spec: `docs/superpowers/specs/2026-10-14-panel-widget-model-design.md` (sections
   widget or kind is one edit that drops the keys the new one does not take.
 
 **Results.** Gate (Phil, live on HDMI-A-1, 2026-10-14): all 13 checklist items, counted by Phil as 21 steps with the eight error cases of item 4 (a-h), passed with no failures: the start state and its four `building panel` lines (each panel built once, the clock at a fixed 320 px); the clock's `format`, quoted text, `font` and `font_size` by hand (one `panel-rebuild` each); a rename by hand; the eight error cases keeping the previous layout with the quoted notification texts; the settings window's panel list, Widget frame and add list; adding panels with free names (`Clock`, `Clock 2`); widget properties from the window; names in the window; switching the widget; Revert all; a hand edit while the window is open; `examples/corner-test.toml`; DP-1 untouched. The deferred-rebuild click fix (panel buttons keep the focus where it is) was not reported as a problem. Not checked live (covered by tests): a widget whose build raises and is not retried until its entry changes, a widget property type the window cannot show refused at registration, the Panel type row and the greyed-out `float` row (no built-in widget supports two panel kinds). Known limits: the duplicate-name error under a renamed row names the later entry's index in its path prefix (the message names both entries); a live theme-font change leaves an existing clock's font fallback until the panel is rebuilt.
+
+## 21. Implemented: the shell fade
+
+Plan: `docs/superpowers/plans/2026-10-16-shell-fade.md`. Phil: "make the shell fade-in when
+enabled or requires a full redraw ... On disable have it fade out instead of just disappear
+instantly."
+
+- **Key.** `[theme] fade_ms` (default 50, 0-500 ms; `[monitors.X.theme] fade_ms` per monitor;
+  0 = no fade, exactly the old behaviour). A change is a restyle: nothing is rebuilt, the next
+  fade uses it. The settings window shows it on the General tab as a slider (0-500 is within
+  the slider rule's 500). `--stats` never fades.
+- **Fade in.** Every window of a monitor (the canvas, the four strips, every panel) is built at
+  opacity 0, its panels without input. The monitor is ready when the first re-raise
+  (`RAISE_DELAY_MS`, 500 ms: a re-map that would blink) has run and no "content"
+  measurement (which can rebuild a panel) is pending; then all windows fade in together, the
+  panels take input from the start of the fade, and the shell is fully shown `fade_ms` later.
+  If it is not ready after `READY_TIMEOUT_MS` (1000 ms) it fades in anyway; a fade that has not
+  finished `FINISH_MARGIN_MS` (300 ms) after its duration (a canvas that gets no frames) is
+  finished at once. So a stuck build never leaves a monitor invisible.
+- **Mechanism.** `shell/fade.py` (`Fade`, pure): one `shell.anim.Tween` (linear) on the canvas
+  window's frame clock; its one callback sets `Gtk.Widget.set_opacity` on every window of the
+  monitor in the same frame. GTK 3.24 paints a toplevel's opacity itself (a group with
+  alpha, since the Wayland visual is the RGBA one), over everything the window draws (the
+  canvas drawing, panel content, handles). Alternatives not taken: drawing the fade into the
+  canvas only (the panels' own content and handles would not fade), CSS `opacity` on the content
+  (the canvas would not fade, and a CSS change restyles every widget).
+- **Fade out.** Turning a monitor off (`shell = "plasma"` or `"none"`) fades it out over its
+  `fade_ms`, then destroys its windows; its panels take no input from the start of the fade
+  and its strips (the reserved zone) go at once. An unplugged or replaced monitor is closed at
+  once (no fade on a dead output). A shell that never became visible is closed at once.
+- **Crossfade.** A full rebuild (`rebuild-monitor`: thickness, radius, peek, hover zone,
+  duration) keeps the old shell on screen, detached (no re-layout, re-raise or measurement; its
+  strips destroyed so the new strips reserve the edges alone), until the new shell starts its
+  fade-in; then the new one fades 0 -> 1 and the old one 1 -> 0 over `fade_ms`, and the old one
+  is destroyed. Input moves at that moment: the old panels take none, the new ones all of it.
+  The new windows are mapped later, so they stack above the old ones. At most one leaving
+  shell per monitor: a reload during a crossfade destroys the older leaving shell at once and
+  completes the current fade-in (held fully shown); a shell replaced before it was ever
+  visible is simply closed; a held shell whose successor fails to build fades out on its own.
+  The app keeps leaving shells out of `shells`, so reports, CSS and reloads never see them.
+- **Quit.** SIGINT and SIGTERM (GLib's Unix signal source; Python's own SIGINT handler stays
+  the default so PyGObject installs no quit-without-fade fallback) fade every monitor out and
+  quit when the last fade is done, at the latest the longest `fade_ms` + 250 ms later; a second
+  signal quits at once; the exit status is 128 + the signal (130, 143). Reloads and hot-plug
+  syncs are ignored while quitting.
+- **Not faded.** A restyle, panel adds, removes, rebuilds and state changes, a resolution change
+  (re-laid out in place), failure rebuilds (an in-place apply or a re-layout that raised:
+  closed at once, the new shell still fades in).
+- **Cost.** A 50 ms fade is 3 frames at 60 Hz: 3 full redraws of each window (the canvas's
+  full draw is 1.6 ms without effects, about 15 ms with border and shadow at 1920x1080, so a
+  frame may be dropped with effects on) plus GTK's group for each; blending a translucent
+  layer surface is the compositor's work, as it already is for these ARGB windows.
+- **Verified headless:** the state machine (`tests/test_fade.py`), the build, ready, timeouts,
+  input and close paths of `MonitorShell` on fake windows and a fake frame clock
+  (`tests/test_monitor_fade.py`, including a crossfade of two real `MonitorShell`s inside the
+  real app), the app's hold, crossfade, release and quit rules (`tests/test_app_sync.py`), and
+  that `GLibUnix.signal_add` receives SIGINT and SIGTERM. **Live only (the gate):** what
+  KWin shows: no blink or growth at enable, the fade itself, the crossfade, the quit.
```

- [ ] **Step 2: VERIFY** (ruff skips `*.md`). Expected: `2801 passed`. Then check that the docs name what the code does: `grep -n "READY_TIMEOUT_MS = 1000" shell/fade.py`, `grep -n "FINISH_MARGIN_MS = 300" shell/fade.py`, `grep -n "QUIT_MARGIN_MS = 250" shell/app.py`, `grep -n "^fade_ms = 50 " config.default.toml` each print one line.

- [ ] **Step 3: Commit**

```bash
git add README.md docs/superpowers/specs/2026-10-11-edge-shell-design.md
git commit -m "docs: the shell fade in the README and the spec" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 4: Hand the gate to Phil.** Report the branch, the commits and the checklist below. Nobody but Phil runs it.

#### Gate checklist (Phil, live, HDMI-A-1 only; DP-1 is never touched)

Setup: `cp ~/.config/edge-shell/config.toml ~/.config/edge-shell/config.toml.gate-fade` first. Start the shell from the worktree in a terminal you keep visible: `scripts/py main.py -v` (HDMI-A-1 has `shell = "edge"`, DP-1 keeps `shell = "plasma"`). Open the settings window: `scripts/py main.py --settings`. "Enable" below is the toolbar's **Enable** checkbox with the **HDMI-A-1** monitor page selected (its KDE Plasma checkbox stays as it is). "Fade" is Theme > General > **Fade** (a slider, 0-500 ms).

1. **The old behaviour, for comparison (fade off).** Set Fade to **0**. Untick Enable (HDMI-A-1 page, toolbar), wait, tick it; then change Thickness 10 -> 16 and back (a full rebuild). Expected (today's look): the frame vanishes at once; on enable it blinks in, and about half a second later the panels' content and handles flicker once (the re-raise); "content" panels may jump in length; a thickness change closes and reopens the frame with the same blink. Remember what you saw: items 2, 3 and 5 must not show it.
2. **Slow, to judge (300 ms; the stop condition).** Set Fade to **300**. Untick Enable (HDMI-A-1 page, toolbar): the frame, corners and panels fade out together, clearly visible. Tick it: nothing for about half a second, then everything fades in together. Expected: a clearly visible fade of everything at once, both ways. If nothing fades (the shell appears at full opacity after the wait, or disappears at once), the mechanism is not working on KWin: report it and stop (decision 2's contingency, the opacity on each window's child, is the planned fallback; do not continue the other items on a build that does not fade). Watch about 2 s after an enable: a single flicker of the handles there is the fallback re-raise (open question 2).
3. **Enable and disable at the default (50 ms).** Set Fade back to **50** (or press its Reset) and repeat item 2. Expected: a quick fade, not an instant cut; no blink, no flicker of handles or content after it is shown, no panel growing or jumping, no part (frame, a panel body, a handle, dock icons, clock text) appearing before or after the rest. Say if you see the frame (canvas) a frame or two before the panels' content: the canvas and the panels are separate windows set in the same frame, but the canvas may be drawn first.
4. **Maximized windows.** With a maximized window on HDMI-A-1 and Fade 300: on enable the window shrinks 100 ms after the frame starts to appear (the zone strips are built then); on disable it grows to the screen edges when the frame is gone (the strips are kept until the fade-out ends), with no square corner showing through the fading frame and the panels keeping their look (the monitor's CSS stays until the fade-out ends); on a rebuild (Thickness 10 to 64) the window keeps its size until the new frame has started to appear, then changes once, 100 ms later, without bouncing, for any Fade value (also the default 50: the new strips are built just before the old shell closes). (The first gate run found the shrink 0.5 s early and the corners snapping square at the start of a disable; the re-check found 50 ms too early, the CSS dropped at a disable and the rebuild shrinking early; all fixed, to be re-checked: see the Task 8 record.)
5. **Crossfade on a rebuild.** Fade 300. Theme > General > **Thickness** from 10 to 16 (release the slider). Expected: the old frame stays, about half a second later the thicker frame fades in while the old one fades out, then only the new one; never a moment without a frame and no flash of the desktop through it; a slight dim of the frame half-way is the known effect of decision 8 (say whether you see it; open question 3). Back to 10: the same.
6. **Input follows what you see.** Fade 300. Hover the collapsed handle of a panel first (so the pointer is already on it), then press an arrow key on the focused Thickness slider (key edits are sent at once; do not drag, a release followed by moving to a handle takes longer than the half second). During the half second before the crossfade the old panel (the one you see) answers the pointer; after the crossfade the new one answers. During a disable's fade-out, click where a panel is: the click goes to what is below.
7. **A change during a fade.** Fade 300. Press an arrow key on the focused Thickness slider twice, about 0.3 s apart (10 -> 11 -> 12; this exercises the waiting branch: the second reload arrives while the first rebuilt shell is still invisible). Then try 0.5-0.8 s apart, which hits the middle of the crossfade. Expected: no stacked or double fades, no frame left behind; you end with one frame of the last thickness. (Two slider releases less than 200 ms apart merge into one reload through the watcher's debounce, so use the keys.) Also: change Thickness, then untick Enable before the new frame has appeared: the old frame fades out (it does not vanish at once) and nothing is left.
8. **Per monitor.** Set Fade to 50 on the Theme page and to 300 on the **HDMI-A-1** monitor page's General tab; disable and enable: the 300 ms fade is used. Reset the monitor page's Fade afterwards. Also: dragging the Fade slider sends nothing; after the release the `-v` line reads `config reloaded: 1 change(s): restyle` (no "rebuild" line) and the frame does not blink; the new value is used by the NEXT fade only.
9. **Quit and startup (a throwaway session).** Fade 300. In the shell's terminal press Ctrl+C once: the frame fades out, then the process ends within about fade_ms + 250 ms; `echo $status` (fish; `$?` in bash) prints `130`. Start it again (`scripts/py main.py -v`) and check the startup: HDMI-A-1 appears with a fade about half a second after the start, no blink. Press Ctrl+C twice quickly: it quits at once. Start it once more and from another terminal run `kill -TERM (pgrep -f 'main.py -v')` (fish): the same fade, then `echo $status` in the shell's terminal prints `143`. An unplug cannot be tested here: skip it.
10. **No fade where none belongs.** Change the Accent colour (Theme > General): the colour changes at once, no fade. Collapse and extend a panel (click its handle): its own animation as before, no shell fade. Change Fade itself (0 -> 300 -> 50): nothing is rebuilt and nothing fades.
11. **Logs.** In the `-v` output of the runs above there is no line "a fade did not finish in time" (it would mean the canvas got no frames) and no traceback.
12. **DP-1 untouched.** Last: `grep -n -A3 'monitors.DP-1' ~/.config/edge-shell/config.toml` still shows `shell = "plasma"`, and Plasma's panel on DP-1 is unchanged. Restore your config if you like: `cp ~/.config/edge-shell/config.toml.gate-fade ~/.config/edge-shell/config.toml`.

What only the gate can show (not testable headless): whether GTK's toplevel opacity reaches KWin (item 2), whether any blink is left (items 2, 3, 9), the crossfade's look (item 5), the maximized windows (item 4), the quit's look and status (item 9).

---

### Task 8: Record the gate results

**Files:**
- Modify: `docs/superpowers/specs/2026-10-11-edge-shell-design.md` (section 21, a closing paragraph)

**Interfaces:** none.

- [ ] **Step 1: Write the results.** When Phil has run the gate, add one paragraph at the end of section 21, in the form the earlier sections use: `**Results (Phil, live on HDMI-A-1 only, DP-1 untouched, DATE):** ` then, for all items passed, "all 12 gate items passed" with Phil's own words in quotes; for an item that failed, its number, what Phil saw (his words), and what was done (the fix commit, or the follow-up named). If item 3 shows no fade at all, do not change code under this task: the follow-up is decision 2's contingency (the opacity on each window's child), planned as its own task. Record Phil's answers to the open questions below the results.
- [ ] **Step 2: VERIFY**. Expected: `2801 passed`.
- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-10-11-edge-shell-design.md
git commit -m "docs: record the shell fade gate results" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [x] **Result record (2026-10-17).** The gate was run by Phil on HDMI-A-1 (DP-1 untouched): items 1, 2 and 5-12 passed; items 3 and 4 passed with findings. Finding 3: on a disable (Enable unticked) at Fade 300 the frame's rounded inner corners reverted instantly to 90 degrees (not on enable, not on a rebuild); cause: `fade_out` called `detach()`, which destroyed the zone strips at the start, so a maximized window grew while the frame was still partly opaque. Finding 4: on an enable the strips were built with the shell, so a maximized window shrank about 0.5 s before the frame faded in; Phil wants the window to resize 50 ms after the frame starts to appear. Both are fixed in f61d49a `fix(shell): the zone strips are built 50 ms after a fade-in starts and kept until a fade-out ends`, with 4e8c947 (a shell opened while the previous one fades out reserves late) and 8515e3b (a held shell whose successor is gone gets its strips back before it fades out) as review follow-ups: `detach(keep_strips=True)` for `fade_out` (the strips close with the shell's windows), `reserve_now` on `MonitorShell` (False when fading and the predecessor, if any, is not held: a fresh enable, a startup, a hot-plug or an enable during a fade-out) with `RESERVE_DELAY_MS = 50` after the fade-in starts; a rebuild's successor builds its strips at once and `_leave_shell` still destroys the old ones at the swap; `fade_ms` 0 is unchanged. Phil's re-check of items 3 and 4 is pending.
- [x] **Re-check 1 (Phil, HDMI-A-1, HEAD 1bafeae, 2026-10-17).** Items 4-7 pass. Findings, fixed in the new commits: (1) on a disable the corners still showed 90 degrees and the handle a default look: `css()` dropped the monitor's scope while its shell still faded in `_leaving`; fixed in a4452f7 (`css()` covers the leaving shells, refreshed when the last one goes). (2) The enable shrink at 50 ms was "much better but still too much": `RESERVE_DELAY_MS = 100` (4627cc8). (3) A rebuild crossfade with a maximized window (Thickness 10 to 64): the window shrank before the new frame fades in, because the successor of a held shell reserved at once: now every fading shell reserves 100 ms after its own fade-in starts, the held shell keeps its strips (`detach(keep_strips=True)`) and the successor's `on_reserved` makes the app drop them in the same call (4627cc8; `reserve_again` and `_reserves_now` removed). Re-check pending: items 3 and 4 and a rebuild with a maximized window.

## Self-review

1. **Request and decisions covered.** Fade-in on enable: Tasks 3-4 (built at 0, ready rule, the app opens with `fade_ms`). "Requires a full redraw": Task 5 (crossfade on `rebuild-monitor`, the decided behaviour), Task 6 (interruptions). "Draw off screen ... opacity 0": decision 3 (built and mapped at 0, the reason for not hiding). "Over 50ms": Task 1 (`fade_ms = 50`, 0-500, 0 off, per monitor, slider on General). "Blinks in then expands": the analysis above; the fade waits for the measurement and the re-raise (decision 4), the remaining candidates are gate items 2 and 4 and open questions 2 and 6. Fade out on disable: Task 4; on a normal quit: Task 4 (bounded). "Any random blinking would be an error": Global Constraints, gate items 2, 3, 9. Startup: each monitor fades in when ready (Task 4: every `_open_shell`). `--stats` and `shell.canvas.simulate` unaffected: decision 1, `test_shells_open_with_their_monitors_fade_and_none_while_measuring`. Restyle never fades: `test_a_restyle_never_fades` (Task 3), decision 11. Hot-plug during a fade: Tasks 4 and 6. Reload during a fade: Task 6. Failure paths: Tasks 2, 3, 5 (`test_a_failing_callback_never_breaks_the_fade`, `test_a_build_that_fails_after_the_canvas_leaves_no_fade_behind`, `test_a_held_shell_whose_successor_fails_to_build_fades_out`). Docs and the gate: Task 7; results: Task 8.
2. **Placeholder scan.** Every code step is a measured diff; every test step has its test code; every run step has its measured output; the gate items name the control, the action and the expected result. Task 8's text is Phil's results, which do not exist yet: its form and the rule for a failed item are given.
3. **Type consistency.** `Fade(ticker, set_opacity, duration_ms, timeout_add, source_remove, on_start=None)`, `ready()`, `fade_out(ms, on_done)`, `finish()`, `cancel()`, `state`, `value` (Task 2) are used by `MonitorShell` with those names (Task 3); `MonitorShell(..., fade_ms=, on_fade_in=)` (Task 3), `fade_state`, `fading_out`, `detach()`, `fade_out(ms, on_done)` (Task 4), `finish_fade()` (Task 6) are what `EdgeShellApp` and `FakeShell` use; `on_fade_in(shell)` is `EdgeShellApp._faded_in(shell)`; `on_done(shell)` is `EdgeShellApp._gone(shell)`; `plan.has_windows(config, name)` (Task 4) is used by `_reload` (Tasks 4-5); `unix_signal_add(priority, signum, handler, data)` is what the test replaces.
4. **Review Focus.** Each of the five lines has its pinning tests in the owning task (Tasks 2-6) and, where it is visible, a gate item. The reviewer mutation lists (40 mutations, each killed by the named test, measured on the final code) cover the lines a reviewer could otherwise approve untested.

## Open questions for Phil (each with the default this plan uses)

1. **The half-second wait before a monitor appears.** The fade starts after the panels' re-raise (about 0.5 s after enable or start), because the re-raise re-maps the panels and would blink after the fade. **Recommended default: as planned (wait).** Alternative: fade in at once (within a frame of the build) and accept one flicker of the handles at 0.5 s; or make the re-raise event-driven first (a separate investigation: the 50 ms attempt was too early at Gate 1).
2. **The 2 s fallback re-raise** still re-maps the panels once, after the fade (a possible single flicker of handles and content, gate item 2). **Recommended default: keep it** (it is the safety net for a slow compositor; without it the handles could stay hidden under the canvas). If the gate shows the flicker, drop the fallback while `fade_ms > 0` (two lines and a test).
3. **The crossfade's mid-way dim** (two half-transparent frames over each other cover 75 % at the midpoint; one frame at 50 ms). **Recommended default: as decided (new 0 -> 1 while old 1 -> 0).** Alternative if gate item 5 shows it: keep the old shell at full opacity under the new one and remove it when the new one is fully shown (no dim; but where the old frame is wider than the new, that part vanishes at the end instead of fading).
4. **Ctrl+C's exit status** becomes 130 (SIGTERM 143), and the windows are destroyed by the shell after its fade instead of by the process dying. **Recommended default: as planned.** Alternative: exit 0 after a fade-out quit (one line).
5. **(Fixed with the gate's fix commit: each strip is tracked as it is built.) The pre-existing strip leak** (a `FrameEdge` failing mid-build leaves the earlier strips untracked; found while writing Task 3's tests). **Recommended default: a small follow-up fix** (track each strip as it is built; about 3 lines and a test), not in this plan.
6. **(Answered by Phil's gate, finding 4: the strips are built after the fade-in starts; built 100 ms after, and a rebuild's held shell keeps its zone until then; see Task 8.) The reserved zone appears with the build, 0.5 s before the frame fades in** (maximized windows shrink before the frame is visible, gate item 4). **Recommended default: as planned**, decided after gate item 4. Alternative: build the strips at the start of the fade-in (and in a crossfade destroy the old strips then too), so the zone and the frame appear together (about one task: the strips move from `_build` to `_faded_in`, and the build-order test changes for `fade_ms > 0`).
7. **The bound 500 ms.** **Recommended default: 0-500** (the slider rule takes it; a longer fade reads as lag). Alternative: 0-1000 (a spin button instead of the slider).
