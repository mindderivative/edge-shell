# Settings Window Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A normal settings window that edits the user config (`~/.config/edge-shell/config.toml`, or the file given with `--config`) through a form generated from the Pydantic JSON schema and the widget registry: theme colours, fonts, thickness, radius, border, shadow and handle style; the per-monitor shell mode (`edge | plasma | both | none`) and per-monitor theme and layout overrides; each monitor's panel list (add, remove, reorder, widget choice, edge, align, offset, order, length, depth, state, handle, interactions); with every change validated by the shell's own rules before it is written, so the running shell reloads it live.

**Architecture:** The window runs in its own process (`main.py --settings`, a single-instance `Gtk.Application`), never inside the shell: the only channel between the two is the config file, which the shell already watches and hot-reloads (spec 6). A pure core is built and tested headlessly first: `settings/files.py` (atomic, symlink-safe writes; one backup per session; restore), `settings/document.py` (round-trip TOML editing with tomlkit that keeps comments, and refuses any edit whose re-parsed result differs from the intended plain-data edit), `settings/session.py` (apply = edit, check with the shell's loader and widget registry, write; undo, revert, hand-edit detection), `settings/form.py` (the form description from `Config.model_json_schema()`: field kinds, bounds, enums, colours) and `settings/values.py` (the value each field shows and where it is inherited from, plus a layout-warning preview from the shell's own resolver). A thin GTK layer renders it: `settings/fields.py` (one row per field), `settings/panels.py` (the panel list editor), `settings/view.py` (pages, banner, undo/revert, a plain `Gtk.Box` so it is tested without a window), `settings/window.py` and `settings/app.py` (the toplevel and the process). The shell gains one entry point: a right-click on any panel handle starts the window on the shell's config file.

**Tech Stack:** Python 3.14 (>=3.12), PyGObject 3.50.0 (`<3.52`), GTK 3, Fabric 0.0.2 (shell side only), Pydantic 2, **tomlkit >= 0.13 (new, pure Python)**, pytest, ruff 0.17.0.

**Spec:** `docs/superpowers/specs/2026-10-11-edge-shell-design.md`: section 13 (this plan), 6 (config, user file over defaults, validation with key paths, live reload table), 5.3 (monitor modes), 7 (Plasma integration: why the Plasma toggle is deferred), 14 (forms vs drag-and-drop), 15-17 (handle, interaction and layout keys the form exposes; "the settings window exposes slot, order and gap, and shows the overlap warning"). Previous plans for style and gates: `docs/superpowers/plans/2026-10-13-handle-customization.md`, `docs/superpowers/plans/2026-10-13-layout-anchoring.md`.

**Phil's requirements (verbatim):** "eventually, I want a settings panel for this project, where we can hide or show the plasma shell and hide or show the edge shell. I want this settings panel to basically allow me to change colors, turn the shell on or off, change the location of the edge bars and panels, pick what widgets I want, etc... Basically fully customizable Edge Shell". "We should have the ability to apply edge shell to one monitor and plasma shell to another." Earlier decisions: config first, then the settings window (a normal window); monitor modes `edge|plasma|both|none`; the window writes the user config file only; the form is generated from the Pydantic JSON schema and the widget registry; opened from a key binding, tray icon or frame handle (spec 13).

**Scope (Plan 4).** In: everything in the config models except the deprecated `pos` (shown, removable, not editable): `[theme]` with `border`, `shadow`, `handle_style`; `[layout]`; per monitor `shell`, `theme` override, `layout` override and the panel list; undo, revert, per-field reset; layout-warning preview; live apply; the backup and `--restore-config`; opening by CLI, by a right-click on a panel handle, and by a KDE custom shortcut (documented; Phil sets it). Out (decision 1): hiding or showing Plasma's panels, workspaces and tray widgets, a tray icon, drag-and-drop layout editing, HiDPI, editing `config.default.toml`.

