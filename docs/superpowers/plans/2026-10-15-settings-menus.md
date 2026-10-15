# Settings Menus and File Operations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the settings window a conventional menu bar (File: New, Open, Save, Save As, Close, Exit; Edit: Undo, Redo, Cut, Copy, Paste, Revert all; Help: About) with standard shortcuts, a saved point on top of live apply (Save, a `*` in the title, a Save / Discard / Cancel question before leaving a config with unsaved changes), native file dialogs and an empty window after Close.

**Architecture:** Pure logic first: `SettingsSession` gains redo and a saved point (`settings/session.py`), the menu bar is data with its shortcuts and enable rules (`settings/menus.py`), the unsaved-changes decision and the New/Open/Save As file operations are pure functions (`settings/fileops.py`), About reads `pyproject.toml` (`settings/about.py`), and starting a window on a file is shared with the shell (`settings/launch.py`). A thin GTK layer renders it: every dialog sits behind one small seam (`settings/dialogs.py`: a `Dialogs` protocol, `GtkDialogs` for real, a fake in tests), the menu bar is built from the data (`settings/menubar.py`), and a new `SettingsController` (`settings/controller.py`, a plain `Gtk.Box` holding the menu bar and the existing `SettingsView` or an empty page) owns the window's actions, so tests drive it without creating a window. `SettingsWindow` becomes a few lines around it. One window per config file stays: a window never switches files; New, Open and Save As open the chosen file in its own window (a new process, or the window already open on it) and close this one.

**Tech Stack:** Python 3.14 (>=3.12), PyGObject 3.50.0 (`<3.52`), GTK 3.24 (`Gtk.MenuBar`, `Gio.SimpleActionGroup`, `Gtk.Application` accelerators, `Gtk.FileChooserNative` through the desktop portal, `Gtk.MessageDialog`, `Gtk.AboutDialog`), tomlkit 0.15.1, pytest, ruff 0.17.0.

