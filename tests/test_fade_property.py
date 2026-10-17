"""Property test of the shell fade (spec 21): the real EdgeShellApp, MonitorShell and Fade on
fake windows, a fake frame clock and a virtual-time GLib loop (no wall-clock sleeps). Seeded
random sequences of reloads, hot-plugs, resizes, starved frames and quit signals; after every
event no shell is orphaned, stacked or left half-visible, and in the end all is settled."""

import random
from types import SimpleNamespace

import pytest

pytest.importorskip("gi")
pytest.importorskip("fabric")

import shell.app as app_mod  # noqa: E402
import shell.monitors as mon_mod  # noqa: E402
from shell import plan  # noqa: E402
from shell.canvas.simulate import FakeClock, FakeTicker  # noqa: E402
from shell.config.models import Config  # noqa: E402
from tests.conftest import THEME  # noqa: E402

A, B = "HDMI-A-1", "HDMI-A-2"
ALL_WINDOWS: list = []


class Win:
    def __init__(self, *args, **kwargs):
        self.destroyed = 0
        self.opacity = []
        self.inputs = []
        self.natural = 200
        ALL_WINDOWS.append(self)

    def set_opacity(self, v):
        assert not self.destroyed, "opacity on a destroyed window"
        assert 0.0 <= v <= 1.0, v
        self.opacity.append(v)

    def set_input_enabled(self, e):
        self.inputs.append(e)

    def destroy(self):
        self.destroyed += 1

    def raise_to_top(self):
        assert not self.destroyed, "raise of a destroyed window"

    def apply_theme(self, theme):
        pass

    def set_state(self, s):
        pass

    def set_handle(self, h, i):
        pass

    def get_title(self):
        return "w"

    def natural_length(self):
        return self.natural


class Canvas(Win):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.ticker = FakeTicker()
        self.starved = False

    def add_tick_callback(self, fn):
        assert not self.destroyed, "tick callback on a destroyed canvas"
        return self.ticker.add_tick_callback(fn)

    def remove_tick_callback(self, i):
        self.ticker.remove_tick_callback(i)

    def set_theme(self, t):
        pass

    def add_panel(self, k, s):
        pass

    def remove_panel(self, k):
        pass

    def set_depth(self, k, d):
        pass


class Monitor:
    def __init__(self):
        self.handlers = {}
        self.n = 0
        self.width = 1920

    def get_geometry(self):
        return SimpleNamespace(x=0, y=0, width=self.width, height=1080)

    def connect(self, sig, fn):
        self.n += 1
        self.handlers[self.n] = fn
        return self.n

    def disconnect(self, h):
        del self.handlers[h]

    def get_scale_factor(self):
        return 1


class Loop:
    def __init__(self):
        self.now = 0.0
        self.timers = {}  # id -> (due, fn, args)
        self.idles = {}
        self.next = 1

    def timeout_add(self, ms, fn, *args):
        i, self.next = self.next, self.next + 1
        self.timers[i] = (self.now + ms, ms, fn, args)
        return i

    def idle_add(self, fn, *args):
        i, self.next = self.next, self.next + 1
        self.idles[i] = (fn, args)
        return i

    def source_remove(self, i):
        assert i in self.timers or i in self.idles, f"removed a gone source {i}"
        self.timers.pop(i, None)
        self.idles.pop(i, None)

    def run_idles(self):
        while self.idles:
            i = min(self.idles)
            fn, args = self.idles.pop(i)
            fn(*args)

    def advance(self, ms, canvases, clock):
        end = self.now + ms
        while True:
            self.run_idles()
            nxt = min(self.now + 16.667, end)
            due = sorted((d, i) for i, (d, *_r) in self.timers.items() if d <= nxt)
            for d, i in due:
                if i not in self.timers:
                    continue
                _, period, fn, args = self.timers.pop(i)
                self.now = max(self.now, d)
                if fn(*args):
                    self.timers[i] = (self.now + period, period, fn, args)
                self.run_idles()
            self.now = nxt
            clock.now_us = int(self.now * 1000)
            for c in list(canvases):
                if not c.destroyed and not c.starved:
                    c.ticker.run(clock)
            self.run_idles()
            if self.now >= end:
                return


def theme(fade, thick, color):
    return {**THEME, "fade_ms": fade, "thickness": thick, "frame": color}


def make_config(state):
    mons = {}
    for name in (A, B):
        s = state[name]
        panels = [{"panel": "edge", "name": "dock", "widget": "dock"}]
        if s["panels"] > 1:
            panels.append(
                {"panel": "edge", "name": "clock", "widget": "clock", "length": "content"}
            )
        mons[name] = {
            "shell": "edge" if s["on"] else "plasma",
            "panels": panels,
            "theme": {"fade_ms": s["fade"], "thickness": s["thick"], "frame": s["color"]},
        }
    return Config.model_validate({"theme": dict(THEME), "monitors": mons})