**Date:** 2026-10-14 (the plan's execution date, as in the file name).

**Size:** 14 tasks. 11 carry code and tests (1-11), Task 12 is the gate example and the docs, 2 human gates (Gate A = Task 13, the window and live reload; Gate B = Task 14, safety and entry points, then the results are recorded). Riskiest: Task 3 (tomlkit can silently move keys: found while prototyping, a table added inside a dotted-key table is written as a top-level header; the edit-then-verify design catches it and a test pins it), Task 9 (every edit path: valid, invalid, structural, hand edit, invalid file), Task 11 (the only change to the running shell; Gate B item 6 checks the right-click live).

## Decisions (each marked *default pending Phil*, with the cost if Phil disagrees)

1. **v1 scope: the whole config model; the Plasma panel toggle is deferred to its own plan.** *Default pending Phil.* The window edits every key the models have (theme incl. border, shadow, handle style; layout gap; per monitor: mode, theme and layout overrides, panels with every key including handle and interaction). Deferred, and why: (a) **hiding or showing Plasma's panel** needs `services/plasma.py` (`org.kde.PlasmaShell.evaluateScript`, whose hide/restore behaviour is still unverified: spec 11 spike 2) and the restore file `~/.local/state/edge-shell/plasma-restore.json` with `--restore-plasma` (spec 7); it touches the live Plasma panel on DP-1, so it needs its own spike gate on a temporary panel on HDMI-A-1 first and Phil's go-ahead before DP-1 is touched; (b) workspaces and tray widgets do not exist yet (milestone 7); (c) a tray icon needs the tray host (milestone 7); (d) drag-and-drop layout editing (spec 14) waits for v1 feedback; (e) HiDPI is unsupported by the shell. **How `plasma` and `both` appear:** as the existing mode choices, each with a one-line explanation under the mode row (`settings/form.py` `MODE_HINTS`): `plasma` = "no Edge Shell here; Plasma's panels stay as they are", `both` = "Edge Shell frame and panels next to Plasma's panel: keep Edge Shell panels off the edge Plasma's panel uses", `none` = "no Edge Shell here (the same as plasma until the Plasma panel toggle exists)". So "Edge Shell on one monitor, Plasma on the other" works today (HDMI-A-1 `edge`, DP-1 `plasma`), and "hide or show the edge shell" per monitor is the mode switch. *Cost if Phil wants the Plasma toggle in v1:* about 5 more tasks (a pure restore-file module with a fake script runner, the D-Bus service, a spike gate on a temporary HDMI-A-1 panel, the window's "Plasma panel" switch per monitor, `--restore-plasma`) and one more live gate that touches DP-1 only after Phil confirms.
2. **Edits are written into the one user file with tomlkit (round-trip), and verified.** *Default pending Phil.* Every edit re-reads the file's current text, applies one key-path operation (`set`, `unset`, `add_panel`, `remove_panel`, `move_panel`) with tomlkit, and then re-parses the result with `tomllib` and compares it with the same operation applied to plain dicts: any difference (tomlkit misplacing a table) is refused with "edit the file by hand" and nothing is written. Comments, blank lines, key order and dotted-key style are kept (an unedited document is byte-identical); new nested keys inside an existing table are written as dotted keys (`handle.shape = "bar"`), new top-level and monitor tables as headers (`[monitors.eDP-1]`); a table left empty by a reset is removed. Rejected: (a) rewriting the file from the model loses every comment Phil writes; (c) a separate `settings.toml` overlay merged by the loader keeps the hand file untouched, but a key set in the overlay silently shadows the same key edited by hand ("I changed config.toml and nothing happened"), lists replace wholesale (an overlay panel list hides the hand-written one for that monitor), the shell would have to watch and merge two files, and it breaks "writes the user config file only". *Cost:* a new dependency. tomlkit is pure Python (MIT), **not installed in the venv today** (`scripts/py -c 'import tomlkit'` fails; version 0.15.1 is in the local uv cache). Changes: `pyproject.toml` `dependencies` gains `"tomlkit>=0.13"`; `.github/workflows/ci.yml` installs `"tomlkit>=0.13"` next to pydantic; Phil installs it once into the shared venv (`scripts/py -m pip install 'tomlkit>=0.13'`, Prerequisites). Tests that need it start with `pytest.importorskip("tomlkit")`, so a venv without it still passes (those files skip); `main.py --settings` without it prints the install command and exits 2; the shell itself never imports it. *Cost if Phil prefers the overlay (c):* replace `settings/document.py` with an overlay writer (plain `tomllib` + a tiny TOML emitter), make the loader merge three layers and the watcher watch two files (about 2 tasks), and show "set in settings.toml / config.toml" per row.
3. **The window is its own process; the config file is the only link to the shell.** *Default pending Phil.* `main.py --settings [--config PATH]` runs `settings/app.py`: a `Gtk.Application` with id `org.edgeshell.Settings`, so a second launch brings the open window forward instead of opening another (GApplication's single-instance activation over D-Bus; no Fabric involved). It opens with or without a running shell, and even when the config is invalid (read-only, with the error), which makes it its own escape hatch. Entry points: the CLI; **a right-click on any panel handle** (Task 11: `EdgePanel` calls `EdgeShellApp.open_settings`, which starts `sys.executable main.py --settings --config <the shell's config path>` in a new session, so Ctrl+C on the shell leaves the window open); **a KDE custom shortcut** that runs the same command (Phil adds it in System Settings, documented in the README; the plan never changes system settings); a tray icon later (decision 1). The window is a plain `Gtk.ApplicationWindow` (an xdg toplevel, never a layer surface: nothing in `settings/` imports GtkLayerShell or Fabric windows); on Wayland a client cannot choose its position, so KWin places it (normally on the monitor with the pointer); it has no link to DP-1's Plasma panel. Why not inside the shell process: a bug in the window could take the shell down; the shell's scoped stylesheet and its single-instance `Application` would have to share a main loop with a form; and the window could not open when the shell cannot start. Fabric's D-Bus `InvokeAction`/`Execute` API is not used. *Cost if Phil wants it in-process:* about 1 task (the shell opens `SettingsWindow` itself and shares `ConfigStore`), losing the escape hatch.
4. **The form is a pure description generated from the JSON schema; rows show the value in effect and where it comes from; "inherit" = the key is absent.** *Default pending Phil.* `settings/form.py` turns `Config.model_json_schema()` into `SectionSpec`/`FieldSpec` trees: integers become spin buttons with the schema's `minimum`/`maximum`, `Literal` enums (`HANDLE_SHAPES`, edges, align, state, shell modes) become combo boxes, booleans switches, the font list a comma-separated entry, `length` a mode combo (px, fill, content, percent) plus a number, `widget` a combo of `registry.widget_names()`, and colours a `Gtk.ColorButton` with alpha (written as `#rrggbb`, or `#rrggbbaa` only when not opaque). Colours are recognised by key name (`COLOR_FIELDS` + `color`, `hover_color`) because the models check them with a validator the schema does not show; a test fails if a new plain string key appears that the form does not classify. **Finding:** the per-monitor override models (`ThemeOverride`, `LayoutOverride`, built with `create_model` from bare annotations) lose their bounds in the schema (`thickness` has no minimum/maximum there), so the override sections are generated from the base models (`Theme`, `LayoutSettings`). Every row shows the value in effect and its source (`your config`, `default`, `global theme`, `global layout`, `widget default`, `theme`, or `not set` for `min_length`/`max_length`/`pos`), plus a reset button that removes the key from the user file (the value is then inherited again). No separate "inherit" checkbox: unset means the key is absent, which is exactly what TOML and the loader already mean. A rejected edit shows the loader's message (it names the key path) under the row that caused it; a rejected structural edit (add, remove, move) shows it in a banner. *Cost:* an explicit inherit toggle per row is a small change in `FieldRow`.
5. **Live apply, no Apply button; Undo, Revert all and per-field reset.** *Default pending Phil.* A switch, combo or colour applies at once; a spin button applies 400 ms after the last change (one write and one reload per pause, not per arrow click: a `thickness` change rebuilds the monitor); a text entry applies on Enter or focus-out. Each applied change is one undo step (`Undo` button and Ctrl+Z restore the file's previous text); `Revert all` (with a confirmation) restores the file as it was when the window opened. The window watches the file (the shell's own `ConfigWatcher`): a hand edit while it is open is re-read, announced in a banner, and clears the undo history; an edit made against a stale read is refused, never written over the hand edit. Per-section reset is not in v1. *Cost:* an Apply/Cancel bar = buffer the operations in the session and write once (about half a task); per-section reset = one button per frame calling `unset` on the table (small).
6. **Safety: never write what the shell would reject; atomic writes; a backup and a restore command; no confirm-revert countdown in v1.** *Default pending Phil.* An edit is checked with `load_config_text` (the loader's own merge and validation) plus `registry.validate_widgets` before writing; the write goes to a temporary file next to the target and is renamed over it (the shell's watcher already reacts to renames; a symlinked config, e.g. from a dotfiles repo, keeps its link and the file it points to is replaced; the file mode is kept). Before the first write of a session the file is copied to `config.toml.bak`; `main.py --restore-config` puts it back and keeps the replaced file as `config.toml.before-restore`. The escape hatches when the shell looks wrong: Undo/Ctrl+Z, Revert all, `--restore-config`, and the window itself, which opens even if the shell is not running or the file is invalid. No KDE-style "keep these settings? (15 s)" countdown: the window is a separate normal window the shell cannot take away, and a config that is valid but ugly (transparent frame, every panel removed, every monitor `none`) is undone in one step. The one way the shell can get in the window's way is a huge extended panel on top of it (panels are layer-shell `top` surfaces above normal windows); Ctrl+Z still reaches the focused window (panels never take the keyboard), which Gate B item 9 checks. The shell's "Config not applied" notification stays as the backstop for hand edits. *Cost if Phil wants the countdown:* about 1 task (a pure `risky_change(old, new)` predicate plus a dialog that reverts after 15 s).
7. **Testing.** Pure tests for everything below the GTK line (form, values, files, document, session, and an integration test that a written change reloads in the shell's real `ConfigStore` as the expected `diff_configs` kind: restyle, panel-state, panel-handle, panel-rebuild, relayout, rebuild-monitor, panel-add). GTK tests build widgets only (never a window), after `Gtk.init_check()`, and skip without a display; the view is a `Gtk.Box` for that reason and the toplevel (`settings/window.py`) is a few lines checked at the gates. `Gtk.Application.run` is never called in tests (it would register on the session bus). Two human gates on HDMI-A-1. *Cost:* none.
8. **CLI.** `--list-outputs`, `--settings` and `--restore-config` are mutually exclusive; `--stats` with `--settings` or `--restore-config` is an error (`--list-outputs --stats` keeps today's behaviour). `--config PATH` with `--settings` may name a file that does not exist yet (the first change creates it). *Cost:* none.
9. **A panel's expander title** shows `N. widget: edge, align`; changing the widget, edge or align rebuilds the page so the title follows, and keeps that panel open. Adding a panel opens the new one, moving opens the moved one. *Cost:* none.
10. **The right-click needs the handle to take input**: a panel with click, hover and drag all off takes no input while collapsed (spec 15), so its handle cannot open the window; any other handle, the CLI or the shortcut can. The frame band stays click-through (no frame click). *Cost:* none.

## Prerequisites

- Branch `feat/settings-window` from `main` at `ad58f61` (Plans 1-3 merged), in the worktree `/home/phil/Projects/pyDev/projects/myShell/.claude/worktrees/feat-edge-shell-core`.
- Baseline before Task 1: `scripts/py -m pytest -q` prints `1192 passed` (2 GLib deprecation warnings are normal); `scripts/py -m ruff check .` prints `All checks passed!`.
- **tomlkit in the venv (Phil, once, before Task 3):** the controller asks Phil to approve installing it, then Phil runs (or approves the controller running) `scripts/py -m pip install 'tomlkit>=0.13'`; check with `scripts/py -c 'import tomlkit; print(tomlkit.__version__)'`. Subagent implementers never install packages. If it is not installed, the tomlkit test files skip and every expected total from Task 3 on is lower (the table under File Structure gives both).
- Always stage files by name, never `git add -A` or `git add .`.

## Global Constraints

- Python only through `scripts/py` (shared venv `/home/phil/Projects/pyDev/pyEnvs/global-base`). **PyGObject must stay `<3.52`** (Fabric 0.0.2 breaks on 3.52+).
- **Monitor is an INT.** Fabric 0.0.2's `WaylandWindow.monitor` is an int property; a `Gdk.Monitor` is silently dropped; use `monitor=monitor_index(monitor)` (`shell/gdk_util.py`). This plan creates no layer-shell windows; the settings window is a plain `Gtk.ApplicationWindow` and must never import GtkLayerShell or a Fabric window class.
- **Input shape after allocate.** Fabric's `Window.do_size_allocate` resets the input shape; `EdgePanel.do_size_allocate` re-applies it. Task 11 touches `EdgePanel.__init__` and `_on_press` only; keep that override and keep every attribute `_update_input_region` reads set before `_d`.
- **Keep the delayed `raise_to_top` workaround** (`RAISE_DELAY_MS` / `RAISE_FALLBACK_MS` in `shell/monitors.py`, the re-raise of rebuilt panels in `_new_panel`).
- **Pure modules import no GTK / `gi`:** `settings/form.py`, `settings/values.py`, `settings/files.py`, `settings/document.py`, `settings/session.py`, and as before `shell/config/*` (except `watcher.py`), `shell/registry.py`, `shell/panel_spec.py`, `shell/panel_layout.py`, `shell/outputs.py`. `settings/files.py` is stdlib-only (no tomlkit), so `--restore-config` works without tomlkit.
- **Colours** are `#rrggbb` or `#rrggbbaa` (`check_hex`, `hex_to_rgba`); the window writes `#rrggbbaa` only for a colour that is not opaque.
- **The settings window writes only the user config** (the `--config` path or `~/.config/edge-shell/config.toml`), its `.bak` and, for `--restore-config`, `.before-restore` next to it; never `config.default.toml`, never a live window.
- **Tests.** CI installs only pycairo, pydantic, pytest, ruff and (from Task 1) tomlkit: tests importing `gi` or `fabric` start with `pytest.importorskip("gi")` / `pytest.importorskip("fabric")`; tests needing tomlkit start with `pytest.importorskip("tomlkit")`. GTK tests call `gi.require_version("Gtk", "3.0")` and `gi.require_version("Gdk", "3.0")` before importing `gi.repository`, skip unless `Gtk.init_check()[0]`, and **never create a window** (that would draw on Phil's screen): plain widgets and the `SettingsView` box only. Never call `Gtk.Application.run` or `Gio.Application.register` in a test.
- **Lint.** `ruff` 0.17.0, line length 100, rules E, F, I, UP, B; excludes `docs/` and `*.md`. Import blocks: stdlib, third-party (`gi`, `tomlkit`, `pydantic`), first-party (`settings`, `shell`, `widgets`); `ruff check --fix` sorts them.
- **VERIFY** (before every commit): `scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q`. The suite must be green at the end of EVERY task (0 failed).
- **Git.** Plain separate git commands run from the worktree (no `cd … && git`, no command substitution around git). Stage files by name. **Never push.** Every commit message ends with a second `-m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"`.
- **Live runs.** Phil is the only visual tester, on `HDMI-A-1` only. **Never touch `DP-1`** (it holds the Plasma panel; never set it to `edge` or `both`, in a file or in the window). Subagents executing tasks never launch the shell or the settings window (`main.py` without `--list-outputs`, including `--settings`); headless commands are fine (`pytest`, the `scripts/py -c` checks below, which import the widgets but create no window). Live probes run by the controller are capped at 10 s (`main.py --stats` refuses more); the gates are run by Phil.

## Review Focus

The six input classes most likely to bite Phil that the spec implies but a happy-path test would not catch, each pinned by a test in the owning task:

1. **Phil's comments and layout must survive, and an edit must never move a key to another table** (tomlkit writes a table added inside a dotted-key table as a top-level header: `[monitors.X] theme.accent = …` plus a new `theme.shadow.elevation` would land in the global `[theme.shadow]`). Expect comments, key order and style kept, dotted keys used inside existing tables, and a refused edit (nothing written) whenever the re-parsed file differs from the intended edit. Pinned by `test_an_unedited_document_is_byte_identical`, `test_replacing_a_value_keeps_its_comment`, `test_a_new_key_inside_a_dotted_table_stays_in_that_monitor`, `test_other_toml_layouts_are_edited_in_place` and `test_an_edit_that_would_change_other_keys_is_refused` (Task 3), `test_apply_writes_a_valid_change_keeping_comments` (Task 4), `test_the_settings_example_is_valid_and_keeps_its_comments` (Task 12); live by Gate A item 13.
2. **Phil edits the file by hand while the window is open.** Expect the hand edit never to be overwritten: the window re-reads it, says so, and the next change applies on top of it. Pinned by `test_a_hand_edit_is_never_overwritten` and `test_undo_after_a_hand_edit_rereads_instead` (Task 4), `test_a_hand_edit_is_reloaded_and_announced`, `test_our_own_write_does_not_rebuild` and `test_an_edit_after_a_hand_edit_is_not_applied` (Task 9); live by Gate B items 1-2.
3. **A value the shell would reject** (a cross-field rule such as `min_length > max_length` or `pos` with `align`, an unknown widget, a bound the spin button cannot stop) must never reach the file, and the reason must show where the change was made. Pinned by `test_an_invalid_change_is_not_written`, `test_an_unknown_widget_is_not_written` and `test_a_cross_field_rule_is_not_written` (Task 4), `test_an_invalid_edit_shows_its_error_under_the_row` and `test_a_rejected_panel_edit_shows_in_the_banner` (Task 9); live by Gate A item 10.
4. **A config the shell cannot use** (invalid by hand, missing, a symlink into a dotfiles repo, a directory by mistake) must not lock Phil out: the window still opens (read-only with the error while invalid), writes keep the link, and `--restore-config` brings back the backup. Pinned by `test_write_atomic_follows_a_symlink`, `test_a_failed_write_leaves_the_old_file_and_no_temp_file` and the restore tests (Task 2), `test_a_missing_file_is_the_defaults` and `test_an_invalid_file_opens_with_its_error` (Task 4), `test_an_invalid_file_is_shown_read_only_with_its_error` (Task 9), `test_settings_opens_even_when_the_config_is_invalid` and `test_an_unreadable_config_fails_without_a_window` (Task 10); live by Gate B items 3, 4 and 7.
5. **Spin-button chatter**: holding an arrow on `thickness` must not write the file (and rebuild the monitor) on every step. Expect one write 400 ms after the last change, and a pending write dropped when the file is re-read. Pinned by `test_int_row_takes_its_bounds_from_the_schema_and_is_debounced` and `test_a_new_value_cancels_a_pending_edit` (Task 7); live by Gate A item 4.
6. **Adding, removing or reordering panels** must never leave rows pointing at an entry that is gone (an IndexError on the next refresh) and must keep the user's place. Pinned by `test_add_remove_and_move_are_document_edits` (Task 8), `test_adding_and_removing_panels_rebuilds_the_rows`, `test_changing_a_panel_edge_retitles_it_and_keeps_it_open` and `test_the_visible_page_survives_a_rebuild` (Task 9), `test_move_panel` and `test_removing_the_last_panel_removes_the_list` (Task 3); live by Gate A item 6.

## File Structure

```
pyproject.toml, .github/workflows/ci.yml   # + tomlkit>=0.13 (Task 1)
shell/config/loader.py        # + load_config_text(user_text, default_path) (Task 1)
settings/__init__.py          # NEW package (Task 2)
settings/files.py             # NEW, PURE stdlib: read_text, write_atomic, backup_path, write_backup,
                              #   restore_backup (Task 2)
settings/document.py          # NEW, PURE + tomlkit: UserDocument (set, unset, add_panel, remove_panel,
                              #   move_panel, text, data), DocumentError (Task 3)
settings/session.py           # NEW, PURE: check_text, SettingsSession (apply, undo, revert, reload,
                              #   changed_outside), ChangedOutside (Task 4)
settings/form.py              # NEW, PURE: FieldSpec, SectionSpec, ConfigForm, config_form, section_for,
                              #   MODE_HINTS, HINTS, rgba_to_hex, split_length, join_length,
                              #   parse_fonts, format_fonts (Task 5)
settings/values.py            # NEW, PURE: FieldValue, lookup, field_value, monitor_names,
                              #   layout_preview (Task 6)
settings/fields.py            # NEW, GTK: editors per kind, FieldRow (Task 7)
settings/panels.py            # NEW, GTK: PanelEditor, panel_title (Task 8)
settings/view.py             # NEW, GTK: SettingsView (Task 9)
settings/window.py            # NEW, GTK: SettingsWindow (Task 10)
settings/app.py               # NEW, GTK: SettingsApp, run_settings, connected_outputs (Task 10)
main.py                       # --settings, --restore-config (Task 10)
shell/edge_panel.py           # on_settings kwarg; right-click in _on_press (Task 11)
shell/monitors.py             # on_settings kwarg passed to every panel (Task 11)
shell/app.py                  # settings_command, MAIN_PATH, EdgeShellApp.open_settings (Task 11)
examples/settings-test.toml   # NEW, the gates' config (Task 12)
README.md, docs/superpowers/specs/2026-10-11-edge-shell-design.md   # Tasks 12, 14
tests/test_config_loader_text.py, tests/test_settings_files.py, tests/test_settings_document.py,
tests/test_settings_session.py, tests/test_settings_form.py, tests/test_settings_values.py,
tests/test_settings_fields.py, tests/test_settings_panels.py, tests/test_settings_view.py,
tests/test_settings_app.py, tests/test_main_settings.py, tests/test_open_settings.py,
tests/test_settings_example.py                                     # NEW
tests/test_app_sync.py, tests/test_monitor_shell.py                 # FakeShell / build fixture (Task 11)
```

| Task | Deliverable | Expected `pytest -q` (tomlkit installed) | Without tomlkit | Keeps the suite green because |
| --- | --- | --- | --- | --- |
| 1 | tomlkit dependency, `load_config_text` | 1196 (+4) | 1196 | new function |
| 2 | `settings/files.py` | 1207 (+11) | 1207 | new module, stdlib only |
| 3 | `settings/document.py` | 1237 (+30) | 1207, 1 skipped | new module |
| 4 | `settings/session.py` | 1260 (+23) | 1207, 2 skipped | new module |
| 5 | `settings/form.py` | 1283 (+23) | 1230, 2 skipped | new module |
| 6 | `settings/values.py` | 1292 (+9) | 1239, 2 skipped | new module |
| 7 | `settings/fields.py` | 1306 (+14) | 1253, 2 skipped | new module |
| 8 | `settings/panels.py` | 1310 (+4) | 1253, 3 skipped | new module |
| 9 | `settings/view.py` | 1325 (+15) | 1253, 4 skipped | new module |
| 10 | window, app, `main.py` flags | 1338 (+13) | 1265, 5 skipped | new flags are opt-in |
| 11 | right-click on a handle opens the window | 1346 (+8) | 1273, 5 skipped | new kwargs default to None |
| 12 | gate example, README, spec | 1347 (+1) | 1273, 6 skipped | docs + one example test |
| 13 | Gate A (Phil, live) | 1347 | | no code |
| 14 | Gate B (Phil, live) + results recorded | 1347 | | docs only |

Without a display the GTK files (`test_settings_fields.py`, `test_settings_panels.py`, `test_settings_view.py`) skip as whole modules (one "skipped" each; 33 fewer passed). CI has neither `gi` nor a display, so it skips them and every `gi`/`fabric` test as before.

---

### Task 1: tomlkit dependency and `load_config_text`

**Files:**
- Modify: `pyproject.toml` (the `dependencies` line)
- Modify: `.github/workflows/ci.yml` (the `pip install` line)
- Modify: `shell/config/loader.py` (append a function)
- Test: `tests/test_config_loader_text.py` (new)

**Interfaces:**
- Consumes: `_read_toml`, `parse_config`, `DEFAULT_PATH` (`shell/config/loader.py`), `deep_merge`, `ConfigError` (`shell/config/models.py`).
- Produces: `shell.config.loader.load_config_text(user_text: str, default_path: Path = DEFAULT_PATH) -> Config`; raises `ConfigError("TOML syntax error: …")` for bad TOML and the loader's key-path messages for invalid values.

- [ ] **Step 1: Write the failing test**

Create `tests/test_config_loader_text.py`:

```python
import pytest

from shell.config.loader import load_config, load_config_text
from shell.config.models import ConfigError

USER = '[theme]\naccent = "#112233"\n[monitors.HDMI-A-1]\nshell = "edge"\n'


def test_load_config_text_matches_load_config(tmp_path):
    path = tmp_path / "c.toml"
    path.write_text(USER)
    assert load_config_text(USER) == load_config(path)


def test_load_config_text_of_nothing_is_the_defaults():
    assert load_config_text("") == load_config(None)


def test_load_config_text_syntax_error():
    with pytest.raises(ConfigError, match="TOML syntax error"):
        load_config_text("[theme\n")


def test_load_config_text_names_the_bad_key():
    with pytest.raises(ConfigError, match="theme.thickness"):
        load_config_text("[theme]\nthickness = 1\n")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `scripts/py -m pytest tests/test_config_loader_text.py -q`
Expected: collection error, `ImportError: cannot import name 'load_config_text'`.

- [ ] **Step 3: Implement**

Append to `shell/config/loader.py` (after `load_config`):

```python
def load_config_text(user_text: str, default_path: Path = DEFAULT_PATH) -> Config:
    """Defaults overlaid with a user config given as TOML text: the settings window checks an
    edit with this before writing it, by the same rules as load_config."""
    try:
        user = tomllib.loads(user_text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"TOML syntax error: {exc}") from None
    return parse_config(deep_merge(_read_toml(default_path), user))
```

In `pyproject.toml` replace

```toml
dependencies = ["pydantic>=2.6", "PyGObject<3.52", "pycairo"]
```

with

```toml
dependencies = ["pydantic>=2.6", "PyGObject<3.52", "pycairo", "tomlkit>=0.13"]
```

In `.github/workflows/ci.yml` replace

```yaml
        run: pip install "pydantic>=2.6" pycairo pytest "ruff==0.17.0"
```

with

```yaml
        run: pip install "pydantic>=2.6" pycairo "tomlkit>=0.13" pytest "ruff==0.17.0"
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `scripts/py -m pytest tests/test_config_loader_text.py -q`
Expected: `4 passed`.

- [ ] **Step 5: VERIFY and commit**

Run VERIFY. Expected: `1196 passed`, `All checks passed!`.

```bash
git add pyproject.toml .github/workflows/ci.yml shell/config/loader.py tests/test_config_loader_text.py
git commit -m "feat(config): load_config_text for the settings window; tomlkit dependency" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Safe writes: `settings/files.py`

**Files:**
- Create: `settings/__init__.py`, `settings/files.py`
- Test: `tests/test_settings_files.py`

**Interfaces:**
- Consumes: `ConfigError` (`shell/config/models.py`).
- Produces (stdlib only):
  - `read_text(path: Path) -> str` ("" when the file does not exist; `ConfigError` naming the path for other OS or decode errors)
  - `write_atomic(path: Path, text: str) -> None` (temp file next to the resolved target, fsync, keep mode, `os.replace`; a symlink keeps its link)
  - `backup_path(path: Path) -> Path` (`config.toml.bak` next to the resolved target)
  - `write_backup(path: Path) -> Path | None`
  - `restore_backup(path: Path) -> str` (keeps the replaced file as `config.toml.before-restore`; `ConfigError("no backup to restore: …")`)

- [ ] **Step 1: Write the failing test**

Create `tests/test_settings_files.py`:

```python
"""settings.files: atomic writes, the session backup and restore (pure, stdlib)."""

import os
import stat

import pytest

from settings import files
from shell.config.models import ConfigError


def test_write_atomic_creates_the_file_and_its_directory(tmp_path):
    path = tmp_path / "edge-shell" / "config.toml"
    files.write_atomic(path, "a = 1\n")
    assert path.read_text() == "a = 1\n"
    assert [p.name for p in path.parent.iterdir()] == ["config.toml"]  # no temp file left


def test_write_atomic_replaces_and_keeps_the_mode(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("old\n")
    os.chmod(path, 0o600)
    files.write_atomic(path, "new\n")
    assert path.read_text() == "new\n"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_write_atomic_follows_a_symlink(tmp_path):
    real = tmp_path / "dotfiles" / "config.toml"
    real.parent.mkdir()
    real.write_text("old\n")
    link = tmp_path / "config.toml"
    link.symlink_to(real)
    files.write_atomic(link, "new\n")
    assert link.is_symlink()
    assert real.read_text() == "new\n"


def test_a_failed_write_leaves_the_old_file_and_no_temp_file(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    path.write_text("old\n")

    def boom(*_args):
        raise OSError("disk full")

    monkeypatch.setattr(files.os, "replace", boom)
    with pytest.raises(OSError, match="disk full"):
        files.write_atomic(path, "new\n")
    assert path.read_text() == "old\n"
    assert [p.name for p in tmp_path.iterdir()] == ["config.toml"]


def test_read_text_of_a_missing_file_is_empty(tmp_path):
    assert files.read_text(tmp_path / "absent.toml") == ""


def test_read_text_of_an_unreadable_path_names_it(tmp_path):
    (tmp_path / "dir.toml").mkdir()  # IsADirectoryError, an OSError
    with pytest.raises(ConfigError, match="dir.toml"):
        files.read_text(tmp_path / "dir.toml")


def test_backup_copies_the_current_file(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("a = 1\n")
    assert files.write_backup(path) == tmp_path / "config.toml.bak"
    assert (tmp_path / "config.toml.bak").read_text() == "a = 1\n"


def test_backup_of_a_missing_file_is_none(tmp_path):
    assert files.write_backup(tmp_path / "config.toml") is None
    assert list(tmp_path.iterdir()) == []


def test_restore_puts_the_backup_back_and_keeps_the_replaced_file(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("broken\n")
    (tmp_path / "config.toml.bak").write_text("good\n")
    message = files.restore_backup(path)
    assert path.read_text() == "good\n"
    assert (tmp_path / "config.toml.before-restore").read_text() == "broken\n"
    assert "config.toml.bak" in message and "before-restore" in message


def test_restore_without_a_current_file(tmp_path):
    (tmp_path / "config.toml.bak").write_text("good\n")
    files.restore_backup(tmp_path / "config.toml")
    assert (tmp_path / "config.toml").read_text() == "good\n"
    assert not (tmp_path / "config.toml.before-restore").exists()


def test_restore_without_a_backup_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match="no backup"):
        files.restore_backup(tmp_path / "config.toml")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `scripts/py -m pytest tests/test_settings_files.py -q`
Expected: collection error, `ModuleNotFoundError: No module named 'settings'`.

- [ ] **Step 3: Implement**

Create `settings/__init__.py`:

```python
"""The Edge Shell settings window (spec 13). Pure modules: form, values, files, document,
session. GTK modules: window, app."""
```

Create `settings/files.py`:

```python
"""Safe writes of the user config: atomic replace, one backup per settings session, restore.
Pure: stdlib only (no GTK, no tomlkit), so `main.py --restore-config` works without either."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from shell.config.models import ConfigError


def backup_path(path: Path) -> Path:
    """config.toml -> config.toml.bak, next to the file the path points to."""
    path = path.resolve()
    return path.with_name(path.name + ".bak")


def read_text(path: Path) -> str:
    """The file's text; "" when it does not exist (the defaults apply)."""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigError(f"{path}: {exc}") from None


def write_atomic(path: Path, text: str) -> None:
    """Write `text` to a temporary file next to the target, then rename it over the target, so
    the shell's watcher never reads a half-written file. A symlinked config keeps its link:
    the file it points to is replaced. The mode of an existing file is kept."""
    target = path.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.chmod(tmp, stat.S_IMODE(target.stat().st_mode))
        except FileNotFoundError:
            pass
        os.replace(tmp, target)
    except BaseException:
        tmp.unlink(missing_ok=True)  # only the temporary file this call created
        raise


def write_backup(path: Path) -> Path | None:
    """Copy the current file to config.toml.bak (atomically); None when there is no file."""
    target = path.resolve()
    if not target.exists():
        return None
    backup = backup_path(target)
    write_atomic(backup, read_text(target))
    return backup


def restore_backup(path: Path) -> str:
    """Put config.toml.bak back in place. The current file is kept as
    config.toml.before-restore first, so a restore can itself be undone by hand. Returns a
    line for the user; raises ConfigError when there is no backup."""
    target = path.resolve()
    backup = backup_path(target)
    if not backup.exists():
        raise ConfigError(f"no backup to restore: {backup} does not exist")
    text = read_text(backup)
    kept = target.with_name(target.name + ".before-restore")
    if target.exists():
        write_atomic(kept, read_text(target))
    write_atomic(target, text)
    return f"restored {target} from {backup}" + (
        f" (the replaced file is {kept})" if kept.exists() else ""
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `scripts/py -m pytest tests/test_settings_files.py -q`
Expected: `11 passed`.

- [ ] **Step 5: VERIFY and commit**

Run VERIFY. Expected: `1207 passed`.

```bash
git add settings/__init__.py settings/files.py tests/test_settings_files.py
git commit -m "feat(settings): atomic, symlink-safe writes, session backup and restore" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: In-place TOML edits: `settings/document.py`

Before this task: tomlkit must be installed (Prerequisites). Check: `scripts/py -c 'import tomlkit; print(tomlkit.__version__)'`. If it fails, stop and report to the controller (do not install it yourself).

**Files:**
- Create: `settings/document.py`
- Test: `tests/test_settings_document.py`

**Interfaces:**
- Consumes: `ConfigError` (`shell/config/models.py`), tomlkit.
- Produces:
  - `Path_ = tuple[str | int, ...]` (a key path from the top of the file; an int indexes `panels`)
  - `class DocumentError(ConfigError)`
  - `class UserDocument(text: str = "")` (bad TOML: `ConfigError("TOML syntax error: …")`) with `.text -> str`, `.data -> dict` (a deep copy), `.set(path, value)`, `.unset(path)` (prunes tables it leaves empty, never a panel entry; a missing key raises `DocumentError` "no such key"), `.add_panel(monitor, widget) -> int` (the new index), `.remove_panel(monitor, index)` (the last one removes `panels`), `.move_panel(monitor, index, to)`. Every edit is applied to a copy and verified against the plain-data edit; on any mismatch `DocumentError` ("… edit the file by hand") and the document is unchanged.
- Placement rule for new keys (`_container_kind`): a missing top-level table, `monitors` or a monitor's table is created as a table header (`monitors` as an implicit super table, so no empty `[monitors]` header); anything deeper is added as a dotted key inside the existing table.

- [ ] **Step 1: Write the failing test**

Create `tests/test_settings_document.py`:

```python
"""settings.document: in-place TOML edits that keep comments (pure; needs tomlkit)."""

import tomllib

import pytest

pytest.importorskip("tomlkit")

from settings.document import DocumentError, UserDocument  # noqa: E402
from shell.config.models import ConfigError  # noqa: E402

USER = """\
# my Edge Shell config
[theme]
accent = "#8fd3b6"   # mint

[monitors.HDMI-A-1]
shell = "edge"   # the test monitor
theme.accent = "#d3a68f"      # dotted override

[[monitors.HDMI-A-1.panels]]   # zero
widget = "dock"

[[monitors.HDMI-A-1.panels]]   # one
widget = "clock"
interaction.hover = false

[[monitors.HDMI-A-1.panels]]   # two
widget = "system_bar"

[monitors.DP-1]
shell = "plasma"
"""


def edited(edit, text=USER):
    doc = UserDocument(text)
    edit(doc)
    return doc.text, tomllib.loads(doc.text)


def widgets(data, monitor="HDMI-A-1"):
    return [p["widget"] for p in data["monitors"][monitor].get("panels", [])]


def test_an_unedited_document_is_byte_identical():
    assert UserDocument(USER).text == USER


def test_replacing_a_value_keeps_its_comment():
    text, data = edited(lambda d: d.set(("monitors", "HDMI-A-1", "shell"), "both"))
    assert 'shell = "both"   # the test monitor' in text
    assert "# my Edge Shell config" in text and "# zero" in text
    assert data["monitors"]["HDMI-A-1"]["shell"] == "both"


def test_a_new_key_in_an_existing_table():
    text, data = edited(lambda d: d.set(("theme", "thickness"), 12))
    assert data["theme"] == {"accent": "#8fd3b6", "thickness": 12}
    assert "# mint" in text


def test_a_new_nested_key_under_a_header_table_is_a_dotted_key():
    text, data = edited(lambda d: d.set(("theme", "border", "enabled"), True))
    assert "border.enabled = true" in text
    assert data["theme"]["border"] == {"enabled": True}


def test_a_new_key_inside_a_dotted_table_stays_in_that_monitor():
    """tomlkit writes a table added into a dotted table as a top-level [theme.shadow] header
    (the elevation would land in the global theme); the dotted form keeps it in place."""
    path = ("monitors", "HDMI-A-1", "theme", "shadow", "elevation")
    text, data = edited(lambda d: d.set(path, 80))
    assert data["monitors"]["HDMI-A-1"]["theme"]["shadow"] == {"elevation": 80}
    assert "shadow" not in data["theme"]


def test_a_panel_key_and_a_new_panel_sub_table():
    def edit(d):
        d.set(("monitors", "HDMI-A-1", "panels", 0, "depth"), 80)
        d.set(("monitors", "HDMI-A-1", "panels", 0, "handle", "shape"), "chevron")
        d.set(("monitors", "HDMI-A-1", "panels", 1, "interaction", "drag"), False)

    text, data = edited(edit)
    panels = data["monitors"]["HDMI-A-1"]["panels"]
    assert panels[0] == {"widget": "dock", "depth": 80, "handle": {"shape": "chevron"}}
    assert panels[1]["interaction"] == {"hover": False, "drag": False}
    assert 'handle.shape = "chevron"' in text


def test_a_new_monitor_gets_its_own_table():
    text, data = edited(lambda d: d.set(("monitors", "eDP-1", "shell"), "edge"))
    assert "[monitors.eDP-1]" in text
    assert data["monitors"]["eDP-1"] == {"shell": "edge"}


def test_a_new_monitor_theme_override():
    path = ("monitors", "eDP-1", "theme", "accent")
    text, data = edited(lambda d: d.set(path, "#ffffff"))
    assert data["monitors"]["eDP-1"] == {"theme": {"accent": "#ffffff"}}


def test_edits_on_an_empty_file():
    def edit(d):
        d.set(("monitors", "HDMI-A-1", "shell"), "edge")
        d.set(("theme", "frame"), "#000000")
        d.set(("layout", "gap"), 4)

    text, data = edited(edit, "")
    assert data == {
        "monitors": {"HDMI-A-1": {"shell": "edge"}},
        "theme": {"frame": "#000000"},
        "layout": {"gap": 4},
    }
    assert "[monitors]" not in text  # the monitors table is implicit


@pytest.mark.parametrize(
    "text, path, value, expected",
    [
        (  # dotted keys at the top of the file
            'theme.accent = "#112233"\n',
            ("theme", "border", "enabled"),
            True,
            {"theme": {"accent": "#112233", "border": {"enabled": True}}},
        ),
        (  # an inline table in a panel entry
            '[[monitors.X.panels]]\nwidget = "dock"\nhandle = { shape = "bar" }\n',
            ("monitors", "X", "panels", 0, "handle", "size"),
            20,
            {
                "monitors": {
                    "X": {"panels": [{"widget": "dock", "handle": {"shape": "bar", "size": 20}}]}
                }
            },
        ),
        (  # a monitor known only from its [[panels]] and [theme] headers
            '[[monitors.X.panels]]\nwidget = "dock"\n[monitors.X.theme]\naccent = "#111111"\n',
            ("monitors", "X", "layout", "gap"),
            3,
            {
                "monitors": {
                    "X": {
                        "panels": [{"widget": "dock"}],
                        "theme": {"accent": "#111111"},
                        "layout": {"gap": 3},
                    }
                }
            },
        ),
    ],
)
def test_other_toml_layouts_are_edited_in_place(text, path, value, expected):
    _, data = edited(lambda d: d.set(path, value), text)
    assert data == expected


def test_a_font_list():
    _, data = edited(lambda d: d.set(("theme", "font"), ["JetBrains Mono", "monospace"]))
    assert data["theme"]["font"] == ["JetBrains Mono", "monospace"]


def test_unset_removes_the_key_and_keeps_the_rest():
    text, data = edited(lambda d: d.unset(("theme", "accent")))
    assert "theme" not in data  # the table was left empty: pruned
    assert "# my Edge Shell config" in text and "# zero" in text


def test_unset_prunes_an_emptied_dotted_table_but_not_its_monitor():
    _, data = edited(lambda d: d.unset(("monitors", "HDMI-A-1", "theme", "accent")))
    assert data["monitors"]["HDMI-A-1"]["shell"] == "edge"
    assert "theme" not in data["monitors"]["HDMI-A-1"]


def test_unset_prunes_an_emptied_monitor():
    _, data = edited(lambda d: d.unset(("monitors", "DP-1", "shell")))
    assert "DP-1" not in data["monitors"]


def test_unset_never_removes_a_panel_entry():
    path = ("monitors", "HDMI-A-1", "panels", 1, "interaction", "hover")
    _, data = edited(lambda d: d.unset(path))
    assert data["monitors"]["HDMI-A-1"]["panels"][1] == {"widget": "clock"}


def test_unset_of_a_missing_key_is_an_error_and_changes_nothing():
    doc = UserDocument(USER)
    with pytest.raises(DocumentError, match="no such key"):
        doc.unset(("theme", "frame"))
    assert doc.text == USER


def test_add_panel():
    doc = UserDocument(USER)
    assert doc.add_panel("HDMI-A-1", "clock") == 3
    data = tomllib.loads(doc.text)
    assert widgets(data) == ["dock", "clock", "system_bar", "clock"]
    assert data["monitors"]["HDMI-A-1"]["panels"][3] == {"widget": "clock"}


def test_add_the_first_panel_of_a_monitor():
    doc = UserDocument(USER)
    assert doc.add_panel("DP-1", "dock") == 0
    assert tomllib.loads(doc.text)["monitors"]["DP-1"] == {
        "shell": "plasma",
        "panels": [{"widget": "dock"}],
    }
    doc = UserDocument("")
    assert doc.add_panel("HDMI-A-1", "dock") == 0
    assert tomllib.loads(doc.text) == {"monitors": {"HDMI-A-1": {"panels": [{"widget": "dock"}]}}}


def test_remove_panel():
    text, data = edited(lambda d: d.remove_panel("HDMI-A-1", 1))
    assert widgets(data) == ["dock", "system_bar"]
    assert "# one" not in text and "# two" in text


def test_removing_the_last_panel_removes_the_list():
    doc = UserDocument(USER)
    for _ in range(3):
        doc.remove_panel("HDMI-A-1", 0)
    data = tomllib.loads(doc.text)
    assert data["monitors"]["HDMI-A-1"] == {"shell": "edge", "theme": {"accent": "#d3a68f"}}


@pytest.mark.parametrize(
    "index, to, order",
    [
        (2, 0, ["system_bar", "dock", "clock"]),
        (0, 2, ["clock", "system_bar", "dock"]),
        (1, 0, ["clock", "dock", "system_bar"]),
        (1, 1, ["dock", "clock", "system_bar"]),
    ],
)
def test_move_panel(index, to, order):
    text, data = edited(lambda d: d.move_panel("HDMI-A-1", index, to))
    assert widgets(data) == order
    assert data["monitors"]["HDMI-A-1"]["panels"][order.index("clock")]["interaction"] == {
        "hover": False
    }


def test_move_panel_out_of_range_is_an_error():
    doc = UserDocument(USER)
    with pytest.raises(DocumentError):
        doc.move_panel("HDMI-A-1", 5, 0)
    assert doc.text == USER


def test_a_toml_syntax_error_is_a_config_error():
    with pytest.raises(ConfigError, match="TOML syntax error"):
        UserDocument("[theme\n")


def test_an_edit_that_would_change_other_keys_is_refused(monkeypatch):
    import settings.document as document

    def misplace(doc, path, value):  # what tomlkit does with a table inside a dotted table
        doc["theme"]["shadow"] = {"elevation": value}

    monkeypatch.setattr(document, "_set", misplace)
    doc = UserDocument(USER)
    with pytest.raises(DocumentError, match="by hand"):
        doc.set(("monitors", "HDMI-A-1", "theme", "shadow", "elevation"), 80)
    assert doc.text == USER


def test_data_is_a_copy():
    doc = UserDocument(USER)
    doc.data["theme"]["accent"] = "#000000"
    assert doc.data["theme"]["accent"] == "#8fd3b6"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `scripts/py -m pytest tests/test_settings_document.py -q`
Expected: collection error, `ModuleNotFoundError: No module named 'settings.document'`.

- [ ] **Step 3: Implement**

Create `settings/document.py`:

```python
"""Edit the user's config.toml in place with tomlkit, keeping comments and layout. Pure (no GTK).

Every edit is checked: the edited text is parsed back with tomllib and must equal the same edit
applied to the plain data. tomlkit can misplace a new table (a table added inside a dotted-key
table is written as a top-level header, which moves the keys to another table); such an edit
raises DocumentError instead of producing a file that means something else.

A path is a tuple of keys from the top of the file; an int indexes the panel list, e.g.
("monitors", "HDMI-A-1", "panels", 0, "handle", "shape").
"""

from __future__ import annotations

import copy
import tomllib
from collections.abc import Callable
from typing import Any

import tomlkit
from tomlkit.exceptions import TOMLKitError

from shell.config.models import ConfigError

Path_ = tuple[str | int, ...]


class DocumentError(ConfigError):
    """An edit that could not be made in place (the file is left unchanged)."""


def _container_kind(path: Path_, i: int) -> str:
    """How to create the missing key path[i]: "table" for a top-level table, a monitor's
    table or the monitors table itself (readable headers), "dotted" anywhere deeper (inside a
    [table], a [[panels]] entry or a dotted table; also always valid TOML)."""
    if i == 0 or (i == 1 and path[0] == "monitors"):
        return "table"
    return "dotted"


class UserDocument:
    def __init__(self, text: str = ""):
        try:
            self._doc = tomlkit.parse(text)
            self._data = tomllib.loads(text)
        except (TOMLKitError, tomllib.TOMLDecodeError) as exc:
            raise ConfigError(f"TOML syntax error: {exc}") from None

    @property
    def text(self) -> str:
        return tomlkit.dumps(self._doc)

    @property
    def data(self) -> dict[str, Any]:
        """Plain dicts and lists (a copy)."""
        return copy.deepcopy(self._data)

    # ---- edits ---------------------------------------------------------------------------
    def set(self, path: Path_, value: Any) -> None:
        self._edit(lambda doc: _set(doc, path, value), lambda data: _plain_set(data, path, value))

    def unset(self, path: Path_) -> None:
        """Remove the key (the value is inherited again) and any table left empty by it."""
        self._edit(lambda doc: _unset(doc, path), lambda data: _plain_unset(data, path))

    def add_panel(self, monitor: str, widget: str) -> int:
        """Append a panel entry with only its widget (every other key from the widget's
        defaults); returns its index."""
        self._edit(
            lambda doc: _add_panel(doc, monitor, widget),
            lambda data: _plain_panels(data, monitor, create=True).append({"widget": widget}),
        )
        return len(self._data["monitors"][monitor]["panels"]) - 1

    def remove_panel(self, monitor: str, index: int) -> None:
        self._edit(
            lambda doc: _remove_panel(doc, monitor, index),
            lambda data: _plain_remove_panel(data, monitor, index),
        )

    def move_panel(self, monitor: str, index: int, to: int) -> None:
        """Move the entry at `index` so it ends up at `to` (config order decides ties)."""

        def plain(data):
            panels = _plain_panels(data, monitor)
            panels.insert(to, panels.pop(index))

        self._edit(lambda doc: _move_panel(doc, monitor, index, to), plain)

    def _edit(self, on_doc: Callable[[Any], None], on_data: Callable[[dict], None]) -> None:
        expected = copy.deepcopy(self._data)
        try:
            on_data(expected)
        except (KeyError, IndexError, TypeError) as exc:
            raise DocumentError(f"cannot edit the config: no such key or entry ({exc})") from None
        doc = tomlkit.parse(tomlkit.dumps(self._doc))  # edit a copy; keep self on failure
        try:
            on_doc(doc)
            got = tomllib.loads(tomlkit.dumps(doc))
        except (TOMLKitError, tomllib.TOMLDecodeError, KeyError, IndexError, TypeError) as exc:
            raise DocumentError(f"cannot edit the config in place: {exc}") from None
        if got != expected:
            raise DocumentError(
                "cannot edit the config in place without changing other keys; edit the file by hand"
            )
        self._doc, self._data = doc, expected


# ---- tomlkit side ------------------------------------------------------------------------


def _set(doc, path: Path_, value: Any) -> None:
    node = doc
    for i, key in enumerate(path[:-1]):
        if isinstance(key, int):
            node = node[key]
            continue
        if key not in node:
            if _container_kind(path, i) == "dotted":
                node.add(tomlkit.key([str(k) for k in path[i:]]), value)
                return
            node[key] = tomlkit.table(is_super_table=key == "monitors")
        node = node[key]
    node[path[-1]] = value


def _unset(doc, path: Path_) -> None:
    chain = [doc]
    for key in path[:-1]:
        chain.append(chain[-1][key])
    del chain[-1][path[-1]]
    # prune tables left empty, deepest first; never a [[panels]] entry (an int key)
    for depth in range(len(path) - 1, 0, -1):
        if isinstance(path[depth - 1], int) or isinstance(path[depth], int):
            break
        if len(chain[depth]) == 0:
            del chain[depth - 1][path[depth - 1]]
        else:
            break


def _monitor_table(doc, monitor: str):
    if "monitors" not in doc:
        doc["monitors"] = tomlkit.table(is_super_table=True)
    if monitor not in doc["monitors"]:
        doc["monitors"][monitor] = tomlkit.table()
    return doc["monitors"][monitor]


def _add_panel(doc, monitor: str, widget: str) -> None:
    table = _monitor_table(doc, monitor)
    entry = tomlkit.table()
    entry["widget"] = widget
    if "panels" not in table:
        table["panels"] = tomlkit.aot()
    table["panels"].append(entry)


def _remove_panel(doc, monitor: str, index: int) -> None:
    table = doc["monitors"][monitor]
    del table["panels"][index]
    if len(table["panels"]) == 0:
        del table["panels"]


def _move_panel(doc, monitor: str, index: int, to: int) -> None:
    panels = doc["monitors"][monitor]["panels"]
    entry = panels[index]
    del panels[index]
    panels.insert(to, entry)


# ---- plain-data side (what the edit must mean) -------------------------------------------


def _plain_set(data: dict, path: Path_, value: Any) -> None:
    node = data
    for key in path[:-1]:
        node = node[key] if isinstance(key, int) else node.setdefault(key, {})
    node[path[-1]] = value


def _plain_unset(data: dict, path: Path_) -> None:
    chain = [data]
    for key in path[:-1]:
        chain.append(chain[-1][key])
    del chain[-1][path[-1]]
    for depth in range(len(path) - 1, 0, -1):
        if isinstance(path[depth - 1], int) or isinstance(path[depth], int):
            break
        if not chain[depth]:
            del chain[depth - 1][path[depth - 1]]
        else:
            break


def _plain_panels(data: dict, monitor: str, create: bool = False) -> list:
    if create:
        return data.setdefault("monitors", {}).setdefault(monitor, {}).setdefault("panels", [])
    return data["monitors"][monitor]["panels"]


def _plain_remove_panel(data: dict, monitor: str, index: int) -> None:
    panels = _plain_panels(data, monitor)
    del panels[index]
    if not panels:
        del data["monitors"][monitor]["panels"]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `scripts/py -m pytest tests/test_settings_document.py -q`
Expected: `30 passed`.

- [ ] **Step 5: VERIFY and commit**

Run VERIFY. Expected: `1237 passed`.

```bash
git add settings/document.py tests/test_settings_document.py
git commit -m "feat(settings): verified in-place TOML edits that keep comments" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: The edit session: `settings/session.py`

**Files:**
- Create: `settings/session.py`
- Test: `tests/test_settings_session.py`

**Interfaces:**
- Consumes: `read_text`, `write_atomic`, `write_backup` (Task 2); `UserDocument` (Task 3); `load_config_text`, `DEFAULT_PATH` (Task 1, `shell/config/loader.py`); `validate_widgets` (`shell/registry.py`); `ConfigStore` and `diff_configs` in the tests.
- Produces:
  - `check_text(text: str, default_path: Path = DEFAULT_PATH) -> Config` (the shell's rules, including unknown widgets)
  - `class ChangedOutside(ConfigError)`
  - `class SettingsSession(path: Path, default_path: Path = DEFAULT_PATH)` with attributes `path`, `default_path`, `text`, `start_text`, `user` (plain dict of the file), `config: Config | None` (None while the file is invalid), `error: str | None`, `history: list[str]`, `backed_up: bool`; methods `reload()`, `changed_outside() -> bool`, `apply(edit: Callable[[UserDocument], Any]) -> Config` (raises `ChangedOutside` after re-reading, or `ConfigError` with nothing written), `undo() -> bool`, `revert()`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_settings_session.py`:

```python
"""settings.session: validate, write atomically, back up, undo, revert, hand edits (pure)."""

import pytest

pytest.importorskip("tomlkit")

from settings.session import ChangedOutside, SettingsSession, check_text  # noqa: E402
from shell.config.diff import Change, diff_configs  # noqa: E402
from shell.config.models import ConfigError  # noqa: E402
from shell.config.store import ConfigStore  # noqa: E402

USER = """\
# test config
[monitors.HDMI-A-1]
shell = "edge"   # test monitor

[[monitors.HDMI-A-1.panels]]
widget = "dock"
"""
SHELL = ("monitors", "HDMI-A-1", "shell")
DEPTH = ("monitors", "HDMI-A-1", "panels", 0, "depth")


@pytest.fixture
def path(tmp_path, fake_registry):
    p = tmp_path / "config.toml"
    p.write_text(USER)
    return p


def test_opening_reads_and_checks_the_file(path):
    s = SettingsSession(path)
    assert s.text == USER and s.error is None
    assert s.config.monitor("HDMI-A-1").shell == "edge"
    assert s.user["monitors"]["HDMI-A-1"]["panels"] == [{"widget": "dock"}]
    assert not s.changed_outside()


def test_a_missing_file_is_the_defaults(tmp_path, fake_registry):
    s = SettingsSession(tmp_path / "config.toml")
    assert s.text == "" and s.user == {} and s.config.monitors == {}


def test_an_invalid_file_opens_with_its_error(path):
    path.write_text('[monitors.HDMI-A-1]\nshell = "sideways"\n')
    s = SettingsSession(path)
    assert s.config is None and "monitors.HDMI-A-1.shell" in s.error


def test_apply_writes_a_valid_change_keeping_comments(path):
    s = SettingsSession(path)
    config = s.apply(lambda d: d.set(DEPTH, 80))
    assert config.monitor("HDMI-A-1").panels[0].depth == 80
    text = path.read_text()
    assert "depth = 80" in text and "# test monitor" in text
    assert s.text == text and s.user["monitors"]["HDMI-A-1"]["panels"][0]["depth"] == 80


def test_an_invalid_change_is_not_written(path):
    s = SettingsSession(path)
    with pytest.raises(ConfigError, match="depth"):
        s.apply(lambda d: d.set(DEPTH, 5))  # below the minimum of 16
    assert path.read_text() == USER and s.history == []
    assert not (path.parent / "config.toml.bak").exists()


def test_an_unknown_widget_is_not_written(path):
    s = SettingsSession(path)
    with pytest.raises(ConfigError, match="unknown widget"):
        s.apply(lambda d: d.add_panel("HDMI-A-1", "nope"))
    assert path.read_text() == USER


def test_a_cross_field_rule_is_not_written(path):
    s = SettingsSession(path)
    s.apply(lambda d: d.set(("monitors", "HDMI-A-1", "panels", 0, "pos"), 400))
    with pytest.raises(ConfigError, match="pos cannot be combined"):
        s.apply(lambda d: d.set(("monitors", "HDMI-A-1", "panels", 0, "align"), "end"))


def test_the_first_write_backs_up_the_original_once(path):
    s = SettingsSession(path)
    s.apply(lambda d: d.set(DEPTH, 80))
    s.apply(lambda d: d.set(DEPTH, 90))
    assert (path.parent / "config.toml.bak").read_text() == USER


def test_undo_steps_back_one_change_at_a_time(path):
    s = SettingsSession(path)
    s.apply(lambda d: d.set(DEPTH, 80))
    after_first = path.read_text()
    s.apply(lambda d: d.set(SHELL, "both"))
    assert s.undo() is True
    assert path.read_text() == after_first and s.config.monitor("HDMI-A-1").shell == "edge"
    assert s.undo() is True
    assert path.read_text() == USER
    assert s.undo() is False


def test_revert_goes_back_to_the_start_of_the_session(path):
    s = SettingsSession(path)
    s.apply(lambda d: d.set(DEPTH, 80))
    s.apply(lambda d: d.set(SHELL, "none"))
    s.revert()
    assert path.read_text() == USER and s.history == []
    assert s.config.monitor("HDMI-A-1").shell == "edge"


def test_revert_of_a_session_that_started_without_a_file(tmp_path, fake_registry):
    path = tmp_path / "config.toml"
    s = SettingsSession(path)
    s.apply(lambda d: d.set(("monitors", "HDMI-A-1", "shell"), "edge"))
    s.revert()
    assert path.read_text() == "" and s.config.monitors == {}


def test_a_hand_edit_is_never_overwritten(path):
    s = SettingsSession(path)
    path.write_text(USER + '\n[theme]\naccent = "#112233"\n')  # edited by hand meanwhile
    assert s.changed_outside()
    with pytest.raises(ChangedOutside, match="changed outside"):
        s.apply(lambda d: d.set(DEPTH, 80))
    assert "depth" not in path.read_text()
    assert s.config.theme.accent == "#112233"  # re-read
    s.apply(lambda d: d.set(DEPTH, 80))  # the next change applies on top of the hand edit
    assert 'accent = "#112233"' in path.read_text() and "depth = 80" in path.read_text()


def test_undo_after_a_hand_edit_rereads_instead(path):
    s = SettingsSession(path)
    s.apply(lambda d: d.set(DEPTH, 80))
    path.write_text(USER)
    with pytest.raises(ChangedOutside):
        s.undo()
    assert s.history == [] and s.text == USER


def test_an_edit_can_fix_an_invalid_file(path):
    path.write_text('[monitors.HDMI-A-1]\nshell = "sideways"\n')
    s = SettingsSession(path)
    s.apply(lambda d: d.set(SHELL, "edge"))
    assert s.error is None and s.config.monitor("HDMI-A-1").shell == "edge"


def test_check_text_uses_the_registry(fake_registry):
    with pytest.raises(ConfigError, match="unknown widget"):
        check_text('[[monitors.X.panels]]\nwidget = "nope"\n')


@pytest.mark.parametrize(
    "path_, value, kind",
    [
        (("theme", "accent"), "#112233", "restyle"),
        (DEPTH, 80, "panel-rebuild"),
        (("monitors", "HDMI-A-1", "panels", 0, "state"), "collapsed", "panel-state"),
        (("monitors", "HDMI-A-1", "panels", 0, "handle", "shape"), "bar", "panel-handle"),
        (("monitors", "HDMI-A-1", "layout", "gap"), 20, "relayout"),
        (("theme", "thickness"), 12, "rebuild-monitor"),
        (SHELL, "plasma", "rebuild-monitor"),
    ],
)
def test_a_written_change_reloads_in_the_shell_as_the_expected_kind(path, path_, value, kind):
    """The running shell's ConfigStore reloads the file the session wrote; the diff kind is
    the cheap in-place one where the shell has one (spec 6, live reload table)."""
    store = ConfigStore(path)
    SettingsSession(path).apply(lambda d: d.set(path_, value))
    old, new = store.reload()
    assert [c.kind for c in diff_configs(old, new)] == [kind]


def test_adding_a_panel_reloads_as_panel_add(path):
    store = ConfigStore(path)
    SettingsSession(path).apply(lambda d: d.add_panel("HDMI-A-1", "clock"))
    old, new = store.reload()
    assert diff_configs(old, new) == [Change("panel-add", "HDMI-A-1", 1)]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `scripts/py -m pytest tests/test_settings_session.py -q`
Expected: collection error, `ModuleNotFoundError: No module named 'settings.session'`.

- [ ] **Step 3: Implement**

Create `settings/session.py`:

```python
"""One settings-window session on the user config file. Pure (no GTK).

Every change is applied to the file's current text with settings.document, checked with the
shell's own rules (shell.config.loader + registry.validate_widgets) and only then written,
atomically; the running shell picks it up through its file watcher. A change the shell would
reject is never written. Before the first write of a session the file is copied to
config.toml.bak (`main.py --restore-config` puts it back).
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
        self.backed_up = False
        self.start_text = ""
        self.text = ""
        self.user: dict[str, Any] = {}  # the user file as plain data
        self.config: Config | None = None  # None while the file on disk is invalid
        self.error: str | None = None  # why the file on disk is invalid
        self.reload()
        self.start_text = self.text

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

    def apply(self, edit: Edit) -> Config:
        """Apply one change and write it; returns the new config. Raises ChangedOutside (the
        session re-read the file, undo history cleared) or ConfigError (nothing written)."""
        if self.changed_outside():
            self.reload()
            self.history.clear()
            raise ChangedOutside(
                f"{self.path} was changed outside the settings window; it has been re-read "
                "and the last change was not applied"
            )
        doc = UserDocument(self.text)
        edit(doc)
        config = check_text(doc.text, self.default_path)
        self._write(doc.text)
        self.config, self.error = config, None
        return config

    def undo(self) -> bool:
        """Put back the text before the last change; False when there is nothing to undo."""
        if not self.history:
            return False
        if self.changed_outside():
            self.reload()
            self.history.clear()
            raise ChangedOutside(f"{self.path} was changed outside the settings window")
        previous = self.history.pop()
        files.write_atomic(self.path, previous)
        self.reload()
        return True

    def revert(self) -> None:
        """Back to the file as it was when the session started (no validation: it was the
        file on disk); also when it was changed by hand since."""
        files.write_atomic(self.path, self.start_text)
        self.history.clear()
        self.reload()

    def _write(self, text: str) -> None:
        if not self.backed_up:
            files.write_backup(self.path)
            self.backed_up = True
        files.write_atomic(self.path, text)
        self.history.append(self.text)
        self.text = text
        self.user = tomllib.loads(text)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `scripts/py -m pytest tests/test_settings_session.py -q`
Expected: `23 passed`.

- [ ] **Step 5: VERIFY and commit**

Run VERIFY. Expected: `1260 passed`.

```bash
git add settings/session.py tests/test_settings_session.py
git commit -m "feat(settings): edit session: check by the shell's rules, write, undo, revert" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: The form description: `settings/form.py`

**Files:**
- Create: `settings/form.py`
- Test: `tests/test_settings_form.py`

**Interfaces:**
- Consumes: `Config`, `COLOR_FIELDS`, `HANDLE_SHAPES` (`shell/config/models.py`).
- Produces:
  - `FieldKind = Literal["color", "int", "bool", "enum", "fonts", "length", "widget", "deprecated"]`
  - `FieldSpec(key, label, kind, choices=(), minimum=None, maximum=None, hint="")` (frozen)
  - `SectionSpec(key, label, fields, sections=())` with `.field(key)`, `.section(key)`
  - `ConfigForm(theme, layout, monitor, panel)`; `config_form(widgets: tuple[str, ...]) -> ConfigForm`; `section_for(schema, name, key="", label="", widgets=(), skip=()) -> SectionSpec` (raises `ValueError` for an unknown kind)
  - `COLOR_KEYS`, `HINTS`, `MODE_HINTS`, `LENGTH_PX = (60, 4000)`, `LENGTH_PERCENT = (1, 100)`, `LENGTH_MODES = ("px", "fill", "content", "percent")`
  - `rgba_to_hex(r, g, b, a) -> str`, `split_length(value) -> (mode, number | None)`, `join_length(mode, number) -> int | str`, `parse_fonts(text) -> list[str]`, `format_fonts(fonts) -> str`

- [ ] **Step 1: Write the failing test**

Create `tests/test_settings_form.py`:

```python
"""settings.form: the form description generated from the JSON schema (pure)."""

import pytest

from settings.form import (
    COLOR_KEYS,
    MODE_HINTS,
    config_form,
    format_fonts,
    join_length,
    parse_fonts,
    rgba_to_hex,
    section_for,
    split_length,
)
from shell.config.models import COLOR_FIELDS, HANDLE_SHAPES, Config

WIDGETS = ("clock", "dock", "system_bar")


@pytest.fixture
def form():
    return config_form(WIDGETS)


def test_theme_colours_are_colour_fields(form):
    for key in COLOR_FIELDS:
        assert form.theme.field(key).kind == "color"


def test_theme_numbers_take_their_bounds_from_the_schema(form):
    thickness = form.theme.field("thickness")
    assert (thickness.kind, thickness.minimum, thickness.maximum) == ("int", 2, 64)
    assert form.theme.field("duration_ms").maximum == 5000
    assert form.theme.field("thickness").hint == "px"


def test_theme_font_is_a_font_list(form):
    assert form.theme.field("font").kind == "fonts"


def test_nested_theme_tables_are_sub_sections(form):
    assert [s.key for s in form.theme.sections] == ["border", "shadow", "handle_style"]
    border = form.theme.section("border")
    assert border.field("enabled").kind == "bool"
    assert (border.field("width").minimum, border.field("width").maximum) == (1, 16)
    assert border.field("color").kind == "color"
    assert form.theme.section("shadow").field("elevation").maximum == 100


def test_handle_shapes_come_from_the_model(form):
    shape = form.theme.section("handle_style").field("shape")
    assert shape.kind == "enum" and shape.choices == HANDLE_SHAPES
    assert form.panel.section("handle").field("shape").choices == HANDLE_SHAPES


def test_layout_gap(form):
    gap = form.layout.field("gap")
    assert (gap.kind, gap.minimum, gap.maximum) == ("int", 0, 400)


def test_monitor_section_is_the_shell_mode_only(form):
    assert [f.key for f in form.monitor.fields] == ["shell"]
    assert form.monitor.field("shell").choices == ("edge", "plasma", "both", "none")
    assert form.monitor.sections == ()
    assert set(MODE_HINTS) == set(form.monitor.field("shell").choices)


def test_panel_fields(form):
    p = form.panel
    assert p.field("widget").kind == "widget" and p.field("widget").choices == WIDGETS
    assert p.field("edge").choices == ("top", "bottom", "left", "right")
    assert p.field("align").choices == ("start", "center", "end")
    assert (p.field("offset").minimum, p.field("offset").maximum) == (-20000, 20000)
    assert p.field("length").kind == "length"
    assert (p.field("depth").minimum, p.field("depth").maximum) == (16, 2000)
    assert p.field("state").choices == ("collapsed", "extended")
    assert p.field("pos").kind == "deprecated"
    assert [s.key for s in p.sections] == ["handle", "interaction"]
    assert p.section("interaction").field("hover").kind == "bool"
    handle = p.section("handle")
    assert (handle.field("size").minimum, handle.field("size").maximum) == (4, 40)
    assert handle.field("hover_color").kind == "color"


def test_every_string_field_is_known_to_the_form():
    """A new string key in the models must be classified here (colour, font, enum, ...):
    otherwise section_for raises instead of guessing."""
    schema = Config.model_json_schema()
    for name, model in schema["$defs"].items():
        for key, prop in model["properties"].items():
            options = [o for o in prop.get("anyOf", [prop]) if o.get("type") != "null"]
            plain = [o for o in options if o.get("type") == "string" and "enum" not in o]
            if plain and key not in ("widget", "pos", "length"):
                assert key in COLOR_KEYS, f"{name}.{key}"


def test_an_unknown_field_kind_is_an_error():
    schema = {"$defs": {"M": {"properties": {"blob": {"type": "object"}}}}}
    with pytest.raises(ValueError, match="blob"):
        section_for(schema, "M")


@pytest.mark.parametrize(
    "rgba, expected",
    [
        ((0.0, 0.0, 0.0, 1.0), "#000000"),
        ((1.0, 1.0, 1.0, 1.0), "#ffffff"),
        ((143 / 255, 211 / 255, 182 / 255, 1.0), "#8fd3b6"),
        ((0.0, 0.0, 0.0, 128 / 255), "#00000080"),
        ((0.0, 0.0, 0.0, 0.0), "#00000000"),
        ((1.2, -0.1, 0.5, 1.0), "#ff0080"),
    ],
)
def test_rgba_to_hex(rgba, expected):
    assert rgba_to_hex(*rgba) == expected


@pytest.mark.parametrize(
    "value, split",
    [
        (300, ("px", 300.0)),
        ("fill", ("fill", None)),
        ("content", ("content", None)),
        ("50%", ("percent", 50.0)),
        ("12.5%", ("percent", 12.5)),
    ],
)
def test_lengths_round_trip(value, split):
    assert split_length(value) == split
    assert join_length(*split) == value


def test_join_length_rounds_px_and_ignores_the_number_for_fill():
    assert join_length("px", 299.6) == 300
    assert join_length("fill", 42.0) == "fill"
    with pytest.raises(ValueError):
        join_length("inches", 3.0)
    with pytest.raises(ValueError):
        split_length("wide")


def test_fonts_round_trip():
    assert parse_fonts(" Hack Nerd Font Mono , JetBrains Mono,, monospace ") == [
        "Hack Nerd Font Mono",
        "JetBrains Mono",
        "monospace",
    ]
    assert format_fonts(["A", "b c"]) == "A, b c"
    assert parse_fonts("  ") == []
```

- [ ] **Step 2: Run it to verify it fails**

Run: `scripts/py -m pytest tests/test_settings_form.py -q`
Expected: collection error, `ModuleNotFoundError: No module named 'settings.form'`.

- [ ] **Step 3: Implement**

Create `settings/form.py`:

```python
"""Form description generated from the config models' JSON schema. Pure: no GTK, no tomlkit.

A form is a tree of SectionSpec (one per TOML table) holding FieldSpec (one per key). The GTK
renderer (settings.fields, settings.window) turns each FieldSpec into one row; everything a
row needs (kind, bounds, choices) is here, so it is tested without a display. The values shown
in the rows come from settings.values.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from shell.config.models import COLOR_FIELDS, Config

FieldKind = Literal["color", "int", "bool", "enum", "fonts", "length", "widget", "deprecated"]

# Keys holding a #rrggbb / #rrggbbaa colour. The models check them with a field validator,
# which the JSON schema does not show, so they are recognised by name (pinned by a test).
COLOR_KEYS = frozenset(COLOR_FIELDS) | {"color", "hover_color"}
LENGTH_PX = (60, 4000)  # shell.config.models.check_length
LENGTH_PERCENT = (1, 100)
LENGTH_MODES = ("px", "fill", "content", "percent")
HINTS = {
    "thickness": "px",
    "radius": "px",
    "peek": "px",
    "hover_zone": "px",
    "duration_ms": "ms",
    "width": "px",
    "elevation": "% (100 % = 48 px)",
    "size": "px along the edge",
    "weight": "px",
    "gap": "px between neighbouring panels",
    "offset": "px from the aligned end",
    "depth": "px past the frame",
    "min_length": "px",
    "max_length": "px",
    "pos": "deprecated: reset it and use align and offset",
}
MODE_HINTS = {
    "edge": "Edge Shell frame and panels",
    "plasma": "no Edge Shell here; Plasma's panels stay as they are",
    "both": "Edge Shell frame and panels next to Plasma's panel: keep Edge Shell panels off "
    "the edge Plasma's panel uses",
    "none": "no Edge Shell here (the same as plasma until the Plasma panel toggle exists)",
}


@dataclass(frozen=True)
class FieldSpec:
    key: str  # the key inside its table
    label: str
    kind: FieldKind
    choices: tuple[str, ...] = ()
    minimum: int | None = None
    maximum: int | None = None
    hint: str = ""


@dataclass(frozen=True)
class SectionSpec:
    key: str  # the table's key inside its parent ("" for the top of a form)
    label: str
    fields: tuple[FieldSpec, ...]
    sections: tuple[SectionSpec, ...] = ()

    def field(self, key: str) -> FieldSpec:
        return next(f for f in self.fields if f.key == key)

    def section(self, key: str) -> SectionSpec:
        return next(s for s in self.sections if s.key == key)


def _options(prop: dict) -> list[dict]:
    """The non-null alternatives of a property (an optional key is anyOf [..., null])."""
    return [o for o in prop.get("anyOf", [prop]) if o.get("type") != "null"]


def _field(key: str, prop: dict, widgets: tuple[str, ...]) -> FieldSpec:
    first = _options(prop)[0]
    common = {"key": key, "label": prop.get("title", key), "hint": HINTS.get(key, "")}
    if key == "widget":
        return FieldSpec(kind="widget", choices=widgets, **common)
    if key == "pos":
        return FieldSpec(kind="deprecated", **common)
    if key == "length":
        return FieldSpec(kind="length", minimum=LENGTH_PX[0], maximum=LENGTH_PX[1], **common)
    if key in COLOR_KEYS:
        return FieldSpec(kind="color", **common)
    if "enum" in first:
        return FieldSpec(kind="enum", choices=tuple(first["enum"]), **common)
    if first.get("type") == "boolean":
        return FieldSpec(kind="bool", **common)
    if first.get("type") == "integer":
        return FieldSpec(
            kind="int", minimum=first.get("minimum"), maximum=first.get("maximum"), **common
        )
    if key == "font" and first.get("type") == "array":
        return FieldSpec(kind="fonts", **common)
    raise ValueError(f"no form field for {key!r}: {prop}")


def section_for(
    schema: dict,
    name: str,
    key: str = "",
    label: str = "",
    widgets: tuple[str, ...] = (),
    skip: tuple[str, ...] = (),
) -> SectionSpec:
    """The section for the model `name` in `schema["$defs"]`. Nested models become
    sub-sections; keys in `skip` are left out (the panel list has its own editor)."""
    model = schema["$defs"][name]
    fields: list[FieldSpec] = []
    sections: list[SectionSpec] = []
    for fkey, prop in model["properties"].items():
        if fkey in skip:
            continue
        ref = _options(prop)[0].get("$ref")
        if ref is not None:
            sub = ref.rsplit("/", 1)[-1]
            title = fkey.replace("_", " ").capitalize()
            sections.append(section_for(schema, sub, fkey, title, widgets))
        else:
            fields.append(_field(fkey, prop, widgets))
    return SectionSpec(key, label or name, tuple(fields), tuple(sections))


@dataclass(frozen=True)
class ConfigForm:
    theme: SectionSpec  # [theme], also the per-monitor [monitors.NAME.theme] override
    layout: SectionSpec  # [layout], also [monitors.NAME.layout]
    monitor: SectionSpec  # [monitors.NAME] keys other than its tables: the shell mode
    panel: SectionSpec  # one [[monitors.NAME.panels]] entry


def config_form(widgets: tuple[str, ...]) -> ConfigForm:
    """Every section the settings window shows; `widgets` is registry.widget_names().

    Per-monitor overrides use the base models (Theme, LayoutSettings), not ThemeOverride /
    LayoutOverride: those are built with create_model from the bare annotations and lose the
    bounds (their schema has no minimum / maximum)."""
    schema = Config.model_json_schema()
    return ConfigForm(
        theme=section_for(schema, "Theme", "theme", "Theme"),
        layout=section_for(schema, "LayoutSettings", "layout", "Layout"),
        monitor=section_for(
            schema, "MonitorConfig", "", "Monitor", skip=("theme", "layout", "panels")
        ),
        panel=section_for(schema, "PanelConfig", "", "Panel", widgets=widgets),
    )


# ---- value conversions between the config and the editor widgets ------------------------


def rgba_to_hex(red: float, green: float, blue: float, alpha: float) -> str:
    """A colour chooser's 0..1 channels as #rrggbb, or #rrggbbaa when it is not opaque."""
    parts = [round(max(0.0, min(1.0, c)) * 255) for c in (red, green, blue, alpha)]
    text = "#" + "".join(f"{p:02x}" for p in parts[:3])
    return text if parts[3] == 255 else text + f"{parts[3]:02x}"


def split_length(value: int | str) -> tuple[str, float | None]:
    """A panel length as (mode, number): 300 -> ("px", 300), "fill" -> ("fill", None),
    "content" -> ("content", None), "12.5%" -> ("percent", 12.5)."""
    if isinstance(value, int):
        return "px", float(value)
    if value in ("fill", "content"):
        return value, None
    if value.endswith("%"):
        return "percent", float(value[:-1])
    raise ValueError(f"not a panel length: {value!r}")


def join_length(mode: str, number: float | None) -> int | str:
    """The inverse of split_length; the number is ignored for fill and content."""
    if mode == "px":
        return int(round(number or 0))
    if mode in ("fill", "content"):
        return mode
    if mode == "percent":
        text = f"{number:.1f}".rstrip("0").rstrip(".")
        return f"{text}%"
    raise ValueError(f"unknown length mode {mode!r}")


def parse_fonts(text: str) -> list[str]:
    """'Hack Nerd Font Mono, monospace' -> ['Hack Nerd Font Mono', 'monospace']."""
    return [name.strip() for name in text.split(",") if name.strip()]


def format_fonts(fonts: list[str]) -> str:
    return ", ".join(fonts)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `scripts/py -m pytest tests/test_settings_form.py -q`
Expected: `23 passed`.

- [ ] **Step 5: VERIFY and commit**

Run VERIFY. Expected: `1283 passed`.

```bash
git add settings/form.py tests/test_settings_form.py
git commit -m "feat(settings): form description generated from the JSON schema" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Values in effect: `settings/values.py`

**Files:**
- Create: `settings/values.py`
- Test: `tests/test_settings_values.py`

**Interfaces:**
- Consumes: `Config` (`shell/config/models.py`), `request_for`, `requests_for` (`shell/registry.py`), `layout_monitor` (`shell/panel_layout.py`), `Output` (`shell/outputs.py`).
- Produces:
  - `FieldValue(value, is_set: bool, source: str)` (frozen)
  - `lookup(data: dict, path: tuple) -> (found: bool, value)`
  - `field_value(config: Config, user: dict, path: tuple) -> FieldValue` (paths under `theme`, `layout`, `monitors.NAME.shell|theme|layout|panels.I.…`; `KeyError` otherwise). Sources: `your config`, `default`, `global theme`, `global layout`, `widget default`, `theme`, `not set`.
  - `monitor_names(config, outputs: list[Output]) -> list[tuple[str, bool]]` (connected first in kscreen order, then configured but disconnected ones by name)
  - `layout_preview(config, name, width, height) -> list[str]` (the shell's layout warnings)

- [ ] **Step 1: Write the failing test**

Create `tests/test_settings_values.py`:

```python
"""settings.values: the value each field shows and where it comes from (pure)."""

import pytest

from settings.values import FieldValue, field_value, layout_preview, lookup, monitor_names
from shell.outputs import Output

USER = {
    "theme": {"accent": "#112233", "border": {"width": 3}},
    "monitors": {
        "HDMI-A-1": {
            "shell": "edge",
            "theme": {"accent": "#d3a68f"},
            "panels": [
                {"widget": "dock", "depth": 80, "handle": {"shape": "bar"}},
                {"widget": "bar", "interaction": {"hover": False}},
            ],
        }
    },
}


@pytest.fixture
def config(make_config, fake_registry):
    return make_config(theme=USER["theme"], monitors=USER["monitors"])


def test_lookup():
    assert lookup(USER, ("theme", "accent")) == (True, "#112233")
    assert lookup(USER, ("monitors", "HDMI-A-1", "panels", 1, "widget")) == (True, "bar")
    assert lookup(USER, ("monitors", "HDMI-A-1", "panels", 5, "widget")) == (False, None)
    assert lookup(USER, ("theme", "accent", "x")) == (False, None)
    assert lookup({}, ("layout", "gap")) == (False, None)


def test_global_theme(config):
    assert field_value(config, USER, ("theme", "accent")) == FieldValue(
        "#112233", True, "your config"
    )
    assert field_value(config, USER, ("theme", "frame")) == FieldValue("#0b0c0d", False, "default")
    assert field_value(config, USER, ("theme", "border", "width")).value == 3
    assert field_value(config, USER, ("theme", "border", "enabled")) == FieldValue(
        False, False, "default"
    )
    assert field_value(config, USER, ("layout", "gap")) == FieldValue(8, False, "default")


def test_monitor_mode(config):
    assert field_value(config, USER, ("monitors", "HDMI-A-1", "shell")).value == "edge"
    assert field_value(config, USER, ("monitors", "DP-1", "shell")) == FieldValue(
        "plasma", False, "default"
    )


def test_monitor_theme_override_inherits_the_global_theme(config):
    mon = ("monitors", "HDMI-A-1", "theme")
    assert field_value(config, USER, (*mon, "accent")) == FieldValue("#d3a68f", True, "your config")
    assert field_value(config, USER, (*mon, "border", "width")) == FieldValue(
        3, False, "global theme"
    )
    assert field_value(config, USER, ("monitors", "HDMI-A-1", "layout", "gap")) == FieldValue(
        8, False, "global layout"
    )


def test_panel_keys_fall_back_to_the_widget_defaults(config):
    p0 = ("monitors", "HDMI-A-1", "panels", 0)
    p1 = ("monitors", "HDMI-A-1", "panels", 1)
    assert field_value(config, USER, (*p0, "depth")) == FieldValue(80, True, "your config")
    assert field_value(config, USER, (*p0, "edge")) == FieldValue("bottom", False, "widget default")
    assert field_value(config, USER, (*p0, "length")).value == 560
    assert field_value(config, USER, (*p1, "state")).value == "collapsed"
    assert field_value(config, USER, (*p1, "pos")) == FieldValue(None, False, "not set")
    assert field_value(config, USER, (*p0, "min_length")) == FieldValue(None, False, "not set")
    assert field_value(config, USER, (*p0, "widget")) == FieldValue("dock", True, "your config")


def test_panel_handle_and_interaction(config):
    p0 = ("monitors", "HDMI-A-1", "panels", 0)
    p1 = ("monitors", "HDMI-A-1", "panels", 1)
    assert field_value(config, USER, (*p0, "handle", "shape")) == FieldValue(
        "bar", True, "your config"
    )
    assert field_value(config, USER, (*p0, "handle", "size")) == FieldValue(15, False, "theme")
    # the panel's monitor theme (accent override does not touch the handle colours)
    assert field_value(config, USER, (*p0, "handle", "color")) == FieldValue(
        "#7b7f84", False, "theme"
    )
    assert field_value(config, USER, (*p0, "handle", "hover_color")).value == "#e6e8ea"
    assert field_value(config, USER, (*p0, "handle", "offset")) == FieldValue(
        0, False, "widget default"
    )
    assert field_value(config, USER, (*p1, "interaction", "hover")) == FieldValue(
        False, True, "your config"
    )
    assert field_value(config, USER, (*p1, "interaction", "click")) == FieldValue(
        True, False, "default"
    )


def test_unknown_paths_are_errors(config):
    with pytest.raises(KeyError):
        field_value(config, USER, ("nope",))
    with pytest.raises(KeyError):
        field_value(config, USER, ("monitors", "HDMI-A-1", "nope"))


def test_monitor_names_lists_connected_then_configured(make_config):
    config = make_config(monitors={"eDP-1": {"shell": "edge"}, "HDMI-A-1": {"shell": "edge"}})
    outputs = [Output("HDMI-A-1", 0, 0, 1920, 1080), Output("DP-1", 0, 1080, 1920, 1080)]
    assert monitor_names(config, outputs) == [
        ("HDMI-A-1", True),
        ("DP-1", True),
        ("eDP-1", False),
    ]
    assert monitor_names(config, []) == [("HDMI-A-1", False), ("eDP-1", False)]


def test_layout_preview_reports_what_the_shell_would(make_config, fake_registry):
    clean = make_config(monitors={"HDMI-A-1": {"shell": "edge", "panels": [{"widget": "dock"}]}})
    assert layout_preview(clean, "HDMI-A-1", 1920, 1080) == []
    too_long = make_config(
        monitors={"HDMI-A-1": {"shell": "edge", "panels": [{"widget": "dock", "length": 3000}]}}
    )
    warnings = layout_preview(too_long, "HDMI-A-1", 1920, 1080)
    assert len(warnings) == 1 and warnings[0].startswith("monitors.HDMI-A-1")
    assert layout_preview(too_long, "HDMI-A-1", 3840, 2160) == []
```

- [ ] **Step 2: Run it to verify it fails**

Run: `scripts/py -m pytest tests/test_settings_values.py -q`
Expected: collection error, `ModuleNotFoundError: No module named 'settings.values'`.

- [ ] **Step 3: Implement**

Create `settings/values.py`:

```python
"""What each settings field shows: the value in effect and where it comes from. Pure.

A field is addressed by its TOML key path (settings.document.Path_). `is_set` says the user
file sets that key (the row's reset button removes it); `source` names where an unset value
is inherited from.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shell.config.models import Config
from shell.outputs import Output
from shell.panel_layout import layout_monitor
from shell.registry import request_for, requests_for

PANEL_REQUEST_KEYS = ("widget", "edge", "align", "offset", "order", "length", "depth", "state")
PANEL_OWN_KEYS = ("pos", "min_length", "max_length")  # no widget default: None when unset


@dataclass(frozen=True)
class FieldValue:
    value: Any  # in effect now (None: not set anywhere, e.g. min_length)
    is_set: bool  # the user file sets this key
    source: str  # "your config", or where the value is inherited from


def lookup(data: dict, path: tuple) -> tuple[bool, Any]:
    """(found, value) of a key path in plain data; ints index lists."""
    node: Any = data
    for key in path:
        try:
            node = node[key]
        except (KeyError, IndexError, TypeError):
            return False, None
    return True, node


def _attr(obj: Any, keys: tuple) -> Any:
    for key in keys:
        obj = getattr(obj, key)
    return obj


def field_value(config: Config, user: dict, path: tuple) -> FieldValue:
    """The value in effect for `path` under `config` (the merged, validated config) and the
    user file's plain data `user`."""
    is_set, _ = lookup(user, path)
    head, rest = path[0], path[1:]
    if head in ("theme", "layout"):
        value = _attr(config.theme if head == "theme" else config.layout, rest)
        return FieldValue(value, is_set, "your config" if is_set else "default")
    if head != "monitors":
        raise KeyError(f"no settings field for {path}")
    name, table, rest = path[1], path[2], path[3:]
    if table == "shell":
        return FieldValue(config.monitor(name).shell, is_set, _src(is_set, "default"))
    if table == "theme":
        value = _attr(config.theme_for(name), rest)
        return FieldValue(value, is_set, _src(is_set, "global theme"))
    if table == "layout":
        value = _attr(config.layout_for(name), rest)
        return FieldValue(value, is_set, _src(is_set, "global layout"))
    if table == "panels":
        return _panel_value(config, name, rest[0], rest[1:], is_set)
    raise KeyError(f"no settings field for {path}")


def _src(is_set: bool, inherited: str) -> str:
    return "your config" if is_set else inherited


def _panel_value(config: Config, name: str, index: int, keys: tuple, is_set: bool) -> FieldValue:
    entry = config.monitor(name).panels[index]
    req = request_for(entry)
    key = keys[0]
    if key in PANEL_REQUEST_KEYS:
        return FieldValue(getattr(req, key), is_set, _src(is_set, "widget default"))
    if key in PANEL_OWN_KEYS:
        return FieldValue(getattr(entry, key), is_set, _src(is_set, "not set"))
    if key == "interaction":
        return FieldValue(getattr(req.interaction, keys[1]), is_set, _src(is_set, "default"))
    if key == "handle":
        sub = keys[1]
        own = getattr(req.handle, sub)
        if own is not None:
            return FieldValue(own, is_set, _src(is_set, "widget default"))
        theme = config.theme_for(name)
        if sub == "color":
            return FieldValue(theme.handle, is_set, "theme")
        if sub == "hover_color":
            return FieldValue(theme.handle_hover, is_set, "theme")
        return FieldValue(getattr(theme.handle_style, sub), is_set, "theme")
    raise KeyError(f"no settings field for panel key {keys}")


def monitor_names(config: Config, outputs: list[Output]) -> list[tuple[str, bool]]:
    """(name, connected) for every monitor in the config or connected now: connected ones
    first in kscreen order, then configured but disconnected ones by name."""
    connected = [o.name for o in outputs]
    rest = sorted(n for n in config.monitors if n not in connected)
    return [(n, True) for n in connected] + [(n, False) for n in rest]


def layout_preview(config: Config, name: str, width: int, height: int) -> list[str]:
    """The layout warnings the shell would report for this monitor (panels shrunk, moved or
    hidden), from the same resolver. "content" panels count at their widget's default length
    (the shell measures them after building)."""
    theme = config.theme_for(name)
    return layout_monitor(
        requests_for(config, name),
        width,
        height,
        theme.thickness,
        theme.radius,
        config.layout_for(name).gap,
        where=f"monitors.{name}",
    ).warnings
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `scripts/py -m pytest tests/test_settings_values.py -q`
Expected: `9 passed`.

- [ ] **Step 5: VERIFY and commit**

Run VERIFY. Expected: `1292 passed`.

```bash
git add settings/values.py tests/test_settings_values.py
git commit -m "feat(settings): the value each field shows and where it is inherited from" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Field rows: `settings/fields.py`

**Files:**
- Create: `settings/fields.py`
- Test: `tests/test_settings_fields.py`

**Interfaces:**
- Consumes: `FieldSpec`, `LENGTH_*`, `rgba_to_hex`, `split_length`, `join_length`, `parse_fonts`, `format_fonts` (Task 5); `FieldValue` (Task 6); `hex_to_rgba` (`shell/theme.py`).
- Produces:
  - `DEBOUNCE_MS = 400`, `DEBOUNCED = ("int", "length")`
  - editors `ColorEditor`, `IntEditor`, `BoolEditor`, `ChoiceEditor`, `FontsEditor`, `LengthEditor` (attributes `mode`, `number`), `DeprecatedEditor`, each with `.widget` and `.set(value)` (never emits); `make_editor(spec, emit) -> editor` (`ValueError` for an unknown kind)
  - `class FieldRow(Gtk.Box)(spec, path, on_change(path, value), on_reset(path))` with `.spec`, `.path`, `.editor`, `.source` (label), `.reset` (button), `.error` (label), `.show_value(FieldValue)` (never calls back; cancels a pending debounced edit; reset is sensitive when the key is set, never for `widget`), `.show_error(message | None)`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_settings_fields.py`:

```python
"""settings.fields: the GTK row of each field kind (widgets only; no window is shown)."""

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from gi.repository import Gdk, Gtk  # noqa: E402

import settings.fields as fields  # noqa: E402

if not Gtk.init_check()[0]:
    pytest.skip("no display", allow_module_level=True)

from settings.form import FieldSpec, config_form  # noqa: E402
from settings.values import FieldValue  # noqa: E402

FORM = config_form(("clock", "dock", "system_bar"))


@pytest.fixture(autouse=True)
def immediate(monkeypatch):
    """Debounced edits fire at once (no main loop in tests)."""
    monkeypatch.setattr(fields.GLib, "timeout_add", lambda _ms, fn: fn() and 0)


def row_for(spec, value, is_set=False, path=("theme", "x")):
    changes, resets = [], []
    row = fields.FieldRow(spec, path, lambda p, v: changes.append((p, v)), resets.append)
    row.show_value(FieldValue(value, is_set, "default"))
    return row, changes, resets


def test_show_value_never_calls_back():
    for spec, value in [
        (FORM.theme.field("accent"), "#8fd3b6"),
        (FORM.theme.field("thickness"), 12),
        (FORM.theme.section("border").field("enabled"), True),
        (FORM.theme.section("handle_style").field("shape"), "bar"),
        (FORM.theme.field("font"), ["A", "B"]),
        (FORM.panel.field("length"), "50%"),
        (FORM.panel.field("pos"), 600),
    ]:
        _, changes, _ = row_for(spec, value)
        assert changes == [], spec.key


def test_colour_row_writes_hex_with_alpha_only_when_needed():
    row, changes, _ = row_for(FORM.theme.field("accent"), "#8fd3b6", path=("theme", "accent"))
    button = row.editor.widget
    assert button.props.use_alpha
    button.set_rgba(Gdk.RGBA(0, 0, 0, 0.5))
    button.emit("color-set")
    button.set_rgba(Gdk.RGBA(1, 1, 1, 1))
    button.emit("color-set")
    assert changes == [(("theme", "accent"), "#00000080"), (("theme", "accent"), "#ffffff")]


def test_int_row_takes_its_bounds_from_the_schema_and_is_debounced(monkeypatch):
    timers = []
    monkeypatch.setattr(fields.GLib, "timeout_add", lambda ms, fn: timers.append((ms, fn)) or 7)
    monkeypatch.setattr(fields.GLib, "source_remove", lambda _id: None)
    row, changes, _ = row_for(FORM.theme.field("thickness"), 10)
    spin = row.editor.widget
    assert tuple(spin.get_range()) == (2.0, 64.0)
    spin.set_value(11)
    spin.set_value(12)
    assert changes == []  # waits for the pause
    assert [ms for ms, _fn in timers] == [fields.DEBOUNCE_MS, fields.DEBOUNCE_MS]
    timers[-1][1]()
    assert changes == [(("theme", "x"), 12)]


def test_a_new_value_cancels_a_pending_edit(monkeypatch):
    removed = []
    monkeypatch.setattr(fields.GLib, "timeout_add", lambda _ms, _fn: 9)
    monkeypatch.setattr(fields.GLib, "source_remove", removed.append)
    row, changes, _ = row_for(FORM.theme.field("thickness"), 10)
    row.editor.widget.set_value(11)
    row.show_value(FieldValue(10, False, "default"))  # e.g. the file was re-read
    assert removed == [9] and changes == []


def test_unset_optional_int_shows_the_minimum():
    row, _, _ = row_for(FORM.panel.field("min_length"), None)
    assert row.editor.widget.get_value() == 60


def test_bool_enum_and_widget_rows():
    row, changes, _ = row_for(FORM.theme.section("border").field("enabled"), False)
    row.editor.widget.set_active(True)
    row, changes2, _ = row_for(FORM.theme.section("handle_style").field("shape"), "auto")
    assert row.editor.widget.get_active_id() == "auto"
    row.editor.widget.set_active_id("chevron")
    row, changes3, _ = row_for(FORM.panel.field("widget"), "dock")
    row.editor.widget.set_active_id("clock")
    assert [c[1] for c in changes + changes2 + changes3] == [True, "chevron", "clock"]


def test_fonts_row_commits_on_enter_only_when_changed():
    row, changes, _ = row_for(FORM.theme.field("font"), ["Hack Nerd Font Mono", "monospace"])
    entry = row.editor.widget
    assert entry.get_text() == "Hack Nerd Font Mono, monospace"
    entry.emit("activate")
    assert changes == []
    entry.set_text("JetBrains Mono, monospace")
    entry.emit("activate")
    assert changes == [(("theme", "x"), ["JetBrains Mono", "monospace"])]


def test_length_row_modes():
    row, changes, _ = row_for(FORM.panel.field("length"), 300)
    editor = row.editor
    assert editor.mode.get_active_id() == "px" and editor.number.get_value() == 300
    editor.mode.set_active_id("fill")
    assert not editor.number.get_sensitive()
    editor.mode.set_active_id("percent")
    editor.number.set_value(25)
    assert [c[1] for c in changes] == ["fill", "100%", "25%"]  # px 300 clamps to 100 %


def test_length_row_shows_percent_with_one_decimal():
    row, _, _ = row_for(FORM.panel.field("length"), "12.5%")
    assert row.editor.mode.get_active_id() == "percent"
    assert row.editor.number.get_value() == 12.5 and row.editor.number.get_digits() == 1


def test_reset_button_follows_is_set_and_calls_back():
    row, _, resets = row_for(FORM.theme.field("accent"), "#8fd3b6", is_set=False)
    assert not row.reset.get_sensitive()
    row.show_value(FieldValue("#112233", True, "your config"))
    assert row.reset.get_sensitive()
    row.reset.clicked()
    assert resets == [("theme", "x")]


def test_the_widget_of_a_panel_cannot_be_reset():
    row, _, _ = row_for(FORM.panel.field("widget"), "dock", is_set=True)
    assert not row.reset.get_sensitive()


def test_source_shows_the_hint_and_the_origin():
    row, _, _ = row_for(FORM.theme.field("thickness"), 10)
    assert row.source.get_text() == "px · default"


def test_errors_show_under_the_row_until_the_next_value():
    row, _, _ = row_for(FORM.theme.field("thickness"), 10)
    row.show_error("theme.thickness: too thick")
    assert row.error.get_visible() and "too thick" in row.error.get_text()
    row.show_value(FieldValue(10, False, "default"))
    assert not row.error.get_visible()


def test_an_unknown_kind_has_no_editor():
    with pytest.raises(ValueError):
        fields.make_editor(FieldSpec("x", "X", "blob"), lambda _v: None)  # type: ignore[arg-type]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `scripts/py -m pytest tests/test_settings_fields.py -q`
Expected: collection error, `ModuleNotFoundError: No module named 'settings.fields'` (or the whole module skipped with "no display" when there is none: then check with Phil's session, the tests need a display).

- [ ] **Step 3: Implement**

Create `settings/fields.py`:

```python
"""GTK rows for the settings form: one FieldRow per FieldSpec (settings.form). Thin: the
conversions live in settings.form, the values in settings.values."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk

from settings.form import (
    LENGTH_MODES,
    LENGTH_PERCENT,
    LENGTH_PX,
    FieldSpec,
    format_fonts,
    join_length,
    parse_fonts,
    rgba_to_hex,
    split_length,
)
from settings.values import FieldValue
from shell.theme import hex_to_rgba

DEBOUNCE_MS = 400  # spin buttons: one write per pause, not one per click of the arrows
DEBOUNCED = ("int", "length")
UNBOUNDED = (-100000, 100000)

Emit = Callable[[Any], None]


class _Editor:
    """The value widget of a row: `widget`, `set(value)` (never emits), `emit` on user edits."""

    widget: Gtk.Widget

    def set(self, value: Any) -> None:
        raise NotImplementedError


class ColorEditor(_Editor):
    def __init__(self, emit: Emit):
        self.widget = Gtk.ColorButton(use_alpha=True)  # the ColorChooser property
        self.widget.connect("color-set", lambda b: emit(_hex_of(b.get_rgba())))

    def set(self, value: str) -> None:
        self.widget.set_rgba(Gdk.RGBA(*hex_to_rgba(value)))


def _hex_of(rgba: Gdk.RGBA) -> str:
    return rgba_to_hex(rgba.red, rgba.green, rgba.blue, rgba.alpha)


class IntEditor(_Editor):
    def __init__(self, spec: FieldSpec, emit: Emit):
        low = UNBOUNDED[0] if spec.minimum is None else spec.minimum
        high = UNBOUNDED[1] if spec.maximum is None else spec.maximum
        self.widget = Gtk.SpinButton.new_with_range(low, high, 1)
        self.widget.set_numeric(True)
        self.widget.connect("value-changed", lambda s: emit(s.get_value_as_int()))

    def set(self, value: int | None) -> None:
        # None (e.g. min_length not set) shows the lowest value; the source says "not set"
        self.widget.set_value(self.widget.get_range()[0] if value is None else value)


class BoolEditor(_Editor):
    def __init__(self, emit: Emit):
        self.widget = Gtk.Switch(halign=Gtk.Align.START)
        self.widget.connect("notify::active", lambda s, _p: emit(s.get_active()))

    def set(self, value: bool) -> None:
        self.widget.set_active(bool(value))


class ChoiceEditor(_Editor):
    def __init__(self, choices: tuple[str, ...], emit: Emit):
        self.widget = Gtk.ComboBoxText()
        for choice in choices:
            self.widget.append(choice, choice)
        self.widget.connect("changed", self._on_changed, emit)

    @staticmethod
    def _on_changed(combo: Gtk.ComboBoxText, emit: Emit) -> None:
        if combo.get_active_id() is not None:
            emit(combo.get_active_id())

    def set(self, value: str) -> None:
        self.widget.set_active_id(value)


class FontsEditor(_Editor):
    def __init__(self, emit: Emit):
        self.widget = Gtk.Entry(width_chars=40)
        self._shown: list[str] = []

        def commit(*_args) -> bool:
            fonts = parse_fonts(self.widget.get_text())
            if fonts != self._shown:
                emit(fonts)
            return False

        self.widget.connect("activate", commit)
        self.widget.connect("focus-out-event", commit)

    def set(self, value: list[str]) -> None:
        self._shown = list(value)
        self.widget.set_text(format_fonts(value))


class LengthEditor(_Editor):
    """A mode (px, fill, content, percent) and a number for px and percent."""

    def __init__(self, emit: Emit):
        self.widget = Gtk.Box(spacing=6)
        self.mode = Gtk.ComboBoxText()
        for mode in LENGTH_MODES:
            self.mode.append(mode, mode)
        self.number = Gtk.SpinButton.new_with_range(*LENGTH_PX, 1)
        self.widget.pack_start(self.mode, False, False, 0)
        self.widget.pack_start(self.number, False, False, 0)
        self._emit = emit
        self._quiet = False
        self.mode.connect("changed", self._on_mode)
        self.number.connect("value-changed", lambda *_a: self._send())

    def _range(self, mode: str) -> None:
        percent = mode == "percent"
        self.number.set_digits(1 if percent else 0)
        self.number.set_increments(0.5 if percent else 1, 10)
        self.number.set_range(*(LENGTH_PERCENT if percent else LENGTH_PX))
        self.number.set_sensitive(mode in ("px", "percent"))

    def _on_mode(self, _combo) -> None:
        if self._quiet:
            return
        self._quiet = True
        self._range(self.mode.get_active_id())  # may clamp the number: no emit for that
        self._quiet = False
        self._send()

    def _send(self) -> None:
        if not self._quiet:
            self._emit(join_length(self.mode.get_active_id(), self.number.get_value()))

    def set(self, value: int | str) -> None:
        mode, number = split_length(value)
        self._quiet = True
        self.mode.set_active_id(mode)
        self._range(mode)
        if number is not None:
            self.number.set_value(number)
        self._quiet = False


class DeprecatedEditor(_Editor):
    """`pos`: shown, never edited here (the row's reset button removes it)."""

    def __init__(self):
        self.widget = Gtk.Label(xalign=0)

    def set(self, value: Any) -> None:
        self.widget.set_text("not set" if value is None else str(value))


def make_editor(spec: FieldSpec, emit: Emit) -> _Editor:
    if spec.kind == "color":
        return ColorEditor(emit)
    if spec.kind == "int":
        return IntEditor(spec, emit)
    if spec.kind == "bool":
        return BoolEditor(emit)
    if spec.kind in ("enum", "widget"):
        return ChoiceEditor(spec.choices, emit)
    if spec.kind == "fonts":
        return FontsEditor(emit)
    if spec.kind == "length":
        return LengthEditor(emit)
    if spec.kind == "deprecated":
        return DeprecatedEditor()
    raise ValueError(f"no editor for field kind {spec.kind!r}")


class FieldRow(Gtk.Box):
    """Label, editor, where the value comes from, a reset button and an error line.

    `on_change(path, value)` runs when the user edits the value (spin buttons: after a
    DEBOUNCE_MS pause); `on_reset(path)` when the reset button is pressed. Values shown with
    show_value never call back."""

    def __init__(
        self,
        spec: FieldSpec,
        path: tuple,
        on_change: Callable[[tuple, Any], None],
        on_reset: Callable[[tuple], None],
    ):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.spec, self.path = spec, path
        self._on_change = on_change
        self._updating = False
        self._timer = 0
        self._pending: Any = None
        self.editor = make_editor(spec, self._changed)
        line = Gtk.Box(spacing=8)
        name = Gtk.Label(label=spec.label, xalign=0)
        name.set_size_request(150, -1)
        self.source = Gtk.Label(xalign=0)
        self.source.get_style_context().add_class("dim-label")
        self.reset = Gtk.Button.new_from_icon_name("edit-undo-symbolic", Gtk.IconSize.BUTTON)
        self.reset.set_tooltip_text("Remove this key from your config (use the inherited value)")
        self.reset.connect("clicked", lambda *_a: on_reset(path))
        line.pack_start(name, False, False, 0)
        line.pack_start(self.editor.widget, False, False, 0)
        line.pack_start(self.source, True, True, 0)
        line.pack_end(self.reset, False, False, 0)
        self.error = Gtk.Label(xalign=0, wrap=True, selectable=True)
        self.error.get_style_context().add_class("error")
        self.error.set_no_show_all(True)
        self.pack_start(line, False, False, 0)
        self.pack_start(self.error, False, False, 0)

    def show_value(self, value: FieldValue) -> None:
        self._cancel()
        self._updating = True
        try:
            self.editor.set(value.value)
        finally:
            self._updating = False
        note = value.source if not self.spec.hint else f"{self.spec.hint} · {value.source}"
        self.source.set_text(note)
        self.reset.set_sensitive(value.is_set and self.spec.kind != "widget")
        self.show_error(None)

    def show_error(self, message: str | None) -> None:
        self.error.set_text(message or "")
        self.error.set_visible(bool(message))

    def _changed(self, value: Any) -> None:
        if self._updating:
            return
        if self.spec.kind not in DEBOUNCED:
            self._on_change(self.path, value)
            return
        self._cancel()
        self._pending = value
        self._timer = GLib.timeout_add(DEBOUNCE_MS, self._flush)

    def _flush(self) -> bool:
        self._timer = 0
        self._on_change(self.path, self._pending)
        return GLib.SOURCE_REMOVE

    def _cancel(self) -> None:
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `scripts/py -m pytest tests/test_settings_fields.py -q`
Expected: `14 passed`.

- [ ] **Step 5: VERIFY and commit**

Run VERIFY. Expected: `1306 passed`.

```bash
git add settings/fields.py tests/test_settings_fields.py
git commit -m "feat(settings): GTK field rows with schema bounds, reset and debounced spins" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 8: The panel list editor: `settings/panels.py`

**Files:**
- Create: `settings/panels.py`
- Test: `tests/test_settings_panels.py`

**Interfaces:**
- Consumes: `UserDocument` (Task 3), `ConfigForm`, `SectionSpec` (Task 5), `PanelRequest` (`shell/panel_spec.py`); in tests `requests_for` and the `fake_registry` fixture.
- Produces:
  - `panel_title(index, req) -> str` (`"1. dock: bottom, center"`)
  - `class PanelEditor(Gtk.Box)(form, monitor, requests, make_rows(section, prefix) -> Gtk.Widget, on_edit(edit, open_index), expand=None)` with `.expanders`, `.widget_choice`, `.add(widget | None)` (open index = the new entry), `.remove(index)` (None), `.move(index, to)` (`to`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_settings_panels.py`:

```python
"""settings.panels: the panel list editor of one monitor (widgets only; no window shown)."""

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
pytest.importorskip("tomlkit")

from gi.repository import Gtk  # noqa: E402

import settings.panels as panels  # noqa: E402

if not Gtk.init_check()[0]:
    pytest.skip("no display", allow_module_level=True)

from settings.document import UserDocument  # noqa: E402
from settings.form import config_form  # noqa: E402
from shell.registry import requests_for  # noqa: E402

FORM = config_form(("bar", "clock", "dock"))
USER = '[[monitors.M.panels]]\nwidget = "dock"\n[[monitors.M.panels]]\nwidget = "clock"\n'


@pytest.fixture
def editor(make_config, fake_registry):
    config = make_config(monitors={"M": {"panels": [{"widget": "dock"}, {"widget": "clock"}]}})
    made, edits = [], []

    def make_rows(section, prefix):
        made.append((section.label, prefix))
        return Gtk.Box()

    on_edit = lambda edit, open_index: edits.append((edit, open_index))  # noqa: E731
    ed = panels.PanelEditor(FORM, "M", requests_for(config, "M"), make_rows, on_edit, 1)
    return ed, made, edits


def apply(edits):
    doc = UserDocument(USER)
    for edit, _open in edits:
        edit(doc)
    return [p["widget"] for p in doc.data["monitors"]["M"].get("panels", [])]


def test_one_expander_per_entry_with_its_rows(editor):
    ed, made, _ = editor
    assert [e.get_label() for e in ed.expanders] == [
        "1. dock: bottom, center",
        "2. clock: top, center",
    ]
    assert made == [
        ("Panel", ("monitors", "M", "panels", 0)),
        ("Panel", ("monitors", "M", "panels", 1)),
    ]
    assert [e.get_expanded() for e in ed.expanders] == [False, True]


def test_add_remove_and_move_are_document_edits(editor):
    ed, _, edits = editor
    ed.add("bar")
    assert apply(edits) == ["dock", "clock", "bar"] and edits[0][1] == 2  # the new one opens
    edits.clear()
    ed.move(1, 0)
    assert apply(edits) == ["clock", "dock"] and edits[0][1] == 0  # the moved one opens
    edits.clear()
    ed.remove(0)
    assert apply(edits) == ["clock"] and edits[0][1] is None


def test_the_widget_list_comes_from_the_form(editor):
    ed, _, edits = editor
    model = ed.widget_choice.get_model()
    assert [row[0] for row in model] == ["bar", "clock", "dock"]
    ed.add(None)  # nothing chosen: no edit
    assert edits == []


def test_first_cannot_move_up_and_last_cannot_move_down(editor):
    ed, _, _ = editor

    def buttons(i):
        body = ed.expanders[i].get_child()
        return body.get_children()[0].get_children()

    up0, down0, _ = buttons(0)
    up1, down1, _ = buttons(1)
    assert (up0.get_sensitive(), down0.get_sensitive()) == (False, True)
    assert (up1.get_sensitive(), down1.get_sensitive()) == (True, False)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `scripts/py -m pytest tests/test_settings_panels.py -q`
Expected: collection error, `ModuleNotFoundError: No module named 'settings.panels'`.

- [ ] **Step 3: Implement**

Create `settings/panels.py`:

```python
"""GTK editor for one monitor's panel list: an expander per [[panels]] entry with its fields,
plus add, remove and reorder buttons. Structural edits go through `on_edit` (the window applies
them with the session and rebuilds); field rows come from the window's `make_rows`."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from settings.document import UserDocument
from settings.form import ConfigForm, SectionSpec
from shell.panel_spec import PanelRequest

Edit = Callable[[UserDocument], Any]


def panel_title(index: int, req: PanelRequest) -> str:
    """'1. dock: bottom, center' (1-based, as the list reads)."""
    return f"{index + 1}. {req.widget}: {req.edge}, {req.align}"


class PanelEditor(Gtk.Box):
    def __init__(
        self,
        form: ConfigForm,
        monitor: str,
        requests: list[PanelRequest],
        make_rows: Callable[[SectionSpec, tuple], Gtk.Widget],
        on_edit: Callable[[Edit, int | None], None],
        expand: int | None = None,
    ):
        """`requests`: registry.requests_for(config, monitor), one per entry in config order.
        `on_edit(edit, open_index)`: apply a structural edit, then show entry `open_index`
        open (None: none). `expand`: the entry to show open now."""
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.monitor = monitor
        self._on_edit = on_edit
        self._count = len(requests)
        self.expanders: list[Gtk.Expander] = []
        last = len(requests) - 1
        for i, req in enumerate(requests):
            expander = Gtk.Expander(label=panel_title(i, req), expanded=i == expand)
            body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_start=18)
            buttons = Gtk.Box(spacing=6)
            for icon, tip, sensitive, action in (
                ("go-up-symbolic", "Move up", i > 0, lambda _b, i=i: self.move(i, i - 1)),
                ("go-down-symbolic", "Move down", i < last, lambda _b, i=i: self.move(i, i + 1)),
                ("list-remove-symbolic", "Remove this panel", True, lambda _b, i=i: self.remove(i)),
            ):
                button = Gtk.Button.new_from_icon_name(icon, Gtk.IconSize.BUTTON)
                button.set_tooltip_text(tip)
                button.set_sensitive(sensitive)
                button.connect("clicked", action)
                buttons.pack_start(button, False, False, 0)
            body.pack_start(buttons, False, False, 0)
            rows = make_rows(form.panel, ("monitors", monitor, "panels", i))
            body.pack_start(rows, False, False, 0)
            expander.add(body)
            self.expanders.append(expander)
            self.pack_start(expander, False, False, 0)
        adder = Gtk.Box(spacing=6)
        self.widget_choice = Gtk.ComboBoxText()
        for name in form.panel.field("widget").choices:
            self.widget_choice.append(name, name)
        self.widget_choice.set_active(0)
        add = Gtk.Button(label="Add panel")
        add.connect("clicked", lambda _b: self.add(self.widget_choice.get_active_id()))
        adder.pack_start(self.widget_choice, False, False, 0)
        adder.pack_start(add, False, False, 0)
        self.pack_start(adder, False, False, 0)

    def add(self, widget: str | None) -> None:
        if widget:
            self._on_edit(lambda d: d.add_panel(self.monitor, widget), self._count)

    def remove(self, index: int) -> None:
        self._on_edit(lambda d: d.remove_panel(self.monitor, index), None)

    def move(self, index: int, to: int) -> None:
        self._on_edit(lambda d: d.move_panel(self.monitor, index, to), to)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `scripts/py -m pytest tests/test_settings_panels.py -q`
Expected: `4 passed`.

- [ ] **Step 5: VERIFY and commit**

Run VERIFY. Expected: `1310 passed`.

```bash
git add settings/panels.py tests/test_settings_panels.py
git commit -m "feat(settings): panel list editor: add, remove, reorder" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 9: The settings view: `settings/view.py`

**Files:**
- Create: `settings/view.py`
- Test: `tests/test_settings_view.py`

**Interfaces:**
- Consumes: `FieldRow` (Task 7), `PanelEditor` (Task 8), `SettingsSession`, `ChangedOutside`, `check_text` (Task 4), `config_form`, `MODE_HINTS`, `SectionSpec` (Task 5), `field_value`, `layout_preview`, `monitor_names` (Task 6), `requests_for`, `widget_names` (`shell/registry.py`), `Output` (`shell/outputs.py`).
- Produces: `TITLE_KEYS = ("widget", "edge", "align")`; `class SettingsView(Gtk.Box)(session, outputs)` with `.session`, `.outputs` (name -> Output), `.form`, `.rows`, `.previews` (monitor -> label), `.stack` (pages `theme`, `monitor:NAME`), `.banner`, `.banner_label`, `.undo_button`; methods `rebuild()`, `refresh()`, `section_rows(section, prefix) -> Gtk.Widget`, `apply(edit, row=None, structural=False) -> bool`, `undo()`, `revert()`, `file_changed()`, `show_banner(text, kind)`, `hide_banner()`; the private `_on_change(path, value)` / `_on_reset(path)` are the rows' callbacks (the tests call them as a user edit would).

- [ ] **Step 1: Write the failing test**

Create `tests/test_settings_view.py`:

```python
"""settings.view: pages, edits through the session, undo, revert, hand edits. The view is a
plain Gtk.Box: no window is created."""

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
pytest.importorskip("tomlkit")

from gi.repository import Gtk  # noqa: E402

if not Gtk.init_check()[0]:
    pytest.skip("no display", allow_module_level=True)

from settings.panels import PanelEditor  # noqa: E402
from settings.session import SettingsSession  # noqa: E402
from settings.view import SettingsView  # noqa: E402
from shell.outputs import Output  # noqa: E402

USER = """\
# gate config
[monitors.HDMI-A-1]
shell = "edge"

[[monitors.HDMI-A-1.panels]]
widget = "dock"
"""
HDMI = Output("HDMI-A-1", 0, 0, 1920, 1080)
DP = Output("DP-1", 0, 1080, 1920, 1080)
SHELL = ("monitors", "HDMI-A-1", "shell")
DEPTH = ("monitors", "HDMI-A-1", "panels", 0, "depth")


@pytest.fixture
def make(tmp_path, fake_registry):
    path = tmp_path / "config.toml"
    path.write_text(USER)

    def _make(outputs=(HDMI, DP)):
        return SettingsView(SettingsSession(path), list(outputs)), path

    return _make


def pages(view):
    return [view.stack.child_get_property(c, "name") for c in view.stack.get_children()]


def row(view, path):
    return next(r for r in view.rows if r.path == path)


def walk(widget):
    yield widget
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            yield from walk(child)


def panel_editor(view, monitor="HDMI-A-1"):
    page = view.stack.get_child_by_name(f"monitor:{monitor}")
    return next(w for w in walk(page) if isinstance(w, PanelEditor))


def test_a_page_for_the_theme_and_each_monitor(make):
    view, _ = make()
    assert pages(view) == ["theme", "monitor:HDMI-A-1", "monitor:DP-1"]
    accent = row(view, ("theme", "accent")).editor.widget.get_rgba()
    assert accent.to_string() == "rgb(143,211,182)"
    assert row(view, ("monitors", "DP-1", "shell")).editor.widget.get_active_id() == "plasma"
    assert row(view, DEPTH).editor.widget.get_value() == 64  # the widget's default


def test_a_configured_monitor_that_is_not_connected_is_listed(make):
    view, _ = make(outputs=())
    assert pages(view) == ["theme", "monitor:HDMI-A-1"]


def test_a_valid_edit_is_written_and_shown(make):
    view, path = make()
    view._on_change(DEPTH, 90)
    assert "depth = 90" in path.read_text() and "# gate config" in path.read_text()
    r = row(view, DEPTH)
    assert r.editor.widget.get_value() == 90 and r.reset.get_sensitive()
    assert view.undo_button.get_sensitive()


def test_an_invalid_edit_shows_its_error_under_the_row(make):
    view, path = make()
    view._on_change(("monitors", "HDMI-A-1", "panels", 0, "pos"), 400)
    align = ("monitors", "HDMI-A-1", "panels", 0, "align")
    view._on_change(align, "end")
    r = row(view, align)
    assert r.error.get_visible() and "pos cannot be combined" in r.error.get_text()
    assert 'align = "end"' not in path.read_text()


def test_reset_removes_the_key(make):
    view, path = make()
    view._on_change(DEPTH, 90)
    view._on_reset(DEPTH)
    assert "depth" not in path.read_text()
    assert row(view, DEPTH).source.get_text().endswith("widget default")


def test_adding_and_removing_panels_rebuilds_the_rows(make):
    view, path = make()
    panel_editor(view).add("clock")
    assert any(r.path[:4] == ("monitors", "HDMI-A-1", "panels", 1) for r in view.rows)
    assert panel_editor(view).expanders[1].get_expanded()  # the new panel is open
    panel_editor(view).remove(0)
    assert path.read_text().count("[[monitors.HDMI-A-1.panels]]") == 1
    assert not any(r.path[:4] == ("monitors", "HDMI-A-1", "panels", 1) for r in view.rows)


def test_changing_a_panel_edge_retitles_it_and_keeps_it_open(make):
    view, path = make()
    view._on_change(("monitors", "HDMI-A-1", "panels", 0, "edge"), "top")
    expander = panel_editor(view).expanders[0]
    assert expander.get_label() == "1. dock: top, center" and expander.get_expanded()
    assert 'edge = "top"' in path.read_text()


def test_a_rejected_panel_edit_shows_in_the_banner(make):
    view, path = make()
    panel_editor(view).add("nope")
    assert "unknown widget" in view.banner_label.get_text() and view.banner.get_visible()
    assert path.read_text() == USER


def test_undo_and_revert(make):
    view, path = make()
    view._on_change(DEPTH, 90)
    view._on_change(SHELL, "both")
    view.undo()
    assert "depth = 90" in path.read_text() and 'shell = "edge"' in path.read_text()
    view.revert()
    assert path.read_text() == USER
    assert not view.undo_button.get_sensitive()


def test_the_visible_page_survives_a_rebuild(make):
    view, _ = make()
    view.stack.set_visible_child_name("monitor:DP-1")
    view.rebuild()
    assert view.stack.get_visible_child_name() == "monitor:DP-1"


def test_a_hand_edit_is_reloaded_and_announced(make):
    view, path = make()
    path.write_text(USER.replace('"edge"', '"both"'))
    view.file_changed()
    assert row(view, SHELL).editor.widget.get_active_id() == "both"
    assert view.banner.get_visible() and "changed outside" in view.banner_label.get_text()


def test_our_own_write_does_not_rebuild(make):
    view, _ = make()
    view._on_change(DEPTH, 90)
    rows = list(view.rows)
    view.file_changed()  # the watcher fires for the view's own write
    assert view.rows == rows and not view.banner.get_visible()


def test_an_edit_after_a_hand_edit_is_not_applied(make):
    view, path = make()
    path.write_text(USER + '\n[theme]\naccent = "#112233"\n')
    view._on_change(DEPTH, 90)
    assert "depth" not in path.read_text()
    assert view.banner.get_visible() and "changed outside" in view.banner_label.get_text()


def test_an_invalid_file_is_shown_read_only_with_its_error(make):
    view, path = make()
    path.write_text('[monitors.HDMI-A-1]\nshell = "sideways"\n')
    view.file_changed()
    assert pages(view) == ["theme"]
    assert not view.stack.get_child_by_name("theme").get_sensitive()
    assert "is not valid" in view.banner_label.get_text()
    assert "monitors.HDMI-A-1.shell" in view.banner_label.get_text()


def test_layout_warnings_are_previewed_for_connected_monitors(make):
    view, _ = make()
    preview = view.previews["HDMI-A-1"]
    assert not preview.get_visible()
    view._on_change(("monitors", "HDMI-A-1", "panels", 0, "length"), 3000)
    assert preview.get_visible() and "monitors.HDMI-A-1" in preview.get_text()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `scripts/py -m pytest tests/test_settings_view.py -q`
Expected: collection error, `ModuleNotFoundError: No module named 'settings.view'`.

- [ ] **Step 3: Implement**

Create `settings/view.py`:

```python
"""The settings window's content: a top bar (Undo, Revert all, the file path), a banner for
errors and notices, and a page per topic (the global theme and layout, then one page per
monitor: shell mode, panels, theme and layout overrides). A plain Gtk.Box, so it is tested
without creating a window; settings.window puts it in the toplevel.

Every edit goes through SettingsSession.apply: a valid one is written to the user config and
the running shell reloads it; an invalid one is shown under its row and not written."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from settings.document import UserDocument
from settings.fields import FieldRow
from settings.form import MODE_HINTS, SectionSpec, config_form
from settings.panels import PanelEditor
from settings.session import ChangedOutside, SettingsSession, check_text
from settings.values import field_value, layout_preview, monitor_names
from shell.config.models import ConfigError
from shell.outputs import Output
from shell.registry import requests_for, widget_names

Edit = Callable[[UserDocument], Any]
TITLE_KEYS = ("widget", "edge", "align")  # shown in a panel's expander title (panel_title)


class SettingsView(Gtk.Box):
    def __init__(self, session: SettingsSession, outputs: list[Output]):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.session = session
        self.outputs = {o.name: o for o in outputs}
        self.form = config_form(tuple(widget_names()))
        self.rows: list[FieldRow] = []
        self.previews: dict[str, Gtk.Label] = {}
        self._expand: dict[str, int] = {}  # monitor -> panel entry to show open after a rebuild

        bar = Gtk.Box(spacing=6, margin=6)
        self.undo_button = Gtk.Button(label="Undo")
        self.undo_button.set_tooltip_text("Undo the last change (Ctrl+Z)")
        self.undo_button.connect("clicked", lambda _b: self.undo())
        revert = Gtk.Button(label="Revert all")
        revert.set_tooltip_text("Put back the file as it was when this window opened")
        revert.connect("clicked", lambda _b: self._confirm_revert())
        where = Gtk.Label(label=str(session.path), xalign=1, selectable=True)
        where.get_style_context().add_class("dim-label")
        bar.pack_start(self.undo_button, False, False, 0)
        bar.pack_start(revert, False, False, 0)
        bar.pack_end(where, True, True, 0)

        self.banner = Gtk.InfoBar()
        self.banner_label = Gtk.Label(xalign=0, wrap=True, selectable=True)
        self.banner.get_content_area().add(self.banner_label)
        self.banner.set_no_show_all(True)
        self.stack = Gtk.Stack()
        sidebar = Gtk.StackSidebar(stack=self.stack)
        body = Gtk.Box()
        body.pack_start(sidebar, False, False, 0)
        body.pack_start(self.stack, True, True, 0)
        self.pack_start(bar, False, False, 0)
        self.pack_start(self.banner, False, False, 0)
        self.pack_start(body, True, True, 0)
        self.rebuild()

    # ---- building ------------------------------------------------------------------------
    @property
    def config(self):
        """The config the rows show: the session's, or the defaults while the file is
        invalid (the pages are then insensitive)."""
        return self.session.config or check_text("", self.session.default_path)

    def rebuild(self) -> None:
        """Rebuild every page (after a panel was added, removed or moved, an undo, a revert
        or a hand edit); keeps the visible page."""
        visible = self.stack.get_visible_child_name()
        for child in self.stack.get_children():
            self.stack.remove(child)
            child.destroy()
        self.rows, self.previews = [], {}
        valid = self.session.config is not None
        self._page("theme", "Theme", self._theme_page(), valid)
        if valid:
            for name, connected in monitor_names(self.config, list(self.outputs.values())):
                title = name if connected else f"{name} (not connected)"
                self._page(f"monitor:{name}", title, self._monitor_page(name), True)
        self.stack.show_all()
        if visible and self.stack.get_child_by_name(visible) is not None:
            self.stack.set_visible_child_name(visible)
        if valid:
            self.refresh()
        else:
            self.show_banner(
                f"{self.session.path} is not valid, so it cannot be edited here; fix it in a "
                "text editor (this window reloads it when it is saved), press Revert all, or "
                f"run main.py --restore-config.\n{self.session.error}",
                Gtk.MessageType.ERROR,
            )
        self.undo_button.set_sensitive(bool(self.session.history))

    def _page(self, name: str, title: str, content: Gtk.Widget, sensitive: bool) -> None:
        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        content.set_margin_start(16)
        content.set_margin_end(16)
        content.set_margin_top(12)
        content.set_margin_bottom(12)
        scroller.add(content)
        scroller.set_sensitive(sensitive)
        self.stack.add_titled(scroller, name, title)

    def section_rows(self, section: SectionSpec, prefix: tuple) -> Gtk.Widget:
        """A box of FieldRows for `section` at key path `prefix`; sub-sections in frames."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        for spec in section.fields:
            row = FieldRow(spec, (*prefix, spec.key), self._on_change, self._on_reset)
            self.rows.append(row)
            box.pack_start(row, False, False, 0)
        for sub in section.sections:
            frame = Gtk.Frame(label=sub.label)
            inner = self.section_rows(sub, (*prefix, sub.key))
            inner.set_margin_start(8)
            inner.set_margin_end(8)
            inner.set_margin_bottom(8)
            frame.add(inner)
            box.pack_start(frame, False, False, 6)
        return box

    @staticmethod
    def _heading(text: str) -> Gtk.Label:
        label = Gtk.Label(xalign=0)
        label.set_markup(f"<b>{text}</b>")
        return label

    def _theme_page(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.pack_start(self._heading("Theme (every monitor)"), False, False, 0)
        box.pack_start(self.section_rows(self.form.theme, ("theme",)), False, False, 0)
        box.pack_start(self._heading("Layout"), False, False, 0)
        box.pack_start(self.section_rows(self.form.layout, ("layout",)), False, False, 0)
        return box

    def _monitor_page(self, name: str) -> Gtk.Widget:
        prefix = ("monitors", name)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.pack_start(self.section_rows(self.form.monitor, prefix), False, False, 0)
        hints = "\n".join(f"{mode}: {hint}" for mode, hint in MODE_HINTS.items())
        note = Gtk.Label(label=hints, xalign=0, wrap=True)
        note.get_style_context().add_class("dim-label")
        box.pack_start(note, False, False, 0)
        box.pack_start(self._heading("Panels"), False, False, 0)
        editor = PanelEditor(
            self.form,
            name,
            requests_for(self.config, name),
            self.section_rows,
            lambda edit, expand, n=name: self._structural(n, edit, expand),
            self._expand.pop(name, None),
        )
        box.pack_start(editor, False, False, 0)
        preview = Gtk.Label(xalign=0, wrap=True, selectable=True)
        preview.get_style_context().add_class("warning")
        preview.set_no_show_all(True)
        self.previews[name] = preview
        box.pack_start(preview, False, False, 0)
        for key, title, section in (
            ("theme", "Theme override (this monitor only)", self.form.theme),
            ("layout", "Layout override (this monitor only)", self.form.layout),
        ):
            expander = Gtk.Expander(label=title)
            expander.add(self.section_rows(section, (*prefix, key)))
            box.pack_start(expander, False, False, 0)
        return box

    # ---- showing values ------------------------------------------------------------------
    def refresh(self) -> None:
        """Show the session's current values in every row (no rebuild: focus is kept)."""
        config, user = self.config, self.session.user
        for row in self.rows:
            row.show_value(field_value(config, user, row.path))
        for name, label in self.previews.items():
            out = self.outputs.get(name)
            warnings = layout_preview(config, name, out.width, out.height) if out else []
            label.set_text("\n".join(warnings))
            label.set_visible(bool(warnings))
        self.undo_button.set_sensitive(bool(self.session.history))

    def show_banner(self, text: str, kind: Gtk.MessageType = Gtk.MessageType.ERROR) -> None:
        self.banner.set_message_type(kind)
        self.banner_label.set_text(text)
        self.banner_label.show()
        self.banner.show()

    def hide_banner(self) -> None:
        self.banner.hide()

    # ---- edits ---------------------------------------------------------------------------
    def apply(self, edit: Edit, row: FieldRow | None = None, structural: bool = False) -> bool:
        """Apply one edit; True when it was written. A rejected edit shows its error under
        `row` (or in the banner); a hand edit since the last read reloads everything."""
        try:
            self.session.apply(edit)
        except ChangedOutside as exc:
            self.rebuild()
            self.show_banner(str(exc), Gtk.MessageType.WARNING)
            return False
        except ConfigError as exc:
            if row is not None:
                row.show_error(f"Not saved: {exc}")
            else:
                self.show_banner(f"Not saved: {exc}")
            return False
        self.hide_banner()
        if structural:
            self.rebuild()
        else:
            self.refresh()
        return True

    def _on_change(self, path: tuple, value: Any) -> None:
        titled = len(path) == 5 and path[2] == "panels" and path[4] in TITLE_KEYS
        if titled:  # the panel's expander title shows these: rebuild, keep that panel open
            self._expand[path[1]] = path[3]
        if not self.apply(lambda d: d.set(path, value), self._row(path), structural=titled):
            self._expand.pop(path[1], None)

    def _on_reset(self, path: tuple) -> None:
        self.apply(lambda d: d.unset(path), self._row(path))

    def _structural(self, monitor: str, edit: Edit, expand: int | None) -> None:
        """A panel added, removed or moved: row indexes change, so rebuild (never refresh
        rows that may point at an entry that is gone). `expand`: the entry to show open."""
        if expand is not None:
            self._expand[monitor] = expand
        if not self.apply(edit, structural=True):
            self._expand.pop(monitor, None)

    def _row(self, path: tuple) -> FieldRow | None:
        return next((r for r in self.rows if r.path == path), None)

    def undo(self) -> None:
        try:
            if not self.session.undo():
                return
        except ChangedOutside as exc:
            self.rebuild()
            self.show_banner(str(exc), Gtk.MessageType.WARNING)
            return
        self.hide_banner()
        self.rebuild()

    def revert(self) -> None:
        self.session.revert()
        self.hide_banner()
        self.rebuild()

    def _confirm_revert(self) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=self.get_toplevel(),
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text="Revert every change made in this window?",
        )
        dialog.format_secondary_text(
            f"{self.session.path} goes back to how it was when the window opened."
        )
        answer = dialog.run()
        dialog.destroy()
        if answer == Gtk.ResponseType.OK:
            self.revert()

    def file_changed(self) -> None:
        """The config file changed on disk (the app's ConfigWatcher). Our own writes leave
        nothing to do; a hand edit is re-read and every page rebuilt."""
        if not self.session.changed_outside():
            return
        self.session.reload()
        self.session.history.clear()
        self.rebuild()
        if self.session.config is not None:
            self.show_banner(
                f"{self.session.path} was changed outside this window; showing the new values",
                Gtk.MessageType.INFO,
            )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `scripts/py -m pytest tests/test_settings_view.py -q`
Expected: `15 passed`.

- [ ] **Step 5: VERIFY and commit**

Run VERIFY. Expected: `1325 passed`.

```bash
git add settings/view.py tests/test_settings_view.py
git commit -m "feat(settings): settings view: pages, live apply, undo, revert, hand edits" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 10: The window, its process and the CLI flags

**Files:**
- Create: `settings/window.py`, `settings/app.py`
- Modify: `main.py` (argument parsing and the two new branches)
- Test: `tests/test_settings_app.py`, `tests/test_main_settings.py`

**Interfaces:**
- Consumes: `SettingsView` (Task 9), `SettingsSession` (Task 4), `restore_backup` (Task 2), `ConfigWatcher` (`shell/config/watcher.py`), `parse_kscreen`, `read_kscreen_json`, `Output` (`shell/outputs.py`), `DEFAULT_PATH`, `USER_PATH` (`shell/config/loader.py`).
- Produces:
  - `settings.window.TITLE = "Edge Shell settings"`; `SettingsWindow(Gtk.ApplicationWindow)(session, outputs, application=None)` with `.view`, a `win.undo` action, `.file_changed()`
  - `settings.app.APP_ID = "org.edgeshell.Settings"`, `TOMLKIT_HINT`, `connected_outputs() -> list[Output]` ([] when kscreen-doctor fails), `class SettingsApp(Gtk.Application)(path, default_path=DEFAULT_PATH)` with `.window`, `.failed`, `do_activate()` (builds once, then presents; Ctrl+Z accel; watches the file), `run_settings(path, default_path=DEFAULT_PATH) -> int` (2 without tomlkit or when the file cannot be read)
  - `main.py`: `--settings` and `--restore-config` (mutually exclusive with `--list-outputs`; `--stats` with either is an error); both use `--config` or `USER_PATH`; `--settings` runs before the `ConfigStore` is built.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_settings_app.py`:

```python
"""settings.app: the window's own process (never run here: Gtk.Application.run would take the
session bus name)."""

import sys

import pytest

pytest.importorskip("gi")

import settings.app as app_mod  # noqa: E402


def test_connected_outputs_from_kscreen(monkeypatch):
    text = (
        '{"outputs": [{"name": "HDMI-A-1", "enabled": true, "scale": 1,'
        ' "pos": {"x": 0, "y": 0}, "size": {"width": 1920, "height": 1080}}]}'
    )
    monkeypatch.setattr(app_mod, "read_kscreen_json", lambda: text)
    assert [(o.name, o.width) for o in app_mod.connected_outputs()] == [("HDMI-A-1", 1920)]


def test_connected_outputs_is_empty_when_kscreen_fails(monkeypatch, caplog):
    def fail():
        raise OSError("no kscreen-doctor")

    monkeypatch.setattr(app_mod, "read_kscreen_json", fail)
    assert app_mod.connected_outputs() == []
    assert "kscreen-doctor failed" in caplog.text


def test_without_tomlkit_the_window_explains_how_to_install_it(monkeypatch, tmp_path, capsys):
    monkeypatch.setitem(sys.modules, "tomlkit", None)  # import tomlkit -> ImportError
    assert app_mod.run_settings(tmp_path / "c.toml") == 2
    assert "pip install" in capsys.readouterr().err


def test_an_unreadable_config_fails_without_a_window(tmp_path, capsys, fake_registry):
    pytest.importorskip("tomlkit")
    folder = tmp_path / "config.toml"
    folder.mkdir()  # reading it raises IsADirectoryError
    app = app_mod.SettingsApp.__new__(app_mod.SettingsApp)  # not registered on the bus
    app.path, app.default_path = folder, app_mod.DEFAULT_PATH
    app.window, app.failed, app._watcher = None, False, None
    app_mod.SettingsApp.do_activate(app)
    assert app.failed and app.window is None
    assert "cannot open the settings" in capsys.readouterr().err
```

Create `tests/test_main_settings.py`:

```python
"""main.py --settings and --restore-config (no window: run_settings is replaced)."""

import pytest

pytest.importorskip("gi")
pytest.importorskip("fabric")

import main as main_mod  # noqa: E402
import settings.app as settings_app  # noqa: E402


@pytest.fixture
def opened(monkeypatch):
    calls = []
    monkeypatch.setattr(settings_app, "run_settings", lambda path: calls.append(path) or 0)
    return calls


def test_settings_opens_the_window_on_the_given_config(tmp_path, opened):
    cfg = tmp_path / "c.toml"
    assert main_mod.main(["--settings", "--config", str(cfg)]) == 0
    assert opened == [cfg]  # need not exist: the window creates it on the first change


def test_settings_defaults_to_the_user_config(tmp_path, monkeypatch, opened):
    monkeypatch.setattr(main_mod, "USER_PATH", tmp_path / "config.toml")
    assert main_mod.main(["--settings"]) == 0
    assert opened == [tmp_path / "config.toml"]


def test_settings_opens_even_when_the_config_is_invalid(tmp_path, opened):
    cfg = tmp_path / "c.toml"
    cfg.write_text("[theme\n")
    assert main_mod.main(["--settings", "--config", str(cfg)]) == 0
    assert opened == [cfg]


def test_restore_config_puts_the_backup_back(tmp_path, capsys):
    cfg = tmp_path / "c.toml"
    cfg.write_text("broken\n")
    (tmp_path / "c.toml.bak").write_text("good\n")
    assert main_mod.main(["--restore-config", "--config", str(cfg)]) == 0
    assert cfg.read_text() == "good\n"
    assert "restored" in capsys.readouterr().out


def test_restore_config_without_a_backup_fails(tmp_path, capsys):
    assert main_mod.main(["--restore-config", "--config", str(tmp_path / "c.toml")]) == 1
    assert "no backup" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv",
    [
        ["--settings", "--list-outputs"],
        ["--settings", "--restore-config"],
        ["--settings", "--stats", "5"],
        ["--restore-config", "--stats", "5"],
    ],
)
def test_modes_do_not_combine(argv):
    with pytest.raises(SystemExit) as exc:
        main_mod.main(argv)
    assert exc.value.code == 2
```

- [ ] **Step 2: Run them to verify they fail**

Run: `scripts/py -m pytest tests/test_settings_app.py tests/test_main_settings.py -q`
Expected: collection errors, `ModuleNotFoundError: No module named 'settings.app'`.

- [ ] **Step 3: Implement**

Create `settings/window.py`:

```python
"""The settings toplevel: a normal xdg window (never a layer surface; KWin places it, usually
on the monitor with the pointer) holding a SettingsView, plus the Ctrl+Z undo action."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, Gtk

from settings.session import SettingsSession
from settings.view import SettingsView
from shell.outputs import Output

TITLE = "Edge Shell settings"


class SettingsWindow(Gtk.ApplicationWindow):
    def __init__(self, session: SettingsSession, outputs: list[Output], application=None):
        super().__init__(application=application, title=TITLE)
        self.set_default_size(860, 680)
        self.view = SettingsView(session, outputs)
        self.add(self.view)
        undo = Gio.SimpleAction.new("undo", None)  # Ctrl+Z (SettingsApp sets the accel)
        undo.connect("activate", lambda *_a: self.view.undo())
        self.add_action(undo)
        self.view.show_all()

    def file_changed(self) -> None:
        self.view.file_changed()
```

Create `settings/app.py`:

```python
"""The settings window's own process: a single-instance Gtk.Application (a second
`main.py --settings` brings the open window forward), separate from the running shell, which
only ever sees the config file change."""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from shell.config.loader import DEFAULT_PATH
from shell.outputs import Output, parse_kscreen, read_kscreen_json

log = logging.getLogger(__name__)

APP_ID = "org.edgeshell.Settings"
TOMLKIT_HINT = "the settings window needs tomlkit: scripts/py -m pip install 'tomlkit>=0.13'"


def connected_outputs() -> list[Output]:
    """Connected monitors (names and sizes) from kscreen-doctor; [] when it fails (the window
    then lists only the configured monitors and shows no layout preview)."""
    try:
        return parse_kscreen(read_kscreen_json())
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        log.warning("kscreen-doctor failed, showing configured monitors only: %s", exc)
        return []


class SettingsApp(Gtk.Application):
    def __init__(self, path: Path, default_path: Path = DEFAULT_PATH):
        super().__init__(application_id=APP_ID)
        self.path = path
        self.default_path = default_path
        self.window = None
        self.failed = False  # the config file could not be read: no window, exit code 2
        self._watcher = None

    def do_activate(self) -> None:
        if self.window is None:
            from settings.session import SettingsSession
            from settings.window import SettingsWindow
            from shell.config.models import ConfigError
            from shell.config.watcher import ConfigWatcher

            try:
                session = SettingsSession(self.path, self.default_path)
            except ConfigError as exc:  # unreadable (not invalid: that opens read-only)
                print(f"cannot open the settings: {exc}", file=sys.stderr)
                self.failed = True
                return  # no window and no hold: run() returns
            self.window = SettingsWindow(session, connected_outputs(), application=self)
            self.set_accels_for_action("win.undo", ["<Control>z"])
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._watcher = ConfigWatcher(self.path, self.window.file_changed)
        self.window.present()


def run_settings(path: Path, default_path: Path = DEFAULT_PATH) -> int:
    """Open the settings window on `path` (the shell's config file); returns the exit code."""
    try:
        import tomlkit  # noqa: F401
    except ImportError:
        print(TOMLKIT_HINT, file=sys.stderr)
        return 2
    import widgets  # noqa: F401  (registers the built-in panels: names and defaults)

    app = SettingsApp(path, default_path)
    code = app.run([sys.argv[0]])
    return 2 if app.failed else code
```

In `main.py`, replace the body of `main()` from `parser.add_argument("--list-outputs", …)` to the end of the function with:

```python
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--list-outputs", action="store_true", help="print monitors and connector names"
    )
    mode.add_argument(
        "--settings",
        action="store_true",
        help="open the settings window on the config file (works with or without a running "
        "shell; the file need not exist yet)",
    )
    mode.add_argument(
        "--restore-config",
        action="store_true",
        help="put back the config as it was before the last settings-window session changed "
        "it (config.toml.bak; the replaced file is kept as config.toml.before-restore)",
    )
    parser.add_argument(
        "--stats",
        type=_stats_seconds,
        default=None,
        metavar="SECONDS",
        help="measure for SECONDS (max 10): toggle every panel every 300 ms, then print frame "
        "pacing, canvas draw cost, canvas/panel cadence and CPU, and quit",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    if args.stats is not None and (args.settings or args.restore_config):
        parser.error("--stats only applies when running the shell")
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.list_outputs:
        from shell.monitors import describe_monitors

        print("\n".join(describe_monitors()))
        return 0

    path = args.config or USER_PATH
    if args.restore_config:
        from settings.files import restore_backup

        try:
            print(restore_backup(path))
        except ConfigError as exc:
            print(exc, file=sys.stderr)
            return 1
        return 0

    import widgets  # noqa: F401  (registers the built-in panels before the config is validated)

    if args.settings:
        # Before the ConfigStore: the window must open even when the file is invalid.
        from settings.app import run_settings

        return run_settings(path)

    try:
        store = ConfigStore(path, required=args.config is not None)
    except ConfigError as exc:
        print(f"config error:\n{exc}", file=sys.stderr)
        return 2

    from shell.app import EdgeShellApp

    return EdgeShellApp(store, stats_seconds=args.stats).run()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `scripts/py -m pytest tests/test_settings_app.py tests/test_main_settings.py tests/test_main.py -q`
Expected: `21 passed` (4 + 9 new, 8 existing).

Headless import check (creates no window): `scripts/py -c "import settings.window, settings.app; print('ok')"` prints `ok`.

- [ ] **Step 5: VERIFY and commit**

Run VERIFY. Expected: `1338 passed`.

```bash
git add settings/window.py settings/app.py main.py tests/test_settings_app.py tests/test_main_settings.py
git commit -m "feat(settings): settings window process, main.py --settings and --restore-config" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 11: A right-click on a panel handle opens the settings

**Files:**
- Modify: `shell/edge_panel.py` (`EdgePanel.__init__` signature, docstring and one attribute; `_on_press`)
- Modify: `shell/monitors.py` (`MonitorShell.__init__`; `_new_panel`)
- Modify: `shell/app.py` (imports, `MAIN_PATH`, `settings_command`, `_open_shell`, `open_settings`)
- Modify: `tests/test_app_sync.py` (`FakeShell.__init__`; one new test), `tests/test_monitor_shell.py` (the `build` fixture; one new test)
- Test: `tests/test_open_settings.py` (new)

**Interfaces:**
- Consumes: `main.py --settings --config PATH` (Task 10).
- Produces: `EdgePanel(..., on_settings: Callable[[], None] | None = None)` (button 3 on the handle calls it and stops the event; button 1 unchanged); `MonitorShell(..., on_settings=None)` passes it to every panel; `shell.app.MAIN_PATH`, `shell.app.settings_command(config_path: Path | None) -> list[str]`, `EdgeShellApp.open_settings()` (spawns in a new session; an `OSError` is logged and notified as "Settings not opened", never raised).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_open_settings.py`:

```python
"""Opening the settings window from the shell: a right-click on a panel handle (stand-ins only;
nothing is spawned)."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("gi")
pytest.importorskip("fabric")

import shell.app as app_mod  # noqa: E402
import shell.edge_panel as ep  # noqa: E402


def press(button):
    return SimpleNamespace(button=button, x_root=5.0, y_root=5.0)


def panel_stub(on_settings):
    return SimpleNamespace(
        _on_settings=on_settings,
        _interaction=SimpleNamespace(drag=True),
        _press=None,
        _d=0.0,
        _press_depth=None,
        _dragging=False,
        _suppress_click=False,
    )


def test_a_right_click_on_the_handle_opens_the_settings():
    calls = []
    s = panel_stub(lambda: calls.append(1))
    assert ep.EdgePanel._on_press(s, None, press(3)) is True
    assert calls == [1] and s._press is None  # not the start of a drag


def test_a_right_click_without_a_settings_callback_does_nothing():
    s = panel_stub(None)
    assert ep.EdgePanel._on_press(s, None, press(3)) is False
    assert s._press is None


def test_a_left_press_still_starts_a_drag():
    calls = []
    s = panel_stub(lambda: calls.append(1))
    assert ep.EdgePanel._on_press(s, None, press(1)) is False
    assert s._press == (5.0, 5.0) and calls == []


def test_settings_command_uses_this_interpreter_and_the_config(tmp_path):
    cfg = tmp_path / "c.toml"
    assert app_mod.settings_command(cfg) == [
        sys.executable,
        str(Path(app_mod.__file__).resolve().parents[1] / "main.py"),
        "--settings",
        "--config",
        str(cfg),
    ]
    assert app_mod.settings_command(None)[-1] == "--settings"


def test_open_settings_starts_its_own_process(monkeypatch, make_config, tmp_path):
    spawned = []
    monkeypatch.setattr(app_mod.subprocess, "Popen", lambda cmd, **kw: spawned.append((cmd, kw)))
    store = SimpleNamespace(config=make_config(), path=tmp_path / "c.toml")
    app_mod.EdgeShellApp(store).open_settings()
    ((cmd, kw),) = spawned
    assert cmd[-3:] == ["--settings", "--config", str(tmp_path / "c.toml")]
    assert kw["start_new_session"] is True  # Ctrl+C on the shell leaves the window open


def test_open_settings_failure_is_notified_not_raised(monkeypatch, make_config, tmp_path):
    notified = []

    def fail(cmd, **kw):
        if cmd[0] == "notify-send":
            notified.append(cmd)
            return None
        raise OSError("no such interpreter")

    monkeypatch.setattr(app_mod.subprocess, "Popen", fail)
    store = SimpleNamespace(config=make_config(), path=tmp_path / "c.toml")
    app_mod.EdgeShellApp(store).open_settings()
    assert notified and "Settings not opened" in notified[0]
```

In `tests/test_app_sync.py` replace `FakeShell.__init__`'s signature and first lines

```python
    def __init__(
        self, name, monitor, config, register, unregister=None, on_layout=None, on_error=None
    ):
        self.name = name
        self.monitor = monitor
        self.on_layout = on_layout
        self.on_error = on_error
```

with

```python
    def __init__(
        self,
        name,
        monitor,
        config,
        register,
        unregister=None,
        on_layout=None,
        on_error=None,
        on_settings=None,
    ):
        self.name = name
        self.monitor = monitor
        self.on_layout = on_layout
        self.on_error = on_error
        self.on_settings = on_settings
```

and add after `test_sync_reports_what_it_opened_and_closed`:

```python
def test_opened_shells_get_the_settings_opener(env):
    app, mapping = env
    mapping["HDMI-A-1"] = object()
    app.sync_monitors()
    assert app.shells["HDMI-A-1"].on_settings == app.open_settings
```

In `tests/test_monitor_shell.py`, in the `build` fixture replace

```python
    def _build(monitors, theme=None, monitor=None, on_layout=None, on_error=None):
        tracked = []
        cfg = make_config(monitors=monitors, theme=theme)
        shell = mon_mod.MonitorShell(
            "HDMI-A-1",
            monitor or FakeMonitor(),
            cfg,
            tracked.append,
            on_layout=on_layout,
            on_error=on_error,
        )
```

with

```python
    def _build(
        monitors, theme=None, monitor=None, on_layout=None, on_error=None, on_settings=None
    ):
        tracked = []
        cfg = make_config(monitors=monitors, theme=theme)
        shell = mon_mod.MonitorShell(
            "HDMI-A-1",
            monitor or FakeMonitor(),
            cfg,
            tracked.append,
            on_layout=on_layout,
            on_error=on_error,
            on_settings=on_settings,
        )
```

and add before `test_canvas_first_then_strips_then_panels`:

```python
def test_every_panel_gets_the_settings_opener(build):
    def opener():
        return None

    shell, _, _ = build(edge({"widget": "dock"}, {"widget": "clock"}), on_settings=opener)
    assert [p.kwargs["on_settings"] for p in shell.panels] == [opener, opener]
    shell, _, _ = build(edge({"widget": "dock"}))
    assert shell.panels[0].kwargs["on_settings"] is None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `scripts/py -m pytest tests/test_open_settings.py tests/test_app_sync.py tests/test_monitor_shell.py -q`
Expected: failures: `AttributeError: module 'shell.app' has no attribute 'settings_command'`, `TypeError: MonitorShell.__init__() got an unexpected keyword argument 'on_settings'`, and the right-click tests (`_on_settings` is ignored: `_on_press` returns False).

- [ ] **Step 3: Implement**

`shell/edge_panel.py`: in `EdgePanel.__init__`'s signature, after `interaction: Interaction = ALL_INTERACTIONS,` add

```python
        on_settings: Callable[[], None] | None = None,
```

extend the docstring's last sentence `change later in place (set_handle)."""` to

```python
        change later in place (set_handle). `on_settings()` is called on a right-click on the
        handle (EdgeShellApp.open_settings)."""
```

after `self._on_depth = on_depth` add

```python
        self._on_settings = on_settings  # a right-click on the handle opens the settings
```

and make `_on_press` start with the right-click:

```python
    def _on_press(self, _widget, event) -> bool:
        if event.button == 3 and self._on_settings is not None:
            self._on_settings()  # right-click: open the settings window (spec 13)
            return True
        if event.button != 1 or not self._interaction.drag:
```

(the rest of `_on_press` is unchanged).

`shell/monitors.py`: `MonitorShell.__init__` gains a last parameter and keeps it; replace

```python
        on_error=None,
    ):
        """`on_layout(shell)` is called after a re-layout this shell starts by itself (content
        measured, monitor geometry changed), so the app can report new layout warnings;
        `on_error(shell)` when such a re-layout raised (logged here; the app rebuilds us)."""
```

with

```python
        on_error=None,
        on_settings=None,
    ):
        """`on_layout(shell)` is called after a re-layout this shell starts by itself (content
        measured, monitor geometry changed), so the app can report new layout warnings;
        `on_error(shell)` when such a re-layout raised (logged here; the app rebuilds us);
        `on_settings()` is given to every panel (a right-click on its handle)."""
```

after `self._on_error = on_error or (lambda _shell: None)` add

```python
        self._on_settings = on_settings
```

and in `_new_panel`, after `interaction=req.interaction,` add

```python
                on_settings=self._on_settings,
```

`shell/app.py`: add `from pathlib import Path` after `from collections import defaultdict`; add before `def _already_running()`:

```python
MAIN_PATH = Path(__file__).resolve().parents[1] / "main.py"


def settings_command(config_path: Path | None) -> list[str]:
    """The command that opens the settings window on the shell's config file, with the
    shell's own interpreter (the venv that has Fabric and tomlkit)."""
    command = [sys.executable, str(MAIN_PATH), "--settings"]
    if config_path is not None:
        command += ["--config", str(config_path)]
    return command
```

in `_open_shell`, after `on_error=lambda shell, n=name: self._relayout_failed(n, shell),` add

```python
            on_settings=self.open_settings,
```

and add before `def _notify`:

```python
    def open_settings(self) -> None:
        """Start the settings window in its own process on this shell's config file (a
        right-click on a panel handle). A window that is already open is brought forward
        (single instance). Never raises into GTK."""
        command = settings_command(self.store.path)
        log.info("opening the settings window: %s", " ".join(command))
        try:
            subprocess.Popen(command, start_new_session=True, stdin=subprocess.DEVNULL)
        except OSError as exc:
            log.error("could not open the settings window: %s", exc)
            self._notify("Settings not opened", str(exc))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `scripts/py -m pytest tests/test_open_settings.py tests/test_app_sync.py tests/test_monitor_shell.py tests/test_edge_panel_drag.py tests/test_edge_panel_handle.py -q`
Expected: all pass (6 new in `test_open_settings.py`, 1 new in each of the other two).

- [ ] **Step 5: VERIFY and commit**

Run VERIFY. Expected: `1346 passed`.

```bash
git add shell/edge_panel.py shell/monitors.py shell/app.py tests/test_open_settings.py tests/test_app_sync.py tests/test_monitor_shell.py
git commit -m "feat(shell): a right-click on a panel handle opens the settings window" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 12: Gate example, README and spec

**Files:**
- Create: `examples/settings-test.toml`, `tests/test_settings_example.py`
- Modify: `README.md` (links, Requirements, a new "Settings window" section after "Handles and interactions", Known limitations)
- Modify: `docs/superpowers/specs/2026-10-11-edge-shell-design.md` (section 8 layout, section 13, section 14)

**Interfaces:**
- Consumes: everything above; the real widgets (`import widgets`).
- Produces: the gates' config; user documentation.

- [ ] **Step 1: Write the failing test**

Create `tests/test_settings_example.py`:

```python
"""The gate example config is valid with the real widgets and edits keep its comments."""

from pathlib import Path

import pytest

pytest.importorskip("gi")
pytest.importorskip("fabric")
pytest.importorskip("tomlkit")

import widgets  # noqa: E402, F401  (registers the built-in panels)
from settings.document import UserDocument  # noqa: E402
from settings.session import check_text  # noqa: E402

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "settings-test.toml"


def test_the_settings_example_is_valid_and_keeps_its_comments():
    text = EXAMPLE.read_text()
    config = check_text(text)
    assert [p.widget for p in config.monitor("HDMI-A-1").panels] == [
        "dock",
        "clock",
        "system_bar",
    ]
    assert config.monitor("DP-1").shell == "plasma"  # never edge (Phil tests on HDMI-A-1)
    doc = UserDocument(text)
    doc.set(("theme", "accent"), "#d3a68f")
    assert "# mint" in doc.text and 'accent = "#d3a68f"' in doc.text
```

Run: `scripts/py -m pytest tests/test_settings_example.py -q`
Expected: `FileNotFoundError` for `examples/settings-test.toml`.

- [ ] **Step 2: Create the example**

Create `examples/settings-test.toml`:

```toml
# Gates A and B (settings window plan): the shell and the settings window on a copy of this
# file, on HDMI-A-1 only. DP-1 is listed as "plasma" so the window shows it; never change it.
#   cp examples/settings-test.toml /tmp/edge-settings.toml
#   scripts/py main.py --config /tmp/edge-settings.toml -v              (terminal 1: the shell)
#   scripts/py main.py --settings --config /tmp/edge-settings.toml      (terminal 2: the window)

[theme]
accent = "#8fd3b6"   # mint: Gate A item 3 changes it; this comment must survive

[monitors.HDMI-A-1]
shell = "edge"       # the test monitor

[[monitors.HDMI-A-1.panels]]   # dock, bottom centre
widget = "dock"

[[monitors.HDMI-A-1.panels]]   # clock, top centre
widget = "clock"

[[monitors.HDMI-A-1.panels]]   # system bar, right edge
widget = "system_bar"

[monitors.DP-1]
shell = "plasma"     # holds the Plasma panel: leave it alone
```

Run: `scripts/py -m pytest tests/test_settings_example.py -q`
Expected: `1 passed`.

- [ ] **Step 3: README**

In the link list at the top, after the layout plan line, add:

```markdown
- [Settings window plan](docs/superpowers/plans/2026-10-14-settings-window.md)
```

In "Requirements", replace the Python line with:

```markdown
- Python 3.12+ with Fabric (from git), PyGObject **below 3.52**, pycairo, Pydantic 2, tomlkit
  (the settings window only: `scripts/py -m pip install 'tomlkit>=0.13'`)
```

In "Run", add after the `--stats` line:

```bash
scripts/py main.py --settings                              # the settings window (user config)
scripts/py main.py --settings --config /tmp/edge.toml      # ... on another file
scripts/py main.py --restore-config                        # undo the last settings session
```

Add a new section after "### Handles and interactions" (before "## Develop"):

````markdown
### Settings window

`scripts/py main.py --settings` opens a normal window that edits your config file (the
`--config` file if given, else `~/.config/edge-shell/config.toml`; it is created on the first
change). A right-click on any panel handle opens it too, on the running shell's config file.
Only one settings window runs at a time; opening it again brings it forward.

- **Theme** page: every theme key, the border, the shadow, the handle style and the layout gap.
  One page per monitor (connected monitors and the ones in your config): the shell mode
  (`edge`, `plasma`, `both`, `none`), the panels (add, remove, move up or down; every panel key
  including the handle and interactions), a preview of the layout warnings the shell would
  give, and per-monitor theme and layout overrides.
- Each row shows the value in effect and where it comes from (`your config`, `default`,
  `global theme`, `widget default`, ...). The reset button removes the key from your file, so
  the value is inherited again.
- Changes apply at once (spin buttons 0.4 s after the last change); the running shell reloads
  them like a hand edit. A change the shell would reject is not saved: the reason (with the
  key path) shows under the row.
- **Undo** (Ctrl+Z) steps back one change; **Revert all** puts the file back as it was when
  the window opened. Before its first change the window copies the file to `config.toml.bak`;
  `scripts/py main.py --restore-config` puts that copy back (the replaced file is kept as
  `config.toml.before-restore`).
- Your comments and formatting are kept: the window edits the file in place (tomlkit) and
  refuses a change it could not make without touching other keys. If you edit the file by hand
  while the window is open, it re-reads it and tells you; it never writes over a hand edit.
  An invalid file opens read-only with the error until it is fixed.

**Keyboard shortcut (KDE):** System Settings > Keyboard > Shortcuts > Add New > Command or
Script, command `/home/phil/Projects/pyDev/projects/myShell/scripts/py
/home/phil/Projects/pyDev/projects/myShell/main.py --settings`, then assign a key (for example
Meta+Alt+E).

`plasma` and `none` both leave a monitor to Plasma for now: hiding or showing Plasma's own panel
from the window is planned (it needs the Plasma integration, spec section 7).
````

In "Known limitations / planned", replace `- A settings window is not built yet.` with:

```markdown
- Settings window: no Plasma panel toggle yet, no tray icon, no drag-and-drop layout; `pos`
  (deprecated) is shown and can be removed, not edited; a panel with click, hover and drag all
  off takes no input while collapsed, so its handle cannot open the window (use another
  handle, the shortcut or `--settings`); KWin chooses the window's monitor.
```

- [ ] **Step 4: Spec**

In section 8's tree, after the `├── widgets/` line add:

```
├── settings/                 # the settings window (own process): form, document, session, GTK view
```

In section 13, after its paragraph, add:

```markdown
**Implemented (2026-10-14, plan `docs/superpowers/plans/2026-10-14-settings-window.md`):** a separate process (`main.py --settings`, single-instance `Gtk.Application` `org.edgeshell.Settings`), opened from the CLI, a right-click on any panel handle (on the shell's config file) or a KDE custom shortcut; the config file is its only link to the shell. The form is generated from `Config.model_json_schema()` and the widget registry (`settings/form.py`; per-monitor overrides use the base models' bounds, which `ThemeOverride`/`LayoutOverride` lose). Edits are made in place with tomlkit (comments kept), verified by re-parsing, checked by the shell's own loader and `validate_widgets`, and written atomically (symlinks kept); never an invalid file. Live apply (spin buttons debounced 400 ms), Undo/Ctrl+Z, Revert all, per-field reset; `config.toml.bak` per session and `main.py --restore-config`; hand edits while the window is open are re-read and never overwritten; an invalid file opens read-only. Deferred: hiding or showing Plasma's panel (needs section 7 and spike 2), tray icon, drag-and-drop layout, HiDPI. Gate results: see the plan's Tasks 13-14 (recorded below after the gates).
```

In section 14, replace the second bullet with:

```markdown
- Should the settings window also expose a drag-and-drop layout editor, or only form fields? **v1 is forms only** (settings window plan, decision 1); drag-and-drop is revisited after Phil has used v1.
```

- [ ] **Step 5: VERIFY and commit**

Run VERIFY. Expected: `1347 passed`.

```bash
git add examples/settings-test.toml tests/test_settings_example.py README.md docs/superpowers/specs/2026-10-11-edge-shell-design.md
git commit -m "docs(settings): gate example, README section, spec 13 as implemented" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 13: Gate A (Phil, live on HDMI-A-1): the window and live reload

No code. The controller prepares the commands; **Phil runs them** (subagents never launch the shell or the window). DP-1 is never changed: its page shows `plasma`, leave it.

**Prepare (Phil):**

```bash
cp examples/settings-test.toml /tmp/edge-settings.toml
scripts/py main.py --config /tmp/edge-settings.toml -v              # terminal 1: the shell
scripts/py main.py --settings --config /tmp/edge-settings.toml      # terminal 2: the window
```

Keep terminal 1 visible: each change should print `config reloaded: N change(s): <kinds>`.

**Checklist** (Phil answers each with pass / what was seen):

1. The window opens as a normal window titled "Edge Shell settings" (title bar, movable, in the task switcher), not as part of the frame. Pages in the sidebar: Theme, HDMI-A-1, DP-1. The top bar shows Undo (greyed), Revert all and the file path. *On failure:* note what appeared (screenshot with `spectacle`); if it is missing from the task switcher or looks like a panel, stop: decision 3 is wrong.
2. Theme page: the accent row shows the mint colour, "default" sources everywhere except accent ("your config"). *On failure:* note the row and its text.
3. Change **frame** with its colour button to a clearly different colour (for example a dark red): within about 1 s the frame and every panel body on HDMI-A-1 take it; terminal 1 shows `restyle`; DP-1 is unchanged. Then change **accent** to any other colour (nothing visible uses it by default) and run `grep -n accent /tmp/edge-settings.toml`: the accent line still ends with `# mint: Gate A item 3 changes it; this comment must survive`. *On failure:* copy the log line and the grep output.
4. Border: switch **enabled** on, set **width** with the spin arrows from 2 to 6 by clicking quickly: the border appears and grows; terminal 1 shows one or two `restyle` reloads, not one per click. Then **thickness** 10 → 14 with the arrows: one `rebuild-monitor` after you stop; press **Ctrl+Z** in the window: thickness is back to 10 (another reload). *On failure:* count the reload lines; note whether Ctrl+Z did nothing.
5. HDMI-A-1 page, panel 1 (dock): open it, set **align** `end`, **offset** 40: the dock moves to the bottom right (`panel-rebuild`); set **handle > shape** `chevron`: the handle becomes a chevron with no `building panel` line in the `-v` log (`panel-handle`); set **interaction > hover** off: hovering the collapsed strip no longer peeks. *On failure:* note the kind printed and what moved.
6. **Add panel** with `clock`: a second clock appears (top centre, next to the first; `panel-add`), its entry "4. clock: top, center" opens in the window. Move it up twice (it becomes "2. clock …", right after the dock; the two clocks may swap places on screen, since equal orders keep the config order), then remove it: the shell follows each step; no error banner. *On failure:* note the step and the banner text.
7. Dock **length**: `fill` (spans the bottom edge between its neighbours), `percent` 50 (half the free span), back to `px` 560. *On failure:* note the mode and what the dock did.
8. Dock length `px` 3000: the window shows a warning under the panel list ("... shrunk ..."), and the shell sends a "Panels adjusted" notification. Set it back to 560 (or Ctrl+Z). *On failure:* note which of the two did not happen.
9. HDMI-A-1 **shell** mode `plasma`: the frame and panels on HDMI-A-1 disappear (`rebuild-monitor`), DP-1 is untouched; back to `edge`: they return. *On failure:* stop and switch it back by Ctrl+Z; note the log.
10. Dock **min_length** 600, then **max_length** 300: the second change is refused, a red "Not saved: … min_length must not be larger than max_length" appears under max_length, `/tmp/edge-settings.toml` has no `max_length`, terminal 1 prints nothing new. Reset min_length with its reset button. *On failure:* copy the message or the file.
11. Theme accent **reset** button: the accent returns to the default `#8fd3b6`, the row says "default", and the `accent` line is gone from the file (`grep accent /tmp/edge-settings.toml` prints nothing). *On failure:* note the row and the file.
12. **Revert all** → OK in the dialog: the shell returns to the start state; `cmp /tmp/edge-settings.toml examples/settings-test.toml` prints nothing. *On failure:* run `diff` instead of `cmp` and copy it.
13. `cat /tmp/edge-settings.toml.bak` equals the example (the backup made before the first change). Close the window and stop the shell (Ctrl+C in terminal 1). *On failure:* copy the backup's first lines.

---

### Task 14: Gate B (Phil, live on HDMI-A-1): safety and entry points; record the results

**Prepare (Phil):** as in Gate A (fresh copy: `cp examples/settings-test.toml /tmp/edge-settings.toml`), shell in terminal 1 and the window in terminal 2.

1. **Hand edit while open:** in a text editor change `accent = "#8fd3b6"` to `"#d3a68f"` in `/tmp/edge-settings.toml` and save: the shell reloads (`restyle`), the window shows a blue banner "… was changed outside this window …" and the accent row shows the new colour. *On failure:* note whether the window or the shell missed it.
2. Then change the dock **depth** in the window to 80: written on top of the hand edit (`grep -E 'accent|depth' /tmp/edge-settings.toml` shows both). *On failure:* copy the grep.
3. **Invalid hand edit:** add `thickness = 1` under `[theme]` and save: the shell notifies "Config not applied" and keeps running; the window shows a red banner naming `theme.thickness` and its pages are greyed out. Fix it (remove the line, save): the window becomes editable again. *On failure:* note which side did not react.
4. **Restore:** make two more changes in the window (any), close it, run `scripts/py main.py --restore-config --config /tmp/edge-settings.toml`: it prints `restored … from ….bak (the replaced file is ….before-restore)`; the file is back to how it was before the window's first change of this session (item 2): accent `#d3a68f` from the hand edit, no dock `depth`; the shell reloads to that. *On failure:* copy the output and `cat /tmp/edge-settings.toml`.
5. **Single instance:** with the window open, run `scripts/py main.py --settings --config /tmp/edge-settings.toml` again: no second window; the open one comes forward (or its taskbar entry flashes, if KWin's focus-stealing prevention holds it back); the command exits 0 (`echo $?`). *On failure:* note what opened.
6. **Right-click a handle:** close the window. Right-click the dock's handle: the settings window opens on `/tmp/edge-settings.toml` (path in its top bar) and terminal 1 logs `opening the settings window: …`. Left-click still toggles the dock, dragging still works. *On failure:* copy the log line; note whether the window opened behind other windows.
7. **Without the shell:** close the window, stop the shell (Ctrl+C). Run `scripts/py main.py --settings --config /tmp/edge-settings.toml`: it opens; change the clock's **state** to `collapsed`, close it. Start the shell again: the clock starts collapsed. *On failure:* note the step.
8. **KDE shortcut (optional):** add the shortcut from the README with `--config /tmp/edge-settings.toml` appended, press it: the window opens. Remove the shortcut afterwards if it was only for the gate. *On failure:* note what happened (information only; not blocking).
9. **A panel over the window:** move the window over the bottom of HDMI-A-1, then set the dock **depth** to 900 (extended): the dock covers part of the window. With the window still focused press **Ctrl+Z**: the dock shrinks back. *On failure:* note whether the keyboard still reached the window (then decision 6 needs the countdown).

**Record the results (controller, after Phil's answers):** in the spec's section 13 replace "Gate results: see the plan's Tasks 13-14 (recorded below after the gates)." with a short "Results." paragraph (each gate item: passed, or what was seen and what was changed), and adjust the README if a gate changed behaviour. VERIFY (expected `1347 passed`), then:

```bash
git add docs/superpowers/specs/2026-10-11-edge-shell-design.md README.md
git commit -m "docs: record the settings window gate results" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Self-review

- **Spec coverage.** Spec 13: normal window (Task 10, decision 3), opened from a key binding (README + Gate B item 8), frame handle (Task 11), tray icon (deferred, decision 1); colours, monitor modes, panel positions, widget list (Tasks 5-9); hiding or showing the Plasma shell (deferred with its cost, decision 1); writes the user file only (Tasks 2-4, Global Constraints); form from the JSON schema and the registry (Task 5, Task 8's widget list). Spec 6: validation with key paths (Task 4, shown in Task 9), invalid config never replaces a working one (Task 4: never written; the shell's own rule still holds for hand edits). Spec 16: slot, order and gap exposed and the overlap warning shown (Tasks 6 and 9: `layout_preview`). Spec 14: forms only (Task 12).
- **Placeholders.** None: every code step carries the full file or the exact replacement; every test is written out.
- **Type consistency.** `UserDocument` methods (Task 3) are what `SettingsSession.apply` edits receive (Task 4) and what `PanelEditor` and `SettingsView` build (Tasks 8-9); `on_edit(edit, open_index)` matches between Tasks 8 and 9; `FieldValue` (Task 6) is what `FieldRow.show_value` takes (Task 7); `settings_command` / `open_settings` (Task 11) call `--settings --config` from Task 10; `SettingsWindow.file_changed` (Task 10) forwards to `SettingsView.file_changed` (Task 9).
- **Prototype.** Every module and test in Tasks 1-12 was run in a scratch copy of the worktree (with tomlkit 0.15.1 from the local uv cache on the path): `1347 passed`, ruff clean; with tomlkit hidden: `1273 passed, 6 skipped`. The GTK tests built widgets only.

## Open questions for Phil

1. **tomlkit:** OK to add the dependency and install it in the shared venv (`scripts/py -m pip install 'tomlkit>=0.13'`)? (Decision 2; the alternative is the overlay file.)
2. **Opening from the frame:** is a right-click on a panel handle the gesture you want (decision 3), or a dock button / middle click instead? Which key for the KDE shortcut?
3. **Plasma toggle:** deferring "hide or show the Plasma shell" to its own plan (spike on a temporary HDMI-A-1 panel first) OK? (Decision 1.)
4. **Live apply** without an Apply button, with Undo/Revert all and no 15 s confirm countdown: OK? (Decisions 5, 6.)
5. Not part of this plan, noticed while reading Fabric: `fabric.Application` registers `org.Fabric.fabric.edge-shell` on the session bus with `Execute`/`Evaluate` methods that run arbitrary Python inside the shell for any local session-bus client. The settings window does not use it. Turning it off (`Application(..., open_client=False)`) would be a one-line follow-up if nothing else needs it.
