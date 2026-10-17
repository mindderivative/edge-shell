# Settings Input Styles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the settings window the input styles of spec section 8: dropdowns that open at the size of their entries, thin toggles with a round knob, a slider (with a spin button for exact typing) for every whole number with a short bounded range, and a searchable font dropdown over the installed families (the desktop's font first), used one per family in the theme's font list and for a widget's font property.

**Architecture:** The dropdown fix is one call on every combo the window makes (`opens_below`: `wrap_width` 1, which takes GTK's popup path that anchors the menu below the combo instead of laying it over the combo with the active entry on it). All CSS moves into one pure module, `settings/style.py` (CSS text as data, tested without GTK; `install_css()` adds it once at USER priority, every rule scoped by a style class), which restyles our `Gtk.Switch`es. `settings/form.py` decides which rows are sliders (`uses_slider`, pure) and that a widget property named `font` is a font row (`kind="font"`); `settings/fonts.py` (pure) builds the font lists; `settings/fontpicker.py` (GTK) is the picker (a `Gtk.MenuButton` with a `Gtk.Popover`: search entry above a `Gtk.ListBox`) plus the Pango and `Gtk.Settings` readers; `settings/fields.py` gets `SliderEditor`, `FontListEditor` and `FontEditor` behind the unchanged `FieldRow` contracts (`show_value(value, keep_pending)`, `flush`, `unsent`, `discard`, the reset button, the error line, the edit queue).

**Tech Stack:** Python 3.14 (>=3.12), PyGObject 3.50.0 (`<3.52`), GTK 3.24.52 (`Gtk.ComboBoxText`, `Gtk.Switch`, `Gtk.Scale`, `Gtk.SpinButton`, `Gtk.Adjustment`, `Gtk.MenuButton`, `Gtk.Popover`, `Gtk.ListBox`, `Gtk.CssProvider`), Pango / PangoCairo 1.0 (font families, font descriptions), pydantic 2, tomlkit 0.15.1, pytest, ruff 0.17.0.

**Spec:** `docs/superpowers/specs/2026-10-14-panel-widget-model-design.md` section 8 (Plan 4, the contract), sections 1-2 (goal, plan order, a live gate on HDMI-A-1 for every plan, DP-1 never touched), 9-10 (risks: "Gtk popup sizing may not have a clean fix on this GTK version (plan 4, spike first)"; Phil's decisions). Earlier plans for style and contracts: `docs/superpowers/plans/2026-10-14-settings-window.md`, `docs/superpowers/plans/2026-10-15-settings-menus.md`, `docs/superpowers/plans/2026-10-15-settings-tree.md` (the edit queue, the 640 px tab budget).

**Phil's request (verbatim):** "6. Input styles - Color picker is good - Toggles should be thinner in height with handles being round not oval shaped - If a numeric has a minimum and maximum use sliders instead of number spinners. - Font: list system available fonts in a dropdown that is searchable by typing. Default should be the system selected font. - DropDown's menu should fit the content on open. Right now it sizes to a single entry with scrolling and then resizes to fit the content when it detects a mouse over or scroll wheel input."

**Decided with Phil earlier:** the dropdown sizing starts as an investigation (reproduce headless as far as possible, find the cause, deliver the smallest fix: `set_wrap_width`, `popup-fixed-width`, CSS `min-height` on menu items, `Gtk.ComboBoxText` against a `Gtk.MenuButton` + `Gtk.Popover` list; with no clean fix, replace the choice editor by a popover list, also used by the font picker), and it must say plainly what is verified headless and what only Phil can see live. The colour picker stays as it is.

**Date:** 2026-10-16. **Size:** 8 tasks: 6 with code and tests (1-6), Task 7 the docs and the gate checklist (Phil runs the gate), Task 8 recording the gate results. Riskiest: Task 1 (the fix is verified live only), Task 3 (the slider changes the most common row and its tests), Task 5 (the font list replaces the typed-text font entry, so the typed-text tests move to the name row).

## Decisions (each *default pending Phil* unless marked decided; alternatives and their cost)

1. **Dropdown sizing: `wrap_width` 1 on every combo (`opens_below`), decided by investigation.** *Default pending Phil's gate.* **Cause.** GTK 3.24 pops up a combo's menu in one of two ways (`gtk/gtkcombobox.c`, `gtk_combo_box_menu_popup`, gtk-3-24 branch). With `wrap_width == 0` (our combos today) it lays the menu over the combo with the ACTIVE entry on top of it: `rect_anchor_dy` is minus the height of the entries above the active one, the anchor hints are slide and resize (no flip), and a `popped-up` handler sets the menu's scroll offset once it is up. On Wayland that popup is an xdg-popup the compositor constrains: KWin slides and resizes it to fit, and GtkMenu draws scroll arrows over a menu one entry high until a motion or wheel event makes it measure again: exactly Phil's report. With `wrap_width > 0` GTK takes the other path: the menu anchors below the combo (`GDK_GRAVITY_SOUTH_WEST` to `NORTH_WEST`, flip, slide and resize; no offset), so it opens at its size (above the combo when there is no room below). With one column the grid menu is a plain list. **Candidates rejected:** `popup-fixed-width` (it only chooses the menu's width, minimum against natural: not the placement); CSS `min-height` on menu items (row height, not the placement); the `appears-as-list` style property (a different popup, a tree view in its own window: another look, and GTK 3 marks it deprecated); a `Gtk.MenuButton` + `Gtk.Popover` list (a popover is drawn inside the window, so it cannot be shrunk by the compositor, but it replaces `ChoiceEditor`'s `Gtk.ComboBoxText` API that the toolbar and about 30 tests use: about one task). **Headless (verified by the tests and the command in Task 1):** every combo of the window has `wrap_width` 1, its popup is GTK's `GtkTreeMenu` with one item per entry, greyed-out entries stay greyed out. **Live only (Phil, Gate item 1):** the popup's size and place on KWin. **Contingency** if Gate item 1 fails: a follow-up task replaces `ChoiceEditor`'s combo with a popover list built on `settings.fontpicker`'s list (without the search entry), which cannot be constrained by the compositor; nothing in this plan depends on that.
2. **Toggles: `Gtk.Switch` restyled by a class-scoped stylesheet, centred in its row.** *Default pending Phil.* Measured headless: the switch in a row is **52 x 30 px** today: Breeze's switch is 52 x 24, and the row (about 30 px high, its Reset button) stretches it vertically because the switch is not `valign`-centred; GTK 3.24 gives the knob (`slider`) half the content width and the whole content height, so the stretched knob is a tall oval. GTK never draws the switch's content smaller than **32 x 16 px** (measured with Breeze and with Adwaita, also with the font size set to 0: it is not the text). So the stylesheet sets every size: content 32 x 16 (2:1, so the knob is a circle), knob 16 px across with a 1 px border (`min-width/min-height: 14px`, `border-radius: 50%`), track padding 2 px and border 1 px, pill radius: **38 x 22 px** outside, and the switch is `valign` CENTER. The theme keeps its colours. A provider at USER priority wins over the theme's rules whatever their specificity (GTK cascades by priority first), so one rule per node holds in every state (`:checked`, `:backdrop`, `:disabled`, `:hover`); no state rules are needed. Scoped by the class `edge-switch` on our switches only, never a bare `switch` selector. A knob larger than the track (Material style) is not possible with GTK 3 CSS (the knob is drawn inside the track's content box): it needs a custom-drawn widget, about one task. *Cost to change the size:* `KNOB_PX` is GTK's floor; only padding and border can shrink (20 px is the least with a 1 px border and 1 px padding).
3. **Sliders: an `int` with both bounds and a range of at most 500 (`SLIDER_MAX_SPAN`) is a slider and a spin button on one `Gtk.Adjustment`.** *Default pending Phil (open question 2).* Phil: "If a numeric has a minimum and maximum use sliders instead of number spinners"; the spec adds "px/length fields keep spin + unit", read here as the length row (mode + number) and the wide pixel ranges. Sliders: thickness 2-64, radius 1-64, peek 1-64, hover zone 1-64, border width 1-16, shadow elevation 0-100, handle size 4-40 and weight 1-8 (theme and panel), gap 0-400, the clock's font size 6-96. Spin buttons stay for duration 0-5000 ms, offset ±20000, handle offset ±2000, order 0-1000, depth 16-2000, min/max length 60-4000, corner width/height 60-4000 (a 160 px slider would move 6 to 250 values per pixel there), and the length row. **Widget:** `Gtk.Scale` (160 px, no drawn value, `round_digits` 0, accessible name = the row's label) and beside it the spin button (`strict_spin`: typed text, Enter, focus-out, flush, invalid text revert, as before). One adjustment means one `value-changed` per change, whichever is moved; the editor sends `int(round(value))`. **Edits:** the row is `kind == "int"`, so its edits go through the view's edit queue with the shared 0.4 s timer: a drag pushes every whole number on the way, the queue keeps the last one per path, and a drag back to the shown value un-queues it (nothing written; an inherited value stays inherited). **Keys:** a focused slider takes Left/Right/Up/Down (one step), Page Up/Down (a tenth of the range), Home, End (GtkRange's own bindings). **Wheel:** never edits (`wheel_scrolls_the_page` on the slider and on the spin button). **Unset optional value** (the clock's `font_size`, None = the theme's size): shows the minimum, like a spin row today, and the note says where the value comes from; nothing is written until the user moves it. **`FieldRow` packs `editor.outer`** (the box of slider and spin for a slider, the value widget otherwise); `editor.widget` stays the spin button, so the rebuild's refocus, `flush`, `unsent` and every existing test that sets a number keep working unchanged.
4. **Fonts: a `Gtk.MenuButton` with a `Gtk.Popover` (a search entry above a `Gtk.ListBox`), not a `Gtk.ComboBox` with entry completion.** *Default pending Phil.* Phil: "a dropdown that is searchable by typing". A combo over 300 families is the Wayland-constrained GtkMenu of decision 1 at its worst, and a `Gtk.EntryCompletion` popup is a compositor popup too; a popover is drawn inside the settings window, so it opens at its size: a list sized to its rows up to 360 px (`propagate_natural_height`, `max_content_height`), then it scrolls; 280 px wide. Typing filters by any part of the name, ignoring case (`settings.fonts.matches`); Enter picks the first row shown; a click picks any row; Escape closes. The button shows the font (22 characters, the rest cut, the whole name as its tooltip). **The list** (`settings.fonts.picker_entries`): the inherited row (a widget's font: "Theme font"), a configured name that is not installed ("NAME (not installed)", selected, kept: opening the list never drops it), the desktop's font ("NAME (system font)": the family of `Gtk.Settings:gtk-font-name`, which KDE sets to its General font; on Phil's machine today "Hack Nerd Font"), the CSS generic families `monospace`, `sans-serif`, `serif` (the shell writes them unquoted), then every installed family. **Families** (`installed_families`): Pango's font map (`PangoCairo.FontMap.get_default().list_families()`, about 300 here, 6 ms), read once per process when a list first opens (`functools.cache`), without fontconfig's aliases ("Monospace", "Sans", "Serif", "System-ui"), without a name `check_font_name` refuses (it could not be written: it goes into CSS), one per name regardless of case, sorted without case. Tests replace `fontpicker.installed_families` and `fontpicker.system_family` (looked up when a list opens), so no test depends on the machine's fonts. **Writing:** only names from the list can be picked (no free text), so the window cannot write a name the model refuses; a name already in the file that the model accepts is shown and kept.
5. **"Default should be the system selected font": the desktop's font is the first family of every list and what Add font adds; nothing is written while a row is unset.** *Default pending Phil (open question 1).* The spec says "the unset state shows System font (resolved from `Gtk.Settings:gtk-font-name`) and writes nothing". In the config model that is not what unset means: an unset widget `font` is the theme's font (`widgets/clock.py`: "reset: the theme's font"), and the theme's `font` list is required (`min_length=1`) and comes from `config.default.toml` (Hack Nerd Font Mono, JetBrains Mono, monospace). So: a widget's Font row shows "Theme font" while unset and its list starts with "Theme font", which resets the key (writes nothing, `UNSET` in `FieldRow`); the theme's font list shows the inherited list (its note says "default"). Picking "NAME (system font)" writes that family name. *Alternative (A), one task:* a reserved name `system-ui` (CSS's own generic name for the desktop's UI font) that the shell resolves to the `gtk-font-name` family when it writes CSS (`shell/theme.py`), offered as "System font (NAME)", and optionally the shipped default list starting with it: the shell's look would then follow the KDE font setting. Not done here: it changes the shell and its default look, which this plan (input styles) should not decide alone.
6. **The theme's font list: one picker per family, with Move up, Move down, Remove and Add font.** *Default pending Phil.* The list is an ordered fallback (the first installed family is used), so order matters: each line is a picker and three icon buttons (`go-up-symbolic`, `go-down-symbolic`, `list-remove-symbolic`, with tooltips and accessible names); Add font appends the desktop's font, else the first generic family the list does not hold (`next_font`). Every change sends the whole list at once (no typed text, `dirty()` is False). The last family's Remove is insensitive (the model needs one). Lines are hidden, never destroyed, when the list gets shorter: a line's own Remove click must not free the button its signal runs in (the view defers its own destroys for the same reason). *Rejected:* the comma-separated entry with completion on the word under the cursor (typing only, no browsing, and the completion popup is a compositor popup). *Cost:* the old `FontsEditor`, `parse_fonts`, `format_fonts` go; the tests that used the font entry as "a row with typed text" use the panel name row instead (same contracts).
7. **Rows that change (migration).** `IntEditor` (spin) becomes `SliderEditor` where `uses_slider`; `LengthEditor` (mode + number) stays; `BoolEditor` gets the style class and `valign` CENTER; `ChoiceEditor` and the length mode combo get `opens_below`; `FontsEditor` becomes `FontListEditor`; a widget's `font` property (`TextEditor` today) becomes `FontEditor`; `ColorEditor`, `TextEditor` (name, clock format), `DeprecatedEditor` are unchanged. Every `FieldRow` contract stays: `show_value(value, keep_pending)` (a slider with a queued edit keeps it, as a spin did), `flush()` (a number typed in a slider's spin button is sent), `unsent()`, `discard()`, the reset button (resets through the queue as before), the error line, the 150 px label and the 28-character note. **Width:** every tab stays within 640 px (the tree plan's budget): measured at most 549 px (the General tab with the font list), 524 px on panel pages including the clock's Widget tab; Task 6 adds the clock and corner pages, with a 60-character font name, to the width test.
8. **One stylesheet module.** `settings/style.py` holds all of the window's CSS: the info note's colours move there from `settings/view.py` (cheap: two constants, one function, two tests move) and the switch rules join them; `install_css()` adds one provider once at USER priority; `BoolEditor` calls it too (idempotent), so a switch built outside the view (a test) has the look. The module imports GTK only inside `install_css()`, so the CSS text is tested on the CI runner (no `gi`).
9. **Performance.** The font list is built when a picker opens, not when the page is built (about 40 pickers would otherwise build 300 rows each); the families are read once per process. Sliders and switches cost what the spin buttons and switches did.

## Out of scope (later plans)

- The `system-ui` font resolved by the shell (decision 5, alternative A); a custom-drawn toggle with a knob larger than its track; a popover replacement of every combo (decision 1, contingency only).
- Float panels, Plasma panel hide/show, width/height and scrolling for every panel kind, widget discovery (memory: future-panel-sizing-and-scrolling, widget-discovery-plugins).

## Prerequisites

- Branch `feat/input-styles` from `origin/main` `be65690` (settings window, panel/widget model, menus, tree and tabs merged), in the worktree `/home/phil/Projects/pyDev/projects/myShell/.claude/worktrees/feat-edge-shell-core`.
- Baseline before Task 1: `scripts/py -m pytest -q` prints `2626 passed` (0 skipped; warnings are normal); `scripts/py -m ruff check .` prints `All checks passed!`; `scripts/py -m ruff format --check .` reports every file formatted. With GTK blocked (below): `1905 passed, 33 skipped`.
- tomlkit and PangoCairo are available: `scripts/py -c 'import tomlkit, gi; gi.require_version("PangoCairo", "1.0"); from gi.repository import PangoCairo; print(tomlkit.__version__)'` prints `0.15.1`. If it fails, STOP and report (tests would skip, and a skipped test must not read as green). Nobody installs packages.
- **How the code steps are written.** Every code step is a unified diff made from the measured prototype (each task applied in order on a copy of `be65690`, `ruff format` run, the suite run after each; the totals below are those runs). Save a step's diff block to a file (for example `/tmp/claude-1000/step.diff`) and apply it from the worktree root with `git apply --whitespace=nowarn /tmp/claude-1000/step.diff`; a new file appears in full (`new file mode`). Apply a task's test diff (Step 1) before its implementation diff. If a diff does not apply, STOP and report: do not hand-merge silently. Stage files by name, never `git add -A` or `git add .`.

## Global Constraints

- Python only through `scripts/py` (shared venv `/home/phil/Projects/pyDev/pyEnvs/global-base`). **PyGObject must stay `<3.52`** (Fabric 0.0.2 breaks on 3.52+).
- **Pure modules import no GTK / `gi` at import time:** the new `settings/fonts.py` and `settings/style.py` (its `install_css()` imports GTK when called), and as before `settings/form.py`, `settings/values.py`, `settings/queue.py`, `settings/pages.py`, `settings/screens.py`, `settings/panels.py`, `settings/files.py`, `settings/document.py`, `settings/session.py`, `settings/menus.py`, `settings/fileops.py`, `settings/about.py`, `settings/launch.py`.
- **The settings process never imports Fabric or `widgets` from its modules** (`test_the_settings_process_never_imports_fabric_windows` stays green): `settings/fontpicker.py` imports only `gi` (Gtk, Pango, PangoCairo) and `settings.fonts`.
- **The window writes only** the config file it shows and the files plans 1-3 named (`.bak`, `.before-revert`, File menu files). Never `config.default.toml`. **No change to the shell** (`shell/`, `widgets/`): the config model and its meaning are unchanged.
- **CSS** is scoped by a style class this window sets (`edge-switch`, `info-note`); never a bare element selector; one provider, USER priority, installed once.
- **The mouse wheel never edits a row** (sliders, spin buttons, combos: `wheel_scrolls_the_page`).
- **Tests.** CI installs only pycairo, pydantic, pytest, ruff and tomlkit: tests importing `gi` start with `pytest.importorskip("gi")` (module level, or the `gtk` fixture of `tests/test_settings_style.py` for single tests); GTK tests call `gi.require_version("Gtk", "3.0")` (and `"Gdk", "3.0"`) before `gi.repository`, skip unless `Gtk.init_check()[0]`, and **never create or show a window, run a dialog, spawn a process or depend on the installed fonts**: plain widgets, emitted signals, `size_allocate` on a plain box, a popover opened as a widget flag (no toplevel exists, nothing is mapped), fake font lists. Never call `Gtk.Application.run`.
- **Lint.** `ruff` 0.17.0, line length 100, rules E, F, I, UP, B; excludes `docs/` and `*.md`.
- **VERIFY** (before every commit): `scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q`. The suite must be green at the end of EVERY task (0 failed, 0 skipped) with exactly the total in the File Structure table. At the end of Task 6 also run it with GTK blocked, as the CI runner has no `gi`: `mkdir -p /tmp/claude-1000/nogi/gi`, write `raise ModuleNotFoundError("No module named gi (blocked)", name="gi")` into `/tmp/claude-1000/nogi/gi/__init__.py`, then `PYTHONPATH=/tmp/claude-1000/nogi scripts/py -m pytest -q` prints `1916 passed, 36 skipped` (only skips, no error).
- **Git.** Plain separate git commands run from the worktree (no `cd … && git`, no command substitution around git). Stage files by name. **Never push.** Every commit message ends with a second `-m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`.
- **Live runs.** Phil is the only visual tester, on `HDMI-A-1` only. **Never touch `DP-1`** (it holds the Plasma panel; never set it to `edge` or `both`, in a file or in the window; never click its checkboxes). Subagents executing tasks never launch the shell or the settings window (`main.py` without `--list-outputs`, including `--settings`), never open a window or a dialog; headless commands are fine (`pytest`, `scripts/py -c` checks). The gate (Task 7's checklist) is run by Phil.

## Review Focus

The five failure modes most likely to bite Phil that the spec implies but a happy-path test would not catch, each pinned by a test in the owning task:

1. **A slider drag writes 50 values, or a drag back pins an inherited value.** A drag emits every whole number on the way; expect one write after the pause and nothing at all when the slider ends where it started. Pinned by `test_a_slider_drag_is_one_queued_edit_and_a_drag_back_none` (Task 3, with the real `EditQueue`); live by Gate item 3.
2. **The mouse wheel over a new input edits it** (a slider under the pointer while scrolling a long tab). Expect the page to scroll and nothing to change. Pinned by `test_the_mouse_wheel_never_edits_a_row` (Task 3 adds the slider and its spin button) and `test_the_mouse_wheel_edits_no_input_of_the_window` (Task 6: every scale, spin button and combo of a real view, the toolbar's included, file unchanged); live by Gate item 5.
3. **A font in the file that is not installed (a typo, a font from another machine) is dropped or replaced when the list opens.** Expect it shown on the button, listed first as "NAME (not installed)" and selected, and the file unchanged until the user picks another. Pinned by `test_a_font_that_is_not_installed_is_listed_and_kept` (Task 4) and `test_a_widget_font_that_is_not_installed_is_shown_and_kept` (Task 6); live by Gate item 10.
4. **The font list edited through its own buttons** (Remove clicked on its own line, the last font removed, a re-read with more fonts than lines). Expect the line hidden, not destroyed inside its own click; the last Remove insensitive and never sent; new lines for a longer list. Pinned by `test_the_last_font_cannot_be_removed_and_a_shorter_list_hides_lines` and `test_moving_removing_and_adding_fonts` (Task 5); live by Gate item 11.
5. **A new input widening a tab past the 640 px beside the tree** (a 60-character font name, the clock's Widget tab, a corner panel page): expect no tab wider than 640 px, the Reset buttons on screen. Pinned by `test_the_clock_and_corner_pages_fit_beside_the_tree_too` (Task 6) with `test_no_tab_is_wider_than_the_space_beside_the_tree_at_860` (kept); live by Gate item 12.

## File Structure

```
settings/style.py               # CREATE (Task 2): INFO_NOTE_CLASS, INFO_NOTE_CSS (moved from view),
                                #   SWITCH_CLASS, KNOB_PX, BORDER_PX, TRACK_PADDING_PX, SWITCH_CSS,
                                #   STYLESHEET, install_css(); pure until install_css() runs
settings/fonts.py               # CREATE (Task 4; Task 5 adds next_font): GENERIC_FAMILIES,
                                #   SYSTEM_SUFFIX, MISSING_SUFFIX, Entry, font_families,
                                #   picker_entries, matches, first_match, next_font (pure)
settings/fontpicker.py          # CREATE (Task 4): installed_families, family_of, system_family,
                                #   FontPicker (GTK)
settings/fields.py              # MODIFY: opens_below (T1); BoolEditor style (T2); _Editor.outer,
                                #   SliderEditor, FieldRow packs outer (T3); FontListEditor
                                #   replaces FontsEditor (T5); UNSET, THEME_FONT, FontEditor,
                                #   FieldRow resets on UNSET (T6)
settings/form.py                # MODIFY: SLIDER_MAX_SPAN, uses_slider (T3); parse_fonts and
                                #   format_fonts removed (T5); kind "font" (T6)
settings/view.py                # MODIFY (T2): the info note CSS moves to settings.style
README.md, docs/superpowers/specs/2026-10-14-panel-widget-model-design.md   # MODIFY (T7, T8)
tests/test_settings_style.py    # CREATE (T2)
tests/test_settings_fonts.py    # CREATE (T4; T5 adds one test)
tests/test_settings_fontpicker.py  # CREATE (T4)
tests/test_settings_fields.py, tests/test_settings_view.py, tests/test_settings_form.py,
tests/test_settings_example.py  # MODIFY
```

| After task | Suite (`scripts/py -m pytest -q`) | Delta | Tests added (-removed) |
|---|---|---|---|
| baseline `be65690` | 2626 passed | | |
| 1 dropdowns | 2628 passed | +2 | fields +1, view +1 |
| 2 style, toggles | 2632 passed | +4 | style +5, fields +1, view -2 (moved to style) |
| 3 sliders | 2639 passed | +7 | form +2, fields +5 |
| 4 font picker | 2651 passed | +12 | fonts +5, fontpicker +7 |
| 5 font list | 2654 passed | +3 | fonts +1, fields +4 -1, form -1 |
| 6 wiring | 2659 passed | +5 | form +1, fields +2, view +2 |
| 7 docs | 2659 passed | 0 | |
| 6 with GTK blocked | 1916 passed, 36 skipped | | baseline 1905 passed, 33 skipped |

---

### Task 1: Dropdowns open below their row with every entry (investigation and fix)

**Files:**
- Modify: `settings/fields.py` (new `opens_below` after `_pass_scroll`; `ChoiceEditor.__init__`; `LengthEditor.__init__`)
- Test: `tests/test_settings_fields.py`, `tests/test_settings_view.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `settings.fields.opens_below(combo: Gtk.ComboBox) -> None` (sets `wrap_width` 1). Every `ChoiceEditor` (enum, widget, panel type rows and the toolbar's panel type list, which is a `ChoiceEditor`) and every `LengthEditor.mode` calls it.

- [ ] **Step 1: The investigation (record, no code).** Read the decision 1 text above; it is the record of what was done. Run this headless check (it builds GTK's popup of a plain combo without showing anything):

```bash
scripts/py -c 'import gi; gi.require_version("Gtk", "3.0"); from gi.repository import Gtk; c = Gtk.ComboBoxText(); [c.append(x, x) for x in ("top", "bottom", "left", "right")]; m = c.get_popup_accessible().get_widget(); print(type(m).__name__, len(m.get_children()), c.get_wrap_width(), c.get_popup_fixed_width())'
```

Expected: `GtkTreeMenu 4 0 True`: the popup is a menu holding every entry (the size request is not short of entries), and our combos use the `wrap_width == 0` path that lays the menu over the combo with the active entry on it (gtkcombobox.c `gtk_combo_box_menu_popup`, gtk-3-24). The popup's place and size on KWin cannot be seen without a window: Gate item 1 checks it live.

- [ ] **Step 2: Write the failing tests**

```diff
diff --git a/tests/test_settings_fields.py b/tests/test_settings_fields.py
--- a/tests/test_settings_fields.py
+++ b/tests/test_settings_fields.py
@@ -448,3 +448,14 @@
     entry.set_text("Dock 3")
     assert entry.emit("focus-out-event", Gdk.Event.new(Gdk.EventType.FOCUS_CHANGE)) is False
     assert changes == [(("theme", "x"), "Dock 3")]
+
+
+def test_a_combo_opens_below_itself_with_every_entry():
+    """Phil: a dropdown opened one entry high with a scrollbar. wrap_width 1 takes GTK's
+    popup path that anchors the menu below the combo (settings.fields.opens_below)."""
+    shape, _, _ = row_for(FORM.theme.section("handle_style").field("shape"), "auto")
+    length, _, _ = row_for(FORM.edge_panel.field("length"), 300)
+    for combo in (shape.editor.widget, length.editor.mode):
+        assert combo.get_wrap_width() == 1
+        menu = combo.get_popup_accessible().get_widget()  # built by GTK, never shown here
+        assert len(menu.get_children()) == len(combo.get_model())  # one item per entry
diff --git a/tests/test_settings_view.py b/tests/test_settings_view.py
--- a/tests/test_settings_view.py
+++ b/tests/test_settings_view.py
@@ -1833,3 +1833,11 @@
     assert after.startswith(before) and "kscreen-doctor failed: timed out" in after
     view.tree.detect_button.clicked()  # again: not added twice
     assert view.banner_label.get_text() == after
+
+
+def test_every_combo_of_the_window_opens_below_itself(make_real):
+    """The toolbar's panel type list, every enum and widget row and the length mode."""
+    view, _ = make_real()
+    combos = [w for w in walk(view) if isinstance(w, Gtk.ComboBox)]
+    assert len(combos) >= 10 and view.toolbar.kind.widget in combos
+    assert [c for c in combos if c.get_wrap_width() != 1] == []
```

- [ ] **Step 3: Run them to verify they fail**

Run: `scripts/py -m pytest -q tests/test_settings_fields.py::test_a_combo_opens_below_itself_with_every_entry tests/test_settings_view.py::test_every_combo_of_the_window_opens_below_itself`
Expected: `2 failed`: the fields test `assert 0 == 1` (`get_wrap_width()` is 0), the view test `assert [<Gtk.ComboBox...>, ...] == []` (every combo of the window).

- [ ] **Step 4: Implement**

```diff
diff --git a/settings/fields.py b/settings/fields.py
--- a/settings/fields.py
+++ b/settings/fields.py
@@ -52,6 +52,20 @@
 def _pass_scroll(widget: Gtk.Widget, _event: Gdk.Event) -> bool:
     GObject.signal_stop_emission_by_name(widget, "scroll-event")  # skip the widget's handler
     return False  # not handled: the event goes on to the page's ScrolledWindow
+
+
+def opens_below(combo: Gtk.ComboBox) -> None:
+    """The combo's list opens below it at the size of its entries (Phil: it opened one entry
+    high with a scrollbar and grew on a mouse-over or a wheel turn). GTK 3.24 pops a combo's
+    menu up in one of two ways (gtkcombobox.c, gtk_combo_box_menu_popup). With wrap_width 0
+    it lays the menu over the combo with the ACTIVE entry on it: a negative rect_anchor_dy,
+    anchor hints slide and resize (no flip), and a scroll offset set once the menu is up. On
+    Wayland the compositor then constrains that popup, and GtkMenu shows scroll arrows until a
+    motion or wheel event makes it measure again. With wrap_width > 0 GTK anchors the menu
+    below the combo (above when there is no room: flip, slide and resize) with no offset. One
+    column keeps the list a plain list. The size request is not the cause: popup-fixed-width
+    and a menu item's min-height act on widths and row heights, not on this placement."""
+    combo.set_wrap_width(1)
 
 
 class _Editor:
@@ -160,6 +174,7 @@
         if disabled:
             (cell,) = self.widget.get_cells()
             self.widget.set_cell_data_func(cell, self._grey_out)
+        opens_below(self.widget)
         wheel_scrolls_the_page(self.widget)
         self.widget.connect("changed", self._on_changed, emit)
 
@@ -243,6 +258,7 @@
         strict_spin(self.number)
         self.widget.pack_start(self.mode, False, False, 0)
         self.widget.pack_start(self.number, False, False, 0)
+        opens_below(self.mode)
         wheel_scrolls_the_page(self.mode)
         wheel_scrolls_the_page(self.number)
         self.fallback_px = FALLBACK_PX
```

- [ ] **Step 5: Run them to verify they pass, then VERIFY**

Run the two tests again: 2 passed. Then VERIFY: `2628 passed`. `test_a_disabled_choice_is_greyed_out_and_never_sent` still passes (the cell data function works on the grid menu too).

- [ ] **Step 6: Commit**

```bash
git add settings/fields.py tests/test_settings_fields.py tests/test_settings_view.py
git commit -m "fix(settings): dropdowns open below their row with every entry shown" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

**Reviewer mutation list** (each must make the named tests fail; every one was run on the prototype and killed):
- remove `opens_below(self.widget)` from `ChoiceEditor` → both new tests fail;
- remove `opens_below(self.mode)` from `LengthEditor` → both fail;
- `combo.set_wrap_width(0)` in `opens_below` → both fail.

---

### Task 2: One class-scoped stylesheet; thin toggles with a round knob

**Files:**
- Create: `settings/style.py`, `tests/test_settings_style.py`
- Modify: `settings/view.py` (the info note CSS and `install_info_note_css` move out; `install_css()` replaces the call; the unused `Gdk` import goes), `settings/fields.py` (`BoolEditor`)
- Test: `tests/test_settings_style.py`, `tests/test_settings_fields.py`, `tests/test_settings_view.py` (the two info note CSS tests move to `test_settings_style.py`)

**Interfaces:**
- Consumes: nothing new.
- Produces: `settings.style`: `INFO_NOTE_CLASS = "info-note"`, `INFO_NOTE_CSS: str`, `SWITCH_CLASS = "edge-switch"`, `KNOB_PX = 16`, `BORDER_PX = 1`, `TRACK_PADDING_PX = 2`, `SWITCH_CSS: str`, `STYLESHEET: str`, `install_css() -> Gtk.CssProvider` (once; same provider after). `settings.view` re-exports `INFO_NOTE_CLASS` by importing it (tests import it from there). `BoolEditor.widget` has the class `edge-switch`, `halign` START, `valign` CENTER.

- [ ] **Step 1: Write the failing tests** (the new style tests; the toggle test; the two moved tests leave the view tests)

```diff
diff --git a/tests/test_settings_style.py b/tests/test_settings_style.py
new file mode 100644
--- /dev/null
+++ b/tests/test_settings_style.py
@@ -0,0 +1,87 @@
+"""settings.style: the window's one stylesheet. The CSS text is tested without GTK; the tests
+that measure a widget need a display (no window is shown)."""
+
+import re
+
+import pytest
+
+from settings import style
+
+
+@pytest.fixture
+def gtk():
+    gi = pytest.importorskip("gi")
+    gi.require_version("Gtk", "3.0")
+    gi.require_version("Gdk", "3.0")
+    from gi.repository import Gtk
+
+    if not Gtk.init_check()[0]:
+        pytest.skip("no display")
+    return Gtk
+
+
+def selectors(css: str) -> list[str]:
+    """Every selector of `css` (the text before each `{`, split at commas)."""
+    heads = re.findall(r"([^{}]+)\{", css)
+    return [s.strip() for head in heads for s in head.split(",")]
+
+
+def rule(css: str, selector: str) -> dict[str, str]:
+    """The declarations of the rule whose selector is exactly `selector`."""
+    for head, body in re.findall(r"([^{}]+)\{([^}]*)\}", css):
+        if head.strip() == selector:
+            pairs = (d.split(":", 1) for d in body.split(";") if d.strip())
+            return {k.strip(): v.strip() for k, v in pairs}
+    raise KeyError(selector)
+
+
+def test_every_rule_is_scoped_by_one_of_our_classes():
+    """Never a bare `switch` or `label`: the stylesheet is on the whole screen."""
+    found = selectors(style.STYLESHEET)
+    assert len(found) >= 6
+    for selector in found:
+        first = selector.split()[0]
+        assert f".{style.INFO_NOTE_CLASS}" in first or f".{style.SWITCH_CLASS}" in first, selector
+
+
+def test_the_info_note_css_has_the_class_colours_and_a_backdrop_rule():
+    css = style.INFO_NOTE_CSS
+    assert f".{style.INFO_NOTE_CLASS}" in css
+    assert "#2b5c8a" in css  # the background
+    assert "#ffffff" in css  # the text
+    assert ":backdrop" in css  # an unfocused window keeps both
+
+
+def test_the_switch_content_is_twice_as_wide_as_high_and_the_knob_is_round():
+    """GTK gives the knob half the content width and the whole content height: a circle when
+    the content is 2:1 (settings.style)."""
+    track = rule(style.SWITCH_CSS, f"switch.{style.SWITCH_CLASS}")
+    knob = rule(style.SWITCH_CSS, f"switch.{style.SWITCH_CLASS} slider")
+    assert track["min-width"] == f"{2 * style.KNOB_PX}px"
+    assert track["min-height"] == f"{style.KNOB_PX}px"
+    assert track["margin"] == "0" and track["border-width"] == f"{style.BORDER_PX}px"
+    inner = style.KNOB_PX - 2 * style.BORDER_PX  # the knob's border makes it KNOB_PX across
+    assert knob["min-width"] == knob["min-height"] == f"{inner}px"
+    assert knob["border-width"] == f"{style.BORDER_PX}px"
+    assert knob["margin"] == knob["padding"] == "0"
+    assert knob["border-radius"] == "50%"
+
+
+def test_the_stylesheet_is_valid_and_installed_once(gtk):
+    provider = gtk.CssProvider()
+    provider.load_from_data(style.STYLESHEET.encode())  # raises on a parse error
+    first = style.install_css()
+    assert style.install_css() is first  # a second call reuses it
+
+
+def test_a_styled_switch_is_thinner_with_a_2_to_1_content_box(gtk):
+    style.install_css()
+    plain, styled = gtk.Switch(), gtk.Switch()
+    styled.get_style_context().add_class(style.SWITCH_CLASS)
+    for switch in (plain, styled):
+        switch.show()  # a widget flag only: no window exists
+    edge = 2 * (style.TRACK_PADDING_PX + style.BORDER_PX)  # padding and border, both sides
+    height = styled.get_preferred_height().minimum_height
+    assert styled.get_preferred_width().minimum_width == 2 * style.KNOB_PX + edge  # 38
+    assert height == style.KNOB_PX + edge  # 22: the content is 2:1
+    assert height < plain.get_preferred_height().minimum_height  # Breeze 24, Adwaita 26
diff --git a/tests/test_settings_fields.py b/tests/test_settings_fields.py
--- a/tests/test_settings_fields.py
+++ b/tests/test_settings_fields.py
@@ -459,3 +459,23 @@
         assert combo.get_wrap_width() == 1
         menu = combo.get_popup_accessible().get_widget()  # built by GTK, never shown here
         assert len(menu.get_children()) == len(combo.get_model())  # one item per entry
+
+
+def test_a_toggle_is_centred_in_its_row_with_a_round_knob():
+    """Phil: thinner, with a round knob. The row is about 30 px high (its Reset button); the
+    switch keeps its own height, so its content stays 2:1 and the knob a circle."""
+    from settings.style import BORDER_PX, KNOB_PX, SWITCH_CLASS, TRACK_PADDING_PX
+
+    row, _, _ = row_for(FORM.theme.section("border").field("enabled"), True)
+    row.show_all()  # widget flags only: no window exists
+    alloc = Gdk.Rectangle()
+    alloc.width = row.get_preferred_width().natural_width
+    alloc.height = row.get_preferred_height().natural_height
+    row.size_allocate(alloc)
+    switch = row.editor.widget
+    assert switch.get_style_context().has_class(SWITCH_CLASS)
+    assert switch.get_allocated_height() == switch.get_preferred_height().minimum_height
+    assert switch.get_allocated_height() < alloc.height  # centred, not stretched
+    edge = 2 * (TRACK_PADDING_PX + BORDER_PX)
+    assert switch.get_allocated_width() - edge == 2 * (switch.get_allocated_height() - edge)
+    assert switch.get_allocated_height() - edge == KNOB_PX
diff --git a/tests/test_settings_view.py b/tests/test_settings_view.py
--- a/tests/test_settings_view.py
+++ b/tests/test_settings_view.py
@@ -877,24 +877,7 @@
 
 
 # ---- the info note keeps its blue background and light text, focused or not ----------------
-def test_the_info_note_css_has_the_class_colours_and_a_backdrop_rule():
-    from settings.view import INFO_NOTE_CLASS, INFO_NOTE_CSS
-
-    assert f".{INFO_NOTE_CLASS}" in INFO_NOTE_CSS
-    assert "#2b5c8a" in INFO_NOTE_CSS  # the background
-    assert "#ffffff" in INFO_NOTE_CSS  # the text
-    assert ":backdrop" in INFO_NOTE_CSS  # an unfocused window keeps both
-
-
-def test_the_info_note_css_is_valid_and_installed_once():
-    from settings import view as view_module
-
-    provider = Gtk.CssProvider()
-    provider.load_from_data(view_module.INFO_NOTE_CSS.encode())  # raises on a parse error
-    first = view_module.install_info_note_css()
-    assert view_module.install_info_note_css() is first  # a second call reuses it
-
-
+# (its CSS is in settings.style: tests/test_settings_style.py)
 def test_an_info_banner_gets_the_class_and_others_do_not(make):
     from settings.view import INFO_NOTE_CLASS
 
```

- [ ] **Step 2: Run them to verify they fail**

Run: `scripts/py -m pytest -q tests/test_settings_style.py`
Expected: `ERROR tests/test_settings_style.py`, `Interrupted: 1 error during collection` (`ImportError: cannot import name 'style' from 'settings'`).
Run: `scripts/py -m pytest -q tests/test_settings_fields.py::test_a_toggle_is_centred_in_its_row_with_a_round_knob`
Expected: 1 failed (`ModuleNotFoundError: No module named 'settings.style'`).

- [ ] **Step 3: Implement**

```diff
diff --git a/settings/style.py b/settings/style.py
new file mode 100644
--- /dev/null
+++ b/settings/style.py
@@ -0,0 +1,86 @@
+"""The settings window's own stylesheet: one CssProvider at USER priority on the screen,
+installed once (install_css). Every rule is scoped by a style class this window puts on its
+own widgets, never a bare element selector, so nothing else on the screen changes. A higher
+provider priority wins over the theme's rules whatever their specificity (GTK cascades by
+priority first), so one rule per node holds in every state (:checked, :backdrop, :disabled,
+:hover) of KDE's Breeze and of Adwaita alike.
+
+The CSS text is plain data: it is tested without GTK; install_css imports GTK when it runs."""
+
+from __future__ import annotations
+
+from typing import Any
+
+# The once-only info note must not depend on the theme: GTK's own infobar colours turn the
+# text orange in a focused window and white in an unfocused one. A blue background with light
+# text, with the :backdrop (unfocused) state spelled out, reads the same either way.
+INFO_NOTE_CLASS = "info-note"
+INFO_NOTE_CSS = """
+infobar.info-note,
+infobar.info-note > revealer > box,
+infobar.info-note:backdrop,
+infobar.info-note:backdrop > revealer > box {
+    background-color: #2b5c8a;
+    background-image: none;
+}
+infobar.info-note label,
+infobar.info-note:backdrop label {
+    color: #ffffff;
+}
+"""
+
+# Toggles (Phil: thinner, with a round knob, not an oval). GTK 3.24 gives the knob (the
+# `slider` node) half the switch's content width and its whole content height, so the knob is
+# a circle exactly when the content box is twice as wide as it is high. GTK never makes the
+# content smaller than 32 x 16 px (measured with Breeze and Adwaita, whatever the font size),
+# so the knob is 16 px across, its 1 px border included. Every size is set here (the theme's borders
+# would add to them); the theme keeps its colours. The switch is centred in its row (a row is
+# about 30 px high: a stretched switch made the knob a tall oval). Outside: 38 x 22 px (Breeze's
+# own switch is 52 x 24).
+SWITCH_CLASS = "edge-switch"
+KNOB_PX = 16  # the knob's diameter, border included
+BORDER_PX = 1
+TRACK_PADDING_PX = 2
+SWITCH_CSS = f"""
+switch.{SWITCH_CLASS} {{
+    min-width: {2 * KNOB_PX}px;
+    min-height: {KNOB_PX}px;
+    padding: {TRACK_PADDING_PX}px;
+    border-width: {BORDER_PX}px;
+    margin: 0;
+    border-radius: {KNOB_PX}px;
+}}
+switch.{SWITCH_CLASS} slider {{
+    min-width: {KNOB_PX - 2 * BORDER_PX}px;
+    min-height: {KNOB_PX - 2 * BORDER_PX}px;
+    border-width: {BORDER_PX}px;
+    margin: 0;
+    padding: 0;
+    border-radius: 50%;
+}}
+"""
+
+STYLESHEET = INFO_NOTE_CSS + SWITCH_CSS
+_provider: Any = None  # the installed Gtk.CssProvider (None: not installed yet)
+
+
+def install_css():
+    """Add STYLESHEET to the default screen at USER priority, once; later calls return the
+    same provider. With no screen (no display) the provider is made but not added."""
+    global _provider
+    if _provider is None:
+        import gi
+
+        gi.require_version("Gtk", "3.0")
+        gi.require_version("Gdk", "3.0")
+        from gi.repository import Gdk, Gtk
+
+        provider = Gtk.CssProvider()
+        provider.load_from_data(STYLESHEET.encode())
+        screen = Gdk.Screen.get_default()
+        if screen is not None:
+            Gtk.StyleContext.add_provider_for_screen(
+                screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_USER
+            )
+        _provider = provider
+    return _provider
diff --git a/settings/view.py b/settings/view.py
--- a/settings/view.py
+++ b/settings/view.py
@@ -23,8 +23,7 @@
 import gi
 
 gi.require_version("Gtk", "3.0")
-gi.require_version("Gdk", "3.0")
-from gi.repository import Gdk, GLib, Gtk
+from gi.repository import GLib, Gtk
 
 from settings.dialogs import GtkDialogs
 from settings.document import UserDocument
@@ -53,6 +52,7 @@
 from settings.queue import RESET, EditQueue, QueuedEdit, describe, path_text
 from settings.screens import DetectError, desktop_label, detect_outputs
 from settings.session import ChangedOutside, SettingsSession, check_text
+from settings.style import INFO_NOTE_CLASS, install_css
 from settings.toolbar import ScreenToolbar
 from settings.tree import SettingsTree
 from settings.values import field_value, layout_preview, lookup, panel_ops
@@ -62,41 +62,6 @@
 from shell.registry import requests_for
 
 Edit = Callable[[UserDocument], Any]
-
-# The once-only info note must not depend on the theme: GTK's own infobar colours turn the
-# text orange in a focused window and white in an unfocused one. A blue background with light
-# text, with the :backdrop (unfocused) state spelled out, reads the same either way.
-INFO_NOTE_CLASS = "info-note"
-INFO_NOTE_CSS = """
-infobar.info-note,
-infobar.info-note > revealer > box,
-infobar.info-note:backdrop,
-infobar.info-note:backdrop > revealer > box {
-    background-color: #2b5c8a;
-    background-image: none;
-}
-infobar.info-note label,
-infobar.info-note:backdrop label {
-    color: #ffffff;
-}
-"""
-_info_note_provider: Gtk.CssProvider | None = None
-
-
-def install_info_note_css() -> Gtk.CssProvider:
-    """Add the info note's CSS to the screen (USER priority), once; later calls reuse it."""
-    global _info_note_provider
-    if _info_note_provider is None:
-        provider = Gtk.CssProvider()
-        provider.load_from_data(INFO_NOTE_CSS.encode())
-        screen = Gdk.Screen.get_default()
-        if screen is not None:
-            Gtk.StyleContext.add_provider_for_screen(
-                screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_USER
-            )
-        _info_note_provider = provider
-    return _info_note_provider
-
 
 # shown in a panel's tree row and page heading (panel_title), or deciding its rows (widget:
 # the kind and the Widget tab; panel: the kind's rows; corner: the edge choices): a change
@@ -157,7 +122,7 @@
             self.add_panel,
             lambda action: self.on_panel_action(self.stack.get_visible_child_name(), action),
         )
-        install_info_note_css()
+        install_css()  # the info note's colours (settings.style)
         self.banner = Gtk.InfoBar()
         self.banner_label = Gtk.Label(xalign=0, wrap=True, selectable=True)
         self.banner.get_content_area().add(self.banner_label)
diff --git a/settings/fields.py b/settings/fields.py
--- a/settings/fields.py
+++ b/settings/fields.py
@@ -24,6 +24,7 @@
     rgba_to_hex,
     split_length,
 )
+from settings.style import SWITCH_CLASS, install_css  # noqa: E402
 from settings.values import FieldValue  # noqa: E402
 from shell.theme import hex_to_rgba  # noqa: E402
 
@@ -146,8 +147,13 @@
 
 
 class BoolEditor(_Editor):
+    """A toggle: thin, with a round knob (settings.style), centred in its row (a switch
+    stretched to the row's height made the knob a tall oval)."""
+
     def __init__(self, emit: Emit):
-        self.widget = Gtk.Switch(halign=Gtk.Align.START)
+        install_css()
+        self.widget = Gtk.Switch(halign=Gtk.Align.START, valign=Gtk.Align.CENTER)
+        self.widget.get_style_context().add_class(SWITCH_CLASS)
         self.widget.connect("notify::active", lambda s, _p: emit(s.get_active()))
 
     def set(self, value: bool) -> None:
```

- [ ] **Step 4: Run them to verify they pass, then VERIFY**

Run both commands of Step 2: 5 passed, then 1 passed. VERIFY: `2632 passed`. Also with Adwaita, to see that the numbers do not come from Breeze: `GTK_THEME=Adwaita scripts/py -m pytest -q tests/test_settings_style.py tests/test_settings_fields.py` passes.

- [ ] **Step 5: Commit**

```bash
git add settings/style.py settings/view.py settings/fields.py tests/test_settings_style.py tests/test_settings_fields.py tests/test_settings_view.py
git commit -m "feat(settings): one class-scoped stylesheet; thin toggles with a round knob" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

**Reviewer mutation list:**
- drop `add_class(SWITCH_CLASS)` in `BoolEditor` → `test_a_toggle_is_centred_in_its_row_with_a_round_knob` fails;
- `Gtk.Switch(halign=Gtk.Align.START)` (no `valign`) → the toggle test fails (the switch is stretched to the row);
- knob `border-radius: 3px` → `test_the_switch_content_is_twice_as_wide_as_high_and_the_knob_is_round` fails;
- track `min-height: {KNOB_PX + 4}px` → the CSS test, `test_a_styled_switch_is_thinner_with_a_2_to_1_content_box` and the toggle test fail;
- `switch slider {{` (unscoped) → `test_every_rule_is_scoped_by_one_of_our_classes`, the CSS test and `test_a_styled_switch_is_thinner_with_a_2_to_1_content_box` fail;
- drop `install_css()` in `BoolEditor` → the toggle test fails (no rule reaches the switch).

---

### Task 3: Bounded numbers get a slider beside their spin button

**Files:**
- Modify: `settings/form.py` (`SLIDER_MAX_SPAN`, `uses_slider`), `settings/fields.py` (`SLIDER_WIDTH`, `_Editor.outer`, `SliderEditor`, `make_editor`, `FieldRow` packs `editor.outer`)
- Test: `tests/test_settings_form.py`, `tests/test_settings_fields.py`

**Interfaces:**
- Consumes: `settings.fields.strict_spin`, `commit_spin`, `_spin_dirty`, `wheel_scrolls_the_page` (existing); the view's `_on_queue(path, value, base)` through `FieldRow` (kind `"int"` is in `DEBOUNCED`).
- Produces: `settings.form.SLIDER_MAX_SPAN = 500`; `settings.form.uses_slider(spec: FieldSpec) -> bool`; `settings.fields.SLIDER_WIDTH = 160`; `_Editor.outer -> Gtk.Widget` (property: the widget the row packs; `self.widget` by default); `SliderEditor(spec: FieldSpec, emit: Emit)` with `.adjustment: Gtk.Adjustment`, `.scale: Gtk.Scale`, `.widget: Gtk.SpinButton`, `.outer` (a `Gtk.Box` of both), `set(value: int | None)`, `commit()`, `dirty() -> bool`; `make_editor` returns it for `kind == "int"` when `uses_slider(spec)`.

- [ ] **Step 1: Write the failing tests**

```diff
diff --git a/tests/test_settings_form.py b/tests/test_settings_form.py
--- a/tests/test_settings_form.py
+++ b/tests/test_settings_form.py
@@ -21,6 +21,7 @@
     rgba_to_hex,
     section_for,
     split_length,
+    uses_slider,
 )
 from shell.config.models import (
     COLOR_FIELDS,
@@ -453,3 +454,45 @@
         "Float panel (coming soon)",
     ]
     assert len({c.label for c in choices}) == len(choices)
+
+
+def test_a_bounded_whole_number_with_a_short_range_is_a_slider():
+    form = config_form(WIDGETS)
+    sliders = {
+        (name, f.key)
+        for name, section in (
+            ("theme", form.theme),
+            ("border", form.theme.section("border")),
+            ("shadow", form.theme.section("shadow")),
+            ("handle_style", form.theme.section("handle_style")),
+            ("layout", form.layout),
+            ("edge", form.edge_panel),
+            ("edge.handle", form.edge_panel.section("handle")),
+            ("corner", form.corner_panel),
+        )
+        for f in section.fields
+        if uses_slider(f)
+    }
+    assert sliders == {
+        ("theme", "thickness"),
+        ("theme", "radius"),
+        ("theme", "peek"),
+        ("theme", "hover_zone"),
+        ("border", "width"),
+        ("shadow", "elevation"),
+        ("handle_style", "size"),
+        ("handle_style", "weight"),
+        ("layout", "gap"),
+        ("edge.handle", "size"),
+        ("edge.handle", "weight"),
+    }  # duration 0-5000, offsets, depth, order, lengths and corner sizes keep a spin button
+
+
+def test_the_slider_rule_needs_both_bounds_and_a_short_range():
+    from settings.form import SLIDER_MAX_SPAN, FieldSpec
+
+    assert uses_slider(FieldSpec("a", "A", "int", minimum=0, maximum=SLIDER_MAX_SPAN))
+    assert not uses_slider(FieldSpec("a", "A", "int", minimum=0, maximum=SLIDER_MAX_SPAN + 1))
+    assert not uses_slider(FieldSpec("a", "A", "int", minimum=0))
+    assert not uses_slider(FieldSpec("a", "A", "int", maximum=9))
+    assert not uses_slider(FieldSpec("a", "A", "length", minimum=60, maximum=100))
diff --git a/tests/test_settings_fields.py b/tests/test_settings_fields.py
--- a/tests/test_settings_fields.py
+++ b/tests/test_settings_fields.py
@@ -141,7 +141,8 @@
     length, changes2, _ = row_for(FORM.edge_panel.field("length"), 300)
     for widget in (
         mode.editor.widget,
-        thickness.editor.widget,
+        thickness.editor.widget,  # a slider's spin button
+        thickness.editor.scale,  # and the slider itself
         length.editor.mode,
         length.editor.number,
     ):
@@ -479,3 +480,73 @@
     edge = 2 * (TRACK_PADDING_PX + BORDER_PX)
     assert switch.get_allocated_width() - edge == 2 * (switch.get_allocated_height() - edge)
     assert switch.get_allocated_height() - edge == KNOB_PX
+
+
+def test_a_bounded_number_is_a_slider_beside_a_spin_with_one_value():
+    queued = []
+    row, changes, _ = row_for(FORM.theme.field("thickness"), 10, queued=queued)
+    editor = row.editor
+    assert isinstance(editor, fields.SliderEditor)
+    assert editor.outer.get_children() == [editor.scale, editor.widget]
+    assert editor.outer.is_ancestor(row)  # the row packs the box of both
+    adjustment = editor.scale.get_adjustment()
+    assert (adjustment.get_lower(), adjustment.get_upper()) == (2.0, 64.0)
+    assert editor.scale.get_value() == editor.widget.get_value() == 10
+    assert not editor.scale.get_draw_value()  # the spin button shows the number
+    assert editor.scale.get_accessible().get_name() == "Thickness"
+    editor.scale.set_value(20)  # the slider moves the spin button
+    assert editor.widget.get_value() == 20
+    editor.widget.set_value(30)  # and the spin button the slider
+    assert editor.scale.get_value() == 30
+    assert queued == [(("theme", "x"), 20, 10), (("theme", "x"), 30, 10)] and changes == []
+
+
+def test_a_slider_drag_is_one_queued_edit_and_a_drag_back_none():
+    """Every whole number on the way is pushed; the view's queue keeps the last one per row,
+    and dragging back to the shown value un-queues it (an inherited value stays inherited)."""
+    from settings.queue import EditQueue
+
+    queue = EditQueue()
+    row = fields.FieldRow(FORM.theme.field("thickness"), ("theme", "t"), id, id, queue.push)
+    row.show_value(FieldValue(10, False, "default"))
+    for value in range(11, 31):
+        row.editor.scale.set_value(value)
+    assert [(e.path, e.value) for e in queue] == [(("theme", "t"), 30)]
+    for value in range(29, 9, -1):
+        row.editor.scale.set_value(value)
+    assert len(queue) == 0
+
+
+def test_a_slider_sends_whole_numbers_and_takes_its_keys():
+    row, changes, _ = row_for(FORM.theme.field("thickness"), 10)
+    scale = row.editor.scale
+    scale.emit("change-value", Gtk.ScrollType.JUMP, 12.6)  # a drag between two values
+    assert scale.get_value() == 13 and changes[-1] == (("theme", "x"), 13)
+    assert type(changes[-1][1]) is int
+    scale.emit("move-slider", Gtk.ScrollType.STEP_FORWARD)  # Right arrow
+    assert changes[-1][1] == 14
+    scale.emit("move-slider", Gtk.ScrollType.END)  # End
+    assert changes[-1][1] == 64
+    scale.emit("move-slider", Gtk.ScrollType.START)  # Home
+    assert changes[-1][1] == 2
+
+
+def test_a_wide_or_open_range_keeps_its_spin_button():
+    for spec in (
+        FORM.edge_panel.field("offset"),
+        FORM.edge_panel.field("depth"),
+        FORM.theme.field("duration_ms"),
+        FORM.corner_panel.field("width"),
+    ):
+        row, _, _ = row_for(spec, 100)
+        assert isinstance(row.editor, fields.IntEditor), spec.key
+        assert row.editor.outer is row.editor.widget
+
+
+def test_an_unset_optional_slider_shows_its_minimum_and_sends_nothing():
+    row, changes, _ = row_for(
+        FieldSpec("font_size", "Font size", "int", minimum=6, maximum=96), None
+    )
+    assert row.editor.scale.get_value() == 6 and not row.unsent()
+    row.flush()
+    assert changes == []
```

- [ ] **Step 2: Run them to verify they fail**

Run: `scripts/py -m pytest -q tests/test_settings_form.py`
Expected: `ERROR tests/test_settings_form.py`, `Interrupted: 1 error during collection` (`ImportError: cannot import name 'uses_slider' from 'settings.form'`).
Run: `scripts/py -m pytest -q tests/test_settings_fields.py`
Expected: `6 failed, 36 passed`: the five new tests and `test_the_mouse_wheel_never_edits_a_row` (`AttributeError: 'IntEditor' object has no attribute 'scale'`, `module 'settings.fields' has no attribute 'SliderEditor'`, `'IntEditor' object has no attribute 'outer'`).

- [ ] **Step 3: Implement**

```diff
diff --git a/settings/form.py b/settings/form.py
--- a/settings/form.py
+++ b/settings/form.py
@@ -88,6 +88,12 @@
 }
 KIND_LABELS = {"edge": "Edge", "corner": "Corner", "float": "Float (coming soon)"}
 LEAD_ROWS = ("name", "widget", "panel")  # every panel section starts with these
+# A whole number with both bounds gets a slider (Phil: "If a numeric has a minimum and maximum
+# use sliders instead of number spinners") when its range is at most this wide: on a 160 px
+# slider that is at most 3 values per pixel. Wider ranges (an offset of +-20000, a corner
+# width of 60-4000 px, a duration of 0-5000 ms, a depth of 16-2000 px, an order of 0-1000)
+# keep the spin button, whose arrows step by one.
+SLIDER_MAX_SPAN = 500
 CORNER_ROWS = (*LEAD_ROWS, "corner", "edge", "width", "height", "state")  # a corner panel
 
 
@@ -104,6 +110,14 @@
     disabled: tuple[str, ...] = ()  # choices shown but not selectable ("coming soon")
     required: bool = False  # the entry needs it: no reset button
     max_length: int | None = None  # a text row: the most characters the entry takes
+
+
+def uses_slider(spec: FieldSpec) -> bool:
+    """True when the row of `spec` is a slider: an int with both bounds and a range of at most
+    SLIDER_MAX_SPAN."""
+    if spec.kind != "int" or spec.minimum is None or spec.maximum is None:
+        return False
+    return spec.maximum - spec.minimum <= SLIDER_MAX_SPAN
 
 
 @dataclass(frozen=True)
diff --git a/settings/fields.py b/settings/fields.py
--- a/settings/fields.py
+++ b/settings/fields.py
@@ -23,6 +23,7 @@
     parse_fonts,
     rgba_to_hex,
     split_length,
+    uses_slider,
 )
 from settings.style import SWITCH_CLASS, install_css  # noqa: E402
 from settings.values import FieldValue  # noqa: E402
@@ -34,6 +35,7 @@
 FALLBACK_PX = 300  # px when switching a length to px with no px value known (never the 60 min)
 FALLBACK_PERCENT = 50.0
 SOURCE_CHARS = 28  # the width of a row's note (where its value comes from); longer is cut
+SLIDER_WIDTH = 160  # px; with its spin button a slider row stays inside a tab's 640 px
 
 Emit = Callable[[Any], None]
 _UNSHOWN = object()
@@ -74,6 +76,11 @@
 
     widget: Gtk.Widget
 
+    @property
+    def outer(self) -> Gtk.Widget:
+        """What the row shows: the value widget itself, or a box around it (a slider)."""
+        return self.widget
+
     def set(self, value: Any) -> None:
         raise NotImplementedError
 
@@ -144,6 +151,52 @@
     def set(self, value: int | None) -> None:
         # None (e.g. min_length not set) shows the lowest value; the source says "not set"
         self.widget.set_value(self.widget.get_range()[0] if value is None else value)
+
+
+class SliderEditor(_Editor):
+    """A bounded whole number (settings.form.uses_slider): a slider and, beside it, a spin
+    button for exact typing; both move one Gtk.Adjustment, so they always show the same
+    value and every change is sent once. `widget` is the spin button (typed text, flush and
+    the focus after a rebuild work as for a plain number row); `scale` the slider. Dragging
+    sends each whole number on the way: the view's queue keeps the last one per row and
+    applies it after the pause (settings.queue). The keys of a focused slider work (arrows,
+    Page Up/Down, Home, End); the mouse wheel never edits it (wheel_scrolls_the_page). An
+    unset optional value (a widget's font size) shows the minimum, as a spin row does."""
+
+    def __init__(self, spec: FieldSpec, emit: Emit):
+        low, high = spec.minimum, spec.maximum
+        page = max(1, (high - low) // 10)
+        self.adjustment = Gtk.Adjustment(
+            value=low, lower=low, upper=high, step_increment=1, page_increment=page
+        )
+        self.scale = Gtk.Scale(
+            orientation=Gtk.Orientation.HORIZONTAL, adjustment=self.adjustment, draw_value=False
+        )
+        self.scale.set_round_digits(0)  # a drag moves in whole numbers
+        self.scale.set_size_request(SLIDER_WIDTH, -1)
+        self.scale.get_accessible().set_name(spec.label)
+        self.widget = Gtk.SpinButton(adjustment=self.adjustment, climb_rate=1, digits=0)
+        self.widget.set_numeric(True)
+        strict_spin(self.widget)
+        self._box = Gtk.Box(spacing=6)
+        self._box.pack_start(self.scale, False, False, 0)
+        self._box.pack_start(self.widget, False, False, 0)
+        for widget in (self.scale, self.widget):
+            wheel_scrolls_the_page(widget)
+        self.adjustment.connect("value-changed", lambda a: emit(int(round(a.get_value()))))
+
+    @property
+    def outer(self) -> Gtk.Widget:
+        return self._box
+
+    def commit(self) -> None:
+        commit_spin(self.widget)
+
+    def dirty(self) -> bool:
+        return _spin_dirty(self.widget)
+
+    def set(self, value: int | None) -> None:
+        self.adjustment.set_value(self.adjustment.get_lower() if value is None else value)
 
 
 class BoolEditor(_Editor):
@@ -332,7 +385,7 @@
     if spec.kind == "color":
         return ColorEditor(emit)
     if spec.kind == "int":
-        return IntEditor(spec, emit)
+        return SliderEditor(spec, emit) if uses_slider(spec) else IntEditor(spec, emit)
     if spec.kind == "bool":
         return BoolEditor(emit)
     if spec.kind in ("enum", "widget"):
@@ -391,7 +444,7 @@
         self.reset.set_tooltip_text("Remove this key from your config (use the inherited value)")
         self.reset.connect("clicked", lambda *_a: on_reset(path))
         line.pack_start(name, False, False, 0)
-        line.pack_start(self.editor.widget, False, False, 0)
+        line.pack_start(self.editor.outer, False, False, 0)
         line.pack_start(self.source, True, True, 0)
         line.pack_end(self.reset, False, False, 0)
         self.error = Gtk.Label(xalign=0, wrap=True, selectable=True)
```

- [ ] **Step 4: Run them to verify they pass, then VERIFY**

Run `scripts/py -m pytest -q tests/test_settings_form.py tests/test_settings_fields.py`: all pass. VERIFY: `2639 passed`. The width test `test_no_tab_is_wider_than_the_space_beside_the_tree_at_860` still passes (prototype: at most 524 px on every tab after this task).

- [ ] **Step 5: Commit**

```bash
git add settings/form.py settings/fields.py tests/test_settings_form.py tests/test_settings_fields.py
git commit -m "feat(settings): bounded numbers get a slider beside their spin button" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

**Reviewer mutation list:**
- `SLIDER_MAX_SPAN = 1000` → `test_a_bounded_whole_number_with_a_short_range_is_a_slider` fails (order 0-1000 becomes a slider);
- `<` instead of `<=` in `uses_slider` → `test_the_slider_rule_needs_both_bounds_and_a_short_range` fails;
- no wheel guard on the scale → `test_the_mouse_wheel_never_edits_a_row` fails;
- `emit(a.get_value())` (no int rounding) → `test_a_slider_sends_whole_numbers_and_takes_its_keys` and `test_a_slider_drag_is_one_queued_edit_and_a_drag_back_none` fail (floats are not the shown int);
- drop `set_round_digits(0)` → the same test fails (the drag lands on 12.6);
- `draw_value=True`, or no accessible name → `test_a_bounded_number_is_a_slider_beside_a_spin_with_one_value` fails;
- `FieldRow` packs `editor.widget` again → `test_a_bounded_number_is_a_slider_beside_a_spin_with_one_value` fails (the box is in no row; GTK refuses a second parent for the spin) and so does the view's `test_a_widget_with_properties_gets_the_widget_tab`;
- `make_editor` always `IntEditor` → the four slider tests of this task that build a row and `test_the_mouse_wheel_never_edits_a_row` fail.

---

### Task 4: A searchable font picker over the installed families

**Files:**
- Create: `settings/fonts.py` (pure), `settings/fontpicker.py` (GTK), `tests/test_settings_fonts.py`, `tests/test_settings_fontpicker.py`

**Interfaces:**
- Consumes: `shell.config.models.check_font_name(name: str) -> str` (raises `ValueError`).
- Produces (`settings.fonts`): `GENERIC_FAMILIES = ("monospace", "sans-serif", "serif")`, `SYSTEM_SUFFIX = " (system font)"`, `MISSING_SUFFIX = " (not installed)"`, `Entry = tuple[str | None, str]` (value, label), `font_families(names: Iterable[str]) -> tuple[str, ...]`, `picker_entries(families: Sequence[str], system: str, current: str | None, inherit_label: str | None = None) -> tuple[Entry, ...]`, `matches(label: str, text: str) -> bool`, `first_match(entries: Sequence[Entry], text: str) -> Entry | None`.
- Produces (`settings.fontpicker`): `POPUP_HEIGHT = 360`, `POPUP_WIDTH = 280`, `FONT_CHARS = 22`, `installed_families() -> tuple[str, ...]` (cached), `family_of(font_name: str) -> str`, `system_family() -> str`, `FontPicker(on_pick: Callable[[str | None], None], families: Callable[[], Sequence[str]] | None = None, system: Callable[[], str] | None = None, inherit_label: str | None = None)` with `.button: Gtk.MenuButton` (the widget to pack), `.label`, `.popover`, `.search: Gtk.Entry`, `.list: Gtk.ListBox`, `.entries`, `.value`, `set(value: str | None)` (never calls back), `fill()` (built when the list opens: the button's `toggled`), `visible_labels() -> list[str]`. `families`/`system` None: `installed_families`/`system_family` looked up when the list opens (tests monkeypatch the module functions).

- [ ] **Step 1: Write the failing tests**

```diff
diff --git a/tests/test_settings_fonts.py b/tests/test_settings_fonts.py
new file mode 100644
--- /dev/null
+++ b/tests/test_settings_fonts.py
@@ -0,0 +1,64 @@
+"""settings.fonts: the font pickers' lists (pure: no GTK, no installed fonts)."""
+
+from settings.fonts import (
+    GENERIC_FAMILIES,
+    first_match,
+    font_families,
+    matches,
+    picker_entries,
+)
+
+
+def test_installed_families_are_cleaned_deduplicated_and_sorted_without_case():
+    names = [
+        "Noto Sans",
+        "  JetBrains Mono ",
+        "noto sans",  # the same family twice
+        "Monospace",  # fontconfig's aliases: the generic names stand for them
+        "Sans",
+        "Serif",
+        "System-ui",
+        "",
+        'Bad "Quote" Font',  # cannot go into CSS: check_font_name refuses it
+        "Semi;colon",
+        "abyssinica SIL",
+    ]
+    assert font_families(names) == ("abyssinica SIL", "JetBrains Mono", "Noto Sans")
+
+
+def test_a_picker_lists_inherit_missing_system_generics_then_families():
+    families = ("DejaVu Sans", "Hack Nerd Font", "JetBrains Mono")
+    entries = picker_entries(families, "Hack Nerd Font", "Gone Font", "Theme font")
+    assert entries == (
+        (None, "Theme font"),
+        ("Gone Font", "Gone Font (not installed)"),  # kept and shown, never dropped
+        ("Hack Nerd Font", "Hack Nerd Font (system font)"),
+        *((g, g) for g in GENERIC_FAMILIES),
+        ("DejaVu Sans", "DejaVu Sans"),
+        ("JetBrains Mono", "JetBrains Mono"),  # the system font is not listed twice
+    )
+
+
+def test_an_installed_or_generic_current_value_is_not_marked_missing():
+    families = ("JetBrains Mono",)
+    for current in ("JetBrains Mono", "jetbrains mono", "monospace", None):
+        labels = [label for _v, label in picker_entries(families, "", current)]
+        assert not any(label.endswith("(not installed)") for label in labels), current
+    assert [v for v, _l in picker_entries(families, "", None)] == [
+        *GENERIC_FAMILIES,
+        "JetBrains Mono",
+    ]  # no system font known, no inherited row
+
+
+def test_typing_finds_any_part_of_a_name_without_case():
+    assert matches("Hack Nerd Font Mono", "mono")
+    assert matches("monospace", " MONO ")
+    assert matches("Anything", "")
+    assert not matches("Noto Sans", "mono")
+
+
+def test_enter_picks_the_first_row_shown():
+    entries = picker_entries(("Fira Mono", "Noto Sans"), "Noto Sans", None, "Theme font")
+    assert first_match(entries, "mono") == ("monospace", "monospace")
+    assert first_match(entries, "") == (None, "Theme font")
+    assert first_match(entries, "zzz") is None
diff --git a/tests/test_settings_fontpicker.py b/tests/test_settings_fontpicker.py
new file mode 100644
--- /dev/null
+++ b/tests/test_settings_fontpicker.py
@@ -0,0 +1,94 @@
+"""settings.fontpicker: the searchable font dropdown. The fonts are a fixed list (never the
+machine's); the popover is opened as a widget flag only (no window exists, nothing is
+mapped)."""
+
+import pytest
+
+gi = pytest.importorskip("gi")
+gi.require_version("Gtk", "3.0")
+
+from gi.repository import Gtk  # noqa: E402
+
+if not Gtk.init_check()[0]:
+    pytest.skip("no display", allow_module_level=True)
+
+from settings import fontpicker  # noqa: E402
+
+FAMILIES = ("DejaVu Sans", "Fira Mono", "Hack Nerd Font", "Noto Sans")
+
+
+def picker(value="Fira Mono", inherit=None, system="Noto Sans"):
+    picks = []
+    p = fontpicker.FontPicker(picks.append, lambda: FAMILIES, lambda: system, inherit)
+    p.set(value)
+    return p, picks
+
+
+def test_the_button_shows_the_value_and_set_never_calls_back():
+    p, picks = picker("Fira Mono")
+    assert p.label.get_text() == "Fira Mono" and p.button.get_tooltip_text() == "Fira Mono"
+    p.set(None)
+    assert p.label.get_text() == ""  # no inherited row: nothing to name
+    q, _ = picker(None, inherit="Theme font")
+    assert q.label.get_text() == "Theme font"
+    assert picks == []
+
+
+def test_opening_the_list_fills_it_with_the_system_font_first_and_the_shown_row_selected():
+    p, _ = picker("Fira Mono")
+    assert len(p.list.get_children()) == 0  # nothing is built before the list opens
+    p.button.set_active(True)  # the popover is visible as a flag only: no window exists
+    labels = [row.get_child().get_text() for row in p.list.get_children()]
+    assert labels[0] == "Noto Sans (system font)"
+    assert labels == p.visible_labels()
+    assert p.list.get_selected_row().get_child().get_text() == "Fira Mono"
+    p.button.set_active(False)
+
+
+def test_typing_filters_the_rows_and_enter_picks_the_first():
+    p, picks = picker("Fira Mono")
+    p.fill()
+    p.search.set_text("SANS")
+    assert p.visible_labels() == ["Noto Sans (system font)", "sans-serif", "DejaVu Sans"]
+    rows = p.list.get_children()
+    shown = [row.get_child().get_text() for row in rows if row.get_child_visible()]
+    assert shown == p.visible_labels()  # what the list box shows after its own filter
+    p.search.emit("activate")  # Enter
+    assert picks == ["Noto Sans"] and p.label.get_text() == "Noto Sans"
+
+
+def test_a_click_picks_a_row_and_the_shown_row_sends_nothing():
+    p, picks = picker("Fira Mono")
+    p.fill()
+    rows = p.list.get_children()
+    fira = next(r for r in rows if r.get_child().get_text() == "Fira Mono")
+    p.list.emit("row-activated", fira)  # the value shown: nothing to send
+    assert picks == []
+    dejavu = next(r for r in rows if r.get_child().get_text() == "DejaVu Sans")
+    p.list.emit("row-activated", dejavu)
+    assert picks == ["DejaVu Sans"]
+
+
+def test_the_inherited_row_picks_none():
+    p, picks = picker("Fira Mono", inherit="Theme font")
+    p.fill()
+    p.list.emit("row-activated", p.list.get_row_at_index(0))
+    assert picks == [None] and p.label.get_text() == "Theme font"
+
+
+def test_a_font_that_is_not_installed_is_listed_and_kept():
+    p, picks = picker("Gone Font")
+    p.fill()
+    assert p.visible_labels()[0] == "Gone Font (not installed)"
+    assert p.list.get_selected_row().get_index() == 0
+    assert p.label.get_text() == "Gone Font" and picks == []
+
+
+def test_the_desktop_font_and_the_installed_families():
+    assert fontpicker.family_of("Hack Nerd Font  10") == "Hack Nerd Font"
+    assert fontpicker.family_of("Noto Sans Bold Italic 11") == "Noto Sans"
+    assert isinstance(fontpicker.system_family(), str)
+    families = fontpicker.installed_families()  # the machine's: only what holds for any set
+    assert fontpicker.installed_families() is families  # read once
+    assert list(families) == sorted(families, key=lambda n: (n.casefold(), n))
+    assert "Monospace" not in families and "monospace" not in families
```

- [ ] **Step 2: Run them to verify they fail**

Run: `scripts/py -m pytest -q tests/test_settings_fonts.py tests/test_settings_fontpicker.py`
Expected: `ERROR tests/test_settings_fonts.py`, `ERROR tests/test_settings_fontpicker.py`, `Interrupted: 2 errors during collection` (`ModuleNotFoundError: No module named 'settings.fonts'`; `ImportError: cannot import name 'fontpicker' from 'settings'`).

- [ ] **Step 3: Implement**

```diff
diff --git a/settings/fonts.py b/settings/fonts.py
new file mode 100644
--- /dev/null
+++ b/settings/fonts.py
@@ -0,0 +1,77 @@
+"""The font lists of the settings window's font pickers (settings.fontpicker). Pure: the
+installed families come in as plain names (from Pango there), so this is tested without GTK
+and without depending on the fonts of the machine.
+
+A picker lists, in order: the inherited value (a widget's font: "Theme font"; its value is
+None, choosing it resets the key), a configured name that is not installed (kept and shown, so
+that it is never dropped by opening the list), the desktop's own font ("Noto Sans (system
+font)", Phil: the default should be the system font), the CSS generic families the shell keeps
+unquoted, then every installed family, sorted without case."""
+
+from __future__ import annotations
+
+from collections.abc import Iterable, Sequence
+
+from shell.config.models import check_font_name
+
+GENERIC_FAMILIES = ("monospace", "sans-serif", "serif")  # shell.theme writes them unquoted
+# Pango lists fontconfig's aliases as families ("Monospace", "Sans", "Serif", "System-ui");
+# the generic names above stand for them
+_ALIASES = frozenset(
+    {"monospace", "sans", "sans-serif", "serif", "system-ui", "cursive", "fantasy", "emoji"}
+)
+SYSTEM_SUFFIX = " (system font)"
+MISSING_SUFFIX = " (not installed)"
+
+Entry = tuple[str | None, str]  # (the value written, the label shown)
+
+
+def font_families(names: Iterable[str]) -> tuple[str, ...]:
+    """Installed family names as a picker lists them: stripped, without the aliases, without
+    a name the config could not hold (check_font_name: it goes into CSS), one per name
+    regardless of case, sorted without case."""
+    kept: dict[str, str] = {}
+    for raw in names:
+        name = raw.strip()
+        key = name.casefold()
+        if not name or key in _ALIASES or key in kept:
+            continue
+        try:
+            check_font_name(name)
+        except ValueError:
+            continue
+        kept[key] = name
+    return tuple(sorted(kept.values(), key=lambda n: (n.casefold(), n)))
+
+
+def picker_entries(
+    families: Sequence[str],
+    system: str,
+    current: str | None,
+    inherit_label: str | None = None,
+) -> tuple[Entry, ...]:
+    """The rows of a picker, in order (see the module text). `families`: font_families();
+    `system`: the desktop font's family ("" when unknown); `current`: the value shown;
+    `inherit_label`: the label of the inherited value's row (None: no such row)."""
+    entries: list[Entry] = []
+    if inherit_label is not None:
+        entries.append((None, inherit_label))
+    known = {f.casefold() for f in (*families, *GENERIC_FAMILIES)}
+    if current is not None and current.casefold() not in known:
+        entries.append((current, current + MISSING_SUFFIX))
+    if system:
+        entries.append((system, system + SYSTEM_SUFFIX))
+    entries += [(g, g) for g in GENERIC_FAMILIES]
+    entries += [(f, f) for f in families if f.casefold() != system.casefold()]
+    return tuple(entries)
+
+
+def matches(label: str, text: str) -> bool:
+    """A row is shown when its label holds the typed text, ignoring case and the spaces
+    around it ("mono" finds "Hack Nerd Font Mono" and "monospace")."""
+    return text.strip().casefold() in label.casefold()
+
+
+def first_match(entries: Sequence[Entry], text: str) -> Entry | None:
+    """The row Enter picks: the first one shown for `text`."""
+    return next((e for e in entries if matches(e[1], text)), None)
diff --git a/settings/fontpicker.py b/settings/fontpicker.py
new file mode 100644
--- /dev/null
+++ b/settings/fontpicker.py
@@ -0,0 +1,150 @@
+"""A searchable font dropdown (Phil: "list system available fonts in a dropdown that is
+searchable by typing. Default should be the system selected font"): a button showing the font,
+opening a popover with a search entry above the list of families (settings.fonts). Typing
+filters the list (any part of the name, without case); Enter picks the first row shown; a click
+picks a row. The list is a GTK popover, drawn inside the settings window, sized to its rows up
+to POPUP_HEIGHT (then it scrolls): it is not a compositor popup, so it opens at its size.
+
+The installed families are read once per process, when a list is first opened
+(installed_families, cached); tests pass their own list. Values shown with set() never call
+back."""
+
+from __future__ import annotations
+
+import functools
+from collections.abc import Callable, Sequence
+
+import gi
+
+gi.require_version("Gtk", "3.0")
+gi.require_version("Pango", "1.0")
+gi.require_version("PangoCairo", "1.0")
+from gi.repository import Gtk, Pango, PangoCairo  # noqa: E402
+
+from settings.fonts import Entry, first_match, font_families, matches, picker_entries  # noqa: E402
+
+POPUP_HEIGHT = 360  # px: the most the list takes before it scrolls
+POPUP_WIDTH = 280
+FONT_CHARS = 22  # the button's label; a longer name is cut, the whole name is the tooltip
+
+
+@functools.cache
+def installed_families() -> tuple[str, ...]:
+    """Every installed font family (Pango's font map), as settings.fonts.font_families lists
+    them. Read once: a font installed while the window is open shows after a restart."""
+    return font_families(f.get_name() for f in PangoCairo.FontMap.get_default().list_families())
+
+
+def family_of(font_name: str) -> str:
+    """The family of a Pango font name: "Noto Sans Bold 10" -> "Noto Sans"."""
+    return Pango.FontDescription.from_string(font_name).get_family() or ""
+
+
+def system_family() -> str:
+    """The desktop's font family (Gtk.Settings gtk-font-name, which KDE sets to its General
+    font); "" when unknown."""
+    settings = Gtk.Settings.get_default()
+    name = settings.props.gtk_font_name if settings is not None else None
+    return family_of(name) if name else ""
+
+
+class FontPicker:
+    """`on_pick(value)` runs when the user picks a row whose value is not the one shown: a
+    family name, or None for the inherited row (`inherit_label`, e.g. "Theme font"). `button`
+    is the widget to pack. `families` and `system` (None: installed_families and
+    system_family, looked up when the list opens, so tests can replace them) give the list."""
+
+    def __init__(
+        self,
+        on_pick: Callable[[str | None], None],
+        families: Callable[[], Sequence[str]] | None = None,
+        system: Callable[[], str] | None = None,
+        inherit_label: str | None = None,
+    ):
+        self._on_pick = on_pick
+        self._families = families
+        self._system = system
+        self.inherit_label = inherit_label
+        self.value: str | None = None
+        self.entries: tuple[Entry, ...] = ()
+        self.label = Gtk.Label(xalign=0)
+        self.label.set_ellipsize(Pango.EllipsizeMode.END)
+        self.label.set_max_width_chars(FONT_CHARS)
+        self.label.set_width_chars(FONT_CHARS)
+        face = Gtk.Box(spacing=4)
+        face.pack_start(self.label, True, True, 0)
+        face.pack_start(
+            Gtk.Image.new_from_icon_name("pan-down-symbolic", Gtk.IconSize.BUTTON), False, False, 0
+        )
+        self.button = Gtk.MenuButton()
+        self.button.add(face)
+        self.search = Gtk.Entry(placeholder_text="Type to search")
+        self.search.set_icon_from_icon_name(Gtk.EntryIconPosition.PRIMARY, "edit-find-symbolic")
+        self.list = Gtk.ListBox(activate_on_single_click=True)
+        self.list.set_filter_func(self._shown)
+        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
+        scroller.set_propagate_natural_height(True)  # the popover fits its rows ...
+        scroller.set_max_content_height(POPUP_HEIGHT)  # ... up to this height
+        scroller.set_min_content_width(POPUP_WIDTH)
+        scroller.add(self.list)
+        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
+        box.set_property("margin", 6)
+        box.pack_start(self.search, False, False, 0)
+        box.pack_start(scroller, True, True, 0)
+        box.show_all()
+        self.popover = Gtk.Popover(relative_to=self.button)
+        self.popover.add(box)
+        self.button.set_popover(self.popover)
+        self.button.connect("toggled", self._toggled)
+        self.search.connect("changed", lambda _e: self.list.invalidate_filter())
+        self.search.connect("activate", self._pick_first)
+        self.list.connect(
+            "row-activated", lambda _l, row: self._pick(self.entries[row.get_index()])
+        )
+
+    def set(self, value: str | None) -> None:
+        """Show `value` (None: the inherited row's label)."""
+        self.value = value
+        text = value if value is not None else (self.inherit_label or "")
+        self.label.set_text(text)
+        self.button.set_tooltip_text(text or None)
+
+    def _toggled(self, button: Gtk.MenuButton) -> None:
+        if button.get_active():
+            self.fill()
+
+    def fill(self) -> None:
+        """(Re)build the rows for the value shown, clear the search and select the shown row
+        (the button runs this when the list opens)."""
+        families = (self._families or installed_families)()
+        system = (self._system or system_family)()
+        self.entries = picker_entries(families, system, self.value, self.inherit_label)
+        for row in self.list.get_children():
+            self.list.remove(row)
+        for _value, label in self.entries:
+            self.list.add(Gtk.Label(label=label, xalign=0))
+        self.list.show_all()
+        self.search.set_text("")
+        shown = next((i for i, e in enumerate(self.entries) if e[0] == self.value), None)
+        if shown is not None:
+            self.list.select_row(self.list.get_row_at_index(shown))
+        self.search.grab_focus()
+
+    def visible_labels(self) -> list[str]:
+        """The labels of the rows the search leaves shown (tests, and the reviewer's eye)."""
+        return [label for _v, label in self.entries if matches(label, self.search.get_text())]
+
+    def _shown(self, row: Gtk.ListBoxRow) -> bool:
+        return matches(self.entries[row.get_index()][1], self.search.get_text())
+
+    def _pick_first(self, _entry: Gtk.Entry) -> None:
+        entry = first_match(self.entries, self.search.get_text())
+        if entry is not None:
+            self._pick(entry)
+
+    def _pick(self, entry: Entry) -> None:
+        self.popover.popdown()
+        value = entry[0]
+        if value != self.value:
+            self.set(value)
+            self._on_pick(value)
```

- [ ] **Step 4: Run them to verify they pass, then VERIFY**

Run the command of Step 2: 12 passed. VERIFY: `2651 passed`.

- [ ] **Step 5: Commit**

```bash
git add settings/fonts.py settings/fontpicker.py tests/test_settings_fonts.py tests/test_settings_fontpicker.py
git commit -m "feat(settings): a searchable font picker over the installed families" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

**Reviewer mutation list:**
- keep the aliases (`if not name or key in kept:`) → `test_installed_families_are_cleaned_deduplicated_and_sorted_without_case` fails;
- drop the `check_font_name` filter → the same test fails;
- never list a missing current value (`if False:`) → `test_a_picker_lists_inherit_missing_system_generics_then_families` and `test_a_font_that_is_not_installed_is_listed_and_kept` fail;
- list the system font twice → `test_a_picker_lists_inherit_missing_system_generics_then_families` fails;
- case-sensitive `matches` → `test_typing_finds_any_part_of_a_name_without_case` and `test_typing_filters_the_rows_and_enter_picks_the_first` fail;
- no `set_filter_func` → `test_typing_filters_the_rows_and_enter_picks_the_first` fails (every row stays visible in the list box);
- send the value shown again → `test_a_click_picks_a_row_and_the_shown_row_sends_nothing` fails;
- drop `@functools.cache` → `test_the_desktop_font_and_the_installed_families` fails;
- no `fill()` on `toggled` → `test_opening_the_list_fills_it_with_the_system_font_first_and_the_shown_row_selected` fails.

---

### Task 5: The theme's font list is one font picker per family

**Files:**
- Modify: `settings/fonts.py` (`next_font`), `settings/fields.py` (`FontListEditor`, `_FontLine`, `FONT_LINE_BUTTONS` replace `FontsEditor`; imports; two docstrings no longer name the font list as typed text), `settings/form.py` (`parse_fonts`, `format_fonts` removed)
- Test: `tests/test_settings_fonts.py`, `tests/test_settings_fields.py`, `tests/test_settings_form.py`, `tests/test_settings_view.py`

**Interfaces:**
- Consumes: `settings.fontpicker.FontPicker`, `settings.fontpicker.system_family` (looked up at Add time, through the module), `settings.fonts.GENERIC_FAMILIES`.
- Produces: `settings.fonts.next_font(fonts: Sequence[str], system: str) -> str`; `settings.fields.FontListEditor(emit: Emit)` with `.widget` (a vertical `Gtk.Box`), `.fonts: list[str]`, `.lines: list[_FontLine]` (the first `len(fonts)` are shown), `.add_button: Gtk.Button`, `set(value: list[str])`; `_FontLine.picker: FontPicker`, `.buttons: dict[str, Gtk.Button]` (`"up"`, `"down"`, `"remove"`), `.box`. `make_editor` returns `FontListEditor` for `kind == "fonts"`.

- [ ] **Step 1: Write the failing tests.** The font entry was the tests' "row with typed text"; the font list has no typed text, so those tests (two in `test_settings_fields.py`, six in `test_settings_view.py`) now use a panel name row: same contracts. `test_fonts_round_trip` goes with `parse_fonts`.

```diff
diff --git a/tests/test_settings_fonts.py b/tests/test_settings_fonts.py
--- a/tests/test_settings_fonts.py
+++ b/tests/test_settings_fonts.py
@@ -5,6 +5,7 @@
     first_match,
     font_families,
     matches,
+    next_font,
     picker_entries,
 )
 
@@ -62,3 +63,11 @@
     assert first_match(entries, "mono") == ("monospace", "monospace")
     assert first_match(entries, "") == (None, "Theme font")
     assert first_match(entries, "zzz") is None
+
+
+def test_add_font_appends_the_system_font_else_a_generic_family_not_listed_yet():
+    assert next_font(["Hack Nerd Font Mono"], "Noto Sans") == "Noto Sans"
+    assert next_font(["noto sans"], "Noto Sans") == "monospace"
+    assert next_font(["Noto Sans", "monospace", "sans-serif"], "Noto Sans") == "serif"
+    assert next_font(["A"], "") == "monospace"  # no desktop font known
+    assert next_font(["Noto Sans", *GENERIC_FAMILIES], "Noto Sans") == "Noto Sans"
diff --git a/tests/test_settings_fields.py b/tests/test_settings_fields.py
--- a/tests/test_settings_fields.py
+++ b/tests/test_settings_fields.py
@@ -90,15 +90,66 @@
     assert [c[1] for c in changes + changes2 + changes3] == [True, "chevron", "clock"]
 
 
-def test_fonts_row_commits_on_enter_only_when_changed():
+@pytest.fixture
+def fonts(monkeypatch):
+    """A fixed font list and desktop font: never the machine's (settings.fontpicker)."""
+    from settings import fontpicker
+
+    monkeypatch.setattr(fontpicker, "installed_families", lambda: ("Fira Mono", "Noto Sans"))
+    monkeypatch.setattr(fontpicker, "system_family", lambda: "Noto Sans")
+
+
+def shown_fonts(editor):
+    return [line.picker.label.get_text() for line in editor.lines if line.box.get_visible()]
+
+
+def test_the_font_list_is_one_picker_per_family(fonts):
     row, changes, _ = row_for(FORM.theme.field("font"), ["Hack Nerd Font Mono", "monospace"])
-    entry = row.editor.widget
-    assert entry.get_text() == "Hack Nerd Font Mono, monospace"
-    entry.emit("activate")
-    assert changes == []
-    entry.set_text("JetBrains Mono, monospace")
-    entry.emit("activate")
-    assert changes == [(("theme", "x"), ["JetBrains Mono", "monospace"])]
+    editor = row.editor
+    assert isinstance(editor, fields.FontListEditor)
+    assert shown_fonts(editor) == ["Hack Nerd Font Mono", "monospace"]
+    first, second = editor.lines
+    assert not first.buttons["up"].get_sensitive() and first.buttons["down"].get_sensitive()
+    assert second.buttons["up"].get_sensitive() and not second.buttons["down"].get_sensitive()
+    assert not row.unsent() and changes == []  # nothing typed, nothing sent by showing
+
+
+def test_picking_a_family_sends_the_whole_list(fonts):
+    row, changes, _ = row_for(FORM.theme.field("font"), ["Hack Nerd Font Mono", "monospace"])
+    picker = row.editor.lines[1].picker
+    picker.fill()
+    picker.search.set_text("fira")
+    picker.search.emit("activate")
+    assert changes == [(("theme", "x"), ["Hack Nerd Font Mono", "Fira Mono"])]
+    assert shown_fonts(row.editor) == ["Hack Nerd Font Mono", "Fira Mono"]
+
+
+def test_moving_removing_and_adding_fonts(fonts):
+    row, changes, _ = row_for(FORM.theme.field("font"), ["A", "B", "C"])
+    editor = row.editor
+    editor.lines[2].buttons["up"].clicked()
+    editor.lines[0].buttons["remove"].clicked()
+    editor.add_button.clicked()  # the desktop's font
+    editor.add_button.clicked()  # it is listed: the first generic family not listed
+    assert [v for _p, v in changes] == [
+        ["A", "C", "B"],
+        ["C", "B"],
+        ["C", "B", "Noto Sans"],
+        ["C", "B", "Noto Sans", "monospace"],
+    ]
+    assert shown_fonts(editor) == ["C", "B", "Noto Sans", "monospace"]
+
+
+def test_the_last_font_cannot_be_removed_and_a_shorter_list_hides_lines(fonts):
+    row, changes, _ = row_for(FORM.theme.field("font"), ["A", "B"])
+    editor = row.editor
+    editor.lines[1].buttons["remove"].clicked()  # the line's own button: hidden, not destroyed
+    assert shown_fonts(editor) == ["A"] and len(editor.lines) == 2
+    assert not editor.lines[0].buttons["remove"].get_sensitive()
+    editor.lines[0].buttons["remove"].clicked()  # insensitive in the window; never sent anyway
+    assert [v for _p, v in changes] == [["A"]]
+    row.show_value(FieldValue(["X", "Y", "Z"], True, "your config"))  # a re-read: lines grow
+    assert shown_fonts(editor) == ["X", "Y", "Z"] and len(editor.lines) == 3
 
 
 def test_length_row_modes():
@@ -156,17 +207,17 @@
     queued = []
     spin, changes, _ = row_for(FORM.theme.field("thickness"), 10, queued=queued)
     spin.editor.widget.set_text("14")  # typed, Enter not pressed
-    fonts, changes2, _ = row_for(FORM.theme.field("font"), ["A"])
-    fonts.editor.widget.set_text("B, monospace")
-    assert spin.unsent() and fonts.unsent()
+    name, changes2, _ = row_for(FORM.edge_panel.field("name"), "Dock")
+    name.editor.widget.set_text("Bottom dock")
+    assert spin.unsent() and name.unsent()
     spin.flush()
-    fonts.flush()
+    name.flush()
     assert queued == [(("theme", "x"), 14, 10)] and changes == []
-    assert changes2 == [(("theme", "x"), ["B", "monospace"])]
+    assert changes2 == [(("theme", "x"), "Bottom dock")]
     spin.flush()
-    fonts.flush()
+    name.flush()
     assert len(queued) == 1 and len(changes2) == 1  # nothing typed any more
-    assert not spin.unsent() and not fonts.unsent()
+    assert not spin.unsent() and not name.unsent()
 
 
 def test_choices_show_their_labels():
@@ -278,16 +329,16 @@
             row.show_value(FieldValue(result.get(row.path[1], row.shown), True, "x"), True)
 
     thick = fields.FieldRow(FORM.theme.field("thickness"), ("theme", "t"), on_change, id)
-    font = fields.FieldRow(FORM.theme.field("font"), ("theme", "f"), on_change, id)
-    rows[:] = [thick, font]
-    thick.shown, font.shown = 10, ["A"]
+    name = fields.FieldRow(FORM.edge_panel.field("name"), ("theme", "n"), on_change, id)
+    rows[:] = [thick, name]
+    thick.shown, name.shown = 10, "Dock"
     for row in rows:
         row.show_value(FieldValue(row.shown, False, "default"))
     thick.editor.widget.set_value(20)
-    font.editor.widget.set_text("B, C")
+    name.editor.widget.set_text("Bottom dock")
     for row in rows:  # SettingsView.flush
         row.flush()
-    assert result == {"t": 20, "f": ["B", "C"]}
+    assert result == {"t": 20, "n": "Bottom dock"}
 
 
 def test_a_toggle_within_the_pause_does_not_drop_a_queued_spin():
diff --git a/tests/test_settings_form.py b/tests/test_settings_form.py
--- a/tests/test_settings_form.py
+++ b/tests/test_settings_form.py
@@ -14,9 +14,7 @@
     WidgetChoice,
     add_choices,
     config_form,
-    format_fonts,
     join_length,
-    parse_fonts,
     props_section,
     rgba_to_hex,
     section_for,
@@ -298,16 +296,6 @@
         join_length("inches", 3.0)
     with pytest.raises(ValueError):
         split_length("wide")
-
-
-def test_fonts_round_trip():
-    assert parse_fonts(" Hack Nerd Font Mono , JetBrains Mono,, monospace ") == [
-        "Hack Nerd Font Mono",
-        "JetBrains Mono",
-        "monospace",
-    ]
-    assert format_fonts(["A", "b c"]) == "A, b c"
-    assert parse_fonts("  ") == []
 
 
 # ---- panel type and widget properties (panel/widget spec 3.7) -------------------------
diff --git a/tests/test_settings_view.py b/tests/test_settings_view.py
--- a/tests/test_settings_view.py
+++ b/tests/test_settings_view.py
@@ -642,20 +642,20 @@
     assert path.read_text() == USER and not view.session.history
 
 
-FONT = ("theme", "font")
-
-
-def test_typed_fonts_never_reach_the_file_through_a_hand_edit_rebuild(make):
+NAME = ("monitors", "HDMI-A-1", "panels", 0, "name")
+
+
+def test_typed_text_never_reaches_the_file_through_a_hand_edit_rebuild(make):
     """The rebuild unparents the focused entry and GTK sends focus-out: the retired row's
-    commit must not write the typed fonts onto the re-read file."""
-    view, path = make()
-    old = row(view, FONT)
-    old.editor.widget.set_text("Typed Font")
+    commit must not write the typed name onto the re-read file."""
+    view, path = make()
+    old = row(view, NAME)
+    old.editor.widget.set_text("Typed Name")
     path.write_text(USER.replace('shell = "edge"', 'shell = "both"'))
     view.file_changed()
     old.editor.commit()  # the focus-out of the retired entry
     old.flush()
-    assert "Typed Font" not in path.read_text() and not view.session.history
+    assert "Typed Name" not in path.read_text() and not view.session.history
 
 
 TILE_USER = """\
@@ -972,10 +972,10 @@
 
 def test_typed_text_dropped_by_a_hand_edit_is_named(make):
     view, path = make()
-    row(view, FONT).editor.widget.set_text("Typed Font")
+    row(view, NAME).editor.widget.set_text("Typed Name")
     path.write_text(USER.replace('shell = "edge"', 'shell = "both"'))
     view.file_changed()
-    assert "theme.font (typed text)" in view.banner_label.get_text()
+    assert "monitors.HDMI-A-1.panels[0].name (typed text)" in view.banner_label.get_text()
 
 
 def test_the_deferred_rebuild_applies_what_was_queued_meanwhile_once(make, clock):
@@ -1036,33 +1036,33 @@
 def test_typed_text_is_named_when_a_timer_drain_meets_a_hand_edit(make, clock):
     view, path = make()
     row(view, DEPTH).editor.widget.set_value(120)
-    row(view, FONT).editor.widget.set_text("Typed Font")
+    row(view, NAME).editor.widget.set_text("Typed Name")
     path.write_text(USER.replace('shell = "edge"', 'shell = "both"'))
     _fire(view, clock)
     text = view.banner_label.get_text()
-    assert "theme.font (typed text)" in text and "panels[0].depth = 120" in text
+    assert "panels[0].name (typed text)" in text and "panels[0].depth = 120" in text
 
 
 def test_typed_text_is_named_when_an_immediate_edit_meets_a_hand_edit(make):
     view, path = make()
-    row(view, FONT).editor.widget.set_text("Typed Font")
+    row(view, NAME).editor.widget.set_text("Typed Name")
     path.write_text(USER.replace('shell = "edge"', 'shell = "both"'))
     view._on_change(SHELL, "both")
     drain()
     text = view.banner_label.get_text()
-    assert "theme.font (typed text)" in text and "changed outside" in text
+    assert "panels[0].name (typed text)" in text and "changed outside" in text
 
 
 def test_a_refused_revert_names_the_edits_it_dropped(make, clock):
     view, path = make()
     row(view, DEPTH).editor.widget.set_value(120)
-    row(view, FONT).editor.widget.set_text("Typed Font")
+    row(view, NAME).editor.widget.set_text("Typed Name")
     hand = USER.replace('shell = "edge"', 'shell = "both"')
     path.write_text(hand)
     view.revert()  # refused: the hand edit is the new starting point
     text = view.banner_label.get_text()
     assert "changed outside" in text and "Not applied" in text
-    assert "panels[0].depth = 120" in text and "theme.font (typed text)" in text
+    assert "panels[0].depth = 120" in text and "panels[0].name (typed text)" in text
     assert path.read_text() == hand and len(view.queue) == 0
 
 
@@ -1072,9 +1072,9 @@
     spin = row(view, DEPTH).editor.widget
     spin.set_text("130")
     assert view.save() and "depth = 130" in path.read_text()
-    row(view, FONT).editor.widget.set_text("Typed Font")
+    row(view, NAME).editor.widget.set_text("Typed Name")
     view.flush()
-    assert "Typed Font" in path.read_text()
+    assert 'name = "Typed Name"' in path.read_text()
 
 
 def test_a_nested_run_of_the_queue_inside_a_flush_does_nothing(make, clock):
```

- [ ] **Step 2: Run them to verify they fail**

Run: `scripts/py -m pytest -q tests/test_settings_fonts.py`
Expected: `ERROR tests/test_settings_fonts.py`, `Interrupted: 1 error during collection` (`ImportError: cannot import name 'next_font' from 'settings.fonts'`).
Run: `scripts/py -m pytest -q tests/test_settings_fields.py tests/test_settings_form.py tests/test_settings_view.py`
Expected: `4 failed, 239 passed`: the four new font list tests (`AttributeError: module 'settings.fields' has no attribute 'FontListEditor'`, `'FontsEditor' object has no attribute 'lines'`). The rewritten typed-text tests already pass (they use the name row), and the form tests pass (they only lost `test_fonts_round_trip` and the two imports).

- [ ] **Step 3: Implement**

```diff
diff --git a/settings/fonts.py b/settings/fonts.py
--- a/settings/fonts.py
+++ b/settings/fonts.py
@@ -75,3 +75,13 @@
 def first_match(entries: Sequence[Entry], text: str) -> Entry | None:
     """The row Enter picks: the first one shown for `text`."""
     return next((e for e in entries if matches(e[1], text)), None)
+
+
+def next_font(fonts: Sequence[str], system: str) -> str:
+    """The family "Add font" appends: the desktop's font, else the first generic family the
+    list does not hold yet (a fallback list names each family once)."""
+    have = {f.casefold() for f in fonts}
+    for name in (system, *GENERIC_FAMILIES):
+        if name and name.casefold() not in have:
+            return name
+    return system or GENERIC_FAMILIES[0]
diff --git a/settings/fields.py b/settings/fields.py
--- a/settings/fields.py
+++ b/settings/fields.py
@@ -13,14 +13,15 @@
 gi.require_version("Pango", "1.0")
 from gi.repository import Gdk, GObject, Gtk, Pango  # noqa: E402
 
+from settings import fontpicker  # noqa: E402
+from settings.fontpicker import FontPicker  # noqa: E402
+from settings.fonts import next_font  # noqa: E402
 from settings.form import (  # noqa: E402
     LENGTH_MODES,
     LENGTH_PERCENT,
     LENGTH_PX,
     FieldSpec,
-    format_fonts,
     join_length,
-    parse_fonts,
     rgba_to_hex,
     split_length,
     uses_slider,
@@ -254,31 +255,110 @@
             self.widget.set_active(-1)  # not a choice: show none, never the previous one
 
 
-class FontsEditor(_Editor):
+class _FontLine:
+    """One family of a font list: its picker and its Move up, Move down and Remove."""
+
+    def __init__(self, picker: FontPicker, buttons: dict[str, Gtk.Button]):
+        self.picker = picker
+        self.buttons = buttons
+        self.box = Gtk.Box(spacing=4)
+        self.box.pack_start(picker.button, False, False, 0)
+        for button in buttons.values():
+            self.box.pack_start(button, False, False, 0)
+        for child in self.box.get_children():
+            child.show_all()
+        self.box.set_no_show_all(True)  # shown by FontListEditor only while it is in use
+
+
+FONT_LINE_BUTTONS = (  # action, icon, tooltip
+    ("up", "go-up-symbolic", "Move this font up: it is tried earlier"),
+    ("down", "go-down-symbolic", "Move this font down: it is tried later"),
+    ("remove", "list-remove-symbolic", "Remove this font from the list"),
+)
+
+
+class FontListEditor(_Editor):
+    """The theme's font list, an ordered fallback list (the first installed family is used):
+    one searchable picker per family (settings.fontpicker), each with Move up, Move down and
+    Remove, and Add font below. Every change sends the whole list at once; there is no typed
+    text (dirty() is False). The list keeps one family (the config needs one): its Remove is
+    insensitive. Add font appends the desktop's font (Phil: the default is the system font),
+    else a generic family the list does not hold. Lines are hidden, never destroyed, when the
+    list gets shorter: a line's own Remove click must not free the button it runs in."""
+
     def __init__(self, emit: Emit):
-        self.widget = Gtk.Entry(width_chars=30)
-        self._shown: list[str] = []
         self._emit = emit
-        self.widget.connect("activate", lambda *_a: self.commit())
-        self.widget.connect("focus-out-event", lambda *_a: self.commit() or False)
-
-    def dirty(self) -> bool:
-        return parse_fonts(self.widget.get_text()) != self._shown
-
-    def commit(self) -> None:
-        fonts = parse_fonts(self.widget.get_text())
-        if fonts != self._shown:
-            self._shown = fonts
-            self._emit(fonts)
+        self.fonts: list[str] = []
+        self.lines: list[_FontLine] = []  # the first len(fonts) are shown
+        self.list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
+        self.add_button = Gtk.Button(label="Add font", halign=Gtk.Align.START)
+        self.add_button.set_tooltip_text("Add a font at the end of the list")
+        self.add_button.connect("clicked", lambda _b: self._add())
+        self.widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
+        self.widget.pack_start(self.list_box, False, False, 0)
+        self.widget.pack_start(self.add_button, False, False, 0)
 
     def set(self, value: list[str]) -> None:
-        self._shown = list(value)
-        self.widget.set_text(format_fonts(value))
+        self.fonts = list(value)
+        self._sync()
+
+    def _line(self, index: int) -> _FontLine:
+        picker = FontPicker(lambda value: self._replace(index, value))
+        buttons = {}
+        for action, icon, tip in FONT_LINE_BUTTONS:
+            button = Gtk.Button.new_from_icon_name(icon, Gtk.IconSize.BUTTON)
+            button.set_tooltip_text(tip)
+            button.get_accessible().set_name(tip.split(":")[0])
+            button.connect("clicked", lambda _b, a=action: self._act(index, a))
+            buttons[action] = button
+        line = _FontLine(picker, buttons)
+        self.list_box.pack_start(line.box, False, False, 0)
+        return line
+
+    def _sync(self) -> None:
+        while len(self.lines) < len(self.fonts):
+            self.lines.append(self._line(len(self.lines)))
+        count = len(self.fonts)
+        for i, line in enumerate(self.lines):
+            line.box.set_visible(i < count)
+            if i < count:
+                line.picker.set(self.fonts[i])
+                line.buttons["up"].set_sensitive(i > 0)
+                line.buttons["down"].set_sensitive(i < count - 1)
+                line.buttons["remove"].set_sensitive(count > 1)
+
+    def _send(self, fonts: list[str]) -> None:
+        self.fonts = fonts
+        self._sync()
+        self._emit(list(fonts))
+
+    def _replace(self, index: int, value: str | None) -> None:
+        if value is None or index >= len(self.fonts) or self.fonts[index] == value:
+            return
+        fonts = list(self.fonts)
+        fonts[index] = value
+        self._send(fonts)
+
+    def _act(self, index: int, action: str) -> None:
+        fonts = list(self.fonts)
+        if action == "remove" and len(fonts) > 1:
+            del fonts[index]
+        elif action in ("up", "down"):
+            other = index - 1 if action == "up" else index + 1
+            if not 0 <= other < len(fonts):
+                return
+            fonts[index], fonts[other] = fonts[other], fonts[index]
+        else:
+            return
+        self._send(fonts)
+
+    def _add(self) -> None:
+        self._send([*self.fonts, next_font(self.fonts, fontpicker.system_family())])
 
 
 class TextEditor(_Editor):
     """A line of text (a panel's name, a widget's text property): sent on Enter or when the
-    entry loses focus, like the font list."""
+    entry loses focus."""
 
     def __init__(self, emit: Emit, max_length: int | None = None):
         self.widget = Gtk.Entry(width_chars=30)
@@ -391,7 +471,7 @@
     if spec.kind in ("enum", "widget"):
         return ChoiceEditor(spec.choices, emit, spec.labels, spec.disabled)
     if spec.kind == "fonts":
-        return FontsEditor(emit)
+        return FontListEditor(emit)
     if spec.kind == "text":
         return TextEditor(emit, spec.max_length)
     if spec.kind == "length":
@@ -408,8 +488,8 @@
     button is pressed. A spin button's edits (DEBOUNCED kinds) go to `on_queue(path, value,
     base)` instead, `base` being the value the row showed (the view's EditQueue applies them
     after the pause: settings.queue); without `on_queue` they go to on_change at once. The row
-    holds no timer and no pending value of its own: only text typed and not yet sent (a font
-    list, a name, a number without Enter), which flush() sends. `is_pending(path)` says whether
+    holds no timer and no pending value of its own: only text typed and not yet sent (a name,
+    a number without Enter), which flush() sends. `is_pending(path)` says whether
     the view still has an edit of this row queued (a refresh then keeps the editor as it is).
     Values shown with show_value never call back."""
 
@@ -485,9 +565,9 @@
         self.error.set_visible(bool(message))
 
     def flush(self) -> None:
-        """Send text typed and not sent yet (a font list or a name without Enter, a number
-        without Enter): the view applies it with the queue (the window is closing, the pages
-        are about to be rebuilt)."""
+        """Send text typed and not sent yet (a name or a number without Enter): the view
+        applies it with the queue (the window is closing, the pages are about to be
+        rebuilt)."""
         self.editor.commit()
 
     def unsent(self) -> bool:
diff --git a/settings/form.py b/settings/form.py
--- a/settings/form.py
+++ b/settings/form.py
@@ -497,12 +497,3 @@
         text = f"{number:.1f}".rstrip("0").rstrip(".")
         return f"{text}%"
     raise ValueError(f"unknown length mode {mode!r}")
-
-
-def parse_fonts(text: str) -> list[str]:
-    """'Hack Nerd Font Mono, monospace' -> ['Hack Nerd Font Mono', 'monospace']."""
-    return [name.strip() for name in text.split(",") if name.strip()]
-
-
-def format_fonts(fonts: list[str]) -> str:
-    return ", ".join(fonts)
```

- [ ] **Step 4: Run them to verify they pass, then VERIFY**

Run: `scripts/py -m pytest -q tests/test_settings_fonts.py tests/test_settings_fields.py tests/test_settings_form.py tests/test_settings_view.py`: all pass. VERIFY: `2654 passed`. `test_no_tab_is_wider_than_the_space_beside_the_tree_at_860` still passes (the General tab holds the list).

- [ ] **Step 5: Commit**

```bash
git add settings/fonts.py settings/fields.py settings/form.py tests/test_settings_fonts.py tests/test_settings_fields.py tests/test_settings_form.py tests/test_settings_view.py
git commit -m "feat(settings): the theme's font list is one font picker per family" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

**Reviewer mutation list:**
- `if action == "remove":` (the last font removable) → `test_the_last_font_cannot_be_removed_and_a_shorter_list_hides_lines` fails;
- `line.box.set_visible(True)` (a shorter list keeps showing its old lines) → the same test fails;
- `next_font` without the "not listed yet" check → `test_add_font_appends_the_system_font_else_a_generic_family_not_listed_yet` and `test_moving_removing_and_adding_fonts` fail;
- the last Remove always sensitive → `test_the_last_font_cannot_be_removed_and_a_shorter_list_hides_lines` fails.

---

### Task 6: A widget's font is a font picker; every new input fits the tabs and ignores the wheel

**Files:**
- Modify: `settings/form.py` (`FieldKind` gets `"font"`; a widget property named `font` of type string is a `"font"` row), `settings/fields.py` (`UNSET`, `THEME_FONT`, `FontEditor`, `make_editor`, `FieldRow` keeps `_on_reset` and resets on `UNSET`)
- Test: `tests/test_settings_form.py`, `tests/test_settings_fields.py`, `tests/test_settings_view.py`, `tests/test_settings_example.py`

**Interfaces:**
- Consumes: `FontPicker(on_pick, inherit_label=...)` (Task 4); the `fonts` fixture of `tests/test_settings_fields.py` (Task 5).
- Produces: `settings.fields.UNSET` (an editor's "remove this key"; `FieldRow` calls its `on_reset(path)` and shows the key as unset), `settings.fields.THEME_FONT = "Theme font"`, `FontEditor(emit: Emit)` with `.picker: FontPicker`, `.widget` (the picker's button), `set(value: str | None)`; `make_editor` returns it for `kind == "font"`.

- [ ] **Step 1: Write the failing tests.** `test_the_mouse_wheel_edits_no_input_of_the_window` is a pin over the whole window: it passes already (Tasks 1-3 put the guards in) and fails when any guard is removed (mutation list).

```diff
diff --git a/tests/test_settings_form.py b/tests/test_settings_form.py
--- a/tests/test_settings_form.py
+++ b/tests/test_settings_form.py
@@ -484,3 +484,14 @@
     assert not uses_slider(FieldSpec("a", "A", "int", minimum=0))
     assert not uses_slider(FieldSpec("a", "A", "int", maximum=9))
     assert not uses_slider(FieldSpec("a", "A", "length", minimum=60, maximum=100))
+
+
+def test_a_widget_font_property_is_a_font_row_and_other_strings_stay_text():
+    class Props(WidgetProps):  # not ClockProps: widgets.clock imports gi, which CI does not have
+        font: Annotated[str, Field(min_length=1, max_length=100)] | None = None
+        format: str = "HH:mm"
+
+    section = props_section(Props)
+    assert section.field("font").kind == "font"
+    assert section.field("format").kind == "text"
+    assert config_form(WIDGETS).theme.field("font").kind == "fonts"  # the theme's list
diff --git a/tests/test_settings_fields.py b/tests/test_settings_fields.py
--- a/tests/test_settings_fields.py
+++ b/tests/test_settings_fields.py
@@ -601,3 +601,31 @@
     assert row.editor.scale.get_value() == 6 and not row.unsent()
     row.flush()
     assert changes == []
+
+
+def test_a_widget_font_row_picks_a_family_or_resets_to_the_theme_font(fonts):
+    spec = FieldSpec("font", "Font", "font")
+    changes, resets = [], []
+    row = fields.FieldRow(spec, ("p", "font"), lambda p, v: changes.append((p, v)), resets.append)
+    row.show_value(FieldValue(None, False, "widget default"))
+    picker = row.editor.picker
+    assert picker.label.get_text() == fields.THEME_FONT  # unset: the theme's font
+    picker.fill()
+    assert picker.visible_labels()[:2] == [fields.THEME_FONT, "Noto Sans (system font)"]
+    picker.search.set_text("fira")
+    picker.search.emit("activate")
+    assert changes == [(("p", "font"), "Fira Mono")] and resets == []
+    picker.fill()
+    picker.list.emit("row-activated", picker.list.get_row_at_index(0))  # "Theme font"
+    assert resets == [("p", "font")] and len(changes) == 1  # reset: nothing written
+    assert not row.unsent()
+
+
+def test_a_widget_font_that_is_not_installed_is_shown_and_kept(fonts):
+    row, changes, resets = row_for(FieldSpec("font", "Font", "font"), "Gone Font", is_set=True)
+    picker = row.editor.picker
+    picker.fill()
+    assert picker.label.get_text() == "Gone Font"
+    assert picker.visible_labels()[1] == "Gone Font (not installed)"
+    row.flush()
+    assert changes == resets == []
diff --git a/tests/test_settings_view.py b/tests/test_settings_view.py
--- a/tests/test_settings_view.py
+++ b/tests/test_settings_view.py
@@ -1320,6 +1320,44 @@
         for scroller in nb.get_children():
             width = scroller.get_child().get_preferred_width().minimum_width
             assert width <= 640, (page, nb.get_tab_label_text(scroller), width)
+
+
+def test_the_clock_and_corner_pages_fit_beside_the_tree_too(make_real, monkeypatch):
+    """The new inputs (sliders, the font pickers, the theme's font list) inside the 640 px of
+    a tab, on the pages that have them all: the Theme page, a clock panel (its Widget tab: a
+    font picker and a font size slider) and a corner panel."""
+    from settings import fontpicker
+    from settings.fields import FontEditor
+
+    long_name = "A Very Long Installed Font Family Name Indeed Bold Condensed"
+    monkeypatch.setattr(fontpicker, "installed_families", lambda: (long_name,))
+    view, path = make_real()
+    add(view, "clock")
+    add(view, "summary", "corner")
+    view.session.apply(lambda d: d.set(("theme", "font"), [long_name, "monospace"]))
+    view.rebuild()
+    clock = row(view, ("monitors", "HDMI-A-1", "panels", 1, "font"))
+    assert isinstance(clock.editor, FontEditor)
+    for page in ("theme", "panel:HDMI-A-1:1", "panel:HDMI-A-1:2"):
+        nb = notebook(view, page)
+        for scroller in nb.get_children():
+            width = scroller.get_child().get_preferred_width().minimum_width
+            assert width <= 640, (page, nb.get_tab_label_text(scroller), width)
+
+
+def test_the_mouse_wheel_edits_no_input_of_the_window(make_real):
+    """Every slider, spin button and combo of every page (and the toolbar) passes the wheel
+    to the page: a turn over any of them changes nothing and writes nothing."""
+    view, path = make_real()
+    add(view, "clock")
+    before = path.read_text()
+    inputs = [w for w in walk(view) if isinstance(w, (Gtk.Range, Gtk.SpinButton, Gtk.ComboBox))]
+    assert sum(isinstance(w, Gtk.Scale) for w in inputs) >= 20  # theme, monitor, clock pages
+    for widget in inputs:
+        event = Gdk.Event.new(Gdk.EventType.SCROLL)
+        event.scroll.direction = Gdk.ScrollDirection.UP
+        assert widget.emit("scroll-event", event) is False, widget
+    assert len(view.queue) == 0 and path.read_text() == before
 
 
 def test_a_rows_note_is_cut_with_its_whole_text_as_the_tooltip(make_real):
diff --git a/tests/test_settings_example.py b/tests/test_settings_example.py
--- a/tests/test_settings_example.py
+++ b/tests/test_settings_example.py
@@ -38,7 +38,7 @@
     clock = form.widget_props("clock")
     assert [(f.key, f.kind) for f in clock.fields] == [
         ("format", "text"),
-        ("font", "text"),
+        ("font", "font"),
         ("font_size", "int"),
     ]
     assert (clock.field("font_size").minimum, clock.field("font_size").maximum) == (6, 96)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `scripts/py -m pytest -q tests/test_settings_form.py tests/test_settings_fields.py tests/test_settings_view.py tests/test_settings_example.py`
Expected: `5 failed, 245 passed`: `test_a_widget_font_property_is_a_font_row_and_other_strings_stay_text` (`assert 'text' == 'font'`), the two widget font tests (`ValueError: no editor for field kind 'font'`), `test_the_clock_and_corner_pages_fit_beside_the_tree_too` (`ImportError: cannot import name 'FontEditor' from 'settings.fields'`) and `test_the_real_widgets_make_a_form_and_the_clock_has_its_widget_rows` (`('font', 'text')` against `('font', 'font')`).

- [ ] **Step 3: Implement**

```diff
diff --git a/settings/form.py b/settings/form.py
--- a/settings/form.py
+++ b/settings/form.py
@@ -28,7 +28,7 @@
 )
 
 FieldKind = Literal[
-    "color", "int", "bool", "enum", "fonts", "length", "widget", "deprecated", "text"
+    "color", "int", "bool", "enum", "fonts", "font", "length", "widget", "deprecated", "text"
 ]
 
 # Keys holding a #rrggbb / #rrggbbaa colour. The models check them with a field validator,
@@ -225,6 +225,8 @@
         return FieldSpec(kind="int", minimum=low, maximum=high, **common)
     if not text and key == "font" and first.get("type") == "array":
         return FieldSpec(kind="fonts", **common)
+    if text and key == "font" and first.get("type") == "string":
+        return FieldSpec(kind="font", **common)  # a widget's font: one family, unset = theme
     if first.get("type") == "string" and (text or key == "name"):
         return FieldSpec(kind="text", max_length=first.get("maxLength"), **common)
     raise ValueError(f"no form field for {key!r}: {prop}")
diff --git a/settings/fields.py b/settings/fields.py
--- a/settings/fields.py
+++ b/settings/fields.py
@@ -40,6 +40,8 @@
 
 Emit = Callable[[Any], None]
 _UNSHOWN = object()
+UNSET = object()  # an editor's "remove this key": the row resets it (the inherited value)
+THEME_FONT = "Theme font"  # a widget font row's inherited value
 
 
 def _same(a: Any, b: Any) -> bool:
@@ -356,6 +358,21 @@
         self._send([*self.fonts, next_font(self.fonts, fontpicker.system_family())])
 
 
+class FontEditor(_Editor):
+    """A widget's font (one family; unset: the theme's font): a searchable picker whose first
+    row is "Theme font"; picking it sends UNSET (the row resets the key: nothing is
+    written)."""
+
+    def __init__(self, emit: Emit):
+        self.picker = FontPicker(
+            lambda value: emit(UNSET if value is None else value), inherit_label=THEME_FONT
+        )
+        self.widget = self.picker.button
+
+    def set(self, value: str | None) -> None:
+        self.picker.set(value)
+
+
 class TextEditor(_Editor):
     """A line of text (a panel's name, a widget's text property): sent on Enter or when the
     entry loses focus."""
@@ -472,6 +489,8 @@
         return ChoiceEditor(spec.choices, emit, spec.labels, spec.disabled)
     if spec.kind == "fonts":
         return FontListEditor(emit)
+    if spec.kind == "font":
+        return FontEditor(emit)
     if spec.kind == "text":
         return TextEditor(emit, spec.max_length)
     if spec.kind == "length":
@@ -505,6 +524,7 @@
         super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
         self.spec, self.path = spec, path
         self._on_change = on_change
+        self._on_reset = on_reset
         self._on_queue = on_queue
         self._is_pending = is_pending or (lambda _path: False)
         self._updating = False
@@ -522,7 +542,7 @@
         self.source.get_style_context().add_class("dim-label")
         self.reset = Gtk.Button.new_from_icon_name("edit-undo-symbolic", Gtk.IconSize.BUTTON)
         self.reset.set_tooltip_text("Remove this key from your config (use the inherited value)")
-        self.reset.connect("clicked", lambda *_a: on_reset(path))
+        self.reset.connect("clicked", lambda *_a: self._on_reset(path))
         line.pack_start(name, False, False, 0)
         line.pack_start(self.editor.outer, False, False, 0)
         line.pack_start(self.source, True, True, 0)
@@ -577,6 +597,10 @@
     def _changed(self, value: Any) -> None:
         if self._updating or self._discarding:
             return
+        if value is UNSET:  # the editor's inherited row (a widget font's "Theme font")
+            self._shown = None
+            self._on_reset(self.path)
+            return
         if self.spec.kind in DEBOUNCED and self._on_queue is not None:
             self._on_queue(self.path, value, self._shown)  # the queue un-queues a change back
             return
```

- [ ] **Step 4: Run them to verify they pass, then VERIFY (twice)**

Run the command of Step 2: all pass. VERIFY: `2659 passed`. Then with GTK blocked (Global Constraints, VERIFY): `1916 passed, 36 skipped`; the 3 new skips are `test_settings_style.py`'s two GTK tests and `test_settings_fontpicker.py`.

- [ ] **Step 5: Commit**

```bash
git add settings/form.py settings/fields.py tests/test_settings_form.py tests/test_settings_fields.py tests/test_settings_view.py tests/test_settings_example.py
git commit -m "feat(settings): a widget's font is a font picker; the new inputs fit and ignore the wheel" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

**Reviewer mutation list:**
- `kind="text"` for the widget font → `test_a_widget_font_property_is_a_font_row_and_other_strings_stay_text` and `test_the_clock_and_corner_pages_fit_beside_the_tree_too` fail;
- drop the `UNSET` branch in `FieldRow._changed` → `test_a_widget_font_row_picks_a_family_or_resets_to_the_theme_font` fails (the sentinel would be written);
- no `inherit_label` in `FontEditor` → the same test fails;
- remove `wheel_scrolls_the_page(self.widget)` from `ChoiceEditor`, or from `IntEditor`, or the slider's guard → `test_the_mouse_wheel_edits_no_input_of_the_window` fails (the slider's also fails `test_the_mouse_wheel_never_edits_a_row`).

---

### Task 7: The docs, and the gate checklist for Phil

**Files:**
- Modify: `README.md` (Settings window: a new **Inputs** bullet; the queue bullet names sliders; the wheel sentence; a known limitation), `docs/superpowers/specs/2026-10-14-panel-widget-model-design.md` (section 8: an "Implemented" paragraph with the readings and the deviation of decision 5)

**Interfaces:** none (docs).

- [ ] **Step 1: Apply the docs diff**

```diff
diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -402,14 +402,28 @@
 - Each row shows the value in effect and where it comes from (`your config`, `default`,
   `global theme`, `widget default`, ...). The reset button removes the key from your file, so
   the value is inherited again.
-- Changes apply at once; the running shell reloads them like a hand edit. Spin buttons wait
-  0.4 s after the last change of any spin button, and one queue applies every change in the
-  order you made it: per setting only the last value counts, and a spin button changed and
-  changed back is not written at all. Anything still waiting is applied before a panel is
+- **Inputs.** A whole number with a minimum and a maximum at most 500 apart (thickness,
+  radius, peek, hover zone, border width, shadow elevation, handle size and weight, gap, a
+  widget's font size) is a slider with a spin button beside it for typing an exact value; both
+  show the same number. A focused slider takes the arrow keys, Page Up/Down, Home and End.
+  Wider ranges (duration, offsets, order, depth, lengths, a corner panel's width and height)
+  keep a spin button. Toggles are thin switches with a round knob. A dropdown opens below its
+  row (above when there is no room) with every entry shown. **Fonts**: a font button opens a list of the installed families
+  with a search field (type any part of a name; Enter picks the first match, a click any row);
+  the desktop's own font is first ("Noto Sans (system font)"), then `monospace`, `sans-serif`,
+  `serif`, then every family. The theme's font list has one such button per font (the first
+  installed one is used), with Move up, Move down and Remove, and **Add font** (it adds the
+  desktop's font). A widget's Font row (the clock) starts with **Theme font**: choosing it
+  removes the key, so the theme's font is used. A font in your file that is not installed is
+  shown as it is, listed as "NAME (not installed)", and kept.
+- Changes apply at once; the running shell reloads them like a hand edit. Spin buttons and
+  sliders wait 0.4 s after the last change of any of them (a drag writes once, after you stop),
+  and one queue applies every change in the order you made it: per setting only the last value
+  counts, and a value changed and changed back is not written at all. Anything still waiting is applied before a panel is
   added, moved or removed, before Undo, Save or leaving the config (New, Open, Close, Exit),
   and before Detect monitors; Revert all drops it. A change the shell would reject is not
   saved: the reason (with the key path) shows under the row. The mouse wheel scrolls the page
-  and never changes a value, so scrolling over a monitor's shell mode cannot switch it. If the file
+  and never changes a value (a slider, a spin button or a dropdown included). If the file
   is changed in an editor while changes are still waiting, they are not applied (they were made
   for the file before it changed, and panels are tracked by their place in the list) and the
   banner names them: "Not applied (made for the file before it changed):
@@ -484,6 +498,11 @@
   within 0.4 s are written together after the last change; at narrow widths the tabs scroll
   sideways; a right-click on a handle opens the window but not yet on that panel's page
   (follow-up).
+- Settings window, inputs: the font list is read once per window process (a font installed
+  while the window is open shows after it is reopened); an unset optional number (a widget's
+  font size) shows the slider's minimum, and its note says where the value comes from; the
+  theme's own default font list is unchanged (Hack Nerd Font Mono, JetBrains Mono, monospace):
+  the desktop font is offered first, not used by itself.
 - Settings window, editing limits: unsetting a whole table leaves that table's own label comment
   behind (not reachable from the window, which only resets single keys); after an edit a CRLF
   file may have `\n` endings on the lines the window writes (the session reads with universal
diff --git a/docs/superpowers/specs/2026-10-14-panel-widget-model-design.md b/docs/superpowers/specs/2026-10-14-panel-widget-model-design.md
--- a/docs/superpowers/specs/2026-10-14-panel-widget-model-design.md
+++ b/docs/superpowers/specs/2026-10-14-panel-widget-model-design.md
@@ -158,6 +158,8 @@
 - **Fonts**: a searchable dropdown (`Gtk.ComboBox` with entry completion, or a popover list with a search entry) over installed families (Pango font map, sorted, deduplicated); the unset state shows "System font" (resolved from `Gtk.Settings:gtk-font-name`) and writes nothing. The theme `font` list keeps its list editor with the same picker per entry.
 - **Dropdown sizing**: investigate first (a spike task: reproduce under a plain Gtk3 combo on Wayland/KDE, check popup size request vs `set_wrap_width`/`popup-fixed-width`/CSS `min-height` on menu items, `Gtk.ComboBoxText` vs a `Gtk.MenuButton` + popover). Deliver the smallest fix that opens a combo at the size of its content on first show; if it is a GTK quirk with no clean fix, replace the choice editor with a popover list (also used by the font picker).
 
+**Implemented (2026-10-16, `docs/superpowers/plans/2026-10-16-input-styles.md`; the live gate results follow):** with these readings (decisions in the plan): **dropdowns** keep `Gtk.ComboBoxText` with `wrap_width` 1: GTK 3.24 pops a combo's menu up over the combo with the active entry on it (wrap width 0), which on Wayland puts the menu above its anchor where the compositor shrinks it (GtkMenu then shows scroll arrows until a motion event); with a wrap width GTK anchors the menu below the combo; the size request was never the cause (`popup-fixed-width` and menu item `min-height` change nothing on that path); **toggles** are `Gtk.Switch` restyled by one class-scoped stylesheet (`settings/style.py`, USER priority, also holding the info note's colours): 38 x 22 px, a 16 px round knob (GTK's own floor for the switch's content), centred in the row (a switch stretched to the row's height made the knob a tall oval); **sliders**: an `int` with both bounds at most 500 apart (`SLIDER_MAX_SPAN`) is a 160 px `Gtk.Scale` and a spin button on one `Gtk.Adjustment`; wider ranges (duration 0-5000 ms, offsets, order, depth, lengths, corner sizes) keep the spin button; drags go through the edit queue (one write after the 0.4 s pause; a drag back writes nothing); the wheel never edits; **fonts**: a `Gtk.MenuButton` with a popover (a search entry above a list box, sized to its rows up to 360 px; a popover is drawn inside the window, not a compositor popup) over Pango's families (read once, aliases and CSS-unsafe names dropped, sorted without case), listing the desktop's font first ("NAME (system font)", from `gtk-font-name`), then `monospace`, `sans-serif`, `serif`, then the families; a configured font that is not installed is listed "NAME (not installed)" and kept; the theme's `font` list is one picker per entry with Move up, Move down, Remove and Add font (adds the desktop's font); a widget's `font` property (the clock) has a "Theme font" row that resets the key. Deviation: "the unset state shows System font and writes nothing" is not possible as written: an unset widget font is the theme's font, and the theme's `font` list is required and comes from `config.default.toml`; the desktop font is offered first and added by Add font instead (plan, open question 1).
+
 ## 9. Risks
 
 - The widget/panel refactor touches every widget and the panel classes; the existing 1881 tests are the safety net, and plan 1's first task is the registry and widget base class with the old widgets ported one by one.
```

- [ ] **Step 2: VERIFY** (record the real total; ruff skips `*.md`), then check that the README names what the code does: `grep -n "SLIDER_MAX_SPAN = 500" settings/form.py`, `grep -n "KNOB_PX = 16" settings/style.py`, `grep -n "POPUP_HEIGHT = 360" settings/fontpicker.py` each print one line.

- [ ] **Step 3: Commit**

```bash
git add README.md docs/superpowers/specs/2026-10-14-panel-widget-model-design.md
git commit -m "docs: input styles in the README and the spec" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 4: Hand the gate to Phil.** Report the branch, the commits and the checklist below. Nobody but Phil runs it.

#### Gate checklist (Phil, live, HDMI-A-1 only; DP-1 is never touched)

Setup: the shell running on HDMI-A-1 as usual (DP-1 keeps `shell = "plasma"`); `cp ~/.config/edge-shell/config.toml ~/.config/edge-shell/config.toml.gate4` first; open the window with `scripts/py main.py --settings` from the worktree. Everything below is on the **Theme** page, the **HDMI-A-1** monitor page or an **HDMI-A-1** panel page.

1. **Dropdowns open at their size.** What you saw before: a dropdown opened one entry high with a scrollbar, then grew to its entries on a mouse-over or a wheel turn. Open each of these, with the mouse kept still after the click: (a) Theme > Handle > Handle style > **Shape** (5 entries); (b) an HDMI-A-1 panel page > Position > **Edge** (4 entries; pick one whose value is not the first, e.g. `bottom`: that was the case where the active entry was laid over the combo); (c) the toolbar's **panel type** list (every type, "Float panel (coming soon)" greyed out); (d) a dock panel's Position > **Length** mode (px, fill, content, percent). Expected: each opens below its row (above it if the row is near the bottom of the screen) with every entry visible at once, no scroll arrows, no change of size when the mouse moves over it. Also expected: the list no longer opens with the current entry over the box (it opens below it; the current entry is highlighted).
2. **Toggles.** Theme > Borders > **Enabled**, Theme > Shadows > **Enabled**, a panel's Interaction > **Click / Hover / Drag**. Expected: a thin switch (about 38 x 22 px, thinner than before), vertically centred in its row, with a round knob (a circle, not an oval), in both positions; each row's label is level with its control (switch, slider, spin); the same with the window unfocused (click another window: Breeze's unfocused colours, same shape); colours as Breeze draws them.
3. **Slider drag.** Theme > General > **Thickness**: drag the slider from its value (e.g. 10) to 20 and release. Expected: the number beside it follows the drag; the shell's frame changes once, when you release the mouse button (not while the pointer moves or pauses); the row's note says "your config"; the file has `thickness = 20` under `[theme]`. Then drag it to 30 and, without stopping, back to 20 (the value in the file) and release: nothing is written (the file is unchanged, the frame does not move). Then press the row's Reset: the key goes and the note says "default" again.
4. **Slider keys and typing.** Click the Thickness slider (it gets the focus): Right arrow +1, Left −1, Page Up +6, Page Down −6 (Page Up raises), End → 64, Home → 2 (the frame follows each, after the pause). Type `12` in the spin button beside it and press Enter: 12. Type `abc` and press Tab: it goes back to the value (nothing written).
5. **The wheel edits nothing.** On the Theme page's General tab, scroll the wheel over the Thickness slider, its spin button, the Duration spin button, then on Handle the Shape dropdown, and over the font buttons: the page scrolls (when it can) and no value changes; the file is unchanged.
6. **Wide ranges keep spin buttons.** Theme > General > **Duration** (0-5000 ms), a panel's Position > **Offset**, **Depth**, **Order**: spin buttons as before. Handle > **Size**, **Weight**, Layout > **Gap**, Shadows > **Elevation**, Borders > **Width**: sliders.
7. **Font search by typing.** Theme > General > **Font**: click the first font's button. Expected: a list opens under it (inside the window) with a search field that has the focus, fitting its rows up to about 360 px and then scrolling. Type `mono`: only names containing "mono" (any case) remain (e.g. `monospace`, `JetBrains Mono`, `Hack Nerd Font Mono`). Press Enter: the first one is picked, the list closes, the button shows it, the shell's font changes. Open it again, type `jet`, click a row with the mouse: picked. Escape closes without a change.
8. **System font first.** Open any font list with an empty search: the first family row reads "Hack Nerd Font (system font)" (your KDE General font as GTK sees it: System Settings > Appearance > Fonts > General; if you change it there, a newly opened settings window shows the new one), then `monospace`, `sans-serif`, `serif`, then every family A-Z. **Add font** under the theme's list adds that system font at the end (if it is already listed: `monospace`, then `sans-serif`, `serif`).
9. **Unset against written (the clock).** On HDMI-A-1, add a clock with the toolbar (panel type "Clock (edge panel)", **Add**); its page opens: tab **Widget**. Expected: the **Font** row's button reads "Theme font" and the file's clock entry has no `font` key. Open the list: "Theme font" first (selected), then the system font, the generic families and the families. Pick `JetBrains Mono`: `font = "JetBrains Mono"` appears in the clock's entry and the clock changes. Open the list and pick "Theme font": the `font` line is removed from the file (nothing else written) and the clock goes back to the theme's font. The **Font size** row is a slider (6-96) showing 6 while unset (its note says "widget default"); move it: `font_size` is written; Reset removes it. Remove the clock afterwards (toolbar or tree Remove).
10. **A font that is not installed is kept.** In a text editor, set the theme's font list to `font = ["Not A Real Font", "monospace"]` under `[theme]` and save. The window re-reads it (banner). Expected: the first font button reads "Not A Real Font"; opening its list shows "Not A Real Font (not installed)" first and selected; Escape: the file is unchanged (still names it). The shell falls back to `monospace` for that entry as before.
11. **The font list's buttons.** With three fonts in the theme's list: Move down on the first moves it (the file's order follows), Move up on the last, Remove on the middle one. With one font left its Remove is greyed out. Add font adds a line. Undo (Ctrl+Z) steps back through each change. Keyboard focus stays on the moved font's button after Move; after the last Remove it goes to Add font; the Reset button beside the font list is small.
12. **Narrow window.** Make the window 860 px wide, then as narrow as it goes: on the Theme page's General tab (the font list), Borders and Handle tabs, and on the clock's Widget tab, at 860 px (the default) no tab scrolls sideways and every Reset button is on screen; at the narrowest width a horizontal scrollbar appears and the Reset buttons are reached by scrolling (expected and preferred over squeezing everything).
13. **DP-1 untouched.** Last: `grep -n -A3 'monitors.DP-1' ~/.config/edge-shell/config.toml` still shows `shell = "plasma"`, and Plasma's panel on DP-1 is unchanged. Restore your config if you like: `cp ~/.config/edge-shell/config.toml.gate4 ~/.config/edge-shell/config.toml`.

What only the gate can show (not testable headless): item 1 (the popup's place and size on KWin), the look of items 2 and 7 (colours, the circle as drawn by Breeze, the popover's position), the shell following the edits (items 3, 4, 7, 9), the real font list and system font (item 8).

---

### Task 8: Record the gate results

**Files:**
- Modify: `docs/superpowers/specs/2026-10-14-panel-widget-model-design.md` (section 8, after the "Implemented" paragraph)

**Interfaces:** none.

- [ ] **Step 1: Write the results.** When Phil has run the gate, add one paragraph after section 8's "Implemented" paragraph, in the form plan 3 used: `**Results (Phil, live on HDMI-A-1 only, DP-1 untouched, DATE):** ` then, for all items passed, "all 13 gate items passed" with Phil's own words in quotes; for an item that failed, its number, what Phil saw (his words), and what was done (the fix commit, or the follow-up plan named). If Gate item 1 fails, do not change code under this task: the follow-up is decision 1's contingency (the popover list), planned on its own.
- [ ] **Step 2: VERIFY** (record the real total).
- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-10-14-panel-widget-model-design.md
git commit -m "docs: record the input styles gate results" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

## Self-review

1. **Spec coverage (section 8, Phil's six points).** Colour picker: unchanged (`ColorEditor` untouched). Toggles: Task 2 (thinner, round knob; CSS scoped; states by priority; tested without a window, look in Gate item 2). Sliders for both bounds: Task 3 (`Gtk.Scale` + editable spin, debounce through the queue, wheel guard), the span rule (decision 3, open question 2). Fonts: Task 4 (searchable dropdown over Pango's families, sorted, deduplicated; desktop font from `gtk-font-name`), Task 5 (the theme list keeps a list editor with the same picker per entry), Task 6 (a widget's font; unset writes nothing). Dropdown sizing: Task 1 (investigation first, the smallest fix, what is headless and what is live; contingency named). Gate on HDMI-A-1, DP-1 untouched: Task 7. Deviation recorded: decision 5 (unset font semantics) in the plan and in the spec text of Task 7.
2. **Placeholder scan.** Every code step is a measured diff; every test step has its test code; the gate items name the row, the action and the expected result. Task 8's text is Phil's results, which do not exist yet: its form and the rule for a failed item are given.
3. **Type consistency.** `opens_below(combo)` (T1) used by `ChoiceEditor` and `LengthEditor`; `SWITCH_CLASS`, `KNOB_PX`, `BORDER_PX`, `TRACK_PADDING_PX`, `install_css` (T2) used by `BoolEditor` and the tests; `uses_slider(spec)`, `SLIDER_MAX_SPAN` (T3) used by `make_editor`; `_Editor.outer` packed by `FieldRow`; `FontPicker(on_pick, families=None, system=None, inherit_label=None)` (T4) used by `_FontLine` (T5) and `FontEditor` (T6); `picker_entries`, `matches`, `first_match`, `next_font`, `GENERIC_FAMILIES` match between `settings.fonts`, the picker and the tests; `UNSET` and `THEME_FONT` (T6) only in `settings.fields`.
4. **Review Focus.** Each of the five lines has its pinning tests in the owning task (Tasks 3, 3+6, 4+6, 5, 6) and a gate item.

## Open questions for Phil (each with the default this plan uses)

1. **"Default should be the system selected font": what should be the default?** The plan offers the desktop's font first in every font list and adds it with Add font; an unset font stays what the config model says (a widget: the theme's font; the theme: `config.default.toml`'s list), and "Theme font" resets a widget's font. **Recommended default: as planned.** If you meant that the shell itself should use the KDE font unless told otherwise, say so: a follow-up task adds a `system-ui` entry the shell resolves to your KDE font (and, if you want, puts it first in the shipped default list); your shell's font would then change with System Settings.
2. **Which numbers get a slider?** The plan: both bounds and a range of at most 500 (theme sizes, border width, shadow elevation, handle size/weight, gap, the clock's font size); duration (0-5000 ms), offsets, order, depth, lengths and corner sizes keep spin buttons. **Recommended default: as planned.** Alternatives: every bounded number (a 160 px slider over 0-5000 ms moves about 30 ms per pixel; the spin beside it still types exact values), or a smaller limit (e.g. 100: gap 0-400 would keep its spin button).
3. **Toggle size.** 38 x 22 px with a 16 px knob (GTK 3 draws no smaller switch content than 32 x 16). **Recommended default: as planned.** A thinner track with a knob that sticks out above and below it needs a custom-drawn toggle (about one task).
4. **If the dropdown fix does not hold live (Gate item 1):** replace every dropdown with a popover list like the font picker's (no search field), about one task, or first try the deprecated `appears-as-list` list style (a few lines, a different look). **Recommended default: the popover list**, the same widget as the font picker, which the compositor cannot resize.
5. **An unset optional number with a slider** (the clock's Font size, unset = the theme's size) shows the slider's minimum (6), as a spin row did. **Recommended default: as planned.** Alternative: an empty spin field with "theme" as its placeholder (a few lines and two tests).