@pytest.fixture
def world(monkeypatch, fake_registry):
    ALL_WINDOWS.clear()
    loop = Loop()
    for mod in (mon_mod, app_mod):
        monkeypatch.setattr(mod.GLib, "timeout_add", loop.timeout_add)
        monkeypatch.setattr(mod.GLib, "idle_add", loop.idle_add)
        monkeypatch.setattr(mod.GLib, "source_remove", loop.source_remove)
    canvases = []

    def mk_canvas(*a, **k):
        c = Canvas()
        canvases.append(c)
        return c

    monkeypatch.setattr(mon_mod, "ShapeCanvas", mk_canvas)
    monkeypatch.setattr(mon_mod, "FrameEdge", Win)
    monkeypatch.setattr(mon_mod, "panel_class", lambda geo: Win)
    monkeypatch.setattr(mon_mod.MonitorShell, "_check_monitor", lambda self, w: None)
    monkeypatch.delenv("EDGE_SHELL_RAISE_MS", raising=False)
    created = []
    real_init = mon_mod.MonitorShell.__init__

    def init(self, *a, **k):
        created.append(self)
        real_init(self, *a, **k)

    monkeypatch.setattr(mon_mod.MonitorShell, "__init__", init)

    def no_popen(*a, **k):
        raise AssertionError("a process would be spawned")

    monkeypatch.setattr(app_mod.subprocess, "Popen", no_popen)
    monkeypatch.setattr(app_mod.EdgeShellApp, "_notify", lambda self, t, m: None)
    mapping = {}
    monkeypatch.setattr(app_mod, "monitors_by_name", lambda: dict(mapping))
    return SimpleNamespace(loop=loop, canvases=canvases, created=created, mapping=mapping)


class FakeApp:
    def __init__(self):
        self.windows = []
        self.quits = 0

    def add_window(self, w):
        self.windows.append(w)

    def remove_window(self, w):
        self.windows.remove(w)

    def quit(self):
        self.quits += 1

    def set_stylesheet_from_string(self, css, compile=False):
        pass


def check(app, w, fa, where):
    live = [s for s in w.created if not s._closed]
    # no orphan: every live shell is current or leaving
    known = {id(s) for s in app.shells.values()} | {id(s) for s in app._leaving.values()}
    for s in live:
        assert id(s) in known, f"{where}: orphan live shell {s.name} {s.fade_state}"
    for name, s in app._leaving.items():
        assert not s._closed, f"{where}: closed shell still in _leaving"
        assert s._detached, f"{where}: leaving shell not detached"
        assert s.fade_state in ("shown", "fading-out"), (where, s.fade_state)
        if s.fade_state == "shown":  # held: must have an invisible successor
            assert s.strips == [], f"{where}: held shell keeps strips (stacked zones)"
            succ = app.shells.get(name)
            assert succ is not None and succ.fade_state == "waiting", (
                f"{where}: held shell of {name} with successor "
                f"{None if succ is None else succ.fade_state}"
            )
    for s in app.shells.values():
        assert not s._closed and not s._detached
        assert s.fade_state in ("waiting", "fading-in", "shown"), (where, s.fade_state)
    per = {}
    for s in live:
        per.setdefault(s.name, []).append(s)
    for name, ss in per.items():
        assert len(ss) <= 2, f"{where}: {len(ss)} live shells on {name}"
        assert sum(s.fade_state == "fading-in" for s in ss) <= 1
        assert sum(s.fade_state == "fading-out" for s in ss) <= 1
    livewins = [win for s in live for win in s.windows]
    assert len({id(x) for x in livewins}) == len(livewins)
    for x in ALL_WINDOWS:
        assert x.destroyed <= 1, f"{where}: a window destroyed {x.destroyed} times"
    for x in livewins:
        assert x.destroyed == 0, f"{where}: a live shell holds a destroyed window"
    live_ids = {id(x) for x in livewins}
    for x in ALL_WINDOWS:
        if id(x) not in live_ids:
            assert x.destroyed == 1, f"{where}: a window of no live shell is not destroyed"
    assert sorted(map(id, fa.windows)) == sorted(live_ids), f"{where}: registered != live"
    for s in live:  # input follows visibility
        for p in s.live_panels():
            if p.inputs:
                want = s.fade_state in ("fading-in", "shown") and not s._detached
                if s.fade_state == "shown" and s._detached:
                    want = p.inputs[-1]  # held: keeps its input until fading out
                assert p.inputs[-1] == want, (where, s.fade_state, p.inputs)


