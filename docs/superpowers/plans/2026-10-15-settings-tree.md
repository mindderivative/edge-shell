# Settings Toolbar, Tree and Tabbed Pages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the settings window into the layout of spec section 7: a per-screen toolbar (the screen's name, **Enable**, the native desktop's checkbox writing the four-valued `shell` key, a one-line note, a panel type list with **Add**, and Move up / Move down / Remove for the panel shown), a left tree (Detect monitors; Theme; each monitor with its panels by name, each with Move up / Move down / Remove buttons on its row) at least 200 px wide, and tabbed pages (Theme and monitor pages: General, Borders, Shadows, Handle, Layout; panel pages: Panel, Position, Handle, Interaction, Widget). Undo and Revert all leave the top bar (the Edit menu has both). Behind it, every edit goes through one ordered edit queue, and the shell warns when the config names a monitor that is not connected.

**Architecture:** Pure logic first: the tabs are data (`settings/form.py`: `THEME_TAB_OF`, `PANEL_TAB_OF`, `theme_tabs`, `panel_tabs`, `add_choices`), page names and the tree's rows are pure (`settings/pages.py`), the mode checkboxes, the desktop's name and monitor detection are pure (`settings/screens.py`), the monitor-name comparison is pure and shared with the shell (`shell/monitor_check.py`), the edit queue is pure (`settings/queue.py`), and the panel list's add / move / remove edits become pure (`settings/panels.py`, its GTK `PanelEditor` goes). A thin GTK layer renders it: `settings/tree.py` (`SettingsTree`, a `Gtk.ListBox` tree whose selected panel row shows three buttons), `settings/toolbar.py` (`ScreenToolbar`), and `SettingsView` (`settings/view.py`) holds the toolbar, the banner and a `Gtk.Paned` with the tree beside a `Gtk.Stack` of pages, each page a heading above a `Gtk.Notebook`. Every page is still built at every rebuild (so `flush()` and `refresh()` reach every row); the tree only chooses the page shown, and a rebuild keeps the page (by name) and each page's tab (by title). `FieldRow` loses its own debounce timer: spin edits go to the view's queue, which one shared timer applies after the pause.

**Tech Stack:** Python 3.14 (>=3.12), PyGObject 3.50.0 (`<3.52`), GTK 3.24 (`Gtk.ListBox`, `Gtk.Paned`, `Gtk.Stack`, `Gtk.Notebook`, `Gtk.CheckButton`, `Gtk.ComboBoxText`), Pango (ellipsized row titles), tomlkit 0.15.1, pydantic 2, pytest, ruff 0.17.0.

**Spec:** `docs/superpowers/specs/2026-10-14-panel-widget-model-design.md` section 7 (Plan 3, the contract), sections 1-2 (goal, plan order, gates on HDMI-A-1, DP-1 never touched), 6 (menus: Edit has Undo and Revert all; the empty window after Close), 9-10 (risks, Phil's decisions: "Mode checkboxes independent, written to the existing four-valued `shell`"); `docs/superpowers/specs/2026-10-11-edge-shell-design.md` sections 5.3 (monitors by connector name, the four modes), 7 (Plasma integration: hiding Plasma's panel is deferred), 13 (the settings window as built: live apply, flush on leave, keep-open-once, ChangedOutside, the wheel guard, deferred rebuilds). Style and earlier decisions: `docs/superpowers/plans/2026-10-14-settings-window.md`, `docs/superpowers/plans/2026-10-15-settings-menus.md`.

**Phil's request (verbatim):** "2. Toolbar: remove Undo and Revert all. Add the following that applies separately for each screen: Label of screen selected; Enable edge shell checkbox with label of Enable; Enable native desktop environment checkbox with a label of the native desktop environment, e.g. checkbox + KDE Plasma or checkbox + Hyprland; Panels type drop down with add button (Give all widgets/panels a clear distinct name. None of this widget_panel (Corner Panel) stuff. The python code of the widget/panel should have a unique name as well as an identifier.) 3. Left menu: Auto-detect monitors on system; List Theme and Monitors, same as currently displayed. Monitors will expand and contract like a tree or accordion with a list of added panels which are individually selectable; Minimum width should be 200 px. 3. Theme selected content: Navigation tabs that separate the customization sections: General, Borders, Shadows, Handle, Layout. 4. Monitor selected content: Same contents as Theme but make it clear this is an override of the overall theme. 5. Panel selected content: Navigation tabs that separate the customization sections tailored to the panels available customizations. Add a renaming key : value for easier identification in the settings window and in the config file."

**Decided with Phil (2026-10-15, his words in quotes; applied as decided):**
1. The two checkboxes map onto the existing `shell` key: edge on + native off = `edge`; edge off + native on = `plasma`; both on = `both`; both off = `none`. Edge Shell does not hide or show Plasma's panel (deferred), so `edge` and `both` behave the same at runtime today; the window shows a one-line note about it. The native checkbox's label comes from `XDG_CURRENT_DESKTOP` (first known component, through a small name table, fallback "Native desktop"). Plan 2 kept the Undo and Revert all buttons; this plan removes them from the top bar.
2. Theme keys: "Sort the theme keys based on their relation, borders would be under the Border tab." (decision 2).
3. Move up / Move down / Remove: "can be on the toolbar or on the tree to the right of the tree item label (if that is possible)" (decision 6: both).
4. Monitors: "The shell should detect the monitors and compare them against the config, if they match everything is fine, if they do not then a warning should be output with the monitor names that should be used." (decision 9; Task 3 in the shell, Task 9 in the window).
5. Pending edits, hand edits, deferred builds: "should be allowed. Maybe make a queue to ensure nothing gets lost. Use your best judgement keeping performance, ease of use, and options in mind." (decision 8; Task 4).
6. Widget discovery (a `widgets/` folder with one subfolder per widget and a `<name>_widget.py` entry point, found by the shell) is a later plan; this plan keeps every widget list coming from the registry (Out of scope).

**Date:** 2026-10-15. **Size:** 12 tasks: 9 with code and tests (1-9), Task 10 docs and the gate checklist, Task 11 the live gate (Phil), Task 12 recording the results. Riskiest: Task 4 (the edit queue replaces every row's debounce and the flush paths), Task 6 (the view's page model), Task 8 (panel pages replace the panel list; structural edits pick the page shown).

## Decisions (each marked *default pending Phil* unless Phil decided it, with the alternatives and their cost)

