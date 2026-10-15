"""The settings window's content: the menu bar and the SettingsView (or, after File > Close, an
empty page with New and Open), with the window's actions (the "win" group the menu items and
the shortcuts use). A plain Gtk.Box, so it is tested without creating a window;
settings.window puts it in the toplevel. Every dialog goes through `dialogs`
(settings.dialogs), so tests answer with a fake and no dialog runs.

One window per config file: the window's application id is made from its file, so a window
never switches files. File > New, Open and Save As therefore open the chosen file in its own
window (`launch`, a new process, or the window already open on it) and close this one, after
the unsaved-changes question; choosing this window's own file shows it here."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib, Gtk

from settings.about import about_info
from settings.dialogs import Dialogs
from settings.fileops import (
    Answer,
    check_new,
    check_openable,
    create_new,
    default_folder,
    leave,
    new_name,
    new_path,
    same_file,
    save_copy,
)
from settings.launch import spawn_settings
from settings.menubar import build_menubar
from settings.menus import ACTIONS, clipboard_enabled, enabled, menu_state, window_title
from settings.session import ChangedOutside, SettingsSession
from settings.view import SettingsView
from shell.config.loader import USER_PATH
from shell.config.models import ConfigError
from shell.outputs import Output

log = logging.getLogger(__name__)


class SettingsController(Gtk.Box):
    def __init__(
        self,
        path: Path,
        session: SettingsSession,
        outputs: list[Output],
        dialogs: Dialogs,
        quit: Callable[[], None] | None = None,
        launch: Callable[[Path], None] = spawn_settings,
        user_path: Path = USER_PATH,
        on_title: Callable[[str], None] | None = None,
    ):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.path = path  # the window's file (its application id is made from it)
        self.default_path = session.default_path
        self.outputs = list(outputs)
        self.dialogs = dialogs
        self.quit = quit or (lambda: None)  # closes the window (File > Exit)
        self.launch = launch  # opens another file in its own window
        self.user_path = user_path  # the default config: the choosers start in its folder
        self._on_title = on_title or (lambda _t: None)  # the window's set_title
        self.title = ""
        self.session: SettingsSession | None = None
        self.view: SettingsView | None = None
        self._clipboard: dict[str, bool] | None = None
        # leaving after a flush that could not write (or met a hand edit) stays once, so the
        # error is seen; asked again, it goes on
        self._leave_warned = False
        self.handlers: dict[str, Callable[[], None]] = {
            "new": self.new,
            "open": self.open,
            "save": self.save,
            "save-as": self.save_as,
            "close": self.close_config,
            "exit": self.exit,
            "undo": self.undo,
            "redo": self.redo,
            "cut": lambda: self._clip("cut-clipboard"),
            "copy": lambda: self._clip("copy-clipboard"),
            "paste": lambda: self._clip("paste-clipboard"),
            "revert": self.revert,
            "about": lambda: self.dialogs.about(self.get_toplevel(), about_info()),
        }
        self.actions = Gio.SimpleActionGroup()
        for name in ACTIONS:
            if name in self.handlers:
                action = Gio.SimpleAction.new(name, None)
                action.connect("activate", lambda _a, _p, n=name: self.handlers[n]())
                self.actions.add_action(action)
        self.insert_action_group("win", self.actions)
        self.menubar, self.menus = build_menubar()
        # Cut, Copy and Paste follow the focused widget: refreshed when the Edit menu opens
        # (the window also refreshes them when the focus moves)
        self.menus["Edit"].connect("show", lambda _m: self.sync_clipboard())
        self.body = Gtk.Stack()
        self.body.add_named(self._empty_page(), "empty")
        self.pack_start(self.menubar, False, False, 0)
        self.pack_start(self.body, True, True, 0)
        self.open_session(session)

    def _empty_page(self) -> Gtk.Widget:
        """What the window shows with no config open (after File > Close)."""
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, valign=Gtk.Align.CENTER)
        title = Gtk.Label()
        title.set_markup("<big>No config open</big>")
        hint = Gtk.Label(label="Open a config file, or create a new one.")
        hint.get_style_context().add_class("dim-label")
        buttons = Gtk.Box(spacing=6, halign=Gtk.Align.CENTER)
        for label, action in (("_New…", "win.new"), ("_Open…", "win.open")):
            button = Gtk.Button.new_with_mnemonic(label)
            button.set_action_name(action)
            buttons.pack_start(button, False, False, 0)
        self.notice = Gtk.Label(wrap=True, selectable=True, max_width_chars=70)
        self.notice.set_no_show_all(True)  # only an error made with no config open shows here
        for child in (title, hint, buttons, self.notice):
            page.pack_start(child, False, False, 0)
        page.show_all()  # a Gtk.Stack only shows a visible child
        return page

    def open_session(self, session: SettingsSession) -> None:
        self._drop_view()
        self.session = session
        self._leave_warned = False
        self.view = SettingsView(
            session, self.outputs, confirm_revert=self.dialogs.confirm_revert, on_state=self.sync
        )
        self.view.use_undo_action("win.undo")  # the top bar's button is the menu's Undo
        self.body.add_named(self.view, "config")
        self.view.show_all()
        self.body.set_visible_child_name("config")
        self.notice.hide()
        if session.config is not None and not same_file(session.path, self.user_path):
            # the shell reads only its own file: say once (the next good edit hides it)
            self.view.show_banner(
                f"This is not the default config ({self.user_path}): a running shell uses "
                "these changes only if it was started with --config on this file.",
                Gtk.MessageType.INFO,
            )
        self.sync()

    def _drop_view(self) -> None:
        view, self.view, self.session = self.view, None, None
        if view is not None:
            view.cancel_deferred_rebuild()  # it would rebuild a view that is gone
            for row in view.rows:
                row.discard()
            self.body.remove(view)
            # destroyed when idle: an action can run inside a signal of a widget of this view
            GLib.idle_add(lambda: view.destroy() or GLib.SOURCE_REMOVE)
        self.body.set_visible_child_name("empty")

    def sync(self) -> None:
        """Every action's enabled state from the session (after each write, undo, revert,
        save or re-read; the view calls it after every refresh and rebuild)."""
        for name, ok in enabled(menu_state(self.session, self._clipboard)).items():
            action = self.actions.lookup_action(name)
            if action is not None:
                action.set_enabled(ok)
        session = self.session
        title = window_title(session and session.path, bool(session and session.dirty))
        if title != self.title:
            self.title = title
            self._on_title(title)

    def tell(self, text: str, kind: Gtk.MessageType = Gtk.MessageType.ERROR) -> None:
        """A message in the view's banner, or on the empty page when no config is open."""
        if self.view is not None:
            self.view.show_banner(text, kind)
        else:
            self.notice.set_text(text)
            self.notice.show()

    # ---- File ------------------------------------------------------------------------------
    def new(self) -> None:
        """File > New: choose a name (in the config folder), create the file with no keys,
        and open it in its own window (this one closes, after the unsaved question)."""
        folder = default_folder(self.user_path)
        path = self.dialogs.choose_new(self.get_toplevel(), folder, new_name(folder))
        if path is None:
            return
        path = new_path(path)
        try:
            check_new(path)  # before the unsaved question: a refusal never costs the edits
        except ConfigError as exc:
            self.tell(str(exc))
            return
        if not self.can_leave():
            return
        try:
            create_new(path)
        except ConfigError as exc:
            self.tell(str(exc))
            return
        self._switch_to(path)

    def open(self) -> None:
        """File > Open: open the chosen file in its own window (this one closes, after the
        unsaved question); this window's own file shows here."""
        path = self.dialogs.choose_open(self.get_toplevel(), default_folder(self.user_path))
        if path is None:
            return
        if self.session is not None and same_file(path, self.session.path):
            self.tell(f"{path} is already open in this window", Gtk.MessageType.INFO)
            return
        try:
            check_openable(path)
        except ConfigError as exc:
            self.tell(f"Cannot open it: {exc}")
            return
        if self.can_leave():
            self._switch_to(path)

    def save(self) -> None:
        if self.view is not None:
            self.view.save()
        self.sync()

    def save_as(self) -> None:
        """File > Save As: the current text is written to the chosen file (a file it replaces
        is kept as .before-save-as), this file goes back to its saved point (the changes now
        live in the copy), and the copy opens in its own window. This window's own file: Save."""
        if self.view is None:
            return
        self.view.flush()
        if self.view.refused_outside:
            return
        session = self.session
        target = self.dialogs.choose_save_as(
            self.get_toplevel(), default_folder(self.user_path), session.path.name
        )
        if target is None:
            return
        if same_file(target, session.path):
            self.save()
            return
        try:
            outside = session.changed_outside()  # the copy must match the file as it stands
        except ConfigError as exc:
            self.tell(f"Not saved: {exc}")
            return
        if outside:
            self.view.file_changed()  # re-read: the hand edit is shown
            self.tell(
                f"Nothing was saved as {target}: {session.path} was changed outside this "
                "window and has been re-read. Choose Save As again.",
                Gtk.MessageType.WARNING,
            )
            return
        try:
            kept = save_copy(session.path, session.text, target)
        except ConfigError as exc:
            self.tell(f"Not saved: {exc}")
            return
        if kept is not None:
            log.info("Save As kept the replaced %s as %s", target, kept)
        try:
            session.discard()
        except ConfigError as exc:  # also ChangedOutside: a hand edit, re-read
            self.view.rebuild()
            self.tell(
                f"Saved as {target}, but {session.path} was not put back as it was last "
                f"saved: {exc}",
                Gtk.MessageType.WARNING,
            )
            return
        self.view.rebuild()  # shown as last saved (if the new window cannot be started)
        self._switch_to(target)

    def close_config(self) -> None:
        """File > Close: after the unsaved question, the empty page (New, Open)."""
        if self.can_leave():
            self._drop_view()
            self.sync()

    def reopen(self) -> None:
        """Show this window's own file again (Open on it from the empty page, or a launch on
        it while no config is open: `main.py --settings`, a right-click on a panel handle)."""
        try:
            session = SettingsSession(self.path, self.default_path)
        except ConfigError as exc:
            self.tell(f"Cannot open it: {exc}")
            return
        self.open_session(session)

    def _switch_to(self, path: Path) -> None:
        """Leave this file for `path` (the unsaved question is answered): this window's own
        file shows here; another one opens in its own window and this one closes."""
        if same_file(path, self.path):
            self.reopen()
            return
        try:
            self.launch(path)
        except OSError as exc:
            self.tell(f"Cannot open a window for {path}: {exc}")
            return
        self.quit()

    def exit(self) -> None:
        if self.can_leave():
            self.quit()

    def can_leave(self) -> bool:
        """May the window leave its config (Close, Exit, New, Open, the close button)?
        Pending values are applied first; a flush that could not write, or met a hand edit,
        stays once (its message is on screen). With changes since the last save, asks Save /
        Discard / Cancel; a save or discard that fails is shown and stays."""
        if self.view is None:
            return True
        self.view.flush()
        if (self.view.save_failed or self.view.refused_outside) and not self._leave_warned:
            self._leave_warned = True
            return False
        session = self.session
        answers: list[Answer] = []

        def ask() -> Answer:
            answers.append(self.dialogs.ask_unsaved(self.get_toplevel(), session.path))
            return answers[-1]

        try:
            allowed = leave(session, ask)
            if allowed and Answer.DISCARD in answers:
                # the saved text is back in the file: the rows must show it too, in case the
                # window stays (a New or Open that then fails)
                self.view.rebuild()
            return allowed
        except ChangedOutside as exc:
            self.view.rebuild()
            self.view.show_banner(str(exc), Gtk.MessageType.WARNING)
            return False
        except ConfigError as exc:
            self.view.show_banner(f"Not saved: {exc}")
            return False
        finally:
            self.sync()

    # ---- Edit ------------------------------------------------------------------------------
    def undo(self) -> None:
        if self.view is not None:
            self.view.undo()

    def redo(self) -> None:
        if self.view is not None:
            self.view.redo()

    def revert(self) -> None:
        if self.view is not None:
            self.view.confirm_revert()

    def focus_widget(self) -> Gtk.Widget | None:
        """The window's focused widget (None outside a window, as in tests)."""
        top = self.get_toplevel()
        return top.get_focus() if isinstance(top, Gtk.Window) else None

    def sync_clipboard(self) -> None:
        """Cut, Copy and Paste from what the focused widget allows (a text entry or text view;
        anything else turns all three off)."""
        widget = self.focus_widget()
        if isinstance(widget, Gtk.Entry):  # also a spin button
            state = (True, widget.get_editable(), bool(widget.get_selection_bounds()))
        elif isinstance(widget, Gtk.TextView):
            state = (True, widget.get_editable(), widget.get_buffer().get_has_selection())
        else:
            state = (False, False, False)
        self._clipboard = clipboard_enabled(*state)
        self.sync()

    def _clip(self, signal: str) -> None:
        """Edit > Cut, Copy, Paste: the focused text widget's own clipboard signal, the one
        its Ctrl+X/C/V key binding emits (so the menu and the keys do exactly the same)."""
        widget = self.focus_widget()
        if isinstance(widget, Gtk.Entry | Gtk.TextView):
            widget.emit(signal)
        self.sync_clipboard()

    # ---- the file on disk ------------------------------------------------------------------
    def file_changed(self) -> None:
        if self.view is not None:
            self.view.file_changed()