EVENTS = [
    "rebuild",
    "off",
    "on",
    "restyle",
    "fade",
    "panels",
    "plug",
    "unplug",
    "replace",
    "resize",
    "starve",
    "tick",
    "tick",
    "tick",
    "tick",
    "quit",
]


def run_sequence(seed, w):
    rng = random.Random(seed)
    loop = w.loop
    clock = FakeClock()
    state = {
        n: {
            "on": True,
            "fade": rng.choice([0, 1, 50, 500]),
            "thick": 10,
            "color": "#0b0c0d",
            "panels": 1,
        }
        for n in (A, B)
    }
    store = SimpleNamespace(config=make_config(state), path=None, last_error=None, pending=None)

    def reload_():
        old, new = store.config, store.pending
        store.config = new
        return old, new

    store.reload = reload_
    app = app_mod.EdgeShellApp(store)
    fa = FakeApp()
    app.app = fa
    w.mapping[A] = Monitor()
    if rng.random() < 0.7:
        w.mapping[B] = Monitor()
    app.sync_monitors()
    log = []
    check(app, w, fa, "start")
    for step in range(rng.randint(5, 40)):
        ev = rng.choice(EVENTS)
        name = rng.choice((A, B))
        log.append((ev, name))
        where = f"seed {seed} step {step} {log}"
        s = state[name]
        if ev in ("rebuild", "off", "on", "restyle", "fade", "panels"):
            if ev == "rebuild":
                s["thick"] = 12 if s["thick"] == 10 else 10
            elif ev == "off":
                s["on"] = False
            elif ev == "on":
                s["on"] = True
            elif ev == "restyle":
                s["color"] = "#111111" if s["color"] == "#0b0c0d" else "#0b0c0d"
            elif ev == "fade":
                s["fade"] = rng.choice([0, 1, 50, 500])
            else:
                s["panels"] = 3 - s["panels"]
            store.pending = make_config(state)
            app.reload()
        elif ev == "plug":
            if name not in w.mapping:
                w.mapping[name] = Monitor()
            app._schedule_sync()
        elif ev == "unplug":
            if len(w.mapping) > 1 or rng.random() < 0.3:
                w.mapping.pop(name, None)
            app._schedule_sync()
        elif ev == "replace":
            if name in w.mapping:
                w.mapping[name] = Monitor()
            app._schedule_sync()
        elif ev == "resize":
            mon = w.mapping.get(name)
            if mon is not None:
                mon.width = rng.choice([1920, 2560])
                for fn in list(mon.handlers.values()):
                    fn()
        elif ev == "starve":
            for c in w.canvases:
                c.starved = rng.random() < 0.5
        elif ev == "tick":
            loop.advance(
                rng.choice([1, 10, 17, 40, 60, 300, 520, 610, 1100, 2600]), w.canvases, clock
            )
        elif ev == "quit":
            app._on_quit_signal(
                app_mod.signal.SIGINT if rng.random() < 0.5 else app_mod.signal.SIGTERM
            )
        if fa.quits:
            break
        check(app, w, fa, where)
    if not app._quitting and not fa.quits and rng.random() < 0.5:
        app._on_quit_signal(app_mod.signal.SIGINT)
    for c in w.canvases:
        c.starved = False if rng.random() < 0.5 else c.starved
    loop.advance(7000, w.canvases, clock)
    where = f"seed {seed} end {log}"
    assert fa.quits <= 1, where
    if app._quitting:
        assert fa.quits == 1, f"{where}: quit never happened"
        assert loop.timers == {} and loop.idles == {}, f"{where}: timers {loop.timers}"
        return
    check(app, w, fa, where)
    assert app._leaving == {}, f"{where}: leaving {list(app._leaving)}"
    for n, sh in app.shells.items():
        assert sh.fade_state == "shown", (where, n, sh.fade_state)
        for x in sh.windows:
            assert not x.opacity or x.opacity[-1] == 1.0, (where, x.opacity[-3:])
        for p in sh.live_panels():
            assert not p.inputs or p.inputs[-1] is True
    connected = {n: m for n, m in w.mapping.items()}
    want = set(plan.desired_shells(store.config, connected)) if connected else set(app.shells)
    assert set(app.shells) == want, (where, set(app.shells), want)
    for n, sh in app.shells.items():
        if connected:
            assert sh.monitor is w.mapping[n], where
    assert loop.timers == {} and loop.idles == {}, f"{where}: timers left {loop.timers}"
    for c in w.canvases:
        if not c.destroyed:
            assert c.ticker._callbacks == {}, f"{where}: tick callbacks left"


@pytest.mark.parametrize("seed", range(150))
def test_random_sequences(world, seed):
    run_sequence(seed, world)