1. **Page model: a `Gtk.Stack` of pages beside the tree in a `Gtk.Paned`; each page is a heading (and banner) above a `Gtk.Notebook`.** *Default pending Phil.* Pages are named `theme`, `monitor:NAME`, `panel:NAME:INDEX` (`settings/pages.py`; INDEX is the entry's place in `[[monitors.NAME.panels]]`, as the shell tracks panels). Each notebook tab holds its own `Gtk.ScrolledWindow`, so the tab bar never scrolls away. **Every page is built at every rebuild**, as every monitor page is today: every row exists, so `flush()` and `refresh()` reach every row and switching pages never drops anything (the row count is today's: the panel rows lived in expanders). A rebuild keeps the page shown (by name; a page that is gone falls back to its monitor's page, else Theme: `fallback_page`) and each page's tab (by title, remembered on `switch-page`; a notebook only switches to a visible tab, so each tab is `show_all()`ed when added). The tree's selection follows. Rejected: (a) building only the shown page (fewer widgets; rows on other pages would not exist for `flush`/`refresh`; the queue of decision 8 makes this possible later, about one task); (b) a `Gtk.StackSwitcher` instead of a notebook (no Ctrl+PageUp/PageDown, no scrollable tab bar). The `Gtk.Paned` lets Phil widen the tree; its first child does not shrink below its size request (200 px).
2. **Tabs are data in `settings/form.py` (Phil: "Sort the theme keys based on their relation").** Theme and monitor pages: **General** (frame, text, text_secondary, accent, surface_hover, thickness, radius, peek, hover_zone, duration_ms, font), **Borders** (`[theme.border]`), **Shadows** (`[theme.shadow]`), **Handle** (the `handle` and `handle_hover` colours, then `[theme.handle_style]` under a "Handle style" heading), **Layout** (`[layout]`: gap). `THEME_TAB_OF` names the tab of each key or table that is not on General; **a key or table added to the model later lands on General**, a table as its own part with a heading (pinned by `test_a_new_theme_key_or_table_lands_on_general`). Panel pages: **Panel** (name, widget, the panel type row for a widget of several kinds), **Position** (edge panels: edge, pos (deprecated), align, offset, order, length, min_length, max_length, depth; corner panels: corner, edge, width, height), **Handle** (`[handle]`: shape, size, weight, offset, colour, hover colour), **Interaction** (state, then `[interaction]`: click, hover, drag), **Widget** (the widget's property model; absent when it has none). `PANEL_TAB_OF` names Panel, Handle and Interaction keys; any other key (a new framework key) lands on Position. A tab's sub-table parts are shown flat; a tab's later parts get a bold heading (Handle: "Handle style"; Interaction: "Interaction"). Tests check that every key is on exactly one tab. *Cost if Phil wants `state` on Panel or Position:* one dict entry, one test line.
3. **Monitor page: the same tabs as the Theme page at `[monitors.NAME]`**, under an info bar "These values override the Theme for NAME. A row you have not set here shows the Theme's value." and the monitor's layout warnings; rows not set show the inherited value with the source "global theme" / "global layout" (as today). The shell mode row leaves the page (the toolbar has it). *Default pending Phil.*
4. **The toolbar shows the screen of the page shown.** *Default pending Phil.* A monitor page: that monitor; a panel page: its monitor (and Move up / Move down / Remove act on that panel). The Theme page, and an invalid file: "No screen selected", every control insensitive (rejected: hiding the toolbar, which makes the pages jump up and down when switching). The title is the tree's ("DP-2 (not connected)"); its tooltip names the mode and its meaning (`shell = "both": ...`, from `MODE_HINTS`). A toggle writes `mode_of(edge, native)` through the queue; afterwards (also after a refusal or a hand edit) the checkboxes show the value in effect, never the click. The checkboxes write an explicit value; there is no "reset to default" for the mode any more (`plasma` is the default; writing it explicitly changes nothing at runtime). *Cost of a mode reset button:* a few lines and one test.
5. **The panel type list names widget and kind: "Clock (edge panel)", "Summary (corner panel)", then "Float panel (coming soon)" (listed, greyed out).** *Default pending Phil.* The spec asks for "a panel type dropdown (display names, float disabled)"; Phil asks for "clear distinct names". A new panel needs both a widget and a kind, so one list gives every (widget, kind) pair the registry allows (a widget of two kinds is listed twice), edge panels first, each sorted by display name (`add_choices`). Add writes `{panel, name, widget}` with a free name (`Clock`, `Clock 2`: `new_panel_entry(user, monitor, widget, kind)`) and shows the new panel's page. The widget list comes from the registry (`registry_widgets()`), so widget discovery (Out of scope) fills it later. Rejected: two dropdowns (kind, then widget): one more click and a list that changes under the user.
6. **The tree is a `Gtk.ListBox`, and the selected panel row shows Move up, Move down and Remove at its right edge; the toolbar has the same three for the panel page shown (Phil: "on the toolbar or on the tree to the right of the tree item label (if that is possible)").** A `Gtk.TreeView` cannot hold buttons in its cells: a clickable icon renderer needs the pointer position (`get_path_at_pos`), which tests cannot produce without a realized window, has no hover or focus feedback and no per-icon tooltip. Real `Gtk.Button`s in `Gtk.ListBoxRow`s are focusable (Tab), have tooltips, and are clicked in tests. Rows: Theme; each monitor with an expander arrow (only when it has panels); its panels indented by 24 px, hidden while it is collapsed. Buttons show only on the selected row (hover-reveal is not testable headless; *cost of hover-reveal:* an `enter-notify`/`leave-notify` pair, gate-checked only). The first panel cannot move up, the last not down (insensitive). Expansion is kept across rebuilds by page name (`collapsed`); a rename only retitles the rows (no row is remade, so selection and focus stay); when the pages change shape the old rows are removed and destroyed when the loop is idle (a rebuild runs inside a row button's `clicked`). Keyboard: Up/Down move and select (the list box's own), Left collapses a monitor or goes from a panel to its monitor, Right or + expands, - collapses, Tab reaches the selected row's buttons; the list's accessible name is "Settings pages". Lost against a tree view: type-ahead search (*cost:* a `Gtk.SearchEntry` filter above the list, about half a task). No context menu (*cost:* a `Gtk.Menu` on button 3 with the same three actions, a few lines and two tests).
7. **Panel pages: heading, warnings, tabs.** *Default pending Phil.* A panel page shows its title (`panel_title`: "1. Dock: bottom, center", "2. Summary: bottom-left, from bottom, 300x390") and its monitor's layout warnings (the same `previews` as the monitor page, one label per page) above the tabs of decision 2. Renaming is the Panel tab's Name row (`name` is a title key): the write is immediate, the pages are rebuilt when the loop is idle (as today, so a click on a tree button is not lost), and the tree row, the heading and the page shown follow; the tab stays. Structural edits pick the page shown afterwards: Add, the new panel; Move, the moved panel; Remove, its monitor. A structural edit refused by a hand edit picks no page (the re-read file's panel N may be another panel). `PanelEditor` (expanders) is removed; `settings/panels.py` becomes pure (`panel_title`, `panel_section`, `add_step`, `panel_step`).
8. **An edit queue (Phil: "Maybe make a queue to ensure nothing gets lost").** *Design default pending Phil.* `settings/queue.py`: `EditQueue` holds value edits (a set, or `RESET`) by key path in arrival order; a new edit of a queued path replaces it and moves to the end; an edit back to the value the row showed (`base`) un-queues the path (a value changed and changed back is never written, so an inherited value stays inherited). Rows push: a spin button (int and length rows) pushes every step and the view applies the queue once the user pauses (**one shared 400 ms timer, started again by each spin edit**; rows hold no timer and no pending value any more); every other edit (a combo, a switch, a colour, a reset, typed text on Enter or focus-out, a toolbar checkbox) is pushed and the queue is applied at once, so it comes after what was queued before it. **Barriers** apply the whole queue first: `flush()` (each row sends its typed text into the queue, then the queue is applied), which Undo, Redo, Save, Save As, leaving the config, the structural edits (add, move, remove) and Detect monitors call; and `rebuild()` itself applies a non-empty queue first and then rebuilds once (`_rebuild_due`), so **a rebuild never loses a queued edit**; the deferred (idle) rebuild applies what was queued meanwhile and rebuilds once. **A hand edit met while edits are queued drops them and names them** in the banner ("Not applied (made for the file before it changed): monitors.HDMI-A-1.panels[0].depth = 120, theme.font (typed text)"): the edits were made for the old file, and panel entries are tracked by index, so the same path may mean another panel in the re-read file (rejected: replaying still-valid paths, which could write a dock's depth onto the panel a hand edit moved to index 0). Revert all drops the queue without a word (it puts everything back anyway). File > Close retires the view (`retire()`: timer, idle rebuild and queue gone). **Contracts, as they carry over:** `flush()` keeps its meaning and its flags (`save_failed`, `refused_outside`); `keep_pending` now asks `queue.pending(path)` or the editor's typed text instead of a row timer; `discard()` only stops a retired row from calling back (queued edits are not the row's); `_rebuild_soon(defer)` and `_rebuild_due` coalesce rebuilds as before, now around the queue; `ChangedOutside` is handled as before plus the named drop. **Cost:** one timer for the whole window instead of one per spin row being edited; one dict; the visible change is that two spin rows edited within 0.4 s are written together after the last pause, in the order they were changed. Rejected: (a) a queue per row (today's timers; nothing orders two rows); (b) replay after a hand edit (above).
9. **Monitor names (Phil: "if they do not then a warning should be output with the monitor names that should be used").** `shell/monitor_check.py` (pure): `unknown_monitors(configured, connected)` and `monitor_report(...)` → `"config monitors: HDMI-A-2; connected: DP-1, HDMI-A-1"`, or None when every configured name is connected, the config names none, or nothing is known to be connected (kscreen-doctor failed or a hot-plug flap: nothing to compare against). **The shell** checks at every `sync_monitors` (start, hot-plug, reload): a report logs a WARNING and sends one notification ("Monitor not connected", the report and "Use the connected names in the config."); it is sent again only when the text changes (another config, a monitor plugged in or out), so each change from the settings window says nothing new, and a match forgets it (a later mismatch is reported again). A connected monitor missing from the config is fine (it keeps `plasma`) and is not reported. Nothing else changes: a monitor that is not connected has no frame, as before. **The window**: the tree marks configured monitors that are not connected "(not connected)" with the same function; **Detect monitors** (above the tree) applies the queue, asks kscreen-doctor again through an injectable function (`SettingsView(detect=...)`, default `settings.screens.detect_outputs`; tests always pass a fake, kscreen-doctor never runs in a test), rebuilds, and says "Connected monitors: DP-1, HDMI-A-1." or, with a mismatch, a warning with the report; a failure ("kscreen-doctor failed: ...; the monitor list is unchanged") keeps the list. Detected monitors stay after File > Close and a reopen. With no monitor at all (none connected, none configured) the tree shows only Theme and "No monitor found. Connect one and press Detect monitors."; the toolbar names no screen. *Final review (2026-10-15):* the shell counts a configured name as unknown only if it is not connected now and was never seen connected in the session (`_seen_connected`), so a correct monitor unplugged and replugged says nothing; Detect monitors keeps the list on an empty read, like a failed one.
10. **Mode edge cases.** `both` shows both checkboxes on; a monitor with no `shell` key (connected but not configured, or a table without the key) shows the default `plasma` (native on, Enable off) and a toggle writes the key (creating `[monitors.NAME]`); an invalid file shows no screen. **DP-1:** tests use temporary files only; the gate edits only HDMI-A-1 and checks DP-1 last (`shell = "plasma"` unchanged, Plasma's panel unchanged). The mouse wheel never toggles a check button (GTK check buttons ignore the wheel); the combo keeps the wheel guard (`ChoiceEditor`).
11. **File menu interplay.** Unchanged: New, Open, Save As open the chosen file in its own window; Close leaves the empty page (New, Open) where the toolbar and the tree are not shown at all (they belong to the view, which is gone; the spec's "insensitive" is met by their absence); a reopen builds a fresh view with the last detected monitors. The top bar's file path label goes too (the window title shows the file since plan 2).
12. **Right-click on a handle opening the window on that panel: deferred.** *Default pending Phil.* It needs a `--page` option in `main.py`, the shell passing the panel's monitor and index, and the single-instance application handling a command line (`Gio.ApplicationFlags.HANDLES_COMMAND_LINE`) so a running window can switch pages: about one task with its own gate step. Not cheap enough to fold in.

## Out of scope (later plans)

- **Widget discovery** (Phil, 2026-10-15): widgets as subclasses of the base `Widget` under `widgets/<name>/` with an entry point `<name>_widget.py` (a single file, a package, or a compiled `<name>_widget.so`), found by the shell, "installed" by dropping them into that folder. This plan hard-codes no widget list: the panel type list, the widget rows and the Widget tab all come from the registry (`registry_widgets()`, `registry.widget_title`, `registry.supported_kinds`, `registry.widget_props_model`), which discovery will fill.
- Input styles (plan 4: toggles, sliders, font picker, dropdown sizing), float panels, hiding or showing Plasma's panel, width/height and scrolling for every panel kind (memory: future-panel-sizing-and-scrolling), tree search, a tree context menu, hover-reveal of the row buttons, opening the window on a panel from its handle (decision 12).

## Prerequisites

- Branch `feat/settings-tree`, stacked on `feat/settings-menus` at `c1bee7b` (the menus plan is implemented; its live gate is pending), on top of `origin/main` `70cf965`, in the worktree `/home/phil/Projects/pyDev/projects/myShell/.claude/worktrees/feat-edge-shell-core`.
- Baseline before Task 1: `scripts/py -m pytest -q` prints `2366 passed` (0 skipped; warnings are normal); `scripts/py -m ruff check .` prints `All checks passed!`; `scripts/py -m ruff format --check .` reports every file formatted.
- tomlkit is installed in the shared venv: `scripts/py -c 'import tomlkit; print(tomlkit.__version__)'` prints `0.15.1`. If it fails, STOP and report (the session, view and controller tests would skip, and a skipped test must not read as green). Nobody installs packages.
- **How the code steps are written.** Every code step is a unified diff made from the measured prototype (each task applied in order on a copy of `c1bee7b` and the suite run after each). Apply a step's diff from the worktree root with `git apply --whitespace=nowarn`, after saving the block to a file (for example `/tmp/claude-1000/step.diff`); a new file appears in full (`new file mode`). If a diff does not apply, STOP and report: do not hand-merge silently. Always stage files by name, never `git add -A` or `git add .`.

## Global Constraints

- Python only through `scripts/py` (shared venv `/home/phil/Projects/pyDev/pyEnvs/global-base`). **PyGObject must stay `<3.52`** (Fabric 0.0.2 breaks on 3.52+).
- **Pure modules import no GTK / `gi`:** `settings/pages.py`, `settings/screens.py`, `settings/queue.py`, `settings/panels.py` (now), `shell/monitor_check.py`, and as before `settings/form.py`, `settings/values.py`, `settings/files.py`, `settings/document.py`, `settings/session.py`, `settings/menus.py`, `settings/fileops.py`, `settings/about.py`, `settings/launch.py`.
- **The settings process never imports Fabric or `widgets` from its modules** (`test_the_settings_process_never_imports_fabric_windows` stays green): the new modules import only `settings.*`, `shell.config.*`, `shell.outputs`, `shell.registry`, `shell.panel_spec`, `shell.widget`, `shell.monitor_check`.
- **The settings window writes only** the config file it shows, its `.bak`, `.before-revert`, and what the File menu writes (plan 2). Never `config.default.toml`.
- **kscreen-doctor never runs in a test**: `SettingsView(detect=...)` and `detect_outputs(read=...)` take fakes; `settings.app.connected_outputs` keeps its own monkeypatched tests. **notify-send never runs in a test**: `tests/test_app_sync.py` gets an autouse fixture replacing `subprocess.Popen` there.
- **Tests.** CI installs only pycairo, pydantic, pytest, ruff and tomlkit: tests importing `gi` or `fabric` start with `pytest.importorskip("gi")` / `pytest.importorskip("fabric")`; tests needing tomlkit `pytest.importorskip("tomlkit")`. GTK tests call `gi.require_version("Gtk", "3.0")` and `gi.require_version("Gdk", "3.0")` before importing `gi.repository`, skip unless `Gtk.init_check()[0]`, and **never create or show a window, run a dialog, spawn a process or use the real clipboard**: plain widgets (`SettingsTree`, `ScreenToolbar`, `SettingsView`, `SettingsController` boxes), emitted signals, fake dialogs, fake `detect`, fake `launch` and `quit`. Never call `Gtk.Application.run` or `Gio.Application.register` in a test.
- **Lint.** `ruff` 0.17.0, line length 100, rules E, F, I, UP, B; excludes `docs/` and `*.md`.
- **VERIFY** (before every commit): `scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q`. The suite must be green at the end of EVERY task (0 failed, 0 skipped) with exactly the total in the File Structure table.
- **Git.** Plain separate git commands run from the worktree (no `cd … && git`, no command substitution around git). Stage files by name. **Never push.** Every commit message ends with a second `-m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`.
- **Live runs.** Phil is the only visual tester, on `HDMI-A-1` only. **Never touch `DP-1`** (it holds the Plasma panel; never set it to `edge` or `both`, in a file or in the window; never click its checkboxes). Subagents executing tasks never launch the shell or the settings window (`main.py` without `--list-outputs`, including `--settings`), never open a window or a dialog; headless commands are fine (`pytest`, `scripts/py -c` checks). The gate (Task 11) is run by Phil.

## Review Focus

The five failure modes most likely to bite Phil that the spec implies but a happy-path test would not catch, each pinned by tests in the owning task:

1. **Edits in quick succession, around structural actions and around a hand edit (the queue).** Order: two spin rows and a combo changed within the pause are written in the order they were changed (`test_spin_edits_of_several_rows_share_one_pause_and_apply_in_order`, `test_an_edit_applied_at_once_comes_after_the_queued_ones`, `test_edits_come_out_in_arrival_order`); coalescing: last edit per path wins and moves to the end, a change back writes nothing (`test_a_new_edit_of_a_queued_path_replaces_it_and_moves_to_the_end`, `test_an_edit_back_to_the_shown_value_takes_the_path_out`, `test_a_spin_changed_back_within_the_pause_writes_nothing`); barrier: a move, Undo, Save or Detect applies the queue first (`test_a_pending_value_is_written_before_a_panel_moves`, `test_a_pending_value_is_written_before_undo_and_revert`, `test_detect_applies_the_queue_first_and_keeps_the_page`); hand edit: queued edits and typed text are dropped and named (`test_a_hand_edit_met_while_applying_names_every_dropped_edit`, `test_typed_text_dropped_by_a_hand_edit_is_named`, `test_a_hand_edit_drops_the_queue_and_its_timer_at_once`); loss on rebuild: never (`test_a_rebuild_applies_the_queued_edits_first_and_runs_once`, `test_the_deferred_rebuild_applies_what_was_queued_meanwhile_once`). Tasks 4, 8, 9; live by Gate items 11-12.
2. **The toolbar showing a mode that is not in the file** (a refused toggle, a hand edit not yet read, a monitor with no `shell` key, the Theme page, an invalid file): expect the checkboxes to show the value in effect, never the click. Pinned by `test_a_refused_mode_change_shows_the_mode_in_the_file`, `test_a_monitor_with_no_shell_key_shows_the_default`, `test_the_toolbar_follows_the_selected_screen`, `test_an_invalid_file_leaves_the_toolbar_without_a_screen`, `test_it_shows_the_screen_and_its_mode_without_calling_back` (Task 7); live by Gate items 5-6.
3. **Losing the page, the tab or the selection** (a rename, a title key change, add / move / remove, Undo of an add, a hand edit that removes the page, a structural edit refused by a hand edit): expect the page shown (or its monitor's, or Theme) with its tab, and the tree row selected. Pinned by `test_a_rebuild_keeps_the_page_and_its_tab`, `test_a_page_that_is_gone_after_a_hand_edit_falls_back_to_the_theme` (Task 6), `test_a_titled_change_keeps_the_panels_tab`, `test_renaming_a_panel_retitles_its_tree_row_and_page_and_keeps_it_shown`, `test_the_tree_rows_buttons_move_and_remove`, `test_undo_of_an_add_falls_back_to_the_monitor_page`, `test_an_add_refused_by_a_hand_edit_does_not_jump_to_another_panel` (Task 8); live by Gate items 7-10.
4. **Monitor names that do not match** (the config names a monitor that is not connected, kscreen-doctor fails, nothing is connected, a connected monitor is not configured, the same mismatch on every reload): expect one warning naming the names to use, no notification storm, nothing for an unconfigured connected monitor, an unchanged list after a failed detection. Pinned by `test_a_configured_name_that_is_not_connected_is_reported_with_the_names_to_use`, `test_no_report`, `test_a_configured_monitor_that_is_not_connected_is_reported_once`, `test_the_report_comes_again_after_the_names_matched`, `test_a_reload_with_the_same_mismatch_says_nothing_new` (Task 3), `test_detect_names_a_configured_monitor_that_is_not_connected`, `test_a_failed_detection_keeps_the_list`, `test_no_monitor_at_all_says_how_to_find_one` (Task 9); live by Gate item 13.
5. **The tree's rows and buttons** (collapsing the monitor of the selected panel, the buttons on the wrong row, moving the first up or the last down, the window's `show_all` revealing hidden rows or buttons, rows destroyed inside their own button's click): expect the monitor selected when its selected panel hides, buttons only on the selected panel row, first/last moves greyed out, hidden things staying hidden, old rows destroyed when idle. Pinned by `test_collapsing_hides_a_selected_panel_and_selects_its_monitor`, `test_the_selected_panel_row_shows_its_buttons`, `test_new_rows_never_call_back_and_old_ones_go_when_idle`, `test_left_and_right_collapse_expand_and_go_up` (Task 5); live by Gate items 2 and 10.

## File Structure

```
settings/form.py              # MODIFY (Task 1): THEME_TABS, THEME_TAB_OF, PANEL_TABS, PANEL_TAB_OF,
                              #   TabSpec, theme_tabs, panel_tabs, KIND_NOUNS, FLOAT_CHOICE,
                              #   AddChoice, add_choices
settings/values.py            # MODIFY (Task 1): new_panel_entry(user, monitor, widget, kind=None)
settings/screens.py           # NEW, PURE (Task 2): mode_flags, mode_of, SHELL_NOTE, DESKTOP_NAMES,
                              #   NATIVE_FALLBACK, desktop_label, DetectError, detect_outputs
settings/pages.py             # NEW, PURE (Task 2): THEME, NOT_CONNECTED, monitor_page, panel_page,
                              #   PageRef, parse_page, screen_of, fallback_page, TreeEntry,
                              #   tree_entries (Task 9: marks with shell.monitor_check)
shell/monitor_check.py        # NEW, PURE (Task 3): TITLE, unknown_monitors, monitor_report
shell/app.py                  # MODIFY (Task 3): _check_monitor_names in sync_monitors
settings/queue.py             # NEW, PURE (Task 4): RESET, QueuedEdit, EditQueue, path_text, describe
settings/fields.py            # MODIFY (Task 4): FieldRow without a timer (on_queue, is_pending, unsent)
settings/view.py              # MODIFY: queue (Task 4); tree, stack, tabbed pages (Task 6); toolbar,
                              #   no Undo/Revert buttons (Task 7); panel pages (Task 8); Detect (Task 9)
settings/controller.py        # MODIFY: retire (Task 4); no use_undo_action (Task 7); outputs kept
                              #   (Task 9)
settings/tree.py              # NEW, GTK (Task 5): MIN_WIDTH, NO_MONITORS, PANEL_ACTIONS, TreeRow,
                              #   SettingsTree
settings/toolbar.py           # NEW, GTK (Task 7): NO_SCREEN, ScreenToolbar; panel buttons (Task 8)
settings/panels.py            # REWRITE, PURE (Task 8): panel_title, panel_section, add_step, panel_step
README.md, settings/__init__.py, examples/settings-test.toml,
docs/superpowers/specs/2026-10-14-panel-widget-model-design.md,
docs/superpowers/specs/2026-10-11-edge-shell-design.md           # Tasks 10, 12
tests/test_settings_tabs.py, tests/test_settings_screens.py, tests/test_settings_pages.py,
tests/test_monitor_check.py, tests/test_settings_queue.py, tests/test_settings_tree.py,
tests/test_settings_toolbar.py                                   # NEW
tests/test_app_sync.py (3), tests/test_settings_fields.py (4), tests/test_settings_view.py
(4, 6, 7, 8, 9), tests/test_settings_controller.py (4, 7, 9), tests/test_settings_dialogs.py (7),
tests/test_settings_panels.py (8: rewritten, pure)               # MODIFY
```

| Task | Deliverable | Expected `pytest -q` (measured on a scratch copy) | Keeps the suite green because |
| --- | --- | --- | --- |
| 1 | tabs as data, the panel type list, `new_panel_entry(kind)` | 2379 passed (+13) | new functions; `kind=None` keeps the old call |
| 2 | `settings/screens.py`, `settings/pages.py` | 2418 passed (+39) | new modules |
| 3 | `shell/monitor_check.py`, the shell's warning | 2428 passed (+10) | report only; notify-send stubbed in its tests |
| 4 | the edit queue; rows without timers | 2445 passed (+17) | flush/keep_pending/discard keep their meaning; 9 row tests rewritten |
| 5 | `settings/tree.py` | 2459 passed (+14) | new module |
| 6 | tree + stack + tabbed Theme/monitor pages | 2467 passed (+8) | the panel list sits on a temporary Panels tab |
| 7 | the per-screen toolbar; no Undo/Revert buttons | 2483 passed (+16) | tests asking the buttons now ask the history / toolbar |
| 8 | panel pages; move/remove/rename from tree and toolbar | 2495 passed (+12) | `PanelEditor` tests become pure `panel_step` tests |
| 9 | Detect monitors, the no-monitor state | 2501 passed (+6) | new method; injectable detect |
| 10 | README, spec, example header, docstring, gate checklist | 2501 passed | docs only |
| 11 | Gate (Phil, live on HDMI-A-1) | 2501 passed | no code |
| 12 | Record the results | 2501 passed | docs only |

Without a display the GTK test files skip as whole modules (`test_settings_tree.py`, `test_settings_toolbar.py`, `test_settings_view.py`, `test_settings_controller.py`, `test_settings_fields.py`); without tomlkit the session, view, controller and panels files skip. CI has neither `gi` nor a display: `test_settings_tabs.py`, `test_settings_screens.py`, `test_settings_pages.py`, `test_settings_queue.py`, `test_monitor_check.py` and (with tomlkit) `test_settings_panels.py` run there.

---

### Task 1: Tabs as data and the panel type list (`settings/form.py`)

**Files:**
- Modify: `settings/form.py` (a new block before "value conversions"), `settings/values.py` (`new_panel_entry`)
- Test: `tests/test_settings_tabs.py` (new)

**Interfaces:**
- Consumes: `ConfigForm` (`theme`, `layout`, `panel_for(kind, corner=None, kinds=())`, `widget_props(id)`), `SectionSpec`, `FieldSpec`, `WidgetChoice` (unchanged).
- Produces: `THEME_TABS = ("General", "Borders", "Shadows", "Handle", "Layout")`, `THEME_TAB_OF: dict[str, str]`, `PANEL_TABS = ("Panel", "Position", "Handle", "Interaction", "Widget")`, `PANEL_TAB_OF: dict[str, str]`, `TabSpec(title: str, parts: tuple[tuple[tuple[str, ...], SectionSpec], ...])` (a part is a section shown at a key path relative to the page's own), `theme_tabs(form: ConfigForm) -> tuple[TabSpec, ...]` (parts keyed `("theme",)`, `("theme", "border")`, ..., `("layout",)`), `panel_tabs(section: SectionSpec, props: SectionSpec | None = None) -> tuple[TabSpec, ...]` (parts keyed relative to the entry: `()`, `("handle",)`, `("interaction",)`), `KIND_NOUNS = {"edge": "edge panel", "corner": "corner panel"}`, `FLOAT_CHOICE = "float"`, `AddChoice(id: str, label: str, kind: str, widget: str | None, enabled: bool = True)`, `add_choices(widgets: tuple[WidgetChoice, ...]) -> tuple[AddChoice, ...]`, `settings.values.new_panel_entry(user: dict, monitor: str, widget: str, kind: str | None = None) -> dict[str, str]`.

- [ ] **Step 1: Write the failing test** (`tests/test_settings_tabs.py`, new):

```diff
diff --git a/tests/test_settings_tabs.py b/tests/test_settings_tabs.py
new file mode 100644
index 0000000..c2dadac
--- /dev/null
+++ b/tests/test_settings_tabs.py
@@ -0,0 +1,198 @@
+"""settings.form: the tabs of the Theme, monitor and panel pages, and the toolbar's panel type
+list (pure)."""
+
+from dataclasses import replace
+
+from settings.form import (
+    FLOAT_CHOICE,
+    PANEL_TABS,
+    THEME_TABS,
+    FieldSpec,
+    SectionSpec,
+    WidgetChoice,
+    add_choices,
+    config_form,
+    panel_tabs,
+    props_section,
+    theme_tabs,
+)
+from settings.values import new_panel_entry
+from shell.widget import WidgetProps
+
+WIDGETS = (
+    WidgetChoice("clock", "Clock"),
+    WidgetChoice("dock", "Dock"),
+    WidgetChoice("summary", "Summary", ("corner",)),
+    WidgetChoice("system_bar", "System bar"),
+)
+FORM = config_form(WIDGETS)
+
+
+def keys(tab):
+    """(key path, row key) of every row on a tab, in order."""
+    return [(*key, f.key) for key, section in tab.parts for f in section.fields] + [
+        (*key, sub.key, f.key)
+        for key, section in tab.parts
+        for sub in section.sections
+        for f in sub.fields
+    ]
+
+
+def by_title(tabs):
+    return {t.title: t for t in tabs}
+
+
+def test_the_theme_page_has_five_tabs_in_order():
+    assert tuple(t.title for t in theme_tabs(FORM)) == THEME_TABS
+    assert THEME_TABS == ("General", "Borders", "Shadows", "Handle", "Layout")
+
+
+def test_each_theme_key_is_on_its_tab():
+    tabs = by_title(theme_tabs(FORM))
+    general = keys(tabs["General"])
+    assert ("theme", "accent") in general and ("theme", "thickness") in general
+    assert ("theme", "font") in general and ("theme", "handle") not in general
+    assert keys(tabs["Borders"]) == [
+        ("theme", "border", "enabled"),
+        ("theme", "border", "width"),
+        ("theme", "border", "color"),
+    ]
+    assert keys(tabs["Shadows"])[0] == ("theme", "shadow", "enabled")
+    assert keys(tabs["Handle"]) == [
+        ("theme", "handle"),
+        ("theme", "handle_hover"),
+        ("theme", "handle_style", "shape"),
+        ("theme", "handle_style", "size"),
+        ("theme", "handle_style", "weight"),
+    ]
+    assert keys(tabs["Layout"]) == [("layout", "gap")]
+
+
+def test_every_theme_and_layout_key_is_on_exactly_one_tab():
+    shown = [k for t in theme_tabs(FORM) for k in keys(t)]
+    every = [("theme", f.key) for f in FORM.theme.fields]
+    every += [("theme", s.key, f.key) for s in FORM.theme.sections for f in s.fields]
+    every += [("layout", f.key) for f in FORM.layout.fields]
+    assert sorted(shown) == sorted(every) and len(shown) == len(set(shown))
+
+
+def test_a_new_theme_key_or_table_lands_on_general():
+    new_row = FieldSpec("glow", "Glow", "int")
+    new_table = SectionSpec("halo", "Halo", (FieldSpec("size", "Size", "int"),))
+    theme = replace(
+        FORM.theme, fields=(*FORM.theme.fields, new_row), sections=(*FORM.theme.sections, new_table)
+    )
+    general = by_title(theme_tabs(replace(FORM, theme=theme)))["General"]
+    assert ("theme", "glow") in keys(general)
+    assert general.parts[-1][0] == ("theme", "halo")  # a table of its own, shown flat
+
+
+def test_a_sub_table_part_is_shown_at_its_own_key_path():
+    borders = by_title(theme_tabs(FORM))["Borders"]
+    ((key, section),) = borders.parts
+    assert key == ("theme", "border") and section.key == "border"
+
+
+def test_an_edge_panel_has_four_tabs_without_widget_properties():
+    tabs = panel_tabs(FORM.panel_for("edge"))
+    assert [t.title for t in tabs] == ["Panel", "Position", "Handle", "Interaction"]
+    t = by_title(tabs)
+    assert keys(t["Panel"]) == [("name",), ("widget",)]  # one kind: no Panel type row
+    assert keys(t["Position"]) == [
+        ("edge",),
+        ("pos",),
+        ("align",),
+        ("offset",),
+        ("order",),
+        ("length",),
+        ("min_length",),
+        ("max_length",),
+        ("depth",),
+    ]
+    assert keys(t["Handle"])[0] == ("handle", "shape") and len(keys(t["Handle"])) == 6
+    assert keys(t["Interaction"]) == [
+        ("state",),
+        ("interaction", "click"),
+        ("interaction", "hover"),
+        ("interaction", "drag"),
+    ]
+
+
+def test_a_corner_panel_has_its_own_position_rows():
+    t = by_title(panel_tabs(FORM.panel_for("corner", "top-right")))
+    assert keys(t["Position"]) == [("corner",), ("edge",), ("width",), ("height",)]
+    assert t["Position"].parts[0][1].field("edge").choices == ("top", "right")
+
+
+def test_a_two_kind_widget_shows_the_panel_type_on_the_panel_tab():
+    t = by_title(panel_tabs(FORM.panel_for("edge", kinds=("edge", "corner"))))
+    assert keys(t["Panel"]) == [("name",), ("widget",), ("panel",)]
+
+
+class Props(WidgetProps):
+    format: str = "HH:mm"
+
+
+def test_the_widget_tab_is_last_and_only_with_properties():
+    tabs = panel_tabs(FORM.panel_for("edge"), props_section(Props))
+    assert tuple(t.title for t in tabs) == PANEL_TABS
+    assert keys(tabs[-1]) == [("format",)]  # a key of the entry itself
+
+
+def test_every_panel_key_is_on_exactly_one_tab():
+    for section in (FORM.panel_for("edge"), FORM.panel_for("corner")):
+        shown = [k for t in panel_tabs(section) for k in keys(t)]
+        every = [(f.key,) for f in section.fields]
+        every += [(s.key, f.key) for s in section.sections for f in s.fields]
+        assert sorted(shown) == sorted(every) and len(shown) == len(set(shown))
+
+
+def test_the_panel_type_list_names_widget_and_kind():
+    choices = add_choices(WIDGETS)
+    assert [c.label for c in choices] == [
+        "Clock (edge panel)",
+        "Dock (edge panel)",
+        "System bar (edge panel)",
+        "Summary (corner panel)",
+        "Float panel (coming soon)",
+    ]
+    assert [c.id for c in choices][:4] == [
+        "edge:clock",
+        "edge:dock",
+        "edge:system_bar",
+        "corner:summary",
+    ]
+    assert (choices[3].kind, choices[3].widget, choices[3].enabled) == ("corner", "summary", True)
+    float_ = choices[-1]
+    assert (float_.id, float_.kind, float_.widget, float_.enabled) == (
+        FLOAT_CHOICE,
+        "float",
+        None,
+        False,
+    )
+
+
+def test_a_widget_of_two_kinds_is_listed_once_per_kind():
+    both = WidgetChoice("tile", "Tile", ("edge", "corner"))
+    ids = [c.id for c in add_choices((both,))]
+    assert ids == ["edge:tile", "corner:tile", FLOAT_CHOICE]
+
+
+def test_a_new_panel_entry_takes_the_chosen_kind(corner_registry):
+    from shell.panel_spec import CornerDefaults, PanelDefaults
+    from shell.widget import Widget
+
+    corner_registry.register_widget(
+        "tile",
+        title="Tile",
+        edge=PanelDefaults(edge="top", length=100, depth=40, label="tile"),
+        corner=CornerDefaults(corner="top-left", width=200, height=100, label="tile"),
+    )(type("Tile", (Widget,), {}))
+    assert new_panel_entry({}, "M", "tile")["panel"] == "edge"  # the first kind
+    assert new_panel_entry({}, "M", "tile", "corner") == {
+        "panel": "corner",
+        "name": "Tile",
+        "widget": "tile",
+    }
+    # a kind the widget lacks is written as asked: the session's check refuses it
+    assert new_panel_entry({}, "M", "dock", "corner")["panel"] == "corner"
```

- [ ] **Step 2: Run it to see it fail**

Run: `scripts/py -m pytest -q tests/test_settings_tabs.py`
Expected: `1 error` during collection (`ImportError: cannot import name 'FLOAT_CHOICE' from 'settings.form'`).

- [ ] **Step 3: Implement** (`settings/form.py`, `settings/values.py`):

```diff
diff --git a/settings/form.py b/settings/form.py
index 5ad8b85..2a026a1 100644
--- a/settings/form.py
+++ b/settings/form.py
@@ -340,6 +340,109 @@ def config_form(widgets: tuple[WidgetChoice, ...] = ()) -> ConfigForm:
     )
 
 
+# ---- tabs: which rows each page shows on which tab (panel/widget spec 7) ------------------
+# The Theme page and every monitor page have these tabs; [layout] is the Layout tab, and every
+# [theme] key or table goes on the tab THEME_TAB_OF names, any other one (a key added to the
+# model later included) on General.
+THEME_TABS = ("General", "Borders", "Shadows", "Handle", "Layout")
+THEME_TAB_OF = {
+    "border": "Borders",
+    "shadow": "Shadows",
+    "handle": "Handle",  # the handle colour
+    "handle_hover": "Handle",
+    "handle_style": "Handle",
+}
+# A panel page's tabs; every key of the entry goes on the tab PANEL_TAB_OF names, any other
+# one (edge, align, length, corner, width, ... and a key added later) on Position. Widget is
+# the widget's own properties, absent when it has none.
+PANEL_TABS = ("Panel", "Position", "Handle", "Interaction", "Widget")
+PANEL_TAB_OF = {
+    "name": "Panel",
+    "widget": "Panel",
+    "panel": "Panel",
+    "handle": "Handle",
+    "interaction": "Interaction",
+    "state": "Interaction",
+}
+
+Part = tuple[tuple[str, ...], SectionSpec]
+
+
+@dataclass(frozen=True)
+class TabSpec:
+    """One tab of a page: its title and its parts. A part is a section shown at a key path
+    relative to the page's own (the Theme page: (); a monitor page: ("monitors", NAME); a panel
+    page: ("monitors", NAME, "panels", i)); a sub-table's part shows its rows flat."""
+
+    title: str
+    parts: tuple[Part, ...]
+
+
+def _parts(
+    section: SectionSpec, key: tuple[str, ...], tab_of: dict[str, str], title: str, default: str
+) -> tuple[Part, ...]:
+    """The parts of `section` (at `key`) on the tab `title`: its own rows on that tab in one
+    part, then each of its sub-tables on that tab as a part of its own."""
+    rows = tuple(f for f in section.fields if tab_of.get(f.key, default) == title)
+    parts: list[Part] = [(key, replace(section, fields=rows, sections=()))] if rows else []
+    for sub in section.sections:
+        if tab_of.get(sub.key, default) == title:
+            parts.append(((*key, sub.key), sub))
+    return tuple(parts)
+
+
+def theme_tabs(form: ConfigForm) -> tuple[TabSpec, ...]:
+    """The tabs of the Theme page (a monitor page shows the same at its own prefix)."""
+    tabs = [
+        TabSpec(title, _parts(form.theme, ("theme",), THEME_TAB_OF, title, "General"))
+        for title in THEME_TABS[:-1]
+    ]
+    tabs.append(TabSpec("Layout", ((("layout",), form.layout),)))
+    return tuple(t for t in tabs if t.parts)
+
+
+def panel_tabs(section: SectionSpec, props: SectionSpec | None = None) -> tuple[TabSpec, ...]:
+    """The tabs of a panel page: `section` is the entry's rows (ConfigForm.panel_for), `props`
+    its widget's "Widget" section (ConfigForm.widget_props; None: no Widget tab)."""
+    tabs = [
+        TabSpec(title, _parts(section, (), PANEL_TAB_OF, title, "Position"))
+        for title in PANEL_TABS[:-1]
+    ]
+    if props is not None:
+        tabs.append(TabSpec("Widget", (((), props),)))
+    return tuple(t for t in tabs if t.parts)
+
+
+# ---- the toolbar's panel type list ---------------------------------------------------------
+KIND_NOUNS = {"edge": "edge panel", "corner": "corner panel"}
+FLOAT_CHOICE = "float"
+
+
+@dataclass(frozen=True)
+class AddChoice:
+    id: str  # "edge:clock" (kind:widget), or FLOAT_CHOICE
+    label: str  # "Clock (edge panel)"
+    kind: str
+    widget: str | None  # None: the float entry (nothing to add yet)
+    enabled: bool = True
+
+
+def add_choices(widgets: tuple[WidgetChoice, ...]) -> tuple[AddChoice, ...]:
+    """The panel types the toolbar can add: one per widget and panel kind it can be shown in,
+    by display name ("Clock (edge panel)", "Summary (corner panel)"), edge panels first, each
+    kind sorted by display name; then "Float panel (coming soon)", listed and disabled (spec
+    3.3: float panels are reserved)."""
+    ordered = sorted(widgets, key=lambda w: (w.label.casefold(), w.id))
+    choices = [
+        AddChoice(f"{kind}:{w.id}", f"{w.label} ({noun})", kind, w.id)
+        for kind, noun in KIND_NOUNS.items()
+        for w in ordered
+        if kind in w.kinds
+    ]
+    choices.append(AddChoice(FLOAT_CHOICE, "Float panel (coming soon)", "float", None, False))
+    return tuple(choices)
+
+
 # ---- value conversions between the config and the editor widgets ------------------------
 
 
diff --git a/settings/values.py b/settings/values.py
index 906d2ec..af05b9d 100644
--- a/settings/values.py
+++ b/settings/values.py
@@ -261,16 +261,20 @@ def unique_name(base: str, taken: list[str]) -> str:
         n += 1
 
 
-def new_panel_entry(user: dict, monitor: str, widget: str) -> dict[str, str]:
+def new_panel_entry(
+    user: dict, monitor: str, widget: str, kind: str | None = None
+) -> dict[str, str]:
     """The keys a new panel of `widget` on `monitor` is written with (`user`: the user file's
-    plain data): the first kind the widget supports, a name made from its title that is not
-    used on that monitor yet ("Clock", "Clock 2", ...) and the widget; every other key comes
-    from the widget's defaults. An unknown widget is written as an edge panel named after its
-    id (the session's check rejects it with the shell's text)."""
+    plain data): `kind` (None: the first kind the widget supports), a name made from its title
+    that is not used on that monitor yet ("Clock", "Clock 2", ...) and the widget; every other
+    key comes from the widget's defaults. An unknown widget is written as an edge panel named
+    after its id, a kind the widget does not support as given (the session's check rejects
+    both with the shell's text)."""
     try:
-        kind, title = supported_kinds(widget)[0], widget_title(widget)
+        first, title = supported_kinds(widget)[0], widget_title(widget)
     except KeyError:
-        kind, title = "edge", widget
+        first, title = "edge", widget
+    kind = kind or first
     _, panels = lookup(user, ("monitors", monitor, "panels"))
     taken = [p.get("name") for p in panels or () if isinstance(p, dict)]
     return {"panel": kind, "name": unique_name(title, taken), "widget": widget}
```

- [ ] **Step 4: Run it to see it pass**

Run: `scripts/py -m pytest -q tests/test_settings_tabs.py tests/test_settings_values.py tests/test_settings_form.py`
Expected: all pass (13 new).

- [ ] **Step 5: VERIFY**

Run: `scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q`
Expected: `All checks passed!`, `2379 passed`.

**Reviewer mutations** (each must make at least one test fail): `THEME_TAB_OF` without `"handle"` (the colour lands on General: `test_each_theme_key_is_on_its_tab`); `_parts` dropping sub-tables (`test_every_theme_and_layout_key_is_on_exactly_one_tab`); the default tab "Position" changed to "Panel" (`test_an_edge_panel_has_four_tabs_without_widget_properties`); `panel_tabs` appending Widget for `props=None` (`test_an_edge_panel_has_four_tabs_without_widget_properties`); `add_choices` without the float entry or with it enabled (`test_the_panel_type_list_names_widget_and_kind`); `kind = kind or first` changed to `kind = first` (`test_a_new_panel_entry_takes_the_chosen_kind`).

- [ ] **Step 6: Commit**

```bash
git add settings/form.py settings/values.py tests/test_settings_tabs.py
git commit -m "feat(settings): tabs for the Theme, monitor and panel pages; the panel type list" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 2: Page names, the tree's rows, the mode checkboxes and the desktop's name

**Files:**
- Create: `settings/screens.py`, `settings/pages.py`
- Test: `tests/test_settings_screens.py`, `tests/test_settings_pages.py` (new)

**Interfaces:**
- Consumes: `shell.outputs.Output`, `parse_kscreen`, `read_kscreen_json`; `settings.values.monitor_names(config, outputs) -> list[tuple[str, bool]]`; `Config.monitor(name).panels`.
- Produces: `settings.screens`: `mode_flags(mode: str) -> tuple[bool, bool]` (KeyError for an unknown mode), `mode_of(edge: bool, native: bool) -> str`, `SHELL_NOTE: str`, `DESKTOP_NAMES: dict[str, str]`, `NATIVE_FALLBACK = "Native desktop"`, `desktop_label(env: Mapping[str, str] | None = None) -> str`, `class DetectError(Exception)`, `detect_outputs(read: Callable[[], str] | None = None) -> list[Output]` (raises `DetectError("kscreen-doctor failed: ...")`). `settings.pages`: `THEME = "theme"`, `NOT_CONNECTED = " (not connected)"`, `monitor_page(name) -> str`, `panel_page(name, index) -> str`, `PageRef(kind, monitor=None, index=None)`, `parse_page(page) -> PageRef` (ValueError otherwise), `screen_of(page: str | None) -> str | None`, `fallback_page(page) -> str`, `TreeEntry(page, title, children=())`, `tree_entries(config: Config | None, outputs: list[Output]) -> tuple[TreeEntry, ...]`.

- [ ] **Step 1: Write the failing tests:**

```diff
diff --git a/tests/test_settings_pages.py b/tests/test_settings_pages.py
new file mode 100644
index 0000000..0ffea79
--- /dev/null
+++ b/tests/test_settings_pages.py
@@ -0,0 +1,92 @@
+"""settings.pages: page names and the tree's rows (pure)."""
+
+import pytest
+
+from settings.pages import (
+    THEME,
+    PageRef,
+    TreeEntry,
+    fallback_page,
+    monitor_page,
+    panel_page,
+    parse_page,
+    screen_of,
+    tree_entries,
+)
+from shell.outputs import Output
+
+HDMI = Output("HDMI-A-1", 0, 0, 1920, 1080)
+DP = Output("DP-1", 0, 1080, 1920, 1080)
+
+
+def test_page_names_round_trip():
+    assert parse_page(THEME) == PageRef("theme")
+    assert parse_page(monitor_page("HDMI-A-1")) == PageRef("monitor", "HDMI-A-1")
+    assert parse_page(panel_page("HDMI-A-1", 3)) == PageRef("panel", "HDMI-A-1", 3)
+    assert panel_page("HDMI-A-1", 3) == "panel:HDMI-A-1:3"
+
+
+def test_a_monitor_name_with_a_colon_round_trips():
+    assert parse_page(monitor_page("a:b")) == PageRef("monitor", "a:b")
+    assert parse_page(panel_page("a:b", 10)) == PageRef("panel", "a:b", 10)
+
+
+@pytest.mark.parametrize("name", ["", "monitor", "panel:M", "panel:M:x", "panel:M:²", "other:M"])
+def test_anything_else_is_not_a_page(name):
+    with pytest.raises(ValueError, match="not a settings page"):
+        parse_page(name)
+
+
+def test_the_screen_of_a_page():
+    assert screen_of(None) is None and screen_of(THEME) is None
+    assert screen_of(monitor_page("DP-1")) == "DP-1"
+    assert screen_of(panel_page("HDMI-A-1", 0)) == "HDMI-A-1"
+
+
+def test_a_gone_panel_falls_back_to_its_monitor_and_a_monitor_to_the_theme():
+    assert fallback_page(panel_page("HDMI-A-1", 2)) == monitor_page("HDMI-A-1")
+    assert fallback_page(monitor_page("DP-2")) == THEME
+
+
+def test_the_tree_lists_theme_monitors_and_their_panels(make_config, fake_registry):
+    config = make_config(
+        monitors={
+            "HDMI-A-1": {
+                "shell": "edge",
+                "panels": [
+                    {"panel": "edge", "name": "Bottom dock", "widget": "dock"},
+                    {"panel": "edge", "name": "Clock", "widget": "clock"},
+                ],
+            },
+            "DP-2": {"shell": "plasma"},
+        }
+    )
+    assert tree_entries(config, [HDMI, DP]) == (
+        TreeEntry("theme", "Theme"),
+        TreeEntry(
+            "monitor:HDMI-A-1",
+            "HDMI-A-1",
+            (
+                TreeEntry("panel:HDMI-A-1:0", "Bottom dock"),
+                TreeEntry("panel:HDMI-A-1:1", "Clock"),
+            ),
+        ),
+        TreeEntry("monitor:DP-1", "DP-1"),  # connected, not in the config
+        TreeEntry("monitor:DP-2", "DP-2 (not connected)"),  # only in the config
+    )
+
+
+def test_with_nothing_detected_the_configured_monitors_are_listed(make_config):
+    config = make_config(monitors={"HDMI-A-1": {"shell": "edge"}})
+    assert [e.title for e in tree_entries(config, [])] == [
+        "Theme",
+        "HDMI-A-1 (not connected)",
+    ]
+
+
+def test_an_invalid_file_lists_only_the_theme():
+    assert tree_entries(None, [HDMI]) == (TreeEntry("theme", "Theme"),)
+
+
+def test_no_monitor_at_all_lists_only_the_theme(make_config):
+    assert tree_entries(make_config(), []) == (TreeEntry("theme", "Theme"),)
diff --git a/tests/test_settings_screens.py b/tests/test_settings_screens.py
new file mode 100644
index 0000000..e5e4505
--- /dev/null
+++ b/tests/test_settings_screens.py
@@ -0,0 +1,114 @@
+"""settings.screens: the toolbar's mode checkboxes, the desktop's name and monitor detection
+(pure; kscreen-doctor never runs)."""
+
+import subprocess
+import sys
+
+import pytest
+
+from settings import screens
+from settings.screens import (
+    NATIVE_FALLBACK,
+    DetectError,
+    desktop_label,
+    detect_outputs,
+    mode_flags,
+    mode_of,
+)
+from shell.config.models import ShellMode
+
+KSCREEN = (
+    '{"outputs": [{"name": "HDMI-A-1", "enabled": true, "scale": 1, '
+    '"pos": {"x": 0, "y": 0}, "size": {"width": 1920, "height": 1080}}]}'
+)
+
+
+@pytest.mark.parametrize(
+    "mode, flags",
+    [
+        ("edge", (True, False)),
+        ("plasma", (False, True)),
+        ("both", (True, True)),
+        ("none", (False, False)),
+    ],
+)
+def test_the_checkboxes_map_onto_the_four_shell_values(mode, flags):
+    assert mode_flags(mode) == flags
+    assert mode_of(*flags) == mode
+
+
+def test_every_shell_value_has_its_checkboxes():
+    from typing import get_args
+
+    assert {mode_of(*mode_flags(m)) for m in get_args(ShellMode)} == set(get_args(ShellMode))
+
+
+def test_an_unknown_shell_value_is_an_error():
+    with pytest.raises(KeyError):
+        mode_flags("sideways")
+
+
+@pytest.mark.parametrize(
+    "value, label",
+    [
+        ("KDE", "KDE Plasma"),
+        ("KDE:plasma", "KDE Plasma"),
+        ("kde", "KDE Plasma"),
+        ("Hyprland", "Hyprland"),
+        ("GNOME:GNOME-Classic", "GNOME"),
+        ("X-Cinnamon", "Cinnamon"),
+        ("SomethingNew", NATIVE_FALLBACK),
+        ("", NATIVE_FALLBACK),
+        (" : ", NATIVE_FALLBACK),
+    ],
+)
+def test_the_native_checkbox_is_labelled_with_the_desktop(value, label):
+    assert desktop_label({"XDG_CURRENT_DESKTOP": value}) == label
+
+
+def test_no_desktop_variable_is_the_fallback():
+    assert desktop_label({}) == NATIVE_FALLBACK == "Native desktop"
+
+
+def test_the_label_reads_the_environment_by_default(monkeypatch):
+    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "Hyprland")
+    assert desktop_label() == "Hyprland"
+
+
+def test_detect_reads_the_monitors():
+    outputs = detect_outputs(lambda: KSCREEN)
+    assert [(o.name, o.width, o.height) for o in outputs] == [("HDMI-A-1", 1920, 1080)]
+
+
+@pytest.mark.parametrize(
+    "error",
+    [
+        OSError("No such file or directory: 'kscreen-doctor'"),
+        subprocess.TimeoutExpired(["kscreen-doctor", "-j"], 5),
+        subprocess.CalledProcessError(1, ["kscreen-doctor", "-j"]),
+    ],
+)
+def test_a_failed_detection_raises_with_the_reason(error):
+    def read():
+        raise error
+
+    with pytest.raises(DetectError, match="kscreen-doctor failed"):
+        detect_outputs(read)
+
+
+def test_unexpected_output_raises():
+    with pytest.raises(DetectError, match="kscreen-doctor failed"):
+        detect_outputs(lambda: "not json")
+
+
+def test_the_default_reader_is_looked_up_when_called(monkeypatch):
+    """No test ever runs kscreen-doctor: the default reader can be replaced."""
+    monkeypatch.setattr(screens, "read_kscreen_json", lambda: KSCREEN)
+    assert [o.name for o in detect_outputs()] == ["HDMI-A-1"]
+
+
+@pytest.mark.parametrize("module", ["settings.screens", "settings.pages"])
+def test_the_pure_modules_import_no_gtk(module):
+    code = f"import sys, {module}; print(any(m.startswith(('gi', 'fabric')) for m in sys.modules))"
+    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
+    assert out.stdout.strip() == "False"
```

- [ ] **Step 2: Run them to see them fail**

Run: `scripts/py -m pytest -q tests/test_settings_screens.py tests/test_settings_pages.py`
Expected: `2 errors` during collection (`ModuleNotFoundError: No module named 'settings.screens'` / `'settings.pages'`).

- [ ] **Step 3: Implement:**

```diff
diff --git a/settings/pages.py b/settings/pages.py
new file mode 100644
index 0000000..0a97098
--- /dev/null
+++ b/settings/pages.py
@@ -0,0 +1,88 @@
+"""The settings window's pages and the tree that selects them (panel/widget spec 7). Pure: no
+GTK.
+
+A page is named by a string, its Gtk.Stack child name: "theme", "monitor:NAME" and
+"panel:NAME:INDEX" (INDEX: the entry's place in [[monitors.NAME.panels]], 0-based; panels are
+tracked by index, spec 3.1). The tree lists Theme, then one row per monitor (connected ones
+first in kscreen order, then the ones only in the config, "(not connected)"), each with its
+panels by name as children.
+"""
+
+from __future__ import annotations
+
+from dataclasses import dataclass
+
+from settings.values import monitor_names
+from shell.config.models import Config
+from shell.outputs import Output
+
+THEME = "theme"
+NOT_CONNECTED = " (not connected)"
+
+
+def monitor_page(name: str) -> str:
+    return f"monitor:{name}"
+
+
+def panel_page(name: str, index: int) -> str:
+    return f"panel:{name}:{index}"
+
+
+@dataclass(frozen=True)
+class PageRef:
+    kind: str  # "theme" | "monitor" | "panel"
+    monitor: str | None = None
+    index: int | None = None
+
+
+def parse_page(page: str) -> PageRef:
+    """The parts of a page name; ValueError for anything that is not one."""
+    if page == THEME:
+        return PageRef("theme")
+    kind, sep, rest = page.partition(":")
+    if kind == "monitor" and sep:
+        return PageRef("monitor", rest)
+    if kind == "panel":
+        name, sep, index = rest.rpartition(":")
+        if sep and index.isascii() and index.isdigit():
+            return PageRef("panel", name, int(index))
+    raise ValueError(f"not a settings page: {page!r}")
+
+
+def screen_of(page: str | None) -> str | None:
+    """The monitor a page belongs to (the toolbar's screen): a monitor page's own, a panel
+    page's monitor; None for the Theme page or no page."""
+    return None if page is None else parse_page(page).monitor
+
+
+def fallback_page(page: str) -> str:
+    """The page shown when `page` is gone after a rebuild (its panel removed, by an undo or a
+    hand edit; its monitor no longer listed): a panel's monitor page, else the Theme page. The
+    caller checks that the monitor page still exists."""
+    ref = parse_page(page)
+    return monitor_page(ref.monitor) if ref.kind == "panel" else THEME
+
+
+@dataclass(frozen=True)
+class TreeEntry:
+    page: str
+    title: str
+    children: tuple[TreeEntry, ...] = ()
+
+
+def tree_entries(config: Config | None, outputs: list[Output]) -> tuple[TreeEntry, ...]:
+    """The tree's rows. `config` None (the file is invalid: read-only) lists only Theme. A
+    monitor that is connected is listed whether or not the config has it; one only in the
+    config is "NAME (not connected)". A monitor's children are its panels by `name`, in the
+    order of its [[panels]] entries."""
+    entries = [TreeEntry(THEME, "Theme")]
+    if config is None:
+        return tuple(entries)
+    for name, connected in monitor_names(config, outputs):
+        panels = tuple(
+            TreeEntry(panel_page(name, i), entry.name)
+            for i, entry in enumerate(config.monitor(name).panels)
+        )
+        title = name if connected else name + NOT_CONNECTED
+        entries.append(TreeEntry(monitor_page(name), title, panels))
+    return tuple(entries)
diff --git a/settings/screens.py b/settings/screens.py
new file mode 100644
index 0000000..be9cfe5
--- /dev/null
+++ b/settings/screens.py
@@ -0,0 +1,77 @@
+"""The per-screen toolbar's logic (panel/widget spec 7). Pure: no GTK.
+
+- `mode_flags` / `mode_of`: the toolbar's two checkboxes (Edge Shell on this screen, the
+  native desktop on this screen) and the monitor's four-valued `shell` key. Edge on + native
+  off = "edge", edge off + native on = "plasma", both on = "both", both off = "none". The shell
+  does not hide or show Plasma's panel yet (spec 7, deferred), so "edge" and "both" behave the
+  same at runtime today: SHELL_NOTE says so under the checkboxes.
+- `desktop_label`: the native checkbox's label, from XDG_CURRENT_DESKTOP.
+- `detect_outputs`: the connected monitors (kscreen-doctor), raising DetectError on failure
+  (settings.app.connected_outputs, used at start, returns [] instead).
+"""
+
+from __future__ import annotations
+
+import os
+import subprocess
+from collections.abc import Callable, Mapping
+
+from shell.outputs import Output, parse_kscreen, read_kscreen_json
+
+_FLAGS: dict[str, tuple[bool, bool]] = {
+    "edge": (True, False),
+    "plasma": (False, True),
+    "both": (True, True),
+    "none": (False, False),
+}
+SHELL_NOTE = (
+    "Plasma's panel is not hidden or shown by Edge Shell yet; with both on, keep the bottom "
+    "edge free of Edge Shell panels"
+)
+# XDG_CURRENT_DESKTOP's first known component (matched without case) -> the checkbox's label
+DESKTOP_NAMES = {
+    "KDE": "KDE Plasma",
+    "Hyprland": "Hyprland",
+    "GNOME": "GNOME",
+    "sway": "Sway",
+    "niri": "niri",
+    "XFCE": "Xfce",
+    "LXQt": "LXQt",
+    "X-Cinnamon": "Cinnamon",
+    "MATE": "MATE",
+    "Budgie": "Budgie",
+    "COSMIC": "COSMIC",
+}
+NATIVE_FALLBACK = "Native desktop"
+
+
+def mode_flags(mode: str) -> tuple[bool, bool]:
+    """(Edge Shell on, native desktop on) for a `shell` value; KeyError for anything else."""
+    return _FLAGS[mode]
+
+
+def mode_of(edge: bool, native: bool) -> str:
+    """The `shell` value the two checkboxes write."""
+    return next(mode for mode, flags in _FLAGS.items() if flags == (bool(edge), bool(native)))
+
+
+def desktop_label(env: Mapping[str, str] | None = None) -> str:
+    """The native desktop's name: the first known component of XDG_CURRENT_DESKTOP ("KDE" in
+    "KDE:plasma") through DESKTOP_NAMES; NATIVE_FALLBACK when it is unset, empty or unknown."""
+    env = os.environ if env is None else env
+    first = env.get("XDG_CURRENT_DESKTOP", "").split(":")[0].strip().casefold()
+    names = {key.casefold(): label for key, label in DESKTOP_NAMES.items()}
+    return names.get(first, NATIVE_FALLBACK)
+
+
+class DetectError(Exception):
+    """The monitors could not be detected (the message says why)."""
+
+
+def detect_outputs(read: Callable[[], str] | None = None) -> list[Output]:
+    """The connected monitors now, from `read` (default: `kscreen-doctor -j`); DetectError when
+    it fails or prints something unexpected. Tests always pass `read`."""
+    try:
+        return parse_kscreen((read or read_kscreen_json)())
+    except (OSError, subprocess.SubprocessError, ValueError) as exc:
+        raise DetectError(f"kscreen-doctor failed: {exc}") from None
```

- [ ] **Step 4: Run them to see them pass**

Run: `scripts/py -m pytest -q tests/test_settings_screens.py tests/test_settings_pages.py`
Expected: `39 passed`.

- [ ] **Step 5: VERIFY**

Run: `scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q`
Expected: `All checks passed!`, `2418 passed`.

**Reviewer mutations:** `_FLAGS["both"] = (True, False)` (`test_the_checkboxes_map_onto_the_four_shell_values`); `desktop_label` without `.casefold()` (the `"kde"` case); `split(":")[0]` → `split(":")[-1]` (`"KDE:plasma"`); `detect_outputs` catching only `OSError` (the timeout and called-process cases); `read or read_kscreen_json` bound at definition (`test_the_default_reader_is_looked_up_when_called`); `parse_page` accepting a non-ASCII digit (`"panel:M:²"`); `fallback_page` returning THEME for a panel (`test_a_gone_panel_falls_back_...`); `tree_entries` listing panels for an unconnected monitor in another order or dropping the connected-but-unconfigured monitor (`test_the_tree_lists_theme_monitors_and_their_panels`).

- [ ] **Step 6: Commit**

```bash
git add settings/screens.py settings/pages.py tests/test_settings_screens.py tests/test_settings_pages.py
git commit -m "feat(settings): page names, the tree's rows, the mode checkboxes and the desktop name" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 3: The shell warns when the config names a monitor that is not connected

**Files:**
- Create: `shell/monitor_check.py`
- Modify: `shell/app.py` (`__init__`, `sync_monitors`, new `_check_monitor_names`, imports)
- Test: `tests/test_monitor_check.py` (new), `tests/test_app_sync.py` (an autouse fixture that stubs `subprocess.Popen`, four tests)

**Interfaces:**
- Consumes: `EdgeShellApp.sync_monitors` (`connected = monitors_by_name()`; returns early when the mapping is empty and shells exist), `EdgeShellApp._notify(title, message)`, `self.config.monitors`.
- Produces: `shell.monitor_check.TITLE = "Monitor not connected"`, `unknown_monitors(configured: Iterable[str], connected: Iterable[str]) -> list[str]`, `monitor_report(configured, connected) -> str | None`; `EdgeShellApp._monitors_reported: str | None`, `EdgeShellApp._check_monitor_names(connected) -> None` (Task 9 reuses `monitor_report` and `unknown_monitors` in the window).

- [ ] **Step 1: Write the failing tests:**

```diff
diff --git a/tests/test_app_sync.py b/tests/test_app_sync.py
index 2b2a0d9..e14a55a 100644
--- a/tests/test_app_sync.py
+++ b/tests/test_app_sync.py
@@ -65,6 +65,13 @@ def _reset_fake_shell(monkeypatch):
         monkeypatch.setattr(FakeShell, attr, value)
 
 
+@pytest.fixture(autouse=True)
+def _no_notify_send(monkeypatch):
+    """No test here starts notify-send (a monitor-name warning would show on the desktop);
+    a test that checks the command patches Popen itself."""
+    monkeypatch.setattr(app_mod.subprocess, "Popen", lambda *_a, **_k: None)
+
+
 @pytest.fixture
 def env(monkeypatch, make_config):
     mapping: dict = {}
@@ -817,3 +824,64 @@ def test_a_panel_that_fails_again_after_a_relayout_rebuild_is_notified_again(env
     shell = app.shells["HDMI-A-1"]
     shell.on_error(shell)
     assert notes.count(failure) == 2
+
+
+# ---- monitor names in the config against the connected monitors --------------------------
+
+
+def test_a_configured_monitor_that_is_not_connected_is_reported_once(env, monkeypatch, caplog):
+    app, mapping = env  # the config names HDMI-A-1
+    notes = []
+    monkeypatch.setattr(app_mod.EdgeShellApp, "_notify", lambda self, *a: notes.append(a))
+    caplog.set_level("WARNING", logger="shell.app")
+    mapping["DP-1"] = object()
+    app.sync_monitors()
+    app.sync_monitors()  # the same mismatch: nothing new
+    assert notes == [
+        (
+            "Monitor not connected",
+            "config monitors: HDMI-A-1; connected: DP-1\nUse the connected names in the config.",
+        )
+    ]
+    assert caplog.text.count("config monitors: HDMI-A-1; connected: DP-1") == 1
+    assert app.shells == {}  # unchanged behaviour: no frame for a monitor that is not there
+
+
+def test_the_report_comes_again_after_the_names_matched(env, monkeypatch):
+    app, mapping = env
+    notes = []
+    monkeypatch.setattr(app_mod.EdgeShellApp, "_notify", lambda self, *a: notes.append(a))
+    mapping["DP-1"] = object()
+    app.sync_monitors()
+    mapping["HDMI-A-1"] = object()  # plugged in: every name matches, nothing said
+    app.sync_monitors()
+    del mapping["HDMI-A-1"]  # out again: said again
+    app.sync_monitors()
+    assert len(notes) == 2
+
+
+def test_a_connected_monitor_the_config_does_not_name_is_fine(env, monkeypatch):
+    app, mapping = env
+    notes = []
+    monkeypatch.setattr(app_mod.EdgeShellApp, "_notify", lambda self, *a: notes.append(a))
+    mapping["HDMI-A-1"] = object()
+    mapping["DP-1"] = object()  # not in the config: it keeps plasma
+    app.sync_monitors()
+    assert notes == []
+
+
+def test_a_reload_with_the_same_mismatch_says_nothing_new(renv, monkeypatch):
+    app, store, _errors, mapping, make_config = renv
+    notes = []
+    monkeypatch.setattr(app_mod.EdgeShellApp, "_notify", lambda self, *a: notes.append(a))
+    panels = [{"panel": "edge", "name": "dock", "widget": "dock"}]
+    store.pending = make_config(monitors={"HDMI-A-1": mon(panels=panels), "HDMI-A-2": mon()})
+    app.reload()
+    store.pending = make_config(
+        theme={"accent": "#112233"},
+        monitors={"HDMI-A-1": mon(panels=panels), "HDMI-A-2": mon()},
+    )
+    app.reload()  # e.g. the next change from the settings window
+    assert [n[1].splitlines()[0] for n in notes] == [
+        "config monitors: HDMI-A-2; connected: HDMI-A-1"
+    ]
diff --git a/tests/test_monitor_check.py b/tests/test_monitor_check.py
new file mode 100644
index 0000000..9c8ec57
--- /dev/null
+++ b/tests/test_monitor_check.py
@@ -0,0 +1,31 @@
+"""shell.monitor_check: configured monitor names against the connected ones (pure)."""
+
+import pytest
+
+from shell.monitor_check import monitor_report, unknown_monitors
+
+
+def test_a_configured_name_that_is_not_connected_is_reported_with_the_names_to_use():
+    report = monitor_report(["HDMI-A-2", "DP-1"], ["HDMI-A-1", "DP-1"])
+    assert report == "config monitors: HDMI-A-2; connected: DP-1, HDMI-A-1"
+
+
+@pytest.mark.parametrize(
+    "configured, connected",
+    [
+        (["HDMI-A-1"], ["HDMI-A-1", "DP-1"]),  # every configured name is connected
+        ([], ["HDMI-A-1"]),  # the config names no monitor
+        (["HDMI-A-1"], []),  # nothing known to be connected: nothing to compare
+    ],
+)
+def test_no_report(configured, connected):
+    assert monitor_report(configured, connected) is None
+
+
+def test_a_connected_monitor_missing_from_the_config_is_not_reported():
+    assert unknown_monitors(["DP-1"], ["DP-1", "HDMI-A-1"]) == []
+
+
+def test_unknown_names_are_sorted_and_counted_once():
+    assert unknown_monitors(["b", "a", "b", "DP-1"], ["DP-1"]) == ["a", "b"]
+    assert monitor_report({"b": 1, "a": 2}, {"DP-1": 0}) == "config monitors: a, b; connected: DP-1"
```

- [ ] **Step 2: Run them to see them fail**

Run: `scripts/py -m pytest -q tests/test_monitor_check.py tests/test_app_sync.py`
Expected: `1 error` during collection (`ModuleNotFoundError: No module named 'shell.monitor_check'`); with that file aside, three of the four new `test_app_sync.py` tests fail (no notification is sent; the fourth, a connected monitor the config does not name, passes before and after).

- [ ] **Step 3: Implement:**

```diff
diff --git a/shell/app.py b/shell/app.py
index bbbcd76..76d301e 100644
--- a/shell/app.py
+++ b/shell/app.py
@@ -26,6 +26,8 @@ from shell.canvas.stats import StatsRecorder
 from shell.config.diff import diff_configs
 from shell.config.store import ConfigStore
 from shell.config.watcher import ConfigWatcher
+from shell.monitor_check import TITLE as MONITOR_TITLE
+from shell.monitor_check import monitor_report
 from shell.monitors import MonitorShell, monitors_by_name
 from shell.registry import all_off_paths, deprecated_pos_paths, moved_default_paths
 from shell.theme import scope_class, to_css
@@ -55,6 +57,7 @@ class EdgeShellApp:
         self._layout_reported: dict[str, list[str]] = {}  # last notified warnings per monitor
         self._failures_reported: dict[str, list[str]] = {}  # last notified build failures
         self._relayout_rebuilt: set[str] = set()  # rebuilt after a failed re-layout, until a reload
+        self._monitors_reported: str | None = None  # the last monitor_report notified
         self._log_deprecated(store.config)
 
     @property
@@ -81,6 +84,7 @@ class EdgeShellApp:
             # kscreen-doctor failed or a hot-plug flap; closing all would blank every frame
             log.warning("monitor mapping unavailable, keeping current shells")
             return set(), set()
+        self._check_monitor_names(connected)
         wanted = plan.desired_shells(self.config, connected)
         desired = {name: connected[name] for name in wanted}
         active = {name: shell.monitor for name, shell in self.shells.items()}
@@ -94,6 +98,20 @@ class EdgeShellApp:
             self.refresh_css()
         return set(close), set(open_)
 
+    def _check_monitor_names(self, connected) -> None:
+        """Warn (log and one notification) when the config names a monitor that is not
+        connected, with the names to use; again only when the text changes (a config that
+        names another monitor, a monitor plugged in or out), so a reload with the same
+        mismatch, such as each change from the settings window, says nothing new. A match
+        forgets the last report: a later mismatch is reported again."""
+        report = monitor_report(self.config.monitors, connected)
+        if report == self._monitors_reported:
+            return
+        self._monitors_reported = report
+        if report is not None:
+            log.warning("monitor names in the config are not connected (%s)", report)
+            self._notify(MONITOR_TITLE, f"{report}\nUse the connected names in the config.")
+
     def _close_shell(self, name: str) -> None:
         self._forget_reports(name)
         self.shells.pop(name).close()
diff --git a/shell/monitor_check.py b/shell/monitor_check.py
new file mode 100644
index 0000000..6eb396c
--- /dev/null
+++ b/shell/monitor_check.py
@@ -0,0 +1,32 @@
+"""Monitor names in the config against the connected monitors (Phil, 2026-10-15: "if they
+match everything is fine, if they do not then a warning should be output with the monitor
+names that should be used"). Pure: the shell (shell/app.py) and the settings window
+(settings/pages.py, the Detect monitors button) use the same comparison and text.
+
+A configured name that is not connected is reported, with the connected names to use instead;
+a connected monitor the config does not name is fine (it keeps the default, plasma) and is not
+reported. Nothing changes in what the shell does: a monitor that is not connected has no
+frame, as before."""
+
+from __future__ import annotations
+
+from collections.abc import Iterable
+
+TITLE = "Monitor not connected"
+
+
+def unknown_monitors(configured: Iterable[str], connected: Iterable[str]) -> list[str]:
+    """The configured monitor names that are not connected, sorted."""
+    known = set(connected)
+    return sorted(name for name in set(configured) if name not in known)
+
+
+def monitor_report(configured: Iterable[str], connected: Iterable[str]) -> str | None:
+    """The text 'config monitors: HDMI-A-2; connected: DP-1, HDMI-A-1', or None when every
+    configured name is connected (or the config names none). With nothing connected known
+    (kscreen-doctor failed, or a hot-plug flap) there is nothing to compare against: None."""
+    connected = sorted(set(connected))
+    unknown = unknown_monitors(configured, connected)
+    if not unknown or not connected:
+        return None
+    return f"config monitors: {', '.join(unknown)}; connected: {', '.join(connected)}"
```

- [ ] **Step 4: Run them to see them pass**

Run: `scripts/py -m pytest -q tests/test_monitor_check.py tests/test_app_sync.py`
Expected: all pass (10 new).

- [ ] **Step 5: VERIFY**

Run: `scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q`
Expected: `All checks passed!`, `2428 passed`.

**Reviewer mutations:** `if report == self._monitors_reported: return` removed (`test_a_configured_monitor_that_is_not_connected_is_reported_once`, `test_a_reload_with_the_same_mismatch_says_nothing_new`); `self._monitors_reported = report` only when `report is not None` (`test_the_report_comes_again_after_the_names_matched`); `or not connected` removed from `monitor_report` (`test_no_report[configured2-connected2]`); `unknown_monitors` comparing the other way round (connected not configured: `test_a_connected_monitor_missing_from_the_config_is_not_reported`, `test_a_connected_monitor_the_config_does_not_name_is_fine`); the check moved before the early return of `sync_monitors` (no test change needed: it would then report against an empty mapping, which `monitor_report` answers None; reviewer reads it).

- [ ] **Step 6: Commit**

```bash
git add shell/monitor_check.py shell/app.py tests/test_monitor_check.py tests/test_app_sync.py
git commit -m "feat(shell): warn when the config names a monitor that is not connected" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 4: One edit queue applies every edit in order

**Files:**
- Create: `settings/queue.py`
- Modify: `settings/fields.py` (`FieldRow`: no timer; `on_queue`, `is_pending`, `unsent`; `GLib` no longer imported there), `settings/view.py` (the queue, `_run_queue`, `_drain`, `_apply_queued`, `_tell_dropped`, `retire`; `flush`, `rebuild`, `revert`, `file_changed` on the queue; `_flush_first` goes), `settings/controller.py` (`_drop_view` calls `view.retire()`)
- Test: `tests/test_settings_queue.py` (new), `tests/test_settings_fields.py` (9 row tests rewritten: rows queue, they hold no timer), `tests/test_settings_view.py` (the timer fixtures patch `settings.view`'s `GLib`; `type_into` waits for the queue; 10 new queue tests), `tests/test_settings_controller.py` (fixture patch target; `test_closing_retires_the_view`)

**Interfaces:**
- Consumes: `SettingsSession.apply`, `ChangedOutside`, `settings.values.panel_ops`, `lookup`; `FieldRow(spec, path, on_change, on_reset)`.
- Produces: `settings.queue.RESET`, `QueuedEdit(path, value, base)`, `EditQueue.push(path, value, base=...)`, `.pop() -> QueuedEdit | None`, `.drop() -> list[QueuedEdit]`, `.pending(path) -> bool`, `len()`, iteration; `path_text(path) -> str`, `describe(edits) -> str`. `FieldRow(spec, path, on_change, on_reset, on_queue: Callable[[tuple, Any, Any], None] | None = None, is_pending: Callable[[tuple], bool] | None = None)`, `FieldRow.unsent() -> bool` (`cancel_pending` and the row timer are gone). `SettingsView.queue: EditQueue`, `SettingsView._on_queue(path, value, base)`, `_queue_due()`, `_run_queue(defer=False)`, `retire()`; `flush(defer=False)` and `rebuild()` keep their names and meaning (both apply the queue). Tasks 6-9 build on these.

- [ ] **Step 1: Write the failing tests:**

```diff
diff --git a/tests/test_settings_controller.py b/tests/test_settings_controller.py
index 85e4db5..8e4d537 100644
--- a/tests/test_settings_controller.py
+++ b/tests/test_settings_controller.py
@@ -99,10 +99,10 @@ def make(tmp_path, fake_registry):
 @pytest.fixture
 def pending(monkeypatch):
     """Spin pauses never fire on their own: a typed value stays pending until flushed."""
-    import settings.fields as fields
+    import settings.view as view_module
 
-    monkeypatch.setattr(fields.GLib, "timeout_add", lambda _ms, _fn: 3)
-    monkeypatch.setattr(fields.GLib, "source_remove", lambda _id: None)
+    monkeypatch.setattr(view_module.GLib, "timeout_add", lambda _ms, _fn: 3)
+    monkeypatch.setattr(view_module.GLib, "source_remove", lambda _id: None)
 
 
 def row(c, path):
@@ -359,6 +359,15 @@ def test_close_shows_the_empty_page_where_only_new_open_and_exit_work(make):
     assert c.view is None
 
 
+def test_closing_retires_the_view(make, pending):
+    c, path = make()
+    view = c.view
+    row(c, DEPTH).editor.widget.set_value(120)  # queued
+    c.dialogs_.unsaved = Answer.DISCARD
+    run(c, "close")
+    assert len(view.queue) == 0 and not view._queue_timer and "depth" not in path.read_text()
+
+
 def test_close_with_unsaved_changes_asks_and_cancel_keeps_the_config(make):
     c, path = make()
     c.view._on_change(DEPTH, 90)
diff --git a/tests/test_settings_fields.py b/tests/test_settings_fields.py
index f170187..49fa26b 100644
--- a/tests/test_settings_fields.py
+++ b/tests/test_settings_fields.py
@@ -18,18 +18,14 @@ from settings.form import FieldSpec, WidgetChoice, config_form  # noqa: E402
 from settings.values import FieldValue  # noqa: E402
 
 FORM = config_form(tuple(WidgetChoice(w) for w in ("clock", "dock", "system_bar")))
-REAL_TIMEOUT_ADD = GLib.timeout_add
 
 
-@pytest.fixture(autouse=True)
-def immediate(monkeypatch):
-    """Debounced edits fire at once (no main loop in tests)."""
-    monkeypatch.setattr(fields.GLib, "timeout_add", lambda _ms, fn: fn() and 0)
-
-
-def row_for(spec, value, is_set=False, path=("theme", "x")):
+def row_for(spec, value, is_set=False, path=("theme", "x"), queued=None):
+    """A row; with `queued` (a list) its spin edits go there as (path, value, base), as they
+    go to the view's queue."""
     changes, resets = [], []
-    row = fields.FieldRow(spec, path, lambda p, v: changes.append((p, v)), resets.append)
+    on_queue = None if queued is None else lambda p, v, b: queued.append((p, v, b))
+    row = fields.FieldRow(spec, path, lambda p, v: changes.append((p, v)), resets.append, on_queue)
     row.show_value(FieldValue(value, is_set, "default"))
     return row, changes, resets
 
@@ -59,32 +55,23 @@ def test_colour_row_writes_hex_with_alpha_only_when_needed():
     assert changes == [(("theme", "accent"), "#00000080"), (("theme", "accent"), "#ffffff")]
 
 
-def test_int_row_takes_its_bounds_from_the_schema_and_is_debounced(monkeypatch):
-    timers, removed = [], []
-    monkeypatch.setattr(
-        fields.GLib, "timeout_add", lambda ms, fn: timers.append((ms, fn)) or 6 + len(timers)
-    )
-    monkeypatch.setattr(fields.GLib, "source_remove", removed.append)
-    row, changes, _ = row_for(FORM.theme.field("thickness"), 10)
+def test_int_row_takes_its_bounds_from_the_schema_and_queues_its_edits():
+    queued = []
+    row, changes, _ = row_for(FORM.theme.field("thickness"), 10, queued=queued)
     spin = row.editor.widget
     assert tuple(spin.get_range()) == (2.0, 64.0)
     spin.set_value(11)
     spin.set_value(12)
-    assert changes == []  # waits for the pause
-    assert [ms for ms, _fn in timers] == [fields.DEBOUNCE_MS, fields.DEBOUNCE_MS]
-    assert removed == [7]  # one timer per pause: the first was cancelled by the second edit
-    timers[-1][1]()
-    assert changes == [(("theme", "x"), 12)]
+    assert changes == []  # the view applies them after the pause
+    # the base is the value the row showed, also for the second step (the queue un-queues a
+    # change back to it)
+    assert queued == [(("theme", "x"), 11, 10), (("theme", "x"), 12, 10)]
 
 
-def test_a_new_value_cancels_a_pending_edit(monkeypatch):
-    removed = []
-    monkeypatch.setattr(fields.GLib, "timeout_add", lambda _ms, _fn: 9)
-    monkeypatch.setattr(fields.GLib, "source_remove", removed.append)
+def test_a_row_without_a_queue_sends_spin_edits_at_once():
     row, changes, _ = row_for(FORM.theme.field("thickness"), 10)
     row.editor.widget.set_value(11)
-    row.show_value(FieldValue(10, False, "default"))  # e.g. the file was re-read
-    assert removed == [9] and changes == []
+    assert changes == [(("theme", "x"), 11)]
 
 
 def test_unset_optional_int_shows_the_minimum():
@@ -164,19 +151,21 @@ def test_the_mouse_wheel_never_edits_a_row():
     assert edits == changes == changes2 == []
 
 
-def test_flush_sends_a_pending_spin_value_and_typed_fonts(monkeypatch):
-    monkeypatch.setattr(fields.GLib, "timeout_add", lambda _ms, _fn: 5)
-    monkeypatch.setattr(fields.GLib, "source_remove", lambda _id: None)
-    spin, changes, _ = row_for(FORM.theme.field("thickness"), 10)
-    spin.editor.widget.set_value(14)
+def test_flush_sends_typed_text_only():
+    queued = []
+    spin, changes, _ = row_for(FORM.theme.field("thickness"), 10, queued=queued)
+    spin.editor.widget.set_text("14")  # typed, Enter not pressed
     fonts, changes2, _ = row_for(FORM.theme.field("font"), ["A"])
-    fonts.editor.widget.set_text("B, monospace")  # typed, Enter not pressed
+    fonts.editor.widget.set_text("B, monospace")
+    assert spin.unsent() and fonts.unsent()
     spin.flush()
     fonts.flush()
-    assert changes == [(("theme", "x"), 14)]
+    assert queued == [(("theme", "x"), 14, 10)] and changes == []
     assert changes2 == [(("theme", "x"), ["B", "monospace"])]
     spin.flush()
-    assert len(changes) == 1  # nothing pending any more
+    fonts.flush()
+    assert len(queued) == 1 and len(changes2) == 1  # nothing typed any more
+    assert not spin.unsent() and not fonts.unsent()
 
 
 def test_choices_show_their_labels():
@@ -227,54 +216,59 @@ def test_an_unknown_kind_has_no_editor():
         fields.make_editor(FieldSpec("x", "X", "blob"), lambda _v: None)  # type: ignore[arg-type]
 
 
-def fake_timers(monkeypatch):
-    """Debounce timers that never fire on their own: returns (started, removed) id lists."""
-    started, removed = [], []
+def test_a_discarded_row_never_calls_back():
+    queued = []
+    spin, changes, _ = row_for(FORM.theme.field("thickness"), 10, queued=queued)
+    name, changes2, _ = row_for(FORM.edge_panel.field("name"), "Dock")
+    for row in (spin, name):
+        row.discard()  # retired by a rebuild
+    spin.editor.widget.set_value(30)
+    name.editor.widget.set_text("Typed")
+    name.editor.widget.emit("activate")  # or the focus-out GTK sends when it is unparented
+    spin.flush()
+    name.flush()
+    assert queued == changes == changes2 == []
 
-    def add(_ms, _fn):
-        started.append(5 + len(started))
-        return started[-1]
 
-    monkeypatch.setattr(fields.GLib, "timeout_add", add)
-    monkeypatch.setattr(fields.GLib, "source_remove", removed.append)
-    return started, removed
+def test_a_row_starts_no_timer(monkeypatch):
+    """The spin pause is the view's one queue timer: a row never starts a timer of its own."""
 
+    def no_timer(*_a):
+        raise AssertionError("a row started a timer")
 
-def test_a_destroyed_row_cancels_its_pending_edit(monkeypatch):
-    started, removed = fake_timers(monkeypatch)
-    row, changes, _ = row_for(FORM.theme.field("thickness"), 10)
+    monkeypatch.setattr(GLib, "timeout_add", no_timer)
+    queued = []
+    row, _, _ = row_for(FORM.theme.field("thickness"), 10, queued=queued)
     row.editor.widget.set_value(30)
-    row.destroy()
-    assert removed == started and changes == []
+    length, _, _ = row_for(FORM.edge_panel.field("length"), 300, queued=queued)
+    length.editor.number.set_value(400)
+    assert [v for _p, v, _b in queued] == [30, 400]
 
 
-def test_a_destroyed_row_never_writes_when_the_loop_runs(monkeypatch):
-    monkeypatch.setattr(fields.GLib, "timeout_add", REAL_TIMEOUT_ADD)
-    row, changes, _ = row_for(FORM.theme.field("thickness"), 10)
-    row.editor.widget.set_value(30)
-    row.destroy()
-    deadline = GLib.get_monotonic_time() + 500_000
-    while GLib.get_monotonic_time() < deadline:
-        GLib.MainContext.default().iteration(False)
-    assert changes == []
+def test_a_refresh_keeps_a_queued_edit_and_typed_text():
+    queued, pending = [], set()
 
+    def on_queue(path, value, base):
+        queued.append(value)
+        pending.add(path)
 
-def test_a_refresh_keeps_the_pending_edit_of_another_row(monkeypatch):
-    started, removed = fake_timers(monkeypatch)
-    thick, changes, _ = row_for(FORM.theme.field("thickness"), 10)
+    thick = fields.FieldRow(
+        FORM.theme.field("thickness"), ("theme", "x"), id, id, on_queue, pending.__contains__
+    )
+    thick.show_value(FieldValue(10, False, "default"))
     thick.editor.widget.set_value(30)
-    thick.show_value(FieldValue(10, False, "inherited"), keep_pending=True)
-    assert removed == [] and thick.editor.widget.get_value() == 30
+    thick.show_value(FieldValue(10, False, "inherited"), keep_pending=True)  # another apply
+    assert thick.editor.widget.get_value() == 30  # still the queued 30
     assert thick.source.get_text().endswith("inherited")
-    thick.flush()
-    assert changes == [(("theme", "x"), 30)]
-    thick.editor.widget.set_value(12)  # a plain show_value still drops the edit
-    thick.show_value(FieldValue(30, True, "your config"))
-    assert thick.editor.widget.get_value() == 30 and removed == [started[0], started[1]]
+    pending.clear()  # the view applied it
+    thick.show_value(FieldValue(30, True, "your config"), keep_pending=True)
+    assert thick.editor.widget.get_value() == 30 and thick.source.get_text().endswith("config")
+    thick.editor.widget.set_value(12)  # queued again; a plain show_value (a re-read) shows
+    thick.show_value(FieldValue(30, True, "your config"))  # the file's value all the same
+    assert thick.editor.widget.get_value() == 30
 
 
-def test_closing_applies_every_row_even_when_each_apply_refreshes_all(monkeypatch):
-    fake_timers(monkeypatch)
+def test_closing_applies_every_row_even_when_each_apply_refreshes_all():
     result, rows = {}, []
 
     def on_change(path, value):
@@ -295,16 +289,20 @@ def test_closing_applies_every_row_even_when_each_apply_refreshes_all(monkeypatc
     assert result == {"t": 20, "f": ["B", "C"]}
 
 
-def test_a_toggle_within_the_pause_does_not_drop_a_pending_spin(monkeypatch):
-    fake_timers(monkeypatch)
-    result, rows = {}, []
+def test_a_toggle_within_the_pause_does_not_drop_a_queued_spin():
+    result, rows, queue = {}, [], {}
 
     def on_change(path, value):
         result[path[1]] = value
         for row in rows:
             row.show_value(FieldValue(result.get(row.path[1], 10), True, "x"), True)
 
-    thick = fields.FieldRow(FORM.theme.field("thickness"), ("theme", "t"), on_change, id)
+    def on_queue(path, value, _base):
+        queue[path] = value
+
+    thick = fields.FieldRow(
+        FORM.theme.field("thickness"), ("theme", "t"), on_change, id, on_queue, queue.__contains__
+    )
     flag = fields.FieldRow(
         FORM.theme.section("border").field("enabled"), ("theme", "b"), on_change, id
     )
@@ -312,9 +310,9 @@ def test_a_toggle_within_the_pause_does_not_drop_a_pending_spin(monkeypatch):
     thick.show_value(FieldValue(10, False, "default"))
     flag.show_value(FieldValue(False, False, "default"))
     thick.editor.widget.set_value(14)
-    flag.editor.widget.set_active(True)
-    thick.flush()
-    assert result == {"t": 14, "b": True}
+    flag.editor.widget.set_active(True)  # applied now: every row is refreshed
+    assert result == {"b": True} and queue == {("theme", "t"): 14}
+    assert thick.editor.widget.get_value() == 14
 
 
 def test_empty_or_invalid_spin_text_writes_nothing():
@@ -337,8 +335,7 @@ def test_empty_or_invalid_spin_text_writes_nothing():
                 assert changes == [], (spec.key, text)
 
 
-def test_flush_sends_a_number_typed_without_enter(monkeypatch):
-    fake_timers(monkeypatch)
+def test_flush_sends_a_number_typed_without_enter():
     for spec, value, typed, expected in [
         (FORM.theme.field("thickness"), 10, "20", 20),
         (FORM.edge_panel.field("length"), 300, "200", 200),
@@ -353,19 +350,13 @@ def test_flush_sends_a_number_typed_without_enter(monkeypatch):
         assert len(changes) == 1  # invalid text sends nothing
 
 
-def test_a_value_changed_back_within_the_pause_is_not_written(monkeypatch):
-    fake_timers(monkeypatch)
-    row, changes, _ = row_for(FORM.theme.field("thickness"), 10, is_set=False)
+def test_a_value_changed_back_is_queued_with_the_shown_value_as_its_base():
+    """The queue then un-queues it (settings.queue): an inherited value is not pinned."""
+    queued = []
+    row, changes, _ = row_for(FORM.theme.field("thickness"), 10, queued=queued)
     row.editor.widget.set_value(11)
     row.editor.widget.set_value(10)
-    row.flush()
-    assert changes == []  # an inherited value is not pinned by a no-op
-    row.editor.widget.set_value(12)
-    row.flush()
-    assert changes == [(("theme", "x"), 12)]
-    row.editor.widget.set_value(12)
-    row.flush()
-    assert len(changes) == 1
+    assert queued == [(("theme", "x"), 11, 10), (("theme", "x"), 10, 10)] and changes == []
 
 
 def test_choosing_the_same_colour_writes_nothing():
diff --git a/tests/test_settings_queue.py b/tests/test_settings_queue.py
new file mode 100644
index 0000000..78efd37
--- /dev/null
+++ b/tests/test_settings_queue.py
@@ -0,0 +1,68 @@
+"""settings.queue: the edit queue's order, coalescing and the text of dropped edits (pure)."""
+
+from settings.queue import RESET, EditQueue, describe, path_text
+
+A, B, C = ("theme", "a"), ("theme", "b"), ("monitors", "M", "panels", 0, "depth")
+
+
+def order(queue):
+    return [(e.path, e.value) for e in queue]
+
+
+def test_edits_come_out_in_arrival_order():
+    q = EditQueue()
+    q.push(A, 1)
+    q.push(B, 2)
+    q.push(C, RESET)
+    assert [q.pop().path for _ in range(3)] == [A, B, C]
+    assert q.pop() is None and len(q) == 0
+
+
+def test_a_new_edit_of_a_queued_path_replaces_it_and_moves_to_the_end():
+    q = EditQueue()
+    q.push(A, 1)
+    q.push(B, 2)
+    q.push(A, 3)
+    assert order(q) == [(B, 2), (A, 3)] and len(q) == 2
+
+
+def test_an_edit_back_to_the_shown_value_takes_the_path_out():
+    q = EditQueue()
+    q.push(A, 11, base=10)
+    q.push(A, 12, base=11)  # the base stays the first one: 10
+    q.push(A, 10, base=12)
+    assert not q.pending(A) and len(q) == 0
+    q.push(A, 10, base=10)  # a no-op is never queued
+    assert len(q) == 0
+
+
+def test_a_base_compares_type_and_value():
+    q = EditQueue()
+    q.push(A, 1, base=True)  # 1 == True in Python, but it is another value here
+    assert q.pending(A)
+
+
+def test_without_a_base_every_edit_is_queued():
+    q = EditQueue()
+    q.push(A, 10)
+    q.push(A, 10)
+    assert order(q) == [(A, 10)]
+
+
+def test_drop_empties_the_queue_and_returns_what_it_held():
+    q = EditQueue()
+    q.push(A, 1)
+    q.push(B, RESET)
+    dropped = q.drop()
+    assert [(e.path, e.value) for e in dropped] == [(A, 1), (B, RESET)] and len(q) == 0
+
+
+def test_dropped_edits_are_named_with_their_paths():
+    q = EditQueue()
+    q.push(C, 120)
+    q.push(A, RESET)
+    q.push(B, "#112233")
+    assert describe(q.drop()) == (
+        "monitors.M.panels[0].depth = 120, theme.a (reset), theme.b = '#112233'"
+    )
+    assert path_text(("theme",)) == "theme"
diff --git a/tests/test_settings_view.py b/tests/test_settings_view.py
index 7e50ec7..e14d306 100644
--- a/tests/test_settings_view.py
+++ b/tests/test_settings_view.py
@@ -276,10 +276,10 @@ def test_an_unwritable_folder_shows_in_the_banner(make):
 
 
 def test_close_flushes_a_pending_spin_value(make, monkeypatch):
-    import settings.fields as fields
+    import settings.view as view_module
 
-    monkeypatch.setattr(fields.GLib, "timeout_add", lambda _ms, _fn: 3)
-    monkeypatch.setattr(fields.GLib, "source_remove", lambda _id: None)
+    monkeypatch.setattr(view_module.GLib, "timeout_add", lambda _ms, _fn: 3)
+    monkeypatch.setattr(view_module.GLib, "source_remove", lambda _id: None)
     view, path = make()
     row(view, DEPTH).editor.widget.set_value(120)  # inside the 400 ms pause
     assert "depth" not in path.read_text()
@@ -290,10 +290,10 @@ def test_close_flushes_a_pending_spin_value(make, monkeypatch):
 @pytest.fixture
 def pending(monkeypatch):
     """Spin pauses never fire on their own: a typed value stays pending until flushed."""
-    import settings.fields as fields
+    import settings.view as view_module
 
-    monkeypatch.setattr(fields.GLib, "timeout_add", lambda _ms, _fn: 3)
-    monkeypatch.setattr(fields.GLib, "source_remove", lambda _id: None)
+    monkeypatch.setattr(view_module.GLib, "timeout_add", lambda _ms, _fn: 3)
+    monkeypatch.setattr(view_module.GLib, "source_remove", lambda _id: None)
 
 
 def test_another_rows_apply_keeps_a_pending_spin_value(make, pending):
@@ -381,10 +381,10 @@ def test_reset_of_a_corner_gives_the_edge_combo_the_default_corners_edges(make,
 @pytest.fixture
 def timers(monkeypatch):
     """Spin pauses never fire on their own, but their timer ids are real (a flush cancels)."""
-    import settings.fields as fields
+    import settings.view as view_module
 
-    monkeypatch.setattr(fields.GLib, "timeout_add", lambda _ms, _fn: 3)
-    monkeypatch.setattr(fields.GLib, "source_remove", lambda _id: None)
+    monkeypatch.setattr(view_module.GLib, "timeout_add", lambda _ms, _fn: 3)
+    monkeypatch.setattr(view_module.GLib, "source_remove", lambda _id: None)
 
 
 THICKNESS = ("monitors", "HDMI-A-1", "theme", "thickness")
@@ -485,10 +485,10 @@ MIN_LENGTH, MAX_LENGTH = (*P0, "min_length"), (*P0, "max_length")
 
 
 def type_into(view, path, value):
-    """A user edit of a spin row: the value typed, then its 400 ms pause over."""
+    """A user edit of a spin row: the value typed, then its 400 ms pause over (the queue)."""
     r = row(view, path)
     r.editor.widget.set_value(value)
-    r.flush()
+    view._queue_due()
     return r
 
 
@@ -532,15 +532,19 @@ def test_a_rebuild_from_a_widgets_own_signal_destroys_that_widget_only_when_idle
     assert destroyed == [combo]
 
 
-def test_a_rebuild_cancels_the_old_rows_pending_values_at_once(make, pending):
-    """Their destroy now waits for the idle loop: a pending pause must not write meanwhile."""
+def test_a_hand_edit_drops_the_queue_and_its_timer_at_once(make, monkeypatch):
+    """The old rows are destroyed when the loop is idle: no queued value may be written
+    meanwhile, and none is lost without a word."""
+    started, removed = [], []
+    monkeypatch.setattr(GLib, "timeout_add", lambda _ms, _fn: started.append(7) or 7)
+    monkeypatch.setattr(GLib, "source_remove", removed.append)
     view, path = make()
-    old = row(view, DEPTH)
-    old.editor.widget.set_value(120)
-    assert old._timer
+    row(view, DEPTH).editor.widget.set_value(120)
+    assert view.queue.pending(DEPTH) and started == [7]
     path.write_text(USER.replace('shell = "edge"', 'shell = "both"'))
-    view.file_changed()  # a hand edit: rebuild, pending values go with the old rows
-    assert not old._timer
+    view.file_changed()  # a hand edit: rebuild; the queue was made for the old file
+    assert len(view.queue) == 0 and removed == [7] and not view._queue_timer
+    assert "monitors.HDMI-A-1.panels[0].depth = 120" in view.banner_label.get_text()
 
 
 def test_the_revert_dialog_says_where_an_invalid_hand_edit_is_kept(make):
@@ -829,3 +833,117 @@ def test_a_successful_save_clears_an_old_error_banner(make):
 @pytest.mark.parametrize("text", ["A & B", "<b>x</b>", "HDMI & <DP>"])
 def test_a_heading_with_markup_characters_is_shown_as_text(text):
     assert SettingsView._heading(text).get_text() == text
+
+
+# ---- the edit queue (settings.queue) ---------------------------------------------------------
+
+
+@pytest.fixture
+def clock(monkeypatch):
+    """The queue's pause timer, by hand: (started ids, removed ids, fire())."""
+    started, removed, callbacks = [], [], {}
+
+    def add(_ms, fn):
+        started.append(10 + len(started))
+        callbacks[started[-1]] = fn
+        return started[-1]
+
+    monkeypatch.setattr(GLib, "timeout_add", add)
+    monkeypatch.setattr(GLib, "source_remove", removed.append)
+    return started, removed, lambda: callbacks[started[-1]]()
+
+
+def written_in_order(view):
+    """The keys each write added, in order (from the undo history and the file)."""
+    texts = [*view.session.history, view.session.text]
+    return [
+        next(line for line in b.splitlines() if line not in a.splitlines())
+        for a, b in zip(texts, texts[1:], strict=False)
+    ]
+
+
+def test_spin_edits_of_several_rows_share_one_pause_and_apply_in_order(make, clock):
+    started, removed, fire = clock
+    view, path = make()
+    row(view, DEPTH).editor.widget.set_value(120)
+    row(view, THICKNESS).editor.widget.set_value(17)
+    assert started == [10, 11] and removed == [10]  # one timer, started again by each edit
+    assert "depth" not in path.read_text()
+    fire()  # the pause is over
+    assert written_in_order(view) == ["depth = 120", "theme.thickness = 17"]
+    assert len(view.queue) == 0 and not view._queue_timer
+
+
+def test_an_edit_applied_at_once_comes_after_the_queued_ones(make, clock):
+    view, path = make()
+    row(view, DEPTH).editor.widget.set_value(120)
+    view._on_change(SHELL, "both")  # a combo or a checkbox: applied now
+    assert written_in_order(view) == ["depth = 120", 'shell = "both"']
+
+
+def test_a_spin_changed_back_within_the_pause_writes_nothing(make, clock):
+    view, path = make()
+    spin = row(view, DEPTH).editor.widget
+    spin.set_value(90)
+    spin.set_value(64)  # back to the widget default it showed
+    view.flush()
+    assert path.read_text() == USER and not view.session.history
+
+
+def test_a_rebuild_applies_the_queued_edits_first_and_runs_once(make, clock):
+    view, path = make()
+    rebuilds = _count_rebuilds(view)
+    row(view, DEPTH).editor.widget.set_value(120)
+    view.rebuild()  # e.g. Detect monitors
+    assert "depth = 120" in path.read_text() and len(view.queue) == 0
+    assert row(view, DEPTH).editor.widget.get_value() == 120
+    assert len(rebuilds) == 2  # the call, and the one it runs after the queue
+
+
+def test_a_hand_edit_met_while_applying_names_every_dropped_edit(make, clock):
+    view, path = make()
+    row(view, DEPTH).editor.widget.set_value(120)
+    row(view, THICKNESS).editor.widget.set_value(17)
+    hand = USER.replace('shell = "edge"', 'shell = "both"')
+    path.write_text(hand)
+    view.flush()
+    assert path.read_text() == hand
+    text = view.banner_label.get_text()
+    assert "changed outside" in text and "Not applied" in text
+    assert "monitors.HDMI-A-1.panels[0].depth = 120" in text
+    assert "monitors.HDMI-A-1.theme.thickness = 17" in text
+
+
+def test_typed_text_dropped_by_a_hand_edit_is_named(make):
+    view, path = make()
+    row(view, FONT).editor.widget.set_text("Typed Font")
+    path.write_text(USER.replace('shell = "edge"', 'shell = "both"'))
+    view.file_changed()
+    assert "theme.font (typed text)" in view.banner_label.get_text()
+
+
+def test_the_deferred_rebuild_applies_what_was_queued_meanwhile_once(make, clock):
+    view, path = make()
+    view._on_change((*P0, "name"), "Bottom dock")  # a title key: rebuilt when idle
+    rebuilds = _count_rebuilds(view)
+    row(view, DEPTH).editor.widget.set_value(120)  # queued before the loop is idle
+    drain()
+    assert "depth = 120" in path.read_text() and 'name = "Bottom dock"' in path.read_text()
+    assert len(rebuilds) == 1
+
+
+def test_revert_drops_the_queue_without_a_word(make, clock):
+    view, path = make()
+    view._on_change(SHELL, "both")
+    row(view, DEPTH).editor.widget.set_value(120)
+    view.revert()
+    assert path.read_text() == USER and len(view.queue) == 0
+    assert "Not applied" not in view.banner_label.get_text()
+
+
+def test_a_retired_view_starts_nothing_later(make, clock):
+    started, removed, _ = clock
+    view, path = make()
+    row(view, DEPTH).editor.widget.set_value(120)
+    view.retire()
+    assert removed == started and len(view.queue) == 0
```

- [ ] **Step 2: Run them to see them fail**

Run: `scripts/py -m pytest -q tests/test_settings_queue.py tests/test_settings_fields.py tests/test_settings_view.py tests/test_settings_controller.py`
Expected: `1 error` during collection (`ModuleNotFoundError: No module named 'settings.queue'`); without that file, the rewritten row tests fail (`FieldRow` takes no `on_queue`) and the new view tests fail (`SettingsView` has no `queue`).

- [ ] **Step 3: Implement:**

```diff
diff --git a/settings/controller.py b/settings/controller.py
index 753ac90..30d3bbf 100644
--- a/settings/controller.py
+++ b/settings/controller.py
@@ -149,9 +149,7 @@ class SettingsController(Gtk.Box):
     def _drop_view(self) -> None:
         view, self.view, self.session = self.view, None, None
         if view is not None:
-            view.cancel_deferred_rebuild()  # it would rebuild a view that is gone
-            for row in view.rows:
-                row.discard()
+            view.retire()  # no queue timer or idle rebuild may run on a view that is gone
             self.body.remove(view)
             # destroyed when idle: an action can run inside a signal of a widget of this view
             GLib.idle_add(lambda: view.destroy() or GLib.SOURCE_REMOVE)
diff --git a/settings/fields.py b/settings/fields.py
index 4a3ebf2..2c1c5c7 100644
--- a/settings/fields.py
+++ b/settings/fields.py
@@ -10,7 +10,7 @@ import gi
 
 gi.require_version("Gtk", "3.0")
 gi.require_version("Gdk", "3.0")
-from gi.repository import Gdk, GLib, GObject, Gtk  # noqa: E402
+from gi.repository import Gdk, GObject, Gtk  # noqa: E402
 
 from settings.form import (  # noqa: E402
     LENGTH_MODES,
@@ -327,9 +327,14 @@ def make_editor(spec: FieldSpec, emit: Emit) -> _Editor:
 class FieldRow(Gtk.Box):
     """Label, editor, where the value comes from, a reset button and an error line.
 
-    `on_change(path, value)` runs when the user edits the value (spin buttons: after a
-    DEBOUNCE_MS pause); `on_reset(path)` when the reset button is pressed. Values shown with
-    show_value never call back."""
+    `on_change(path, value)` runs when the user edits the value; `on_reset(path)` when the reset
+    button is pressed. A spin button's edits (DEBOUNCED kinds) go to `on_queue(path, value,
+    base)` instead, `base` being the value the row showed (the view's EditQueue applies them
+    after the pause: settings.queue); without `on_queue` they go to on_change at once. The row
+    holds no timer and no pending value of its own: only text typed and not yet sent (a font
+    list, a name, a number without Enter), which flush() sends. `is_pending(path)` says whether
+    the view still has an edit of this row queued (a refresh then keeps the editor as it is).
+    Values shown with show_value never call back."""
 
     def __init__(
         self,
@@ -337,14 +342,16 @@ class FieldRow(Gtk.Box):
         path: tuple,
         on_change: Callable[[tuple, Any], None],
         on_reset: Callable[[tuple], None],
+        on_queue: Callable[[tuple, Any, Any], None] | None = None,
+        is_pending: Callable[[tuple], bool] | None = None,
     ):
         super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
         self.spec, self.path = spec, path
         self._on_change = on_change
+        self._on_queue = on_queue
+        self._is_pending = is_pending or (lambda _path: False)
         self._updating = False
-        self._timer = 0
         self._discarding = False  # retired by a rebuild: nothing it holds may be written
-        self._pending: Any = None
         self._shown: Any = _UNSHOWN  # the value last shown or written: a no-op is not written
         self.editor = make_editor(spec, self._changed)
         line = Gtk.Box(spacing=8)
@@ -364,20 +371,18 @@ class FieldRow(Gtk.Box):
         self.error.set_no_show_all(True)
         self.pack_start(line, False, False, 0)
         self.pack_start(self.error, False, False, 0)
-        self.connect("destroy", lambda *_a: self._cancel())  # a stale timer must not write
 
     def show_value(self, value: FieldValue, keep_pending: bool = False) -> None:
         """Show `value` and clear the error. With `keep_pending` (refreshing every row after
-        another row's apply) the error stays, and a row holding an edit that is not applied yet
-        (a debounced spin value, typed text) only updates its source and reset, so that the
+        another row's apply) the error stays, and a row with an edit that is not applied yet
+        (queued in the view, or typed text) only updates its source and reset, so that the
         refresh never drops it."""
         self._shown = value.value
         if not keep_pending:
             self.show_error(None)
-        if keep_pending and (self._timer or self.editor.dirty()):
+        if keep_pending and (self._is_pending(self.path) or self.editor.dirty()):
             self._show_note(value)
             return
-        self._cancel()
         self._updating = True
         try:
             if isinstance(self.editor, LengthEditor):
@@ -398,47 +403,31 @@ class FieldRow(Gtk.Box):
         self.error.set_visible(bool(message))
 
     def flush(self) -> None:
-        """Send what the user changed but has not been applied yet: a debounced spin value
-        or a typed font list (the window is closing)."""
-        self.editor.commit()  # before the timer check: update() re-arms it through _changed
-        if self._timer:
-            self._cancel()
-            self._write(self._pending)
+        """Send text typed and not sent yet (a font list or a name without Enter, a number
+        without Enter): the view applies it with the queue (the window is closing, the pages
+        are about to be rebuilt)."""
+        self.editor.commit()
+
+    def unsent(self) -> bool:
+        """True while the editor holds typed text that was not sent."""
+        return self.editor.dirty()
 
     def _changed(self, value: Any) -> None:
         if self._updating or self._discarding:
             return
-        if self.spec.kind not in DEBOUNCED:
-            self._write(value)
+        if self.spec.kind in DEBOUNCED and self._on_queue is not None:
+            self._on_queue(self.path, value, self._shown)  # the queue un-queues a change back
             return
-        self._cancel()
-        self._pending = value
-        self._timer = GLib.timeout_add(DEBOUNCE_MS, self._flush)
-
-    def _flush(self) -> bool:
-        self._timer = 0
-        self._write(self._pending)
-        return GLib.SOURCE_REMOVE
+        self._write(value)
 
     def _write(self, value: Any) -> None:
-        if self._discarding:
-            return
         if _same(value, self._shown):
             return  # a no-op must not turn an inherited value into an explicit one
         self._shown = value
         self._on_change(self.path, value)
 
-    def cancel_pending(self) -> None:
-        """Drop a debounced value without writing it (the row is about to be discarded)."""
-        self._cancel()
-
     def discard(self) -> None:
-        """The row is retired (a rebuild or a hand-edit reload): drop what it holds and never
-        call back again, also for the focus-out GTK sends when its entry is unparented."""
+        """The row is retired (a rebuild or a hand-edit reload): never call back again, also
+        for the focus-out GTK sends when its entry is unparented. Its queued edits stay in the
+        view's queue (they are not the row's)."""
         self._discarding = True
-        self._cancel()
-
-    def _cancel(self) -> None:
-        if self._timer:
-            GLib.source_remove(self._timer)
-            self._timer = 0
diff --git a/settings/queue.py b/settings/queue.py
new file mode 100644
index 0000000..c3ebd82
--- /dev/null
+++ b/settings/queue.py
@@ -0,0 +1,91 @@
+"""The settings window's edit queue (Phil, 2026-10-15: "Maybe make a queue to ensure nothing
+gets lost"). Pure: no GTK.
+
+Every value edit of a row (a set, or a reset) is pushed here with its key path and applied by
+the view in arrival order. Spin buttons push on every step and the view applies the queue once
+the user pauses (one shared timer, settings.view); every other edit is applied at once, after
+what is queued before it. Per path the last edit wins: a new edit of a queued path replaces it
+and moves to the end (the order of the latest edits is kept), and an edit back to the value the
+row showed before (its `base`) takes the path out of the queue, so a value changed and changed
+back is never written (an inherited value stays inherited).
+
+Structural edits (a panel added, removed, moved), Undo, Redo, Save, leaving the config and
+Detect monitors are barriers: the view applies the whole queue first. A rebuild of the pages
+never touches the queue (queued edits are not held by the rows). A hand edit met while edits
+are queued drops them and the view names them on screen (`describe`): they were made for the
+file as it was, and panel entries are tracked by index, so the same path may mean another panel
+in the re-read file. Revert all drops them silently: it puts everything back anyway."""
+
+from __future__ import annotations
+
+from dataclasses import dataclass
+from typing import Any
+
+RESET = object()  # the edit "remove this key" (the row's reset button)
+_NO_BASE = object()
+
+
+def _same(a: Any, b: Any) -> bool:
+    return type(a) is type(b) and a == b
+
+
+@dataclass(frozen=True)
+class QueuedEdit:
+    path: tuple
+    value: Any  # the new value, or RESET
+    base: Any = _NO_BASE  # what the row showed before its first queued edit
+
+
+class EditQueue:
+    def __init__(self) -> None:
+        self._items: dict[tuple, QueuedEdit] = {}  # insertion order = apply order
+
+    def push(self, path: tuple, value: Any, base: Any = _NO_BASE) -> None:
+        """Queue `value` (or RESET) for `path`. `base`: the value shown before the edit (a
+        spin button's): an edit back to it un-queues the path."""
+        old = self._items.pop(path, None)
+        if old is not None:
+            base = old.base
+        if base is not _NO_BASE and _same(value, base):
+            return
+        self._items[path] = QueuedEdit(path, value, base)
+
+    def pop(self) -> QueuedEdit | None:
+        """The oldest edit, removed; None when empty."""
+        if not self._items:
+            return None
+        path = next(iter(self._items))
+        return self._items.pop(path)
+
+    def drop(self) -> list[QueuedEdit]:
+        """Remove and return every queued edit."""
+        items = list(self._items.values())
+        self._items.clear()
+        return items
+
+    def pending(self, path: tuple) -> bool:
+        return path in self._items
+
+    def __len__(self) -> int:
+        return len(self._items)
+
+    def __iter__(self):
+        return iter(list(self._items.values()))
+
+
+def path_text(path: tuple) -> str:
+    """("monitors", "HDMI-A-1", "panels", 0, "depth") -> "monitors.HDMI-A-1.panels[0].depth"."""
+    text = ""
+    for key in path:
+        text += f"[{key}]" if isinstance(key, int) else (f".{key}" if text else str(key))
+    return text
+
+
+def describe(edits: list[QueuedEdit]) -> str:
+    """The dropped edits as one line: "theme.thickness = 17, monitors.X.panels[0].depth
+    (reset)"."""
+    parts = []
+    for edit in edits:
+        value = "(reset)" if edit.value is RESET else f"= {edit.value!r}"
+        parts.append(f"{path_text(edit.path)} {value}")
+    return ", ".join(parts)
diff --git a/settings/view.py b/settings/view.py
index 5ca39dd..93b1833 100644
--- a/settings/view.py
+++ b/settings/view.py
@@ -18,9 +18,10 @@ from gi.repository import GLib, Gtk
 
 from settings.dialogs import GtkDialogs
 from settings.document import UserDocument
-from settings.fields import FieldRow
+from settings.fields import DEBOUNCE_MS, FieldRow
 from settings.form import MODE_HINTS, SectionSpec, config_form, registry_widgets
 from settings.panels import PanelEditor
+from settings.queue import RESET, EditQueue, QueuedEdit, describe, path_text
 from settings.session import ChangedOutside, SettingsSession, check_text
 from settings.values import field_value, layout_preview, lookup, monitor_names, panel_ops
 from shell.config.models import ConfigError
@@ -61,6 +62,8 @@ class SettingsView(Gtk.Box):
         self._flushing = False  # while True a rebuild is only noted: flush() does it at the end
         self._rebuild_due = False
         self._rebuild_idle = 0  # the idle source of a deferred rebuild (0: none)
+        self.queue = EditQueue()  # every value edit, applied in order (settings.queue)
+        self._queue_timer = 0  # the one pause timer of the queued spin edits (0: none)
 
         bar = Gtk.Box(spacing=6, margin=6)
         self.undo_button = Gtk.Button(label="Undo")
@@ -104,7 +107,12 @@ class SettingsView(Gtk.Box):
 
     def rebuild(self) -> None:
         """Rebuild every page (after a panel was added, removed or moved, an undo, a revert
-        or a hand edit); keeps the visible page."""
+        or a hand edit); keeps the visible page. Edits still queued are applied first (the
+        new rows could not show them): this rebuild then runs once, at the end."""
+        if len(self.queue) and not self._flushing:
+            self._rebuild_due = True
+            self._run_queue()
+            return
         self.cancel_deferred_rebuild()  # overtaken by this one
         visible = self.stack.get_visible_child_name()
         window = self.get_toplevel()
@@ -112,7 +120,7 @@ class SettingsView(Gtk.Box):
         if focus is not None and focus.is_ancestor(self.stack):
             window.set_focus(None)  # not left on a removed widget: shortcuts then find no group
         for row in self.rows:
-            row.discard()  # pending or typed values go with the old rows, never written later
+            row.discard()  # typed text goes with the old rows (queued edits stay queued)
         retired = self.stack.get_children()
         for child in retired:
             self.stack.remove(child)
@@ -171,7 +179,14 @@ class SettingsView(Gtk.Box):
         """A box of FieldRows for `section` at key path `prefix`; sub-sections in frames."""
         box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
         for spec in section.fields:
-            row = FieldRow(spec, (*prefix, spec.key), self._on_change, self._on_reset)
+            row = FieldRow(
+                spec,
+                (*prefix, spec.key),
+                self._on_change,
+                self._on_reset,
+                self._on_queue,
+                self.queue.pending,
+            )
             self.rows.append(row)
             box.pack_start(row, False, False, 0)
         for sub in section.sections:
@@ -293,10 +308,10 @@ class SettingsView(Gtk.Box):
         return True
 
     def _rebuild_soon(self, defer: bool = False) -> None:
-        """Rebuild now, or at the end of the running flush(): a rebuild in the middle would
-        destroy the rows that still hold a pending value. `defer`: when the loop is idle, not
-        now (a name entry's focus-out runs this before the click that caused it is released:
-        a button unparented by the rebuild would lose that click)."""
+        """Rebuild now, or once the queue is applied (one rebuild for every edit that asks for
+        it). `defer`: when the loop is idle, not now (a name entry's focus-out runs this before
+        the click that caused it is released: a button unparented by the rebuild would lose
+        that click)."""
         if self._flushing:
             self._rebuild_due = True
         elif defer:
@@ -306,50 +321,108 @@ class SettingsView(Gtk.Box):
             self.rebuild()
 
     def _rebuild_idle_cb(self) -> bool:
+        """The deferred rebuild: what was queued meanwhile is applied first, then one rebuild."""
         self._rebuild_idle = 0
-        self.rebuild()
+        self._rebuild_due = True
+        self._run_queue()
         return False
 
+    # ---- the edit queue (settings.queue) -------------------------------------------------
     def _on_change(self, path: tuple, value: Any) -> None:
-        titled = len(path) == 5 and path[2] == "panels" and path[4] in TITLE_KEYS
-        if titled:  # the panel's expander title shows these: rebuild, keep that panel open
-            if self._flush_first():
-                return
-            self._expand[path[1]] = path[3]
-        if len(path) == 5 and path[2] == "panels":  # a panel's own key: maybe a compound edit
-            _, entry = lookup(self.session.user, path[:4])
-            edit = _panel_edit(path[:4], panel_ops(entry or {}, path[4], value))
-        else:
-            edit = lambda d: d.set(path, value)  # noqa: E731
-        if not self.apply(edit, self._row(path), structural=titled, defer=True):
-            self._expand.pop(path[1], None)
-
-    def _flush_first(self) -> bool:
-        """A titled change rebuilds the page, which drops the other rows' pending values: apply
-        them first (the rebuild they ask for waits for the idle loop, one rebuild in all).
-        True: a hand edit was met, the file was re-read, and this edit was typed for the old
-        file."""
-        if not self._flushing:
-            self.flush(defer=True)
-            return self.refused_outside
-        return False
+        """An edit of a row (or of the toolbar): applied now, after the edits queued before it."""
+        self.queue.push(path, value)
+        self._run_queue(defer=True)
 
     def _on_reset(self, path: tuple) -> None:
+        self.queue.push(path, RESET)
+        self._run_queue(defer=True)
+
+    def _on_queue(self, path: tuple, value: Any, base: Any) -> None:
+        """A spin button's edit: queued and applied with the rest once the user pauses for
+        DEBOUNCE_MS (one timer for every row, started again by each edit)."""
+        self.queue.push(path, value, base)
+        self._cancel_queue_timer()
+        if len(self.queue):
+            self._queue_timer = GLib.timeout_add(DEBOUNCE_MS, self._queue_due)
+
+    def _queue_due(self) -> bool:
+        self._queue_timer = 0
+        self._run_queue(defer=True)
+        return GLib.SOURCE_REMOVE
+
+    def _cancel_queue_timer(self) -> None:
+        if self._queue_timer:
+            GLib.source_remove(self._queue_timer)
+            self._queue_timer = 0
+
+    def _run_queue(self, defer: bool = False) -> None:
+        """Apply every queued edit in order. Inside a running flush() nothing more happens:
+        that flush applies the new edit in its turn. A rebuild an edit asks for (a title key)
+        waits until the queue is empty: once, `defer`red to the idle loop or not."""
+        if self._flushing:
+            return
+        self.save_failed = False
+        self.refused_outside = False
+        self._flushing = True
+        try:
+            self._drain()
+        finally:
+            self._flushing = False
+            if self._rebuild_due:
+                self._rebuild_due = False
+                self._rebuild_soon(defer)
+
+    def _drain(self) -> None:
+        """Apply the queue, oldest edit first. A hand edit met on the way (the file was
+        re-read) drops that edit and every later one, and says which on screen."""
+        self._cancel_queue_timer()
+        while (item := self.queue.pop()) is not None:
+            self._apply_queued(item)
+            if self.refused_outside:
+                self._tell_dropped([item, *self.queue.drop()], [])
+                break
+
+    def _apply_queued(self, item: QueuedEdit) -> None:
+        """One queued edit: a set or a reset; a panel's own key can be a compound edit
+        (settings.values.panel_ops); a key in a panel's title rebuilds the pages."""
+        path, value = item.path, item.value
         panel_key = len(path) == 5 and path[2] == "panels"
         titled = panel_key and path[4] in TITLE_KEYS  # the title and rows follow: rebuild
-        if panel_key and path[4] == "corner":
-            _, entry = lookup(self.session.user, path[:4])  # resetting a corner also drops an
-            # edge it cannot hold (panel_ops only turns None into an unset for the corner)
-            edit = _panel_edit(path[:4], panel_ops(entry or {}, path[4], None))
-        else:
+        if panel_key and (value is not RESET or path[4] == "corner"):
+            # resetting a corner also drops an edge it cannot hold (panel_ops turns None into
+            # an unset for the corner only)
+            _, entry = lookup(self.session.user, path[:4])
+            ops = panel_ops(entry or {}, path[4], None if value is RESET else value)
+            edit = _panel_edit(path[:4], ops)
+        elif value is RESET:
             edit = lambda d: d.unset(path)  # noqa: E731
+        else:
+            edit = lambda d: d.set(path, value)  # noqa: E731
         if titled:
-            if self._flush_first():
-                return
-            self._expand[path[1]] = path[3]
-        if not self.apply(edit, self._row(path), structural=titled, defer=True) and titled:
+            self._expand[path[1]] = path[3]  # keep that panel open
+        if not self.apply(edit, self._row(path), structural=titled):
             self._expand.pop(path[1], None)
 
+    def _tell_dropped(self, dropped: list[QueuedEdit], typed: list[tuple]) -> None:
+        """Add to the banner what was not applied because the file changed outside this
+        window (never lost silently): the queued edits and the rows with typed text."""
+        parts = [describe(dropped)] if dropped else []
+        parts += [f"{path_text(path)} (typed text)" for path in typed]
+        if parts:
+            text = self.banner_label.get_text()
+            note = "Not applied (made for the file before it changed): " + ", ".join(parts)
+            self.show_banner(f"{text}\n{note}" if text else note, Gtk.MessageType.WARNING)
+
+    def retire(self) -> None:
+        """The view is going (File > Close, Open, New): no timer or idle rebuild may run on
+        it later. Its queue was applied by the leave question's flush; anything left is
+        dropped."""
+        self.cancel_deferred_rebuild()
+        self._cancel_queue_timer()
+        self.queue.drop()
+        for row in self.rows:
+            row.discard()
+
     def _structural(self, monitor: str, edit: Edit, expand: int | None) -> None:
         """A panel added, removed or moved: row indexes change, so rebuild (never refresh
         rows that may point at an entry that is gone). `expand`: the entry to show open."""
@@ -408,30 +481,31 @@ class SettingsView(Gtk.Box):
         return True
 
     def revert(self) -> None:
-        # no flush: a pending value is about to be reverted, and applying it first would
-        # re-read a hand edit and hide the "changed outside" warning
+        # no flush: queued values are about to be reverted (dropped without a word), and
+        # applying them first would re-read a hand edit and hide the "changed outside" warning
+        self._cancel_queue_timer()
+        self.queue.drop()
         if self._file_action(lambda: self.session.revert() or True):
             self.hide_banner()
             self.rebuild()
 
     def flush(self, defer: bool = False) -> None:
-        """Apply what is typed or pending in any row (a spin button inside its 400 ms pause,
-        a font list without Enter): the window is closing, or the rows are about to be rebuilt
-        (a panel added, removed or moved, Undo). Rows keep their pending
-        edit through the refresh after each apply, so every row is applied in turn; a rebuild an
-        apply asks for waits until the last row was applied (once, at the end). Not for Revert
-        all or a hand edit: their pending values are discarded with the rows. `save_failed` says
-        whether any of them could not be written (the error is on screen); `refused_outside` that
-        a hand edit was met: the rows from that one on were dropped (a rebuild follows).
-        `defer`: the rebuild at the end waits for the idle loop (see _rebuild_soon)."""
+        """The barrier before anything that must see every edit (a panel added, removed or
+        moved, Undo, Redo, Save, leaving the config): each row sends its typed text (a font
+        list or a name without Enter, a number without Enter) into the queue, then the whole
+        queue is applied in order (a spin edit inside its pause included). A rebuild an edit
+        asks for waits until the end (once). Not for Revert all or a hand edit: they drop the
+        queue. `save_failed` says whether an edit could not be written (the error is on
+        screen); `refused_outside` that a hand edit was met: that edit and the later ones were
+        dropped and named on screen (a rebuild follows). `defer`: the rebuild at the end waits
+        for the idle loop (see _rebuild_soon)."""
         self.save_failed = False
         self.refused_outside = False
         self._flushing = True
         try:
             for row in list(self.rows):
-                row.flush()
-                if self.refused_outside:
-                    break  # the rest would be applied onto the re-read file
+                row.flush()  # typed text -> the queue (applied below, in its turn)
+            self._drain()
         finally:
             self._flushing = False
             if self._rebuild_due:
@@ -464,17 +538,21 @@ class SettingsView(Gtk.Box):
         try:
             if not self.session.changed_outside():
                 return
-            self.session.rebase()  # pending values go with the rows: they were typed against
-            # the old file
+            self.session.rebase()
         except ConfigError as exc:
             self.show_banner(f"Cannot read the config: {exc}")
             return
+        # queued edits and typed text were made for the old file: dropped, and named below
+        self._cancel_queue_timer()
+        dropped = self.queue.drop()
+        typed = [row.path for row in self.rows if row.unsent()]
         self.rebuild()
         if self.session.config is not None:
             self.show_banner(
                 f"{self.session.path} was changed outside this window; showing the new values",
                 Gtk.MessageType.INFO,
             )
+        self._tell_dropped(dropped, typed)
 
 
 def _destroy_all(widgets: list[Gtk.Widget]) -> bool:
```

- [ ] **Step 4: Run them to see them pass**

Run: `scripts/py -m pytest -q tests/test_settings_queue.py tests/test_settings_fields.py tests/test_settings_view.py tests/test_settings_controller.py tests/test_settings_app.py`
Expected: all pass.

- [ ] **Step 5: VERIFY**

Run: `scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q`
Expected: `All checks passed!`, `2445 passed`.

**Reviewer mutations** (the queue: order, coalescing, barrier, hand edit, rebuild; the first five were run on the prototype and each failed tests):
- order: `EditQueue.pop` takes the newest (`next(reversed(...))`) → 3 failed (`test_edits_come_out_in_arrival_order`, `test_spin_edits_of_several_rows_share_one_pause_and_apply_in_order`, ...);
- coalescing: `push` keeps the old position (`self._items.get(path)` instead of `pop`) → 3 failed (`test_a_new_edit_of_a_queued_path_replaces_it_and_moves_to_the_end`, ...);
- barrier: `_structural` without its `flush()` (Task 8's code; at this task: `undo` without `flush()`) → `test_a_pending_value_is_written_before_a_panel_moves`, `test_a_pending_value_is_written_before_undo_and_revert` fail;
- hand edit: `_drain` going on after a refusal (`continue` instead of dropping and naming) → 2 failed (`test_a_flush_that_met_a_hand_edit_applies_no_further_row`, `test_a_hand_edit_met_while_applying_names_every_dropped_edit`); `file_changed` not dropping the queue → 3 failed;
- loss on rebuild: `rebuild` not applying the queue first → `test_a_rebuild_applies_the_queued_edits_first_and_runs_once` fails;
- `push` without the `base` check → `test_an_edit_back_to_the_shown_value_takes_the_path_out`, `test_a_spin_changed_back_within_the_pause_writes_nothing`;
- `_on_queue` without `_cancel_queue_timer()` (a timer per edit) → `test_spin_edits_of_several_rows_share_one_pause_and_apply_in_order` (`removed == [10]`);
- `FieldRow._changed` calling `on_change` for spin rows that have `on_queue` → `test_int_row_takes_its_bounds_from_the_schema_and_queues_its_edits`;
- `show_value` ignoring `is_pending` → `test_a_refresh_keeps_a_queued_edit_and_typed_text`, `test_another_rows_apply_keeps_a_pending_spin_value`;
- `_rebuild_idle_cb` not setting `_rebuild_due` → `test_the_deferred_rebuild_applies_what_was_queued_meanwhile_once`;
- `revert` naming the dropped edits → `test_revert_drops_the_queue_without_a_word`; `retire` not cancelling the timer → `test_a_retired_view_starts_nothing_later`.
- Known equivalent mutant: `rebuild`'s `and not self._flushing` guard removed survives (no path calls `rebuild()` while the queue is being applied: `_rebuild_soon` defers it to the end); it stays as a guard against a lost rebuild if one ever does.

- [ ] **Step 6: Commit**

```bash
git add settings/queue.py settings/fields.py settings/view.py settings/controller.py tests/test_settings_queue.py tests/test_settings_fields.py tests/test_settings_view.py tests/test_settings_controller.py
git commit -m "feat(settings): one edit queue applies every edit in order" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 5: The page tree with panel buttons (`settings/tree.py`)

**Files:**
- Create: `settings/tree.py`
- Test: `tests/test_settings_tree.py` (new)

**Interfaces:**
- Consumes: `settings.pages.TreeEntry`.
- Produces: `MIN_WIDTH = 200`, `NO_MONITORS`, `PANEL_ACTIONS: tuple[tuple[str, str, str], ...]` (`("up", "go-up-symbolic", "Move this panel up")`, `("down", ...)`, `("remove", "list-remove-symbolic", "Remove this panel")`; the toolbar reuses it in Task 8), `TreeRow(Gtk.ListBoxRow)` (`page`, `parent_page`, `children`, `arrow`, `label`, `buttons: dict[str, Gtk.Button]`, `title`), `SettingsTree(on_select: Callable[[str], None], on_action: Callable[[str, str], None] | None = None)` with `detect_button`, `list` (`Gtk.ListBox`), `hint`, `collapsed: set[str]`, `show(entries)`, `rows() -> list[tuple[str, str]]`, `row_of(page) -> TreeRow | None`, `is_expanded(page) -> bool`, `selected() -> str | None`, `select(page) -> bool` (no callback).

- [ ] **Step 1: Write the failing test:**

```diff
diff --git a/tests/test_settings_tree.py b/tests/test_settings_tree.py
new file mode 100644
index 0000000..630ff24
--- /dev/null
+++ b/tests/test_settings_tree.py
@@ -0,0 +1,198 @@
+"""settings.tree: the left column's tree of pages (a plain widget; no window is created)."""
+
+import pytest
+
+gi = pytest.importorskip("gi")
+gi.require_version("Gtk", "3.0")
+gi.require_version("Gdk", "3.0")
+
+from gi.repository import Gdk, GLib, Gtk  # noqa: E402
+
+if not Gtk.init_check()[0]:
+    pytest.skip("no display", allow_module_level=True)
+
+from settings.pages import TreeEntry  # noqa: E402
+from settings.tree import MIN_WIDTH, NO_MONITORS, SettingsTree  # noqa: E402
+
+ENTRIES = (
+    TreeEntry("theme", "Theme"),
+    TreeEntry(
+        "monitor:HDMI-A-1",
+        "HDMI-A-1",
+        (TreeEntry("panel:HDMI-A-1:0", "Dock"), TreeEntry("panel:HDMI-A-1:1", "Clock")),
+    ),
+    TreeEntry("monitor:DP-1", "DP-1", (TreeEntry("panel:DP-1:0", "Bar"),)),
+    TreeEntry("monitor:DP-2", "DP-2 (not connected)"),
+)
+
+
+@pytest.fixture
+def tree():
+    picked, actions = [], []
+    t = SettingsTree(picked.append, lambda page, action: actions.append((page, action)))
+    t.picked, t.actions = picked, actions
+    t.show(ENTRIES)
+    yield t
+    t.destroy()
+
+
+def click(tree, page):
+    tree.list.select_row(tree.row_of(page))  # as a click (or Up/Down) does
+
+
+def press(tree, keyval):
+    event = Gdk.Event.new(Gdk.EventType.KEY_PRESS)
+    event.keyval = keyval
+    return tree.list.emit("key-press-event", event)
+
+
+def visible(tree):
+    return [r.page for r in tree._rows if r.get_visible()]
+
+
+def drain():
+    ctx = GLib.MainContext.default()
+    while ctx.iteration(False):
+        pass
+
+
+def test_the_rows_are_theme_monitors_and_their_panels(tree):
+    assert tree.rows() == [
+        ("theme", "Theme"),
+        ("monitor:HDMI-A-1", "HDMI-A-1"),
+        ("panel:HDMI-A-1:0", "Dock"),
+        ("panel:HDMI-A-1:1", "Clock"),
+        ("monitor:DP-1", "DP-1"),
+        ("panel:DP-1:0", "Bar"),
+        ("monitor:DP-2", "DP-2 (not connected)"),
+    ]
+    assert visible(tree) == [p for p, _t in tree.rows()]  # every monitor starts open
+    assert tree.is_expanded("monitor:HDMI-A-1") and not tree.is_expanded("monitor:DP-2")
+    assert tree.row_of("panel:DP-1:0").get_children()[0].get_margin_start() == 24  # indented
+    assert not tree.row_of("monitor:DP-2").arrow.get_visible()  # no panels: no arrow
+
+
+def test_it_is_at_least_200_px_wide(tree):
+    assert MIN_WIDTH == 200 and tree.get_size_request()[0] == 200
+
+
+def test_a_users_click_asks_for_the_page(tree):
+    click(tree, "panel:HDMI-A-1:1")
+    assert tree.picked == ["panel:HDMI-A-1:1"] and tree.selected() == "panel:HDMI-A-1:1"
+
+
+def test_select_by_the_program_does_not_call_back(tree):
+    assert tree.select("monitor:DP-1") and tree.selected() == "monitor:DP-1"
+    assert tree.picked == []
+    assert not tree.select("monitor:nope") and tree.selected() == "monitor:DP-1"
+
+
+def test_the_arrow_collapses_and_the_monitor_stays_collapsed_when_the_rows_change(tree):
+    tree.row_of("monitor:HDMI-A-1").arrow.clicked()
+    assert "panel:HDMI-A-1:0" not in visible(tree) and tree.collapsed == {"monitor:HDMI-A-1"}
+    more = (*ENTRIES, TreeEntry("monitor:HDMI-A-2", "HDMI-A-2 (not connected)"))
+    tree.show(more)  # another shape: the rows are made again
+    assert "panel:HDMI-A-1:0" not in visible(tree) and "panel:DP-1:0" in visible(tree)
+    tree.row_of("monitor:HDMI-A-1").arrow.clicked()
+    assert "panel:HDMI-A-1:0" in visible(tree) and tree.collapsed == set()
+
+
+def test_collapsing_hides_a_selected_panel_and_selects_its_monitor(tree):
+    click(tree, "panel:HDMI-A-1:1")
+    tree.row_of("monitor:HDMI-A-1").arrow.clicked()
+    assert tree.selected() == "monitor:HDMI-A-1" and tree.picked[-1] == "monitor:HDMI-A-1"
+
+
+def test_selecting_a_panel_opens_its_monitor(tree):
+    tree.row_of("monitor:DP-1").arrow.clicked()
+    assert tree.select("panel:DP-1:0")
+    assert tree.is_expanded("monitor:DP-1") and "panel:DP-1:0" in visible(tree)
+
+
+def test_the_selected_panel_row_shows_its_buttons(tree):
+    def shown(page):
+        return [a for a, b in tree.row_of(page).buttons.items() if b.get_visible()]
+
+    assert shown("panel:HDMI-A-1:0") == []
+    click(tree, "panel:HDMI-A-1:0")
+    assert shown("panel:HDMI-A-1:0") == ["up", "down", "remove"]
+    buttons = tree.row_of("panel:HDMI-A-1:0").buttons
+    assert not buttons["up"].get_sensitive() and buttons["down"].get_sensitive()  # the first
+    last = tree.row_of("panel:HDMI-A-1:1").buttons
+    assert last["up"].get_sensitive() and not last["down"].get_sensitive()
+    assert not any(b.get_focus_on_click() for b in buttons.values())
+    assert buttons["remove"].get_tooltip_text() == "Remove this panel"
+    click(tree, "panel:HDMI-A-1:1")
+    assert shown("panel:HDMI-A-1:0") == [] and shown("panel:HDMI-A-1:1") == [
+        "up",
+        "down",
+        "remove",
+    ]
+    tree.show_all()  # the window's show_all never shows the hidden buttons or rows
+    assert shown("panel:HDMI-A-1:0") == []
+
+
+def test_a_row_button_sends_its_action(tree):
+    click(tree, "panel:HDMI-A-1:1")
+    tree.row_of("panel:HDMI-A-1:1").buttons["up"].clicked()
+    tree.row_of("panel:HDMI-A-1:1").buttons["remove"].clicked()
+    assert tree.actions == [("panel:HDMI-A-1:1", "up"), ("panel:HDMI-A-1:1", "remove")]
+
+
+def test_left_and_right_collapse_expand_and_go_up(tree):
+    click(tree, "panel:HDMI-A-1:0")
+    assert press(tree, Gdk.KEY_Left) is True  # a panel: to its monitor
+    assert tree.selected() == "monitor:HDMI-A-1" and tree.picked[-1] == "monitor:HDMI-A-1"
+    press(tree, Gdk.KEY_Left)  # the monitor: collapse
+    assert not tree.is_expanded("monitor:HDMI-A-1")
+    press(tree, Gdk.KEY_plus)
+    assert tree.is_expanded("monitor:HDMI-A-1")
+    press(tree, Gdk.KEY_minus)
+    press(tree, Gdk.KEY_Right)
+    assert tree.is_expanded("monitor:HDMI-A-1")
+    assert press(tree, Gdk.KEY_Down) is False  # left to the list box
+
+
+def test_a_rename_only_changes_the_title_and_keeps_the_selection(tree):
+    click(tree, "panel:HDMI-A-1:0")
+    old = tree.row_of("panel:HDMI-A-1:0")
+    renamed = (
+        ENTRIES[0],
+        TreeEntry(
+            "monitor:HDMI-A-1",
+            "HDMI-A-1",
+            (
+                TreeEntry("panel:HDMI-A-1:0", "Bottom dock"),
+                TreeEntry("panel:HDMI-A-1:1", "Clock"),
+            ),
+        ),
+        *ENTRIES[2:],
+    )
+    tree.show(renamed)
+    assert tree.row_of("panel:HDMI-A-1:0") is old and old.title == "Bottom dock"
+    assert tree.selected() == "panel:HDMI-A-1:0" and tree.picked == ["panel:HDMI-A-1:0"]
+
+
+def test_new_rows_never_call_back_and_old_ones_go_when_idle(tree):
+    click(tree, "panel:HDMI-A-1:1")
+    old = tree.row_of("panel:HDMI-A-1:1")
+    gone = []
+    old.connect("destroy", lambda *_a: gone.append(1))
+    tree.show(ENTRIES[:2])  # DP-1 gone: the rows are made again (inside a button's signal)
+    assert tree.picked == ["panel:HDMI-A-1:1"] and gone == []
+    drain()
+    assert gone == [1]
+
+
+def test_with_only_the_theme_it_says_there_is_no_monitor(tree):
+    assert not tree.hint.get_visible()
+    tree.show(ENTRIES[:1])
+    assert tree.hint.get_visible() and tree.hint.get_text() == NO_MONITORS
+    tree.show(ENTRIES)
+    assert not tree.hint.get_visible()
+
+
+def test_the_detect_button_is_above_the_list(tree):
+    assert tree.get_children()[0] is tree.detect_button
+    assert tree.detect_button.get_label() == "Detect monitors"
+    assert tree.list.get_accessible().get_name() == "Settings pages"
```

- [ ] **Step 2: Run it to see it fail**

Run: `scripts/py -m pytest -q tests/test_settings_tree.py`
Expected: `1 error` during collection (`ModuleNotFoundError: No module named 'settings.tree'`).

- [ ] **Step 3: Implement:**

```diff
diff --git a/settings/tree.py b/settings/tree.py
new file mode 100644
index 0000000..97293b3
--- /dev/null
+++ b/settings/tree.py
@@ -0,0 +1,245 @@
+"""The settings window's left column (panel/widget spec 7): a Detect monitors button above a
+tree of Theme, one expandable row per monitor and, under it, its panels by name. Selecting a
+row asks for its page (`on_select(page)`); the view shows it. The selected panel row shows
+three small buttons at its right edge, Move up, Move down and Remove (`on_action(page,
+action)`; Phil, 2026-10-15: "on the tree to the right of the tree item label"); the toolbar has
+the same three.
+
+A Gtk.ListBox of rows, not a Gtk.TreeView: a tree view's cells cannot hold buttons (a clickable
+icon renderer needs the pointer position, which tests cannot give without a window), while
+real buttons in a list row are focusable, have tooltips and are clicked in tests. A monitor's
+panels are rows below it, indented, hidden while it is collapsed. Keyboard: Up/Down move (and
+select), Left collapses a monitor or goes from a panel to its monitor, Right (or +) expands,
+- collapses, Tab reaches the selected row's buttons. A plain Gtk.Box: tested without a window.
+
+The rows are set with show(entries) after every rebuild of the pages. When the pages are the
+same as before (a rename, a refresh), only the titles change, so the selection and the
+expansion stay as they are; otherwise the rows are made again and a monitor the user collapsed
+stays collapsed (by its page name)."""
+
+from __future__ import annotations
+
+from collections.abc import Callable
+
+import gi
+
+gi.require_version("Gtk", "3.0")
+gi.require_version("Gdk", "3.0")
+gi.require_version("Pango", "1.0")
+from gi.repository import Gdk, GLib, Gtk, Pango
+
+from settings.pages import TreeEntry
+
+MIN_WIDTH = 200
+NO_MONITORS = "No monitor found. Connect one and press Detect monitors."
+# (action, icon, tooltip) of the buttons of a selected panel row (and of the toolbar)
+PANEL_ACTIONS = (
+    ("up", "go-up-symbolic", "Move this panel up"),
+    ("down", "go-down-symbolic", "Move this panel down"),
+    ("remove", "list-remove-symbolic", "Remove this panel"),
+)
+_OPEN, _CLOSED = "pan-down-symbolic", "pan-end-symbolic"
+
+
+class TreeRow(Gtk.ListBoxRow):
+    """One row: Theme, a monitor (with an expander arrow when it has panels) or a panel."""
+
+    def __init__(self, page: str, title: str, parent: str | None, on_action, on_arrow):
+        super().__init__()
+        self.page, self.parent_page = page, parent
+        self.children: list[TreeRow] = []
+        box = Gtk.Box(spacing=4)
+        box.set_margin_start(24 if parent else 0)
+        self.arrow: Gtk.Button | None = None
+        if parent is None:
+            self.arrow = Gtk.Button.new_from_icon_name(_OPEN, Gtk.IconSize.MENU)
+            self.arrow.set_relief(Gtk.ReliefStyle.NONE)
+            self.arrow.set_focus_on_click(False)
+            self.arrow.set_tooltip_text("Show or hide its panels")
+            self.arrow.connect("clicked", lambda _b: on_arrow(self))
+            box.pack_start(self.arrow, False, False, 0)
+        self.label = Gtk.Label(label=title, xalign=0)
+        self.label.set_ellipsize(Pango.EllipsizeMode.END)  # a long name never widens the tree
+        box.pack_start(self.label, True, True, 0)
+        self.buttons: dict[str, Gtk.Button] = {}
+        if parent is not None:
+            for action, icon, tip in PANEL_ACTIONS:
+                button = Gtk.Button.new_from_icon_name(icon, Gtk.IconSize.MENU)
+                button.set_relief(Gtk.ReliefStyle.NONE)
+                button.set_tooltip_text(tip)
+                # a press must not move the focus: a name entry's focus-out would rebuild the
+                # pages under the click
+                button.set_focus_on_click(False)
+                button.connect("clicked", lambda _b, a=action: on_action(self.page, a))
+                box.pack_end(button, False, False, 0)
+                self.buttons[action] = button
+        self.add(box)
+        self.show_all()
+        for button in self.buttons.values():
+            button.set_no_show_all(True)
+            button.hide()  # shown on the selected row only
+        self.set_no_show_all(True)  # the tree decides (a collapsed monitor's panels)
+
+    @property
+    def title(self) -> str:
+        return self.label.get_text()
+
+
+class SettingsTree(Gtk.Box):
+    def __init__(
+        self,
+        on_select: Callable[[str], None],
+        on_action: Callable[[str, str], None] | None = None,
+    ):
+        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
+        self.set_size_request(MIN_WIDTH, -1)
+        self._on_select = on_select
+        self._on_action = on_action or (lambda _page, _action: None)
+        self._quiet = False  # rows or the selection set by the program: no callbacks
+        self._rows: list[TreeRow] = []  # parents before their children
+        self.collapsed: set[str] = set()  # monitor pages the user collapsed
+        self.detect_button = Gtk.Button(label="Detect monitors")
+        self.detect_button.set_tooltip_text(
+            "Look for connected monitors again (kscreen-doctor) and list them with the "
+            "monitors in your config"
+        )
+        self.list = Gtk.ListBox()
+        self.list.set_selection_mode(Gtk.SelectionMode.SINGLE)
+        self.list.get_accessible().set_name("Settings pages")
+        self.list.connect("row-selected", self._selected)
+        self.list.connect("key-press-event", self._key)
+        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
+        scroller.add(self.list)
+        self.hint = Gtk.Label(label=NO_MONITORS, xalign=0, wrap=True)
+        self.hint.get_style_context().add_class("dim-label")
+        self.hint.set_no_show_all(True)
+        self.pack_start(self.detect_button, False, False, 0)
+        self.pack_start(scroller, True, True, 0)
+        self.pack_start(self.hint, False, False, 0)
+
+    # ---- rows ------------------------------------------------------------------------------
+    def show(self, entries: tuple[TreeEntry, ...]) -> None:
+        """Show these rows (settings.pages.tree_entries)."""
+        shape = [p for e in entries for p in (e.page, *(c.page for c in e.children))]
+        self._quiet = True
+        try:
+            if shape == [r.page for r in self._rows]:
+                titles = {e.page: e.title for e in entries}
+                titles.update((c.page, c.title) for e in entries for c in e.children)
+                for row in self._rows:
+                    row.label.set_text(titles[row.page])
+            else:
+                self._fill(entries)
+        finally:
+            self._quiet = False
+        self.hint.set_visible(len(entries) < 2)  # Theme alone: no monitor to show
+
+    def _fill(self, entries: tuple[TreeEntry, ...]) -> None:
+        retired, self._rows = self._rows, []
+        for row in retired:
+            self.list.remove(row)
+        if retired:
+            # destroyed when the loop is idle: show() runs inside a row button's "clicked"
+            # (Remove, Move), which GTK finishes on that button afterwards
+            GLib.idle_add(_destroy_all, retired)
+        for entry in entries:
+            parent = self._add(entry.page, entry.title, None)
+            for i, child in enumerate(entry.children):
+                row = self._add(child.page, child.title, entry.page)
+                row.buttons["up"].set_sensitive(i > 0)
+                row.buttons["down"].set_sensitive(i < len(entry.children) - 1)
+                parent.children.append(row)
+            self._expand(parent, entry.page not in self.collapsed)
+
+    def _add(self, page: str, title: str, parent: str | None) -> TreeRow:
+        row = TreeRow(page, title, parent, self._on_action, self._toggle)
+        self.list.add(row)
+        row.show()
+        self._rows.append(row)
+        return row
+
+    def _expand(self, row: TreeRow, expanded: bool) -> None:
+        if row.arrow is not None:
+            row.arrow.set_visible(bool(row.children))
+            icon = _OPEN if expanded else _CLOSED
+            row.arrow.set_image(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.MENU))
+        for child in row.children:
+            child.set_visible(expanded)
+        if expanded:
+            self.collapsed.discard(row.page)
+        elif row.children:
+            self.collapsed.add(row.page)
+
+    def _toggle(self, row: TreeRow) -> None:
+        """The arrow of a monitor row (or Left/Right on it)."""
+        self._expand(row, row.page in self.collapsed)
+        selected = self.list.get_selected_row()
+        if selected is not None and not selected.get_visible():
+            self.select(row.page)  # the selected panel was hidden: its monitor
+            self._on_select(row.page)
+
+    def rows(self) -> list[tuple[str, str]]:
+        """(page, title) of every row, parents before their children (hidden ones too)."""
+        return [(r.page, r.title) for r in self._rows]
+
+    def row_of(self, page: str) -> TreeRow | None:
+        return next((r for r in self._rows if r.page == page), None)
+
+    def is_expanded(self, page: str) -> bool:
+        row = self.row_of(page)
+        return row is not None and bool(row.children) and page not in self.collapsed
+
+    # ---- selection -------------------------------------------------------------------------
+    def selected(self) -> str | None:
+        row = self.list.get_selected_row()
+        return None if row is None else row.page
+
+    def select(self, page: str) -> bool:
+        """Select the row of `page` (no callback); a panel's monitor is expanded to show it.
+        False when there is no such row."""
+        row = self.row_of(page)
+        if row is None:
+            return False
+        self._quiet = True
+        try:
+            if row.parent_page is not None:
+                self._expand(self.row_of(row.parent_page), True)
+            self.list.select_row(row)
+            self._show_buttons(row)
+        finally:
+            self._quiet = False
+        return True
+
+    def _selected(self, _list, row: TreeRow | None) -> None:
+        self._show_buttons(row)
+        if not self._quiet and row is not None:
+            self._on_select(row.page)
+
+    def _show_buttons(self, selected: TreeRow | None) -> None:
+        for row in self._rows:
+            for button in row.buttons.values():
+                button.set_visible(row is selected)
+
+    def _key(self, _list, event: Gdk.EventKey) -> bool:
+        row = self.list.get_selected_row()
+        if row is None:
+            return False
+        key = event.keyval
+        if key in (Gdk.KEY_Left, Gdk.KEY_minus, Gdk.KEY_KP_Subtract):
+            if row.parent_page is not None:  # a panel: to its monitor
+                self.select(row.parent_page)
+                self._on_select(row.parent_page)
+            elif row.page not in self.collapsed and row.children:
+                self._toggle(row)
+            return True
+        if key in (Gdk.KEY_Right, Gdk.KEY_plus, Gdk.KEY_KP_Add):
+            if row.children and row.page in self.collapsed:
+                self._toggle(row)
+            return True
+        return False
+
+
+def _destroy_all(rows: list[TreeRow]) -> bool:
+    for row in rows:
+        row.destroy()
+    return GLib.SOURCE_REMOVE
```

- [ ] **Step 4: Run it to see it pass**

Run: `scripts/py -m pytest -q tests/test_settings_tree.py`
Expected: `14 passed`.

- [ ] **Step 5: VERIFY**

Run: `scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q`
Expected: `All checks passed!`, `2459 passed`.

**Reviewer mutations:** `show` always calling `_fill` (rows remade on a rename: `test_a_rename_only_changes_the_title_and_keeps_the_selection` checks the row object); `_fill` ignoring `collapsed` (`test_the_arrow_collapses_and_the_monitor_stays_collapsed_when_the_rows_change`); `_show_buttons` showing every row's buttons (`test_the_selected_panel_row_shows_its_buttons`); no `set_no_show_all` on the buttons or rows (`tree.show_all()` in the same test); `_toggle` not selecting the monitor when its selected panel hides (`test_collapsing_hides_a_selected_panel_and_selects_its_monitor`); `_fill` destroying old rows at once (`test_new_rows_never_call_back_and_old_ones_go_when_idle`); `select` without `_quiet` (`test_select_by_the_program_does_not_call_back`); Left on a panel not calling back (`test_left_and_right_collapse_expand_and_go_up`); the first row's Move up sensitive (`test_the_selected_panel_row_shows_its_buttons`).

- [ ] **Step 6: Commit**

```bash
git add settings/tree.py tests/test_settings_tree.py
git commit -m "feat(settings): the page tree with panel buttons on the selected row" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 6: Tabbed Theme and monitor pages beside the tree

**Files:**
- Modify: `settings/view.py` (module docstring, imports, `__init__`: tree in a `Gtk.Paned` instead of the `Gtk.StackSidebar`; `rebuild` from `tree_entries`; `_page_to_show`, `show_page`, `_add_page`, `_tabbed`, `_add_tab`, `_keep_tab`, `_remember_tab`, `_theme_page`, `_preview`, `_monitor_page`, `override_text`; `previews` is `dict[str, list[Gtk.Label]]`)
- Test: `tests/test_settings_view.py` (one preview assertion; 8 new tests)

The monitor page keeps, until Task 7 and Task 8 take them over, a last **Panels** tab with the mode row and the old panel list (`PanelEditor`); the tree shows no panel rows yet (Task 8 adds them with the panel pages).

**Interfaces:**
- Consumes: Task 1 (`theme_tabs`, `TabSpec`), Task 2 (`THEME`, `fallback_page`, `monitor_page`, `parse_page`, `tree_entries`), Task 5 (`SettingsTree`), Task 4 (rows built with `on_queue`, `is_pending`).
- Produces: `SettingsView.tree: SettingsTree`, `SettingsView.show_page(page: str) -> None`, `SettingsView._tab_of: dict[str, str]`, `SettingsView._tabbed(page, top, tabs, prefix, extra=()) -> Gtk.Widget` (`extra` goes in Task 8), `SettingsView.previews: dict[str, list[Gtk.Label]]`, `override_text(name) -> str`.

- [ ] **Step 1: Write the failing tests:**

```diff
diff --git a/tests/test_settings_view.py b/tests/test_settings_view.py
index e14d306..c427621 100644
--- a/tests/test_settings_view.py
+++ b/tests/test_settings_view.py
@@ -213,7 +213,7 @@ def test_an_invalid_file_is_shown_read_only_with_its_error(make):
 
 def test_layout_warnings_are_previewed_for_connected_monitors(make):
     view, _ = make()
-    preview = view.previews["HDMI-A-1"]
+    (preview,) = view.previews["HDMI-A-1"]  # on the monitor page
     assert not preview.get_visible()
     view._on_change(("monitors", "HDMI-A-1", "panels", 0, "length"), 3000)
     assert preview.get_visible() and "monitors.HDMI-A-1" in preview.get_text()
@@ -947,3 +947,105 @@ def test_a_retired_view_starts_nothing_later(make, clock):
     row(view, DEPTH).editor.widget.set_value(120)
     view.retire()
     assert removed == started and len(view.queue) == 0
+
+
+# ---- the tree and the tabbed pages (panel/widget spec 7) -----------------------------------
+
+
+def notebook(view, page):
+    return next(w for w in walk(view.stack.get_child_by_name(page)) if isinstance(w, Gtk.Notebook))
+
+
+def tabs(view, page):
+    nb = notebook(view, page)
+    return [nb.get_tab_label_text(c) for c in nb.get_children()]
+
+
+def current_tab(view, page):
+    nb = notebook(view, page)
+    return nb.get_tab_label_text(nb.get_nth_page(nb.get_current_page()))
+
+
+def show_tab(view, page, title):
+    notebook(view, page).set_current_page(tabs(view, page).index(title))  # as a click does
+
+
+def texts(widget):
+    return [w.get_text() for w in walk(widget) if isinstance(w, Gtk.Label)]
+
+
+def click_row(view, page):
+    """Select a tree row as a click does."""
+    view.tree.list.select_row(view.tree.row_of(page))
+
+
+def test_the_tree_lists_the_theme_and_the_monitors_beside_the_pages(make):
+    view, _ = make()
+    assert [p for p, _t in view.tree.rows()][:2] == ["theme", "monitor:HDMI-A-1"]
+    assert ("monitor:DP-1", "DP-1") in view.tree.rows()
+    assert view.tree.selected() == "theme" == view.stack.get_visible_child_name()
+    paned = view.tree.get_parent()
+    assert isinstance(paned, Gtk.Paned) and paned.get_child2() is view.stack
+    assert view.tree.get_size_request()[0] >= 200
+
+
+def test_selecting_a_tree_row_shows_its_page(make):
+    view, _ = make()
+    click_row(view, "monitor:DP-1")
+    assert view.stack.get_visible_child_name() == "monitor:DP-1"
+
+
+def test_the_theme_page_has_its_tabs(make):
+    view, _ = make()
+    assert tabs(view, "theme") == ["General", "Borders", "Shadows", "Handle", "Layout"]
+    assert "Theme (every monitor)" in texts(view.stack.get_child_by_name("theme"))
+
+
+def test_a_monitor_page_has_the_theme_tabs_under_an_override_banner(make):
+    view, _ = make()
+    assert tabs(view, "monitor:HDMI-A-1")[:5] == tabs(view, "theme")
+    page = view.stack.get_child_by_name("monitor:HDMI-A-1")
+    assert any("These values override the Theme for HDMI-A-1" in t for t in texts(page))
+    accent = row(view, ("monitors", "HDMI-A-1", "theme", "accent"))
+    assert accent.source.get_text() == "global theme"  # not set here: the Theme's value
+    assert row(view, ("monitors", "HDMI-A-1", "layout", "gap")).source.get_text() == (
+        "px between neighbouring panels · global layout"
+    )
+
+
+def test_a_rebuild_keeps_the_page_and_its_tab(make):
+    view, _ = make()
+    click_row(view, "monitor:HDMI-A-1")
+    show_tab(view, "monitor:HDMI-A-1", "Borders")
+    view._on_change(("monitors", "HDMI-A-1", "theme", "border", "width"), 4)
+    view.rebuild()
+    assert view.stack.get_visible_child_name() == "monitor:HDMI-A-1"
+    assert view.tree.selected() == "monitor:HDMI-A-1"
+    assert current_tab(view, "monitor:HDMI-A-1") == "Borders"
+    assert current_tab(view, "theme") == "General"  # each page keeps its own
+
+
+def test_a_page_that_is_gone_after_a_hand_edit_falls_back_to_the_theme(make):
+    view, path = make(outputs=())
+    click_row(view, "monitor:HDMI-A-1")
+    path.write_text('[theme]\naccent = "#112233"\n')  # by hand: no monitor any more
+    view.file_changed()
+    assert pages(view) == ["theme"]
+    assert view.stack.get_visible_child_name() == "theme" == view.tree.selected()
+
+
+def test_an_invalid_file_shows_only_the_theme_in_the_tree(make):
+    view, path = make()
+    path.write_text('[monitors.HDMI-A-1]\nshell = "sideways"\n')
+    view.file_changed()
+    assert view.tree.rows() == [("theme", "Theme")]
+    assert not view.stack.get_child_by_name("theme").get_sensitive()
+
+
+def test_a_later_part_of_a_tab_has_its_own_heading(make):
+    view, _ = make()
+    nb = notebook(view, "theme")
+    handle = nb.get_nth_page(tabs(view, "theme").index("Handle"))
+    assert "Handle style" in texts(handle)
+    borders = nb.get_nth_page(tabs(view, "theme").index("Borders"))
+    assert "Border" not in texts(borders)  # one part: no heading
```

- [ ] **Step 2: Run them to see them fail**

Run: `scripts/py -m pytest -q tests/test_settings_view.py`
Expected: `9 failed` (no `tree`, no notebooks, `previews` holds a label, not a list).

- [ ] **Step 3: Implement** (`settings/view.py`):

```diff
diff --git a/settings/view.py b/settings/view.py
index 93b1833..7c4e24d 100644
--- a/settings/view.py
+++ b/settings/view.py
@@ -1,7 +1,15 @@
 """The settings window's content: a top bar (Undo, Revert all, the file path), a banner for
-errors and notices, and a page per topic (the global theme and layout, then one page per
-monitor: shell mode, panels, theme and layout overrides). A plain Gtk.Box, so it is tested
-without creating a window; settings.window puts it in the toplevel.
+errors and notices, and beside the tree (settings.tree: Theme, the monitors) the page the tree
+selects (panel/widget spec 7). The Theme page and each monitor page have tabs (General,
+Borders, Shadows, Handle, Layout: settings.form.theme_tabs); a monitor page's values override
+the Theme for that monitor, and it has a Panels tab with its shell mode and its panel list. A
+plain Gtk.Box, so it is tested without creating a window; settings.window puts it in the
+toplevel.
+
+Every page is built at each rebuild (as before: every row exists, so flush() and refresh()
+reach every row, on any page); the tree only chooses which one is shown, so switching pages
+never drops a pending value. A rebuild keeps the shown page (by its name, settings.pages) and
+each page's tab (by its title).
 
 Every edit goes through SettingsSession.apply: a valid one is written to the user config and
 the running shell reloads it; an invalid one is shown under its row and not written."""
@@ -9,6 +17,7 @@ the running shell reloads it; an invalid one is shown under its row and not writ
 from __future__ import annotations
 
 from collections.abc import Callable
+from dataclasses import replace
 from typing import Any
 
 import gi
@@ -19,11 +28,20 @@ from gi.repository import GLib, Gtk
 from settings.dialogs import GtkDialogs
 from settings.document import UserDocument
 from settings.fields import DEBOUNCE_MS, FieldRow
-from settings.form import MODE_HINTS, SectionSpec, config_form, registry_widgets
+from settings.form import (
+    MODE_HINTS,
+    SectionSpec,
+    TabSpec,
+    config_form,
+    registry_widgets,
+    theme_tabs,
+)
+from settings.pages import THEME, fallback_page, monitor_page, parse_page, tree_entries
 from settings.panels import PanelEditor
 from settings.queue import RESET, EditQueue, QueuedEdit, describe, path_text
 from settings.session import ChangedOutside, SettingsSession, check_text
-from settings.values import field_value, layout_preview, lookup, monitor_names, panel_ops
+from settings.tree import SettingsTree
+from settings.values import field_value, layout_preview, lookup, panel_ops
 from shell.config.models import ConfigError
 from shell.outputs import Output
 from shell.registry import requests_for
@@ -53,8 +71,10 @@ class SettingsView(Gtk.Box):
         self.outputs = {o.name: o for o in outputs}
         self.form = config_form(registry_widgets())
         self.rows: list[FieldRow] = []
-        self.previews: dict[str, Gtk.Label] = {}
+        # monitor -> the labels showing its layout warnings (its page; later its panels' pages)
+        self.previews: dict[str, list[Gtk.Label]] = {}
         self._expand: dict[str, int] = {}  # monitor -> panel entry to show open after a rebuild
+        self._tab_of: dict[str, str] = {}  # page -> the title of the tab last shown on it
         self.save_failed = False  # the last flush() could not write something (shown on screen)
         # the last flush() met a hand edit: that row and the rest were not applied (warning on
         # screen); the caller must not go on to a structural edit or an undo on the re-read file
@@ -84,10 +104,11 @@ class SettingsView(Gtk.Box):
         self.banner.get_content_area().add(self.banner_label)
         self.banner.set_no_show_all(True)
         self.stack = Gtk.Stack()
-        sidebar = Gtk.StackSidebar(stack=self.stack)
-        body = Gtk.Box()
-        body.pack_start(sidebar, False, False, 0)
-        body.pack_start(self.stack, True, True, 0)
+        self.tree = SettingsTree(self.show_page)
+        self.tree.set_property("margin", 6)
+        body = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
+        body.pack1(self.tree, False, False)  # never narrower than its MIN_WIDTH
+        body.pack2(self.stack, True, False)
         self.pack_start(bar, False, False, 0)
         self.pack_start(self.banner, False, False, 0)
         self.pack_start(body, True, True, 0)
@@ -132,14 +153,17 @@ class SettingsView(Gtk.Box):
             GLib.idle_add(_destroy_all, retired)
         self.rows, self.previews = [], {}
         valid = self.session.config is not None
-        self._page("theme", "Theme", self._theme_page(), valid)
-        if valid:
-            for name, connected in monitor_names(self.config, list(self.outputs.values())):
-                title = name if connected else f"{name} (not connected)"
-                self._page(f"monitor:{name}", title, self._monitor_page(name), True)
+        entries = tree_entries(self.session.config, list(self.outputs.values()))
+        self._add_page(THEME, self._theme_page(), valid)
+        for entry in entries[1:]:
+            name = parse_page(entry.page).monitor
+            self._add_page(entry.page, self._monitor_page(name, entry.title), True)
         self.stack.show_all()
-        if visible and self.stack.get_child_by_name(visible) is not None:
-            self.stack.set_visible_child_name(visible)
+        page = self._page_to_show(visible)
+        self.stack.set_visible_child_name(page)
+        # the panel rows come with the panel pages
+        self.tree.show(tuple(replace(e, children=()) for e in entries))
+        self.tree.select(page)
         if valid:
             self.refresh()
         else:
@@ -165,15 +189,73 @@ class SettingsView(Gtk.Box):
         if not self._undo_by_action:
             self.undo_button.set_sensitive(bool(self.session.history))
 
-    def _page(self, name: str, title: str, content: Gtk.Widget, sensitive: bool) -> None:
+    def _page_to_show(self, wanted: str | None) -> str:
+        """`wanted` if it is still a page; else its fallback (a gone panel's monitor), else the
+        Theme page."""
+        for page in (wanted, wanted and fallback_page(wanted)):
+            if page and self.stack.get_child_by_name(page) is not None:
+                return page
+        return THEME
+
+    def show_page(self, page: str) -> None:
+        """Show `page` (the tree's selection)."""
+        if self.stack.get_child_by_name(page) is not None:
+            self.stack.set_visible_child_name(page)
+
+    def _add_page(self, name: str, content: Gtk.Widget, sensitive: bool) -> None:
+        content.set_sensitive(sensitive)
+        self.stack.add_named(content, name)
+
+    def _tabbed(
+        self,
+        page: str,
+        top: list[Gtk.Widget],
+        tabs: tuple[TabSpec, ...],
+        prefix: tuple,
+        extra: tuple[tuple[str, Gtk.Widget], ...] = (),
+    ) -> Gtk.Widget:
+        """A page: `top` (its heading, a banner) above a notebook with one tab per TabSpec
+        (then the `extra` tabs, (title, content)), each tab scrolled on its own. A tab's later
+        parts get a heading of their own (the Handle tab: the handle colours, then "Handle
+        style"). The tab last shown on `page` is shown again."""
+        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
+        box.set_margin_start(16)
+        box.set_margin_end(16)
+        box.set_margin_top(12)
+        box.set_margin_bottom(12)
+        for widget in top:
+            box.pack_start(widget, False, False, 0)
+        notebook = Gtk.Notebook(scrollable=True)
+        for tab in tabs:
+            content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
+            content.set_property("margin", 12)
+            for i, (key, section) in enumerate(tab.parts):
+                if i > 0:
+                    content.pack_start(self._heading(section.label), False, False, 6)
+                content.pack_start(self.section_rows(section, (*prefix, *key)), False, False, 0)
+            self._add_tab(notebook, tab.title, content)
+        for title, content in extra:
+            self._add_tab(notebook, title, content)
+        box.pack_start(notebook, True, True, 0)
+        self._keep_tab(page, notebook)
+        return box
+
+    @staticmethod
+    def _add_tab(notebook: Gtk.Notebook, title: str, content: Gtk.Widget) -> None:
         scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
-        content.set_margin_start(16)
-        content.set_margin_end(16)
-        content.set_margin_top(12)
-        content.set_margin_bottom(12)
         scroller.add(content)
-        scroller.set_sensitive(sensitive)
-        self.stack.add_titled(scroller, name, title)
+        scroller.show_all()  # a notebook only switches to a visible page (_keep_tab)
+        notebook.append_page(scroller, Gtk.Label(label=title))
+
+    def _keep_tab(self, page: str, notebook: Gtk.Notebook) -> None:
+        """Show the tab last shown on `page` (by its title) and remember the user's choice."""
+        titles = [notebook.get_tab_label_text(c) for c in notebook.get_children()]
+        if self._tab_of.get(page) in titles:
+            notebook.set_current_page(titles.index(self._tab_of[page]))
+        notebook.connect("switch-page", self._remember_tab, page)
+
+    def _remember_tab(self, notebook: Gtk.Notebook, child: Gtk.Widget, _num, page: str) -> None:
+        self._tab_of[page] = notebook.get_tab_label_text(child)
 
     def section_rows(self, section: SectionSpec, prefix: tuple) -> Gtk.Widget:
         """A box of FieldRows for `section` at key path `prefix`; sub-sections in frames."""
@@ -206,22 +288,33 @@ class SettingsView(Gtk.Box):
         return label
 
     def _theme_page(self) -> Gtk.Widget:
-        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
-        box.pack_start(self._heading("Theme (every monitor)"), False, False, 0)
-        box.pack_start(self.section_rows(self.form.theme, ("theme",)), False, False, 0)
-        box.pack_start(self._heading("Layout"), False, False, 0)
-        box.pack_start(self.section_rows(self.form.layout, ("layout",)), False, False, 0)
-        return box
+        heading = self._heading("Theme (every monitor)")
+        return self._tabbed(THEME, [heading], theme_tabs(self.form), ())
+
+    def _preview(self, name: str) -> Gtk.Label:
+        """A label for `name`'s layout warnings (shown by refresh when there are any)."""
+        preview = Gtk.Label(xalign=0, wrap=True, selectable=True)
+        preview.get_style_context().add_class("warning")
+        preview.set_no_show_all(True)
+        self.previews.setdefault(name, []).append(preview)
+        return preview
 
-    def _monitor_page(self, name: str) -> Gtk.Widget:
+    def _monitor_page(self, name: str, title: str) -> Gtk.Widget:
+        """A monitor's page: the same tabs as the Theme page at [monitors.NAME], under a banner
+        saying that they override the Theme; a row that is not set shows the Theme's value
+        ("global theme")."""
         prefix = ("monitors", name)
-        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
-        box.pack_start(self.section_rows(self.form.monitor, prefix), False, False, 0)
+        banner = Gtk.InfoBar(message_type=Gtk.MessageType.INFO)
+        banner.get_content_area().add(Gtk.Label(label=override_text(name), xalign=0, wrap=True))
+        top = [self._heading(title), banner, self._preview(name)]
+        # until the toolbar and the panel pages take them over: the mode and the panel list
+        panels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
+        panels.set_property("margin", 12)
+        panels.pack_start(self.section_rows(self.form.monitor, prefix), False, False, 0)
         hints = "\n".join(f"{mode}: {hint}" for mode, hint in MODE_HINTS.items())
         note = Gtk.Label(label=hints, xalign=0, wrap=True)
         note.get_style_context().add_class("dim-label")
-        box.pack_start(note, False, False, 0)
-        box.pack_start(self._heading("Panels"), False, False, 0)
+        panels.pack_start(note, False, False, 0)
         editor = PanelEditor(
             self.form,
             name,
@@ -230,20 +323,9 @@ class SettingsView(Gtk.Box):
             lambda edit, expand, n=name: self._structural(n, edit, expand),
             self._expand.pop(name, None),
         )
-        box.pack_start(editor, False, False, 0)
-        preview = Gtk.Label(xalign=0, wrap=True, selectable=True)
-        preview.get_style_context().add_class("warning")
-        preview.set_no_show_all(True)
-        self.previews[name] = preview
-        box.pack_start(preview, False, False, 0)
-        for key, title, section in (
-            ("theme", "Theme override (this monitor only)", self.form.theme),
-            ("layout", "Layout override (this monitor only)", self.form.layout),
-        ):
-            expander = Gtk.Expander(label=title)
-            expander.add(self.section_rows(section, (*prefix, key)))
-            box.pack_start(expander, False, False, 0)
-        return box
+        panels.pack_start(editor, False, False, 0)
+        tabs = theme_tabs(self.form)
+        return self._tabbed(monitor_page(name), top, tabs, prefix, (("Panels", panels),))
 
     # ---- showing values ------------------------------------------------------------------
     def refresh(self) -> None:
@@ -254,11 +336,12 @@ class SettingsView(Gtk.Box):
         config, user = self.config, self.session.user
         for row in self.rows:
             row.show_value(field_value(config, user, row.path), keep_pending=True)
-        for name, label in self.previews.items():
+        for name, labels in self.previews.items():
             out = self.outputs.get(name)
             warnings = layout_preview(config, name, out.width, out.height) if out else []
-            label.set_text("\n".join(warnings))
-            label.set_visible(bool(warnings))
+            for label in labels:
+                label.set_text("\n".join(warnings))
+                label.set_visible(bool(warnings))
         self._sync_undo_button()
         self._on_state()
 
@@ -555,6 +638,14 @@ class SettingsView(Gtk.Box):
         self._tell_dropped(dropped, typed)
 
 
+def override_text(name: str) -> str:
+    """The banner of a monitor's page."""
+    return (
+        f"These values override the Theme for {name}. A row you have not set here shows the "
+        "Theme's value."
+    )
+
+
 def _destroy_all(widgets: list[Gtk.Widget]) -> bool:
     for widget in widgets:
         widget.destroy()
```

- [ ] **Step 4: Run them to see them pass**

Run: `scripts/py -m pytest -q tests/test_settings_view.py tests/test_settings_controller.py tests/test_settings_app.py tests/test_settings_dialogs.py`
Expected: all pass.

- [ ] **Step 5: VERIFY**

Run: `scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q`
Expected: `All checks passed!`, `2467 passed`.

**Reviewer mutations:** `_keep_tab` not restoring (`test_a_rebuild_keeps_the_page_and_its_tab`); `_add_tab` without `scroller.show_all()` (the same test: a notebook does not switch to a hidden page); `_page_to_show` without the fallback (`test_a_page_that_is_gone_after_a_hand_edit_falls_back_to_the_theme`); `rebuild` not selecting the page in the tree (`test_the_tree_lists_the_theme_and_the_monitors_beside_the_pages`); `body.pack1(self.tree, True, True)` (shrinkable below 200 px; reviewer reads it, the size request is pinned by `test_it_is_at_least_200_px_wide`); the heading for the first part too (`test_a_later_part_of_a_tab_has_its_own_heading`); the monitor page built at `("monitors",)` (`test_a_monitor_page_has_the_theme_tabs_under_an_override_banner`).

- [ ] **Step 6: Commit**

```bash
git add settings/view.py tests/test_settings_view.py
git commit -m "feat(settings): tabbed Theme and monitor pages beside the page tree" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 7: The per-screen toolbar; Undo and Revert all leave the top bar

**Files:**
- Create: `settings/toolbar.py`
- Modify: `settings/view.py` (the toolbar replaces the top bar: no `undo_button`, `revert_button`, path label, `use_undo_action`, `_sync_undo_button`; `desktop=` parameter; `_sync_toolbar`, `_on_mode`, `add_panel`; the mode row leaves the Panels tab), `settings/controller.py` (no `use_undo_action` call)
- Test: `tests/test_settings_toolbar.py` (new), `tests/test_settings_view.py` (`shown_mode`, assertions on the history instead of the Undo button, 6 new tests), `tests/test_settings_controller.py` (the Undo-button test becomes `test_undo_and_revert_all_are_only_in_the_edit_menu`; `shown_mode`), `tests/test_settings_dialogs.py` (Revert all through `confirm_revert()`)

**Interfaces:**
- Consumes: Task 1 (`AddChoice`, `add_choices`, `MODE_HINTS`), Task 2 (`SHELL_NOTE`, `mode_flags`, `mode_of`, `desktop_label`, `screen_of`, `NOT_CONNECTED`), `settings.fields.ChoiceEditor` (greys out float), Task 4 (`_on_change` goes through the queue).
- Produces: `settings.toolbar.NO_SCREEN = "No screen selected"`, `ScreenToolbar(choices, native_label, on_mode: Callable[[str, str], None], on_add: Callable[[str, AddChoice], None])` with `title`, `edge`, `native`, `kind` (`ChoiceEditor`), `add_button`, `note`, `screen`, `show_screen(screen: str | None, title="", mode="plasma")`, `chosen() -> AddChoice | None`; `SettingsView(session, outputs, confirm_revert=None, on_state=None, desktop=None)`, `SettingsView.toolbar`, `SettingsView.add_panel(screen: str, choice: AddChoice) -> None`, `SettingsView._on_mode(screen, mode)`, `SettingsView._sync_toolbar()`.

- [ ] **Step 1: Write the failing tests:**

```diff
diff --git a/tests/test_settings_controller.py b/tests/test_settings_controller.py
index 8e4d537..7a1234c 100644
--- a/tests/test_settings_controller.py
+++ b/tests/test_settings_controller.py
@@ -166,19 +166,30 @@ def test_items_follow_the_session(make):
     assert on(c, "redo") and not on(c, "revert")  # back at the start: nothing to revert
 
 
-def test_the_top_bars_undo_button_is_the_undo_action(make):
+def test_undo_and_revert_all_are_only_in_the_edit_menu(make):
+    """Plan 3: the top bar's Undo and Revert all buttons are gone (Edit menu, Ctrl+Z)."""
     c, path = make()
-    button = c.view.undo_button
-    assert button.get_action_name() == "win.undo"
-    assert button.get_sensitive() == on(c, "undo") is True  # enabled whenever Undo is
+    labels = [w.get_label() for w in walk(c.view) if isinstance(w, Gtk.Button)]
+    assert "Undo" not in labels and "Revert all" not in labels
     c.view._on_change(DEPTH, 90)
     c.view._on_change(SHELL, "both")
-    button.clicked()  # one click is one undo (not the action and a handler of its own)
+    run(c, "undo")  # one undo
     assert 'shell = "edge"' in path.read_text() and "depth = 90" in path.read_text()
-    c.actions.lookup_action("undo").set_enabled(False)
-    assert not button.get_sensitive()  # it follows the action, not the history
-    c.sync()
-    assert button.get_sensitive()
+
+
+def walk(widget):
+    yield widget
+    if isinstance(widget, Gtk.Container):
+        for child in widget.get_children():
+            yield from walk(child)
+
+
+def shown_mode(view, screen="HDMI-A-1"):
+    """The `shell` value the toolbar's checkboxes show for `screen` (its page shown)."""
+    from settings.screens import mode_of
+
+    view.show_page(f"monitor:{screen}")
+    return mode_of(view.toolbar.edge.get_active(), view.toolbar.native.get_active())
 
 
 def test_save_and_undo_stay_on_while_a_value_is_pending(make, pending):
@@ -309,7 +320,7 @@ def test_a_discard_that_meets_a_hand_edit_stays_and_says_so(make):
     assert c.can_leave() is False and path.read_text() == hand
     assert "nothing was discarded" in c.view.banner_label.get_text()
     # the rows were rebuilt from the hand edit, not left showing the old value
-    assert row(c, SHELL).editor.widget.get_active_id() == "both"
+    assert shown_mode(c.view) == "both"
 
 
 def test_a_hand_edit_that_makes_the_file_invalid_updates_the_items(make):
@@ -674,7 +685,7 @@ def test_save_as_does_not_copy_a_file_changed_by_hand_while_the_chooser_was_open
     run(c, "save-as")
     assert not copy.exists() and c.launches == [] and c.quits == []
     assert path.read_text() == hand and not c.session.changed_outside()
-    assert row(c, SHELL).editor.widget.get_active_id() == "both"  # shown from the hand edit
+    assert shown_mode(c.view) == "both"  # shown from the hand edit
     assert "changed outside" in c.view.banner_label.get_text()
 
 
diff --git a/tests/test_settings_dialogs.py b/tests/test_settings_dialogs.py
index d54af99..b72b525 100644
--- a/tests/test_settings_dialogs.py
+++ b/tests/test_settings_dialogs.py
@@ -58,7 +58,7 @@ def view(tmp_path, fake_registry):
 
 def test_revert_all_asks_through_the_seam_and_cancel_keeps_the_change(view):
     view._on_change(("monitors", "HDMI-A-1", "shell"), "both")
-    view.revert_button.emit("clicked")
+    view.confirm_revert()  # Edit > Revert all
     assert len(view.asked) == 1 and "goes back to how it was" in view.asked[0]
     assert 'shell = "both"' in view.path.read_text()
 
diff --git a/tests/test_settings_toolbar.py b/tests/test_settings_toolbar.py
new file mode 100644
index 0000000..2dce4da
--- /dev/null
+++ b/tests/test_settings_toolbar.py
@@ -0,0 +1,98 @@
+"""settings.toolbar: the per-screen toolbar (a plain widget; no window is created)."""
+
+import pytest
+
+gi = pytest.importorskip("gi")
+gi.require_version("Gtk", "3.0")
+gi.require_version("Gdk", "3.0")
+
+from gi.repository import Gtk  # noqa: E402
+
+if not Gtk.init_check()[0]:
+    pytest.skip("no display", allow_module_level=True)
+
+from settings.form import FLOAT_CHOICE, WidgetChoice, add_choices  # noqa: E402
+from settings.screens import SHELL_NOTE  # noqa: E402
+from settings.toolbar import NO_SCREEN, ScreenToolbar  # noqa: E402
+
+CHOICES = add_choices((WidgetChoice("clock", "Clock"), WidgetChoice("box", "Box", ("corner",))))
+
+
+@pytest.fixture
+def toolbar():
+    modes, adds = [], []
+    t = ScreenToolbar(
+        CHOICES,
+        "KDE Plasma",
+        lambda screen, mode: modes.append((screen, mode)),
+        lambda screen, choice: adds.append((screen, choice.id)),
+    )
+    t.modes, t.adds = modes, adds
+    yield t
+    t.destroy()
+
+
+def checks(t):
+    return t.edge.get_active(), t.native.get_active()
+
+
+def test_with_no_screen_it_is_insensitive(toolbar):
+    assert toolbar.title.get_text() == NO_SCREEN and toolbar.screen is None
+    for w in (toolbar.edge, toolbar.native, toolbar.kind.widget, toolbar.add_button):
+        assert not w.get_sensitive()
+    toolbar.add_button.clicked()
+    assert toolbar.adds == []
+
+
+def test_it_shows_the_screen_and_its_mode_without_calling_back(toolbar):
+    toolbar.show_screen("HDMI-A-1", "HDMI-A-1", "both")
+    assert toolbar.title.get_text() == "HDMI-A-1" and checks(toolbar) == (True, True)
+    toolbar.show_screen("DP-2", "DP-2 (not connected)", "plasma")
+    assert toolbar.title.get_text() == "DP-2 (not connected)"
+    assert checks(toolbar) == (False, True) and toolbar.edge.get_sensitive()
+    assert toolbar.modes == []
+    assert 'shell = "plasma"' in toolbar.title.get_tooltip_text()
+
+
+@pytest.mark.parametrize(
+    "start, toggle, written",
+    [
+        ("plasma", "edge", "both"),
+        ("both", "native", "edge"),
+        ("edge", "edge", "none"),
+        ("none", "native", "plasma"),
+    ],
+)
+def test_a_toggle_writes_the_mode_of_both_checkboxes(toolbar, start, toggle, written):
+    toolbar.show_screen("HDMI-A-1", "HDMI-A-1", start)
+    check = getattr(toolbar, toggle)
+    check.set_active(not check.get_active())  # as a click does
+    assert toolbar.modes == [("HDMI-A-1", written)]
+
+
+def test_the_labels_and_the_note(toolbar):
+    assert toolbar.edge.get_label() == "Enable" and toolbar.native.get_label() == "KDE Plasma"
+    assert toolbar.note.get_text() == SHELL_NOTE
+
+
+def test_add_sends_the_chosen_panel_type(toolbar):
+    toolbar.show_screen("HDMI-A-1", "HDMI-A-1", "edge")
+    assert toolbar.chosen().id == "edge:clock"  # the first one
+    toolbar.kind.widget.set_active_id("corner:box")
+    toolbar.add_button.clicked()
+    assert toolbar.adds == [("HDMI-A-1", "corner:box")]
+
+
+def test_float_is_listed_but_cannot_be_chosen(toolbar):
+    toolbar.show_screen("HDMI-A-1", "HDMI-A-1", "edge")
+    toolbar.kind.widget.set_active_id("corner:box")
+    labels = [r[0] for r in toolbar.kind.widget.get_model()]
+    assert labels[-1] == "Float panel (coming soon)"
+    toolbar.kind.widget.set_active_id(FLOAT_CHOICE)  # greyed out; only the program can
+    assert toolbar.chosen().id == "corner:box"  # the last real choice comes back
+    toolbar.add_button.clicked()
+    assert toolbar.adds == [("HDMI-A-1", "corner:box")]
+
+
+def test_the_add_button_keeps_the_focus_where_it_is(toolbar):
+    assert not toolbar.add_button.get_focus_on_click()
diff --git a/tests/test_settings_view.py b/tests/test_settings_view.py
index c427621..7ffa391 100644
--- a/tests/test_settings_view.py
+++ b/tests/test_settings_view.py
@@ -18,6 +18,7 @@ if not Gtk.init_check()[0]:
     pytest.skip("no display", allow_module_level=True)
 
 from settings.panels import PanelEditor  # noqa: E402
+from settings.screens import mode_of  # noqa: E402
 from settings.session import SettingsSession  # noqa: E402
 from settings.view import SettingsView  # noqa: E402
 from shell.outputs import Output  # noqa: E402
@@ -66,6 +67,12 @@ def row(view, path):
     return next(r for r in view.rows if r.path == path)
 
 
+def shown_mode(view, screen="HDMI-A-1"):
+    """The `shell` value the toolbar's checkboxes show for `screen` (its page shown)."""
+    view.show_page(f"monitor:{screen}")
+    return mode_of(view.toolbar.edge.get_active(), view.toolbar.native.get_active())
+
+
 def walk(widget):
     yield widget
     if isinstance(widget, Gtk.Container):
@@ -83,7 +90,7 @@ def test_a_page_for_the_theme_and_each_monitor(make):
     assert pages(view) == ["theme", "monitor:HDMI-A-1", "monitor:DP-1"]
     accent = row(view, ("theme", "accent")).editor.widget.get_rgba()
     assert accent.to_string() == "rgb(143,211,182)"
-    assert row(view, ("monitors", "DP-1", "shell")).editor.widget.get_active_id() == "plasma"
+    assert shown_mode(view, "DP-1") == "plasma"  # not in the file: the default
     assert row(view, DEPTH).editor.widget.get_value() == 64  # the widget's default
 
 
@@ -98,7 +105,7 @@ def test_a_valid_edit_is_written_and_shown(make):
     assert "depth = 90" in path.read_text() and "# gate config" in path.read_text()
     r = row(view, DEPTH)
     assert r.editor.widget.get_value() == 90 and r.reset.get_sensitive()
-    assert view.undo_button.get_sensitive()
+    assert view.session.history
 
 
 def test_an_invalid_edit_shows_its_error_under_the_row(make):
@@ -167,7 +174,7 @@ def test_undo_and_revert(make):
     assert "depth = 90" in path.read_text() and 'shell = "edge"' in path.read_text()
     view.revert()
     assert path.read_text() == USER
-    assert not view.undo_button.get_sensitive()
+    assert not view.session.history
 
 
 def test_the_visible_page_survives_a_rebuild(make):
@@ -181,7 +188,7 @@ def test_a_hand_edit_is_reloaded_and_announced(make):
     view, path = make()
     path.write_text(USER.replace('shell = "edge"', 'shell = "both"'))
     view.file_changed()
-    assert row(view, SHELL).editor.widget.get_active_id() == "both"
+    assert shown_mode(view) == "both"
     assert view.banner.get_visible() and "changed outside" in view.banner_label.get_text()
 
 
@@ -330,7 +337,7 @@ def test_a_pending_value_does_not_break_a_hand_edit_reload(make, pending):
     row(view, DEPTH).editor.widget.set_value(120)
     path.write_text(USER.replace('shell = "edge"', 'shell = "both"'))
     view.file_changed()
-    assert row(view, SHELL).editor.widget.get_active_id() == "both"
+    assert shown_mode(view) == "both"
     assert "depth" not in path.read_text()
 
 
@@ -472,13 +479,14 @@ def test_the_invalid_file_banner_names_the_restore_command(make):
     assert "--restore-config" in view.banner_label.get_text()
 
 
-def test_undo_is_insensitive_after_a_rebuild_with_no_history(make):
+def test_an_invalid_file_leaves_the_toolbar_without_a_screen(make):
     view, path = make()
-    view._on_change(DEPTH, 90)
-    assert view.undo_button.get_sensitive()
+    view.show_page("monitor:HDMI-A-1")
+    assert view.toolbar.screen == "HDMI-A-1"
     path.write_text('[monitors.HDMI-A-1]\nshell = "sideways"\n')  # invalid: no refresh runs
     view.file_changed()
-    assert not view.session.history and not view.undo_button.get_sensitive()
+    assert view.toolbar.screen is None and not view.toolbar.edge.get_sensitive()
+    assert not view.toolbar.add_button.get_sensitive()
 
 
 MIN_LENGTH, MAX_LENGTH = (*P0, "min_length"), (*P0, "max_length")
@@ -1049,3 +1057,61 @@ def test_a_later_part_of_a_tab_has_its_own_heading(make):
     assert "Handle style" in texts(handle)
     borders = nb.get_nth_page(tabs(view, "theme").index("Borders"))
     assert "Border" not in texts(borders)  # one part: no heading
+
+
+# ---- the per-screen toolbar ------------------------------------------------------------------
+
+
+def test_the_toolbar_follows_the_selected_screen(make):
+    view, _ = make()
+    assert view.toolbar.screen is None  # the Theme page
+    click_row(view, "monitor:HDMI-A-1")
+    assert view.toolbar.screen == "HDMI-A-1"
+    assert (view.toolbar.edge.get_active(), view.toolbar.native.get_active()) == (True, False)
+    click_row(view, "theme")
+    assert view.toolbar.screen is None and not view.toolbar.edge.get_sensitive()
+
+
+def test_a_checkbox_writes_the_mode_in_one_change(make):
+    view, path = make()
+    click_row(view, "monitor:HDMI-A-1")
+    view.toolbar.native.set_active(True)  # as a click does: edge + native
+    assert 'shell = "both"' in path.read_text() and len(view.session.history) == 1
+    view.toolbar.edge.set_active(False)
+    view.toolbar.native.set_active(False)
+    assert 'shell = "none"' in path.read_text()
+    assert shown_mode(view) == "none"
+
+
+def test_a_monitor_with_no_shell_key_shows_the_default(make):
+    view, path = make()
+    assert shown_mode(view, "DP-1") == "plasma"  # in no file: plasma
+    view.toolbar.edge.set_active(True)  # writes a [monitors.DP-1] table (a test file only)
+    assert '[monitors.DP-1]\nshell = "both"' in path.read_text()
+
+
+def test_a_refused_mode_change_shows_the_mode_in_the_file(make):
+    view, path = make()
+    click_row(view, "monitor:HDMI-A-1")
+    hand = USER.replace('shell = "edge"', 'shell = "plasma"')
+    path.write_text(hand)  # by hand, not seen yet
+    view.toolbar.native.set_active(True)  # the user meant edge -> both
+    drain()
+    assert path.read_text() == hand
+    assert "changed outside" in view.banner_label.get_text()
+    assert shown_mode(view) == "plasma"  # the re-read file, not the click
+
+
+def test_add_puts_the_chosen_panel_on_the_selected_screen(make):
+    view, path = make()
+    click_row(view, "monitor:HDMI-A-1")
+    view.toolbar.kind.widget.set_active_id("edge:clock")
+    view.toolbar.add_button.clicked()
+    entries = view.session.user["monitors"]["HDMI-A-1"]["panels"]
+    assert entries[-1] == {"panel": "edge", "name": "Clock", "widget": "clock"}
+    assert view.stack.get_visible_child_name() == "monitor:HDMI-A-1"
+
+
+def test_the_mode_row_left_the_monitor_page(make):
+    view, _ = make()
+    assert not any(r.path == SHELL for r in view.rows)
```

- [ ] **Step 2: Run them to see them fail**

Run: `scripts/py -m pytest -q tests/test_settings_toolbar.py tests/test_settings_view.py tests/test_settings_controller.py tests/test_settings_dialogs.py`
Expected: `1 error` during collection (`ModuleNotFoundError: No module named 'settings.toolbar'`); the view and controller tests fail on `view.toolbar`.

- [ ] **Step 3: Implement:**

```diff
diff --git a/settings/controller.py b/settings/controller.py
index 30d3bbf..c9d18e3 100644
--- a/settings/controller.py
+++ b/settings/controller.py
@@ -132,7 +132,6 @@ class SettingsController(Gtk.Box):
         self.view = SettingsView(
             session, self.outputs, confirm_revert=self.dialogs.confirm_revert, on_state=self.sync
         )
-        self.view.use_undo_action("win.undo")  # the top bar's button is the menu's Undo
         self.body.add_named(self.view, "config")
         self.view.show_all()
         self.body.set_visible_child_name("config")
diff --git a/settings/toolbar.py b/settings/toolbar.py
new file mode 100644
index 0000000..1ffc506
--- /dev/null
+++ b/settings/toolbar.py
@@ -0,0 +1,104 @@
+"""The per-screen toolbar (panel/widget spec 7): the selected screen's name; the checkboxes
+**Enable** (Edge Shell on this screen) and the native desktop (labelled with its name: KDE
+Plasma, Hyprland, ...), written together to the monitor's `shell` key (settings.screens); a
+one-line note that Edge Shell does not hide or show Plasma's panel yet; and the panel type list
+(each widget by display name and panel kind, float listed and greyed out) with **Add**.
+
+It shows the screen of the selected page: a monitor page's, or a panel page's monitor. On the
+Theme page, or while the file is invalid, it names no screen and is insensitive. Values shown
+with show_screen never call back. A plain Gtk.Box: tested without a window."""
+
+from __future__ import annotations
+
+from collections.abc import Callable
+
+import gi
+
+gi.require_version("Gtk", "3.0")
+from gi.repository import GLib, Gtk
+
+from settings.fields import ChoiceEditor
+from settings.form import MODE_HINTS, AddChoice
+from settings.screens import SHELL_NOTE, mode_flags, mode_of
+
+NO_SCREEN = "No screen selected"
+
+
+class ScreenToolbar(Gtk.Box):
+    def __init__(
+        self,
+        choices: tuple[AddChoice, ...],
+        native_label: str,
+        on_mode: Callable[[str, str], None],
+        on_add: Callable[[str, AddChoice], None],
+    ):
+        """`on_mode(screen, shell_value)`: a checkbox was toggled by the user.
+        `on_add(screen, choice)`: Add was pressed with an enabled panel type chosen."""
+        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
+        self.set_property("margin", 6)
+        self._on_mode = on_mode
+        self._on_add = on_add
+        self._quiet = False
+        self.screen: str | None = None
+        self.choices = {c.id: c for c in choices}
+        line = Gtk.Box(spacing=12)
+        self.title = Gtk.Label(xalign=0)
+        self.edge = Gtk.CheckButton(label="Enable")
+        self.edge.set_tooltip_text("Edge Shell's frame and panels on this screen")
+        self.native = Gtk.CheckButton(label=native_label)
+        self.native.set_tooltip_text(f"{native_label} on this screen")
+        for check in (self.edge, self.native):
+            check.connect("toggled", self._toggled)
+        disabled = tuple(c.id for c in choices if not c.enabled)
+        self.kind = ChoiceEditor(
+            tuple(self.choices),
+            lambda chosen: self.kind.set(chosen),  # a greyed-out pick comes back to this one
+            tuple(c.label for c in choices),
+            disabled,
+        )
+        self.kind.widget.set_tooltip_text("The panel type to add to this screen")
+        self.kind.set(next(c.id for c in choices if c.enabled))
+        self.add_button = Gtk.Button(label="Add")
+        self.add_button.set_tooltip_text("Add a panel of this type to this screen")
+        self.add_button.set_focus_on_click(False)
+        self.add_button.connect("clicked", lambda _b: self._add())
+        line.pack_start(self.title, False, False, 0)
+        line.pack_start(self.edge, False, False, 0)
+        line.pack_start(self.native, False, False, 0)
+        line.pack_end(self.add_button, False, False, 0)
+        line.pack_end(self.kind.widget, False, False, 0)
+        self.note = Gtk.Label(label=SHELL_NOTE, xalign=0, wrap=True)
+        self.note.get_style_context().add_class("dim-label")
+        self.pack_start(line, False, False, 0)
+        self.pack_start(self.note, False, False, 0)
+        self.show_screen(None)
+
+    def show_screen(self, screen: str | None, title: str = "", mode: str = "plasma") -> None:
+        """Show `screen` (its tree title, its `shell` value in effect), or no screen."""
+        self.screen = screen
+        self._quiet = True
+        try:
+            edge, native = mode_flags(mode) if screen is not None else (False, False)
+            self.edge.set_active(edge)
+            self.native.set_active(native)
+        finally:
+            self._quiet = False
+        text = NO_SCREEN if screen is None else title or screen
+        self.title.set_markup(f"<b>{GLib.markup_escape_text(text)}</b>")
+        hint = None if screen is None else f'shell = "{mode}": {MODE_HINTS[mode]}'
+        self.title.set_tooltip_text(hint)
+        for widget in (self.edge, self.native, self.kind.widget, self.add_button):
+            widget.set_sensitive(screen is not None)
+
+    def chosen(self) -> AddChoice | None:
+        return self.choices.get(self.kind.widget.get_active_id())
+
+    def _toggled(self, _check) -> None:
+        if self._quiet or self.screen is None:
+            return
+        self._on_mode(self.screen, mode_of(self.edge.get_active(), self.native.get_active()))
+
+    def _add(self) -> None:
+        choice = self.chosen()
+        if self.screen is not None and choice is not None and choice.enabled:
+            self._on_add(self.screen, choice)
diff --git a/settings/view.py b/settings/view.py
index 7c4e24d..888acb4 100644
--- a/settings/view.py
+++ b/settings/view.py
@@ -1,4 +1,4 @@
-"""The settings window's content: a top bar (Undo, Revert all, the file path), a banner for
+"""The settings window's content: the per-screen toolbar (settings.toolbar), a banner for
 errors and notices, and beside the tree (settings.tree: Theme, the monitors) the page the tree
 selects (panel/widget spec 7). The Theme page and each monitor page have tabs (General,
 Borders, Shadows, Handle, Layout: settings.form.theme_tabs); a monitor page's values override
@@ -29,19 +29,30 @@ from settings.dialogs import GtkDialogs
 from settings.document import UserDocument
 from settings.fields import DEBOUNCE_MS, FieldRow
 from settings.form import (
-    MODE_HINTS,
+    AddChoice,
     SectionSpec,
     TabSpec,
+    add_choices,
     config_form,
     registry_widgets,
     theme_tabs,
 )
-from settings.pages import THEME, fallback_page, monitor_page, parse_page, tree_entries
+from settings.pages import (
+    NOT_CONNECTED,
+    THEME,
+    fallback_page,
+    monitor_page,
+    parse_page,
+    screen_of,
+    tree_entries,
+)
 from settings.panels import PanelEditor
 from settings.queue import RESET, EditQueue, QueuedEdit, describe, path_text
+from settings.screens import desktop_label
 from settings.session import ChangedOutside, SettingsSession, check_text
+from settings.toolbar import ScreenToolbar
 from settings.tree import SettingsTree
-from settings.values import field_value, layout_preview, lookup, panel_ops
+from settings.values import field_value, layout_preview, lookup, new_panel_entry, panel_ops
 from shell.config.models import ConfigError
 from shell.outputs import Output
 from shell.registry import requests_for
@@ -60,7 +71,10 @@ class SettingsView(Gtk.Box):
         outputs: list[Output],
         confirm_revert: Callable[[Any, str], bool] | None = None,
         on_state: Callable[[], None] | None = None,
+        desktop: str | None = None,
     ):
+        """`desktop`: the native desktop checkbox's label (None: from XDG_CURRENT_DESKTOP,
+        settings.screens.desktop_label)."""
         super().__init__(orientation=Gtk.Orientation.VERTICAL)
         self.session = session
         # asks before Revert all (parent, text) -> OK?; tests pass a fake, no dialog runs
@@ -69,7 +83,8 @@ class SettingsView(Gtk.Box):
         # window updates its menu items and title
         self._on_state = on_state or (lambda: None)
         self.outputs = {o.name: o for o in outputs}
-        self.form = config_form(registry_widgets())
+        widgets = registry_widgets()
+        self.form = config_form(widgets)
         self.rows: list[FieldRow] = []
         # monitor -> the labels showing its layout warnings (its page; later its panels' pages)
         self.previews: dict[str, list[Gtk.Label]] = {}
@@ -85,20 +100,10 @@ class SettingsView(Gtk.Box):
         self.queue = EditQueue()  # every value edit, applied in order (settings.queue)
         self._queue_timer = 0  # the one pause timer of the queued spin edits (0: none)
 
-        bar = Gtk.Box(spacing=6, margin=6)
-        self.undo_button = Gtk.Button(label="Undo")
-        self.undo_button.set_tooltip_text("Undo the last change (Ctrl+Z)")
-        self._undo_clicked = self.undo_button.connect("clicked", lambda _b: self.undo())
-        self._undo_by_action = False
-        self.revert_button = Gtk.Button(label="Revert all")
-        self.revert_button.set_tooltip_text("Put back the file as it was when this window opened")
-        self.revert_button.connect("clicked", lambda _b: self.confirm_revert())
-        where = Gtk.Label(label=str(session.path), xalign=1, selectable=True)
-        where.get_style_context().add_class("dim-label")
-        bar.pack_start(self.undo_button, False, False, 0)
-        bar.pack_start(self.revert_button, False, False, 0)
-        bar.pack_end(where, True, True, 0)
-
+        # Undo and Revert all are in the Edit menu (and Ctrl+Z); the file is in the title
+        self.toolbar = ScreenToolbar(
+            add_choices(widgets), desktop or desktop_label(), self._on_mode, self.add_panel
+        )
         self.banner = Gtk.InfoBar()
         self.banner_label = Gtk.Label(xalign=0, wrap=True, selectable=True)
         self.banner.get_content_area().add(self.banner_label)
@@ -109,7 +114,7 @@ class SettingsView(Gtk.Box):
         body = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
         body.pack1(self.tree, False, False)  # never narrower than its MIN_WIDTH
         body.pack2(self.stack, True, False)
-        self.pack_start(bar, False, False, 0)
+        self.pack_start(self.toolbar, False, False, 0)
         self.pack_start(self.banner, False, False, 0)
         self.pack_start(body, True, True, 0)
         self.rebuild()
@@ -174,20 +179,19 @@ class SettingsView(Gtk.Box):
                 f"\n{self.session.error}",
                 Gtk.MessageType.ERROR,
             )
-        self._sync_undo_button()
+            self._sync_toolbar()  # refresh() does it for a valid file
         self._on_state()
 
-    def use_undo_action(self, name: str) -> None:
-        """Hand the Undo button to a window action ("win.undo"): it then clicks through the
-        action and is enabled exactly when the menu's Undo is. Without this (the view alone)
-        the button undoes by itself and follows the history."""
-        self._undo_by_action = True
-        self.undo_button.disconnect(self._undo_clicked)
-        self.undo_button.set_action_name(name)
-
-    def _sync_undo_button(self) -> None:
-        if not self._undo_by_action:
-            self.undo_button.set_sensitive(bool(self.session.history))
+    def _sync_toolbar(self) -> None:
+        """The toolbar shows the screen of the page shown (a monitor page's, a panel page's
+        monitor) with its `shell` value in effect; none on the Theme page or while the file is
+        invalid."""
+        screen = screen_of(self.stack.get_visible_child_name())
+        if screen is None or self.session.config is None:
+            self.toolbar.show_screen(None)
+            return
+        title = screen if screen in self.outputs else screen + NOT_CONNECTED
+        self.toolbar.show_screen(screen, title, self.config.monitor(screen).shell)
 
     def _page_to_show(self, wanted: str | None) -> str:
         """`wanted` if it is still a page; else its fallback (a gone panel's monitor), else the
@@ -201,6 +205,7 @@ class SettingsView(Gtk.Box):
         """Show `page` (the tree's selection)."""
         if self.stack.get_child_by_name(page) is not None:
             self.stack.set_visible_child_name(page)
+            self._sync_toolbar()
 
     def _add_page(self, name: str, content: Gtk.Widget, sensitive: bool) -> None:
         content.set_sensitive(sensitive)
@@ -307,14 +312,9 @@ class SettingsView(Gtk.Box):
         banner = Gtk.InfoBar(message_type=Gtk.MessageType.INFO)
         banner.get_content_area().add(Gtk.Label(label=override_text(name), xalign=0, wrap=True))
         top = [self._heading(title), banner, self._preview(name)]
-        # until the toolbar and the panel pages take them over: the mode and the panel list
+        # until the panel pages take it over: the panel list
         panels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
         panels.set_property("margin", 12)
-        panels.pack_start(self.section_rows(self.form.monitor, prefix), False, False, 0)
-        hints = "\n".join(f"{mode}: {hint}" for mode, hint in MODE_HINTS.items())
-        note = Gtk.Label(label=hints, xalign=0, wrap=True)
-        note.get_style_context().add_class("dim-label")
-        panels.pack_start(note, False, False, 0)
         editor = PanelEditor(
             self.form,
             name,
@@ -342,7 +342,7 @@ class SettingsView(Gtk.Box):
             for label in labels:
                 label.set_text("\n".join(warnings))
                 label.set_visible(bool(warnings))
-        self._sync_undo_button()
+        self._sync_toolbar()
         self._on_state()
 
     def show_banner(self, text: str, kind: Gtk.MessageType = Gtk.MessageType.ERROR) -> None:
@@ -517,6 +517,22 @@ class SettingsView(Gtk.Box):
         if not self.apply(edit, structural=True):
             self._expand.pop(monitor, None)
 
+    def _on_mode(self, screen: str, mode: str) -> None:
+        """A toolbar checkbox: write `shell` (an error goes to the banner); the checkboxes
+        then show what is in effect, also when the write was refused."""
+        self._on_change(("monitors", screen, "shell"), mode)
+        self._sync_toolbar()
+
+    def add_panel(self, screen: str, choice: AddChoice) -> None:
+        """The toolbar's Add: a new entry of the chosen widget and kind with a free name
+        (settings.values.new_panel_entry), shown open."""
+        count = len(self.config.monitor(screen).panels)
+
+        def edit(doc: UserDocument) -> None:
+            doc.add_panel(screen, new_panel_entry(doc.data, screen, choice.widget, choice.kind))
+
+        self._structural(screen, edit, count)
+
     def _row(self, path: tuple) -> FieldRow | None:
         return next((r for r in self.rows if r.path == path), None)
 
```

- [ ] **Step 4: Run them to see them pass**

Run: `scripts/py -m pytest -q tests/test_settings_toolbar.py tests/test_settings_view.py tests/test_settings_controller.py tests/test_settings_dialogs.py tests/test_settings_app.py`
Expected: all pass.

- [ ] **Step 5: VERIFY**

Run: `scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q`
Expected: `All checks passed!`, `2483 passed`.

**Reviewer mutations:** `show_screen` without `_quiet` (`test_it_shows_the_screen_and_its_mode_without_calling_back`); `_toggled` writing `mode_of(native, edge)` (`test_a_toggle_writes_the_mode_of_both_checkboxes`); `_on_mode` without `_sync_toolbar()` (`test_a_refused_mode_change_shows_the_mode_in_the_file`); `show_page` without `_sync_toolbar()` (`test_the_toolbar_follows_the_selected_screen`); `_sync_toolbar` showing a screen for an invalid file (`test_an_invalid_file_leaves_the_toolbar_without_a_screen`); the float choice enabled (`test_float_is_listed_but_cannot_be_chosen`); `add_panel` ignoring `choice.kind` (`test_add_puts_the_chosen_panel_on_the_selected_screen` writes `panel = "edge"`; with a corner choice the toolbar test catches it); the Undo button kept (`test_undo_and_revert_all_are_only_in_the_edit_menu`).

- [ ] **Step 6: Commit**

```bash
git add settings/toolbar.py settings/view.py settings/controller.py tests/test_settings_toolbar.py tests/test_settings_view.py tests/test_settings_controller.py tests/test_settings_dialogs.py
git commit -m "feat(settings): the per-screen toolbar; Undo and Revert all leave the top bar" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 8: A tabbed page per panel; move, remove and rename from the tree and the toolbar

**Files:**
- Modify: `settings/panels.py` (rewritten, pure: `PanelEditor` goes), `settings/view.py` (panel pages and tree rows; `_select` replaces `_expand`; `_structural(edit, show)`; `on_panel_action`; `add_panel` through `add_step`; the Panels tab and `_tabbed(extra=)` go; a refused structural edit picks no page), `settings/toolbar.py` (Move up, Move down, Remove; `show_screen(..., panel=)`)
- Test: `tests/test_settings_panels.py` (rewritten, pure), `tests/test_settings_view.py` (helpers `add`, `act`, `shown`, `title`; the expander tests become page tests; 7 new tests), `tests/test_settings_toolbar.py` (5 cases)

**Interfaces:**
- Consumes: Task 1 (`panel_tabs`), Task 2 (`panel_page`, `monitor_page`, `parse_page`), Task 5 (`PANEL_ACTIONS`, `SettingsTree(on_select, on_action)`, `row_of`, `buttons`), Task 7 (`ScreenToolbar`), `settings.values.new_panel_entry(..., kind)`, `shell.registry.requests_for`.
- Produces: `settings.panels.ACTIONS`, `panel_title(index, req) -> str`, `panel_section(form, req) -> SectionSpec`, `add_step(monitor, count, widget, kind=None) -> tuple[Edit, str]`, `panel_step(monitor, index, count, action) -> tuple[Edit, str] | None` (ValueError for an unknown action); `ScreenToolbar(..., on_panel: Callable[[str], None] | None = None)`, `ScreenToolbar.panel_buttons: dict[str, Gtk.Button]`, `show_screen(screen, title="", mode="plasma", panel: tuple[int, int] | None = None)`; `SettingsView.on_panel_action(page: str, action: str) -> None`, `SettingsView._select: str | None`, `SettingsView._panel_page(name, index, req)`.

- [ ] **Step 1: Write the failing tests:**

```diff
diff --git a/tests/test_settings_panels.py b/tests/test_settings_panels.py
index 65a9662..8db20d2 100644
--- a/tests/test_settings_panels.py
+++ b/tests/test_settings_panels.py
@@ -1,26 +1,17 @@
-"""settings.panels: the panel list editor of one monitor (widgets only; no window shown)."""
+"""settings.panels: each panel's title and rows, and the add, move and remove edits with the
+page shown after each (pure)."""
 
 import pytest
 
-gi = pytest.importorskip("gi")
-gi.require_version("Gtk", "3.0")
-gi.require_version("Gdk", "3.0")
 pytest.importorskip("tomlkit")
 
-from gi.repository import Gtk  # noqa: E402
-
-import settings.panels as panels  # noqa: E402
-
-if not Gtk.init_check()[0]:
-    pytest.skip("no display", allow_module_level=True)
-
 from settings.document import UserDocument  # noqa: E402
 from settings.form import WidgetChoice, config_form, registry_widgets  # noqa: E402
+from settings.panels import add_step, panel_section, panel_step, panel_title  # noqa: E402
 from shell.panel_spec import CornerDefaults, PanelDefaults  # noqa: E402
 from shell.registry import requests_for  # noqa: E402
 from shell.widget import Widget, WidgetProps  # noqa: E402
 
-FORM = config_form(tuple(WidgetChoice(w) for w in ("bar", "clock", "dock")))
 CORNER_FORM = config_form(
     (
         WidgetChoice("bar", "Bar"),
@@ -29,111 +20,31 @@ CORNER_FORM = config_form(
         WidgetChoice("dock", "Dock"),
     )
 )
-USER = (
-    '[[monitors.M.panels]]\npanel = "edge"\nname = "dock"\nwidget = "dock"\n'
-    '[[monitors.M.panels]]\npanel = "edge"\nname = "clock"\nwidget = "clock"\n'
-)
-
-
-@pytest.fixture
-def editor(make_config, fake_registry):
-    config = make_config(
-        monitors={
-            "M": {
-                "panels": [
-                    {"panel": "edge", "name": "dock", "widget": "dock"},
-                    {"panel": "edge", "name": "clock", "widget": "clock"},
-                ]
-            }
-        }
-    )
-    made, edits = [], []
-
-    def make_rows(section, prefix):
-        made.append((section.label, prefix))
-        return Gtk.Box()
-
-    on_edit = lambda edit, open_index: edits.append((edit, open_index))  # noqa: E731
-    ed = panels.PanelEditor(FORM, "M", requests_for(config, "M"), make_rows, on_edit, 1)
-    return ed, made, edits
+THREE = ("dock", "clock", "bar")
 
 
-def apply(edits):
-    doc = UserDocument(USER)
-    for edit, _open in edits:
-        edit(doc)
+def widgets_after(edit):
+    entry = '[[monitors.M.panels]]\npanel = "edge"\nname = "{0}"\nwidget = "{0}"\n'
+    doc = UserDocument("".join(entry.format(w) for w in THREE))
+    edit(doc)
     return [p["widget"] for p in doc.data["monitors"]["M"].get("panels", [])]
 
 
-def test_one_expander_per_entry_with_its_rows(editor):
-    ed, made, _ = editor
-    assert [e.get_label() for e in ed.expanders] == [
-        "1. dock: bottom, center",
-        "2. clock: top, center",
-    ]
-    assert made == [
-        ("Panel", ("monitors", "M", "panels", 0)),
-        ("Panel", ("monitors", "M", "panels", 1)),
-    ]
-    assert [e.get_expanded() for e in ed.expanders] == [False, True]
-
-
-def test_add_remove_and_move_are_document_edits(editor):
-    ed, _, edits = editor
-    ed.add("bar")
-    assert apply(edits) == ["dock", "clock", "bar"] and edits[0][1] == 2  # the new one opens
-    edits.clear()
-    ed.move(1, 0)
-    assert apply(edits) == ["clock", "dock"] and edits[0][1] == 0  # the moved one opens
-    edits.clear()
-    ed.remove(0)
-    assert apply(edits) == ["clock"] and edits[0][1] is None
-
-
-def test_the_widget_list_comes_from_the_form(editor):
-    ed, _, edits = editor
-    model = ed.widget_choice.get_model()
-    assert [row[0] for row in model] == ["bar", "clock", "dock"]
-    ed.add(None)  # nothing chosen: no edit
-    assert edits == []
-
-
-def test_first_cannot_move_up_and_last_cannot_move_down(editor):
-    ed, _, _ = editor
-
-    def buttons(i):
-        body = ed.expanders[i].get_child()
-        return body.get_children()[0].get_children()
-
-    up0, down0, _ = buttons(0)
-    up1, down1, _ = buttons(1)
-    assert (up0.get_sensitive(), down0.get_sensitive()) == (False, True)
-    assert (up1.get_sensitive(), down1.get_sensitive()) == (True, False)
-
-
 def test_corner_panels_get_their_own_rows_title_and_edges(make_config, corner_registry):
     """Spec 19: a corner widget's entry shows corner, edge (only its corner's two), width and
     height, never align or length; its title names the corner, the edge and the size."""
-    form = CORNER_FORM
     entries = [
         {"panel": "edge", "name": "dock", "widget": "dock"},
         {"panel": "corner", "name": "box", "widget": "box"},
         {"panel": "corner", "name": "box 2", "widget": "box", "corner": "top-right"},
     ]
-    config = make_config(monitors={"M": {"panels": entries}})
-    sections = []
-
-    def make_rows(section, _prefix):
-        sections.append(section)
-        return Gtk.Box()
-
-    ed = panels.PanelEditor(form, "M", requests_for(config, "M"), make_rows, lambda *_a: None)
-    assert [e.get_label() for e in ed.expanders] == [
+    requests = requests_for(make_config(monitors={"M": {"panels": entries}}), "M")
+    assert [panel_title(i, r) for i, r in enumerate(requests)] == [
         "1. dock: bottom, center",
         "2. box: bottom-left, from bottom, 300x390",
         "3. box 2: top-right, from top, 300x390",  # the name, not the widget
     ]
-    dock, box, moved = sections
+    dock, box, moved = (panel_section(CORNER_FORM, r) for r in requests)
     assert "align" in {f.key for f in dock.fields} and "corner" not in {f.key for f in dock.fields}
     assert [f.key for f in box.fields] == [
         "name",
@@ -146,118 +57,58 @@ def test_corner_panels_get_their_own_rows_title_and_edges(make_config, corner_re
     ]
     assert box.field("edge").choices == ("bottom", "left")
     assert moved.field("edge").choices == ("top", "right")
-    assert [row[0] for row in ed.widget_choice.get_model()] == ["Bar", "Box", "Clock", "Dock"]
-    edits = []
-    ed._on_edit = lambda edit, open_index: edits.append((edit, open_index))
-    ed.add("box")
-    doc = UserDocument("")
-    edits[0][0](doc)
-    assert (
-        doc.data
-        == {"monitors": {"M": {"panels": [{"panel": "corner", "name": "Box", "widget": "box"}]}}}
-        and edits[0][1] == 3
-    )
-
-
-THREE = ("dock", "clock", "bar")
-
-
-def three_panel_editor(make_config, form=FORM):
-    panels_ = [{"panel": "edge", "name": w, "widget": w} for w in THREE]
-    config = make_config(monitors={"M": {"panels": panels_}})
-    edits = []
-    ed = panels.PanelEditor(
-        form,
-        "M",
-        requests_for(config, "M"),
-        lambda *_a: Gtk.Box(),
-        lambda edit, open_index: edits.append((edit, open_index)),
-    )
-    return ed, edits
-
-
-def row_buttons(ed, i):
-    return ed.expanders[i].get_child().get_children()[0].get_children()
-
-
-def widgets_after(edit):
-    entry = '[[monitors.M.panels]]\npanel = "edge"\nname = "{0}"\nwidget = "{0}"\n'
-    doc = UserDocument("".join(entry.format(w) for w in THREE))
-    edit(doc)
-    return [p["widget"] for p in doc.data["monitors"]["M"].get("panels", [])]
 
 
 @pytest.mark.parametrize("i", [0, 1, 2])
-def test_each_rows_remove_button_removes_its_own_entry(make_config, fake_registry, i):
-    ed, edits = three_panel_editor(make_config)
-    row_buttons(ed, i)[2].clicked()
-    ((edit, open_index),) = edits
-    assert open_index is None
+def test_remove_takes_out_its_own_entry_and_shows_the_monitor(fake_registry, i):
+    edit, page = panel_step("M", i, 3, "remove")
     assert widgets_after(edit) == [w for k, w in enumerate(THREE) if k != i]
+    assert page == "monitor:M"
 
 
 @pytest.mark.parametrize("i", [1, 2])
-def test_each_rows_move_up_button_moves_its_own_entry_up(make_config, fake_registry, i):
-    ed, edits = three_panel_editor(make_config)
-    row_buttons(ed, i)[0].clicked()
-    ((edit, open_index),) = edits
-    assert open_index == i - 1
+def test_move_up_moves_its_own_entry_and_shows_it(fake_registry, i):
+    edit, page = panel_step("M", i, 3, "up")
     expected = list(THREE)
     expected[i - 1], expected[i] = expected[i], expected[i - 1]
-    assert widgets_after(edit) == expected
+    assert widgets_after(edit) == expected and page == f"panel:M:{i - 1}"
 
 
 @pytest.mark.parametrize("i", [0, 1])
-def test_each_rows_move_down_button_moves_its_own_entry_down(make_config, fake_registry, i):
-    ed, edits = three_panel_editor(make_config)
-    row_buttons(ed, i)[1].clicked()
-    ((edit, open_index),) = edits
-    assert open_index == i + 1
+def test_move_down_moves_its_own_entry_and_shows_it(fake_registry, i):
+    edit, page = panel_step("M", i, 3, "down")
     expected = list(THREE)
     expected[i], expected[i + 1] = expected[i + 1], expected[i]
-    assert widgets_after(edit) == expected
+    assert widgets_after(edit) == expected and page == f"panel:M:{i + 1}"
 
 
-def click_add(ed):
-    adder = ed.get_children()[-1]
-    next(c for c in adder.get_children() if isinstance(c, Gtk.Button)).clicked()
+@pytest.mark.parametrize("index, action", [(0, "up"), (2, "down"), (3, "remove"), (-1, "remove")])
+def test_nothing_to_do_is_none(index, action):
+    assert panel_step("M", index, 3, action) is None
 
 
-def test_add_panel_button_writes_the_edge_widgets_id_and_opens_it(make_config, fake_registry):
-    ed, edits = three_panel_editor(make_config)
-    ed.widget_choice.set_active_id("clock")
-    click_add(ed)
-    ((edit, open_index),) = edits
-    assert open_index == 3  # len(requests): the new entry opens
-    assert widgets_after(edit) == [*THREE, "clock"]
+def test_an_unknown_action_is_an_error():
+    with pytest.raises(ValueError, match="unknown panel action"):
+        panel_step("M", 0, 3, "sideways")
 
 
-def test_add_panel_button_writes_a_corner_widgets_id_not_its_label(make_config, corner_registry):
-    form = CORNER_FORM
-    ed, edits = three_panel_editor(make_config, form)
-    ed.widget_choice.set_active_id("box")
-    assert ed.widget_choice.get_active_text() == "Box"
-    click_add(ed)
-    ((edit, open_index),) = edits
-    assert open_index == 3
+def test_add_writes_the_widget_and_kind_with_a_free_name_and_shows_it(fake_registry):
+    edit, page = add_step("M", 3, "clock")
+    assert widgets_after(edit) == [*THREE, "clock"] and page == "panel:M:3"
     doc = UserDocument("")
-    edit(doc)
+    add_step("M", 0, "clock")[0](doc)
+    add_step("M", 1, "clock")[0](doc)
+    assert [p["name"] for p in doc.data["monitors"]["M"]["panels"]] == ["Clock", "Clock 2"]
+
+
+def test_add_writes_a_corner_widgets_id_and_kind(corner_registry):
+    doc = UserDocument("")
+    add_step("M", 0, "box", "corner")[0](doc)
     assert doc.data == {
         "monitors": {"M": {"panels": [{"panel": "corner", "name": "Box", "widget": "box"}]}}
     }
 
 
-def test_the_wheel_over_the_add_combo_does_not_change_the_choice(make_config, fake_registry):
-    from gi.repository import Gdk
-
-    ed, _ = three_panel_editor(make_config)
-    ed.widget_choice.set_active(0)
-    event = Gdk.Event.new(Gdk.EventType.SCROLL)
-    event.scroll.direction = Gdk.ScrollDirection.DOWN
-    ed.widget_choice.emit("scroll-event", event)
-    assert ed.widget_choice.get_active() == 0
-
-
 class TileProps(WidgetProps):
     size: int = 10
 
@@ -275,37 +126,19 @@ def tile(corner_registry):
     return corner_registry
 
 
-def test_titles_use_the_panel_name_and_a_widget_frame_shows_its_properties(make_config, tile):
+def test_titles_use_the_panel_name_and_a_two_kind_widget_gets_the_panel_type_row(make_config, tile):
     entries = [
         {"panel": "edge", "name": "Bottom dock", "widget": "dock"},
         {"panel": "corner", "name": "My tile", "widget": "tile", "corner": "top-left"},
     ]
-    config = make_config(monitors={"M": {"panels": entries}})
-    made = []
-
-    def make_rows(section, prefix):
-        made.append((section, prefix))
-        return Gtk.Box()
-
-    form = config_form(registry_widgets())
-    ed = panels.PanelEditor(form, "M", requests_for(config, "M"), make_rows, lambda *_a: None)
-    assert [e.get_label() for e in ed.expanders] == [
+    requests = requests_for(make_config(monitors={"M": {"panels": entries}}), "M")
+    assert [panel_title(i, r) for i, r in enumerate(requests)] == [
         "1. Bottom dock: bottom, center",
         "2. My tile: top-left, from top, 240x200",
     ]
-    (dock, p0), (tile_rows, p1), (widget, p2) = made
+    form = config_form(registry_widgets())
+    dock, tile_rows = (panel_section(form, r) for r in requests)
     assert "panel" not in [f.key for f in dock.fields]  # the dock has one kind
     kind = tile_rows.field("panel")  # the tile has two: the panel type row
     assert kind.choices == ("edge", "corner", "float") and kind.disabled == ("float",)
-    assert (widget.label, [f.key for f in widget.fields]) == ("Widget", ["size"])
-    assert p1 == p2 == ("monitors", "M", "panels", 1)  # widget keys sit in the entry itself
-    frames = [w for w in walk(ed.expanders[1]) if isinstance(w, Gtk.Frame)]
-    assert [f.get_label() for f in frames] == ["Widget"]
-    assert not [w for w in walk(ed.expanders[0]) if isinstance(w, Gtk.Frame)]
-
-
-def walk(widget):
-    yield widget
-    if isinstance(widget, Gtk.Container):
-        for child in widget.get_children():
-            yield from walk(child)
+    assert form.widget_props("tile").label == "Widget" and form.widget_props("dock") is None
diff --git a/tests/test_settings_toolbar.py b/tests/test_settings_toolbar.py
index 2dce4da..920a3db 100644
--- a/tests/test_settings_toolbar.py
+++ b/tests/test_settings_toolbar.py
@@ -96,3 +96,24 @@ def test_float_is_listed_but_cannot_be_chosen(toolbar):
 
 def test_the_add_button_keeps_the_focus_where_it_is(toolbar):
     assert not toolbar.add_button.get_focus_on_click()
+
+
+@pytest.mark.parametrize(
+    "panel, up, down, remove",
+    [
+        (None, False, False, False),  # a monitor page
+        ((0, 1), False, False, True),  # the only panel
+        ((0, 3), False, True, True),
+        ((1, 3), True, True, True),
+        ((2, 3), True, False, True),
+    ],
+)
+def test_the_panel_buttons_follow_the_panel_shown(panel, up, down, remove):
+    actions = []
+    t = ScreenToolbar(CHOICES, "KDE Plasma", lambda *_a: None, lambda *_a: None, actions.append)
+    t.show_screen("HDMI-A-1", "HDMI-A-1", "edge", panel)
+    sensitive = {a: b.get_sensitive() for a, b in t.panel_buttons.items()}
+    assert sensitive == {"up": up, "down": down, "remove": remove}
+    t.panel_buttons["remove"].clicked()
+    assert actions == ["remove"]  # the view checks that a panel page is shown
+    t.destroy()
diff --git a/tests/test_settings_view.py b/tests/test_settings_view.py
index 7ffa391..c752cb7 100644
--- a/tests/test_settings_view.py
+++ b/tests/test_settings_view.py
@@ -17,7 +17,8 @@ from gi.repository import Gdk, GLib, Gtk  # noqa: E402
 if not Gtk.init_check()[0]:
     pytest.skip("no display", allow_module_level=True)
 
-from settings.panels import PanelEditor  # noqa: E402
+from settings.form import AddChoice  # noqa: E402
+from settings.pages import panel_page  # noqa: E402
 from settings.screens import mode_of  # noqa: E402
 from settings.session import SettingsSession  # noqa: E402
 from settings.view import SettingsView  # noqa: E402
@@ -80,14 +81,29 @@ def walk(widget):
             yield from walk(child)
 
 
-def panel_editor(view, monitor="HDMI-A-1"):
-    page = view.stack.get_child_by_name(f"monitor:{monitor}")
-    return next(w for w in walk(page) if isinstance(w, PanelEditor))
+def add(view, widget, kind="edge", monitor="HDMI-A-1"):
+    """The toolbar's Add with this panel type chosen."""
+    view.add_panel(monitor, AddChoice(f"{kind}:{widget}", widget, kind, widget))
 
 
-def test_a_page_for_the_theme_and_each_monitor(make):
+def act(view, index, action, monitor="HDMI-A-1"):
+    """Move up, Move down or Remove on a panel (its tree row's buttons, or the toolbar's)."""
+    view.on_panel_action(panel_page(monitor, index), action)
+
+
+def shown(view):
+    return view.stack.get_visible_child_name()
+
+
+def title(view, entry=0, monitor="HDMI-A-1"):
+    """The heading of a panel's page (its tree row shows its name)."""
+    page = view.stack.get_child_by_name(panel_page(monitor, entry))
+    return next(w for w in walk(page) if isinstance(w, Gtk.Label)).get_text()
+
+
+def test_a_page_for_the_theme_each_monitor_and_each_panel(make):
     view, _ = make()
-    assert pages(view) == ["theme", "monitor:HDMI-A-1", "monitor:DP-1"]
+    assert pages(view) == ["theme", "monitor:HDMI-A-1", "panel:HDMI-A-1:0", "monitor:DP-1"]
     accent = row(view, ("theme", "accent")).editor.widget.get_rgba()
     assert accent.to_string() == "rgb(143,211,182)"
     assert shown_mode(view, "DP-1") == "plasma"  # not in the file: the default
@@ -96,7 +112,7 @@ def test_a_page_for_the_theme_and_each_monitor(make):
 
 def test_a_configured_monitor_that_is_not_connected_is_listed(make):
     view, _ = make(outputs=())
-    assert pages(view) == ["theme", "monitor:HDMI-A-1"]
+    assert pages(view) == ["theme", "monitor:HDMI-A-1", "panel:HDMI-A-1:0"]
 
 
 def test_a_valid_edit_is_written_and_shown(make):
@@ -142,26 +158,27 @@ def test_reset_removes_the_key(make, corner_registry):
 
 def test_adding_and_removing_panels_rebuilds_the_rows(make):
     view, path = make()
-    panel_editor(view).add("clock")
+    add(view, "clock")
     assert any(r.path[:4] == ("monitors", "HDMI-A-1", "panels", 1) for r in view.rows)
-    assert panel_editor(view).expanders[1].get_expanded()  # the new panel is open
-    panel_editor(view).remove(0)
+    assert shown(view) == "panel:HDMI-A-1:1" == view.tree.selected()  # the new panel's page
+    act(view, 0, "remove")
     assert path.read_text().count("[[monitors.HDMI-A-1.panels]]") == 1
     assert not any(r.path[:4] == ("monitors", "HDMI-A-1", "panels", 1) for r in view.rows)
+    assert shown(view) == "monitor:HDMI-A-1"  # after a remove: its monitor
 
 
-def test_changing_a_panel_edge_retitles_it_and_keeps_it_open(make):
+def test_changing_a_panel_edge_retitles_it_and_keeps_its_page(make):
     view, path = make()
+    view.show_page("panel:HDMI-A-1:0")
     view._on_change(("monitors", "HDMI-A-1", "panels", 0, "edge"), "top")
     drain()
-    expander = panel_editor(view).expanders[0]
-    assert expander.get_label() == "1. dock: top, center" and expander.get_expanded()
+    assert title(view) == "1. dock: top, center" and shown(view) == "panel:HDMI-A-1:0"
     assert 'edge = "top"' in path.read_text()
 
 
 def test_a_rejected_panel_edit_shows_in_the_banner(make):
     view, path = make()
-    panel_editor(view).add("nope")
+    add(view, "nope")
     assert "unknown widget" in view.banner_label.get_text() and view.banner.get_visible()
     assert path.read_text() == USER
 
@@ -220,10 +237,11 @@ def test_an_invalid_file_is_shown_read_only_with_its_error(make):
 
 def test_layout_warnings_are_previewed_for_connected_monitors(make):
     view, _ = make()
-    (preview,) = view.previews["HDMI-A-1"]  # on the monitor page
-    assert not preview.get_visible()
+    previews = view.previews["HDMI-A-1"]  # on the monitor page and on its panel's page
+    assert len(previews) == 2 and not any(p.get_visible() for p in previews)
     view._on_change(("monitors", "HDMI-A-1", "panels", 0, "length"), 3000)
-    assert preview.get_visible() and "monitors.HDMI-A-1" in preview.get_text()
+    for preview in previews:
+        assert preview.get_visible() and "monitors.HDMI-A-1" in preview.get_text()
 
 
 P0 = ("monitors", "HDMI-A-1", "panels", 0)
@@ -233,6 +251,7 @@ def test_a_dock_turned_into_a_corner_widget_is_one_edit(make, corner_registry):
     """Spec 19: the widget and the keys only the old kind takes change in ONE write (one
     reload); the entry then shows the corner rows, and its title follows."""
     view, path = make()
+    view.show_page("panel:HDMI-A-1:0")
     view._on_change((*P0, "align"), "end")
     drain()
     view._on_change((*P0, "widget"), "box")
@@ -246,9 +265,8 @@ def test_a_dock_turned_into_a_corner_widget_is_one_edit(make, corner_registry):
     )
     assert row(view, (*P0, "corner")).editor.widget.get_active_id() == "bottom-left"
     assert not any(r.path == (*P0, "align") for r in view.rows)
-    expander = panel_editor(view).expanders[0]
-    assert expander.get_label() == "1. dock: bottom-left, from bottom, 300x390"  # its name stays
-    assert expander.get_expanded()
+    assert title(view) == "1. dock: bottom-left, from bottom, 300x390"  # its name stays
+    assert shown(view) == "panel:HDMI-A-1:0"
 
 
 def test_a_new_corner_drops_an_edge_it_does_not_have(make, corner_registry):
@@ -314,11 +332,12 @@ def test_another_rows_apply_keeps_a_pending_spin_value(make, pending):
 
 def test_a_pending_value_is_written_before_a_panel_moves(make, pending):
     view, path = make()
-    panel_editor(view).add("clock")
+    add(view, "clock")
     row(view, DEPTH).editor.widget.set_value(120)  # on entry 0, the dock
-    panel_editor(view).move(0, 1)
+    act(view, 0, "down")
     entry = view.session.user["monitors"]["HDMI-A-1"]["panels"]
     assert [p["widget"] for p in entry] == ["clock", "dock"] and entry[1]["depth"] == 120
+    assert shown(view) == "panel:HDMI-A-1:1"  # the moved panel's page
 
 
 def test_a_pending_value_is_written_before_undo_and_revert(make, pending):
@@ -346,19 +365,16 @@ def edge_choices(view, entry=0):
     return [r[0] for r in combo.get_model()], combo.get_active_id()
 
 
-def title(view, entry=0):
-    return panel_editor(view).expanders[entry].get_label()
-
-
-def test_reset_of_a_title_key_retitles_the_panel_and_keeps_it_open(make, corner_registry):
+def test_reset_of_a_title_key_retitles_the_panel_and_keeps_its_page(make, corner_registry):
     view, _ = make()
+    view.show_page("panel:HDMI-A-1:0")
     plain = title(view)
     view._on_change((*P0, "edge"), "top")
     drain()
     assert title(view) != plain
     view._on_reset((*P0, "edge"))
     drain()
-    assert title(view) == plain and panel_editor(view).expanders[0].get_expanded()
+    assert title(view) == plain and shown(view) == "panel:HDMI-A-1:0"
 
     view._on_change((*P0, "widget"), "box")
     drain()
@@ -368,7 +384,7 @@ def test_reset_of_a_title_key_retitles_the_panel_and_keeps_it_open(make, corner_
     assert title(view) != boxed
     view._on_reset((*P0, "width"))
     drain()
-    assert title(view) == boxed and panel_editor(view).expanders[0].get_expanded()
+    assert title(view) == boxed and shown(view) == "panel:HDMI-A-1:0"
 
 
 def test_reset_of_a_corner_gives_the_edge_combo_the_default_corners_edges(make, corner_registry):
@@ -460,16 +476,13 @@ def test_a_banner_clears_after_undo(make):
     assert not view.banner.get_visible()
 
 
-def test_a_rejected_edit_leaves_no_panel_marked_to_open(make):
+def test_a_rejected_structural_edit_leaves_no_page_marked_to_show(make):
     view, _ = make()
-    view._on_change((*P0, "pos"), 400)
-    view._on_change((*P0, "align"), "end")  # a title key, rejected
-    drain()
-    assert view._expand == {}
-    panel_editor(view).add("nope")  # a structural edit, rejected
-    assert view._expand == {}
+    view.show_page("monitor:DP-1")
+    add(view, "nope")  # rejected: no panel 1 page to go to
+    assert view._select is None
     view.rebuild()
-    assert not panel_editor(view).expanders[0].get_expanded()
+    assert shown(view) == "monitor:DP-1"
 
 
 def test_the_invalid_file_banner_names_the_restore_command(make):
@@ -594,10 +607,10 @@ def test_a_flush_that_met_a_hand_edit_applies_no_further_row(make, pending):
 
 def test_a_structural_edit_after_a_refused_flush_is_not_applied(make, pending):
     view, path = make()
-    panel_editor(view).add("clock")
+    add(view, "clock")
     row(view, DEPTH).editor.widget.set_value(120)  # pending on the dock (entry 0)
     path.write_text(SWAPPED)  # by hand: the clock is entry 0 now
-    panel_editor(view).remove(1)  # the user meant the clock
+    act(view, 1, "remove")  # the user meant the clock
     assert path.read_text() == SWAPPED
     assert view.banner.get_visible() and "changed outside" in view.banner_label.get_text()
 
@@ -657,18 +670,20 @@ def tile_view(tmp_path, corner_registry):
     return SettingsView(SettingsSession(path), [HDMI]), path
 
 
-def test_renaming_a_panel_retitles_it_and_keeps_it_open(make):
+def test_renaming_a_panel_retitles_its_tree_row_and_page_and_keeps_it_shown(make):
     view, path = make()
+    view.tree.list.select_row(view.tree.row_of("panel:HDMI-A-1:0"))  # a click in the tree
     view._on_change((*P0, "name"), "Bottom dock")
     drain()
-    expander = panel_editor(view).expanders[0]
-    assert expander.get_label() == "1. Bottom dock: bottom, center" and expander.get_expanded()
+    assert title(view) == "1. Bottom dock: bottom, center"
+    assert view.tree.row_of("panel:HDMI-A-1:0").title == "Bottom dock"
+    assert shown(view) == "panel:HDMI-A-1:0" == view.tree.selected()
     assert 'name = "Bottom dock"' in path.read_text()
 
 
 def test_a_name_used_twice_is_not_written(make):
     view, path = make()
-    panel_editor(view).add("clock")  # a new panel named after the widget's title: "Clock"
+    add(view, "clock")  # a new panel named after the widget's title: "Clock"
     assert 'name = "Clock"' in path.read_text()
     name = ("monitors", "HDMI-A-1", "panels", 1, "name")
     view._on_change(name, "dock")
@@ -704,7 +719,7 @@ def test_the_panel_type_of_a_two_kind_widget_is_switched_in_one_write(tile_view)
     view._on_change((*P0, "panel"), "corner")
     drain()
     assert 'panel = "corner"' in path.read_text() and len(view.session.history) == 1
-    assert panel_editor(view).expanders[0].get_label() == "1. Tile: top-right, from top, 240x200"
+    assert title(view) == "1. Tile: top-right, from top, 240x200"
     view._on_change((*P0, "panel"), "float")  # listed, greyed out; refused if it gets through
     drain()
     assert "float panels are not implemented yet" in row(view, (*P0, "panel")).error.get_text()
@@ -721,8 +736,9 @@ def test_a_titled_change_from_a_focus_out_rebuilds_only_when_idle(make):
     """The name entry's focus-out runs before the click on Remove or Move is released: the
     rebuild waits for the loop, so that button is not unparented under the click."""
     view, path = make()
+    view.tree.select("panel:HDMI-A-1:0")
     entry = row(view, (*P0, "name")).editor.widget
-    remove_button = next(w for w in walk(panel_editor(view)) if isinstance(w, Gtk.Button))
+    remove_button = view.tree.row_of("panel:HDMI-A-1:0").buttons["remove"]
     entry.set_text("Bottom dock")
     entry.emit("focus-out-event", Gdk.Event.new(Gdk.EventType.FOCUS_CHANGE))
     assert 'name = "Bottom dock"' in path.read_text()  # written at once
@@ -730,7 +746,7 @@ def test_a_titled_change_from_a_focus_out_rebuilds_only_when_idle(make):
     assert entry.get_toplevel() is not entry and remove_button.get_parent() is not None
     drain()
     assert row(view, (*P0, "name")).editor.widget is not entry  # rebuilt once idle
-    assert panel_editor(view).expanders[0].get_label().startswith("1. Bottom dock")
+    assert title(view).startswith("1. Bottom dock")
 
 
 def test_a_rename_keeps_the_other_rows_pending_values(tile_view, pending):
@@ -784,18 +800,17 @@ def test_a_title_key_reset_applies_the_other_rows_pending_values_first(
     assert "thickness = 17" in text and "width = 350" not in text
 
 
-def test_the_panel_list_buttons_do_not_take_the_focus_on_click(make):
+def test_the_panel_buttons_do_not_take_the_focus_on_click(make):
     """A press on Remove, Move or Add must not move the focus out of the name entry: its
-    focus-out would rebuild the page before the click is released."""
+    focus-out would rebuild the pages before the click is released."""
     view, _ = make()
-    ours = ("Move up", "Move down", "Remove this panel")
+    ours = ("Move this panel up", "Move this panel down", "Remove this panel")
     buttons = [
         w
-        for w in walk(panel_editor(view))
-        if isinstance(w, Gtk.Button)
-        and (w.get_tooltip_text() in ours or w.get_label() == "Add panel")
+        for w in [*walk(view.tree), *walk(view.toolbar)]
+        if isinstance(w, Gtk.Button) and (w.get_tooltip_text() in ours or w.get_label() == "Add")
     ]
-    assert len(buttons) == 4 and not any(b.get_focus_on_click() for b in buttons)
+    assert len(buttons) == 7 and not any(b.get_focus_on_click() for b in buttons)
 
 
 def test_the_view_reports_every_change_of_state_including_a_save(make):
@@ -1109,9 +1124,88 @@ def test_add_puts_the_chosen_panel_on_the_selected_screen(make):
     view.toolbar.add_button.clicked()
     entries = view.session.user["monitors"]["HDMI-A-1"]["panels"]
     assert entries[-1] == {"panel": "edge", "name": "Clock", "widget": "clock"}
-    assert view.stack.get_visible_child_name() == "monitor:HDMI-A-1"
+    assert shown(view) == "panel:HDMI-A-1:1" == view.tree.selected()  # the new panel's page
+    assert ("panel:HDMI-A-1:1", "Clock") in view.tree.rows()
 
 
 def test_the_mode_row_left_the_monitor_page(make):
     view, _ = make()
     assert not any(r.path == SHELL for r in view.rows)
+
+
+# ---- panel pages ------------------------------------------------------------------------------
+
+
+def test_each_panel_is_a_tree_row_under_its_monitor_with_a_tabbed_page(make):
+    view, _ = make()
+    assert view.tree.rows()[1:3] == [("monitor:HDMI-A-1", "HDMI-A-1"), ("panel:HDMI-A-1:0", "dock")]
+    assert tabs(view, "panel:HDMI-A-1:0") == ["Panel", "Position", "Handle", "Interaction"]
+    assert title(view) == "1. dock: bottom, center"
+    assert not any(r.path == (*P0, "panel") for r in view.rows)  # the dock has one kind
+
+
+def test_a_widget_with_properties_gets_the_widget_tab(tile_view):
+    view, _ = tile_view
+    assert tabs(view, "panel:HDMI-A-1:0")[-1] == "Widget"
+    nb = notebook(view, "panel:HDMI-A-1:0")
+    widget_tab = nb.get_nth_page(tabs(view, "panel:HDMI-A-1:0").index("Widget"))
+    assert any(isinstance(w, Gtk.SpinButton) for w in walk(widget_tab))  # the size row
+    assert "Panel type" in texts(nb.get_nth_page(0))  # two kinds: the panel type row
+
+
+def test_a_titled_change_keeps_the_panels_tab(make):
+    view, _ = make()
+    click_row(view, "panel:HDMI-A-1:0")
+    show_tab(view, "panel:HDMI-A-1:0", "Position")
+    view._on_change((*P0, "edge"), "top")  # a title key: the pages are rebuilt
+    drain()
+    assert shown(view) == "panel:HDMI-A-1:0"
+    assert current_tab(view, "panel:HDMI-A-1:0") == "Position"
+
+
+def test_the_tree_rows_buttons_move_and_remove(make):
+    view, path = make()
+    add(view, "clock")  # entry 1, its page shown and its row selected
+    view.tree.row_of("panel:HDMI-A-1:1").buttons["up"].clicked()
+    assert [p["widget"] for p in view.session.user["monitors"]["HDMI-A-1"]["panels"]] == [
+        "clock",
+        "dock",
+    ]
+    assert shown(view) == "panel:HDMI-A-1:0" == view.tree.selected()
+    view.tree.row_of("panel:HDMI-A-1:0").buttons["remove"].clicked()
+    assert path.read_text().count("[[monitors.HDMI-A-1.panels]]") == 1
+    assert shown(view) == "monitor:HDMI-A-1"
+
+
+def test_the_toolbar_acts_on_the_panel_page_shown(make):
+    view, _ = make()
+    buttons = view.toolbar.panel_buttons
+    click_row(view, "monitor:HDMI-A-1")
+    assert not any(b.get_sensitive() for b in buttons.values())  # no panel page shown
+    add(view, "clock")
+    assert view.toolbar.screen == "HDMI-A-1"  # a panel page: its monitor
+    assert buttons["up"].get_sensitive() and not buttons["down"].get_sensitive()  # the last
+    buttons["up"].clicked()
+    assert shown(view) == "panel:HDMI-A-1:0"
+    assert not buttons["up"].get_sensitive() and buttons["down"].get_sensitive()
+    buttons["remove"].clicked()
+    assert [p["widget"] for p in view.session.user["monitors"]["HDMI-A-1"]["panels"]] == ["dock"]
+
+
+def test_an_add_refused_by_a_hand_edit_does_not_jump_to_another_panel(make):
+    """The hand edit added a panel 1 (the clock): the refused add must not show it as if it
+    were the new one."""
+    view, path = make()
+    click_row(view, "monitor:DP-1")
+    path.write_text(TWO_PANELS)  # by hand, not read yet
+    add(view, "bar")
+    assert "changed outside" in view.banner_label.get_text()
+    assert shown(view) == "monitor:DP-1"
+
+
+def test_undo_of_an_add_falls_back_to_the_monitor_page(make):
+    view, _ = make()
+    add(view, "clock")
+    view.undo()
+    assert pages(view) == ["theme", "monitor:HDMI-A-1", "panel:HDMI-A-1:0", "monitor:DP-1"]
+    assert shown(view) == "monitor:HDMI-A-1" == view.tree.selected()
```

- [ ] **Step 2: Run them to see them fail**

Run: `scripts/py -m pytest -q tests/test_settings_panels.py tests/test_settings_view.py tests/test_settings_toolbar.py`
Expected: `test_settings_panels.py`: `1 error` (`ImportError: cannot import name 'add_step'`); the view and toolbar files: `28 failed` (no panel pages, no `on_panel_action`, no `panel_buttons`).

- [ ] **Step 3: Implement:**

```diff
diff --git a/settings/panels.py b/settings/panels.py
index 29478ef..482780a 100644
--- a/settings/panels.py
+++ b/settings/panels.py
@@ -1,28 +1,23 @@
-"""GTK editor for one monitor's panel list: an expander per [[panels]] entry with its fields,
-plus add, remove and reorder buttons. Edge and corner panels (spec 19) share the list; each
-entry shows the rows of its kind, the panel type row when its widget can be shown in more than
-one kind, and a "Widget" frame with the widget's own properties (panel/widget spec 3.7).
-Structural edits go through `on_edit` (the window applies them with the session and rebuilds);
-field rows come from the window's `make_rows`."""
+"""A monitor's panels in the settings window: each entry's title and rows (edge and corner
+panels share the list, spec 19; a widget of several kinds gets the panel type row, panel/widget
+spec 3.7), and the structural edits the tree and the toolbar make (add, remove, move up or
+down) with the page to show after each. Pure: no GTK (settings.view builds the panel pages;
+the session applies the edits and the view rebuilds)."""
 
 from __future__ import annotations
 
 from collections.abc import Callable
 from typing import Any
 
-import gi
-
-gi.require_version("Gtk", "3.0")
-from gi.repository import Gtk
-
 from settings.document import UserDocument
-from settings.fields import wheel_scrolls_the_page
 from settings.form import ConfigForm, SectionSpec
+from settings.pages import monitor_page, panel_page
 from settings.values import new_panel_entry
 from shell.panel_spec import CornerRequest, PanelRequest
 from shell.registry import supported_kinds
 
 Edit = Callable[[UserDocument], Any]
+ACTIONS = ("up", "down", "remove")
 
 
 def panel_title(index: int, req: PanelRequest | CornerRequest) -> str:
@@ -42,84 +37,27 @@ def panel_section(form: ConfigForm, req: PanelRequest | CornerRequest) -> Sectio
     return form.panel_for(kind, corner, supported_kinds(req.widget))
 
 
-class PanelEditor(Gtk.Box):
-    def __init__(
-        self,
-        form: ConfigForm,
-        monitor: str,
-        requests: list[PanelRequest | CornerRequest],
-        make_rows: Callable[[SectionSpec, tuple], Gtk.Widget],
-        on_edit: Callable[[Edit, int | None], None],
-        expand: int | None = None,
-    ):
-        """`requests`: registry.requests_for(config, monitor), one per entry in config order.
-        `on_edit(edit, open_index)`: apply a structural edit, then show entry `open_index`
-        open (None: none). `expand`: the entry to show open now."""
-        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
-        self.monitor = monitor
-        self._on_edit = on_edit
-        self._count = len(requests)
-        self.expanders: list[Gtk.Expander] = []
-        last = len(requests) - 1
-        for i, req in enumerate(requests):
-            expander = Gtk.Expander(label=panel_title(i, req), expanded=i == expand)
-            body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_start=18)
-            buttons = Gtk.Box(spacing=6)
-            for icon, tip, sensitive, action in (
-                ("go-up-symbolic", "Move up", i > 0, lambda _b, i=i: self.move(i, i - 1)),
-                ("go-down-symbolic", "Move down", i < last, lambda _b, i=i: self.move(i, i + 1)),
-                ("list-remove-symbolic", "Remove this panel", True, lambda _b, i=i: self.remove(i)),
-            ):
-                button = Gtk.Button.new_from_icon_name(icon, Gtk.IconSize.BUTTON)
-                button.set_tooltip_text(tip)
-                button.set_sensitive(sensitive)
-                # a press must not move the focus: the name entry's focus-out would rebuild
-                # the page under the click
-                button.set_focus_on_click(False)
-                button.connect("clicked", action)
-                buttons.pack_start(button, False, False, 0)
-            body.pack_start(buttons, False, False, 0)
-            prefix = ("monitors", monitor, "panels", i)
-            body.pack_start(make_rows(panel_section(form, req), prefix), False, False, 0)
-            props = form.widget_props(req.widget)
-            if props is not None:  # the widget's own keys: in the same entry (same prefix)
-                frame = Gtk.Frame(label=props.label)
-                inner = make_rows(props, prefix)
-                inner.set_margin_start(8)
-                inner.set_margin_end(8)
-                inner.set_margin_bottom(8)
-                frame.add(inner)
-                body.pack_start(frame, False, False, 6)
-            expander.add(body)
-            self.expanders.append(expander)
-            self.pack_start(expander, False, False, 0)
-        adder = Gtk.Box(spacing=6)
-        self.widget_choice = Gtk.ComboBoxText()
-        widget = form.edge_panel.field("widget")
-        for name, label in zip(widget.choices, widget.labels or widget.choices, strict=True):
-            self.widget_choice.append(name, label)
-        self.widget_choice.set_active(0)
-        wheel_scrolls_the_page(self.widget_choice)
-        add = Gtk.Button(label="Add panel")
-        add.set_focus_on_click(False)
-        add.connect("clicked", lambda _b: self.add(self.widget_choice.get_active_id()))
-        adder.pack_start(self.widget_choice, False, False, 0)
-        adder.pack_start(add, False, False, 0)
-        self.pack_start(adder, False, False, 0)
+def add_step(monitor: str, count: int, widget: str, kind: str | None = None) -> tuple[Edit, str]:
+    """Add a panel of `widget` (as `kind`) after the `count` entries `monitor` has: the edit
+    (a free name, settings.values.new_panel_entry) and the new panel's page."""
+
+    def edit(doc: UserDocument) -> None:
+        doc.add_panel(monitor, new_panel_entry(doc.data, monitor, widget, kind))
 
-    def add(self, widget: str | None) -> None:
-        """A new entry with its widget's first kind, a name made from the widget's title that
-        is unique on this monitor, and the widget (a summary block's entry is {"panel":
-        "corner", "name": "Summary", "widget": "summary"}: its corner and size are the
-        widget's)."""
-        if widget:
-            self._on_edit(
-                lambda d: d.add_panel(self.monitor, new_panel_entry(d.data, self.monitor, widget)),
-                self._count,
-            )
+    return edit, panel_page(monitor, count)
 
-    def remove(self, index: int) -> None:
-        self._on_edit(lambda d: d.remove_panel(self.monitor, index), None)
 
-    def move(self, index: int, to: int) -> None:
-        self._on_edit(lambda d: d.move_panel(self.monitor, index, to), to)
+def panel_step(monitor: str, index: int, count: int, action: str) -> tuple[Edit, str] | None:
+    """Move entry `index` of `monitor`'s `count` up or down, or remove it: the edit and the page
+    to show after it (the moved panel's; after a remove, the monitor's). None when there is
+    nothing to do (the first panel up, the last one down, an index that is gone)."""
+    if not 0 <= index < count:
+        return None
+    if action == "remove":
+        return (lambda d: d.remove_panel(monitor, index)), monitor_page(monitor)
+    to = {"up": index - 1, "down": index + 1}.get(action)
+    if to is None:
+        raise ValueError(f"unknown panel action {action!r}")
+    if not 0 <= to < count:
+        return None
+    return (lambda d: d.move_panel(monitor, index, to)), panel_page(monitor, to)
diff --git a/settings/toolbar.py b/settings/toolbar.py
index 1ffc506..3eb1c6d 100644
--- a/settings/toolbar.py
+++ b/settings/toolbar.py
@@ -1,7 +1,8 @@
 """The per-screen toolbar (panel/widget spec 7): the selected screen's name; the checkboxes
 **Enable** (Edge Shell on this screen) and the native desktop (labelled with its name: KDE
 Plasma, Hyprland, ...), written together to the monitor's `shell` key (settings.screens); a
-one-line note that Edge Shell does not hide or show Plasma's panel yet; and the panel type list
+one-line note that Edge Shell does not hide or show Plasma's panel yet; Move up, Move down and
+Remove for the panel page shown (the selected tree row has the same three); and the panel type list
 (each widget by display name and panel kind, float listed and greyed out) with **Add**.
 
 It shows the screen of the selected page: a monitor page's, or a panel page's monitor. On the
@@ -20,6 +21,7 @@ from gi.repository import GLib, Gtk
 from settings.fields import ChoiceEditor
 from settings.form import MODE_HINTS, AddChoice
 from settings.screens import SHELL_NOTE, mode_flags, mode_of
+from settings.tree import PANEL_ACTIONS
 
 NO_SCREEN = "No screen selected"
 
@@ -31,13 +33,17 @@ class ScreenToolbar(Gtk.Box):
         native_label: str,
         on_mode: Callable[[str, str], None],
         on_add: Callable[[str, AddChoice], None],
+        on_panel: Callable[[str], None] | None = None,
     ):
         """`on_mode(screen, shell_value)`: a checkbox was toggled by the user.
-        `on_add(screen, choice)`: Add was pressed with an enabled panel type chosen."""
+        `on_add(screen, choice)`: Add was pressed with an enabled panel type chosen.
+        `on_panel(action)`: Move up, Move down or Remove ("up", "down", "remove") was pressed
+        while a panel page is shown (the view acts on that panel)."""
         super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
         self.set_property("margin", 6)
         self._on_mode = on_mode
         self._on_add = on_add
+        self._on_panel = on_panel or (lambda _action: None)
         self._quiet = False
         self.screen: str | None = None
         self.choices = {c.id: c for c in choices}
@@ -67,14 +73,36 @@ class ScreenToolbar(Gtk.Box):
         line.pack_start(self.native, False, False, 0)
         line.pack_end(self.add_button, False, False, 0)
         line.pack_end(self.kind.widget, False, False, 0)
+        # the same three as the selected tree row's buttons, for the panel page shown
+        self.panel_buttons: dict[str, Gtk.Button] = {}
+        for action, icon, tip in reversed(PANEL_ACTIONS):
+            button = Gtk.Button.new_from_icon_name(icon, Gtk.IconSize.BUTTON)
+            button.set_tooltip_text(tip)
+            button.set_focus_on_click(False)
+            button.connect("clicked", lambda _b, a=action: self._on_panel(a))
+            line.pack_end(button, False, False, 0)
+            self.panel_buttons[action] = button
         self.note = Gtk.Label(label=SHELL_NOTE, xalign=0, wrap=True)
         self.note.get_style_context().add_class("dim-label")
         self.pack_start(line, False, False, 0)
         self.pack_start(self.note, False, False, 0)
         self.show_screen(None)
 
-    def show_screen(self, screen: str | None, title: str = "", mode: str = "plasma") -> None:
-        """Show `screen` (its tree title, its `shell` value in effect), or no screen."""
+    def show_screen(
+        self,
+        screen: str | None,
+        title: str = "",
+        mode: str = "plasma",
+        panel: tuple[int, int] | None = None,
+    ) -> None:
+        """Show `screen` (its tree title, its `shell` value in effect), or no screen. `panel`:
+        (index, count) when a panel page of that screen is shown: Move up, Move down and
+        Remove then act on it (the first cannot move up, the last not down); else they are
+        insensitive."""
+        index, count = panel if panel is not None else (-1, 0)
+        self.panel_buttons["up"].set_sensitive(index > 0)
+        self.panel_buttons["down"].set_sensitive(0 <= index < count - 1)
+        self.panel_buttons["remove"].set_sensitive(index >= 0)
         self.screen = screen
         self._quiet = True
         try:
diff --git a/settings/view.py b/settings/view.py
index 888acb4..5aa4471 100644
--- a/settings/view.py
+++ b/settings/view.py
@@ -17,7 +17,6 @@ the running shell reloads it; an invalid one is shown under its row and not writ
 from __future__ import annotations
 
 from collections.abc import Callable
-from dataclasses import replace
 from typing import Any
 
 import gi
@@ -34,6 +33,7 @@ from settings.form import (
     TabSpec,
     add_choices,
     config_form,
+    panel_tabs,
     registry_widgets,
     theme_tabs,
 )
@@ -42,25 +42,26 @@ from settings.pages import (
     THEME,
     fallback_page,
     monitor_page,
+    panel_page,
     parse_page,
     screen_of,
     tree_entries,
 )
-from settings.panels import PanelEditor
+from settings.panels import add_step, panel_section, panel_step, panel_title
 from settings.queue import RESET, EditQueue, QueuedEdit, describe, path_text
 from settings.screens import desktop_label
 from settings.session import ChangedOutside, SettingsSession, check_text
 from settings.toolbar import ScreenToolbar
 from settings.tree import SettingsTree
-from settings.values import field_value, layout_preview, lookup, new_panel_entry, panel_ops
+from settings.values import field_value, layout_preview, lookup, panel_ops
 from shell.config.models import ConfigError
 from shell.outputs import Output
 from shell.registry import requests_for
 
 Edit = Callable[[UserDocument], Any]
-# shown in a panel's expander title (panel_title), or deciding its rows (widget: the kind
-# and the Widget rows; panel: the kind's rows; corner: the edge choices): a change rebuilds
-# the page and keeps that panel open
+# shown in a panel's tree row and page heading (panel_title), or deciding its rows (widget:
+# the kind and the Widget tab; panel: the kind's rows; corner: the edge choices): a change
+# rebuilds the pages (the panel's page stays shown)
 TITLE_KEYS = ("name", "widget", "panel", "edge", "align", "corner", "width", "height")
 
 
@@ -86,9 +87,9 @@ class SettingsView(Gtk.Box):
         widgets = registry_widgets()
         self.form = config_form(widgets)
         self.rows: list[FieldRow] = []
-        # monitor -> the labels showing its layout warnings (its page; later its panels' pages)
+        # monitor -> the labels showing its layout warnings (its page and its panels' pages)
         self.previews: dict[str, list[Gtk.Label]] = {}
-        self._expand: dict[str, int] = {}  # monitor -> panel entry to show open after a rebuild
+        self._select: str | None = None  # the page to show after the next rebuild (an add, ...)
         self._tab_of: dict[str, str] = {}  # page -> the title of the tab last shown on it
         self.save_failed = False  # the last flush() could not write something (shown on screen)
         # the last flush() met a hand edit: that row and the rest were not applied (warning on
@@ -102,14 +103,18 @@ class SettingsView(Gtk.Box):
 
         # Undo and Revert all are in the Edit menu (and Ctrl+Z); the file is in the title
         self.toolbar = ScreenToolbar(
-            add_choices(widgets), desktop or desktop_label(), self._on_mode, self.add_panel
+            add_choices(widgets),
+            desktop or desktop_label(),
+            self._on_mode,
+            self.add_panel,
+            lambda action: self.on_panel_action(self.stack.get_visible_child_name(), action),
         )
         self.banner = Gtk.InfoBar()
         self.banner_label = Gtk.Label(xalign=0, wrap=True, selectable=True)
         self.banner.get_content_area().add(self.banner_label)
         self.banner.set_no_show_all(True)
         self.stack = Gtk.Stack()
-        self.tree = SettingsTree(self.show_page)
+        self.tree = SettingsTree(self.show_page, self.on_panel_action)
         self.tree.set_property("margin", 6)
         body = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
         body.pack1(self.tree, False, False)  # never narrower than its MIN_WIDTH
@@ -140,7 +145,8 @@ class SettingsView(Gtk.Box):
             self._run_queue()
             return
         self.cancel_deferred_rebuild()  # overtaken by this one
-        visible = self.stack.get_visible_child_name()
+        visible = self._select or self.stack.get_visible_child_name()
+        self._select = None
         window = self.get_toplevel()
         focus = window.get_focus() if isinstance(window, Gtk.Window) else None
         if focus is not None and focus.is_ancestor(self.stack):
@@ -163,11 +169,12 @@ class SettingsView(Gtk.Box):
         for entry in entries[1:]:
             name = parse_page(entry.page).monitor
             self._add_page(entry.page, self._monitor_page(name, entry.title), True)
+            for i, req in enumerate(requests_for(self.config, name)):
+                self._add_page(panel_page(name, i), self._panel_page(name, i, req), True)
         self.stack.show_all()
         page = self._page_to_show(visible)
         self.stack.set_visible_child_name(page)
-        # the panel rows come with the panel pages
-        self.tree.show(tuple(replace(e, children=()) for e in entries))
+        self.tree.show(entries)
         self.tree.select(page)
         if valid:
             self.refresh()
@@ -185,13 +192,17 @@ class SettingsView(Gtk.Box):
     def _sync_toolbar(self) -> None:
         """The toolbar shows the screen of the page shown (a monitor page's, a panel page's
         monitor) with its `shell` value in effect; none on the Theme page or while the file is
-        invalid."""
-        screen = screen_of(self.stack.get_visible_child_name())
+        invalid. On a panel page its Move up, Move down and Remove act on that panel."""
+        page = self.stack.get_visible_child_name()
+        screen = screen_of(page)
         if screen is None or self.session.config is None:
             self.toolbar.show_screen(None)
             return
         title = screen if screen in self.outputs else screen + NOT_CONNECTED
-        self.toolbar.show_screen(screen, title, self.config.monitor(screen).shell)
+        monitor = self.config.monitor(screen)
+        index = parse_page(page).index
+        panel = None if index is None else (index, len(monitor.panels))
+        self.toolbar.show_screen(screen, title, monitor.shell, panel)
 
     def _page_to_show(self, wanted: str | None) -> str:
         """`wanted` if it is still a page; else its fallback (a gone panel's monitor), else the
@@ -217,12 +228,11 @@ class SettingsView(Gtk.Box):
         top: list[Gtk.Widget],
         tabs: tuple[TabSpec, ...],
         prefix: tuple,
-        extra: tuple[tuple[str, Gtk.Widget], ...] = (),
     ) -> Gtk.Widget:
-        """A page: `top` (its heading, a banner) above a notebook with one tab per TabSpec
-        (then the `extra` tabs, (title, content)), each tab scrolled on its own. A tab's later
-        parts get a heading of their own (the Handle tab: the handle colours, then "Handle
-        style"). The tab last shown on `page` is shown again."""
+        """A page: `top` (its heading, a banner) above a notebook with one tab per TabSpec,
+        each tab scrolled on its own. A tab's later parts get a heading of their own (the
+        Handle tab: the handle colours, then "Handle style"). The tab last shown on `page` is
+        shown again."""
         box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
         box.set_margin_start(16)
         box.set_margin_end(16)
@@ -239,8 +249,6 @@ class SettingsView(Gtk.Box):
                     content.pack_start(self._heading(section.label), False, False, 6)
                 content.pack_start(self.section_rows(section, (*prefix, *key)), False, False, 0)
             self._add_tab(notebook, tab.title, content)
-        for title, content in extra:
-            self._add_tab(notebook, title, content)
         box.pack_start(notebook, True, True, 0)
         self._keep_tab(page, notebook)
         return box
@@ -312,20 +320,15 @@ class SettingsView(Gtk.Box):
         banner = Gtk.InfoBar(message_type=Gtk.MessageType.INFO)
         banner.get_content_area().add(Gtk.Label(label=override_text(name), xalign=0, wrap=True))
         top = [self._heading(title), banner, self._preview(name)]
-        # until the panel pages take it over: the panel list
-        panels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
-        panels.set_property("margin", 12)
-        editor = PanelEditor(
-            self.form,
-            name,
-            requests_for(self.config, name),
-            self.section_rows,
-            lambda edit, expand, n=name: self._structural(n, edit, expand),
-            self._expand.pop(name, None),
-        )
-        panels.pack_start(editor, False, False, 0)
-        tabs = theme_tabs(self.form)
-        return self._tabbed(monitor_page(name), top, tabs, prefix, (("Panels", panels),))
+        return self._tabbed(monitor_page(name), top, theme_tabs(self.form), prefix)
+
+    def _panel_page(self, name: str, index: int, req) -> Gtk.Widget:
+        """A panel's page: its title ("1. Dock: bottom, center") and the layout warnings of
+        its monitor above the tabs Panel, Position, Handle, Interaction and, when its widget
+        has properties, Widget (settings.form.panel_tabs); every row is a key of the entry."""
+        top = [self._heading(panel_title(index, req)), self._preview(name)]
+        tabs = panel_tabs(panel_section(self.form, req), self.form.widget_props(req.widget))
+        return self._tabbed(panel_page(name, index), top, tabs, ("monitors", name, "panels", index))
 
     # ---- showing values ------------------------------------------------------------------
     def refresh(self) -> None:
@@ -368,6 +371,7 @@ class SettingsView(Gtk.Box):
             self.session.apply(edit)
         except ChangedOutside as exc:
             self.refused_outside = True
+            self._select = None  # a page picked for the old file could be another panel now
             self._rebuild_soon()
             self.show_banner(str(exc), Gtk.MessageType.WARNING)
             return False
@@ -481,10 +485,7 @@ class SettingsView(Gtk.Box):
             edit = lambda d: d.unset(path)  # noqa: E731
         else:
             edit = lambda d: d.set(path, value)  # noqa: E731
-        if titled:
-            self._expand[path[1]] = path[3]  # keep that panel open
-        if not self.apply(edit, self._row(path), structural=titled):
-            self._expand.pop(path[1], None)
+        self.apply(edit, self._row(path), structural=titled)  # the shown page stays (by name)
 
     def _tell_dropped(self, dropped: list[QueuedEdit], typed: list[tuple]) -> None:
         """Add to the banner what was not applied because the file changed outside this
@@ -506,16 +507,28 @@ class SettingsView(Gtk.Box):
         for row in self.rows:
             row.discard()
 
-    def _structural(self, monitor: str, edit: Edit, expand: int | None) -> None:
+    def _structural(self, edit: Edit, show: str) -> None:
         """A panel added, removed or moved: row indexes change, so rebuild (never refresh
-        rows that may point at an entry that is gone). `expand`: the entry to show open."""
-        self.flush()  # pending values go to the row indexes they were typed for, before they move
+        rows that may point at an entry that is gone), then show the page `show`. A barrier:
+        the queue is applied first, to the indexes its edits were made for."""
+        self.flush()
         if self.refused_outside:
             return  # the file was re-read: these row indexes may mean other panels now
-        if expand is not None:
-            self._expand[monitor] = expand
+        self._select = show
         if not self.apply(edit, structural=True):
-            self._expand.pop(monitor, None)
+            self._select = None
+
+    def on_panel_action(self, page: str, action: str) -> None:
+        """Move up, Move down or Remove, from a tree row's buttons or the toolbar, on the panel
+        of `page` (nothing on another page)."""
+        ref = parse_page(page)
+        if ref.kind != "panel":
+            return
+        step = panel_step(
+            ref.monitor, ref.index, len(self.config.monitor(ref.monitor).panels), action
+        )
+        if step is not None:
+            self._structural(*step)
 
     def _on_mode(self, screen: str, mode: str) -> None:
         """A toolbar checkbox: write `shell` (an error goes to the banner); the checkboxes
@@ -525,13 +538,9 @@ class SettingsView(Gtk.Box):
 
     def add_panel(self, screen: str, choice: AddChoice) -> None:
         """The toolbar's Add: a new entry of the chosen widget and kind with a free name
-        (settings.values.new_panel_entry), shown open."""
+        (settings.values.new_panel_entry); its page is shown."""
         count = len(self.config.monitor(screen).panels)
-
-        def edit(doc: UserDocument) -> None:
-            doc.add_panel(screen, new_panel_entry(doc.data, screen, choice.widget, choice.kind))
-
-        self._structural(screen, edit, count)
+        self._structural(*add_step(screen, count, choice.widget, choice.kind))
 
     def _row(self, path: tuple) -> FieldRow | None:
         return next((r for r in self.rows if r.path == path), None)
```

- [ ] **Step 4: Run them to see them pass**

Run: `scripts/py -m pytest -q tests/test_settings_panels.py tests/test_settings_view.py tests/test_settings_toolbar.py tests/test_settings_controller.py tests/test_settings_app.py`
Expected: all pass.

- [ ] **Step 5: VERIFY**

Run: `scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q`
Expected: `All checks passed!`, `2495 passed`.

**Reviewer mutations:** `self._select = None` removed from `apply`'s `ChangedOutside` branch (run on the prototype: `test_an_add_refused_by_a_hand_edit_does_not_jump_to_another_panel` fails; it was a survivor before that test was written); `panel_step` without the `0 <= index < count` check (run: 2 failed, `test_nothing_to_do_is_none`); `_structural` setting `_select` after `apply` (`test_adding_and_removing_panels_rebuilds_the_rows`); the remove step showing the next panel instead of the monitor (`test_remove_takes_out_its_own_entry_and_shows_the_monitor`); `rebuild` using `visible` before `_select` (`test_the_tree_rows_buttons_move_and_remove`); `_sync_toolbar` passing no `panel` (`test_the_toolbar_acts_on_the_panel_page_shown`); `on_panel_action` acting on a monitor page (the toolbar's Remove on a monitor page: reviewer reads it; `parse_page(...).kind != "panel"` returns); the panel page built at the monitor's prefix (`test_a_widget_with_properties_gets_the_widget_tab`); the Widget tab always added (`test_each_panel_is_a_tree_row_under_its_monitor_with_a_tabbed_page`); `name` taken out of `TITLE_KEYS` (`test_renaming_a_panel_retitles_its_tree_row_and_page_and_keeps_it_shown`).

- [ ] **Step 6: Commit**

```bash
git add settings/panels.py settings/view.py settings/toolbar.py tests/test_settings_panels.py tests/test_settings_view.py tests/test_settings_toolbar.py
git commit -m "feat(settings): a tabbed page per panel; move, remove and rename from the tree and toolbar" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 9: Detect monitors and the no-monitor state

**Files:**
- Modify: `settings/view.py` (`detect=` parameter, `detect_monitors`, the button wired), `settings/pages.py` (`tree_entries` marks with `shell.monitor_check.unknown_monitors`), `settings/controller.py` (`_drop_view` keeps `view.outputs`)
- Test: `tests/test_settings_view.py` (5 new), `tests/test_settings_controller.py` (1 new)

**Interfaces:**
- Consumes: Task 2 (`detect_outputs`, `DetectError`), Task 3 (`monitor_report`, `unknown_monitors`), Task 4 (`flush` as the barrier), Task 5 (`detect_button`, `hint`).
- Produces: `SettingsView(session, outputs, confirm_revert=None, on_state=None, desktop=None, detect: Callable[[], list[Output]] | None = None)`, `SettingsView.detect_monitors() -> None`, `SettingsView._detect`.

- [ ] **Step 1: Write the failing tests:**

```diff
diff --git a/tests/test_settings_controller.py b/tests/test_settings_controller.py
index 7a1234c..439a724 100644
--- a/tests/test_settings_controller.py
+++ b/tests/test_settings_controller.py
@@ -370,6 +370,18 @@ def test_close_shows_the_empty_page_where_only_new_open_and_exit_work(make):
     assert c.view is None
 
 
+def test_detected_monitors_stay_after_close_and_reopen(make):
+    from shell.outputs import Output
+
+    c, _ = make()
+    c.view._detect = lambda: [Output("DP-1", 0, 0, 1920, 1080)]
+    c.view.detect_monitors()
+    run(c, "close")
+    c.reopen()
+    assert ("monitor:DP-1", "DP-1") in c.view.tree.rows()
+    assert ("monitor:HDMI-A-1", "HDMI-A-1 (not connected)") in c.view.tree.rows()
+
+
 def test_closing_retires_the_view(make, pending):
     c, path = make()
     view = c.view
diff --git a/tests/test_settings_view.py b/tests/test_settings_view.py
index c752cb7..3f5cd81 100644
--- a/tests/test_settings_view.py
+++ b/tests/test_settings_view.py
@@ -1209,3 +1209,81 @@ def test_undo_of_an_add_falls_back_to_the_monitor_page(make):
     view.undo()
     assert pages(view) == ["theme", "monitor:HDMI-A-1", "panel:HDMI-A-1:0", "monitor:DP-1"]
     assert shown(view) == "monitor:HDMI-A-1" == view.tree.selected()
+
+
+# ---- Detect monitors --------------------------------------------------------------------------
+
+HDMI2 = Output("HDMI-A-2", 1920, 0, 2560, 1440)
+
+
+def detect_view(path, outputs, found):
+    """A view whose Detect monitors finds `found` (a list, or an exception to raise)."""
+
+    def detect():
+        if isinstance(found, Exception):
+            raise found
+        return list(found)
+
+    return SettingsView(SettingsSession(path), list(outputs), detect=detect)
+
+
+def test_detect_lists_the_connected_monitors_with_the_configured_ones(tmp_path, fake_registry):
+    path = tmp_path / "config.toml"
+    path.write_text(USER)
+    view = detect_view(path, [], [HDMI, HDMI2])
+    assert [t for _p, t in view.tree.rows()] == ["Theme", "HDMI-A-1 (not connected)", "dock"]
+    view.tree.detect_button.clicked()
+    assert [p for p, _t in view.tree.rows()] == [
+        "theme",
+        "monitor:HDMI-A-1",
+        "panel:HDMI-A-1:0",
+        "monitor:HDMI-A-2",  # connected, not in the config: listed, nothing written
+    ]
+    assert view.banner_label.get_text() == "Connected monitors: HDMI-A-1, HDMI-A-2."
+    assert path.read_text() == USER
+
+
+def test_detect_names_a_configured_monitor_that_is_not_connected(tmp_path, fake_registry):
+    path = tmp_path / "config.toml"
+    path.write_text(USER)
+    view = detect_view(path, [HDMI], [DP])
+    view.tree.detect_button.clicked()
+    assert ("monitor:HDMI-A-1", "HDMI-A-1 (not connected)") in view.tree.rows()
+    text = view.banner_label.get_text()
+    assert "config monitors: HDMI-A-1; connected: DP-1" in text
+    assert view.banner.get_message_type() == Gtk.MessageType.WARNING
+
+
+def test_a_failed_detection_keeps_the_list(tmp_path, fake_registry):
+    from settings.screens import DetectError
+
+    path = tmp_path / "config.toml"
+    path.write_text(USER)
+    view = detect_view(path, [HDMI, DP], DetectError("kscreen-doctor failed: timed out"))
+    rows = view.tree.rows()
+    view.tree.detect_button.clicked()
+    assert view.tree.rows() == rows and set(view.outputs) == {"HDMI-A-1", "DP-1"}
+    assert "kscreen-doctor failed: timed out; the monitor list is unchanged" in (
+        view.banner_label.get_text()
+    )
+
+
+def test_detect_applies_the_queue_first_and_keeps_the_page(tmp_path, fake_registry, pending):
+    path = tmp_path / "config.toml"
+    path.write_text(USER)
+    view = detect_view(path, [HDMI], [HDMI, DP])
+    view.show_page("panel:HDMI-A-1:0")
+    row(view, DEPTH).editor.widget.set_value(120)  # inside the pause
+    view.detect_monitors()
+    assert "depth = 120" in path.read_text()
+    assert shown(view) == "panel:HDMI-A-1:0"
+
+
+def test_no_monitor_at_all_says_how_to_find_one(tmp_path, fake_registry):
+    path = tmp_path / "config.toml"
+    path.write_text("# empty\n")
+    view = detect_view(path, [], [])
+    assert view.tree.rows() == [("theme", "Theme")] and view.tree.hint.get_visible()
+    assert view.toolbar.screen is None
+    view.tree.detect_button.clicked()
+    assert view.banner_label.get_text() == "Connected monitors: none."
```

- [ ] **Step 2: Run them to see them fail**

Run: `scripts/py -m pytest -q tests/test_settings_view.py tests/test_settings_controller.py`
Expected: `6 failed` (`SettingsView()` takes no `detect`; no `detect_monitors`).

- [ ] **Step 3: Implement:**

```diff
diff --git a/settings/controller.py b/settings/controller.py
index c9d18e3..ab0f59c 100644
--- a/settings/controller.py
+++ b/settings/controller.py
@@ -149,6 +149,7 @@ class SettingsController(Gtk.Box):
         view, self.view, self.session = self.view, None, None
         if view is not None:
             view.retire()  # no queue timer or idle rebuild may run on a view that is gone
+            self.outputs = list(view.outputs.values())  # what Detect monitors found last
             self.body.remove(view)
             # destroyed when idle: an action can run inside a signal of a widget of this view
             GLib.idle_add(lambda: view.destroy() or GLib.SOURCE_REMOVE)
diff --git a/settings/pages.py b/settings/pages.py
index 0a97098..548fa7d 100644
--- a/settings/pages.py
+++ b/settings/pages.py
@@ -14,6 +14,7 @@ from dataclasses import dataclass
 
 from settings.values import monitor_names
 from shell.config.models import Config
+from shell.monitor_check import unknown_monitors
 from shell.outputs import Output
 
 THEME = "theme"
@@ -78,11 +79,13 @@ def tree_entries(config: Config | None, outputs: list[Output]) -> tuple[TreeEntr
     entries = [TreeEntry(THEME, "Theme")]
     if config is None:
         return tuple(entries)
-    for name, connected in monitor_names(config, outputs):
+    # the shell's own comparison (shell.monitor_check): a configured name not connected
+    unknown = set(unknown_monitors(config.monitors, [o.name for o in outputs]))
+    for name, _connected in monitor_names(config, outputs):
         panels = tuple(
             TreeEntry(panel_page(name, i), entry.name)
             for i, entry in enumerate(config.monitor(name).panels)
         )
-        title = name if connected else name + NOT_CONNECTED
+        title = name + NOT_CONNECTED if name in unknown else name
         entries.append(TreeEntry(monitor_page(name), title, panels))
     return tuple(entries)
diff --git a/settings/view.py b/settings/view.py
index 5aa4471..e60bd0b 100644
--- a/settings/view.py
+++ b/settings/view.py
@@ -49,12 +49,13 @@ from settings.pages import (
 )
 from settings.panels import add_step, panel_section, panel_step, panel_title
 from settings.queue import RESET, EditQueue, QueuedEdit, describe, path_text
-from settings.screens import desktop_label
+from settings.screens import DetectError, desktop_label, detect_outputs
 from settings.session import ChangedOutside, SettingsSession, check_text
 from settings.toolbar import ScreenToolbar
 from settings.tree import SettingsTree
 from settings.values import field_value, layout_preview, lookup, panel_ops
 from shell.config.models import ConfigError
+from shell.monitor_check import monitor_report
 from shell.outputs import Output
 from shell.registry import requests_for
 
@@ -73,9 +74,11 @@ class SettingsView(Gtk.Box):
         confirm_revert: Callable[[Any, str], bool] | None = None,
         on_state: Callable[[], None] | None = None,
         desktop: str | None = None,
+        detect: Callable[[], list[Output]] | None = None,
     ):
         """`desktop`: the native desktop checkbox's label (None: from XDG_CURRENT_DESKTOP,
-        settings.screens.desktop_label)."""
+        settings.screens.desktop_label). `detect`: Detect monitors' reader (None:
+        kscreen-doctor, settings.screens.detect_outputs; tests pass a fake)."""
         super().__init__(orientation=Gtk.Orientation.VERTICAL)
         self.session = session
         # asks before Revert all (parent, text) -> OK?; tests pass a fake, no dialog runs
@@ -84,6 +87,7 @@ class SettingsView(Gtk.Box):
         # window updates its menu items and title
         self._on_state = on_state or (lambda: None)
         self.outputs = {o.name: o for o in outputs}
+        self._detect = detect or detect_outputs
         widgets = registry_widgets()
         self.form = config_form(widgets)
         self.rows: list[FieldRow] = []
@@ -116,6 +120,7 @@ class SettingsView(Gtk.Box):
         self.stack = Gtk.Stack()
         self.tree = SettingsTree(self.show_page, self.on_panel_action)
         self.tree.set_property("margin", 6)
+        self.tree.detect_button.connect("clicked", lambda _b: self.detect_monitors())
         body = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
         body.pack1(self.tree, False, False)  # never narrower than its MIN_WIDTH
         body.pack2(self.stack, True, False)
@@ -497,6 +502,35 @@ class SettingsView(Gtk.Box):
             note = "Not applied (made for the file before it changed): " + ", ".join(parts)
             self.show_banner(f"{text}\n{note}" if text else note, Gtk.MessageType.WARNING)
 
+    def detect_monitors(self) -> None:
+        """Detect monitors: ask kscreen-doctor again and list the connected monitors with the
+        ones in the config (a barrier: queued edits are applied first). The banner names the
+        connected monitors and, when the config names one that is not connected, the names to
+        use instead (shell.monitor_check, the same text as the shell's warning). A failure
+        keeps the list as it was."""
+        self.flush()
+        if self.refused_outside:
+            return
+        try:
+            outputs = self._detect()
+        except DetectError as exc:
+            self.show_banner(f"{exc}; the monitor list is unchanged", Gtk.MessageType.WARNING)
+            return
+        self.outputs = {o.name: o for o in outputs}
+        self.rebuild()
+        if self.session.config is None:
+            return  # the invalid-file banner stays
+        report = monitor_report(self.config.monitors, self.outputs)
+        found = ", ".join(self.outputs) or "none"
+        if report is None:
+            self.show_banner(f"Connected monitors: {found}.", Gtk.MessageType.INFO)
+        else:
+            self.show_banner(
+                f"Monitors in the config that are not connected ({report}): use the connected "
+                "names in the config.",
+                Gtk.MessageType.WARNING,
+            )
+
     def retire(self) -> None:
         """The view is going (File > Close, Open, New): no timer or idle rebuild may run on
         it later. Its queue was applied by the leave question's flush; anything left is
```

- [ ] **Step 4: Run them to see them pass**

Run: `scripts/py -m pytest -q tests/test_settings_view.py tests/test_settings_controller.py tests/test_settings_pages.py`
Expected: all pass.

- [ ] **Step 5: VERIFY**

Run: `scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q`
Expected: `All checks passed!`, `2501 passed`.

**Reviewer mutations:** `detect_monitors` without `flush()` (`test_detect_applies_the_queue_first_and_keeps_the_page`); the outputs replaced before the detection succeeded (`test_a_failed_detection_keeps_the_list`); the report banner as INFO (`test_detect_names_a_configured_monitor_that_is_not_connected` checks WARNING); `_drop_view` not keeping `view.outputs` (`test_detected_monitors_stay_after_close_and_reopen`); the detect button not connected (`test_detect_lists_the_connected_monitors_with_the_configured_ones` clicks it); `tree_entries` marking every monitor not connected when the outputs are empty: unchanged behaviour, pinned by `test_with_nothing_detected_the_configured_monitors_are_listed` (Task 2).

- [ ] **Step 6: Commit**

```bash
git add settings/view.py settings/pages.py settings/controller.py tests/test_settings_view.py tests/test_settings_controller.py
git commit -m "feat(settings): Detect monitors and the no-monitor state" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 10: README, spec, docstring, gate example and checklist

**Files:**
- Modify: `README.md`, `settings/__init__.py` (docstring), `examples/settings-test.toml` (header comment), `docs/superpowers/specs/2026-10-14-panel-widget-model-design.md` (section 7)

**Interfaces:** none (docs). The suite total stays `2501 passed`.

- [ ] **Step 1: `settings/__init__.py`** — replace the docstring with:

```python
"""The Edge Shell settings window (spec 13). Pure modules: form, values, files, document,
session, menus, fileops, about, launch, pages, screens, queue, panels. GTK modules: fields,
tree, toolbar, view, dialogs, menubar, controller, window, app."""
```

- [ ] **Step 2: `examples/settings-test.toml`** — after the line `# Open steps write only under /tmp/edge-menus/.` add:

```toml
# The tree gate (plan 2026-10-15-settings-tree.md) uses a copy at /tmp/edge-tree/config.toml;
# it changes HDMI-A-1 only.
```

(`tests/test_settings_example.py` still passes: only comments change.)

- [ ] **Step 3: `README.md`.**
  - In the plan list, after `- [Settings menus plan](docs/superpowers/plans/2026-10-15-settings-menus.md)` add `- [Settings tree plan](docs/superpowers/plans/2026-10-15-settings-tree.md)`.
  - In "### Settings window", in the **Menus** bullet, replace "The Undo and Revert all buttons stay above the pages. Ctrl+Z" with "Ctrl+Z".
  - Replace the three bullets from "- **Theme** page: every theme key, ..." up to and including "... A name already used on the monitor is refused under the\n  Name row." with:

```markdown
- **Layout.** A toolbar for the selected screen, a tree on the left (at least 200 px wide;
  drag the divider to widen it) and the selected page on the right. The tree lists **Theme**
  and every monitor (connected ones, and the ones in your config: "(not connected)" when the
  config names a monitor that is not there); a monitor's panels are listed under it by name
  (the arrow, or Left and Right, shows and hides them). **Detect monitors** above the tree
  asks `kscreen-doctor` again and says which monitors are connected, or which names in your
  config are not and which to use instead.
- **Toolbar** (the screen of the page shown: a monitor, or a panel's monitor; nothing on the
  Theme page): the screen's name, **Enable** (Edge Shell on this screen) and a checkbox named
  after your desktop (**KDE Plasma**, **Hyprland**, ...; "Native desktop" when it is not
  known). Together they set the monitor's `shell`: Enable only = `edge`, the desktop only =
  `plasma`, both = `both`, neither = `none`. Edge Shell does not hide or show Plasma's panel
  yet, so `edge` and `both` look the same today (the note under the checkboxes says so; with
  both on, keep the bottom edge free of Edge Shell panels). Then Move up, Move down and Remove
  for the panel page shown, and the panel type list with **Add**: every widget by its display
  name and panel kind ("Clock (edge panel)", "Summary (corner panel)"; "Float panel (coming
  soon)" is greyed out). A new panel gets a name made from the widget's display name that is
  free on that monitor (`Clock`, `Clock 2`) and its page opens.
- **Theme** page: tabs **General** (colours, fonts, thickness, radius, peek, hover zone,
  duration), **Borders**, **Shadows**, **Handle** (the handle colours and the handle style)
  and **Layout** (the gap). A **monitor** page has the same tabs under a banner: its values
  override the Theme for that monitor, and a row you have not set there shows the Theme's
  value. The monitor page also shows the layout warnings the shell would give.
- **Panel** pages (select a panel in the tree): its title ("1. Dock: bottom, center"), the
  layout warnings, and tabs **Panel** (Name, Widget and, for a widget of several panel types,
  Panel type), **Position** (edge, align, offset, order, length, depth; a corner panel: corner,
  edge, width, height), **Handle**, **Interaction** (start state, click, hover, drag) and
  **Widget** (the widget's own properties, for example the clock's Format, Font and Font size;
  no tab for a widget without properties). The Name row renames the panel: the tree and the
  title follow at once. The selected panel's tree row has Move up, Move down and Remove
  buttons (Tab reaches them); the toolbar has the same three.
- Switching a panel's widget, or its panel type, removes the keys the new kind or widget does
  not take in the same change (the name stays); moving a corner panel to a corner without its
  edge removes that edge. A name already used on the monitor is refused under the Name row.
```

  - In the bullet "- Changes apply at once (spin buttons 0.4 s after the last change; closing the window applies\n  a pending one); ..." replace "(spin buttons 0.4 s after the last change; closing the window applies\n  a pending one)" with "(spin buttons 0.4 s after the last change of any spin button; one queue applies every\n  change in the order you made it, and anything still waiting is applied before a panel is\n  added, moved or removed, before Undo, Save or leaving the config, and before Detect\n  monitors)". At the end of that bullet's paragraph (after "...cannot switch\n  it.") add: " If the file is changed in an editor while changes are still waiting, they are not\n  applied (they were made for the file before it changed) and the banner names them."
  - In "### Errors, failures and reloads", after the paragraph ending "...the entries of a `plasma` or `none` monitor stay in the file, unused." add:

```markdown
Monitors are matched by connector name (`scripts/py main.py --list-outputs` lists them). When
the config names a monitor that is not connected, the shell logs a warning and sends one
"Monitor not connected" notification with the names to use, for example `config monitors:
HDMI-A-2; connected: DP-1, HDMI-A-1`; it says so again only when that changes. A connected
monitor that the config does not name is fine (it gets nothing, as `plasma`).
```

  - In "## Known limitations / planned", after the "Settings window, files: ..." bullet add:

```markdown
- Settings window, tree and toolbar: the tree has no search; a panel's Move and Remove
  buttons show on the selected row only (not on hover); there is no right-click menu in the
  tree; a right-click on a panel handle opens the window on the page it showed last, not on
  that panel; the mode checkboxes always write `shell` (there is no reset to the default);
  two spin buttons changed within 0.4 s are written together after the last change.
```

- [ ] **Step 4: the spec.** In `docs/superpowers/specs/2026-10-14-panel-widget-model-design.md`, at the end of section 7 (after "- Panel renaming is the `name` row; the tree and titles follow at once.") add:

```markdown

**Planned (2026-10-15, `docs/superpowers/plans/2026-10-15-settings-tree.md`; results recorded after its gate):** as specified, with these readings (decisions in the plan): the tree is a list box whose selected panel row shows Move up, Move down and Remove (Phil: on the tree and on the toolbar); the theme keys are sorted onto tabs by what they relate to, and a new key lands on General; panel pages have Panel, Position, Handle, Interaction (state with click, hover, drag) and Widget; the panel type list names widget and kind ("Clock (edge panel)"); the toolbar shows the screen of the page shown and is insensitive on the Theme page; every edit goes through one ordered queue (a hand edit drops what is queued and names it); the shell warns once when the config names a monitor that is not connected (Phil, 2026-10-15), and Detect monitors says the same in the window. Widget discovery (a `widgets/<name>/<name>_widget.py` folder found by the shell) is a later plan; every widget list here comes from the registry.
```

- [ ] **Step 5: VERIFY**

Run: `scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q`
Expected: `All checks passed!`, `2501 passed`.

- [ ] **Step 6: Commit**

```bash
git add README.md settings/__init__.py examples/settings-test.toml docs/superpowers/specs/2026-10-14-panel-widget-model-design.md
git commit -m "docs: the settings tree, toolbar and tabbed pages in the README and the spec" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 11: Gate (Phil, live on HDMI-A-1 only)

**Files:** none. The controller prepares the commands and Phil runs every step; subagents never run them. **DP-1 is never touched**: the example lists it as `plasma`; do not click its checkboxes, change its rows or select its panels' buttons, at any step.

Setup (Phil, from the worktree):

```bash
mkdir -p /tmp/edge-tree
cp examples/settings-test.toml /tmp/edge-tree/config.toml
scripts/py main.py --config /tmp/edge-tree/config.toml -v                 # terminal 1: the shell
scripts/py main.py --settings --config /tmp/edge-tree/config.toml         # terminal 2: the window
```

Checklist (answer each with pass / fail and what was seen):

1. **Start.** Terminal 1 shows no "monitor names in the config are not connected" warning and no "Monitor not connected" notification (DP-1 and HDMI-A-1 are both connected). The window shows the menu bar (File, Edit, Help), the toolbar ("No screen selected", the checkboxes and the panel type list greyed out), **Detect monitors** above the tree, the tree on the left and the Theme page ("Theme (every monitor)") with the tabs General, Borders, Shadows, Handle, Layout. There is no Undo or Revert all button and no file path above the pages (the title shows the file); Undo, Redo and Revert all are in the Edit menu. *Fail note:* a warning at start means a connector name differs: run `scripts/py main.py --list-outputs` and report both.
2. **Tree.** Rows: Theme, then the connected monitors in the order the list shows them (kscreen-doctor's order, so probably DP-1 before HDMI-A-1; tell me the order you see), HDMI-A-1 with Dock, Clock, System bar indented under it, DP-1 with no panels. Look for: each monitor once, the panels only under HDMI-A-1, no "(not connected)" row. Drag the divider: the tree does not get narrower than about 200 px. Click HDMI-A-1's arrow: its panels hide; again: they show. Click Dock, then press Left: HDMI-A-1 is selected; Left again: collapsed; Right: expanded; Up/Down move the selection and the page follows. Select Dock: three small buttons (Move up, Move down, Remove) show at the right of the Dock row only; Tab reaches them and while one of them has the focus Left, Right and Delete leave the selection and the panels as they are (GTK may move the focus between the buttons with the arrow keys; that is fine).
3. **Theme tabs, Undo with no focus, narrow window.** General has the colours, fonts, thickness, radius, peek, hover zone, duration; Borders, Shadows, Handle (the handle colours, then the handle style: shape, size, weight) and Layout (gap). On Borders switch Border on (terminal 1 logs one reload), then click the Theme row in the tree (no field has the focus) and press Ctrl+Z: the border goes off again (one reload). Edit > Undo does the same for a second change. Drag the window narrower than 860 px: tell me what you see: the toolbar should stay on two lines plus the note line and the tab bar scroll (a horizontal scrollbar under a tab is expected here).
4. **Monitor page.** Select HDMI-A-1: a blue banner "These values override the Theme for HDMI-A-1. A row you have not set here shows the Theme's value." is always there; unset rows say "global theme". On General set the accent to a red: only HDMI-A-1's accent changes (the row says "your config"); press its reset button: it says "global theme" again. Switch to the Borders tab, select Dock, select HDMI-A-1 again: the Borders tab is still shown. **Sideways scroll question:** at the window's normal size (860 px), look at the General and Layout tabs of the HDMI-A-1 page: does a horizontal scrollbar show at the bottom of either tab? Tell me yes or no for each (a vertical scrollbar on General is expected).
5. **Toolbar and mode.** With HDMI-A-1 selected: the toolbar shows **HDMI-A-1**, **Enable** checked, **KDE Plasma** unchecked, and the note "Plasma's panel is not hidden or shown by Edge Shell yet; with both on, keep the bottom edge free of Edge Shell panels". Hover the name: the tooltip says `shell = "edge": Edge Shell frame and panels`. Check KDE Plasma: terminal 3 `grep -A1 'monitors.HDMI-A-1\]' /tmp/edge-tree/config.toml` shows `shell = "both"`; the frame stays (edge and both look the same today). Uncheck Enable: `shell = "plasma"`, the HDMI-A-1 frame goes. Check Enable, uncheck KDE Plasma: `shell = "edge"`, the frame is back. Select Dock: the same toolbar and checkboxes (the screen of its monitor) show. *Never do this on DP-1.*
6. **Theme page toolbar.** Select Theme: the toolbar says "No screen selected" and the checkboxes, the panel type list, Add and the three panel buttons are greyed out (the note stays).
7. **Add.** Select HDMI-A-1; the panel type list shows, in this order, "Clock (edge panel)", "Dock (edge panel)", "System bar (edge panel)", "Summary (corner panel)" and a greyed "Float panel (coming soon)" that cannot be chosen. Choose "Clock (edge panel)", press Add: a row **Clock 2** appears under HDMI-A-1, selected, its page shown; the shell builds a second clock (terminal 1: `building panel 3 'Clock 2' (clock) on HDMI-A-1`).
8. **Panel page tabs.** On Clock 2's page: the title "4. Clock 2: top, center", the toolbar names HDMI-A-1 and its three panel buttons are active, and the tabs are Panel, Position, Handle, Interaction, Widget; Widget has Format, Font, Font size. Select Dock: no Widget tab. There is no "Panels" tab on the HDMI-A-1 page (panels live in the tree).
9. **Rename.** On Clock 2's Panel tab set Name to `Second clock` and press Enter: the tree row and the page title change at once, the page stays; `grep -n "Second clock" /tmp/edge-tree/config.toml` shows it. Type `Third clock` in the Name row and, without pressing Enter, click Theme in the tree: the name is written when the field loses the focus (the tree row says Third clock). Rename it to `Dock`: refused under the Name row ("Not saved: ... names must be unique: 'Dock' is used by ..."), nothing is written.
10. **Move, remove and Delete.** Select Third clock and press its row's Remove button: it goes and HDMI-A-1's page is shown. Add another Clock (edge panel). On its selected tree row, the three buttons show at the right (only on that row): Move up moves it above System bar (the tree and the page follow; the first panel's Move up and the last's Move down are greyed, on the row and on the toolbar). The toolbar's Move down puts it back. **Delete key:** click Dock in the tree, press Ctrl+Up (the keyboard focus moves to HDMI-A-1's row while Dock stays selected; if Ctrl+Up selects HDMI-A-1 as well, say so), press Delete: nothing is removed. Click the new Clock row and press Delete: it is removed and HDMI-A-1's page is shown. Add one more Clock and use the toolbar's Remove: it goes and HDMI-A-1's page is shown.
11. **Edits in quick succession.** On HDMI-A-1's General tab click the thickness spin up three times and, within half a second, select Dock in the tree and click its Position tab's depth spin up twice (be quick): after you stop, the two spin edits queued within one pause are written one after the other in one pass a few milliseconds apart, and the shell's file watcher waits 200 ms (restarting on every change), so terminal 1 logs ONE reload, `config reloaded: 2 change(s): ...`, and nothing before you stopped; `grep -n "thickness\|depth" /tmp/edge-tree/config.toml` shows both. Click thickness up once and press Ctrl+Q within half a second: the Save / Discard / Cancel question appears; answer Discard: the window closes and the file is back as last saved (no thickness change in it).
12. **A hand edit while a change waits.** Start the window again; click Dock's depth spin up and, within half a second, in terminal 3 `printf '# hand\n' >> /tmp/edge-tree/config.toml`: the banner says the file was changed outside this window and, on the next line, "Not applied (made for the file before it changed): monitors.HDMI-A-1.panels[0].depth = ..." (the depth is not written). *Fail note:* if you were slower than half a second, the depth was written first; try again faster or report the banner text.
13. **Monitor names.** Press Detect monitors: the banner says "Connected monitors: DP-1, HDMI-A-1." (order as kscreen-doctor lists them). In terminal 3 append a monitor that does not exist: `printf '\n[monitors.HDMI-A-9]\nshell = "plasma"\n' >> /tmp/edge-tree/config.toml`: terminal 1 logs `monitor names in the config are not connected (config monitors: HDMI-A-9; connected: DP-1, HDMI-A-1)` and one notification "Monitor not connected" appears with "config monitors: HDMI-A-9; connected: DP-1, HDMI-A-1" and "Use the connected names in the config."; the window's tree shows "HDMI-A-9 (not connected)". Change the accent in the window: no second notification. Press Detect monitors: a warning banner "Monitors in the config that are not connected (config monitors: HDMI-A-9; connected: DP-1, HDMI-A-1): use the connected names in the config." Unplug test (only if you can unplug and replug HDMI-A-1's cable; otherwise skip): the name HDMI-A-1 is right and was seen connected in this session, so unplugging it and plugging it back gives no new notification and no new warning in terminal 1. A name that never matched (HDMI-A-9 above) is reported once, not on every reload. At shell start a configured monitor that is simply absent is reported too (the shell cannot tell it from a typo then). Remove the two lines by hand (`sed -i '/HDMI-A-9/,+1d' /tmp/edge-tree/config.toml`, then delete the empty line if you like): the tree drops HDMI-A-9 and nothing new is reported.
14. **Close and reopen.** File > Close: the empty page with New and Open; no toolbar, no tree. Run the terminal 2 command again in terminal 3: the window shows the file again with the tree and toolbar.
15. **DP-1 untouched.** `grep -A1 'monitors.DP-1\]' /tmp/edge-tree/config.toml` prints `shell = "plasma"`; Plasma's panel on DP-1 looks as before; no Edge Shell frame on DP-1.

Clean up after the gate: `rm -r /tmp/edge-tree` (Phil). Stop the shell with Ctrl+C in terminal 1.

### Task 12: Record the gate results

**Files:**
- Modify: `docs/superpowers/specs/2026-10-14-panel-widget-model-design.md` (section 7: the note becomes "**Implemented (2026-10-15, `docs/superpowers/plans/2026-10-15-settings-tree.md`; the live gate results follow):**" and the results are appended), `docs/superpowers/specs/2026-10-11-edge-shell-design.md` (section 13: one paragraph after the menus paragraph naming this plan, the tree, toolbar and tabs, the edit queue and the gate result; section 20 or a new line in section 5.3: the shell's monitor-name warning), `README.md` (any limitation the gate found)

- [ ] **Step 1:** Write Phil's answers per item (pass, or what was seen) into the spec's section 7 note, and every finding with its fix (fixes get their own task with tests, before this step, as in earlier plans).
- [ ] **Step 2: VERIFY**: `scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q` prints the measured total (`2621 passed` before the gate, more if a gate fix added tests), 0 skipped.
- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-10-14-panel-widget-model-design.md docs/superpowers/specs/2026-10-11-edge-shell-design.md README.md
git commit -m "docs: record the settings tree gate results" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

## Self-review

- **Spec coverage (section 7):** Toolbar per selected screen: the screen's name (Task 7), **Enable** and the desktop-named checkbox from `XDG_CURRENT_DESKTOP` through a name table, fallback "Native desktop" (Tasks 2, 7), a panel type dropdown with display names and float disabled, with Add (Tasks 1, 7; decision 5), Undo and Revert all out of the toolbar (Task 7; the Edit menu has them since plan 2). Mode mapping onto the four `shell` values, the one-line note (Tasks 2, 7; decision 10). Left tree at least 200 px with **Detect monitors** re-running kscreen-doctor and merging connected and configured monitors (Tasks 2, 5, 9), Theme and expandable monitor rows with their panels by name, each selectable, selecting a panel selects its page, expansion kept across rebuilds (Tasks 5, 6, 8). Pages with tabs: Theme General/Borders/Shadows/Handle/Layout (Tasks 1, 6), Monitor the same with the override banner and inherited values (Task 6), Panel tabs Panel/Position/Handle/Interaction/Widget, Widget absent without properties (Tasks 1, 8). Renaming via the `name` row, tree and titles follow (Task 8). Phil's later answers: tab sorting (Task 1), Move/Remove on the tree row and the toolbar (Tasks 5, 8), the shell's monitor warning (Task 3) and the window's (Task 9), the edit queue (Task 4), widget discovery out of scope (no hard-coded widget list: Tasks 1, 7). Spec section 6's "toolbar and tree insensitive with no config open": they are not shown at all on the empty page (decision 11). Gate on HDMI-A-1 with DP-1 untouched: Task 11.
- **Placeholder scan:** every code step carries the exact diff from the prototype; no "TBD", no "similar to Task N"; the docs task gives the exact text; the gate items name commands and expected output.
- **Type consistency:** `TabSpec.parts` keys are relative paths in Tasks 1, 6, 8; `AddChoice(id, label, kind, widget, enabled)` is the same in Tasks 1, 7, 8 and the view tests' `add` helper; `SettingsTree(on_select, on_action=None)` (Task 5) is built with both in Task 8; `ScreenToolbar(choices, native_label, on_mode, on_add, on_panel=None)` (Tasks 7, 8); `show_screen(screen, title, mode, panel)` gains `panel` in Task 8 with a default; `SettingsView(session, outputs, confirm_revert, on_state, desktop, detect)` grows by keyword parameters with defaults (Tasks 7, 9), so `SettingsController` needs no change for them; `panel_step`/`add_step` return `(edit, page)` and `_structural(edit, show)` takes them in Task 8; `FieldRow(spec, path, on_change, on_reset, on_queue=None, is_pending=None)` (Task 4) is built with all six only by the view.
- **Review Focus:** each of the five lines names tests in the owning task (all present in the diffs; checked by running them).
- **Measured:** every task was applied in order on a scratch copy of `c1bee7b` (git history kept in the scratch copy only) and the suite run after each: 2379, 2418, 2428, 2445, 2459, 2467, 2483, 2495, 2501 passed, 0 skipped, `ruff check` and `ruff format --check` clean at every step. Each task's tests were also applied alone on the previous task's code to record the failures in its Step 2. The queue mutations listed in Task 4 (order, coalescing, barrier, hand edit, rebuild) and two in Task 8 were run and failed tests; one survivor found while prototyping (the cleared page selection on a refused structural edit) got `test_an_add_refused_by_a_hand_edit_does_not_jump_to_another_panel`; one equivalent mutant is recorded in Task 4.

## Open questions for Phil (each with the recommended default)

1. **The panel type list names widget and kind** ("Clock (edge panel)", "Summary (corner panel)", "Float panel (coming soon)" greyed out), one entry per widget and kind it supports (decision 5). *Recommended: yes* (one list, every name distinct). Alternative: a kind dropdown and a widget dropdown (one more click).
2. **Move up / Move down / Remove show on the selected tree row only** (and on the toolbar), not on hover (decision 6). *Recommended: selected row only* (testable, keyboard reachable; hover adds motion and cannot be tested headless). Alternative: also on hover (a few lines, gate-checked only).
3. **The tree has no type-ahead search and no right-click menu** (decision 6; a list box replaces the tree view so the row buttons can exist). *Recommended: leave them out for now.* Alternatives: a search entry above the tree (about half a task), a context menu with the three actions (small).
4. **`state` (start collapsed or extended) is on the Interaction tab** (decision 2). *Recommended: Interaction* (it is how the panel opens). Alternative: Panel or Position (one dict entry).
5. **The mode checkboxes always write `shell`**; the old mode row's reset (back to the default `plasma`) goes (decision 4). *Recommended: yes* (writing `plasma` is the same as the default). Alternative: a small reset button beside the checkboxes.
6. **A hand edit drops the queued edits and names them** instead of replaying the ones whose paths still exist (decision 8). *Recommended: drop and name* (panels are tracked by index; a replay could change another panel). Alternative: replay only theme and layout paths (no panel indexes), about half a task.
7. **Two spin buttons changed within 0.4 s are written together after the last change** (one queue timer for the window, decision 8). *Recommended: yes* (fewer reloads, one order). Alternative: a timer per row as before, feeding the queue (more timers, the same order).
8. **The toolbar is insensitive on the Theme page** rather than hidden (decision 4). *Recommended: insensitive* (the pages do not jump). Alternative: hidden.
9. **Right-click on a panel handle opens the window on that panel**: deferred (decision 12, about one task). *Recommended: a small follow-up plan* together with widget discovery or plan 4.