**Spec:** `docs/superpowers/specs/2026-10-14-panel-widget-model-design.md` section 6 (Plan 2, the contract), sections 1-2 (goal, plan order, gates on HDMI-A-1), 9-10 (risks, Phil's decisions: "Save model: live apply plus a saved point"); `docs/superpowers/specs/2026-10-11-edge-shell-design.md` section 13 (the settings window as built: single instance per config path, close applies pending edits via flush with keep-open-once on a failed write, backup once per session, `--restore-config`, invalid file read-only, `ChangedOutside`, the wheel guard). Style and earlier decisions: `docs/superpowers/plans/2026-10-14-settings-window.md`.

**Phil's request (verbatim):** "Top menu bar: File: New: Opens native save file dialog, user adds a name and save location. Defaults to applications already predetermined config location. Open: Opens native open file dialog, user opens a config file. Defaults to applications already predetermined config location. Save: Saves config and shows standard ctrl+s keybindings for saving. Save As: Opens a native save file as dialog. Defaults to applications already predetermined config location. Close: Closes currently open config. Prompts users to save if config has unsaved changes. Exit: Exits the settings window. Edit: Undo: same as current ctrl+z function as expected, show shortcut ctrl+z as a menu is expected to. Redo: opposite of undo, show standard shortcut for redo. Shortcut should work the same as the menu button. Cut: Work as expected, show ctrl+x shortcut. Shortcut should work. Copy: Work as expected, show ctrl+c shortcut. Shortcut should work. Paste: Work as expected, show ctrl+v shortcut. Shortcut should work. Revert all: performs the same function as current revert all button. About: Opens a dialog with application information."

**Decided with Phil before planning:** live apply stays (edits are still written to the file and applied by the shell at once); Save sets a saved point; Close, Exit, New, Open and the window's close button with changes since the last save ask Save / Discard / Cancel; Discard writes the saved-point text back (like Revert all, but to the saved point). The toolbar's Undo and Revert all buttons stay in this plan (plan 3 moves them); the menus add the same actions.

**Date:** 2026-10-15. **Size:** 11 tasks: 8 with code and tests (1-8), Task 9 docs and the gate checklist, Task 10 the live gate (Phil), Task 11 recording the results. Riskiest: Task 1 (every history path: apply, undo, redo, save, discard, revert, hand edits), Task 4 (the leave path: flush, keep-open-once, the question, failures), Task 6 (file operations that close this window and start another).

## Decisions (each marked *default pending Phil*, with the alternatives and their cost)

1. **Redo: a second stack in `SettingsSession`.** *Default pending Phil.* `history` stays the undo stack (the texts before each write); `redo_history` holds the texts an Undo replaced. Undo moves the current text onto `redo_history` and writes `history[-1]`; Redo is the mirror (one `_step(source, target)` does both). A written change clears `redo_history` (an edit that changes nothing writes nothing and keeps it). Revert all, Discard and a hand edit (`rebase`) clear both stacks: they are not undoable (as Revert all is today). Undo and Redo refuse after a hand edit exactly like Undo does today (`ChangedOutside`, re-read). **Pending values first:** `SettingsView.redo` flushes pending rows first, like `undo`; a pending value is a new change, so it ends the redo line and Redo then does nothing (pinned by `test_redo_applies_a_pending_value_first_which_ends_the_redo_line`). Rejected: (a) a full undo tree (branching redo): no user asked, costs a data structure and UI; (b) making Revert all undoable: changes today's "Revert all clears the history", one more stack entry and tests. *Cost if Phil wants Revert all undoable:* push the replaced text in `revert()` (3 lines, 2 tests).
2. **The saved point lives in the session.** *Default pending Phil.* `saved_text` is the text at open; `save()` sets it to the current text and copies the file to `config.toml.bak` (the spec's "refreshes the session `.bak`"; `backed_up` is set, so later changes of the session do not overwrite that copy, and `--restore-config` puts back the last saved state); `dirty` is `text != saved_text`, so an Undo back to the saved text is not dirty. `discard()` writes `saved_text` back when dirty and clears both stacks. **Hand edits:** any hand edit, valid or invalid, becomes the saved point (it was saved, in another editor), so Discard never writes over a hand edit and a window does not ask about changes it did not make. Save and Discard after a hand edit raise `ChangedOutside` (re-read). **Revert all keeps its meaning** (the file as the window opened it, or the last valid hand edit); Save does not move it, so Revert all after a Save makes the file dirty again (pinned by `test_revert_after_save_goes_to_the_start_and_is_dirty`). Rejected: (a) the saved point only in the window (the session would not know `dirty`; pure tests impossible); (b) a separate "saved" file next to the config (a second file to keep in step; `.bak` already is that copy). *Cost if Phil wants a hand edit to stay "unsaved":* one line in `rebase` and two tests; Discard would then need the `.before-revert` copy for an invalid hand edit.
3. **The menu bar is data.** *Default pending Phil.* `settings/menus.py` holds `MENUS` (labels with mnemonics, action names, shortcuts), `ACCELS` (what `SettingsApp` registers), `MenuState` and `enabled(state)`: New, Open, Exit, About always; Save, Save As, Close and Undo need an open config (Save and Undo do not wait for unsaved changes or a history: a value typed but not yet applied is no change in the session yet, and both apply it first); Redo needs something to redo; Revert all needs the text to differ from Revert all's start (not the history: an invalid hand edit has no history but can be reverted). `settings/menubar.py` builds `Gtk.MenuItem`s that are `Gtk.Actionable` on `win.<action>` (they follow the action's enabled state) and shows the first shortcut with the item's `Gtk.AccelLabel`. **About is under Help** (Help > About Edge Shell), the desktop convention; the spec lists About next to File and Edit. *Cost if Phil wants a top-level "About" menu:* change one `Menu` label and two test lines.
4. **Shortcuts and text fields.** *Default pending Phil.* New Ctrl+N, Open Ctrl+O, Save Ctrl+S, Save As Shift+Ctrl+S, Close Ctrl+W, Exit Ctrl+Q, Undo Ctrl+Z, Redo Shift+Ctrl+Z and Ctrl+Y are application accelerators (`Gtk.Application.set_accels_for_action`), so they work with the focus anywhere in the window. GTK 3 activates application accelerators before the focused widget sees the key, and only when the action is enabled (a disabled action lets the key through). **Ctrl+Z in a text field is the document's Undo** (as today): GTK 3 entries have no undo of their own; the typed value is applied first and then undone (today's `undo` flush). **Cut, Copy, Paste are shown (Ctrl+X/C/V) but not registered:** the focused widget's own key bindings do the work, so the keys behave exactly as GTK's (also in a selectable label, which the menu items do not cover), and the menu items emit the same widget signals (`cut-clipboard`, `copy-clipboard`, `paste-clipboard`) on the focused `Gtk.Entry` (spin buttons included) or `Gtk.TextView`. The items are enabled by `clipboard_enabled(text_focused, editable, selected)` and refreshed when the Edit menu opens (`show`) and when the window's focus moves (`set-focus`, after the default handler). Rejected: (a) registering Ctrl+X/C/V as accelerators: they would be swallowed in a selectable label and duplicate GTK's own behaviour; (b) entry-local undo: GTK 3 has none, it would be a new feature. *Cost if Phil wants Ctrl+Z inside a text field to undo only the typing:* a per-entry undo buffer (about half a task).
5. **One window per file: New, Open and Save As close this window.** *Default pending Phil.* The application id is per config path (settings plan decision 14), so a window never retargets: the id is fixed when the process registers. The spec asks both for "Open on another path opens that path in a second window" and for New and Open to ask Save / Discard / Cancel; read together: the chosen file opens in its own window (`settings.launch.spawn_settings`: `main.py --settings --config PATH` in a new session; if that file already has a window, it only comes forward) and this window closes, after the question, so the user sees the window switch files. Choosing this window's own file shows it here (Open: "already open"; from the empty page: shown again). Rejected: (a) retargeting this window (the app id cannot change: a later launch on the old file would raise a window showing another file, and one on the new file would open a second window on it); (b) one process for every file (breaks "one window per file" through the id). *Cost if Phil wants the old window to stay open next to the new one:* drop `self.quit()` and the question in `_switch_to`/`open`/`new` (3 lines, 3 tests).
6. **Save As = copy, put this file back to its saved point, open the copy.** *Default pending Phil.* The current text (pending values applied first) is written to the chosen file; a file it replaces (the native dialog asks first) is kept as `NAME.before-save-as` (`.2`, `.3`, ... like `.before-restore`), a new file gets the source's mode (a private config stays private). This file then goes back to its saved point (`discard`: the changes now live in the copy, as in any editor) and the copy opens in its own window. Save As onto this window's own file is Save. **The running shell** reads only its own path; if this window was on the shell's file, the shell shows that file's saved state afterwards (the gate checks it). *Cost if Phil prefers to keep the live changes in this file too:* drop the `discard()` call (1 line, 1 test).
7. **New never replaces a file.** *Default pending Phil.* The chooser starts in `~/.config/edge-shell` (created when missing; the home folder if it cannot be) with a free name (`config.toml`, `config-2.toml`, ...); an existing path (or a dangling symlink) is refused with "already exists; New never replaces a file", the native dialog's own overwrite question is off; missing folders are created; the file holds one comment line (`NEW_TEXT`, valid TOML with no keys: every value is a default; the spec's "empty file"). Rejected: confirm and keep the replaced file as `.before-new` (a destructive action behind a "New" item). *Cost:* none.
8. **Close leaves an empty window.** *Default pending Phil.* After the question, the view is dropped (its rows' pending timers are discarded, the widgets destroyed when idle, as rebuilds do) and an empty page shows "No config open" with New and Open buttons (actionable on `win.new`/`win.open`); Save, Save As, Close, Undo, Redo, Revert all are disabled; the title is "Edge Shell settings". The window keeps its application id (its path): a launch on that file (`main.py --settings`, a right-click on a panel handle) shows the file again (`SettingsApp.do_activate` calls `controller.reopen()`), and Open of that file from the empty page shows it here. The file watcher stays and does nothing while no config is open. The toolbar and the pages are simply not shown (plan 3 moves the toolbar; nothing of it is reachable here).
9. **The dialogs seam.** *Default pending Phil.* `settings.dialogs.Dialogs` (a `typing.Protocol`): `ask_unsaved(parent, path) -> Answer`, `confirm_revert(parent, text) -> bool`, `choose_new(parent, folder, name)`, `choose_open(parent, folder)`, `choose_save_as(parent, folder, name)` (each `-> Path | None`), `about(parent, info)`. `GtkDialogs` implements it with `Gtk.MessageDialog` (Save is the default button, Discard is styled `destructive-action`, Escape and the close button answer Cancel), `Gtk.FileChooserNative` (filters "TOML files" and "All files"; a non-local pick returns None) and `Gtk.AboutDialog`. The Revert all confirmation moves from `SettingsView._confirm_revert` into the seam (`SettingsView(confirm_revert=...)`, public `confirm_revert()`), so the toolbar button and Edit > Revert all share it. A test checks that `GtkDialogs` has every protocol method with the same signature; no test runs a dialog.
10. **Native file dialogs through the portal.** *Default pending Phil.* GTK 3's `FileChooserNative` uses the desktop portal (on Plasma: KDE's own dialog) only when `GTK_USE_PORTAL=1` (or inside a sandbox); without it, it shows GTK's own dialog. `main.py --settings` sets `os.environ.setdefault("GTK_USE_PORTAL", "1")` before GTK starts (the variable is read once, at the first use), so only the settings process (and the windows it starts) is affected; `GTK_USE_PORTAL=0` in the environment keeps GTK's dialog. Risk: with the portal on, GDK may also take its settings (theme, fonts) from the portal; Gate item 15 compares both. *Cost if the gate shows a changed look:* drop the line (GTK's dialog then).
11. **The shell's config path.** *Default pending Phil.* The window cannot know which file a running shell reads; it says what is true: a window on a file other than the default config (`~/.config/edge-shell/config.toml`) shows once, in its info banner, "This is not the default config (...): a running shell uses these changes only if it was started with --config on this file." (the next good edit hides it, as for any banner). No shell control is added. `main.py` changes only the `--restore-config` help text and the portal line; the shell's right-click (`shell/app.py`) keeps its behaviour: `settings_command` moves to `settings/launch.py` (no GTK, no Fabric) and `shell/app.py` imports it from there, so the window and the shell start settings windows the same way.
12. **Window title:** the file (`~/` for the home folder), a leading `*` while it has unsaved changes, then " - Edge Shell settings"; just "Edge Shell settings" with no config open (`menus.window_title`). Updated from `SettingsController.sync`, which the view calls after every refresh and rebuild (`on_state`).
13. **About:** name "Edge Shell", version from the checkout's `pyproject.toml` at run time (the shell runs from its checkout, not installed; fallback `importlib.metadata.version("edge-shell")`, then "unknown"), comments = the project description plus "Built with Fabric (Python, GTK 3).", website `https://github.com/mindderivative/edge-shell` (the git remote), authors from `[project].authors` or else `mindderivative` (the repository owner), licence from a `LICENSE`/`LICENSE.txt`/`LICENSE.md`/`COPYING` file next to `pyproject.toml`, else `[project].license`, else the installed package's metadata licence, else "No licence has been chosen for Edge Shell yet." (Phil chose MIT: the repository now has an MIT `LICENSE` file and About shows it; `test_this_checkout_is_mit_licensed`. The fallbacks matter only for a checkout without it. Open questions 4 and 5 are answered.)
14. **Errors:** a chooser path in a missing folder (New, Save As) creates the folder; a folder that cannot be written, a binary or unreadable file (Open), a missing file: one line in the banner (or on the empty page), never an exception in a GTK callback; a text file that is not a valid config opens read-only with its error, as at start; a window that cannot be started (`OSError`) is reported and this window stays. tomlkit missing: unchanged (`run_settings` prints the install command first). The mouse wheel guard (`settings/fields.py`) is not touched.
15. **Testing:** every new GTK test drives `SettingsController` (a `Gtk.Box`) or plain widgets with a fake `Dialogs`, a fake `launch` and a fake `quit`; none creates a window, runs a dialog, spawns a process or touches the real clipboard (clipboard tests record and stop the widget's signal). The existing window tests in `tests/test_settings_app.py` (which build `SettingsWindow` without showing it, as before) are adjusted, not extended. Mutation lists are given per task for the reviewer.

## Prerequisites

- Branch `feat/settings-menus` from `origin/main` at `70cf965` (the settings window and the panel/widget model are merged), in the worktree `/home/phil/Projects/pyDev/projects/myShell/.claude/worktrees/feat-edge-shell-core`.
- Baseline before Task 1: `scripts/py -m pytest -q` prints `2159 passed` (warnings are normal); `scripts/py -m ruff check .` prints `All checks passed!`.
- tomlkit is installed in the shared venv: `scripts/py -c 'import tomlkit; print(tomlkit.__version__)'` prints `0.15.1`. If it fails, STOP and report (the session, view and controller tests would skip, and a skipped test must not read as green). Nobody installs packages.
- Always stage files by name, never `git add -A` or `git add .`.

## Global Constraints

- Python only through `scripts/py` (shared venv `/home/phil/Projects/pyDev/pyEnvs/global-base`). **PyGObject must stay `<3.52`** (Fabric 0.0.2 breaks on 3.52+).
- **Pure modules import no GTK / `gi`:** `settings/session.py`, `settings/menus.py`, `settings/fileops.py`, `settings/about.py`, `settings/launch.py` (it imports `gi.repository.GLib` only inside `spawn_settings`), and as before `settings/form.py`, `settings/values.py`, `settings/files.py`, `settings/document.py`. `settings/files.py` stays stdlib-only (no tomlkit), so `--restore-config` works without tomlkit.
- **The settings process never imports Fabric or `widgets` from its modules** (`test_the_settings_process_never_imports_fabric_windows` must stay green): `settings/launch.py` must not import `shell.app`.
- **The settings window writes only:** the config file it shows, its `.bak`, `.before-revert` (as before), and for the File menu the file chosen in New or Save As and `NAME.before-save-as` next to a file Save As replaces. Never `config.default.toml`.
- **Tests.** CI installs only pycairo, pydantic, pytest, ruff and tomlkit: tests importing `gi` or `fabric` start with `pytest.importorskip("gi")` / `pytest.importorskip("fabric")`; tests needing tomlkit `pytest.importorskip("tomlkit")`. GTK tests call `gi.require_version("Gtk", "3.0")` and `gi.require_version("Gdk", "3.0")` before importing `gi.repository`, skip unless `Gtk.init_check()[0]`, and **never create a window, run a dialog, spawn a process or use the real clipboard**: plain widgets, `SettingsView` and `SettingsController` boxes, a fake `Dialogs`, fake `launch` and `quit`. Never call `Gtk.Application.run` or `Gio.Application.register` in a test.
- **Lint.** `ruff` 0.17.0, line length 100, rules E, F, I, UP, B; excludes `docs/` and `*.md`. Import blocks: stdlib, third-party (`gi`, `tomlkit`, `pydantic`), first-party (`settings`, `shell`, `widgets`); `ruff check --fix` sorts them.
- **VERIFY** (before every commit): `scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q`. The suite must be green at the end of EVERY task (0 failed) with exactly the total in the File Structure table.
- **Git.** Plain separate git commands run from the worktree (no `cd … && git`, no command substitution around git). Stage files by name. **Never push.** Every commit message ends with a second `-m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`.
- **Live runs.** Phil is the only visual tester, on `HDMI-A-1` only. **Never touch `DP-1`** (it holds the Plasma panel; never set it to `edge` or `both`, in a file or in the window). Subagents executing tasks never launch the shell or the settings window (`main.py` without `--list-outputs`, including `--settings`), never open a window or a dialog; headless commands are fine (`pytest`, `scripts/py -c` checks). The gate (Task 10) is run by Phil.

## Review Focus

The five failure modes most likely to bite Phil that the spec implies but a happy-path test would not catch, each pinned by tests in the owning task:

1. **Leaving a config with unsaved changes** (Close, Exit, the close button, New, Open), including a value still pending in a spin button's 0.4 s pause or a typed font list without Enter: expect the pending value applied first, then Save / Discard / Cancel; Cancel changes nothing and stays; Discard puts the last saved text back (the shell follows); a save or discard that fails is shown and the window stays; a flush that met a hand edit or could not write stays open once (today's keep-open-once). Pinned by `test_cancel_stays_and_changes_nothing`, `test_discard_puts_the_saved_file_back` (Task 3), `test_a_pending_value_counts_as_a_change_when_leaving`, `test_exit_with_unsaved_changes_asks_and_cancel_stays`, `test_exit_discard_puts_the_saved_file_back_and_quits`, `test_leaving_stays_open_once_after_a_refused_flush`, `test_a_failed_save_is_shown_and_keeps_the_changes_unsaved` (Task 4), `test_close_with_unsaved_changes_asks_and_cancel_keeps_the_config`, `test_open_asks_about_unsaved_changes_first` (Task 6); live by Gate items 6-7.
2. **A hand edit meets the saved point** (Phil edits the file in an editor while the window has unsaved changes): expect the hand edit never overwritten by Discard, Save or Redo; it counts as saved (no question about it); a Discard that meets it re-reads and says "nothing was discarded". Pinned by `test_a_hand_edit_is_the_saved_point` (valid and invalid), `test_discard_never_writes_over_a_hand_edit`, `test_save_after_a_hand_edit_rereads_it_as_saved`, `test_redo_after_a_hand_edit_rereads_instead` (Task 1), `test_a_hand_edit_met_by_discard_raises_and_is_kept` (Task 3), `test_a_discard_that_meets_a_hand_edit_stays_and_says_so` (Task 4); live by Gate item 13.
3. **Shortcuts while the cursor is in a text field:** Ctrl+X/C/V must do what they always did in an entry (never swallowed, never acting on the wrong widget), Ctrl+Z undoes the document after applying the typed value, and Edit > Cut/Copy/Paste must act on the focused field only and be greyed out elsewhere. Pinned by `test_clipboard_shortcuts_are_shown_but_left_to_the_focused_widget`, `test_clipboard_enabled` (Task 2), `test_activation_sets_the_undo_accel_watches_the_file_and_presents_once` (copy has no accelerator, Task 4), `test_cut_copy_and_paste_follow_the_focused_entry`, `test_the_items_emit_the_focused_widgets_own_clipboard_signals`, `test_with_no_text_focused_the_items_do_nothing`, `test_opening_the_edit_menu_refreshes_cut_copy_and_paste` (Task 7); live by Gate items 4-5.
4. **A bad choice in a file dialog** (New on an existing file or a dangling symlink, Open of a binary, a folder or a missing file, Save As into a read-only folder or over an existing file, this window's own file): expect nothing destroyed (New refuses, Save As keeps the replaced file as `.before-save-as`), one line in the banner, no exception in a GTK callback, and this window's own file handled in place. Pinned by `test_new_never_replaces_a_file`, `test_new_in_an_unwritable_folder_is_an_error`, `test_check_openable`, `test_save_as_writes_the_text_and_keeps_a_replaced_file`, `test_save_as_of_a_private_config_is_private`, `test_save_as_into_an_unwritable_folder_is_an_error` (Task 5), `test_new_never_replaces_a_file` (controller), `test_open_refuses_a_file_it_cannot_read`, `test_open_of_this_windows_own_file_only_says_so`, `test_save_as_onto_this_file_is_save`, `test_an_error_on_the_empty_page_is_shown_there`, `test_a_window_that_cannot_be_started_is_shown_and_this_one_stays` (Task 6); live by Gate items 9-11.
5. **Which file the shell reads, and one window per file:** opening or creating another file must not silently retarget this window (the app id is per path), a closed window must come back on its own file when launched again, and a window on a file the shell may not read must say so. Pinned by `test_open_shows_another_file_in_its_own_window_and_closes_this_one`, `test_open_from_the_empty_page_shows_this_windows_file_here`, `test_a_launch_on_a_window_with_no_config_open_shows_its_file_again`, `test_save_as_copies_the_changes_and_puts_this_file_back_as_last_saved` (Task 6), `test_spawn_starts_its_own_session_and_reaps_the_child`, `test_the_shell_uses_the_same_command` (Task 5), `test_a_config_other_than_the_default_says_so_once`, `test_the_default_config_has_no_note` (Task 8); live by Gate items 1, 7-9.

## File Structure

```
settings/session.py           # MODIFY (Task 1): redo_history, saved_text, dirty, redo, save, discard
settings/menus.py             # NEW, PURE (Task 2): Item, Menu, MENUS, ACTIONS, ACCELS, MenuState,
                              #   clipboard_enabled, menu_state, enabled; (Task 8) TITLE, window_title
settings/fileops.py           # NEW, PURE (Task 3): Answer, unsaved_question, leave; (Task 5) NEW_TEXT,
                              #   default_folder, new_name, same_file, create_new, check_openable, save_copy
settings/dialogs.py           # NEW, GTK (Task 3): Dialogs protocol, GtkDialogs; (Task 8) about
settings/view.py              # MODIFY: confirm_revert seam (Task 3); on_state, redo, save (Task 4)
main.py                       # MODIFY: GTK_USE_PORTAL (Task 3); --restore-config help text (Task 9)
settings/menubar.py           # NEW, GTK (Task 4): build_menubar
settings/controller.py        # NEW, GTK (Task 4): SettingsController; file ops + empty page (Task 6);
                              #   clipboard (Task 7); title, About, other-file note (Task 8)
settings/window.py            # MODIFY: thin wrapper around the controller (Task 4); set-focus (Task 7);
                              #   title (Task 8)
settings/app.py               # MODIFY: ACCELS (Task 4); reopen an empty window on launch (Task 6)
settings/files.py             # MODIFY (Task 5): keep_copy (keep_before_revert uses it)
settings/launch.py            # NEW (Task 5): MAIN_PATH, settings_command (moved), spawn_settings
shell/app.py                  # MODIFY (Task 5): imports settings_command / MAIN_PATH from settings.launch
settings/about.py             # NEW, PURE (Task 8): AboutInfo, about_info
settings/__init__.py, README.md, examples/settings-test.toml,
docs/superpowers/specs/2026-10-14-panel-widget-model-design.md,
docs/superpowers/specs/2026-10-11-edge-shell-design.md            # Tasks 9, 11
tests/test_settings_saved_point.py, tests/test_settings_menus.py, tests/test_settings_fileops.py,
tests/test_settings_dialogs.py, tests/test_settings_controller.py, tests/test_settings_launch.py,
tests/test_settings_about.py                                        # NEW
tests/test_main_settings.py (Task 3), tests/test_settings_app.py (Tasks 4, 6, 8),
tests/test_settings_view.py (Task 4: one test moves to the controller)   # MODIFY
```

| Task | Deliverable | Expected `pytest -q` (measured on a scratch copy) | Keeps the suite green because |
| --- | --- | --- | --- |
| 1 | session redo, saved point, dirty, save, discard | 2178 passed (+19) | new methods; existing behaviour unchanged |
| 2 | `settings/menus.py` | 2200 passed (+22) | new module |
| 3 | `fileops.leave`, the dialogs seam, revert through it, portal | 2210 passed (+10) | the view's default is the same dialog |
| 4 | menu bar, controller, window actions, accels | 2224 passed (+15, -1 moved) | the window keeps its interface (`view`, `file_changed`) |
| 5 | pure file operations, `settings/launch.py` | 2237 passed (+13) | the shell imports the moved command |
| 6 | New, Open, Save As, Close, empty page, reopen | 2252 passed (+15) | new actions |
| 7 | Cut, Copy, Paste | 2257 passed (+5) | new actions |
| 8 | About, title, other-file note | 2269 passed (+12) | new module; one existing title assertion updated |
| 9 | README, spec, example header, help text, gate checklist | 2269 passed | docs only |
| 10 | Gate (Phil, live on HDMI-A-1) | 2269 passed | no code |
| 11 | Record the results | 2269 passed | docs only |

Without a display the GTK test files skip as whole modules (`test_settings_controller.py`) or per test (`test_settings_dialogs.py`'s view tests, the window tests in `test_settings_app.py`); without tomlkit the session, saved-point and controller files skip. CI has neither `gi` nor a display: the pure files (`test_settings_menus.py` except the accelerator-parse test, `test_settings_fileops.py` except the session tests, `test_settings_about.py`, `test_settings_launch.py` except the gi/fabric tests) run there.

---

### Task 1: Redo and the saved point in `SettingsSession`

**Files:**
- Modify: `settings/session.py` (whole file below)
- Test: `tests/test_settings_saved_point.py` (new)

**Interfaces:**
- Consumes: `settings.files.write_atomic`, `write_backup`, `backup_path`, `read_text`, `keep_before_revert` (unchanged).
- Produces: `SettingsSession.redo_history: list[str]`, `SettingsSession.saved_text: str`, `SettingsSession.dirty -> bool` (property), `SettingsSession.redo() -> bool`, `SettingsSession.save() -> None`, `SettingsSession.discard() -> None` (both raise `ChangedOutside` after a hand edit, `ConfigError` when a write fails). `apply` clears `redo_history`; `revert`, `discard` and `rebase` clear both stacks; `rebase` sets `saved_text`.

- [ ] **Step 1: Write the failing test** `tests/test_settings_saved_point.py`:

```python
"""settings.session: redo, the saved point (Save, dirty, Discard) and how hand edits, Revert all
and the backup meet them (pure)."""

import pytest

pytest.importorskip("tomlkit")

from settings import files  # noqa: E402
from settings.session import ChangedOutside, SettingsSession  # noqa: E402
from shell.config.models import ConfigError  # noqa: E402

USER = """\
# test config
[monitors.HDMI-A-1]
shell = "edge"   # test monitor

[[monitors.HDMI-A-1.panels]]
panel = "edge"
name = "dock"
widget = "dock"
"""
SHELL = ("monitors", "HDMI-A-1", "shell")
DEPTH = ("monitors", "HDMI-A-1", "panels", 0, "depth")
BROKEN = '[monitors.HDMI-A-1]\nshell = "sideways"\n'


@pytest.fixture
def path(tmp_path, fake_registry):
    p = tmp_path / "config.toml"
    p.write_text(USER)
    return p


def bak(path):
    return path.with_name("config.toml.bak")


def test_redo_puts_back_what_undo_replaced(path):
    s = SettingsSession(path)
    s.apply(lambda d: d.set(DEPTH, 80))
    one = path.read_text()
    s.apply(lambda d: d.set(SHELL, "both"))
    two = path.read_text()
    s.undo()
    s.undo()
    assert path.read_text() == USER and len(s.redo_history) == 2
    assert s.redo() is True
    assert path.read_text() == one and s.text == one
    assert s.redo() is True
    assert path.read_text() == two and s.config.monitor("HDMI-A-1").shell == "both"
    assert s.redo() is False and len(s.history) == 2
    assert s.undo() is True and path.read_text() == one  # and back again


def test_a_new_change_ends_the_redo_line(path):
    s = SettingsSession(path)
    s.apply(lambda d: d.set(DEPTH, 80))
    s.undo()
    s.apply(lambda d: d.set(SHELL, "both"))
    assert s.redo_history == [] and s.redo() is False
    assert "depth" not in path.read_text()


def test_an_edit_that_changes_nothing_keeps_the_redo_line(path):
    s = SettingsSession(path)
    s.apply(lambda d: d.set(DEPTH, 80))
    s.undo()
    s.apply(lambda d: d.set(SHELL, "edge"))  # already "edge": nothing is written
    assert s.redo() is True and "depth = 80" in path.read_text()


def test_redo_after_a_hand_edit_rereads_instead(path):
    s = SettingsSession(path)
    s.apply(lambda d: d.set(DEPTH, 80))
    s.undo()
    hand = USER + "# by hand\n"
    path.write_text(hand)
    with pytest.raises(ChangedOutside):
        s.redo()
    assert path.read_text() == hand and s.redo_history == [] and s.history == []


def test_revert_ends_the_redo_line(path):
    s = SettingsSession(path)
    s.apply(lambda d: d.set(DEPTH, 80))
    s.apply(lambda d: d.set(SHELL, "both"))
    s.undo()
    s.revert()
    assert path.read_text() == USER and s.redo_history == [] and s.redo() is False


def test_a_new_session_is_clean_and_a_change_makes_it_dirty(path):
    s = SettingsSession(path)
    assert not s.dirty and s.saved_text == USER
    s.apply(lambda d: d.set(DEPTH, 80))
    assert s.dirty


def test_undo_back_to_the_saved_text_is_not_dirty(path):
    s = SettingsSession(path)
    s.apply(lambda d: d.set(DEPTH, 80))
    s.undo()
    assert not s.dirty
    s.redo()
    assert s.dirty


def test_save_moves_the_saved_point_and_refreshes_the_backup(path):
    s = SettingsSession(path)
    s.apply(lambda d: d.set(DEPTH, 80))
    assert bak(path).read_text() == USER  # the first change's backup
    s.save()
    saved = path.read_text()
    assert not s.dirty and s.saved_text == saved and bak(path).read_text() == saved
    s.apply(lambda d: d.set(SHELL, "both"))
    assert s.dirty and bak(path).read_text() == saved  # later changes keep the saved copy
    s.undo()
    assert not s.dirty  # back at the saved point


def test_save_before_any_change_backs_up_the_file(path):
    s = SettingsSession(path)
    s.save()
    assert bak(path).read_text() == USER and s.backed_up
    s.apply(lambda d: d.set(DEPTH, 80))
    assert bak(path).read_text() == USER


def test_save_of_a_session_without_a_file(tmp_path, fake_registry):
    path = tmp_path / "config.toml"
    s = SettingsSession(path)
    s.save()  # nothing on disk yet: no copy, nothing to fail
    assert not bak(path).exists() and not s.dirty
    s.apply(lambda d: d.set(SHELL, "edge"))
    assert s.dirty
    s.save()
    assert bak(path).read_text() == path.read_text() and not s.dirty


def test_a_failed_save_moves_nothing(path, monkeypatch):
    s = SettingsSession(path)
    s.apply(lambda d: d.set(DEPTH, 80))

    def boom(_path):
        raise PermissionError("denied")

    monkeypatch.setattr(files, "write_backup", boom)
    with pytest.raises(ConfigError, match=r"cannot write .*config\.toml\.bak"):
        s.save()
    assert s.dirty and s.saved_text == USER


def test_discard_writes_the_saved_point_back(path):
    s = SettingsSession(path)
    s.apply(lambda d: d.set(DEPTH, 80))
    s.save()
    saved = path.read_text()
    s.apply(lambda d: d.set(SHELL, "both"))
    s.apply(lambda d: d.set(SHELL, "none"))
    s.discard()
    assert path.read_text() == saved and s.text == saved and not s.dirty
    assert s.history == [] and s.redo_history == []
    assert s.config.monitor("HDMI-A-1").panels[0].depth == 80


def test_discard_of_a_clean_session_writes_nothing(path):
    s = SettingsSession(path)
    inode = path.stat().st_ino
    s.discard()
    assert path.stat().st_ino == inode and path.read_text() == USER


def test_discard_without_a_save_goes_back_to_the_opened_file(path):
    s = SettingsSession(path)
    s.apply(lambda d: d.set(DEPTH, 80))
    s.discard()
    assert path.read_text() == USER


@pytest.mark.parametrize("hand", [USER + "# valid hand work\n", BROKEN])
def test_a_hand_edit_is_the_saved_point(path, hand):
    s = SettingsSession(path)
    s.apply(lambda d: d.set(DEPTH, 80))
    path.write_text(hand)
    s.rebase()
    assert not s.dirty and s.saved_text == hand


def test_save_after_a_hand_edit_rereads_it_as_saved(path):
    s = SettingsSession(path)
    s.apply(lambda d: d.set(DEPTH, 80))
    hand = USER + "# by hand\n"
    path.write_text(hand)
    with pytest.raises(ChangedOutside, match="saved state now"):
        s.save()
    assert not s.dirty and s.text == hand
    assert bak(path).read_text() == USER  # the copy was not refreshed


def test_discard_never_writes_over_a_hand_edit(path):
    s = SettingsSession(path)
    s.apply(lambda d: d.set(DEPTH, 80))
    path.write_text(BROKEN)  # an invalid hand edit: it must survive a Discard
    with pytest.raises(ChangedOutside, match="nothing was discarded"):
        s.discard()
    assert path.read_text() == BROKEN and not s.dirty
    s.discard()  # asked again: nothing to do
    assert path.read_text() == BROKEN


def test_revert_after_save_goes_to_the_start_and_is_dirty(path):
    """Revert all keeps its meaning (the file as the window opened it); Save does not move it."""
    s = SettingsSession(path)
    s.apply(lambda d: d.set(DEPTH, 80))
    s.save()
    s.revert()
    assert path.read_text() == USER and s.dirty
```

- [ ] **Step 2: Run it to verify it fails**

Run: `scripts/py -m pytest tests/test_settings_saved_point.py -q`
Expected: FAIL, 19 failed, with `AttributeError: 'SettingsSession' object has no attribute 'redo_history'` (or `'redo'`, `'saved_text'`, `'dirty'`, `'save'`, `'discard'`).

- [ ] **Step 3: Write the implementation.** Replace `settings/session.py` with:

```python
"""One settings-window session on the user config file. Pure (no GTK).

Every change is applied to the file's current text with settings.document, checked with the
shell's own rules (shell.config.loader + registry.validate_widgets) and only then written,
atomically; the running shell picks it up through its file watcher. A change the shell would
reject is never written. Before the first write of a session the file is copied to
config.toml.bak (`main.py --restore-config` puts it back).

The saved point (File > Save): live apply stays, every change is still written at once. Save
records the current text as the saved point and copies the file to config.toml.bak; the
session is `dirty` while its text differs from the saved point (an Undo back to it is not
dirty). Discard writes the saved point back. A hand edit, valid or not, becomes the saved
point: it was saved, in another editor, so Discard never writes over it.

Limits, by design: the file is read with universal newlines, so the first edit rewrites CRLF
line endings as LF (the .bak stays byte-exact) and `changed_outside` cannot see a hand edit
that only changes line endings. When the config file is missing at open, an older
config.toml.bak from a previous session survives (the first write only backs up an existing
file), and `--restore-config` would restore that older file. An edit that raises something
other than ConfigError escapes `apply` (UserDocument wraps the realistic ones). A file that
is invalid when the session opens has no valid baseline: Revert all would only rewrite it, so
the window offers the hand fix or `--restore-config` instead.
"""

from __future__ import annotations

import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Any

from settings import files
from settings.document import UserDocument
from shell.config.loader import DEFAULT_PATH, load_config_text
from shell.config.models import Config, ConfigError
from shell.registry import validate_widgets

Edit = Callable[[UserDocument], Any]


class ChangedOutside(ConfigError):
    """The file changed on disk since the session last read it (edited by hand); the
    session has re-read it and the change was not applied."""


def check_text(text: str, default_path: Path = DEFAULT_PATH) -> Config:
    """The config `text` would give, by the shell's rules; ConfigError naming the key path."""
    config = load_config_text(text, default_path)
    validate_widgets(config)
    return config


class SettingsSession:
    def __init__(self, path: Path, default_path: Path = DEFAULT_PATH):
        self.path = path
        self.default_path = default_path
        self.history: list[str] = []  # texts before each write, for undo
        self.redo_history: list[str] = []  # texts an undo (or redo) replaced, for redo
        self.backed_up = False
        self.start_text = ""
        self.text = ""
        self.user: dict[str, Any] = {}  # the user file as plain data
        self.config: Config | None = None  # None while the file on disk is invalid
        self.error: str | None = None  # why the file on disk is invalid
        self.reload()
        # An invalid file at open has no valid baseline; keep its text so Revert all is a no-op
        # (a later valid hand edit becomes the baseline through rebase).
        self.start_text = self.text
        self.saved_text = self.text  # the saved point: Save moves it, Discard writes it back

    @property
    def dirty(self) -> bool:
        """The file differs from the saved point (Close, Exit, New and Open ask first)."""
        return self.text != self.saved_text

    def reload(self) -> None:
        """(Re)read the file. An invalid file is kept as it is: `error` says why, `config` is
        None and edits are still allowed (an edit that fixes the file is written)."""
        self.text = files.read_text(self.path)
        try:
            self.user = tomllib.loads(self.text)
        except tomllib.TOMLDecodeError:
            self.user = {}
        try:
            self.config, self.error = check_text(self.text, self.default_path), None
        except ConfigError as exc:
            self.config, self.error = None, str(exc)

    def changed_outside(self) -> bool:
        return files.read_text(self.path) != self.text

    def rebase(self) -> None:
        """Re-read a file that was changed outside the window (a hand edit): a valid hand edit
        becomes the new starting point (Revert all goes back to it, never past it) and the
        undo and redo histories, which led to a file that no longer exists, are cleared. An
        INVALID hand edit does not: the last valid baseline stays, so Revert all (confirmed by
        the user) is a way out of a broken file instead of rewriting the same broken text.
        Any hand edit, valid or not, is the new saved point (it was saved, in an editor)."""
        self.reload()
        self.history.clear()
        self.redo_history.clear()
        self.saved_text = self.text
        if self.config is not None:
            self.start_text = self.text

    def apply(self, edit: Edit) -> Config:
        """Apply one change and write it; returns the new config. Raises ChangedOutside (the
        session re-read the file: a new baseline) or ConfigError (nothing written). A written
        change ends the redo line."""
        if self.changed_outside():
            self.rebase()
            raise ChangedOutside(
                f"{self.path} was changed outside the settings window; it has been re-read "
                "and the last change was not applied"
            )
        doc = UserDocument(self.text)
        edit(doc)
        config = check_text(doc.text, self.default_path)
        if doc.text == self.text:
            return config  # nothing changed: no backup, no write, no do-nothing undo step
        if not self.backed_up:
            backup = files.backup_path(self.path.resolve())
            self._write_file(lambda: files.write_backup(self.path), backup)
            self.backed_up = True
        self._write_file(lambda: files.write_atomic(self.path, doc.text))
        self.history.append(self.text)
        self.redo_history.clear()
        self.text, self.user = doc.text, tomllib.loads(doc.text)
        self.config, self.error = config, None
        return config

    def undo(self) -> bool:
        """Put back the text before the last change; False when there is nothing to undo."""
        return self._step(self.history, self.redo_history)

    def redo(self) -> bool:
        """Put back the text the last Undo replaced; False when there is nothing to redo
        (a new change, Revert all, Discard or a hand edit ends the redo line)."""
        return self._step(self.redo_history, self.history)

    def _step(self, source: list[str], target: list[str]) -> bool:
        """Write the last text of `source`; the text it replaces goes onto `target`."""
        if not source:
            return False
        if self.changed_outside():
            self.rebase()
            raise ChangedOutside(f"{self.path} was changed outside the settings window")
        self._write_file(lambda: files.write_atomic(self.path, source[-1]))
        source.pop()
        target.append(self.text)
        self.reload()
        return True

    def save(self) -> None:
        """File > Save: the current text becomes the saved point and the file is copied to
        config.toml.bak (what `--restore-config` puts back; later changes of this session do
        not overwrite that copy). Refused, with ChangedOutside, after a hand edit (re-read: it
        is the saved point now). A copy that cannot be written moves nothing."""
        if self.changed_outside():
            self.rebase()
            raise ChangedOutside(
                f"{self.path} was changed outside the settings window; it has been re-read "
                "and is the saved state now"
            )
        backup = files.backup_path(self.path.resolve())
        self._write_file(lambda: files.write_backup(self.path), backup)
        self.backed_up = True
        self.saved_text = self.text

    def discard(self) -> None:
        """Back to the saved point (Close, Exit, New or Open with unsaved changes, answered
        Discard): the saved text is written back, like Revert all but to the saved point, and
        both histories are cleared. Refused, with ChangedOutside, after a hand edit (which is
        then the saved point: nothing is left to discard)."""
        if self.changed_outside():
            self.rebase()
            raise ChangedOutside(
                f"{self.path} was changed outside the settings window; it has been re-read "
                "and nothing was discarded"
            )
        if self.dirty:
            self._write_file(lambda: files.write_atomic(self.path, self.saved_text))
        self.history.clear()
        self.redo_history.clear()
        self.reload()

    def keeps_hand_edit(self) -> bool:
        """True when Revert all would replace an invalid hand edit (it has no valid baseline
        of its own), which is then kept as config.toml.before-revert."""
        return self.config is None and self.text != self.start_text

    def revert(self) -> None:
        """Back to the file as it was when the session started, or when it was last changed
        by hand (no validation: it was the file on disk). An invalid hand edit being replaced is
        first kept as config.toml.before-revert (if that cannot be written, nothing changes).
        Refused, with ChangedOutside, when the file was changed by hand since the last read:
        that hand edit becomes the start. Clears both histories (Revert all is not undone)."""
        if self.changed_outside():
            self.rebase()
            raise ChangedOutside(
                f"{self.path} was changed outside the settings window; Revert all keeps that "
                "change (it is the new starting point)"
            )
        if self.start_text != self.text:
            if self.keeps_hand_edit():  # the only copy of that text: keep it first
                self._write_file(lambda: files.keep_before_revert(self.path))
            self._write_file(lambda: files.write_atomic(self.path, self.start_text))
        self.history.clear()
        self.redo_history.clear()
        self.reload()

    def _write_file(self, write: Callable[[], Any], target: Path | None = None) -> None:
        """Run one file write; an OSError (read-only folder, disk full) is a ConfigError the
        window shows, never an exception inside a GTK callback."""
        try:
            write()
        except OSError as exc:
            raise ConfigError(f"cannot write {target or self.path}: {exc}") from None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `scripts/py -m pytest tests/test_settings_saved_point.py tests/test_settings_session.py -q`
Expected: PASS, `57 passed`.

- [ ] **Step 5: VERIFY**

Run: `scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q`
Expected: `All checks passed!`, `2178 passed`.

Reviewer mutations (each must fail at least one test in `tests/test_settings_saved_point.py`; all were checked on a scratch copy): drop `self.redo_history.clear()` in `apply`; move `self.saved_text = self.text` in `rebase` inside the `if self.config is not None:` block; drop `self.backed_up = True` in `save`; drop the `if self.dirty:` guard in `discard` (always write); skip the `changed_outside` check in `discard`; drop `self.redo_history.clear()` in `revert`; make `dirty` compare with `start_text`; make `redo` step onto `redo_history` itself.

- [ ] **Step 6: Commit**

```bash
git add settings/session.py tests/test_settings_saved_point.py
git commit -m "feat(settings): redo and a saved point in the session (Save, dirty, Discard)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 2: The menu bar as data: `settings/menus.py`

**Files:**
- Create: `settings/menus.py`
- Test: `tests/test_settings_menus.py` (new)

**Interfaces:**
- Consumes: nothing (duck-typed session: `dirty`, `history`, `redo_history`, `text`, `start_text`).
- Produces: `Item(label: str, action: str, accels: tuple[str, ...] = (), bound: bool = True)`, `Menu(label: str, items: tuple[Item | None, ...])`, `MENUS: tuple[Menu, ...]`, `ACTIONS: tuple[str, ...]` (13 names: `new open save save-as close exit undo redo cut copy paste revert about`), `ACCELS: dict[str, list[str]]` (`"win.<action>" -> accels`, bound items only), `MenuState(open, dirty, can_undo, can_redo, can_revert, cut, copy, paste)` (all `bool = False`), `clipboard_enabled(text_focused: bool, editable: bool, selected: bool) -> dict[str, bool]`, `menu_state(session, clipboard: dict[str, bool] | None = None) -> MenuState`, `enabled(state: MenuState) -> dict[str, bool]`.

- [ ] **Step 1: Write the failing test** `tests/test_settings_menus.py`:

```python
"""settings.menus: the menu bar as data, its accelerators and when each item works (pure)."""

from types import SimpleNamespace

import pytest

from settings.menus import (
    ACCELS,
    ACTIONS,
    MENUS,
    MenuState,
    clipboard_enabled,
    enabled,
    menu_state,
)


def plain(label):
    return label.replace("_", "").rstrip("…")


def test_the_menus_follow_phils_list():
    assert [plain(m.label) for m in MENUS] == ["File", "Edit", "Help"]
    assert [[plain(i.label) if i else "-" for i in m.items] for m in MENUS] == [
        ["New", "Open", "-", "Save", "Save As", "-", "Close", "Exit"],
        ["Undo", "Redo", "-", "Cut", "Copy", "Paste", "-", "Revert all"],
        ["About Edge Shell"],
    ]


def test_every_action_is_named_once():
    assert len(ACTIONS) == len(set(ACTIONS)) == 13


def test_the_accelerators():
    assert ACCELS == {
        "win.new": ["<Primary>n"],
        "win.open": ["<Primary>o"],
        "win.save": ["<Primary>s"],
        "win.save-as": ["<Primary><Shift>s"],
        "win.close": ["<Primary>w"],
        "win.exit": ["<Primary>q"],
        "win.undo": ["<Primary>z"],
        "win.redo": ["<Primary><Shift>z", "<Primary>y"],
    }


def test_clipboard_shortcuts_are_shown_but_left_to_the_focused_widget():
    items = {i.action: i for m in MENUS for i in m.items if i}
    for action, accel in (("cut", "<Primary>x"), ("copy", "<Primary>c"), ("paste", "<Primary>v")):
        assert items[action].accels == (accel,) and not items[action].bound
        assert f"win.{action}" not in ACCELS


def test_no_shortcut_is_used_twice():
    accels = [a for m in MENUS for i in m.items if i for a in i.accels]
    assert len(accels) == len(set(accels))


def test_mnemonics_are_unique_within_each_menu():
    def key(label):
        return label[label.index("_") + 1].lower()

    assert len({key(m.label) for m in MENUS}) == len(MENUS)
    for menu in MENUS:
        keys = [key(i.label) for i in menu.items if i]
        assert len(keys) == len(set(keys)), menu.label


def test_every_shortcut_is_a_valid_gtk_accelerator():
    gi = pytest.importorskip("gi")
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk

    for accel in (a for m in MENUS for i in m.items if i for a in i.accels):
        key, mods = Gtk.accelerator_parse(accel)
        assert key != 0, accel


def test_with_no_config_open_only_new_open_exit_and_about_work():
    on = {name for name, ok in enabled(MenuState()).items() if ok}
    assert on == {"new", "open", "exit", "about"}
    assert set(enabled(MenuState())) == set(ACTIONS)


@pytest.mark.parametrize(
    "state, on",
    [
        (MenuState(open=True), {"save-as", "close"}),
        (MenuState(open=True, dirty=True), {"save", "save-as", "close"}),
        (MenuState(open=True, can_undo=True), {"save-as", "close", "undo"}),
        (MenuState(open=True, can_redo=True), {"save-as", "close", "redo"}),
        (MenuState(open=True, can_revert=True), {"save-as", "close", "revert"}),
        (MenuState(open=True, copy=True, paste=True), {"save-as", "close", "copy", "paste"}),
        (MenuState(open=False, dirty=True, can_undo=True, can_revert=True), set()),
    ],
)
def test_items_follow_the_state(state, on):
    always = {"new", "open", "exit", "about"}
    assert {name for name, ok in enabled(state).items() if ok} == always | on


@pytest.mark.parametrize(
    "focused, editable, selected, cut, copy, paste",
    [
        (False, False, False, False, False, False),  # a button or nothing has the focus
        (False, True, True, False, False, False),
        (True, True, False, False, False, True),  # an entry, nothing selected
        (True, True, True, True, True, True),
        (True, False, True, False, True, False),  # a read-only text: copy only
        (True, False, False, False, False, False),
    ],
)
def test_clipboard_enabled(focused, editable, selected, cut, copy, paste):
    assert clipboard_enabled(focused, editable, selected) == {
        "cut": cut,
        "copy": copy,
        "paste": paste,
    }


def session(**kw):
    base = dict(dirty=False, history=[], redo_history=[], text="a", start_text="a")
    return SimpleNamespace(**(base | kw))


def test_menu_state_reads_the_session():
    assert menu_state(None) == MenuState()
    assert menu_state(None, {"cut": False, "copy": True, "paste": False}) == MenuState(copy=True)
    assert menu_state(session()) == MenuState(open=True)
    state = menu_state(session(dirty=True, history=["x"], redo_history=["y"], text="b"))
    assert state == MenuState(open=True, dirty=True, can_undo=True, can_redo=True, can_revert=True)
    # Revert all follows the text, not the history: an invalid hand edit has no history but
    # can be reverted; a change typed back to the start has history but nothing to revert
    assert menu_state(session(text="b")).can_revert
    assert not menu_state(session(history=["x"])).can_revert
```

- [ ] **Step 2: Run it to verify it fails**

Run: `scripts/py -m pytest tests/test_settings_menus.py -q`
Expected: collection ERROR, `ModuleNotFoundError: No module named 'settings.menus'`.

- [ ] **Step 3: Write the implementation** `settings/menus.py`:

```python
"""The settings window's menu bar as data, and when each item can be used. Pure (no GTK):
settings.menubar builds the Gtk.MenuBar from MENUS, settings.app registers ACCELS, and the
window sets each action's enabled state from `enabled(menu_state(...))`.

Every item names an action of the window's "win" group. `accels` are GTK accelerator
strings; the first one is shown next to the item. A `bound` item's accels are registered as
application accelerators (they work wherever the focus is in the window, a text entry
included: Ctrl+Z is the document's Undo, the entries have no undo of their own). Cut, Copy and
Paste are not bound: Ctrl+X/C/V stay the focused widget's own key bindings, which do exactly
what the menu items do, also in a selectable label the menu items do not cover."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Item:
    label: str  # with a mnemonic underscore
    action: str  # the action's name in the window's "win" group
    accels: tuple[str, ...] = ()
    bound: bool = True  # False: shown only; the focused widget's own key binding does it


@dataclass(frozen=True)
class Menu:
    label: str
    items: tuple[Item | None, ...]  # None: a separator


MENUS: tuple[Menu, ...] = (
    Menu(
        "_File",
        (
            Item("_New…", "new", ("<Primary>n",)),
            Item("_Open…", "open", ("<Primary>o",)),
            None,
            Item("_Save", "save", ("<Primary>s",)),
            Item("Save _As…", "save-as", ("<Primary><Shift>s",)),
            None,
            Item("_Close", "close", ("<Primary>w",)),
            Item("E_xit", "exit", ("<Primary>q",)),
        ),
    ),
    Menu(
        "_Edit",
        (
            Item("_Undo", "undo", ("<Primary>z",)),
            Item("_Redo", "redo", ("<Primary><Shift>z", "<Primary>y")),
            None,
            Item("Cu_t", "cut", ("<Primary>x",), bound=False),
            Item("_Copy", "copy", ("<Primary>c",), bound=False),
            Item("_Paste", "paste", ("<Primary>v",), bound=False),
            None,
            Item("Re_vert all…", "revert"),
        ),
    ),
    Menu("_Help", (Item("_About Edge Shell", "about"),)),
)

ACTIONS: tuple[str, ...] = tuple(i.action for m in MENUS for i in m.items if i is not None)
# "win.save" -> ["<Primary>s"]: what SettingsApp passes to Gtk.Application.set_accels_for_action
ACCELS: dict[str, list[str]] = {
    f"win.{i.action}": list(i.accels)
    for m in MENUS
    for i in m.items
    if i is not None and i.bound and i.accels
}


@dataclass(frozen=True)
class MenuState:
    """What the items depend on: a config is open (not the empty window after Close), it has
    changes since the last save, there is something to undo, redo or revert, and what the
    focused widget allows for Cut, Copy and Paste (clipboard_enabled)."""

    open: bool = False
    dirty: bool = False
    can_undo: bool = False
    can_redo: bool = False
    can_revert: bool = False
    cut: bool = False
    copy: bool = False
    paste: bool = False


def clipboard_enabled(text_focused: bool, editable: bool, selected: bool) -> dict[str, bool]:
    """Cut needs an editable text widget with a selection, Copy a selection, Paste an editable
    text widget; with no text widget focused (a button, a combo box, nothing) all three are
    off."""
    return {
        "cut": text_focused and editable and selected,
        "copy": text_focused and selected,
        "paste": text_focused and editable,
    }


def menu_state(session: Any, clipboard: dict[str, bool] | None = None) -> MenuState:
    """The MenuState of a SettingsSession (None: no config open)."""
    clip = clipboard or {}
    if session is None:
        return MenuState(**clip)
    return MenuState(
        open=True,
        dirty=session.dirty,
        can_undo=bool(session.history),
        can_redo=bool(session.redo_history),
        can_revert=session.text != session.start_text,
        **clip,
    )


def enabled(state: MenuState) -> dict[str, bool]:
    """Action name -> enabled, for every action in MENUS. New, Open, Exit and About always
    work; Save needs changes since the last save; Save As and Close need an open config;
    Undo, Redo and Revert all need something to undo, redo or revert."""
    return {
        "new": True,
        "open": True,
        "save": state.open and state.dirty,
        "save-as": state.open,
        "close": state.open,
        "exit": True,
        "undo": state.open and state.can_undo,
        "redo": state.open and state.can_redo,
        "cut": state.cut,
        "copy": state.copy,
        "paste": state.paste,
        "revert": state.open and state.can_revert,
        "about": True,
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `scripts/py -m pytest tests/test_settings_menus.py -q`
Expected: PASS, `22 passed`.

- [ ] **Step 5: VERIFY**

Run: `scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q`
Expected: `All checks passed!`, `2200 passed`.

Reviewer mutations (each must fail a test in `tests/test_settings_menus.py`): `"save": state.open` (no dirty check); `"cut": text_focused and editable` (no selection check); Redo without `"<Primary>y"`; Copy with `bound` left at True; `"revert": state.can_revert` (without `state.open`); `can_revert=bool(session.history)`.

- [ ] **Step 6: Commit**

```bash
git add settings/menus.py tests/test_settings_menus.py
git commit -m "feat(settings): the menu bar as data: items, shortcuts and when each works" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 3: The unsaved-changes decision, the dialogs seam, native file dialogs

**Files:**
- Create: `settings/fileops.py`, `settings/dialogs.py`
- Modify: `settings/view.py` (constructor, the Revert all button, `_confirm_revert` -> `confirm_revert`), `main.py` (the portal line)
- Test: `tests/test_settings_fileops.py` (new), `tests/test_settings_dialogs.py` (new), `tests/test_main_settings.py` (one test)

**Interfaces:**
- Consumes: Task 1 `SettingsSession.dirty`, `save()`, `discard()`.
- Produces: `fileops.Answer` (`SAVE`, `DISCARD`, `CANCEL`), `fileops.unsaved_question(path: Path) -> tuple[str, str]`, `fileops.leave(session, ask: Callable[[], Answer]) -> bool` (raises what `save`/`discard` raise); `dialogs.Dialogs` protocol: `ask_unsaved(parent, path) -> Answer`, `confirm_revert(parent, text: str) -> bool`, `choose_new(parent, folder: Path, name: str) -> Path | None`, `choose_open(parent, folder: Path) -> Path | None`, `choose_save_as(parent, folder: Path, name: str) -> Path | None`; `dialogs.GtkDialogs` (the real one); `SettingsView(session, outputs, confirm_revert: Callable[[Any, str], bool] | None = None)`, `SettingsView.revert_button`, `SettingsView.confirm_revert() -> None`.

- [ ] **Step 1: Write the failing tests.** `tests/test_settings_fileops.py`:

```python
"""settings.fileops: leaving a config with unsaved changes (pure; the question is a callable)."""

from pathlib import Path

import pytest

from settings.fileops import Answer, leave, unsaved_question

USER = '[monitors.HDMI-A-1]\nshell = "edge"\n'
SHELL = ("monitors", "HDMI-A-1", "shell")


@pytest.fixture
def session(tmp_path, fake_registry):
    pytest.importorskip("tomlkit")
    from settings.session import SettingsSession

    path = tmp_path / "config.toml"
    path.write_text(USER)
    return SettingsSession(path)


def asker(answer):
    asked = []

    def ask():
        asked.append(answer)
        return answer

    ask.asked = asked
    return ask


def test_a_clean_config_is_left_without_a_question(session):
    ask = asker(Answer.CANCEL)
    assert leave(session, ask) is True and ask.asked == []


def test_cancel_stays_and_changes_nothing(session):
    session.apply(lambda d: d.set(SHELL, "both"))
    ask = asker(Answer.CANCEL)
    assert leave(session, ask) is False and ask.asked == [Answer.CANCEL]
    assert session.dirty and 'shell = "both"' in session.path.read_text()


def test_save_keeps_the_changes_as_the_saved_point(session):
    session.apply(lambda d: d.set(SHELL, "both"))
    assert leave(session, asker(Answer.SAVE)) is True
    assert not session.dirty and 'shell = "both"' in session.path.read_text()
    assert 'shell = "both"' in session.path.with_name("config.toml.bak").read_text()


def test_discard_puts_the_saved_file_back(session):
    session.apply(lambda d: d.set(SHELL, "both"))
    assert leave(session, asker(Answer.DISCARD)) is True
    assert session.path.read_text() == USER and not session.dirty


def test_a_hand_edit_met_by_discard_raises_and_is_kept(session):
    from settings.session import ChangedOutside

    session.apply(lambda d: d.set(SHELL, "both"))
    session.path.write_text(USER + "# by hand\n")
    with pytest.raises(ChangedOutside):
        leave(session, asker(Answer.DISCARD))
    assert session.path.read_text().endswith("# by hand\n")
    assert leave(session, asker(Answer.DISCARD)) is True  # now clean: no question


def test_the_question_names_the_file():
    primary, secondary = unsaved_question(Path("/home/p/.config/edge-shell/config.toml"))
    assert primary == "Save the changes to config.toml?"
    assert "/home/p/.config/edge-shell/config.toml" in secondary and "Discard" in secondary
```

`tests/test_settings_dialogs.py`:

```python
"""settings.dialogs: the seam (no dialog ever runs here) and the view's Revert all through it."""

import inspect

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from settings.dialogs import Dialogs, GtkDialogs  # noqa: E402


def test_the_real_dialogs_have_the_seams_methods():
    for name, member in inspect.getmembers(Dialogs, inspect.isfunction):
        if name.startswith("_"):
            continue
        real = getattr(GtkDialogs, name)
        assert inspect.signature(real) == inspect.signature(member), name


@pytest.fixture
def view(tmp_path, fake_registry):
    pytest.importorskip("tomlkit")
    from gi.repository import Gtk

    if not Gtk.init_check()[0]:
        pytest.skip("no display")
    from settings.session import SettingsSession
    from settings.view import SettingsView

    path = tmp_path / "config.toml"
    path.write_text('[monitors.HDMI-A-1]\nshell = "edge"\n')
    asked = []
    answer = {"ok": False}

    def confirm(_parent, text):
        asked.append(text)
        return answer["ok"]

    v = SettingsView(SettingsSession(path), [], confirm_revert=confirm)
    v.asked, v.answer, v.path = asked, answer, path
    return v


def test_revert_all_asks_through_the_seam_and_cancel_keeps_the_change(view):
    view._on_change(("monitors", "HDMI-A-1", "shell"), "both")
    view.revert_button.emit("clicked")
    assert len(view.asked) == 1 and "goes back to how it was" in view.asked[0]
    assert 'shell = "both"' in view.path.read_text()


def test_revert_all_confirmed_reverts(view):
    view._on_change(("monitors", "HDMI-A-1", "shell"), "both")
    view.answer["ok"] = True
    view.confirm_revert()
    assert view.path.read_text() == '[monitors.HDMI-A-1]\nshell = "edge"\n'
```

In `tests/test_main_settings.py`, add above `def test_restore_config_puts_the_backup_back`:

```python
def test_settings_asks_gtk_for_the_native_file_dialogs(tmp_path, opened, monkeypatch):
    import os

    cfg = str(tmp_path / "c.toml")
    monkeypatch.setenv("GTK_USE_PORTAL", "0")  # a user's own choice wins
    main_mod.main(["--settings", "--config", cfg])
    assert os.environ["GTK_USE_PORTAL"] == "0"
    monkeypatch.delenv("GTK_USE_PORTAL")
    main_mod.main(["--settings", "--config", cfg])
    assert os.environ["GTK_USE_PORTAL"] == "1"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `scripts/py -m pytest tests/test_settings_fileops.py tests/test_settings_dialogs.py tests/test_main_settings.py -q`
Expected: collection ERRORs (`ModuleNotFoundError: No module named 'settings.fileops'` / `'settings.dialogs'`) and `KeyError: 'GTK_USE_PORTAL'` in the main test.

- [ ] **Step 3: Write the implementation.** `settings/fileops.py`:

```python
"""File-menu decisions without GTK: what happens to unsaved changes when the window leaves a
config (Close, Exit, New, Open, Save As, the window's close button). Pure: the questions are
asked through a callable, so tests answer them and no dialog runs."""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from pathlib import Path
from typing import Any


class Answer(Enum):
    SAVE = "save"
    DISCARD = "discard"
    CANCEL = "cancel"


def unsaved_question(path: Path) -> tuple[str, str]:
    """The unsaved-changes dialog's two lines."""
    return (
        f"Save the changes to {path.name}?",
        f"{path} has changes since it was last saved. They are already applied to the "
        "file (and to a shell that reads it). Save keeps them; Discard puts the file back "
        "as it was last saved.",
    )


def leave(session: Any, ask: Callable[[], Answer]) -> bool:
    """May the window leave `session`'s config? True at once when nothing changed since the
    last save; otherwise `ask` decides: Save (the saved point moves to the current text),
    Discard (the saved text is written back) or Cancel (False: stay). A failed save or
    discard raises (ConfigError, or ChangedOutside after a hand edit): the caller shows it
    and stays."""
    if not session.dirty:
        return True
    answer = ask()
    if answer is Answer.CANCEL:
        return False
    if answer is Answer.SAVE:
        session.save()
    else:
        session.discard()
    return True
```

`settings/dialogs.py`:

```python
"""The settings window's dialogs, behind one small seam: the window and the view get a `Dialogs`
object and never build a dialog themselves, so tests pass a fake and no dialog ever runs
there. `GtkDialogs` is the real one: native file choosers (Gtk.FileChooserNative: KDE's own
dialog through the desktop portal, main.py sets GTK_USE_PORTAL=1 for the settings process) and
modal message dialogs. Each method runs its dialog to the end and returns the answer."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from settings.fileops import Answer, unsaved_question

TOML_FILTERS = (("TOML files", "*.toml"), ("All files", "*"))


class Dialogs(Protocol):
    def ask_unsaved(self, parent: Any, path: Path) -> Answer: ...

    def confirm_revert(self, parent: Any, text: str) -> bool: ...

    def choose_new(self, parent: Any, folder: Path, name: str) -> Path | None: ...

    def choose_open(self, parent: Any, folder: Path) -> Path | None: ...

    def choose_save_as(self, parent: Any, folder: Path, name: str) -> Path | None: ...


def _window(parent: Any) -> Gtk.Window | None:
    return parent if isinstance(parent, Gtk.Window) else None


class GtkDialogs:
    def ask_unsaved(self, parent: Any, path: Path) -> Answer:
        primary, secondary = unsaved_question(path)
        dialog = Gtk.MessageDialog(
            transient_for=_window(parent),
            modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.NONE,
            text=primary,
        )
        dialog.format_secondary_text(secondary)
        dialog.add_buttons(
            "_Cancel",
            Gtk.ResponseType.CANCEL,
            "_Discard",
            Gtk.ResponseType.REJECT,
            "_Save",
            Gtk.ResponseType.ACCEPT,
        )
        discard = dialog.get_widget_for_response(Gtk.ResponseType.REJECT)
        discard.get_style_context().add_class("destructive-action")
        dialog.set_default_response(Gtk.ResponseType.ACCEPT)
        response = dialog.run()
        dialog.destroy()
        answers = {Gtk.ResponseType.ACCEPT: Answer.SAVE, Gtk.ResponseType.REJECT: Answer.DISCARD}
        return answers.get(response, Answer.CANCEL)  # Escape or the close button: Cancel

    def confirm_revert(self, parent: Any, text: str) -> bool:
        dialog = Gtk.MessageDialog(
            transient_for=_window(parent),
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text="Revert every change made in this window?",
        )
        dialog.format_secondary_text(text)
        answer = dialog.run()
        dialog.destroy()
        return answer == Gtk.ResponseType.OK

    def choose_new(self, parent: Any, folder: Path, name: str) -> Path | None:
        # no overwrite question: New never replaces a file (the window refuses an existing one)
        return self._choose(
            parent,
            "New config file",
            Gtk.FileChooserAction.SAVE,
            "_Create",
            folder,
            name,
            overwrite=False,
        )

    def choose_open(self, parent: Any, folder: Path) -> Path | None:
        return self._choose(
            parent,
            "Open a config file",
            Gtk.FileChooserAction.OPEN,
            "_Open",
            folder,
            None,
            overwrite=False,
        )

    def choose_save_as(self, parent: Any, folder: Path, name: str) -> Path | None:
        return self._choose(
            parent,
            "Save the config as",
            Gtk.FileChooserAction.SAVE,
            "_Save",
            folder,
            name,
            overwrite=True,
        )

    @staticmethod
    def _choose(parent, title, action, accept, folder, name, overwrite) -> Path | None:
        chooser = Gtk.FileChooserNative.new(title, _window(parent), action, accept, "_Cancel")
        chooser.set_modal(True)
        if folder.is_dir():
            chooser.set_current_folder(str(folder))
        if name is not None:
            chooser.set_current_name(name)
        if action == Gtk.FileChooserAction.SAVE:
            chooser.set_do_overwrite_confirmation(overwrite)
        for label, pattern in TOML_FILTERS:
            choice = Gtk.FileFilter()
            choice.set_name(label)
            choice.add_pattern(pattern)
            chooser.add_filter(choice)
        try:
            response = chooser.run()
            filename = chooser.get_filename()
        finally:
            chooser.destroy()
        if response != Gtk.ResponseType.ACCEPT or not filename:
            return None  # cancelled, or a file that is not local (the portal gave a URI)
        return Path(filename)
```

In `settings/view.py`: add `from settings.dialogs import GtkDialogs` above `from settings.document import UserDocument`. Replace the constructor's first lines

```python
    def __init__(self, session: SettingsSession, outputs: list[Output]):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.session = session
```

with

```python
    def __init__(
        self,
        session: SettingsSession,
        outputs: list[Output],
        confirm_revert: Callable[[Any, str], bool] | None = None,
    ):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.session = session
        # asks before Revert all (parent, text) -> OK?; tests pass a fake, no dialog runs
        self._ask_revert = confirm_revert or GtkDialogs().confirm_revert
```

Replace the Revert all button lines

```python
        revert = Gtk.Button(label="Revert all")
        revert.set_tooltip_text("Put back the file as it was when this window opened")
        revert.connect("clicked", lambda _b: self._confirm_revert())
```

with

```python
        self.revert_button = Gtk.Button(label="Revert all")
        self.revert_button.set_tooltip_text("Put back the file as it was when this window opened")
        self.revert_button.connect("clicked", lambda _b: self.confirm_revert())
```

and `bar.pack_start(revert, False, False, 0)` with `bar.pack_start(self.revert_button, False, False, 0)`. Replace the whole `_confirm_revert` method with:

```python
    def confirm_revert(self) -> None:
        """Revert all, after the confirmation dialog (the button and Edit > Revert all)."""
        if self._ask_revert(self.get_toplevel(), self.revert_text()):
            self.revert()
```

In `main.py`: add `import os` after `import logging`; in `if args.settings:` insert before the existing comment `# Before the ConfigStore: ...`:

```python
        # Native file dialogs (File > New, Open, Save As): GTK 3 asks the desktop portal (on
        # Plasma: KDE's own dialog) only when told to, before GTK starts. GTK_USE_PORTAL=0 in
        # the environment keeps GTK's own dialog.
        os.environ.setdefault("GTK_USE_PORTAL", "1")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `scripts/py -m pytest tests/test_settings_fileops.py tests/test_settings_dialogs.py tests/test_main_settings.py tests/test_settings_view.py -q`
Expected: PASS (6 + 3 + the main tests + the view tests; no failure).

- [ ] **Step 5: VERIFY**

Run: `scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q`
Expected: `All checks passed!`, `2210 passed`.

Reviewer mutations (each must fail a test): drop `if not session.dirty: return True` in `leave` (`test_a_clean_config_is_left_without_a_question`); swap SAVE and DISCARD in `leave`; `if self._ask_revert(...) or True:` in `confirm_revert`; `os.environ["GTK_USE_PORTAL"] = "1"` instead of `setdefault`; add a parameter to `GtkDialogs.choose_open` (`test_the_real_dialogs_have_the_seams_methods`).

- [ ] **Step 6: Commit**

```bash
git add settings/fileops.py settings/dialogs.py settings/view.py main.py tests/test_settings_fileops.py tests/test_settings_dialogs.py tests/test_main_settings.py
git commit -m "feat(settings): the dialogs seam and the unsaved-changes decision; native file dialogs" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 4: The menu bar and the window's actions: `SettingsController`

**Files:**
- Create: `settings/menubar.py`, `settings/controller.py`
- Modify: `settings/view.py` (`on_state`, `redo`, `save`), `settings/window.py` (whole file), `settings/app.py` (accelerators)
- Test: `tests/test_settings_controller.py` (new); `tests/test_settings_app.py` (two tests adjusted); `tests/test_settings_view.py` (`test_close_stays_open_once_after_a_refused_flush` removed: it moves to the controller as `test_leaving_stays_open_once_after_a_refused_flush`)

**Interfaces:**
- Consumes: Task 1 (`redo`, `save`, `dirty`), Task 2 (`MENUS`, `ACTIONS`, `ACCELS`, `enabled`, `menu_state`), Task 3 (`leave`, `Answer`, `Dialogs`, `GtkDialogs`, `SettingsView(confirm_revert=...)`, `confirm_revert()`).
- Produces: `build_menubar(menus=MENUS) -> tuple[Gtk.MenuBar, dict[str, Gtk.Menu]]` (menus by plain label: `"File"`, `"Edit"`, `"Help"`); `SettingsController(path: Path, session: SettingsSession, outputs: list[Output], dialogs: Dialogs, quit: Callable[[], None] | None = None)` with attributes `actions: Gio.SimpleActionGroup` (inserted as `"win"`), `menubar`, `menus`, `body`, `view`, `session`, `handlers: dict[str, Callable[[], None]]`, and methods `open_session(session)`, `sync()`, `save()`, `exit()`, `can_leave() -> bool`, `undo()`, `redo()`, `revert()`, `file_changed()`; `SettingsView(..., on_state: Callable[[], None] | None = None)`, `SettingsView.redo() -> None`, `SettingsView.save() -> bool`; `SettingsWindow(session, outputs, application=None, dialogs: Dialogs | None = None)` with `.controller`, `.view` (property), `file_changed()`.

- [ ] **Step 1: Write the failing tests.** `tests/test_settings_controller.py`:

```python
"""settings.controller: the menu bar, the window's actions and the unsaved-changes question. The
controller is a plain Gtk.Box: no window is created, and the dialogs are a fake (no dialog
runs)."""

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
pytest.importorskip("tomlkit")

from gi.repository import Gtk  # noqa: E402

if not Gtk.init_check()[0]:
    pytest.skip("no display", allow_module_level=True)

from settings import files  # noqa: E402
from settings.controller import SettingsController  # noqa: E402
from settings.fileops import Answer  # noqa: E402
from settings.session import SettingsSession  # noqa: E402

USER = """\
# gate config
[monitors.HDMI-A-1]
shell = "edge"

[[monitors.HDMI-A-1.panels]]
panel = "edge"
name = "dock"
widget = "dock"
"""
SHELL = ("monitors", "HDMI-A-1", "shell")
DEPTH = ("monitors", "HDMI-A-1", "panels", 0, "depth")


class FakeDialogs:
    """Records every question and answers from its attributes; never shows anything."""

    def __init__(self):
        self.calls = []
        self.unsaved = Answer.CANCEL
        self.revert_ok = False

    def ask_unsaved(self, _parent, path):
        self.calls.append(("unsaved", path))
        return self.unsaved

    def confirm_revert(self, _parent, text):
        self.calls.append(("revert", text))
        return self.revert_ok


@pytest.fixture
def make(tmp_path, fake_registry):
    path = tmp_path / "config.toml"
    path.write_text(USER)
    made = []

    def _make():
        quits = []
        dialogs = FakeDialogs()
        c = SettingsController(
            path, SettingsSession(path), [], dialogs, quit=lambda: quits.append(1)
        )
        c.dialogs_, c.quits = dialogs, quits
        made.append(c)
        return c, path

    yield _make
    for c in made:
        c.destroy()


@pytest.fixture
def pending(monkeypatch):
    """Spin pauses never fire on their own: a typed value stays pending until flushed."""
    import settings.fields as fields

    monkeypatch.setattr(fields.GLib, "timeout_add", lambda _ms, _fn: 3)
    monkeypatch.setattr(fields.GLib, "source_remove", lambda _id: None)


def row(c, path):
    return next(r for r in c.view.rows if r.path == path)


def on(c, name):
    return c.actions.lookup_action(name).get_enabled()


def run(c, name):
    c.actions.activate_action(name, None)


def menu_items(c, title):
    return [i for i in c.menus[title].get_children() if not isinstance(i, Gtk.SeparatorMenuItem)]


def test_the_menu_bar_shows_the_menus_and_their_shortcuts(make):
    c, _ = make()
    assert [i.get_label() for i in c.menubar.get_children()] == ["_File", "_Edit", "_Help"]
    edit = menu_items(c, "Edit")
    assert [i.get_label() for i in edit] == [
        "_Undo",
        "_Redo",
        "Cu_t",
        "_Copy",
        "_Paste",
        "Re_vert all…",
    ]
    assert [i.get_action_name() for i in edit][:2] == ["win.undo", "win.redo"]
    key, mods = edit[1].get_child().get_accel()  # the first of Redo's two shortcuts
    assert Gtk.accelerator_name(key, mods) == "<Primary><Shift>z"
    save = menu_items(c, "File")[2]
    assert save.get_label() == "_Save" and save.get_action_name() == "win.save"
    assert Gtk.accelerator_name(*save.get_child().get_accel()) == "<Primary>s"


def test_items_follow_the_session(make):
    c, _ = make()
    assert not on(c, "undo") and not on(c, "redo") and not on(c, "save") and not on(c, "revert")
    undo_item = menu_items(c, "Edit")[0]
    assert not undo_item.get_sensitive()  # the menu item follows its action
    c.view._on_change(DEPTH, 90)
    assert on(c, "undo") and on(c, "save") and on(c, "revert") and not on(c, "redo")
    assert undo_item.get_sensitive()
    run(c, "undo")
    assert on(c, "redo") and not on(c, "undo")
    assert not on(c, "save")  # back at the saved point


def test_undo_and_redo_from_the_menu(make):
    c, path = make()
    c.view._on_change(DEPTH, 90)
    run(c, "undo")
    assert path.read_text() == USER
    run(c, "redo")
    assert "depth = 90" in path.read_text()
    assert row(c, DEPTH).editor.widget.get_value() == 90


def test_redo_applies_a_pending_value_first_which_ends_the_redo_line(make, pending):
    c, path = make()
    c.view._on_change(SHELL, "both")
    run(c, "undo")
    row(c, DEPTH).editor.widget.set_value(120)  # typed, inside the spin's pause
    run(c, "redo")
    assert "depth = 120" in path.read_text() and 'shell = "edge"' in path.read_text()
    assert not on(c, "redo")


def test_save_from_the_menu_sets_the_saved_point(make):
    c, path = make()
    c.view._on_change(DEPTH, 90)
    run(c, "save")
    assert not c.session.dirty and not on(c, "save")
    assert path.with_name("config.toml.bak").read_text() == path.read_text()


def test_save_applies_a_pending_value_first(make, pending):
    c, path = make()
    row(c, DEPTH).editor.widget.set_value(120)
    c.save()  # Ctrl+S while the spin is in its pause
    assert "depth = 120" in path.read_text() and not c.session.dirty


def test_a_failed_save_is_shown_and_keeps_the_changes_unsaved(make, monkeypatch):
    c, path = make()
    c.view._on_change(DEPTH, 90)

    def boom(_path):
        raise PermissionError("denied")

    monkeypatch.setattr(files, "write_backup", boom)
    run(c, "save")
    assert c.session.dirty and on(c, "save")
    assert "cannot write" in c.view.banner_label.get_text() and c.view.banner.get_visible()


def test_revert_all_from_the_menu_asks_first(make):
    c, path = make()
    c.view._on_change(DEPTH, 90)
    run(c, "revert")
    assert c.dialogs_.calls[0][0] == "revert" and "depth = 90" in path.read_text()
    c.dialogs_.revert_ok = True
    run(c, "revert")
    assert path.read_text() == USER


def test_exit_of_a_clean_config_quits_without_asking(make):
    c, _ = make()
    run(c, "exit")
    assert c.quits == [1] and c.dialogs_.calls == []


def test_exit_with_unsaved_changes_asks_and_cancel_stays(make):
    c, path = make()
    c.view._on_change(DEPTH, 90)
    run(c, "exit")
    assert c.dialogs_.calls == [("unsaved", path)] and c.quits == []
    assert "depth = 90" in path.read_text()


def test_exit_discard_puts_the_saved_file_back_and_quits(make):
    c, path = make()
    c.view._on_change(DEPTH, 90)
    c.dialogs_.unsaved = Answer.DISCARD
    run(c, "exit")
    assert path.read_text() == USER and c.quits == [1]


def test_exit_save_keeps_the_changes_and_quits(make):
    c, path = make()
    c.view._on_change(DEPTH, 90)
    c.dialogs_.unsaved = Answer.SAVE
    run(c, "exit")
    assert "depth = 90" in path.read_text() and c.quits == [1]
    assert path.with_name("config.toml.bak").read_text() == path.read_text()


def test_a_pending_value_counts_as_a_change_when_leaving(make, pending):
    c, path = make()
    row(c, DEPTH).editor.widget.set_value(120)
    assert c.can_leave() is False  # applied, then asked (answered Cancel)
    assert "depth = 120" in path.read_text() and c.dialogs_.calls == [("unsaved", path)]


def test_leaving_stays_open_once_after_a_refused_flush(make, pending):
    c, path = make()
    row(c, DEPTH).editor.widget.set_value(120)
    path.write_text(USER.replace('shell = "edge"', 'shell = "both"'))  # by hand
    assert c.can_leave() is False  # stays open once, the warning is on screen
    assert "changed outside" in c.view.banner_label.get_text()
    assert c.can_leave() is True  # the hand edit is the saved point: nothing to ask
    assert c.dialogs_.calls == []


def test_a_discard_that_meets_a_hand_edit_stays_and_says_so(make):
    c, path = make()
    c.view._on_change(DEPTH, 90)
    hand = USER + "# by hand\n"

    def ask(_parent, p):
        path.write_text(hand)  # edited by hand while the question was open
        return Answer.DISCARD

    c.dialogs_.ask_unsaved = ask
    assert c.can_leave() is False and path.read_text() == hand
    assert "nothing was discarded" in c.view.banner_label.get_text()
```

In `tests/test_settings_view.py`, delete the whole `def test_close_stays_open_once_after_a_refused_flush(make, pending):` test (it built `SettingsWindow._on_delete` on a stand-in; the controller test above replaces it).

In `tests/test_settings_app.py`, `test_closing_the_window_flushes_and_ctrl_z_undoes`: replace the body from `from settings.session import SettingsSession` to `assert calls == ["undo", "flush"]` with:

```python
    from settings.fileops import Answer
    from settings.session import SettingsSession
    from settings.view import SettingsView
    from settings.window import TITLE, SettingsWindow

    assert TITLE == "Edge Shell settings"
    calls = []

    class Cancel:  # the unsaved-changes question, answered Cancel (no dialog runs)
        def ask_unsaved(self, _parent, _path):
            calls.append("asked")
            return Answer.CANCEL

        def confirm_revert(self, _parent, _text):
            return False

    monkey = pytest.MonkeyPatch()
    monkey.setattr(SettingsView, "flush", lambda self: calls.append("flush"))
    monkey.setattr(SettingsView, "undo", lambda self: calls.append("undo"))
    try:
        cfg = tmp_path / "c.toml"
        cfg.write_text("")
        session = SettingsSession(cfg)
        session.apply(lambda d: d.set(("theme", "accent"), "#112233"))  # something to undo
        win = SettingsWindow(session, [], dialogs=Cancel())
        assert win.get_title() == TITLE
        win.controller.actions.lookup_action("undo").activate(None)
        assert calls == ["undo"]
        # unsaved changes, answered Cancel: the window stays open
        assert win.emit("delete-event", Gdk.Event.new(Gdk.EventType.DELETE)) is True
        assert calls == ["undo", "flush", "asked"]
```

(the `finally:` block stays). In `test_activation_sets_the_undo_accel_watches_the_file_and_presents_once`, after `assert app.get_accels_for_action("win.undo") == ["<Primary>z"]` add:

```python
    assert app.get_accels_for_action("win.redo") == ["<Primary><Shift>z", "<Primary>y"]
    assert app.get_accels_for_action("win.save") == ["<Primary>s"]
    assert app.get_accels_for_action("win.copy") == []  # the focused widget's own binding
```

- [ ] **Step 2: Run them to verify they fail**

Run: `scripts/py -m pytest tests/test_settings_controller.py tests/test_settings_app.py -q`
Expected: collection ERROR `ModuleNotFoundError: No module named 'settings.controller'`; in `test_settings_app.py` `TypeError: ... unexpected keyword argument 'dialogs'` and the redo accelerator assertion fails (`[] == [...]`).

- [ ] **Step 3: Write the implementation.** `settings/menubar.py`:

```python
"""The Gtk.MenuBar built from settings.menus.MENUS. Each item is a Gtk.Actionable bound to
"win.<action>", so it follows that action's enabled state, and shows its first shortcut (the
shortcuts themselves are application accelerators, set by SettingsApp from ACCELS)."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from settings.menus import MENUS, Menu


def build_menubar(menus: tuple[Menu, ...] = MENUS) -> tuple[Gtk.MenuBar, dict[str, Gtk.Menu]]:
    """The menu bar, and each menu by its plain label ("Edit": the window refreshes Cut, Copy
    and Paste when that menu opens)."""
    bar = Gtk.MenuBar()
    submenus: dict[str, Gtk.Menu] = {}
    for menu in menus:
        top = Gtk.MenuItem.new_with_mnemonic(menu.label)
        sub = Gtk.Menu()
        for item in menu.items:
            if item is None:
                sub.append(Gtk.SeparatorMenuItem())
                continue
            entry = Gtk.MenuItem.new_with_mnemonic(item.label)
            entry.set_action_name(f"win.{item.action}")
            if item.accels:
                key, mods = Gtk.accelerator_parse(item.accels[0])
                entry.get_child().set_accel(key, mods)
            sub.append(entry)
        top.set_submenu(sub)
        bar.append(top)
        submenus[menu.label.replace("_", "")] = sub
    return bar, submenus
```

`settings/controller.py`:

```python
"""The settings window's content: the menu bar and the SettingsView, with the window's actions
(the "win" group the menu items and the shortcuts use). A plain Gtk.Box, so it is tested
without creating a window; settings.window puts it in the toplevel. Every dialog goes through
`dialogs` (settings.dialogs), so tests answer with a fake and no dialog runs."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, Gtk

from settings.dialogs import Dialogs
from settings.fileops import leave
from settings.menubar import build_menubar
from settings.menus import ACTIONS, enabled, menu_state
from settings.session import ChangedOutside, SettingsSession
from settings.view import SettingsView
from shell.config.models import ConfigError
from shell.outputs import Output


class SettingsController(Gtk.Box):
    def __init__(
        self,
        path: Path,
        session: SettingsSession,
        outputs: list[Output],
        dialogs: Dialogs,
        quit: Callable[[], None] | None = None,
    ):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.path = path  # the window's file (its application id is made from it)
        self.outputs = list(outputs)
        self.dialogs = dialogs
        self.quit = quit or (lambda: None)  # closes the window (File > Exit)
        self.session: SettingsSession | None = None
        self.view: SettingsView | None = None
        self._clipboard: dict[str, bool] | None = None
        # leaving after a flush that could not write (or met a hand edit) stays once, so the
        # error is seen; asked again, it goes on
        self._leave_warned = False
        self.handlers: dict[str, Callable[[], None]] = {
            "save": self.save,
            "exit": self.exit,
            "undo": self.undo,
            "redo": self.redo,
            "revert": self.revert,
        }
        self.actions = Gio.SimpleActionGroup()
        for name in ACTIONS:
            if name in self.handlers:
                action = Gio.SimpleAction.new(name, None)
                action.connect("activate", lambda _a, _p, n=name: self.handlers[n]())
                self.actions.add_action(action)
        self.insert_action_group("win", self.actions)
        self.menubar, self.menus = build_menubar()
        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.pack_start(self.menubar, False, False, 0)
        self.pack_start(self.body, True, True, 0)
        self.open_session(session)

    def open_session(self, session: SettingsSession) -> None:
        self.session = session
        self._leave_warned = False
        self.view = SettingsView(
            session, self.outputs, confirm_revert=self.dialogs.confirm_revert, on_state=self.sync
        )
        self.body.pack_start(self.view, True, True, 0)
        self.view.show_all()
        self.sync()

    def sync(self) -> None:
        """Every action's enabled state from the session (after each write, undo, revert,
        save or re-read; the view calls it after every refresh and rebuild)."""
        for name, ok in enabled(menu_state(self.session, self._clipboard)).items():
            action = self.actions.lookup_action(name)
            if action is not None:
                action.set_enabled(ok)

    # ---- File ------------------------------------------------------------------------------
    def save(self) -> None:
        if self.view is not None:
            self.view.save()
        self.sync()

    def exit(self) -> None:
        if self.can_leave():
            self.quit()

    def can_leave(self) -> bool:
        """May the window leave its config (Exit, the close button)? Pending values are
        applied first; a flush that could not write, or met a hand edit, stays once (its
        message is on screen). With changes since the last save, asks Save / Discard /
        Cancel; a save or discard that fails is shown and stays."""
        if self.view is None:
            return True
        self.view.flush()
        if (self.view.save_failed or self.view.refused_outside) and not self._leave_warned:
            self._leave_warned = True
            return False
        session = self.session
        try:
            return leave(
                session, lambda: self.dialogs.ask_unsaved(self.get_toplevel(), session.path)
            )
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

    # ---- the file on disk ------------------------------------------------------------------
    def file_changed(self) -> None:
        if self.view is not None:
            self.view.file_changed()
```

In `settings/view.py`: extend the constructor signature with `on_state: Callable[[], None] | None = None,` after `confirm_revert`, and after the `self._ask_revert = ...` line add:

```python
        # called after every refresh and rebuild (each write, undo, revert or re-read): the
        # window updates its menu items and title
        self._on_state = on_state or (lambda: None)
```

At the end of `rebuild()` (after `self.undo_button.set_sensitive(bool(self.session.history))`) and at the end of `refresh()` (after its `self.undo_button.set_sensitive(...)` line) add `self._on_state()`. After the `undo` method add:

```python
    def redo(self) -> None:
        """Put back what the last Undo took away. A pending value is applied first, like for
        Undo: it is a new change, so it ends the redo line and Redo then does nothing."""
        self.flush()
        if self.refused_outside:
            return
        if self._file_action(self.session.redo):
            self.hide_banner()
            self.rebuild()

    def save(self) -> bool:
        """File > Save: pending values are applied first, then the file is the saved point
        (and config.toml.bak). True when saved; a hand edit or a failed copy is shown."""
        self.flush()
        if self.refused_outside:
            return False
        if not self._file_action(lambda: self.session.save() or True):
            return False
        self.hide_banner()
        self._on_state()
        return True
```

Replace `settings/window.py` with:

```python
"""The settings toplevel: a normal xdg window (never a layer surface; KWin places it, usually
on the monitor with the pointer) holding a SettingsController (menu bar, actions, view). Its
close button is File > Exit: pending values are applied, and with changes since the last save
it asks Save / Discard / Cancel."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from settings.controller import SettingsController
from settings.dialogs import Dialogs, GtkDialogs
from settings.session import SettingsSession
from shell.outputs import Output

TITLE = "Edge Shell settings"


class SettingsWindow(Gtk.ApplicationWindow):
    def __init__(
        self,
        session: SettingsSession,
        outputs: list[Output],
        application=None,
        dialogs: Dialogs | None = None,
    ):
        super().__init__(application=application, title=TITLE)
        self.set_default_size(860, 680)
        self.controller = SettingsController(
            session.path, session, outputs, dialogs or GtkDialogs(), quit=self.destroy
        )
        self.add(self.controller)
        self.connect("delete-event", self._on_delete)
        self.controller.show_all()

    @property
    def view(self):
        return self.controller.view

    def _on_delete(self, *_args) -> bool:
        return not self.controller.can_leave()  # True: stay open

    def file_changed(self) -> None:
        self.controller.file_changed()
```

In `settings/app.py`: add `from settings.menus import ACCELS` above `from shell.config.loader import DEFAULT_PATH`, and replace `self.set_accels_for_action("win.undo", ["<Control>z"])` with:

```python
            for action, accels in ACCELS.items():
                self.set_accels_for_action(action, accels)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `scripts/py -m pytest tests/test_settings_controller.py tests/test_settings_app.py tests/test_settings_view.py -q`
Expected: PASS (15 controller tests; no failure).

- [ ] **Step 5: VERIFY**

Run: `scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q`
Expected: `All checks passed!`, `2224 passed` (15 new, 1 removed from the view tests).

Reviewer mutations (each must fail a test; checked): drop `self.view.flush()` in `can_leave`; drop `self._leave_warned = True` (killed by `test_a_failed_save_keeps_the_window_open_once` in `tests/test_settings_app.py`); drop `self.flush()` in `SettingsView.redo` or in `SettingsView.save`; drop `self._on_state()` at the end of `refresh`; register only the undo accelerator in `SettingsApp`.

- [ ] **Step 6: Commit**

```bash
git add settings/menubar.py settings/controller.py settings/view.py settings/window.py settings/app.py tests/test_settings_controller.py tests/test_settings_app.py tests/test_settings_view.py
git commit -m "feat(settings): menu bar and window actions: Save, Exit, Undo, Redo, Revert all" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 5: File operations for New, Open and Save As; one launcher for settings windows

**Files:**
- Modify: `settings/fileops.py` (imports, `NEW_TEXT` and six functions), `settings/files.py` (`keep_copy`), `shell/app.py` (the moved command)
- Create: `settings/launch.py`
- Test: `tests/test_settings_fileops.py` (imports and 10 tests), `tests/test_settings_launch.py` (new)

**Interfaces:**
- Consumes: `settings.files.write_atomic`, `read_text`, `_free_name`; `shell.config.loader.USER_PATH`.
- Produces: `fileops.NEW_TEXT: str`, `default_folder(user_path: Path = USER_PATH) -> Path`, `new_name(folder: Path) -> str`, `same_file(a: Path, b: Path) -> bool`, `create_new(path: Path) -> None`, `check_openable(path: Path) -> None`, `save_copy(source: Path, text: str, target: Path) -> Path | None` (all raise `ConfigError`); `files.keep_copy(path: Path, suffix: str) -> Path`; `launch.MAIN_PATH`, `launch.settings_command(config_path: Path | None) -> list[str]`, `launch.spawn_settings(config_path: Path) -> None` (raises `OSError`). `shell.app.settings_command` is the same object as `launch.settings_command`.

- [ ] **Step 1: Write the failing tests.** In `tests/test_settings_fileops.py`, replace the import block (docstring to `from settings.fileops import Answer, leave, unsaved_question`) with:

```python
"""settings.fileops: leaving a config with unsaved changes (pure; the question is a callable),
and the file operations of New, Open and Save As."""

import os
import tomllib
from pathlib import Path

import pytest

from settings.fileops import (
    NEW_TEXT,
    Answer,
    check_openable,
    create_new,
    default_folder,
    leave,
    new_name,
    same_file,
    save_copy,
    unsaved_question,
)
from shell.config.models import ConfigError
```

and append:

```python
def test_new_writes_a_config_with_no_keys(tmp_path):
    path = tmp_path / "sub" / "new.toml"  # a missing folder is created
    create_new(path)
    assert path.read_text() == NEW_TEXT and tomllib.loads(NEW_TEXT) == {}


def test_new_never_replaces_a_file(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(USER)
    with pytest.raises(ConfigError, match="already exists"):
        create_new(path)
    assert path.read_text() == USER
    link = tmp_path / "dangling.toml"
    link.symlink_to(tmp_path / "nowhere.toml")
    with pytest.raises(ConfigError, match="already exists"):
        create_new(link)


def test_new_in_an_unwritable_folder_is_an_error(tmp_path):
    if os.geteuid() == 0:
        pytest.skip("root can write into a read-only folder")
    os.chmod(tmp_path, 0o500)
    try:
        with pytest.raises(ConfigError, match="cannot create"):
            create_new(tmp_path / "config.toml")
    finally:
        os.chmod(tmp_path, 0o700)


def test_new_name_is_free(tmp_path):
    assert new_name(tmp_path) == "config.toml"
    (tmp_path / "config.toml").write_text("")
    (tmp_path / "config-2.toml").write_text("")
    assert new_name(tmp_path) == "config-3.toml"


def test_the_choosers_start_in_the_config_folder(tmp_path):
    user = tmp_path / ".config" / "edge-shell" / "config.toml"
    assert default_folder(user) == user.parent and user.parent.is_dir()  # created
    blocked = tmp_path / "file"
    blocked.write_text("")
    assert default_folder(blocked / "edge-shell" / "config.toml") == Path.home()


def test_same_file_through_a_symlink(tmp_path):
    real = tmp_path / "a.toml"
    real.write_text("")
    link = tmp_path / "link.toml"
    link.symlink_to(real)
    assert same_file(real, link) and not same_file(real, tmp_path / "b.toml")


def test_check_openable(tmp_path):
    text = tmp_path / "not-a-config.toml"
    text.write_text("this is [not toml\n")
    check_openable(text)  # opens, read-only with its error, like at start
    with pytest.raises(ConfigError, match="does not exist"):
        check_openable(tmp_path / "missing.toml")
    with pytest.raises(ConfigError):
        check_openable(tmp_path)  # a folder
    binary = tmp_path / "image.png"
    binary.write_bytes(b"\x89PNG\r\n\x1a\n\xff\xfe")
    with pytest.raises(ConfigError):
        check_openable(binary)


def test_save_as_writes_the_text_and_keeps_a_replaced_file(tmp_path):
    source = tmp_path / "config.toml"
    source.write_text(USER)
    target = tmp_path / "other.toml"
    assert save_copy(source, USER, target) is None and target.read_text() == USER
    target.write_text("# older\n")
    kept = save_copy(source, USER, target)
    assert kept == target.with_name("other.toml.before-save-as")
    assert kept.read_text() == "# older\n" and target.read_text() == USER
    target.write_text("# oldest\n")
    assert save_copy(source, USER, target).name == "other.toml.before-save-as.2"


def test_save_as_of_a_private_config_is_private(tmp_path):
    source = tmp_path / "config.toml"
    source.write_text(USER)
    source.chmod(0o600)
    target = tmp_path / "copy.toml"
    save_copy(source, USER, target)
    assert target.stat().st_mode & 0o777 == 0o600


def test_save_as_into_an_unwritable_folder_is_an_error(tmp_path):
    if os.geteuid() == 0:
        pytest.skip("root can write into a read-only folder")
    folder = tmp_path / "ro"
    folder.mkdir()
    os.chmod(folder, 0o500)
    try:
        with pytest.raises(ConfigError, match="cannot write"):
            save_copy(tmp_path / "missing.toml", USER, folder / "x.toml")
    finally:
        os.chmod(folder, 0o700)
```

`tests/test_settings_launch.py`:

```python
"""settings.launch: the command that opens a settings window, and starting it (nothing is
really spawned here)."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import settings.launch as launch


def test_the_command_uses_this_interpreter_and_main_py(tmp_path):
    cfg = tmp_path / "c.toml"
    assert launch.settings_command(cfg) == [
        sys.executable,
        str(Path(launch.__file__).resolve().parents[1] / "main.py"),
        "--settings",
        "--config",
        str(cfg),
    ]
    assert launch.settings_command(None)[-1] == "--settings"


def test_the_shell_uses_the_same_command():
    pytest.importorskip("fabric")
    import shell.app

    assert shell.app.settings_command is launch.settings_command


def test_spawn_starts_its_own_session_and_reaps_the_child(monkeypatch, tmp_path):
    pytest.importorskip("gi")
    from gi.repository import GLib

    started, watched = [], []

    def popen(command, **kw):
        started.append((command, kw))
        return SimpleNamespace(pid=4242, returncode=None)

    monkeypatch.setattr(launch.subprocess, "Popen", popen)
    monkeypatch.setattr(GLib, "child_watch_add", lambda *a: watched.append(a))
    monkeypatch.chdir(tmp_path)
    launch.spawn_settings(Path("rel.toml"))
    command, kw = started[0]
    assert command[-2:] == ["--config", str(tmp_path / "rel.toml")]  # absolute
    assert kw["start_new_session"] is True
    _prio, pid, callback, proc = watched[0]
    assert pid == 4242
    callback(4242, 0, proc)
    assert proc.returncode == 0
```

- [ ] **Step 2: Run them to verify they fail**

Run: `scripts/py -m pytest tests/test_settings_fileops.py tests/test_settings_launch.py -q`
Expected: collection ERRORs: `ImportError: cannot import name 'NEW_TEXT' from 'settings.fileops'` and `ModuleNotFoundError: No module named 'settings.launch'`.

- [ ] **Step 3: Write the implementation.** In `settings/fileops.py`, replace the docstring and import block with:

```python
"""File-menu work without GTK: what happens to unsaved changes when the window leaves a config
(Close, Exit, New, Open, Save As, the window's close button), and the file operations of New,
Open and Save As. Pure: the questions are asked through a callable, so tests answer them and
no dialog runs; file-system errors come back as ConfigError, for the window to show."""

from __future__ import annotations

import stat
from collections.abc import Callable
from enum import Enum
from pathlib import Path
from typing import Any

from settings import files
from shell.config.loader import USER_PATH
from shell.config.models import ConfigError

# File > New writes this: valid TOML with no keys, so every value is the default
NEW_TEXT = "# Edge Shell config. Keys left out take their defaults (config.default.toml).\n"
```

and append after `leave`:

```python
def default_folder(user_path: Path = USER_PATH) -> Path:
    """Where the file choosers start: the default config's folder (~/.config/edge-shell),
    created when missing; the home folder if it cannot be."""
    folder = user_path.parent
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError:
        return Path.home()
    return folder


def new_name(folder: Path) -> str:
    """A file name File > New suggests: config.toml, or config-2.toml, -3, ... when taken."""
    name, n = "config.toml", 2
    while (folder / name).exists():
        name, n = f"config-{n}.toml", n + 1
    return name


def same_file(a: Path, b: Path) -> bool:
    """The same file, also through a symlink or a relative path."""
    return a.resolve() == b.resolve()


def create_new(path: Path) -> None:
    """File > New: write NEW_TEXT at `path` (missing folders are created). Never replaces a
    file: an existing path is refused."""
    if path.exists() or path.is_symlink():
        raise ConfigError(
            f"{path} already exists; New never replaces a file: choose another name, or open "
            "it with File > Open"
        )
    try:
        files.write_atomic(path, NEW_TEXT)
    except OSError as exc:
        raise ConfigError(f"cannot create {path}: {exc}") from None


def check_openable(path: Path) -> None:
    """File > Open: refuse what the settings window could not show (missing, a folder,
    unreadable, not UTF-8 text). A text that is not a valid config does open (read-only, with
    its error), as at start."""
    if not path.exists():
        raise ConfigError(f"{path} does not exist")
    files.read_text(path)  # ConfigError for a folder, no permission or a binary file


def save_copy(source: Path, text: str, target: Path) -> Path | None:
    """File > Save As: write `text` to `target`. A file already there (the chooser asked
    before replacing it) is first kept as target.before-save-as (.2, .3, ...; returned). A
    new file gets the mode of `source` (a private config stays private), a replaced one keeps
    its own."""
    kept = None
    mode = None
    try:
        if target.exists():
            kept = files.keep_copy(target, ".before-save-as")
        elif source.exists():
            mode = stat.S_IMODE(source.stat().st_mode)
        files.write_atomic(target, text, mode=mode)
    except OSError as exc:
        raise ConfigError(f"cannot write {target}: {exc}") from None
    return kept
```

In `settings/files.py`, replace `keep_before_revert` with:

```python
def keep_copy(path: Path, suffix: str) -> Path:
    """Copy the current file, byte for byte and with its mode, to `path` + `suffix` (.2, .3,
    ... when one exists: never overwritten). Returns the copy's path."""
    target = path.resolve()
    kept = _free_name(target.with_name(target.name + suffix))
    write_atomic(kept, target.read_bytes(), mode=stat.S_IMODE(target.stat().st_mode))
    return kept


def keep_before_revert(path: Path) -> Path:
    """config.toml.before-revert (numbered), before Revert all replaces a hand edit."""
    return keep_copy(path, ".before-revert")
```

`settings/launch.py`:

```python
"""Starting a settings window on a config file in its own process: from the shell (a
right-click on a panel handle) and from the settings window itself (File > New, Open and Save
As open the chosen file in its own window: one window per file, each with its own
single-instance application id). No GTK at import time, no Fabric: the shell and the settings
process both import it."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)

MAIN_PATH = Path(__file__).resolve().parents[1] / "main.py"


def settings_command(config_path: Path | None) -> list[str]:
    """The command that opens the settings window on a config file (None: the default one),
    with this process's own interpreter (the venv that has Fabric and tomlkit)."""
    command = [sys.executable, str(MAIN_PATH), "--settings"]
    if config_path is not None:
        command += ["--config", str(config_path)]
    return command


def spawn_settings(config_path: Path) -> None:
    """Start the settings window on `config_path` in a new session (it outlives this window).
    If that file already has a window, it only comes forward. The child is reaped by a GLib
    child watch, so a window that stays open leaves no zombie. Raises OSError when the
    interpreter cannot be started."""
    from gi.repository import GLib

    proc = subprocess.Popen(
        settings_command(config_path.absolute()),
        start_new_session=True,
        stdin=subprocess.DEVNULL,
    )
    GLib.child_watch_add(GLib.PRIORITY_DEFAULT, proc.pid, _reaped, proc)


def _reaped(_pid: int, status: int, proc: subprocess.Popen) -> None:
    proc.returncode = os.waitstatus_to_exitcode(status)  # GLib passes the raw wait status
    if proc.returncode != 0:
        log.warning("a settings window exited with status %d", proc.returncode)
```

In `shell/app.py`: delete `MAIN_PATH = ...` and the whole `def settings_command(...)` function (with the blank lines around them), delete `from pathlib import Path` (no longer used), and add above `from shell import plan`:

```python
from settings.launch import MAIN_PATH, settings_command  # noqa: F401  (shared with the window)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `scripts/py -m pytest tests/test_settings_fileops.py tests/test_settings_launch.py tests/test_open_settings.py tests/test_settings_session.py -q`
Expected: PASS (no failure; `test_settings_command_uses_this_interpreter_and_the_config` in `tests/test_open_settings.py` still passes through the re-export).

- [ ] **Step 5: VERIFY**

Run: `scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q`
Expected: `All checks passed!`, `2237 passed`.

Reviewer mutations (each must fail a test in `tests/test_settings_fileops.py`; checked): `if False:` instead of the exists check in `create_new`; `while False:` in `new_name`; skip `keep_copy` in `save_copy`; leave `mode` None for a new target; drop the `does not exist` check in `check_openable`; skip the `mkdir` in `default_folder`.

- [ ] **Step 6: Commit**

```bash
git add settings/fileops.py settings/files.py settings/launch.py shell/app.py tests/test_settings_fileops.py tests/test_settings_launch.py
git commit -m "feat(settings): file operations for New, Open and Save As; one launcher for settings windows" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 6: File > New, Open, Save As and Close; the empty window

**Files:**
- Modify: `settings/controller.py` (whole file below), `settings/app.py` (reopen)
- Test: `tests/test_settings_controller.py` (the fake and the fixture, 14 tests), `tests/test_settings_app.py` (1 test)

**Interfaces:**
- Consumes: Task 5 (`create_new`, `check_openable`, `default_folder`, `new_name`, `same_file`, `save_copy`, `spawn_settings`), Task 4 controller, Task 1 `discard`.
- Produces: `SettingsController(path, session, outputs, dialogs, quit=None, launch: Callable[[Path], None] = spawn_settings, user_path: Path = USER_PATH)`; new attributes `default_path`, `launch`, `user_path`, `notice: Gtk.Label` (the empty page's message), `body: Gtk.Stack` with children `"empty"` and `"config"`; new methods `new()`, `open()`, `save_as()`, `close_config()`, `reopen()`, `tell(text, kind=Gtk.MessageType.ERROR)`; handlers `new`, `open`, `save-as`, `close`. `SettingsApp.do_activate` calls `window.controller.reopen()` when the window shows no config.

- [ ] **Step 1: Write the failing tests.** In `tests/test_settings_controller.py`, replace the `FakeDialogs` class and the `make` fixture with:

```python
class FakeDialogs:
    """Records every question and answers from its attributes; never shows anything."""

    def __init__(self):
        self.calls = []
        self.unsaved = Answer.CANCEL
        self.revert_ok = False
        self.paths = {}  # what each file chooser "returns" by kind; missing: cancelled
        self.chosen = None  # (kind, folder, suggested name) of the last chooser

    def ask_unsaved(self, _parent, path):
        self.calls.append(("unsaved", path))
        return self.unsaved

    def confirm_revert(self, _parent, text):
        self.calls.append(("revert", text))
        return self.revert_ok

    def _choose(self, kind, folder, name):
        self.chosen = (kind, folder, name)
        return self.paths.get(kind)

    def choose_new(self, _parent, folder, name):
        return self._choose("new", folder, name)

    def choose_open(self, _parent, folder):
        return self._choose("open", folder, None)

    def choose_save_as(self, _parent, folder, name):
        return self._choose("save-as", folder, name)


@pytest.fixture
def make(tmp_path, fake_registry):
    path = tmp_path / "config.toml"
    path.write_text(USER)
    made = []

    def _make():
        quits, launches = [], []
        dialogs = FakeDialogs()
        c = SettingsController(
            path,
            SettingsSession(path),
            [],
            dialogs,
            quit=lambda: quits.append(1),
            launch=launches.append,  # nothing is spawned
            user_path=tmp_path / "home" / "edge-shell" / "config.toml",
        )
        c.dialogs_, c.quits, c.launches = dialogs, quits, launches
        made.append(c)
        return c, path

    yield _make
    for c in made:
        c.destroy()
```

and append:

```python
# ---- New, Open, Save As, Close (Task 6) ------------------------------------------------------
def test_close_shows_the_empty_page_where_only_new_open_and_exit_work(make):
    c, path = make()
    run(c, "close")
    assert c.view is None and c.session is None
    assert c.body.get_visible_child_name() == "empty"
    for name in ("save", "save-as", "close", "undo", "redo", "revert"):
        assert not on(c, name), name
    assert on(c, "new") and on(c, "open") and on(c, "exit")
    c.file_changed()  # the watcher still reports the file: nothing to do
    path.write_text(USER + "# by hand\n")
    c.file_changed()
    assert c.view is None


def test_close_with_unsaved_changes_asks_and_cancel_keeps_the_config(make):
    c, path = make()
    c.view._on_change(DEPTH, 90)
    run(c, "close")
    assert c.view is not None and c.dialogs_.calls == [("unsaved", path)]
    c.dialogs_.unsaved = Answer.DISCARD
    run(c, "close")
    assert c.view is None and path.read_text() == USER


def test_open_shows_another_file_in_its_own_window_and_closes_this_one(make, tmp_path):
    c, _ = make()
    other = tmp_path / "other.toml"
    other.write_text(USER)
    c.dialogs_.paths["open"] = other
    run(c, "open")
    assert c.dialogs_.chosen == ("open", tmp_path / "home" / "edge-shell", None)
    assert c.launches == [other] and c.quits == [1]


def test_open_asks_about_unsaved_changes_first(make, tmp_path):
    c, path = make()
    c.view._on_change(DEPTH, 90)
    other = tmp_path / "other.toml"
    other.write_text(USER)
    c.dialogs_.paths["open"] = other
    run(c, "open")  # answered Cancel
    assert c.launches == [] and c.quits == [] and c.dialogs_.calls == [("unsaved", path)]


def test_a_cancelled_chooser_does_nothing(make):
    c, _ = make()
    for name in ("open", "new", "save-as"):
        run(c, name)
    assert c.launches == [] and c.quits == [] and c.view is not None


def test_open_of_this_windows_own_file_only_says_so(make):
    c, path = make()
    c.dialogs_.paths["open"] = path
    run(c, "open")
    assert c.launches == [] and "already open" in c.view.banner_label.get_text()


def test_open_refuses_a_file_it_cannot_read(make, tmp_path):
    c, _ = make()
    binary = tmp_path / "image.png"
    binary.write_bytes(b"\x89PNG\r\n\x1a\n\xff\xfe")
    c.dialogs_.paths["open"] = binary
    run(c, "open")
    assert c.launches == [] and "Cannot open it" in c.view.banner_label.get_text()


def test_new_creates_the_file_and_opens_it_in_its_own_window(make, tmp_path):
    from settings.fileops import NEW_TEXT

    c, _ = make()
    new = tmp_path / "home" / "edge-shell" / "config.toml"
    c.dialogs_.paths["new"] = new
    run(c, "new")
    assert c.dialogs_.chosen == ("new", new.parent, "config.toml")
    assert new.read_text() == NEW_TEXT and c.launches == [new] and c.quits == [1]


def test_new_never_replaces_a_file(make, tmp_path):
    c, path = make()
    c.dialogs_.paths["new"] = path
    run(c, "new")
    assert path.read_text() == USER and c.launches == []
    assert "already exists" in c.view.banner_label.get_text()


def test_save_as_copies_the_changes_and_puts_this_file_back_as_last_saved(make, tmp_path):
    c, path = make()
    c.view._on_change(DEPTH, 90)
    copy = tmp_path / "copy.toml"
    c.dialogs_.paths["save-as"] = copy
    run(c, "save-as")
    assert c.dialogs_.chosen == ("save-as", tmp_path / "home" / "edge-shell", "config.toml")
    assert "depth = 90" in copy.read_text() and path.read_text() == USER
    assert c.launches == [copy] and c.quits == [1]


def test_save_as_onto_this_file_is_save(make):
    c, path = make()
    c.view._on_change(DEPTH, 90)
    c.dialogs_.paths["save-as"] = path
    run(c, "save-as")
    assert not c.session.dirty and "depth = 90" in path.read_text() and c.launches == []


def test_open_from_the_empty_page_shows_this_windows_file_here(make):
    c, path = make()
    run(c, "close")
    c.dialogs_.paths["open"] = path
    run(c, "open")
    assert c.view is not None and c.launches == [] and c.quits == []
    assert c.body.get_visible_child_name() == "config" and on(c, "close")


def test_a_window_that_cannot_be_started_is_shown_and_this_one_stays(make, tmp_path):
    c, _ = make()

    def fail(_path):
        raise OSError("no such interpreter")

    c.launch = fail
    other = tmp_path / "other.toml"
    other.write_text(USER)
    c.dialogs_.paths["open"] = other
    run(c, "open")
    assert c.quits == [] and "no such interpreter" in c.view.banner_label.get_text()


def test_an_error_on_the_empty_page_is_shown_there(make, tmp_path):
    c, _ = make()
    run(c, "close")
    c.dialogs_.paths["open"] = tmp_path / "missing.toml"
    run(c, "open")
    assert c.notice.get_visible() and "does not exist" in c.notice.get_text()
```

In `tests/test_settings_app.py`, add above `def test_an_uncreatable_config_folder_exits_cleanly_without_a_window`:

```python
def test_a_launch_on_a_window_with_no_config_open_shows_its_file_again(gtk_app, tmp_path):
    app = gtk_app(tmp_path / "c.toml")
    app_mod.SettingsApp.do_activate(app)
    controller = app.window.controller
    controller.close_config()  # nothing changed: no question
    assert controller.view is None
    app_mod.SettingsApp.do_activate(app)  # main.py --settings on the same file
    assert controller.view is not None and controller.session.path == tmp_path / "c.toml"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `scripts/py -m pytest tests/test_settings_controller.py tests/test_settings_app.py -q`
Expected: every controller test ERRORs in the fixture with `TypeError: SettingsController.__init__() got an unexpected keyword argument 'launch'`; the app test fails with `AttributeError: 'SettingsController' object has no attribute 'close_config'`.

- [ ] **Step 3: Write the implementation.** Replace `settings/controller.py` with:

```python
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

from settings.dialogs import Dialogs
from settings.fileops import (
    check_openable,
    create_new,
    default_folder,
    leave,
    new_name,
    same_file,
    save_copy,
)
from settings.launch import spawn_settings
from settings.menubar import build_menubar
from settings.menus import ACTIONS, enabled, menu_state
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
    ):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.path = path  # the window's file (its application id is made from it)
        self.default_path = session.default_path
        self.outputs = list(outputs)
        self.dialogs = dialogs
        self.quit = quit or (lambda: None)  # closes the window (File > Exit)
        self.launch = launch  # opens another file in its own window
        self.user_path = user_path  # the default config: the choosers start in its folder
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
            "revert": self.revert,
        }
        self.actions = Gio.SimpleActionGroup()
        for name in ACTIONS:
            if name in self.handlers:
                action = Gio.SimpleAction.new(name, None)
                action.connect("activate", lambda _a, _p, n=name: self.handlers[n]())
                self.actions.add_action(action)
        self.insert_action_group("win", self.actions)
        self.menubar, self.menus = build_menubar()
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
        self.body.add_named(self.view, "config")
        self.view.show_all()
        self.body.set_visible_child_name("config")
        self.notice.hide()
        self.sync()

    def _drop_view(self) -> None:
        view, self.view, self.session = self.view, None, None
        if view is not None:
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
        if path is None or not self.can_leave():
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
        try:
            return leave(
                session, lambda: self.dialogs.ask_unsaved(self.get_toplevel(), session.path)
            )
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

    # ---- the file on disk ------------------------------------------------------------------
    def file_changed(self) -> None:
        if self.view is not None:
            self.view.file_changed()
```

In `settings/app.py`, between the `for action, accels in ACCELS.items(): ...` loop and `self.window.present()` (same indentation as the `if self.window is None:` line):

```python
        elif self.window.controller.session is None:
            # launched again on this file (main.py --settings, a right-click on a panel handle)
            # while File > Close left the window empty: show the file again
            self.window.controller.reopen()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `scripts/py -m pytest tests/test_settings_controller.py tests/test_settings_app.py -q`
Expected: PASS (29 controller tests; no failure).

- [ ] **Step 5: VERIFY**

Run: `scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q`
Expected: `All checks passed!`, `2252 passed`.

Reviewer mutations (each must fail a test; checked): `self._switch_to(path)` without `if self.can_leave():` in `open`; drop `self.quit()` in `_switch_to`; skip `session.discard()` in `save_as`; `if True:` instead of `if self.can_leave():` in `close_config`; drop the `same_file(path, self.path)` branch in `_switch_to`; `elif False:` in `SettingsApp.do_activate`.

- [ ] **Step 6: Commit**

```bash
git add settings/controller.py settings/app.py tests/test_settings_controller.py tests/test_settings_app.py
git commit -m "feat(settings): File > New, Open, Save As and Close; the empty window" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 7: Edit > Cut, Copy and Paste on the focused text field

**Files:**
- Modify: `settings/controller.py`, `settings/window.py`
- Test: `tests/test_settings_controller.py` (5 tests)

**Interfaces:**
- Consumes: Task 2 `clipboard_enabled`; Task 6 controller.
- Produces: `SettingsController.focus_widget() -> Gtk.Widget | None` (tests replace it), `SettingsController.sync_clipboard() -> None`, `SettingsController._clip(signal: str) -> None`; handlers `cut`, `copy`, `paste`; the Edit menu's `show` and the window's `set-focus` (connected after) call `sync_clipboard`.

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_settings_controller.py`:

```python
# ---- Cut, Copy, Paste (Task 7) ---------------------------------------------------------------
def clip_on(c):
    return {name for name in ("cut", "copy", "paste") if on(c, name)}


def focus(c, widget):
    c.focus_widget = lambda: widget
    c.sync_clipboard()


def recording(widget):
    """Record the widget's clipboard signals and stop them there: the real clipboard (Phil's
    desktop) is never touched."""
    from gi.repository import GObject

    seen = []

    def record(w, name):
        seen.append(name)
        GObject.signal_stop_emission_by_name(w, name)

    for name in ("cut-clipboard", "copy-clipboard", "paste-clipboard"):
        widget.connect(name, record, name)
    return seen


def test_cut_copy_and_paste_follow_the_focused_entry(make):
    c, _ = make()
    entry = Gtk.Entry(text="Sans, Noto Sans")
    focus(c, entry)
    assert clip_on(c) == {"paste"}  # nothing selected
    entry.select_region(0, 4)
    focus(c, entry)
    assert clip_on(c) == {"cut", "copy", "paste"}
    entry.set_editable(False)
    focus(c, entry)
    assert clip_on(c) == {"copy"}
    focus(c, Gtk.Button(label="Add"))
    assert clip_on(c) == set()
    focus(c, None)
    assert clip_on(c) == set()


def test_a_spin_button_and_a_text_view_count_as_text(make):
    c, _ = make()
    spin = Gtk.SpinButton.new_with_range(0, 100, 1)
    focus(c, spin)
    assert "paste" in clip_on(c)
    view = Gtk.TextView()
    buffer = view.get_buffer()
    buffer.set_text("hello")
    buffer.select_range(buffer.get_start_iter(), buffer.get_iter_at_offset(2))
    focus(c, view)
    assert clip_on(c) == {"cut", "copy", "paste"}


def test_the_items_emit_the_focused_widgets_own_clipboard_signals(make):
    c, _ = make()
    entry = Gtk.Entry(text="Sans")
    entry.select_region(0, 2)
    seen = recording(entry)
    focus(c, entry)
    for name in ("copy", "cut", "paste"):
        run(c, name)
    assert seen == ["copy-clipboard", "cut-clipboard", "paste-clipboard"]


def test_with_no_text_focused_the_items_do_nothing(make):
    c, _ = make()
    entry = Gtk.Entry(text="Sans")
    seen = recording(entry)
    focus(c, Gtk.Button())
    run(c, "paste")  # disabled: nothing runs
    c._clip("paste-clipboard")  # and even if called, only a text widget is asked
    assert seen == []


def test_opening_the_edit_menu_refreshes_cut_copy_and_paste(make):
    c, _ = make()
    entry = Gtk.Entry(text="Sans")
    entry.select_region(0, 2)
    c.focus_widget = lambda: entry  # the focus moved, nothing refreshed yet
    assert clip_on(c) == set()
    edit = c.menus["Edit"]
    edit.show()  # what popping the menu up does first (its popup window stays hidden)
    assert clip_on(c) == {"cut", "copy", "paste"}
    edit.hide()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `scripts/py -m pytest tests/test_settings_controller.py -q -k "clipboard or cut or text or edit_menu or no_text"`
Expected: FAIL, `AttributeError: 'SettingsController' object has no attribute 'sync_clipboard'` and `AttributeError: 'NoneType' object has no attribute 'get_enabled'` (no `cut` action yet).

- [ ] **Step 3: Write the implementation.** In `settings/controller.py`: change the menus import to `from settings.menus import ACTIONS, clipboard_enabled, enabled, menu_state`; in `self.handlers`, between `"redo": self.redo,` and `"revert": self.revert,` add:

```python
            "cut": lambda: self._clip("cut-clipboard"),
            "copy": lambda: self._clip("copy-clipboard"),
            "paste": lambda: self._clip("paste-clipboard"),
```

after `self.menubar, self.menus = build_menubar()` add:

```python
        # Cut, Copy and Paste follow the focused widget: refreshed when the Edit menu opens
        # (the window also refreshes them when the focus moves)
        self.menus["Edit"].connect("show", lambda _m: self.sync_clipboard())
```

and after the `revert` method add:

```python
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
```

In `settings/window.py`, replace

```python
        self.connect("delete-event", self._on_delete)
        self.controller.show_all()
```

with

```python
        self.connect("delete-event", self._on_delete)
        # Cut, Copy and Paste follow the focused widget (after the default handler: the new
        # focus is set by then)
        self.connect_after("set-focus", lambda *_a: self.controller.sync_clipboard())
        self.controller.show_all()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `scripts/py -m pytest tests/test_settings_controller.py tests/test_settings_app.py -q`
Expected: PASS (34 controller tests).

- [ ] **Step 5: VERIFY**

Run: `scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q`
Expected: `All checks passed!`, `2257 passed`.

Reviewer mutations (each must fail a test; checked): `True` instead of `bool(widget.get_selection_bounds())`; `if widget is not None:` instead of the `Gtk.Entry | Gtk.TextView` check in `_clip`; drop the Edit menu's `show` connection; `False` instead of `get_has_selection()`.

- [ ] **Step 6: Commit**

```bash
git add settings/controller.py settings/window.py tests/test_settings_controller.py
git commit -m "feat(settings): Edit > Cut, Copy and Paste on the focused text field" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 8: Help > About, the window title and the other-file note

**Files:**
- Create: `settings/about.py`
- Modify: `settings/menus.py` (`TITLE`, `window_title`), `settings/dialogs.py` (`about`), `settings/controller.py` (title, About, note), `settings/window.py` (`TITLE` from menus, `on_title`)
- Test: `tests/test_settings_about.py` (new, 4 tests), `tests/test_settings_menus.py` (4 parametrized cases), `tests/test_settings_controller.py` (fixture, fake, 4 tests), `tests/test_settings_app.py` (one assertion)

**Interfaces:**
- Consumes: Tasks 2-7.
- Produces: `about.AboutInfo(name, version, comments, website, authors: tuple[str, ...], license)`, `about.about_info(root: Path = ROOT) -> AboutInfo`, `about.NAME`, `WEBSITE`, `AUTHORS`, `NO_LICENSE`, `ROOT`; `menus.TITLE = "Edge Shell settings"`, `menus.window_title(path: Path | None, dirty: bool, home: Path | None = None) -> str`; `Dialogs.about(parent, info: AboutInfo) -> None`; `SettingsController(..., on_title: Callable[[str], None] | None = None)`, `SettingsController.title: str`; handler `about`; `settings.window.TITLE` is re-exported from `settings.menus`.

- [ ] **Step 1: Write the failing tests.** `tests/test_settings_about.py`:

```python
"""settings.about: what Help > About shows, read from pyproject.toml at run time (pure)."""

import tomllib
from importlib import metadata

import settings.about as about
from settings.about import AUTHORS, NO_LICENSE, ROOT, WEBSITE, about_info


def test_about_reads_this_checkouts_pyproject():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    info = about_info()
    assert info.name == "Edge Shell" and info.version == project["version"]
    assert info.comments.startswith(project["description"]) and "Fabric" in info.comments
    assert info.website == WEBSITE == "https://github.com/mindderivative/edge-shell"
    assert info.authors == AUTHORS and info.license


def test_declared_authors_and_licence_are_used(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "edge-shell"\nversion = "2.0.0"\ndescription = "d"\n'
        'license = "MIT"\nauthors = [{ name = "Phil" }, { email = "x@y" }]\n'
    )
    info = about_info(tmp_path)
    assert (info.version, info.authors, info.license) == ("2.0.0", ("Phil",), "MIT")


def test_a_licence_file_wins(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "1"\nlicense = "MIT"\n')
    (tmp_path / "LICENSE").write_text("Full licence text\n")
    assert about_info(tmp_path).license == "Full licence text\n"


def test_without_a_pyproject_the_installed_version_or_unknown(tmp_path, monkeypatch):
    def missing(_name):
        raise metadata.PackageNotFoundError("edge-shell")

    monkeypatch.setattr(about.metadata, "version", missing)
    info = about_info(tmp_path)  # no pyproject.toml here
    assert info.version == "unknown" and info.license == NO_LICENSE
    assert info.authors == AUTHORS
    monkeypatch.setattr(about.metadata, "version", lambda _n: "0.9")
    assert about_info(tmp_path).version == "0.9"
```

In `tests/test_settings_menus.py`: add `from pathlib import Path` above `from types import SimpleNamespace`, add `TITLE,` and `window_title,` to the `from settings.menus import (...)` list (keep it sorted: `TITLE` after `MENUS`, `window_title` after `menu_state`), and append:

```python
HOME = Path("/home/phil")


@pytest.mark.parametrize(
    "path, dirty, title",
    [
        (None, False, "Edge Shell settings"),
        (HOME / ".config/edge-shell/config.toml", False, "~/.config/edge-shell/config.toml"),
        (HOME / ".config/edge-shell/config.toml", True, "*~/.config/edge-shell/config.toml"),
        (Path("/tmp/edge-settings.toml"), True, "*/tmp/edge-settings.toml"),
    ],
)
def test_window_title(path, dirty, title):
    expected = title if path is None else f"{title} - {TITLE}"
    assert window_title(path, dirty, home=HOME) == expected
    assert TITLE == "Edge Shell settings"
```

In `tests/test_settings_controller.py`: add to `FakeDialogs` (after `choose_save_as`):

```python
    def about(self, _parent, info):
        self.calls.append(("about", info))
```

replace the `make` fixture's inner function with:

```python
    def _make(user_path=None):
        quits, launches, titles = [], [], []
        dialogs = FakeDialogs()
        c = SettingsController(
            path,
            SettingsSession(path),
            [],
            dialogs,
            quit=lambda: quits.append(1),
            launch=launches.append,  # nothing is spawned
            user_path=user_path or tmp_path / "home" / "edge-shell" / "config.toml",
            on_title=titles.append,
        )
        c.dialogs_, c.quits, c.launches, c.titles = dialogs, quits, launches, titles
        made.append(c)
        return c, path
```

and append:

```python
# ---- About, the title, the default-config note (Task 8) ----------------------------------------
def test_the_title_names_the_file_and_marks_unsaved_changes(make):
    from settings.menus import window_title

    c, path = make()
    clean, dirty = window_title(path, False), window_title(path, True)
    assert clean.endswith(" - Edge Shell settings") and dirty == "*" + clean
    assert c.titles == [clean]
    c.view._on_change(DEPTH, 90)
    assert c.titles[-1] == dirty
    run(c, "undo")  # back at the saved point
    assert c.titles[-1] == clean
    c.view._on_change(DEPTH, 90)
    run(c, "save")
    assert c.titles[-1] == clean
    run(c, "close")
    assert c.titles[-1] == "Edge Shell settings"


def test_about_shows_the_projects_information(make):
    c, _ = make()
    assert on(c, "about")
    run(c, "about")
    (kind, info), *_ = c.dialogs_.calls
    assert kind == "about" and info.name == "Edge Shell" and info.version


def test_a_config_other_than_the_default_says_so_once(make):
    c, _ = make()
    assert c.view.banner.get_visible()
    assert "not the default config" in c.view.banner_label.get_text()
    c.view._on_change(DEPTH, 90)
    assert not c.view.banner.get_visible()  # gone after the next good change


def test_the_default_config_has_no_note(make, tmp_path):
    c, _ = make(user_path=tmp_path / "config.toml")  # the window's own file
    assert not c.view.banner.get_visible()
```

In `tests/test_settings_app.py`, `test_closing_the_window_flushes_and_ctrl_z_undoes`: replace `assert win.get_title() == TITLE` with `assert win.get_title() == f"*{cfg} - {TITLE}"  # the file, with unsaved changes`.

- [ ] **Step 2: Run them to verify they fail**

Run: `scripts/py -m pytest tests/test_settings_about.py tests/test_settings_menus.py tests/test_settings_controller.py tests/test_settings_app.py -q`
Expected: collection ERRORs (`ModuleNotFoundError: No module named 'settings.about'`, `ImportError: cannot import name 'TITLE' from 'settings.menus'`), the controller fixture `TypeError: ... unexpected keyword argument 'on_title'`, and the title assertion in the app test.

- [ ] **Step 3: Write the implementation.** `settings/about.py`:

```python
"""What Help > About shows. Pure (no GTK): read from the checkout's pyproject.toml at run time
(the shell runs from its checkout, not installed), with the installed package's metadata as
the fallback for the version."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "Edge Shell"
WEBSITE = "https://github.com/mindderivative/edge-shell"
AUTHORS = ("mindderivative",)  # the repository owner; pyproject [project].authors wins
NO_LICENSE = "No licence has been chosen for Edge Shell yet."


@dataclass(frozen=True)
class AboutInfo:
    name: str
    version: str
    comments: str
    website: str
    authors: tuple[str, ...]
    license: str


def about_info(root: Path = ROOT) -> AboutInfo:
    try:
        project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError, KeyError):
        project = {}
    authors = tuple(a["name"] for a in project.get("authors", []) if a.get("name")) or AUTHORS
    return AboutInfo(
        name=NAME,
        version=project.get("version") or _installed_version(),
        comments=project.get("description", "") + "\nBuilt with Fabric (Python, GTK 3).",
        website=WEBSITE,
        authors=authors,
        license=_license(root, project.get("license")),
    )


def _installed_version() -> str:
    try:
        return metadata.version("edge-shell")
    except metadata.PackageNotFoundError:
        return "unknown"


def _license(root: Path, declared) -> str:
    """The licence text: a LICENSE file next to pyproject.toml, else pyproject's `license`
    (an SPDX string or a {text = ...} table), else NO_LICENSE."""
    for name in ("LICENSE", "LICENSE.txt", "LICENSE.md", "COPYING"):
        try:
            return (root / name).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
    if isinstance(declared, str) and declared:
        return declared
    if isinstance(declared, dict) and declared.get("text"):
        return declared["text"]
    return NO_LICENSE
```

In `settings/menus.py`, replace

```python
from dataclasses import dataclass
from typing import Any
```

with

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TITLE = "Edge Shell settings"


def window_title(path: Path | None, dirty: bool, home: Path | None = None) -> str:
    """The window title: the file (~ for the home folder), with a leading * while it has
    changes since the last save; only the application name when no config is open."""
    if path is None:
        return TITLE
    home = Path.home() if home is None else home
    shown = str(path)
    if path.is_relative_to(home):
        shown = "~/" + str(path.relative_to(home))
    return f"{'*' if dirty else ''}{shown} - {TITLE}"
```

In `settings/dialogs.py`: add `from settings.about import AboutInfo` above `from settings.fileops import Answer, unsaved_question`; add to the `Dialogs` protocol after `choose_save_as`:

```python
    def about(self, parent: Any, info: AboutInfo) -> None: ...
```

and to `GtkDialogs` before `_choose`:

```python
    def about(self, parent: Any, info: AboutInfo) -> None:
        dialog = Gtk.AboutDialog(
            transient_for=_window(parent),
            modal=True,
            program_name=info.name,
            version=info.version,
            comments=info.comments,
            website=info.website,
            website_label="Project page",
            authors=list(info.authors),
            license=info.license,
            wrap_license=True,
            logo_icon_name="preferences-desktop",
        )
        dialog.run()
        dialog.destroy()
```

In `settings/controller.py`: add `from settings.about import about_info` above `from settings.dialogs import Dialogs`; change the menus import to `from settings.menus import ACTIONS, clipboard_enabled, enabled, menu_state, window_title`; add the parameter `on_title: Callable[[str], None] | None = None,` after `user_path: Path = USER_PATH,`; after `self.user_path = user_path ...` add:

```python
        self._on_title = on_title or (lambda _t: None)  # the window's set_title
        self.title = ""
```

add to `self.handlers` after `"revert": self.revert,`:

```python
            "about": lambda: self.dialogs.about(self.get_toplevel(), about_info()),
```

in `open_session`, between `self.notice.hide()` and `self.sync()`:

```python
        if session.config is not None and not same_file(session.path, self.user_path):
            # the shell reads only its own file: say once (the next good edit hides it)
            self.view.show_banner(
                f"This is not the default config ({self.user_path}): a running shell uses "
                "these changes only if it was started with --config on this file.",
                Gtk.MessageType.INFO,
            )
```

and at the end of `sync()`:

```python
        session = self.session
        title = window_title(session and session.path, bool(session and session.dirty))
        if title != self.title:
            self.title = title
            self._on_title(title)
```

In `settings/window.py`: replace `TITLE = "Edge Shell settings"` with nothing and add the imports `from settings.menus import TITLE` (after `from settings.dialogs import Dialogs, GtkDialogs`) plus, below the imports, `__all__ = ["TITLE", "SettingsWindow"]`; replace the controller construction with:

```python
        self.controller = SettingsController(
            session.path,
            session,
            outputs,
            dialogs or GtkDialogs(),
            quit=self.destroy,
            on_title=self.set_title,  # the file, with a * while it has unsaved changes
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `scripts/py -m pytest tests/test_settings_about.py tests/test_settings_menus.py tests/test_settings_controller.py tests/test_settings_app.py tests/test_settings_dialogs.py -q`
Expected: PASS (no failure).

- [ ] **Step 5: VERIFY**

Run: `scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q`
Expected: `All checks passed!`, `2269 passed`.

Reviewer mutations (each must fail a test; checked): no `*` in `window_title`; `if not self.title:` instead of `if title != self.title:` in `sync`; drop `not same_file(...)` from the note's condition; `version=_installed_version()`; `for name in ():` in `_license`.

- [ ] **Step 6: Commit**

```bash
git add settings/about.py settings/menus.py settings/dialogs.py settings/controller.py settings/window.py tests/test_settings_about.py tests/test_settings_menus.py tests/test_settings_controller.py tests/test_settings_app.py
git commit -m "feat(settings): Help > About, the window title and the other-file note" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 9: README, spec, help text, gate example and checklist

**Files:**
- Modify: `README.md`, `main.py` (help text only), `settings/__init__.py` (docstring), `examples/settings-test.toml` (header comment), `docs/superpowers/specs/2026-10-14-panel-widget-model-design.md` (section 6)

**Interfaces:** none (docs). The suite total stays `2269 passed`.

- [ ] **Step 1: `main.py`** — the `--restore-config` help becomes:

```python
        help="put back the config as it was at the last File > Save in the settings window, "
        "or before that window's first change (config.toml.bak; the replaced file is kept as "
        "config.toml.before-restore)",
```

- [ ] **Step 2: `settings/__init__.py`** — replace the docstring with:

```python
"""The Edge Shell settings window (spec 13). Pure modules: form, values, files, document,
session, menus, fileops, about, launch. GTK modules: fields, panels, view, dialogs, menubar,
controller, window, app."""
```

- [ ] **Step 3: `examples/settings-test.toml`** — after the line `#   scripts/py main.py --settings --config /tmp/edge-settings.toml      (terminal 2: the window)` add:

```toml
# The menus gate (plan 2026-10-15-settings-menus.md) uses the same file; its New, Save As and
# Open steps write only under /tmp/edge-menus/.
```

(`tests/test_settings_example.py` still passes: only comments change.)

- [ ] **Step 4: `README.md`.** In the plan list, add after the settings window plan line: `- [Settings menus plan](docs/superpowers/plans/2026-10-15-settings-menus.md)`. In the command block, the `--restore-config` line's comment becomes `# put back config.toml.bak (the last Save)`. In "### Settings window", after the paragraph that ends "opens a second window for that file." add:

```markdown
- **Menus.** **File**: New… (Ctrl+N), Open… (Ctrl+O), Save (Ctrl+S), Save As… (Shift+Ctrl+S),
  Close (Ctrl+W), Exit (Ctrl+Q). **Edit**: Undo (Ctrl+Z), Redo (Shift+Ctrl+Z or Ctrl+Y), Cut,
  Copy, Paste (Ctrl+X, Ctrl+C, Ctrl+V: in the focused text field; greyed out elsewhere),
  Revert all. **Help**: About Edge Shell. The Undo and Revert all buttons stay above the pages.
  Ctrl+Z in a text field undoes the last change to the file (the typed text is applied first);
  Ctrl+X/C/V work in text fields as everywhere in GTK.
- **Saving.** Changes still apply at once (the shell follows them). **Save** marks the file as
  it is now as saved and copies it to `config.toml.bak` (what `--restore-config` puts back);
  the title shows the file with a `*` while it has changes since the last save (or since it was
  opened). Close, Exit, New, Open and the window's close button ask **Save / Discard / Cancel**
  when there are such changes: Discard puts the file back as it was last saved (the shell
  follows), Cancel stays. Undo back to the saved state is not a change. A hand edit made while
  the window is open counts as saved (it was saved in your editor): Discard never writes over it.
- **Files.** One window per config file. Open and New show the chosen file in its own window
  and close this one (after the question above). New writes a file with no keys (every value is
  a default) and never replaces an existing file. Save As writes the current settings to the
  chosen file (a file it replaces is kept as `NAME.before-save-as`, `.2`, `.3`, ...), puts this
  file back as it was last saved, and shows the copy in its own window. Close leaves an empty
  window with New and Open; `main.py --settings` on its file (or a right-click on a panel
  handle) shows the file again. The file dialogs start in `~/.config/edge-shell` and are KDE's
  own (the settings process sets `GTK_USE_PORTAL=1`; start it with `GTK_USE_PORTAL=0` for GTK's
  dialog). The running shell reads only its own config (`~/.config/edge-shell/config.toml`, or
  its `--config` file): a window on another file says so once.
```

In the existing "**Undo** (Ctrl+Z) steps back one change; ..." bullet, replace "Before its first change the window copies the file to `config.toml.bak` (same permissions)" with "Before its first change, and at every Save, the window copies the file to `config.toml.bak` (same permissions)". In "## Known limitations / planned", add after the "Settings window, start and close" bullet:

```markdown
- Settings window, files: New, Open and Save As start a new settings process for the chosen
  file (the window may take a few seconds to appear: `kscreen-doctor`); this window closes as
  soon as it is started, so a window that fails to start shows nothing (run
  `scripts/py main.py --settings --config FILE` in a terminal to see why). Revert all and
  Discard cannot be undone; Revert all still goes back to the file as the window opened it
  (not to the last Save).
```

- [ ] **Step 5: the spec.** In `docs/superpowers/specs/2026-10-14-panel-widget-model-design.md`, at the end of section 6 add:

```markdown
**Planned (2026-10-15, `docs/superpowers/plans/2026-10-15-settings-menus.md`; results recorded after its gate):** the menus as specified, with these readings (decisions in the plan): About is Help > About Edge Shell; New, Open and Save As open the chosen file in its own window and close this one (one window per file: a window never retargets its application id); Save As writes a copy, puts this file back to its saved point and opens the copy; New never replaces a file and writes one comment line; Cut, Copy and Paste act on the focused text field and their shortcuts stay the widget's own; a hand edit is the new saved point; Save also refreshes `config.toml.bak`; the native dialogs come through the desktop portal (`GTK_USE_PORTAL=1` in the settings process).
```

- [ ] **Step 6: VERIFY**

Run: `scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q`
Expected: `All checks passed!`, `2269 passed`.

- [ ] **Step 7: Commit**

```bash
git add README.md main.py settings/__init__.py examples/settings-test.toml docs/superpowers/specs/2026-10-14-panel-widget-model-design.md
git commit -m "docs: the settings menus in the README and the spec; gate example note" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 10: Gate (Phil, live on HDMI-A-1 only)

**Files:** none. The controller prepares the commands and Phil runs every step; subagents never run them. **DP-1 is never touched**: the example lists it as `plasma`; do not change its row, in the file or in the window, at any step.

Setup (Phil, from the worktree):

```bash
mkdir -p /tmp/edge-menus
cp examples/settings-test.toml /tmp/edge-menus/config.toml
cp examples/hdmi-test.toml /tmp/edge-menus/other.toml
scripts/py main.py --config /tmp/edge-menus/config.toml -v                 # terminal 1: the shell
scripts/py main.py --settings --config /tmp/edge-menus/config.toml         # terminal 2: the window
```

Checklist (answer each with pass / fail and what was seen):

1. **Menus and title.** The window shows a menu bar File, Edit, Help. File lists New… Ctrl+N, Open… Ctrl+O, Save Ctrl+S, Save As… Shift+Ctrl+S, Close Ctrl+W, Exit Ctrl+Q; Edit lists Undo Ctrl+Z, Redo Shift+Ctrl+Z, Cut Ctrl+X, Copy Ctrl+C, Paste Ctrl+V, Revert all…; Help lists About Edge Shell. Redo and Revert all are greyed out on a fresh window; Save and Undo are enabled (a config is open; they do not wait for a change). The title is `/tmp/edge-menus/config.toml - Edge Shell settings`; a blue info bar says "This is not the default config (...)". *Fail note:* a shortcut missing next to an item means `Gtk.AccelLabel.set_accel` did not take; report which.
2. **Undo / Redo.** Change the accent colour on the Theme page: the shell restyles, the title gets a leading `*`, Redo stays greyed, Revert all is now enabled and Undo now has something to undo (Save and Undo were on already), the info bar goes. Ctrl+Z: the colour comes back, the `*` goes. Shift+Ctrl+Z: the change is back with the `*`; Ctrl+Z, then Ctrl+Y: same as Redo. Edit > Undo and Edit > Redo do the same as the keys.
3. **Save.** Ctrl+S: only the `*` goes (Save stays enabled). In terminal 3: `cmp /tmp/edge-menus/config.toml /tmp/edge-menus/config.toml.bak && echo same` prints `same`.
4. **Text fields and the clipboard.** In the theme font list field type `Sans, Serif`, select `Serif` with Shift+arrows, Ctrl+C, move to the end, Ctrl+V: the text is pasted (the entry's own behaviour). Ctrl+X cuts. With text selected, open the Edit menu: Cut, Copy and Paste are on; click into a combo box (shell mode) and open Edit: all three are greyed. Edit > Copy with a selection, then paste into terminal 3 (Shift+Ctrl+V): the selection is pasted. *Fail note:* a key that does nothing in the field means an accelerator swallowed it; report the key.
5. **Ctrl+Z while typing.** Type a new font list without Enter and press Ctrl+Z: the typed list is applied and then undone (the field shows the list in the file; the shell does not change). 
6. **Exit with unsaved changes.** Change the `thickness` spin and press Ctrl+Q within half a second: the question "Save the changes to config.toml?" appears with Cancel, Discard (red) and Save (default). Cancel: the window stays, the change is in the file. Close with the window's X button, answer Discard: the file goes back to the saved state (the shell follows: thickness as before) and the window closes. `cmp` against the `.bak` prints `same`.
7. **Close and reopen.** Start the window again (terminal 2), change the accent, File > Close (Ctrl+W), answer Save: the window shows "No config open" with New… and Open…; File > Save/Save As/Close and Edit > Undo/Redo/Revert all are greyed; the title is `Edge Shell settings`. Run the same command in terminal 3: the window shows the file again (no second window).
8. **Open (native dialog).** Ctrl+O: KDE's file dialog (Plasma style, not GTK's) opens in `~/.config/edge-shell`. Cancel: nothing happens. Ctrl+O again, go to `/tmp/edge-menus`, open `other.toml`: this window closes and a window titled `/tmp/edge-menus/other.toml - Edge Shell settings` appears within a few seconds; the shell in terminal 1 is unchanged (it still reads `config.toml`). Ctrl+O on `other.toml` from that window: "already open in this window".
9. **Save As.** In the `other.toml` window change the accent (title `*`), Shift+Ctrl+S: KDE's save dialog opens in `~/.config/edge-shell` with the name `other.toml`; go to `/tmp/edge-menus`, name it `copy.toml`: the window switches to `copy.toml` (with the new accent); `other.toml` is back to its saved state (`grep accent /tmp/edge-menus/other.toml`). Save As again onto the existing `/tmp/edge-menus/other.toml`: KDE asks to replace it (if it does not, note it); after Replace, `ls /tmp/edge-menus` shows `other.toml.before-save-as`.
10. **New.** Ctrl+N: KDE's save dialog suggests a free name (`config-2.toml` or similar) in `~/.config/edge-shell`; go to `/tmp/edge-menus`, name it `new.toml`: a window on `new.toml` appears showing the default values; `cat /tmp/edge-menus/new.toml` shows the one comment line. Ctrl+N with the name `config.toml` in `/tmp/edge-menus`: if KDE asks to overwrite, answer yes; the window then says "already exists; New never replaces a file" and `cmp /tmp/edge-menus/config.toml /tmp/edge-menus/config.toml.bak` still prints `same`.
11. **Bad files.** `head -c 64 /dev/urandom > /tmp/edge-menus/junk.toml`; Open it: "Cannot open it: ..." in the banner, the window stays. `printf 'this is [not toml\n' > /tmp/edge-menus/bad.toml`; Open it: a window on `bad.toml` opens read-only with the error banner (as today).
12. **About.** Help > About Edge Shell: name Edge Shell, version 0.1.0, the description and "Built with Fabric", a "Project page" link to github.com/mindderivative/edge-shell, credits `mindderivative`, the licence button shows the MIT licence from the `LICENSE` file ("Copyright (c) 2026 Phil Hodgins"); Escape closes it.
13. **A hand edit while unsaved.** In a window on `config.toml` change the accent (`*`), then in terminal 3 `printf '# hand\n' >> /tmp/edge-menus/config.toml`: the window says the file was changed outside and re-reads it; the `*` goes; Ctrl+W closes the config without a question.
14. **Wheel guard.** Scroll over the shell-mode combo and a spin button on the HDMI-A-1 page: the page scrolls, no value changes (unchanged behaviour).
15. **Portal on and off.** Close every settings window, then `GTK_USE_PORTAL=0 scripts/py main.py --settings --config /tmp/edge-menus/config.toml`: Ctrl+O shows GTK's own dialog. Compare the window's look (theme, fonts, colours) with and without `GTK_USE_PORTAL=0`. *Fail note:* if the window looks different with the portal on, decision 10's line is dropped (open question 6).

Clean up after the gate: `rm -r /tmp/edge-menus` (Phil). Stop the shell with Ctrl+C in terminal 1.

### Task 11: Record the gate results

**Files:**
- Modify: `docs/superpowers/specs/2026-10-14-panel-widget-model-design.md` (section 6: the section's note already reads "Implemented (2026-10-15, ...; the live gate results are recorded after it)" (replacing "Planned (...)"): append the results after it and keep that wording), `docs/superpowers/specs/2026-10-11-edge-shell-design.md` (section 13: one sentence after the Gate B results naming the menus plan and its gate result), `README.md` (any limitation the gate found)

- [ ] **Step 1:** Write Phil's answers per item (pass, or what was seen) into the spec's section 6 note, and every finding with its fix (fixes get their own task with tests, before this step, as in earlier plans).
- [ ] **Step 2: VERIFY**: `scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q` prints the measured total (the last fix round ended at the count its commit records; more if a gate fix added tests), 0 skipped.
- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-10-14-panel-widget-model-design.md docs/superpowers/specs/2026-10-11-edge-shell-design.md README.md
git commit -m "docs: record the settings menus gate results" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

## Self-review

- **Spec coverage (section 6):** Menu bar with accelerators and application actions: Tasks 2, 4 (accelerators registered from `ACCELS`). File > New (native, save mode, `~/.config/edge-shell`, creates and opens): Tasks 3 (chooser), 5 (`create_new`, `default_folder`), 6. Open (native): 3, 5, 6. Save (Ctrl+S): 1, 4. Save As (native): 3, 5, 6. Close (prompt): 4, 6. Exit (same prompt, quits): 4. Edit > Undo: 4; Redo (Shift+Ctrl+Z, stack cleared by any new edit): 1, 4; Cut/Copy/Paste on the focused Editable or text view, insensitive elsewhere: 2, 7; Revert all (current behaviour and dialog): 3, 4. About (`Gtk.AboutDialog`, name, version from pyproject, licence, URL, credits): 8. Saved point, dirty, the question on Close/Exit/New/Open/window close, Discard = saved text written back, fresh session per opened or created config (each opens in its own process: backup once, saved point = file text), title with `*`: 1, 3, 4, 6, 8. One app id per path, Open on another path = another window: 6 (decision 5). Empty state after Close with New / Open, toolbar and tree insensitive: 6 (the view, with its toolbar, is not shown at all; plan 3's tree does not exist yet). Gate on HDMI-A-1 with DP-1 untouched: 10.
- **Placeholder scan:** every code step carries the code; no "TBD", no "similar to Task N"; the gate items name commands and expected output.
- **Type consistency:** `SettingsController(path, session, outputs, dialogs, quit=None, launch=spawn_settings, user_path=USER_PATH, on_title=None)` is the same in Tasks 4, 6, 8 and their fixtures; `Dialogs` methods match `GtkDialogs` (pinned by `test_the_real_dialogs_have_the_seams_methods`); `menu_state` reads `dirty`, `history`, `redo_history`, `text`, `start_text`, all set in Task 1; `window_title(path, dirty, home=None)` is used by the controller in Task 8 only after Task 8 adds it.
- **Review Focus:** each of the five lines names tests in the owning task (all present above; checked by running them).
- **Measured:** every task's code was applied in order on a scratch copy of `origin/main` (`70cf965`) and the suite run after each: 2178, 2200, 2210, 2224, 2237, 2252, 2257, 2269 passed, 0 skipped, ruff clean; the 46 mutations listed per task were applied one by one and each made at least one test fail (two survivors found while prototyping were fixed by the `can_revert` assertions in Task 2 and by naming `test_a_failed_save_keeps_the_window_open_once` for the keep-open-once mutation in Task 4).

## Open questions for Phil (each with the recommended default)

1. **Open, New and Save As close this window** and show the chosen file in its own window (decision 5). *Recommended: yes* (a window never switches files; the old file's window would otherwise linger). Alternative: keep both windows open (3 lines).
2. **Save As puts this file back to its last saved state** and the changes live on in the copy (decision 6), so if this window was on the shell's own config, the shell goes back to that file's saved look. *Recommended: yes* (what every editor does with Save As). Alternative: leave this file as it is (1 line).
3. **About under Help** (Help > About Edge Shell) rather than a top-level "About" menu. *Recommended: Help* (the desktop convention). Alternative: a top-level About menu with one item (1 label).
4. **Licence.** Answered: Phil chose MIT. The repository has a `LICENSE` file (MIT, "Copyright (c) 2026 Phil Hodgins") and About shows its text; "No licence has been chosen for Edge Shell yet." appears only for a checkout without a `LICENSE` file and with no licence in `pyproject.toml` or the installed metadata.
5. **Author credit.** About credits `mindderivative` (the GitHub owner). *Recommended:* add `authors = [{ name = "..." }]` to `pyproject.toml` with the name you want shown (About reads it); default stays `mindderivative`.
6. **KDE's file dialogs through the portal** (`GTK_USE_PORTAL=1` in the settings process, decision 10). *Recommended: yes*, unless Gate item 15 shows the window's look changing; then drop the line and use GTK's dialog.
7. **A hand edit counts as saved** (decision 2): the window never asks about, or discards, changes made in an editor. *Recommended: yes.*
8. **New never replaces an existing file** (decision 7). *Recommended: yes.* Alternative: confirm, keep the old file as `.before-new` and replace it.
9. **Ctrl+Z in a text field undoes the last change to the file** (after applying the typed text), as today (decision 4). *Recommended: yes* (GTK 3 text fields have no undo of their own). Alternative: a per-field undo of the typing (about half a task).
