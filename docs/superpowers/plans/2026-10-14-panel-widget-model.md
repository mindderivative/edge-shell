# Panel/Widget Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every panel entry say what it is (`panel = "edge" | "corner" | "float"`, a unique `name`, a registered `widget` and that widget's own properties in the same table), turn the built-in widgets into `Widget` classes that the `EdgePanel` / `CornerPanel` windows host instead of subclass, give the clock `format`, `font` and `font_size`, and keep the shell, the hot reload and the settings window working on the new model (plan 1 of the panel/widget spec).

**Architecture:** The config model grows first and stays green: Task 1 adds `panel`, `name` and a `widget_props` bag to `PanelConfig` (still optional), and `registry.validate_widgets` learns the new rules; Task 2 converts every example and test config (a one-off script plus a short list of hand fixes) and makes `panel` and `name` required, with an "old format" message and the settings window writing `{panel, name, widget}`. Task 3 replaces the registry API (`register_widget` with a title, a `WidgetProps` model and per-kind defaults; `request_for` by `cfg.panel`; requests carry `name` and the validated props). Task 4 makes the panel windows host a `Widget` (the single `build_content` seam now calls `widget.build(props)`; the window's destroy calls `widget.destroy()`), ports the four widgets and renames `widget_panel` to `summary`. Task 5 makes `MonitorShell` rebuild a panel whose name or props changed and contain a widget build failure (log, notify by name, skip the panel). Task 6 adds the clock properties with a fixed format-token table (`services/clock_format.py`, never strftime on user text). Tasks 7-8 adapt the settings window (form rows from each widget's property model, `name` and `panel` rows, compound edits, titles by name). Task 9 documents it and adds the gate example; Tasks 10-11 are Phil's live gate and the recorded results.

**Tech Stack:** Python 3.14 (>=3.12), PyGObject 3.50 (`<3.52`), GTK 3, Fabric 0.0.2 (shell side), Pydantic 2, tomlkit 0.15.1 (settings window), pytest, ruff 0.17.0.

**Spec:** `docs/superpowers/specs/2026-10-14-panel-widget-model-design.md`, sections 3.1-3.8 (this plan), 4 (data flow and errors) and 5 (testing); sections 6-8 are plans 2-4 and are not in this plan. Background: `docs/superpowers/specs/2026-10-11-edge-shell-design.md` sections 5.3 (monitor modes), 6 (config, live reload table), 15-19 (handles, layout, corner panels). Closest previous plans for style and depth: `docs/superpowers/plans/2026-10-14-corner-panel.md`, `docs/superpowers/plans/2026-10-14-settings-window.md`.

**Phil's decisions (from the spec, not re-opened here):** panel entry = `panel` (edge | corner | float, required), `name` (required, 1-40 characters, unique per monitor), `widget` (a registered id), the kind's keys, and the widget's keys flat in the same table, validated by the widget's pydantic model; no aliases and no migration tool (Phil has no saved configs; examples and tests are converted); `float` is accepted by the schema and rejected by validation ("float panels are not implemented yet"); `widget_panel` is renamed `summary`; widgets stop subclassing `EdgePanel` / `CornerPanel` and become `Widget` classes (`build(props)`, `destroy()`) registered with `register_widget(id, title=, props=, edge=PanelDefaults|None, corner=CornerDefaults|None)`; the clock gets `format`, `font`, `font_size` with a FIXED token table (`HH mm ss H h a ddd dd MMM MM yyyy`, anything else is a validation error, user text never reaches strftime); `shell` stays four-valued (no config change); a change of `panel`, `widget`, `name` or any widget property is a `panel-rebuild`; the settings window is adapted inside this plan (spec 3.7), its layout redesign is not.

**Date:** 2026-10-14. **Size:** 11 tasks: 8 code tasks (1-8), docs and the gate example (9), Phil's live gate (10), recorded results (11). Riskiest: Task 2 (it touches about 280 test configs at once; the conversion is a script whose output was checked byte for byte against the prototype), Task 5 (the only change to how live panels are built and rebuilt), Task 7 (the form's rows now come from two schemas).

## Decisions taken while planning

Phil answered the first draft's open questions "all as recommended" (2026-10-14); his answers are folded in below and marked *Phil's answer*, and the last section lists them.

1. **The required flip waits for the conversion.** Task 1 adds `panel` and `name` as optional keys with every new rule applied when they are present; Task 2 converts the examples and tests and makes both required in the same commit. *Why:* the suite stays green after every task and Task 1 stays reviewable on its own. *Cost if Phil prefers one step:* Tasks 1 and 2 merge (one large commit).
2. **The widget-key bag is `PanelConfig.widget_props`, filled by a `mode="before"` validator.** Every key that is not in `FRAMEWORK_KEYS` (`SHARED_KEYS + EDGE_ONLY_KEYS + CORNER_ONLY_KEYS`) goes there, a key literally called `widget_props` too (in a file it can only be a widget key, which the widget then rejects as unknown). `extra="forbid"` stays on the model. `Config.model_json_schema()` therefore shows `widget_props` as a plain object; the settings form skips it and reads each widget's own model from the registry (`settings.form.registry_widgets`, `ConfigForm.widget_props(widget_id)`), as spec section 9 foresees. *Cost:* none beyond the spec.
3. **Where each rule is checked.** The model (pure, no registry): `panel` is one of the three kinds, `name` 1-40 characters without control characters (Unicode category Cc) and without leading or trailing whitespace (rejected: "must not start or end with whitespace", never trimmed; Phil's answer), the old mix-of-kinds rule. `registry.validate_widgets` (needs the registry): float, unknown widget, a kind the widget does not support (`clock cannot be shown in a corner panel (it supports: edge)`), the kind's keys (`monitors.X.panels[0].align: a corner panel takes corner, edge, width and height, not align`; `...width: an edge panel takes no width; corner, width and height only apply to corner panels`), the widget's keys against its model (`format: unknown key for widget 'dock'`, or pydantic's own text for a bad value) and duplicate names (`monitors.X.panels[3].name: names must be unique: 'Clock' is used by panels[0] and panels[3]`; case-sensitive). `register_widget` (at import): the property names and types (decision 10).
4. **Every panel error writes the entry's index in brackets** (Phil's answer): the loader formats pydantic error locations with `shell.config.loader.key_path`, which writes `panels[0]` as `validate_widgets` does (`monitors.HDMI-A-1.panels[0].panel: missing; use "edge", "corner" or "float"`, `monitors.HDMI-A-1.panels[0].length: ...`); other lists keep their dots (`theme.font.0`), and layout warnings and log lines (`monitors.X.panels.1 (dock): ...`, the `pos` / all-off INFO lines) are not errors and keep theirs. A missing `panel` adds ONE extra line per file naming the old format. Three existing test expectations change (Task 2).
5. **Requests carry the props as the validated, frozen `WidgetProps` instance** (pydantic `frozen=True`, so it compares by value and cannot be changed: the spec's "frozen mapping"); `PanelRequest` and `CornerRequest` get `name: str = ""` and `props: WidgetProps = NO_PROPS` (defaults keep every positional constructor in the tests working). `diff_configs` needs no change: `_in_place` drops only state, handle and interaction, so a name or props change is already `panel-rebuild`.
6. **`MonitorShell` must rebuild on a name or props change.** Found while prototyping: `_sync_panels` rebuilds only when the resolved geometry changed, so a renamed clock or a new `format` was reported as `panel-rebuild` and then silently kept the old window. Task 5 keeps a per-index `(name, props)` next to the geometry and rebuilds when it differs.
7. **A widget build failure** (the widget's constructor, `build()`, or the panel window around it) is caught in `MonitorShell._new_panel`: logged with the traceback, the canvas shape removed, the half-built window destroyed (`EdgePanel.__init__` destroys itself if `build_content` raises), the panel left out (`None`, like a panel the layout hides) and the message `HDMI-A-1: panel 'Top clock' (clock) could not be built and is not shown: <error>` added to `shell.build_failures`. The app notifies "Panel not shown" when a monitor's failure list changes (not on every reload). **The panel is not tried again on every re-sync** (Phil's answer): `MonitorShell._failed` remembers the entry it failed for (`_entry_key`: kind, widget, name, props) and skips it, still listing its message, until a reload changes one of those; a move (a resolution change, a neighbour, `depth`) does not retry. A failure that is not a panel build (the layout itself) still closes the monitor as before.
8. **The clock format grammar.** Longest token first (`MMM` before `MM`, `ddd` before `dd`); text in single quotes is literal, letters included (`HH 'at' mm`); two single quotes (`''`) are one literal quote, inside or outside quoted text; a quote that is never closed is an error naming its position (Phil's answer); any other ASCII letter is an error naming it and its 1-based position; every other character (digits, spaces, punctuation, `%`, non-ASCII) is literal text. Formatting is done per token from the `datetime` fields (`ddd` / `MMM` use the fixed strftime codes `%a` / `%b`, locale abbreviations); literal and quoted text never reaches strftime. `format` 1-64 characters.
9. **Clock font and size** go into a `Gtk.CssProvider` on the clock's label at priority `STYLE_PROVIDER_PRIORITY_USER + 1` (Fabric adds the app stylesheet at USER, so the label's own rule wins), CSS from the pure `shell.theme.label_font_css(font, size)`. `font` is checked by the theme's font-name rule, now public as `shell.config.models.check_font_name`; `font_size` is in points, 6-96, emitted as `pt` (Phil's answer; GTK draws 12 pt as 16 px, so the old 20 px clock text is 15 pt). The settings row's hint says "pt". Unset = the theme's font and size.
10. **Settings form and property types.** `config_form(widgets: tuple[WidgetChoice, ...])` (`WidgetChoice(id, title, kinds, props)`; `registry_widgets()` builds them). A widget property's row comes from its JSON-schema type alone (str: a text row; int with bounds: a spin button; a Literal of strings: a combo; bool: a switch; each also `| None`) with its `Field(description=...)` as the hint; the config's name-based rules (colour keys, `length`, `pos`, the `font` list) do not apply there (found while prototyping: a property called `text` became a colour row). Anything else (a float, a list, a dict, a Literal of numbers, a union of two types, a nested model) has no row: the form raises, and **`register_widget` refuses it at import** with a ValueError naming the widget and the property (Phil's answer; `registry.form_type_ok`, `FORM_TYPES = (str, int, bool)`). A test (Task 7) checks that the registry and the form agree type by type. `name` is a text row; `panel`, `name` and `widget` have no reset button (`FieldSpec.required`). The Panel type row is shown only for a widget of more than one kind, with every kind listed and the unsupported ones (always `float`) greyed out and never sent. The add list and the widget row show titles, sorted by title (the "(corner panel)" suffix goes; Phil kept this).
11. **How the tests are converted (Task 2).** A one-off AST script (not committed) gives every dict literal and `PanelConfig(...)` call with a `widget` key, and every TOML string with a `widget = ` line, a `panel` (corner for `box`, `side`, `widget_panel`, `summary`, else edge) and a `name` equal to the widget id, numbered within the same list, call or string (`dock`, `dock 2`), so names are unique per monitor and an unchanged entry keeps its name in before/after pairs. `tests/test_settings_document.py` is not converted (it edits text that is never validated); its `add_panel` calls pass `{"widget": ...}`. About twenty hand fixes follow (a second script, in Task 2). The examples are rewritten by hand with readable names.
12. **Renames.** `widgets/widget_panel.py` becomes `widgets/summary.py` (`SummaryWidget`, title "Summary" (Phil's answer; new panels are named `Summary`, `Summary 2`, like `Dock`, `Clock`, `System bar`), CSS ids `#summary` / `#summary-time` instead of `#widget-panel` / `#widget-panel-time`); `tests/test_widget_panel.py` becomes `tests/test_summary.py`.
13. **The pure clock grammar lives in `services/clock_format.py`**, not in `widgets/`: importing anything under `widgets/` imports Fabric, and CI runs the pure tests without it.

## Prerequisites

- Branch `feat/panel-widget-model` in the worktree `/home/phil/Projects/pyDev/projects/myShell/.claude/worktrees/feat-edge-shell-core`, stacked on `feat/settings-window`; HEAD `8b2e525` ("docs: spec for the panel/widget model and the settings window redesign"). Check: `git log --oneline -1` prints `8b2e525 ...`.
- Baseline: `scripts/py -m pytest -q` prints `1881 passed` (GLib/asyncio deprecation warnings are normal); `scripts/py -m ruff check .` prints `All checks passed!`; `scripts/py -m ruff format --check .` reports every file formatted.
- tomlkit is installed in the shared venv (`scripts/py -c 'import tomlkit; print(tomlkit.__version__)'` prints `0.15.1`). If not, STOP and report: the settings tests would skip and a skip must not read as green. Nobody installs packages (Phil does).
- A display is available for the GTK tests (they build plain widgets, never a window). Without one, `tests/test_settings_fields.py`, `tests/test_settings_panels.py` and `tests/test_settings_view.py` skip as whole modules and the totals below are lower; report that instead of comparing.

## Global Constraints

- Python only through `scripts/py` (shared venv `/home/phil/Projects/pyDev/pyEnvs/global-base`; override with `EDGE_SHELL_PYTHON`). **PyGObject must stay `<3.52`.**
- **Pure modules import no GTK / `gi`:** `shell/config/*` (except `watcher.py`), `shell/registry.py`, `shell/panel_spec.py`, `shell/panel_layout.py`, `shell/theme.py`, **`shell/widget.py` (new)**, **`services/clock_format.py` (new)**, `settings/form.py`, `settings/values.py`, `settings/files.py`, `settings/document.py`, `settings/session.py`.
- **Monitor is an INT** for Fabric windows (`monitor_index`); this plan creates no new window class. Keep `EdgePanel.do_size_allocate`'s input-shape re-apply, the delayed `raise_to_top` workaround (`RAISE_DELAY_MS`, `RAISE_FALLBACK_MS`) and every attribute `_update_input_region` reads set before `_d`.
- **Font names go unescaped into generated CSS:** every font name (theme list or widget property) passes `check_font_name` (no `"`, `\`, `{`, `}`, `;`).
- **User text never reaches strftime** (the clock's `format` is tokenised by `services/clock_format.py`).
- **Tests.** CI installs only pycairo, pydantic, tomlkit, pytest and ruff: tests importing `gi` or `fabric` start with `pytest.importorskip("gi")` / `pytest.importorskip("fabric")`; settings tests that need tomlkit keep their `pytest.importorskip("tomlkit")`. GTK tests skip unless `Gtk.init_check()[0]` and **never create a window**: plain widgets and the `SettingsView` box only. Never call `Gtk.Application.run`.
- **Lint.** ruff 0.17.0, line length 100, rules E, F, I, UP, B; `docs/` and `*.md` excluded.
- **VERIFY** (before every commit): `scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q`. The suite must be green at the end of EVERY task (0 failed, 0 errors). Apply the edits of a step in the order written; when a step has several edits to one file, run `scripts/py -m ruff format .` after the step (a later step's "replace" text assumes formatted code).
- **Git.** Plain separate git commands run from the worktree (no `cd ... && git`, no command substitution around git). Stage files by name, never `git add -A` / `git add .`. **Never push.** Every commit message ends with a second `-m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`.
- **Live runs.** Phil is the only visual tester, on `HDMI-A-1` only. **Never touch `DP-1`** (it holds the Plasma panel: never set it to `edge` or `both`, in a file or in the window). Subagents executing tasks never launch the shell or the settings window (`main.py` without `--list-outputs`, including `--settings`); headless commands are fine (`pytest`, `scripts/py -m shell.canvas.simulate --config ...`, which imports the widgets but creates no window).

## Review Focus

The five input classes or failure modes most likely to bite Phil that the spec implies but a happy-path test would not catch, most likely first, each pinned by a test in the owning task:

1. **A rename or a property change on a panel whose place did not change** (a new clock `format`, a new `name`, from the window or a hand edit). The diff says `panel-rebuild`, but `MonitorShell._sync_panels` used to compare only geometry, so the old window stayed with the old text. Expect that panel, and only it, rebuilt in place. Pinned by `test_a_name_or_property_change_rebuilds_the_panel_in_the_same_place` and `test_an_unchanged_entry_is_not_rebuilt` (Task 5), `test_a_name_or_property_change_rebuilds_the_panel` (Task 3, the diff kinds).
2. **A widget whose build raises** (a bug, a missing icon, a bad font at runtime). Expect the frame and every other panel on that monitor to stay, the half-built window destroyed, one "Panel not shown" notification that names the panel, no retry on every re-sync, and a retry when a reload changes that entry. Pinned by `test_a_panel_that_fails_to_build_is_left_out_and_named`, `test_a_failed_panel_is_not_retried_by_a_relayout_only_by_an_entry_change`, `test_a_failure_while_the_monitor_is_built_keeps_the_frame`, `test_panels_that_could_not_be_built_are_notified_by_name_once`, `test_a_build_that_fails_destroys_the_half_built_window` (Task 5).
3. **A clock format or font that is really an injection** (`%Y`, `%n`, `%%`, `'%Y'` in quotes, an unclosed quote, a font name with `"; } * {`). Expect a validation error naming the key, or the characters shown literally; never strftime on user text, never broken CSS. Pinned by `test_strftime_sequences_are_plain_text`, `test_quoted_text_is_shown_as_written`, `test_an_unterminated_quote_is_an_error`, `test_any_other_letter_is_an_error_naming_it` (Task 6), `test_bad_properties_are_refused` and `test_bad_properties_name_the_key_path_in_a_config` (Task 6).
4. **An old-format file** (an earlier gate copy under `/tmp`, a hand-written entry with only `widget`). Expect "Config not applied" with one line per entry (`...panels[0].panel: missing; use "edge", "corner" or "float"`) plus ONE line naming the old format, and the previous layout kept. Pinned by `test_an_entry_without_panel_names_the_new_format` and `test_a_panel_index_is_written_in_brackets` (Task 2); every example file by `test_every_example_is_valid` (Task 2).
5. **Switching a panel's widget or kind in the settings window** (a clock with `format` turned into a dock, a two-kind widget moved to a corner, a duplicate name typed in). Expect one write that the shell accepts: the old widget's keys and the old kind's keys removed, the name kept; float and a duplicate name refused under their rows, nothing written. Pinned by `test_a_new_widget_drops_the_old_widgets_keys`, `test_a_new_panel_type_drops_the_old_kinds_keys`, `test_a_panel_type_the_widget_cannot_take_is_a_plain_set_for_the_session` (Task 7), `test_switching_the_widget_drops_its_property_keys_in_one_write`, `test_the_panel_type_of_a_two_kind_widget_is_switched_in_one_write`, `test_a_name_used_twice_is_not_written` (Task 8).

Also pinned (registration mistakes fail at import, before any window): a widget property named like a panel key (`edge`, `widget_props`), a property without a default, a property type the settings window cannot show, a bad title (`test_a_bad_registration_fails_at_import`, `test_a_property_the_settings_window_cannot_show_is_refused`, Task 3); a name with a leading or trailing space (`test_a_bad_name_names_the_key_path`, Task 1).

## File Structure

```
shell/config/models.py      # panel, name, widget_props on PanelConfig; FRAMEWORK_KEYS, PANEL_KINDS,
                            #   check_panel_name (T1); required (T2); check_font_name public (T6)
shell/config/loader.py      # key_path (panels[0]), the missing-panel message and the old-format line (T2)
shell/widget.py             # NEW, PURE: WidgetProps, NO_PROPS, Widget (T3)
shell/registry.py           # validate_widgets rules (T1, T2); register_widget, WidgetInfo,
                            #   widget_title, widget_props_model, supported_kinds, defaults(id, kind), form_type_ok,
                            #   widget_props, request_for by cfg.panel (T3; widget_kind removed)
shell/panel_spec.py         # PanelRequest / CornerRequest gain name and props (T3)
shell/edge_panel.py         # hosts a Widget: widget/props kwargs, build_content delegates,
                            #   _on_destroy (T4); destroys itself if the build raises (T5)
shell/corner_panel.py       # docstring only (T4)
shell/monitors.py           # panel_class(geo), the widget instance (T4); rebuild on name/props,
                            #   build_failures, no retry until the entry changes (T5)
shell/app.py                # "Panel not shown" notification (T5)
shell/theme.py              # #summary-time (T4); label_font_css (T6)
services/clock_format.py    # NEW, PURE: TOKENS, parse_clock_format, format_clock (T6)
widgets/dock.py, widgets/clock.py, widgets/system_bar.py   # Widget classes (T3 decorator, T4 port);
                            #   ClockProps and the clock's properties (T6)
widgets/widget_panel.py -> widgets/summary.py   # id "summary" (T2), SummaryWidget (T4)
widgets/__init__.py         # imports summary (T4)
settings/document.py        # add_panel(monitor, entry: dict) (T2)
settings/values.py          # panel_ops sets panel; unique_name, new_panel_entry (T2); registry
                            #   API (T3); name/panel/property values, panel and widget ops (T7)
settings/panels.py          # add writes {panel, name, widget} (T2); kind from the request (T3);
                            #   titles by name, Panel type row, Widget frame (T8)
settings/form.py            # skip new keys (T1); kind wording (T3); WidgetChoice, registry_widgets,
                            #   text rows, required, disabled, widget sections, strict types (T7)
settings/fields.py          # TextEditor (T7); disabled choices, no reset on required rows (T8)
settings/view.py            # registry kinds (T3); config_form(registry_widgets()) (T7); TITLE_KEYS (T8)
examples/*.toml             # converted (T2); examples/widget-props-test.toml NEW (T9)
README.md, docs/superpowers/specs/*.md   # T9, T11
tests/test_panel_entry.py, tests/test_examples.py, tests/test_widget_registry.py,
tests/test_clock_format.py  # NEW (T1, T2, T3, T6)
tests/test_widget_panel.py -> tests/test_summary.py (T4)
tests/conftest.py and about 30 test files   # converted (T2), registry API (T3)
```

| Task | Deliverable | `pytest -q` (tomlkit, display) | Keeps the suite green because |
| --- | --- | --- | --- |
| 1 | `panel`, `name`, widget keys in the model; validation rules | 1905 (+24) | the new keys are optional |
| 2 | every example and test converted; `panel`, `name` required; bracket paths; window writes the new entry | 1922 (+17) | conversion and flip in one commit |
| 3 | `register_widget`, per-kind defaults, props models and types, requests with name/props | 1960 (+38) | the old widgets keep their panel classes under the new decorator |
| 4 | panel windows host `Widget`s; widgets ported; `summary` module | 1969 (+9) | `build_content` stays the one seam |
| 5 | rebuild on name/props; build failures contained, notified, retried only on an entry change | 1977 (+8) | a failure that used to raise is now contained |
| 6 | clock `format` (token table, quoted text), `font`, `font_size` (pt) | 2019 (+42) | new properties default to today's look |
| 7 | form and values: name/panel rows, widget rows, compound edits, text rows, types in sync with the registry | 2043 (+24) | the window builds the same pages plus the new rows |
| 8 | panel list: titles by name, Panel type row, Widget frame, disabled float | 2052 (+9) | GTK details on top of Task 7 |
| 9 | README, spec sections 6/19/20, `examples/widget-props-test.toml` | 2053 (+1) | the example test gains one file |
| 10 | Gate (Phil, HDMI-A-1) | 2053 | no code |
| 11 | gate results recorded | real total | docs only |

Every total above was measured in a scratch copy of the branch with every step of this plan applied in order (and `ruff check` / `ruff format --check` clean after each task).

---
### Task 1: `panel`, `name` and the widget keys in a panel entry

The model learns the three new things a panel entry carries and `validate_widgets` the rules that need the registry. Both new keys stay optional until Task 2 converts every config; every rule applies as soon as the key is present.

**Files:**
- Modify: `shell/config/models.py` (the key sets, `PanelConfig`)
- Modify: `shell/registry.py` (`_kind_problems` wording, `validate_widgets`)
- Modify: `settings/form.py` (`config_form`: no rows for the new keys yet)
- Create: `tests/test_panel_entry.py`
- Modify: `tests/test_config_corner.py`, `tests/test_corner_requests.py`, `tests/test_settings_form.py`

**Interfaces:**
- Consumes: `PanelConfig`, `_Strict`, `SHARED_KEYS`, `EDGE_ONLY_KEYS`, `CORNER_ONLY_KEYS` (`shell/config/models.py`); `registry._DEFAULTS`, `registry.widget_kind`, `registry._kind_problems` (still the old registry); fixtures `fake_registry`, `corner_registry`, `make_config` (`tests/conftest.py`).
- Produces: `shell.config.models.SHARED_KEYS == ("panel", "name", "widget", "edge", "state", "handle", "interaction")`; `FRAMEWORK_KEYS: frozenset[str]` (every panel key); `PanelKind = Literal["edge", "corner", "float"]`; `PANEL_KINDS == ("edge", "corner", "float")`; `PanelName` (str, 1-40); `check_panel_name(value: str) -> str` (ValueError on a control character, or on whitespace at the start or end: `must not start or end with whitespace (a space, a no-break space, ...)`); `PanelConfig.panel: PanelKind | None`, `PanelConfig.name: PanelName | None` (required from Task 2), `PanelConfig.widget_props: dict[str, Any]` (every non-framework key). `registry.validate_widgets` reports, in `monitors.X.panels[i].<key>` form: `float panels are not implemented yet`, `<widget> cannot be shown in a(n) <kind> panel (it supports: <kind>)`, `<key>: unknown key for widget '<widget>'`, `names must be unique: '<name>' is used by panels[a] and panels[b]`, and the reworded kind-key messages.

- [ ] **Step 1: Write the failing tests**

In `tests/test_config_corner.py` replace

```python
def test_the_key_sets_partition_the_panel_keys():
    """The settings window shows SHARED_KEYS plus the keys of the widget's kind."""
    assert SHARED_KEYS == ("widget", "edge", "state", "handle", "interaction")
    assert CORNER_ONLY_KEYS == ("corner", "width", "height")
    keys = SHARED_KEYS + EDGE_ONLY_KEYS + CORNER_ONLY_KEYS
    assert len(set(keys)) == len(keys) and set(keys) == set(PanelConfig.model_fields)


```

with

```python
def test_the_key_sets_partition_the_panel_keys():
    """The settings window shows SHARED_KEYS plus the keys of the widget's kind."""
    assert SHARED_KEYS == ("panel", "name", "widget", "edge", "state", "handle", "interaction")
    assert CORNER_ONLY_KEYS == ("corner", "width", "height")
    keys = SHARED_KEYS + EDGE_ONLY_KEYS + CORNER_ONLY_KEYS
    assert len(set(keys)) == len(keys)
    assert set(keys) | {"widget_props"} == set(PanelConfig.model_fields)


```

In `tests/test_corner_requests.py` replace

```python
        (
            {"widget": "box", "align": "end"},
            "monitors.HDMI-A-1.panels[0].align: box is a corner panel; it takes corner, edge, "
            "width and height, not align",
        ),
        (
```

with

```python
        (
            {"widget": "box", "align": "end"},
            "monitors.HDMI-A-1.panels[0].align: a corner panel takes corner, edge, width and "
            "height, not align",
        ),
        (
```

In `tests/test_corner_requests.py` replace

```python
        (
            {"widget": "dock", "width": 300},
            "monitors.HDMI-A-1.panels[0].width: dock is an edge panel; corner, width and height "
            "only apply to corner panels",
        ),
        (
            {"widget": "clock", "corner": "top-left"},
            "monitors.HDMI-A-1.panels[0].corner: clock is an edge panel",
        ),
    ],
```

with

```python
        (
            {"widget": "dock", "width": 300},
            "monitors.HDMI-A-1.panels[0].width: an edge panel takes no width; corner, width and "
            "height only apply to corner panels",
        ),
        (
            {"widget": "clock", "corner": "top-left"},
            "monitors.HDMI-A-1.panels[0].corner: an edge panel takes no corner",
        ),
    ],
```

Create (or replace entirely) `tests/test_panel_entry.py`:

```python
"""A panel entry's own keys (panel/widget spec 3.1-3.2): panel, name and the widget keys."""

import pytest
from pydantic import ValidationError

from shell.config.models import (
    FRAMEWORK_KEYS,
    PANEL_KINDS,
    Config,
    ConfigError,
    PanelConfig,
)


def mon(*panels):
    return {"HDMI-A-1": {"shell": "edge", "panels": list(panels)}}


def problems(registry, make_config, *panels) -> str:
    with pytest.raises(ConfigError) as exc:
        registry.validate_widgets(make_config(monitors=mon(*panels)))
    return str(exc.value)


def test_the_panel_kinds_are_edge_corner_and_float():
    assert PANEL_KINDS == ("edge", "corner", "float")
    assert PanelConfig(panel="corner", name="Box", widget="box").panel == "corner"
    with pytest.raises(ValidationError) as exc:
        PanelConfig(panel="side", name="Box", widget="box")
    assert exc.value.errors()[0]["loc"] == ("panel",)


@pytest.mark.parametrize("name", ["Clock", "x", "C" * 40, "Uhr · oben", "Dock 2"])
def test_a_name_may_be_any_text_of_1_to_40_characters(name):
    assert PanelConfig(panel="edge", name=name, widget="dock").name == name


@pytest.mark.parametrize(
    ("name", "words"),
    [
        ("", "at least 1 character"),
        ("C" * 41, "at most 40 characters"),
        ("Clock\n", "control characters"),
        ("a\tb", "control characters"),
        (" Clock", "must not start or end with whitespace"),
        ("Clock ", "must not start or end with whitespace"),
        ("\u00a0Clock", "must not start or end with whitespace"),  # a no-break space too
    ],
)
def test_a_bad_name_names_the_key_path(make_config, name, words):
    with pytest.raises(ValidationError) as exc:
        make_config(monitors=mon({"panel": "edge", "name": name, "widget": "dock"}))
    error = exc.value.errors()[0]
    assert error["loc"] == ("monitors", "HDMI-A-1", "panels", 0, "name")
    assert words in error["msg"]


def test_every_other_key_is_a_widget_key():
    p = PanelConfig.model_validate(
        {"panel": "edge", "name": "Clock", "widget": "clock", "edge": "top", "format": "HH:mm"}
    )
    assert p.widget_props == {"format": "HH:mm"}
    assert (p.edge, p.name) == ("top", "Clock")


def test_a_key_called_widget_props_is_a_widget_key_too():
    p = PanelConfig.model_validate(
        {"panel": "edge", "name": "clock", "widget": "clock", "widget_props": {"format": "HH"}}
    )
    assert p.widget_props == {"widget_props": {"format": "HH"}}


def test_the_framework_keys_are_the_model_fields():
    assert set(PanelConfig.model_fields) == FRAMEWORK_KEYS | {"widget_props"}


def test_the_schema_offers_panel_and_name():
    props = Config.model_json_schema()["$defs"]["PanelConfig"]["properties"]

    def first(prop):  # an optional key is anyOf [..., null]
        return prop.get("anyOf", [prop])[0]

    assert first(props["panel"])["enum"] == list(PANEL_KINDS)
    name = first(props["name"])
    assert (name["minLength"], name["maxLength"]) == (1, 40)


def test_float_panels_are_rejected_for_now(corner_registry, make_config):
    text = problems(corner_registry, make_config, {"panel": "float", "name": "F", "widget": "box"})
    assert "monitors.HDMI-A-1.panels[0].panel: float panels are not implemented yet" in text


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        (
            {"panel": "corner", "name": "C", "widget": "clock"},
            "monitors.HDMI-A-1.panels[0].panel: clock cannot be shown in a corner panel "
            "(it supports: edge)",
        ),
        (
            {"panel": "edge", "name": "B", "widget": "box"},
            "monitors.HDMI-A-1.panels[0].panel: box cannot be shown in an edge panel "
            "(it supports: corner)",
        ),
    ],
)
def test_a_widget_on_a_kind_it_does_not_support_is_rejected(
    corner_registry, make_config, entry, message
):
    assert message in problems(corner_registry, make_config, entry)


def test_names_must_be_unique_per_monitor(fake_registry, make_config):
    text = problems(
        fake_registry,
        make_config,
        {"panel": "edge", "name": "Clock", "widget": "clock"},
        {"panel": "edge", "name": "Dock", "widget": "dock"},
        {"panel": "edge", "name": "clock", "widget": "clock"},  # case-sensitive: allowed
        {"panel": "edge", "name": "Clock", "widget": "clock", "edge": "bottom"},
    )
    assert (
        "monitors.HDMI-A-1.panels[3].name: names must be unique: 'Clock' is used by "
        "panels[0] and panels[3]"
    ) in text
    assert "panels[2]" not in text


def test_the_same_name_on_two_monitors_is_fine(fake_registry, make_config):
    entry = {"panel": "edge", "name": "Clock", "widget": "clock"}
    monitors = {"A": {"panels": [entry]}, "B": {"panels": [entry]}}
    fake_registry.validate_widgets(make_config(monitors=monitors))


def test_a_widget_key_the_widget_does_not_have_is_rejected(fake_registry, make_config):
    text = problems(
        fake_registry, make_config, {"panel": "edge", "name": "D", "widget": "dock", "format": "x"}
    )
    assert "monitors.HDMI-A-1.panels[0].format: unknown key for widget 'dock'" in text


def test_a_complete_entry_passes(corner_registry, make_config):
    corner_registry.validate_widgets(
        make_config(
            monitors=mon(
                {"panel": "edge", "name": "Dock", "widget": "dock", "align": "end"},
                {"panel": "corner", "name": "Box", "widget": "box", "corner": "top-left"},
            )
        )
    )
```

In `tests/test_settings_form.py` replace

```python
    edge = {f.key for f in form.edge_panel.fields} | {s.key for s in form.edge_panel.sections}
    corner = {f.key for f in form.corner_panel.fields} | {s.key for s in form.corner_panel.sections}
    assert edge & corner == set(SHARED_KEYS)
    assert edge | corner == set(PanelConfig.model_fields)
    assert edge - corner == set(EDGE_ONLY_KEYS) and corner - edge == set(CORNER_ONLY_KEYS)

```

with

```python
    edge = {f.key for f in form.edge_panel.fields} | {s.key for s in form.edge_panel.sections}
    corner = {f.key for f in form.corner_panel.fields} | {s.key for s in form.corner_panel.sections}
    no_rows = {"panel", "name", "widget_props"}  # not shown as rows (yet)
    assert edge & corner == set(SHARED_KEYS) - no_rows
    assert edge | corner == set(PanelConfig.model_fields) - no_rows
    assert edge - corner == set(EDGE_ONLY_KEYS) and corner - edge == set(CORNER_ONLY_KEYS)

```

In `tests/test_settings_form.py` replace

```python
            options = [o for o in prop.get("anyOf", [prop]) if o.get("type") != "null"]
            plain = [o for o in options if o.get("type") == "string" and "enum" not in o]
            if plain and key not in ("widget", "pos", "length"):
                assert key in COLOR_KEYS, f"{name}.{key}"

```

with

```python
            options = [o for o in prop.get("anyOf", [prop]) if o.get("type") != "null"]
            plain = [o for o in options if o.get("type") == "string" and "enum" not in o]
            if plain and key not in ("widget", "pos", "length", "name"):
                assert key in COLOR_KEYS, f"{name}.{key}"

```


- [ ] **Step 2: Run them to verify they fail**

Run: `scripts/py -m pytest -q tests/test_panel_entry.py tests/test_config_corner.py tests/test_corner_requests.py tests/test_settings_form.py`
Expected: a collection error, `ImportError: cannot import name 'FRAMEWORK_KEYS' from 'shell.config.models'`.

- [ ] **Step 3: Implement**

In `settings/form.py` replace

```python

    def panel(skip: tuple[str, ...]) -> SectionSpec:
        return section_for(schema, "PanelConfig", "", "Panel", widgets, skip, corner_widgets)

```

with

```python

    def panel(skip: tuple[str, ...]) -> SectionSpec:
        skip += ("panel", "name", "widget_props")  # no rows for these keys yet
        return section_for(schema, "PanelConfig", "", "Panel", widgets, skip, corner_widgets)

```

In `shell/config/models.py` replace

```python

import re
from typing import Annotated, Any, Literal, get_args

```

with

```python

import re
import unicodedata
from typing import Annotated, Any, Literal, get_args

```

In `shell/config/models.py` replace

```python

# The panel keys by kind (spec 19; the settings window reads them): both kinds take
# SHARED_KEYS; an entry mixing EDGE_ONLY_KEYS with CORNER_ONLY_KEYS is rejected.
SHARED_KEYS = ("widget", "edge", "state", "handle", "interaction")
EDGE_ONLY_KEYS = ("pos", "align", "offset", "order", "length", "min_length", "max_length", "depth")
CORNER_ONLY_KEYS = ("corner", "width", "height")


class PanelConfig(_Strict):
    """One panel entry. Edge panels use edge / align / offset / order / length / depth; corner
    panels (spec 19) use corner / edge (the edge they open from) / width / height. Which kind an
    entry is comes from its widget (shell.registry.validate_widgets checks the keys against
    it); an entry that mixes the two kinds' keys is rejected here already."""

    widget: str
    edge: Edge | None = None
```

with

```python

# The panel keys by kind (spec 19; the settings window reads them): both kinds take
# SHARED_KEYS; an entry mixing EDGE_ONLY_KEYS with CORNER_ONLY_KEYS is rejected. Every other
# key of an entry is a widget key: PanelConfig collects it in `widget_props`.
SHARED_KEYS = ("panel", "name", "widget", "edge", "state", "handle", "interaction")
EDGE_ONLY_KEYS = ("pos", "align", "offset", "order", "length", "min_length", "max_length", "depth")
CORNER_ONLY_KEYS = ("corner", "width", "height")
FRAMEWORK_KEYS = frozenset((*SHARED_KEYS, *EDGE_ONLY_KEYS, *CORNER_ONLY_KEYS))
PanelKind = Literal["edge", "corner", "float"]  # float: reserved, the registry rejects it
PANEL_KINDS: tuple[str, ...] = get_args(PanelKind)  # the settings window's choices
PanelName = Annotated[str, Field(min_length=1, max_length=40)]


def check_panel_name(value: str) -> str:
    """A panel's name: its label in logs, notifications and the settings window."""
    if any(unicodedata.category(c) == "Cc" for c in value):
        raise ValueError("must not contain control characters (tab, newline, ...)")
    if value != value.strip():
        raise ValueError("must not start or end with whitespace (a space, a no-break space, ...)")
    return value


class PanelConfig(_Strict):
    """One panel entry. `panel` is its kind: edge panels use edge / align / offset / order /
    length / depth; corner panels (spec 19) use corner / edge (the edge they open from) /
    width / height. Every key that is not in FRAMEWORK_KEYS is a widget key: it is collected
    in `widget_props` and checked against the widget's property model by
    shell.registry.validate_widgets, which also checks the kind keys against `panel`; an entry
    that mixes the two kinds' keys is rejected here already."""

    panel: PanelKind | None = None
    name: PanelName | None = None
    widget: str
    edge: Edge | None = None
```

In `shell/config/models.py` replace

```python
    width: Length | None = None  # px from the screen corner, both frame bands included
    height: Length | None = None

    @field_validator("length")
```

with

```python
    width: Length | None = None  # px from the screen corner, both frame bands included
    height: Length | None = None
    widget_props: dict[str, Any] = Field(default_factory=dict)  # never a key in the file

    @model_validator(mode="before")
    @classmethod
    def _collect_widget_keys(cls, data: Any) -> Any:
        """Every key that is not a framework key goes to `widget_props`, a key that is itself
        called "widget_props" too (in the file it can only be a widget key)."""
        if not isinstance(data, dict):
            return data
        own = {k: v for k, v in data.items() if k in FRAMEWORK_KEYS}
        return {**own, "widget_props": {k: v for k, v in data.items() if k not in FRAMEWORK_KEYS}}

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        return None if value is None else check_panel_name(value)

    @field_validator("length")
```

In `shell/registry.py` replace

```python
        wrong = [k for k in EDGE_ONLY_KEYS if getattr(panel, k) is not None]
        problems = [
            f"{where}.{key}: {panel.widget} is a corner panel; it takes corner, edge, width "
            f"and height, not {key}"
            for key in wrong
        ]
```

with

```python
        wrong = [k for k in EDGE_ONLY_KEYS if getattr(panel, k) is not None]
        problems = [
            f"{where}.{key}: a corner panel takes corner, edge, width and height, not {key}"
            for key in wrong
        ]
```

In `shell/registry.py` replace

```python
        return problems
    return [
        f"{where}.{key}: {panel.widget} is an edge panel; corner, width and height only "
        "apply to corner panels"
        for key in CORNER_ONLY_KEYS
        if getattr(panel, key) is not None
    ]


```

with

```python
        return problems
    return [
        f"{where}.{key}: an edge panel takes no {key}; corner, width and height only apply "
        "to corner panels"
        for key in CORNER_ONLY_KEYS
        if getattr(panel, key) is not None
    ]


def _name_problems(where: str, panels: list[PanelConfig]) -> list[str]:
    """A name used twice on one monitor: reported at every later use, naming the first."""
    first: dict[str, int] = {}
    problems = []
    for i, panel in enumerate(panels):
        if panel.name is None:
            continue
        if panel.name in first:
            problems.append(
                f"{where}[{i}].name: names must be unique: {panel.name!r} is used by "
                f"panels[{first[panel.name]}] and panels[{i}]"
            )
        else:
            first[panel.name] = i
    return problems


def _entry_problems(where: str, panel: PanelConfig) -> list[str]:
    if panel.panel == "float":
        return [f"{where}.panel: float panels are not implemented yet"]
    if panel.widget not in _DEFAULTS:
        return [f"{where}.widget: unknown widget {panel.widget!r}"]
    kind = widget_kind(panel.widget)
    if panel.panel is not None and panel.panel != kind:
        article = "an" if panel.panel == "edge" else "a"
        return [
            f"{where}.panel: {panel.widget} cannot be shown in {article} {panel.panel} panel "
            f"(it supports: {kind})"
        ]
    problems = _kind_problems(where, panel)
    problems += [
        f"{where}.{key}: unknown key for widget {panel.widget!r}" for key in panel.widget_props
    ]
    return problems


```

In `shell/registry.py` replace

```python
    for name, mon in config.monitors.items():
        for i, panel in enumerate(mon.panels):
            where = f"monitors.{name}.panels[{i}]"
            if panel.widget not in _DEFAULTS:
                problems.append(f"{where}.widget: unknown widget {panel.widget!r}")
            else:
                problems.extend(_kind_problems(where, panel))
    if problems:
        known = ", ".join(widget_names()) or "none"
```

with

```python
    for name, mon in config.monitors.items():
        for i, panel in enumerate(mon.panels):
            problems.extend(_entry_problems(f"monitors.{name}.panels[{i}]", panel))
        problems.extend(_name_problems(f"monitors.{name}.panels", mon.panels))
    if problems:
        known = ", ".join(widget_names()) or "none"
```


- [ ] **Step 4: Run the tests to verify they pass**

Run: `scripts/py -m pytest -q tests/test_panel_entry.py tests/test_config_corner.py tests/test_corner_requests.py tests/test_settings_form.py`
Expected: all pass (`tests/test_panel_entry.py`: 24 tests).

- [ ] **Step 5: VERIFY and commit**

Run VERIFY. Expected: `1905 passed`, `All checks passed!`.

```bash
git add shell/config/models.py shell/registry.py settings/form.py tests/test_panel_entry.py tests/test_config_corner.py tests/test_corner_requests.py tests/test_settings_form.py
git commit -m "feat(config): panel, name and widget keys in a panel entry, with their checks" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

**Reviewer mutations** (each must turn a test red; all were checked on the finished prototype): a framework key (for example `edge`) left in the widget bag (`test_every_other_key_is_a_widget_key`); the control-character check or the whitespace check removed (`test_a_bad_name_names_the_key_path`); names compared case-insensitively (`test_names_must_be_unique_per_monitor`); float let through (`test_float_panels_are_rejected_for_now`).

---

### Task 2: Convert every example and test config; `panel` and `name` become required

One commit flips the two keys to required and converts everything that builds a panel config, so the suite never sees a half-converted tree. The settings window keeps writing valid entries: `UserDocument.add_panel` takes the entry's keys, a new panel gets its kind and a free name, and a widget switch sets `panel` too.

**Files:**
- Modify: `shell/config/models.py` (`panel`, `name` required), `shell/config/loader.py` (the missing-panel message), `shell/registry.py` (the optional-key guards go)
- Modify: `settings/document.py` (`add_panel(monitor, entry)`), `settings/values.py` (`panel_ops` sets `panel`; `unique_name`, `new_panel_entry`), `settings/panels.py` (`add` writes the new entry)
- Modify: `widgets/widget_panel.py` (registered id `"summary"`, label `"summary"`)
- Modify: every file in `examples/` that has panels (8 files; `hdmi-test.toml` has none)
- Modify: about 20 test files (a one-off script, then about twenty hand fixes); `tests/test_settings_document.py` only its `add_panel` calls
- Create: `tests/test_examples.py`; Modify: `tests/test_config_loader.py`, `tests/test_settings_document.py`, `tests/test_settings_values.py` (new tests appended), `tests/test_config_corner.py`, `tests/test_config_handle.py` (`panels[0]` in the expected paths)

**Interfaces:**
- Consumes: Task 1's `PanelConfig.panel` / `name`, `FRAMEWORK_KEYS`; `registry.widget_kind` (until Task 3); `settings.values.lookup`.
- Produces: `PanelConfig.panel: PanelKind` and `PanelConfig.name: PanelName`, both required; `shell.config.loader.key_path(loc: tuple) -> str` (a panel index in brackets: `monitors.X.panels[0].name`; other lists dotted; `"config"` for an empty location), used for every pydantic error; `shell.config.loader.MISSING_PANEL`, `OLD_FORMAT`; `UserDocument.add_panel(monitor: str, entry: dict[str, Any]) -> int` (writes the keys in order, one per line); `settings.values.unique_name(base: str, taken: list[str]) -> str`; `settings.values.new_panel_entry(user: dict, monitor: str, widget: str) -> dict[str, str]` (`{"panel": kind, "name": free name, "widget": widget}`; the name base becomes the widget's title in Task 7); `panel_ops(entry, "widget", value)` adds `("set", "panel", kind)` when the kind changes. The widget id `widget_panel` is now `summary` everywhere.

- [ ] **Step 1: Write the failing tests**

Create (or replace entirely) `tests/test_examples.py`:

```python
"""Every example config loads with the real widgets (panel/widget spec 3.6)."""

from pathlib import Path

import pytest

pytest.importorskip("gi")
pytest.importorskip("fabric")

import widgets  # noqa: E402, F401  (registers the built-in widgets)
from shell.config.loader import load_config  # noqa: E402
from shell.config.store import ConfigStore  # noqa: E402

EXAMPLES = sorted((Path(__file__).resolve().parents[1] / "examples").glob("*.toml"))


def test_there_are_examples():
    assert len(EXAMPLES) >= 9


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_every_example_is_valid(path):
    config = ConfigStore(path, required=True).config  # the loader plus validate_widgets
    for monitor in config.monitors.values():
        names = [p.name for p in monitor.panels]
        assert len(names) == len(set(names)), path.name
        assert all(p.panel in ("edge", "corner") for p in monitor.panels), path.name


def test_the_default_config_has_no_panels():
    assert all(not m.panels for m in load_config(None).monitors.values())
```

In `tests/test_config_corner.py` replace

```python
    where = "monitors.HDMI-A-1.panels.0" + (f".{path}" if path else "")
```

with

```python
    where = "monitors.HDMI-A-1.panels[0]" + (f".{path}" if path else "")
```

In `tests/test_config_handle.py` replace

```python
"monitors.HDMI-A-1.panels.0.handle.shape: "
```

with

```python
"monitors.HDMI-A-1.panels[0].handle.shape: "
```

In `tests/test_config_loader.py` replace

```python
"monitors.HDMI-A-1.panels.0.length"
```

with

```python
"monitors.HDMI-A-1.panels[0].length"
```

Append to `tests/test_config_loader.py`:

```python


def test_an_entry_without_panel_names_the_new_format(tmp_path):
    path = write(
        tmp_path / "old.toml",
        "# the old format: entries with only a widget\n"
        '[[monitors.HDMI-A-1.panels]]\nwidget = "dock"\n\n[[monitors.HDMI-A-1.panels]]\n'
        'widget = "clock"\n',
    )
    with pytest.raises(ConfigError) as exc:
        load_config(path)
    lines = str(exc.value).splitlines()
    assert 'monitors.HDMI-A-1.panels[0].panel: missing; use "edge", "corner" or "float"' in lines
    assert 'monitors.HDMI-A-1.panels[1].panel: missing; use "edge", "corner" or "float"' in lines
    assert "monitors.HDMI-A-1.panels[0].name: Field required" in lines
    assert len([line for line in lines if "the old format" in line]) == 1  # once per file


def test_panel_name_and_widget_are_required():
    from shell.config.models import Config

    panel = Config.model_json_schema()["$defs"]["PanelConfig"]
    assert {"panel", "name", "widget"} <= set(panel["required"])


def test_a_panel_index_is_written_in_brackets():
    from shell.config.loader import key_path

    assert key_path(("monitors", "X", "panels", 2, "handle", "size")) == (
        "monitors.X.panels[2].handle.size"
    )
    assert key_path(("theme", "font", 0)) == "theme.font.0"  # other lists keep their dots
    assert key_path(()) == "config"
```

In `tests/test_settings_values.py` replace

```python
    monitor_names,
    panel_ops,
)
```

with

```python
    monitor_names,
    new_panel_entry,
    panel_ops,
    unique_name,
)
```

Append to `tests/test_settings_values.py`:

```python


def test_unique_name_numbers_a_taken_name():
    assert unique_name("Clock", []) == "Clock"
    assert unique_name("Clock", ["Clock"]) == "Clock 2"
    assert unique_name("Clock", ["Clock", "Clock 2", "Clock 4"]) == "Clock 3"
    assert unique_name("Clock", ["clock"]) == "Clock"  # names are case-sensitive


def test_a_new_panel_entry_has_its_kind_and_a_free_name(corner_registry):
    user = {
        "monitors": {
            "M": {
                "panels": [
                    {"panel": "edge", "name": "dock", "widget": "dock"},
                    {"panel": "edge", "name": "dock 2", "widget": "dock"},
                ]
            }
        }
    }
    assert new_panel_entry(user, "M", "dock") == {
        "panel": "edge",
        "name": "dock 3",
        "widget": "dock",
    }
    assert new_panel_entry(user, "M", "box") == {"panel": "corner", "name": "box", "widget": "box"}
    assert new_panel_entry(user, "N", "dock")["name"] == "dock"  # another monitor: free
    assert new_panel_entry({}, "M", "nope") == {"panel": "edge", "name": "nope", "widget": "nope"}
```

Append to `tests/test_settings_document.py`:

```python


def test_add_panel_writes_the_entry_keys_in_order_one_per_line():
    doc = UserDocument('[monitors.X]\nshell = "edge"\n')
    doc.add_panel("X", {"panel": "edge", "name": 'Clock "big"', "widget": "clock"})
    assert doc.text == (
        '[monitors.X]\nshell = "edge"\n\n[[monitors.X.panels]]\npanel = "edge"\n'
        'name = "Clock \\"big\\""\nwidget = "clock"\n'
    )
    assert doc.data["monitors"]["X"]["panels"] == [
        {"panel": "edge", "name": 'Clock "big"', "widget": "clock"}
    ]
```


- [ ] **Step 2: Run them to verify they fail**

Run: `scripts/py -m pytest -q tests/test_examples.py tests/test_config_loader.py tests/test_settings_document.py tests/test_config_corner.py tests/test_config_handle.py`
Expected: `22 failed, 174 passed`: `test_every_example_is_valid` for the 8 example files with panels (their entries have no `panel`, so `p.panel` is None); in `tests/test_config_loader.py` `test_panel_bound_reports_full_key_path`, `test_an_entry_without_panel_names_the_new_format`, `test_panel_name_and_widget_are_required` and `test_a_panel_index_is_written_in_brackets` (`ImportError: cannot import name 'key_path'`); `test_add_panel_writes_the_entry_keys_in_order_one_per_line` (`DocumentError: this edit cannot be written in place`); the 8 cases of `test_bad_corner_values_name_the_key_path` and `test_an_unknown_shape_lists_the_known_ones` (the loader still writes `panels.0`).
Run: `scripts/py -m pytest -q tests/test_settings_values.py`
Expected: a collection error, `ImportError: cannot import name 'new_panel_entry' from 'settings.values'`.

- [ ] **Step 3: Implement the required keys, the message and the window's writes**

In `settings/document.py` replace

```python
        )

    def add_panel(self, monitor: str, widget: str) -> int:
        """Append a panel entry with only its widget (every other key from the widget's
        defaults); returns its index."""
        self._edit(
            lambda text: _add_panel_text(text, self._data, monitor, widget),
            lambda data: _plain_panels(data, monitor, create=True).append({"widget": widget}),
            (*_panel_path(monitor), 0),
        )
```

with

```python
        )

    def add_panel(self, monitor: str, entry: dict[str, Any]) -> int:
        """Append a panel entry with the keys of `entry`, in that order, one per line (the
        settings window gives panel, name and widget; every other key comes from the widget's
        defaults); returns its index."""
        entry = dict(entry)
        self._edit(
            lambda text: _add_panel_text(text, self._data, monitor, entry),
            lambda data: _plain_panels(data, monitor, create=True).append(dict(entry)),
            (*_panel_path(monitor), 0),
        )
```

In `settings/document.py` replace

```python


def _new_entry(text: str, header: str, widget: str, blank: bool) -> list[str]:
    newline = "\r\n" if "\r\n" in text else "\n"
    body = "widget = " + tomlkit.item(widget).as_string()
    return ([newline] if blank else []) + [header + newline, body + newline]


def _add_panel_text(text: str, data: dict, monitor: str, widget: str) -> str:
    lines = _lines(text)
    monitors = data.get("monitors", {})
```

with

```python


def _new_entry(text: str, header: str, entry: dict[str, Any], blank: bool) -> list[str]:
    newline = "\r\n" if "\r\n" in text else "\n"
    body = [
        f"{tomlkit.key(key).as_string()} = {tomlkit.item(value).as_string()}{newline}"
        for key, value in entry.items()
    ]
    return ([newline] if blank else []) + [header + newline, *body]


def _add_panel_text(text: str, data: dict, monitor: str, entry: dict[str, Any]) -> str:
    lines = _lines(text)
    monitors = data.get("monitors", {})
```

In `settings/document.py` replace

```python
        # never directly below a comment (it would read as the new entry's label)
        blank = at > s.end[-1] and not gap
        entry = _new_entry(text, _bracket(lines[s.head[-1]]), widget, blank)
        return "".join(lines[:at] + gap + entry + lines[at:])
    tail = len(lines)
    while tail > 0 and _blank_or_comment(lines[tail - 1]):
```

with

```python
        # never directly below a comment (it would read as the new entry's label)
        blank = at > s.end[-1] and not gap
        new = _new_entry(text, _bracket(lines[s.head[-1]]), entry, blank)
        return "".join(lines[:at] + gap + new + lines[at:])
    tail = len(lines)
    while tail > 0 and _blank_or_comment(lines[tail - 1]):
```

In `settings/document.py` replace

```python
        header = "[[" + tomlkit.key(list(_panel_path(monitor))).as_string() + "]]"
    else:  # a monitor known only from dotted keys or an inline table
        return _in_doc(lambda doc: _add_panel(doc, monitor, widget))(text)
    blank = at > 0 and bool(lines[at - 1].strip())
    return "".join(lines[:at] + _new_entry(text, header, widget, blank) + lines[at:])


```

with

```python
        header = "[[" + tomlkit.key(list(_panel_path(monitor))).as_string() + "]]"
    else:  # a monitor known only from dotted keys or an inline table
        return _in_doc(lambda doc: _add_panel(doc, monitor, entry))(text)
    blank = at > 0 and bool(lines[at - 1].strip())
    return "".join(lines[:at] + _new_entry(text, header, entry, blank) + lines[at:])


```

In `settings/document.py` replace

```python


def _add_panel(doc, monitor: str, widget: str) -> None:
    """Only for a monitor without any header of its own (the text side handles the rest)."""
    table = _monitor_table(doc, monitor)
    entry = tomlkit.table()
    entry["widget"] = widget
    if "panels" not in table:
        table["panels"] = tomlkit.aot()
```

with

```python


def _add_panel(doc, monitor: str, keys: dict[str, Any]) -> None:
    """Only for a monitor without any header of its own (the text side handles the rest)."""
    table = _monitor_table(doc, monitor)
    entry = tomlkit.table()
    for key, value in keys.items():
        entry[key] = value
    if "panels" not in table:
        table["panels"] = tomlkit.aot()
```

In `settings/panels.py` replace

```python
from settings.fields import wheel_scrolls_the_page
from settings.form import ConfigForm, SectionSpec
from shell.panel_spec import CornerRequest, PanelRequest
from shell.registry import widget_kind
```

with

```python
from settings.fields import wheel_scrolls_the_page
from settings.form import ConfigForm, SectionSpec
from settings.values import new_panel_entry
from shell.panel_spec import CornerRequest, PanelRequest
from shell.registry import widget_kind
```

In `settings/panels.py` replace

```python

    def add(self, widget: str | None) -> None:
        """A new entry with only its widget, edge or corner kind alike (a corner widget's
        entry is {"widget": "widget_panel"}: its corner and size are the widget's)."""
        if widget:
            self._on_edit(lambda d: d.add_panel(self.monitor, widget), self._count)

    def remove(self, index: int) -> None:
```

with

```python

    def add(self, widget: str | None) -> None:
        """A new entry with its kind, a name unique on this monitor and its widget, edge or
        corner kind alike (a corner widget's entry is {"panel": "corner", "name": "summary",
        "widget": "summary"}: its corner and size are the widget's)."""
        if widget:
            self._on_edit(
                lambda d: d.add_panel(self.monitor, new_panel_entry(d.data, self.monitor, widget)),
                self._count,
            )

    def remove(self, index: int) -> None:
```

In `settings/values.py` replace

```python
    (("set" | "unset", key, value)) applied as ONE edit: one write, one reload.

    - A widget of the other kind also unsets the keys only the old kind takes (a dock turned
      into a corner widget loses its align, length, ...; spec 19), else the shell rejects it.
    - `value` None for "corner" is a reset: the key is unset and the widget's corner applies.
    - An unknown widget is a plain set (the session's check rejects it, ConfigError).
```

with

```python
    (("set" | "unset", key, value)) applied as ONE edit: one write, one reload.

    - A widget of the other kind also sets `panel` to that kind and unsets the keys only the
      old kind takes (a dock turned into a corner widget loses its align, length, ...; spec
      19), else the shell rejects it. The entry keeps its name.
    - `value` None for "corner" is a reset: the key is unset and the widget's corner applies.
    - An unknown widget is a plain set (the session's check rejects it, ConfigError).
```

In `settings/values.py` replace

```python
        except KeyError:  # unknown widget: the session's check rejects it with the shell's text
            return ops
        stale = CORNER_ONLY_KEYS if kind == "edge" else EDGE_ONLY_KEYS
        ops += [("unset", k, None) for k in stale if k in entry]
```

with

```python
        except KeyError:  # unknown widget: the session's check rejects it with the shell's text
            return ops
        if entry.get("panel") != kind:
            ops.append(("set", "panel", kind))
        stale = CORNER_ONLY_KEYS if kind == "edge" else EDGE_ONLY_KEYS
        ops += [("unset", k, None) for k in stale if k in entry]
```

In `settings/values.py` replace

```python
        ops.append(("unset", "edge", None))
    return ops


```

with

```python
        ops.append(("unset", "edge", None))
    return ops


def unique_name(base: str, taken: list[str]) -> str:
    """`base`, or "base 2", "base 3", ...: the first that is not in `taken`."""
    if base not in taken:
        return base
    n = 2
    while f"{base} {n}" in taken:
        n += 1
    return f"{base} {n}"


def new_panel_entry(user: dict, monitor: str, widget: str) -> dict[str, str]:
    """The keys a new panel of `widget` on `monitor` is written with (`user`: the user file's
    plain data): its kind, a name not used on that monitor yet and the widget; every other key
    comes from the widget's defaults. An unknown widget is written as an edge panel (the
    session's check rejects it with the shell's text)."""
    try:
        kind = widget_kind(widget)
    except KeyError:
        kind = "edge"
    _, panels = lookup(user, ("monitors", monitor, "panels"))
    taken = [p.get("name") for p in panels or () if isinstance(p, dict)]
    return {"panel": kind, "name": unique_name(widget, taken), "widget": widget}


```

In `shell/config/loader.py` replace

```python


def format_validation_error(err: ValidationError) -> str:
    lines = []
    for item in err.errors():
        path = ".".join(str(p) for p in item["loc"]) or "config"
        lines.append(f"{path}: {item['msg']}")
    return "\n".join(lines)

```

with

```python


MISSING_PANEL = 'missing; use "edge", "corner" or "float"'
OLD_FORMAT = (
    'panel entries start with panel = "edge" | "corner" | "float", name = "..." and '
    'widget = "..." (an entry with only a widget is the old format; see the README, "Panels")'
)


def key_path(loc: tuple) -> str:
    """A pydantic error location as a key path. A panel entry's index is written in brackets,
    as shell.registry.validate_widgets writes it: monitors.HDMI-A-1.panels[0].name."""
    out = ""
    for i, part in enumerate(loc):
        if isinstance(part, int) and i > 0 and loc[i - 1] == "panels":
            out += f"[{part}]"
        else:
            out += f".{part}" if out else str(part)
    return out or "config"


def _missing_panel(item: dict) -> bool:
    loc = item["loc"]
    return (
        item["type"] == "missing" and len(loc) >= 3 and loc[-1] == "panel" and loc[-3] == "panels"
    )


def format_validation_error(err: ValidationError) -> str:
    lines = []
    old_format = False
    for item in err.errors():
        path = key_path(item["loc"])
        if _missing_panel(item):
            old_format = True
            lines.append(f"{path}: {MISSING_PANEL}")
        else:
            lines.append(f"{path}: {item['msg']}")
    if old_format:  # once per file, however many entries lack it
        lines.append(OLD_FORMAT)
    return "\n".join(lines)

```

In `shell/config/models.py` replace

```python
    that mixes the two kinds' keys is rejected here already."""

    panel: PanelKind | None = None
    name: PanelName | None = None
    widget: str
    edge: Edge | None = None
```

with

```python
    that mixes the two kinds' keys is rejected here already."""

    panel: PanelKind
    name: PanelName
    widget: str
    edge: Edge | None = None
```

In `shell/config/models.py` replace

```python
    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        return None if value is None else check_panel_name(value)

    @field_validator("length")
```

with

```python
    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return check_panel_name(value)

    @field_validator("length")
```

In `shell/registry.py` replace

```python
    problems = []
    for i, panel in enumerate(panels):
        if panel.name is None:
            continue
        if panel.name in first:
            problems.append(
```

with

```python
    problems = []
    for i, panel in enumerate(panels):
        if panel.name in first:
            problems.append(
```

In `shell/registry.py` replace

```python
        return [f"{where}.widget: unknown widget {panel.widget!r}"]
    kind = widget_kind(panel.widget)
    if panel.panel is not None and panel.panel != kind:
        article = "an" if panel.panel == "edge" else "a"
        return [
```

with

```python
        return [f"{where}.widget: unknown widget {panel.widget!r}"]
    kind = widget_kind(panel.widget)
    if panel.panel != kind:
        article = "an" if panel.panel == "edge" else "a"
        return [
```

In `widgets/widget_panel.py` replace

```python

@register(
    "widget_panel",
    CornerDefaults(corner="bottom-left", width=300, height=390, label="widget panel"),
)
class WidgetPanel(CornerPanel):
```

with

```python

@register(
    "summary",
    CornerDefaults(corner="bottom-left", width=300, height=390, label="summary"),
)
class WidgetPanel(CornerPanel):
```


- [ ] **Step 4: Rewrite the examples**

Create (or replace entirely) `examples/corner-test.toml`:

```toml
# Gate B (corner panel plan): corner panels next to edge panels, on HDMI-A-1 only (DP-1 is
# left alone).
#   cp examples/corner-test.toml /tmp/edge-corner.toml
#   scripts/py main.py --config /tmp/edge-corner.toml -v      (edit the copy while it runs)
[monitors.HDMI-A-1]
shell = "edge"

[[monitors.HDMI-A-1.panels]]    # 0: the summary block: bottom-left, rising out of the bottom
panel = "corner"                #    edge (its defaults: 300 x 390 px from the corner, extended)
name = "Summary"
widget = "summary"

[[monitors.HDMI-A-1.panels]]    # 1: dock, bottom centre
panel = "edge"
name = "Dock"
widget = "dock"

[[monitors.HDMI-A-1.panels]]    # 2: clock at the start of the bottom edge: right of the summary
panel = "edge"
name = "Clock"
widget = "clock"
edge = "bottom"
align = "start"

[[monitors.HDMI-A-1.panels]]    # 3: system bar on the left edge, at its end: above the lifted corner
panel = "edge"
name = "System bar"
widget = "system_bar"
edge = "left"
align = "end"

[[monitors.HDMI-A-1.panels]]    # 4: a second summary block, top-right, opening from the right
panel = "corner"                #    edge, collapsed, click only (auto shape: a chevron)
name = "Summary top-right"
widget = "summary"
corner = "top-right"
edge = "right"
width = 260
height = 240
state = "collapsed"
interaction.hover = false
interaction.drag = false
```

Create (or replace entirely) `examples/dock-test.toml`:

```toml
[monitors.HDMI-A-1]
shell = "edge"

[[monitors.HDMI-A-1.panels]]
panel = "edge"
name = "Dock"
widget = "dock"
```

Create (or replace entirely) `examples/effects-test.toml`:

```toml
# Gate 4: shape canvas border and shadow on HDMI-A-1 only (DP-1 is left alone).
#   cp examples/effects-test.toml /tmp/edge-effects.toml
#   scripts/py main.py --config /tmp/edge-effects.toml -v      (edit the copy while it runs)
[theme.border]
enabled = true

[theme.shadow]
enabled = true
elevation = 50

[monitors.HDMI-A-1]
shell = "edge"

[[monitors.HDMI-A-1.panels]]
panel = "edge"
name = "Dock"
widget = "dock"

[[monitors.HDMI-A-1.panels]]
panel = "edge"
name = "Clock"
widget = "clock"

[[monitors.HDMI-A-1.panels]]
panel = "edge"
name = "System bar"
widget = "system_bar"
```

Create (or replace entirely) `examples/handles-test.toml`:

```toml
# Gate B (handle plan): handle shapes, colours, offsets and per-interaction toggles, on
# HDMI-A-1 only (DP-1 is left alone).
#   cp examples/handles-test.toml /tmp/edge-handles.toml
#   scripts/py main.py --config /tmp/edge-handles.toml -v      (edit the copy while it runs)
[monitors.HDMI-A-1]
shell = "edge"

[[monitors.HDMI-A-1.panels]]    # 0: dock, bottom centre: today's dots, every interaction
panel = "edge"
name = "Dock"
widget = "dock"

[[monitors.HDMI-A-1.panels]]    # 1: top left, click only: "auto" draws a chevron
panel = "edge"
name = "Clock (click only)"
widget = "clock"
align = "start"
interaction.hover = false
interaction.drag = false

[[monitors.HDMI-A-1.panels]]    # 2: top right, hover + drag (no click): "auto" draws a bar
panel = "edge"
name = "Clock (hover and drag)"
widget = "clock"
align = "end"
state = "collapsed"
interaction.click = false
handle.size = 28
handle.color = "#8fd3b6"
handle.hover_color = "#ffffff"

[[monitors.HDMI-A-1.panels]]    # 3: right edge: an explicit chevron, thinner, 100 px up
panel = "edge"
name = "System bar"
widget = "system_bar"
handle.shape = "chevron"
handle.size = 24
handle.weight = 2
handle.offset = -100

[[monitors.HDMI-A-1.panels]]    # 4: bottom left, every interaction off: only `state` opens it
panel = "edge"
name = "Clock (state only)"
widget = "clock"
edge = "bottom"
align = "start"
state = "collapsed"
interaction.click = false
interaction.hover = false
interaction.drag = false
```

Create (or replace entirely) `examples/layout-sizes-test.toml`:

```toml
# Gate B (layout plan): fill, content and percentage lengths, on HDMI-A-1 only.
#   cp examples/layout-sizes-test.toml /tmp/edge-sizes.toml
#   scripts/py main.py --config /tmp/edge-sizes.toml -v       (edit the copy while it runs)
[monitors.HDMI-A-1]
shell = "edge"

[[monitors.HDMI-A-1.panels]]    # 0: bottom, fills the span between the two clocks
panel = "edge"
name = "Dock"
widget = "dock"
length = "fill"

[[monitors.HDMI-A-1.panels]]    # 1: bottom-left, as long as its content
panel = "edge"
name = "Clock bottom-left"
widget = "clock"
edge = "bottom"
align = "start"
length = "content"

[[monitors.HDMI-A-1.panels]]    # 2: bottom-right, as long as its content
panel = "edge"
name = "Clock bottom-right"
widget = "clock"
edge = "bottom"
align = "end"
length = "content"

[[monitors.HDMI-A-1.panels]]    # 3: top, half of the free span but at most 700 px
panel = "edge"
name = "Clock top"
widget = "clock"
length = "50%"
max_length = 700

[[monitors.HDMI-A-1.panels]]    # 4: right, as long as its content, centred
panel = "edge"
name = "System bar"
widget = "system_bar"
align = "center"
length = "content"
```

Create (or replace entirely) `examples/layout-test.toml`:

```toml
# Gate A (layout plan): several panels per edge, on HDMI-A-1 only (DP-1 is left alone).
#   cp examples/layout-test.toml /tmp/edge-layout.toml
#   scripts/py main.py --config /tmp/edge-layout.toml -v      (edit the copy while it runs)
[monitors.HDMI-A-1]
shell = "edge"

[[monitors.HDMI-A-1.panels]]    # 0: centre of the bottom edge (the dock's default)
panel = "edge"
name = "Dock"
widget = "dock"

[[monitors.HDMI-A-1.panels]]    # 1: bottom-left, next to the corner
panel = "edge"
name = "Clock bottom-left"
widget = "clock"
edge = "bottom"
align = "start"

[[monitors.HDMI-A-1.panels]]    # 2: bottom-right, next to the corner
panel = "edge"
name = "Clock bottom-right"
widget = "clock"
edge = "bottom"
align = "end"

[[monitors.HDMI-A-1.panels]]    # 3: top centre slot, second (order 1)
panel = "edge"
name = "Clock top, second"
widget = "clock"
order = 1

[[monitors.HDMI-A-1.panels]]    # 4: top centre slot, first (order 0), shorter
panel = "edge"
name = "Clock top, first"
widget = "clock"
length = 120

[[monitors.HDMI-A-1.panels]]    # 5: right edge, 60 px up from the bottom end
panel = "edge"
name = "System bar"
widget = "system_bar"
align = "end"
offset = 60
```

Create (or replace entirely) `examples/panels-test.toml`:

```toml
[monitors.HDMI-A-1]
shell = "edge"

[[monitors.HDMI-A-1.panels]]
panel = "edge"
name = "Dock"
widget = "dock"

[[monitors.HDMI-A-1.panels]]
panel = "edge"
name = "Clock"
widget = "clock"

[[monitors.HDMI-A-1.panels]]
panel = "edge"
name = "System bar"
widget = "system_bar"
```

Create (or replace entirely) `examples/settings-test.toml`:

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
panel = "edge"
name = "Dock"
widget = "dock"

[[monitors.HDMI-A-1.panels]]   # clock, top centre
panel = "edge"
name = "Clock"
widget = "clock"

[[monitors.HDMI-A-1.panels]]   # system bar, right edge
panel = "edge"
name = "System bar"
widget = "system_bar"

[monitors.DP-1]
shell = "plasma"     # holds the Plasma panel: leave it alone
```


- [ ] **Step 5: Convert the test configs**

First the id rename in the two tests that name `widget_panel`:

In `tests/test_config_corner.py` replace

```python
{"widget": "widget_panel", **keys}
```

with

```python
{"widget": "summary", **keys}
```

In `tests/test_widget_panel.py` replace (all 3 occurrences)

```python
"widget_panel"
```

with

```python
"summary"
```

In `tests/test_widget_panel.py` replace

```python
label="widget panel"
```

with

```python
label="summary"
```


Then save this one-off script OUTSIDE the repository (it is not committed), as `/tmp/convert_tests.py`:

```python
"""One-off: give every panel entry in the tests a `panel` and a `name` (Task 2).

Usage: scripts/py convert_tests.py tests/test_a.py tests/test_b.py ...

Rewrites, in place:
- a dict literal with a "widget": "W" key and no "panel" key: `"panel": K, "name": N, ` is
  inserted after its "{";
- a call `PanelConfig(widget="W", ...)` without panel=: `panel=K, name=N, ` before widget=;
- a string literal holding TOML lines `widget = "W"` with no `panel = ` line: `panel = K` and
  `name = N` lines are inserted above each such line (as "\\n" escapes in a one-line string);
  a string that says "old format" is left alone (it is an old-format config on purpose).
K is "corner" for the corner widgets (box, side, widget_panel, summary), else "edge". N is W, then
"W 2", "W 3", ... for the next entries of the same widget in the same list, call or string,
so names are unique per monitor and an unchanged entry keeps its name in before/after pairs.
"""

from __future__ import annotations

import ast
import re
import sys
from collections import Counter
from pathlib import Path

CORNER = {"box", "side", "widget_panel", "summary"}  # the corner widgets the tests use
TOML_WIDGET = re.compile(r'(?P<indent>[ \t]*)widget = "(?P<w>[^"]*)"')


def kind(widget: str) -> str:
    return "corner" if widget in CORNER else "edge"


class Namer:
    def __init__(self) -> None:
        self.seen: Counter[str] = Counter()

    def __call__(self, widget: str) -> str:
        self.seen[widget] += 1
        n = self.seen[widget]
        return widget if n == 1 else f"{widget} {n}"


def offsets(text: str) -> list[int]:
    starts, total = [], 0
    for line in text.splitlines(keepends=True):
        starts.append(total)
        total += len(line)
    starts.append(total)
    return starts


def widget_of_dict(node: ast.Dict) -> str | None:
    keys = [k.value for k in node.keys if isinstance(k, ast.Constant)]
    if "panel" in keys:
        return None
    for k, v in zip(node.keys, node.values, strict=True):
        if isinstance(k, ast.Constant) and k.value == "widget":
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                return v.value
    return None


def is_panel_config(call: ast.Call) -> bool:
    f = call.func
    return isinstance(f, ast.Name) and f.id == "PanelConfig"


def convert(path: Path) -> int:
    text = path.read_text()
    tree = ast.parse(text)
    starts = offsets(text)
    edits: list[tuple[int, int, str]] = []  # (start, end, replacement)

    def at(lineno: int, col: int) -> int:
        # ast columns are UTF-8 byte offsets
        line = text[starts[lineno - 1] : starts[lineno]]
        return starts[lineno - 1] + len(line.encode()[:col].decode())

    groups: dict[int, Namer] = {}

    def namer_for(parent: ast.AST) -> Namer:
        return groups.setdefault(id(parent), Namer())

    parents: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node

    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            widget = widget_of_dict(node)
            if widget is None:
                continue
            name = namer_for(parents.get(id(node), tree))(widget)
            pos = at(node.lineno, node.col_offset) + 1  # after "{"
            edits.append((pos, pos, f'"panel": "{kind(widget)}", "name": "{name}", '))
        elif isinstance(node, ast.Call) and is_panel_config(node):
            kws = {k.arg: k for k in node.keywords}
            w = kws.get("widget")
            if "panel" in kws or w is None or not isinstance(w.value, ast.Constant):
                continue
            widget = w.value.value
            name = namer_for(parents.get(id(node), tree))(widget)
            pos = at(w.lineno, w.col_offset)
            edits.append((pos, pos, f'panel="{kind(widget)}", name="{name}", '))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if "widget = " not in node.value or "panel = " in node.value:
                continue
            if "old format" in node.value:  # an old-format config on purpose (Task 2's test)
                continue
            start = at(node.lineno, node.col_offset)
            end = at(node.end_lineno, node.end_col_offset)
            segment = text[start:end]
            triple = segment.lstrip("rbuRBUfF")[:3] in ('"""', "'''")
            namer = Namer()

            def repl(m: re.Match, triple=triple, namer=namer) -> str:
                widget, indent = m["w"], m["indent"]
                k, n = kind(widget), namer(widget)
                if triple:
                    nl = "\n" + indent
                    return f'{indent}panel = "{k}"{nl}name = "{n}"{nl}widget = "{widget}"'
                return f'{indent}panel = "{k}"\\nname = "{n}"\\nwidget = "{widget}"'

            edits.append((start, end, TOML_WIDGET.sub(repl, segment)))
    for start, end, new in sorted(edits, reverse=True):
        text = text[:start] + new + text[end:]
    path.write_text(text)
    return len(edits)


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        print(arg, convert(Path(arg)))
```


and run it on every test file except `tests/test_settings_document.py` (that file edits TOML text that is never validated), then format:

```bash
ls tests/*.py | grep -v test_settings_document | xargs scripts/py /tmp/convert_tests.py
scripts/py -m ruff format tests
```

Expected: one line per file with its count of rewritten entries; the non-zero ones are exactly: `test_app_sync.py 20`, `test_canvas_stats.py 5`, `test_config_corner.py 3`, `test_config_diff.py 18`, `test_config_handle.py 3`, `test_config_loader.py 2`, `test_config_models.py 17`, `test_config_store.py 2`, `test_corner_layout.py 2`, `test_corner_requests.py 16`, `test_handle_requests.py 21`, `test_monitor_shell.py 102`, `test_registry.py 22`, `test_settings_panels.py 9`, `test_settings_session.py 3`, `test_settings_values.py 31`, `test_settings_view.py 4`. The tests written in Step 1 add nothing to these counts: their entries already have `panel`, and the loader's old-format TOML says "old format", which the script leaves alone.

Then the hand fixes the script cannot know (a widget switch now sets `panel` and keeps the name; a hand edit of `shell = "edge"` must not also change `panel = "edge"`; entries built in a comprehension or an f-string; `add_panel` takes the entry's keys; the TOML strings that grew past 100 characters). Save as `/tmp/t2_fixups.py` (not committed) and run it from the repository root:

```python
"""One-off, Task 2 Step 5: the hand fixes after convert_tests.py and `ruff format tests`.
Run from the repository root: scripts/py /tmp/t2_fixups.py"""

import re
from pathlib import Path


def edit(path, reps, count=1):
    p = Path(path)
    s = p.read_text()
    for a, b in reps:
        assert s.count(a) == count, (path, a, s.count(a))
        s = s.replace(a, b)
    p.write_text(s)


# a widget switch now also sets `panel` (and the entry keeps its name)
edit(
    "tests/test_settings_values.py",
    [
        (
            '[("set", "widget", "box"), ("unset", "align", None), ("unset", "length", None)],',
            '[\n                ("set", "widget", "box"),\n                ("set", "panel", "corner"),\n'
            '                ("unset", "align", None),\n                ("unset", "length", None),\n'
            "            ],",
        ),
        (
            '[("set", "widget", "box"), ("unset", "edge", None)],',
            '[("set", "widget", "box"), ("set", "panel", "corner"), ("unset", "edge", None)],',
        ),
        (
            '[("set", "widget", "dock"), ("unset", "corner", None), ("unset", "width", None)],',
            '[\n                ("set", "widget", "dock"),\n                ("set", "panel", "edge"),\n'
            '                ("unset", "corner", None),\n                ("unset", "width", None),\n'
            "            ],",
        ),
        (
            '    assert result == {"panel": "corner", "name": "box", "widget": "box"}\n',
            '    assert result == {"panel": "corner", "name": "dock", "widget": "box"}  # the name stays\n',
        ),
        (
            '        "panel": "corner",\n        "name": "box",\n        "widget": "box",\n'
            '        "edge": "left",\n    }  # left is an edge of bottom-left',
            '        "panel": "corner",\n        "name": "dock",\n        "widget": "box",\n'
            '        "edge": "left",\n    }  # left is an edge of bottom-left',
        ),
        (
            '    assert result == {"panel": "edge", "name": "dock", "widget": "dock", "edge": "left"}\n',
            '    assert result == {"panel": "edge", "name": "box", "widget": "dock", "edge": "left"}\n',
        ),
    ],
)

# a hand edit of the mode must not turn `panel = "edge"` into "both" too
edit(
    "tests/test_settings_view.py",
    [("USER.replace('\"edge\"', '\"both\"')", "USER.replace('shell = \"edge\"', 'shell = \"both\"')")],
    count=9,
)
edit(
    "tests/test_settings_view.py",
    [
        (
            """'panel = "corner"\\nname = "box"\\nwidget = "box"' in text""",
            """'panel = "corner"\\nname = "dock"\\nwidget = "box"' in text""",
        )
    ],
)

# entries built in a comprehension or an f-string (the converter only sees literals)
edit(
    "tests/test_settings_panels.py",
    [
        (
            '    config = make_config(monitors={"M": {"panels": [{"widget": w} for w in THREE]}})\n',
            '    panels_ = [{"panel": "edge", "name": w, "widget": w} for w in THREE]\n'
            '    config = make_config(monitors={"M": {"panels": panels_}})\n',
        ),
        (
            """    doc = UserDocument("".join(f'[[monitors.M.panels]]\\nwidget = "{w}"\\n' for w in THREE))\n""",
            """    entry = '[[monitors.M.panels]]\\npanel = "edge"\\nname = "{0}"\\nwidget = "{0}"\\n'\n"""
            """    doc = UserDocument("".join(entry.format(w) for w in THREE))\n""",
        ),
    ],
)

# add_panel takes the entry's keys now
edit(
    "tests/test_settings_session.py",
    [
        (
            'd.add_panel("HDMI-A-1", "nope")',
            'd.add_panel("HDMI-A-1", {"panel": "edge", "name": "N", "widget": "nope"})',
        ),
        (
            'd.add_panel("HDMI-A-1", "clock")',
            'd.add_panel("HDMI-A-1", {"panel": "edge", "name": "C", "widget": "clock"})',
        ),
    ],
)
p = Path("tests/test_settings_document.py")
s, n = re.subn(
    r'add_panel\(("[^"]*"|monitor), "([^"]*)"\)', r'add_panel(\1, {"widget": "\2"})', p.read_text()
)
assert n == 27, n
p.write_text(s)

# one-line TOML strings the converter made longer than 100 characters
edit(
    "tests/test_canvas_stats.py",
    [
        (
            """        '[[monitors.HDMI-A-1.panels]]\\npanel = "edge"\\nname = "dock"\\nwidget = "dock"\\nalign = "end"\\n'
        '[[monitors.HDMI-A-1.panels]]\\npanel = "edge"\\nname = "clock"\\nwidget = "clock"\\nlength = "fill"\\n'
""",
            """        '[[monitors.HDMI-A-1.panels]]\\npanel = "edge"\\nname = "dock"\\nwidget = "dock"\\n'
        'align = "end"\\n'
        '[[monitors.HDMI-A-1.panels]]\\npanel = "edge"\\nname = "clock"\\nwidget = "clock"\\n'
        'length = "fill"\\n'
""",
        ),
        (
            """        '[[monitors.HDMI-A-1.panels]]\\npanel = "edge"\\nname = "dock"\\nwidget = "dock"\\nlength = "half"\\n'
""",
            """        '[[monitors.HDMI-A-1.panels]]\\npanel = "edge"\\nname = "dock"\\nwidget = "dock"\\n'
        'length = "half"\\n'
""",
        ),
        (
            """        '[monitors.HDMI-A-1]\\nshell = "edge"\\n[[monitors.HDMI-A-1.panels]]\\npanel = "edge"\\nname = "nope"\\nwidget = "nope"\\n'
""",
            """        '[monitors.HDMI-A-1]\\nshell = "edge"\\n[[monitors.HDMI-A-1.panels]]\\n'
        'panel = "edge"\\nname = "nope"\\nwidget = "nope"\\n'
""",
        ),
    ],
)
edit(
    "tests/test_config_loader.py",
    [
        (
            """            '[[monitors.HDMI-A-1.panels]]\\npanel = "edge"\\nname = "clock"\\nwidget = "clock"\\ndepth = 50\\n',
""",
            """            '[[monitors.HDMI-A-1.panels]]\\npanel = "edge"\\nname = "clock"\\nwidget = "clock"\\n'
            "depth = 50\\n",
""",
        ),
    ],
)
edit(
    "tests/test_config_store.py",
    [
        (
            """GOOD = '[monitors.HDMI-A-1]\\nshell = "edge"\\n[[monitors.HDMI-A-1.panels]]\\npanel = "edge"\\nname = "dock"\\nwidget = "dock"\\n'
""",
            """GOOD = (
    '[monitors.HDMI-A-1]\\nshell = "edge"\\n'
    '[[monitors.HDMI-A-1.panels]]\\npanel = "edge"\\nname = "dock"\\nwidget = "dock"\\n'
)
""",
        ),
        (
            """        '[monitors.HDMI-A-1]\\n[[monitors.HDMI-A-1.panels]]\\npanel = "edge"\\nname = "ghost"\\nwidget = "ghost"\\n',  # unknown widget
""",
            """        '[monitors.HDMI-A-1]\\n[[monitors.HDMI-A-1.panels]]\\npanel = "edge"\\nname = "ghost"\\n'
        'widget = "ghost"\\n',  # unknown widget
""",
        ),
    ],
)
edit(
    "tests/test_settings_panels.py",
    [
        (
            """USER = '[[monitors.M.panels]]\\npanel = "edge"\\nname = "dock"\\nwidget = "dock"\\n[[monitors.M.panels]]\\npanel = "edge"\\nname = "clock"\\nwidget = "clock"\\n'
""",
            """USER = (
    '[[monitors.M.panels]]\\npanel = "edge"\\nname = "dock"\\nwidget = "dock"\\n'
    '[[monitors.M.panels]]\\npanel = "edge"\\nname = "clock"\\nwidget = "clock"\\n'
)
""",
        ),
    ],
)
print("fixups applied")
```


```bash
scripts/py /tmp/t2_fixups.py
scripts/py -m ruff format tests
```

Expected: `fixups applied` (each replacement asserts that its text occurs exactly as often as expected; an AssertionError names the file and the text: STOP and report it).

- [ ] **Step 6: Run the tests to verify they pass**

Run: `scripts/py -m pytest -q tests/test_examples.py tests/test_config_loader.py tests/test_settings_document.py tests/test_settings_values.py`
Expected: all pass.

- [ ] **Step 7: VERIFY and commit**

Run VERIFY. Expected: `1922 passed`, `All checks passed!`. Also `grep -rn '"widget_panel"' shell settings widgets tests examples` prints nothing (the module keeps its file name until Task 4).

```bash
git add shell/config/models.py shell/config/loader.py shell/registry.py settings/document.py settings/values.py settings/panels.py widgets/widget_panel.py examples/corner-test.toml examples/dock-test.toml examples/effects-test.toml examples/handles-test.toml examples/layout-sizes-test.toml examples/layout-test.toml examples/panels-test.toml examples/settings-test.toml tests/test_examples.py tests/test_app_sync.py tests/test_canvas_stats.py tests/test_config_corner.py tests/test_config_diff.py tests/test_config_handle.py tests/test_config_loader.py tests/test_config_models.py tests/test_config_store.py tests/test_corner_layout.py tests/test_corner_requests.py tests/test_handle_requests.py tests/test_monitor_shell.py tests/test_registry.py tests/test_settings_document.py tests/test_settings_panels.py tests/test_settings_session.py tests/test_settings_values.py tests/test_settings_view.py tests/test_widget_panel.py
git status --short
git commit -m "feat(config): panel and name are required; examples and tests converted; summary widget id" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

`git status --short` must show nothing unstaged under `tests/`, `shell/`, `settings/`, `widgets/` or `examples/` before the commit (a file the script touched but the list missed: add it by name).

**Reviewer mutations:** the old-format line repeated per entry or dropped (`test_an_entry_without_panel_names_the_new_format`); `key_path` writing `panels.0` again (`test_a_panel_index_is_written_in_brackets`); a widget switch that keeps the old `panel` (`test_panel_ops_keep_the_entry_valid`, `test_every_edge_only_key_goes_when_the_widget_becomes_a_corner_widget`); `unique_name` ignoring the taken names (`test_unique_name_numbers_a_taken_name`); an example that still lacks `panel` (`test_every_example_is_valid`).

---

### Task 3: The widget registry: `register_widget`, per-kind defaults, property models

`register_widget` replaces `register`: a widget has a title, a `WidgetProps` model and defaults for each panel kind it can be shown in. `request_for` picks the defaults by the entry's `panel`, validates the widget keys and puts `name` and the props on the request. The built-in widgets keep their panel classes for one more task, only their decorator changes. `widget_kind` goes; its three callers in the settings window read the kind from the entry or the request.

**Files:**
- Create: `shell/widget.py`
- Modify: `shell/registry.py` (rewritten), `shell/panel_spec.py` (`name`, `props` on the requests)
- Modify: `widgets/dock.py`, `widgets/clock.py`, `widgets/system_bar.py`, `widgets/widget_panel.py` (decorator only)
- Modify: `settings/values.py`, `settings/panels.py`, `settings/view.py`, `settings/form.py` (kind from the entry; docstrings)
- Create: `tests/test_widget_registry.py`
- Modify: `tests/conftest.py` (`fake_registry`, `corner_registry` use `register_widget`), `tests/test_registry.py`, `tests/test_corner_requests.py`, `tests/test_handle_requests.py`, `tests/test_widget_kinds.py`, `tests/test_widget_panel.py`

**Interfaces:**
- Consumes: `FRAMEWORK_KEYS`, `check_panel_name` (Task 1); `PanelDefaults`, `CornerDefaults`, `PanelRequest`, `CornerRequest` (`shell/panel_spec.py`).
- Produces: `shell.widget.WidgetProps` (pydantic, `extra="forbid"`, `frozen=True`), `shell.widget.NO_PROPS = WidgetProps()`, `shell.widget.Widget` (`build(self, props: WidgetProps) -> Gtk.Widget`, `destroy(self) -> None`). `shell.registry.register_widget(widget_id: str, *, title: str, props: type[WidgetProps] = WidgetProps, edge: PanelDefaults | None = None, corner: CornerDefaults | None = None) -> Callable[[type], type]` (ValueError at registration: no defaults, wrong defaults type, a title outside 1-40 characters or with a control character, a props model that is not a `WidgetProps`, a property named like a panel key or `widget_props`, a property without a default, a property of a type the settings window cannot show (anything but `str`, `int`, `bool`, a `Literal` of strings, or one of these `| None`: `widget 'odd': property 'odd' is of type float, which the settings window cannot show; use str, int, bool, a Literal of strings, or one of these | None`), bad defaults as before); `form_type_ok(annotation) -> bool`, `FORM_TYPES = (str, int, bool)`, `FORM_TYPES_TEXT`; `WidgetInfo(cls, title, props, edge, corner)`; `widget_names() -> list[str]`; `widget_class(id) -> type`; `widget_title(id) -> str`; `widget_props_model(id) -> type[WidgetProps]`; `supported_kinds(id) -> tuple[str, ...]` (edge before corner); `defaults(id, kind) -> PanelDefaults | CornerDefaults` (KeyError for an unknown widget or an unsupported kind); `widget_props(cfg: PanelConfig) -> WidgetProps` (ConfigError when invalid); `request_for(cfg)` (ConfigError for an unknown widget or an unsupported kind). `PanelRequest.name: str = ""`, `PanelRequest.props: WidgetProps = NO_PROPS`, the same two on `CornerRequest`. `registry.widget_kind` and `registry.register` are removed; `registry._DEFAULTS` is gone (`_WIDGETS: dict[str, WidgetInfo]`).

- [ ] **Step 1: Write the failing tests**

In `tests/conftest.py` replace

```python
from shell import registry
from shell.panel_spec import PanelDefaults


@pytest.fixture
def fake_registry(monkeypatch):
    monkeypatch.setattr(registry, "_WIDGETS", {})
    monkeypatch.setattr(registry, "_DEFAULTS", {})
    registry.register("dock", PanelDefaults(edge="bottom", length=560, depth=64, label="dock"))(
        type("Dock", (), {})
    )
    registry.register("clock", PanelDefaults(edge="top", length=168, depth=46, label="clock"))(
        type("Clock", (), {})
    )
    registry.register(
        "bar",
        PanelDefaults(edge="right", length=300, depth=56, pos=600, label="bar", state="collapsed"),
    )(type("Bar", (), {}))
    return registry

```

with

```python
from shell import registry
from shell.panel_spec import PanelDefaults
from shell.widget import Widget


@pytest.fixture
def fake_registry(monkeypatch):
    """Three edge widgets: dock (bottom), clock (top) and bar (right, pos 600, collapsed)."""
    monkeypatch.setattr(registry, "_WIDGETS", {})
    registry.register_widget(
        "dock", title="Dock", edge=PanelDefaults(edge="bottom", length=560, depth=64, label="dock")
    )(type("Dock", (Widget,), {}))
    registry.register_widget(
        "clock", title="Clock", edge=PanelDefaults(edge="top", length=168, depth=46, label="clock")
    )(type("Clock", (Widget,), {}))
    registry.register_widget(
        "bar",
        title="Bar",
        edge=PanelDefaults(
            edge="right", length=300, depth=56, pos=600, label="bar", state="collapsed"
        ),
    )(type("Bar", (Widget,), {}))
    return registry

```

In `tests/conftest.py` replace

```python
    from shell.panel_spec import CornerDefaults

    fake_registry.register(
        "box", CornerDefaults(corner="bottom-left", width=300, height=390, label="box")
    )(type("Box", (), {}))
    return fake_registry
```

with

```python
    from shell.panel_spec import CornerDefaults

    fake_registry.register_widget(
        "box",
        title="Box",
        corner=CornerDefaults(corner="bottom-left", width=300, height=390, label="box"),
    )(type("Box", (Widget,), {}))
    return fake_registry
```

In `tests/test_corner_requests.py` replace

```python
    default_edge,
)


```

with

```python
    default_edge,
)
from shell.widget import Widget


```

In `tests/test_corner_requests.py` replace

```python
    )
    assert req == CornerRequest(
        "box", "bottom-left", "bottom", 300, 390, "extended", "box", HandleSpec(), Interaction()
    )
    assert corner_registry.widget_kind("box") == "corner"
    assert corner_registry.widget_kind("dock") == "edge"


def test_a_widgets_defaults_are_public(corner_registry):
    """The settings window reads defaults(name), never _DEFAULTS."""
    assert corner_registry.defaults("box") == CornerDefaults(
        corner="bottom-left", width=300, height=390, label="box"
    )
    assert corner_registry.defaults("dock").edge == "bottom"
    with pytest.raises(KeyError):
        corner_registry.defaults("nope")


```

with

```python
    )
    assert req == CornerRequest(
        "box",
        "bottom-left",
        "bottom",
        300,
        390,
        "extended",
        "box",
        HandleSpec(),
        Interaction(),
        name="box",
    )
    assert corner_registry.supported_kinds("box") == ("corner",)
    assert corner_registry.supported_kinds("dock") == ("edge",)


def test_a_widgets_defaults_are_public(corner_registry):
    """The settings window reads defaults(name, kind), never _WIDGETS."""
    assert corner_registry.defaults("box", "corner") == CornerDefaults(
        corner="bottom-left", width=300, height=390, label="box"
    )
    assert corner_registry.defaults("dock", "edge").edge == "bottom"
    for name, kind in (("nope", "edge"), ("dock", "corner"), ("box", "edge"), ("box", "x")):
        with pytest.raises(KeyError):
            corner_registry.defaults(name, kind)


```

In `tests/test_corner_requests.py` replace

```python

def test_a_widget_edge_that_fits_the_new_corner_is_kept(corner_registry, make_config):
    corner_registry.register(
        "side", CornerDefaults(corner="bottom-left", width=200, height=300, label="s", edge="left")
    )(type("Side", (), {}))
    a, b = requests(
        corner_registry,
```

with

```python

def test_a_widget_edge_that_fits_the_new_corner_is_kept(corner_registry, make_config):
    corner_registry.register_widget(
        "side",
        title="Side",
        corner=CornerDefaults(corner="bottom-left", width=200, height=300, label="s", edge="left"),
    )(type("Side", (Widget,), {}))
    a, b = requests(
        corner_registry,
```

In `tests/test_corner_requests.py` replace

```python
def test_bad_corner_defaults_fail_at_registration(corner_registry, defaults, message):
    with pytest.raises(ValueError, match=message):
        corner_registry.register("bad", defaults)
    assert "bad" not in corner_registry.widget_names()

```

with

```python
def test_bad_corner_defaults_fail_at_registration(corner_registry, defaults, message):
    with pytest.raises(ValueError, match=message):
        corner_registry.register_widget("bad", title="Bad", corner=defaults)
    assert "bad" not in corner_registry.widget_names()

```

In `tests/test_handle_requests.py` replace

```python
from shell.panel_layout import layout_monitor
from shell.panel_spec import HandleSpec, Interaction, PanelDefaults


```

with

```python
from shell.panel_layout import layout_monitor
from shell.panel_spec import HandleSpec, Interaction, PanelDefaults
from shell.widget import Widget


```

In `tests/test_handle_requests.py` replace

```python
def grip(fake_registry):
    """A widget whose defaults set a handle and turn hover off."""
    fake_registry.register(
        "grip",
        PanelDefaults(
            edge="left",
            length=200,
```

with

```python
def grip(fake_registry):
    """A widget whose defaults set a handle and turn hover off."""
    fake_registry.register_widget(
        "grip",
        title="Grip",
        edge=PanelDefaults(
            edge="left",
            length=200,
```

In `tests/test_handle_requests.py` replace

```python
            interaction=Interaction(hover=False),
        ),
    )(type("Grip", (), {}))
    return fake_registry

```

with

```python
            interaction=Interaction(hover=False),
        ),
    )(type("Grip", (Widget,), {}))
    return fake_registry

```

In `tests/test_handle_requests.py` replace

```python
    defaults = PanelDefaults(edge="left", length=200, depth=40, label="bad", **bad)
    with pytest.raises(ValueError, match="widget 'bad': invalid handle or interaction default"):
        fake_registry.register("bad", defaults)
    assert "bad" not in fake_registry.widget_names()

```

with

```python
    defaults = PanelDefaults(edge="left", length=200, depth=40, label="bad", **bad)
    with pytest.raises(ValueError, match="widget 'bad': invalid handle or interaction default"):
        fake_registry.register_widget("bad", title="Bad", edge=defaults)
    assert "bad" not in fake_registry.widget_names()

```

In `tests/test_handle_requests.py` replace

```python
def mute(fake_registry):
    """A widget whose defaults turn every interaction off."""
    fake_registry.register(
        "mute",
        PanelDefaults(
            edge="left",
            length=200,
```

with

```python
def mute(fake_registry):
    """A widget whose defaults turn every interaction off."""
    fake_registry.register_widget(
        "mute",
        title="Mute",
        edge=PanelDefaults(
            edge="left",
            length=200,
```

In `tests/test_handle_requests.py` replace

```python
            interaction=Interaction(click=False, hover=False, drag=False),
        ),
    )(type("Mute", (), {}))
    return fake_registry

```

with

```python
            interaction=Interaction(click=False, hover=False, drag=False),
        ),
    )(type("Mute", (Widget,), {}))
    return fake_registry

```

In `tests/test_registry.py` replace

```python
from shell.config.models import ConfigError, PanelConfig
from shell.panel_spec import PanelDefaults, PanelRequest


def test_duplicate_registration_rejected(fake_registry):
    with pytest.raises(ValueError):
        registry.register("dock", PanelDefaults("top", 100, 40, "x"))(type("X", (), {}))


```

with

```python
from shell.config.models import ConfigError, PanelConfig
from shell.panel_spec import PanelDefaults, PanelRequest
from shell.widget import Widget


def test_duplicate_registration_rejected(fake_registry):
    with pytest.raises(ValueError):
        registry.register_widget("dock", title="X", edge=PanelDefaults("top", 100, 40, "x"))(
            type("X", (Widget,), {})
        )


```

In `tests/test_registry.py` replace

```python
        label="dock",
        fallback_length=560,
    )

```

with

```python
        label="dock",
        fallback_length=560,
        name="dock",
    )

```

In `tests/test_widget_kinds.py` replace

```python
"""Every registered widget builds the panel class its registration kind promises."""

import pytest
```

with

```python
"""Every registered widget builds the panel class of the kind it supports."""

import pytest
```

In `tests/test_widget_kinds.py` replace

```python
    for name in registry.widget_names():
        is_corner = issubclass(registry.widget_class(name), CornerPanel)
        assert is_corner == (registry.widget_kind(name) == "corner"), name
```

with

```python
    for name in registry.widget_names():
        is_corner = issubclass(registry.widget_class(name), CornerPanel)
        assert is_corner == (registry.supported_kinds(name) == ("corner",)), name
```

In `tests/test_widget_panel.py` replace

```python
    assert registry.widget_class("summary") is wp.WidgetPanel
    assert issubclass(wp.WidgetPanel, CornerPanel)
    assert registry.widget_kind("summary") == "corner"
    assert registry.defaults("summary") == CornerDefaults(
        corner="bottom-left", width=300, height=390, label="summary"
    )
```

with

```python
    assert registry.widget_class("summary") is wp.WidgetPanel
    assert issubclass(wp.WidgetPanel, CornerPanel)
    assert registry.supported_kinds("summary") == ("corner",)
    assert registry.widget_title("summary") == "Summary"
    assert registry.defaults("summary", "corner") == CornerDefaults(
        corner="bottom-left", width=300, height=390, label="summary"
    )
```

Create (or replace entirely) `tests/test_widget_registry.py`:

```python
"""register_widget, per-kind defaults and widget properties (panel/widget spec 3.4-3.5)."""

from typing import Annotated, Literal

import pytest
from pydantic import Field, create_model

from shell.config.diff import Change, diff_configs
from shell.config.models import ConfigError, PanelConfig
from shell.panel_spec import CornerDefaults, CornerRequest, PanelDefaults, PanelRequest
from shell.widget import NO_PROPS, Widget, WidgetProps

EDGE = PanelDefaults(edge="top", length=200, depth=50, label="tile")
CORNER = CornerDefaults(corner="top-right", width=240, height=200, label="tile")


class TileProps(WidgetProps):
    text: str = "hi"
    size: Annotated[int, Field(ge=6, le=96)] | None = None


@pytest.fixture
def tile(fake_registry):
    """A widget for both kinds, with two properties."""
    fake_registry.register_widget("tile", title="Tile", props=TileProps, edge=EDGE, corner=CORNER)(
        type("Tile", (Widget,), {})
    )
    return fake_registry


def mon(*panels):
    return {"HDMI-A-1": {"shell": "edge", "panels": list(panels)}}


def entry(**keys):
    return {"panel": "edge", "name": "Tile", "widget": "tile", **keys}


def test_a_widget_for_both_kinds_takes_the_defaults_of_the_entrys_kind(tile):
    assert tile.supported_kinds("tile") == ("edge", "corner")
    edge = tile.request_for(PanelConfig(**entry()))
    corner = tile.request_for(PanelConfig(**entry(panel="corner")))
    assert isinstance(edge, PanelRequest) and (edge.edge, edge.length, edge.depth) == (
        "top",
        200,
        50,
    )
    assert isinstance(corner, CornerRequest)
    assert (corner.corner, corner.edge, corner.width, corner.height) == (
        "top-right",
        "top",
        240,
        200,
    )
    assert tile.defaults("tile", "edge") is EDGE and tile.defaults("tile", "corner") is CORNER


def test_title_and_property_model_are_public(tile):
    assert tile.widget_title("tile") == "Tile"
    assert tile.widget_props_model("tile") is TileProps
    assert tile.widget_props_model("dock") is WidgetProps  # no properties


def test_requests_carry_the_name_and_the_validated_properties(tile):
    req = tile.request_for(PanelConfig(**entry(size=12)))
    assert req.name == "Tile"
    assert req.props == TileProps(text="hi", size=12)
    plain = tile.request_for(PanelConfig(panel="edge", name="D", widget="dock"))
    assert plain.props == NO_PROPS


def test_a_kind_the_widget_does_not_support_is_refused_by_request_for(fake_registry):
    with pytest.raises(ConfigError, match="dock cannot be shown in a corner panel"):
        fake_registry.request_for(PanelConfig(panel="corner", name="D", widget="dock"))


@pytest.mark.parametrize(
    ("keys", "message"),
    [
        ({"colour": "red"}, "monitors.HDMI-A-1.panels[0].colour: unknown key for widget 'tile'"),
        ({"size": 5}, "monitors.HDMI-A-1.panels[0].size: Input should be greater than or equal"),
        ({"text": 3}, "monitors.HDMI-A-1.panels[0].text: Input should be a valid string"),
    ],
)
def test_widget_keys_are_checked_against_the_widgets_model(tile, make_config, keys, message):
    with pytest.raises(ConfigError) as exc:
        tile.validate_widgets(make_config(monitors=mon(entry(**keys))))
    assert message in str(exc.value)


def test_good_widget_keys_pass(tile, make_config):
    tile.validate_widgets(make_config(monitors=mon(entry(text="ho", size=20))))


def test_the_supported_kinds_are_listed_when_a_kind_is_wrong(corner_registry, make_config):
    with pytest.raises(ConfigError) as exc:
        corner_registry.validate_widgets(
            make_config(monitors=mon({"panel": "edge", "name": "B", "widget": "box"}))
        )
    assert "box cannot be shown in an edge panel (it supports: corner)" in str(exc.value)


@pytest.mark.parametrize(
    ("change", "kind"),
    [
        ({"name": "Tile 2"}, "panel-rebuild"),
        ({"size": 30}, "panel-rebuild"),
        ({"text": "ho"}, "panel-rebuild"),
        ({"panel": "corner"}, "panel-rebuild"),
        ({"state": "collapsed"}, "panel-state"),
    ],
)
def test_a_name_or_property_change_rebuilds_the_panel(tile, make_config, change, kind):
    old = make_config(monitors=mon(entry()))
    new = make_config(monitors=mon(entry(**change)))
    assert diff_configs(old, new) == [Change(kind, "HDMI-A-1", 0)]


class Clash(WidgetProps):
    edge: str = "x"


class Sneaky(WidgetProps):
    widget_props: int = 0


class NoDefault(WidgetProps):
    text: str


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({}, "give edge or corner defaults"),
        ({"edge": EDGE, "props": Clash}, "property 'edge' has the name of a panel key"),
        ({"edge": EDGE, "props": Sneaky}, "property 'widget_props' has the name of a panel key"),
        ({"edge": EDGE, "props": NoDefault}, "every property needs a default"),
        ({"edge": EDGE, "props": dict}, "props must be a WidgetProps model"),
        ({"edge": CORNER}, "edge defaults must be PanelDefaults"),
        ({"corner": EDGE}, "corner defaults must be CornerDefaults"),
        ({"edge": EDGE, "title": ""}, "title must be 1-40 characters"),
        ({"edge": EDGE, "title": "T" * 41}, "title must be 1-40 characters"),
        ({"edge": EDGE, "title": "a\nb"}, "control characters"),
    ],
)
def test_a_bad_registration_fails_at_import(fake_registry, kwargs, message):
    kwargs = {"title": "Bad", **kwargs}
    with pytest.raises(ValueError, match=message):
        fake_registry.register_widget("bad", **kwargs)
    assert "bad" not in fake_registry.widget_names()


def test_the_widget_base_class_must_be_overridden():
    with pytest.raises(NotImplementedError):
        Widget().build(NO_PROPS)
    assert Widget().destroy() is None


def test_widget_props_are_frozen_and_strict():
    with pytest.raises(Exception, match="frozen"):
        TileProps().text = "x"
    with pytest.raises(Exception, match="Extra inputs"):
        TileProps(colour="red")


class Nested(WidgetProps):
    size: int = 1


@pytest.mark.parametrize(
    ("annotation", "default", "words"),
    [
        (float, 1.0, "type float"),
        (float | None, None, "type float | None"),
        (list[str], [], "type list"),
        (dict[str, int], {}, "type dict"),
        (Literal[1, 2], 1, "Literal[1, 2]"),
        (Nested, Nested(), "type Nested"),
    ],
)
def test_a_property_the_settings_window_cannot_show_is_refused(
    fake_registry, annotation, default, words
):
    model = create_model("Odd", __base__=WidgetProps, odd=(annotation, default))
    with pytest.raises(ValueError) as exc:
        fake_registry.register_widget("odd", title="Odd", props=model, edge=EDGE)
    text = str(exc.value)
    assert "widget 'odd': property 'odd'" in text and words in text
    assert "str, int, bool, a Literal of strings" in text
    assert "odd" not in fake_registry.widget_names()


@pytest.mark.parametrize(
    ("annotation", "default"),
    [
        (str, "x"),
        (int, 1),
        (bool, False),
        (Literal["a", "b"], "a"),
        (Annotated[int, Field(ge=1, le=9)] | None, None),
        (str | None, None),
    ],
)
def test_the_property_types_the_settings_window_shows_are_accepted(
    fake_registry, annotation, default
):
    model = create_model("Fine", __base__=WidgetProps, fine=(annotation, default))
    fake_registry.register_widget("fine", title="Fine", props=model, edge=EDGE)(
        type("FineWidget", (Widget,), {})
    )
    assert fake_registry.widget_props_model("fine") is model
```


- [ ] **Step 2: Run them to verify they fail**

Run: `scripts/py -m pytest -q tests/test_widget_registry.py tests/test_registry.py`
Expected: `ImportError while loading conftest ... tests/conftest.py`, `ModuleNotFoundError: No module named 'shell.widget'`.

- [ ] **Step 3: Implement**

In `settings/form.py` replace

```python

    def panel_for(self, kind: str, corner: str | None = None) -> SectionSpec:
        """The section of a panel entry whose widget is of `kind` (registry.widget_kind:
        "edge" or "corner"). Given the `corner` in effect, a corner panel's edge row offers
        only that corner's two edges (corner.split("-"))."""
        if kind == "edge":
```

with

```python

    def panel_for(self, kind: str, corner: str | None = None) -> SectionSpec:
        """The section of a panel entry of `kind` (its `panel` key: "edge" or
        "corner"). Given the `corner` in effect, a corner panel's edge row offers
        only that corner's two edges (corner.split("-"))."""
        if kind == "edge":
```

In `settings/form.py` replace

```python
def config_form(widgets: tuple[str, ...], corner_widgets: tuple[str, ...] = ()) -> ConfigForm:
    """Every section the settings window shows; `widgets` is registry.widget_names() and
    `corner_widgets` those whose registry.widget_kind is "corner".

    Per-monitor overrides use the base models (Theme, LayoutSettings), not ThemeOverride /
```

with

```python
def config_form(widgets: tuple[str, ...], corner_widgets: tuple[str, ...] = ()) -> ConfigForm:
    """Every section the settings window shows; `widgets` is registry.widget_names() and
    `corner_widgets` those shown in a corner panel (registry.supported_kinds).

    Per-monitor overrides use the base models (Theme, LayoutSettings), not ThemeOverride /
```

In `settings/panels.py` replace

```python
from settings.values import new_panel_entry
from shell.panel_spec import CornerRequest, PanelRequest
from shell.registry import widget_kind

Edit = Callable[[UserDocument], Any]
```

with

```python
from settings.values import new_panel_entry
from shell.panel_spec import CornerRequest, PanelRequest

Edit = Callable[[UserDocument], Any]
```

In `settings/panels.py` replace

```python
    edges of the corner it is in."""
    corner = req.corner if isinstance(req, CornerRequest) else None
    return form.panel_for(widget_kind(req.widget), corner)


```

with

```python
    edges of the corner it is in."""
    corner = req.corner if isinstance(req, CornerRequest) else None
    return form.panel_for("edge" if corner is None else "corner", corner)


```

In `settings/values.py` replace

```python
A field is addressed by its TOML key path (settings.document.Path_). `is_set` says the user
file sets that key (the row's reset button removes it); `source` names where an unset value
is inherited from. Panel entries are edge or corner panels (spec 19): the kind comes from the
widget (registry.widget_kind) and decides which keys the entry takes.
"""

```

with

```python
A field is addressed by its TOML key path (settings.document.Path_). `is_set` says the user
file sets that key (the row's reset button removes it); `source` names where an unset value
is inherited from. Panel entries are edge or corner panels (spec 19): the entry's `panel`
key is its kind and decides which keys the entry takes.
"""

```

In `settings/values.py` replace

```python
from shell.panel_layout import layout_monitor
from shell.panel_spec import CornerDefaults, CornerRequest, corner_has_edge, default_edge
from shell.registry import defaults, request_for, requests_for, widget_kind

# keys whose value in effect is the request's (the entry's, else the widget's default)
```

with

```python
from shell.panel_layout import layout_monitor
from shell.panel_spec import CornerDefaults, CornerRequest, corner_has_edge, default_edge
from shell.registry import defaults, request_for, requests_for, supported_kinds

# keys whose value in effect is the request's (the entry's, else the widget's default)
```

In `settings/values.py` replace

```python
    entry = config.monitor(name).panels[index]
    req = request_for(entry)
    d = defaults(entry.widget)  # public registry API: never registry._DEFAULTS
    key = keys[0]
    if key == "interaction":
```

with

```python
    entry = config.monitor(name).panels[index]
    req = request_for(entry)
    d = defaults(entry.widget, entry.panel)  # public registry API: never _WIDGETS
    key = keys[0]
    if key == "interaction":
```

In `settings/values.py` replace

```python
    (("set" | "unset", key, value)) applied as ONE edit: one write, one reload.

    - A widget of the other kind also sets `panel` to that kind and unsets the keys only the
      old kind takes (a dock turned into a corner widget loses its align, length, ...; spec
      19), else the shell rejects it. The entry keeps its name.
    - `value` None for "corner" is a reset: the key is unset and the widget's corner applies.
    - An unknown widget is a plain set (the session's check rejects it, ConfigError).
```

with

```python
    (("set" | "unset", key, value)) applied as ONE edit: one write, one reload.

    - A widget that cannot be shown in the entry's kind also sets `panel` to the first kind
      it supports and unsets the keys only the old kind takes (a dock turned into a corner
      widget loses its align, length, ...; spec 19), else the shell rejects it. The entry
      keeps its name.
    - `value` None for "corner" is a reset: the key is unset and the widget's corner applies.
    - An unknown widget is a plain set (the session's check rejects it, ConfigError).
```

In `settings/values.py` replace

```python
    if key == "widget":
        try:
            kind = widget_kind(value)
        except KeyError:  # unknown widget: the session's check rejects it with the shell's text
            return ops
        if entry.get("panel") != kind:
            ops.append(("set", "panel", kind))
```

with

```python
    if key == "widget":
        try:
            kinds = supported_kinds(value)
        except KeyError:  # unknown widget: the session's check rejects it with the shell's text
            return ops
        kind = entry.get("panel") if entry.get("panel") in kinds else kinds[0]
        if entry.get("panel") != kind:
            ops.append(("set", "panel", kind))
```

In `settings/values.py` replace

```python
        ops += [("unset", k, None) for k in stale if k in entry]
        if kind == "corner":
            corner = entry.get("corner", defaults(value).corner)
    elif key == "corner":
        corner = value or defaults(entry["widget"]).corner
    edge = entry.get("edge")
    if corner is not None and edge is not None and not corner_has_edge(corner, edge):
```

with

```python
        ops += [("unset", k, None) for k in stale if k in entry]
        if kind == "corner":
            corner = entry.get("corner", defaults(value, "corner").corner)
    elif key == "corner":
        corner = value or defaults(entry["widget"], "corner").corner
    edge = entry.get("edge")
    if corner is not None and edge is not None and not corner_has_edge(corner, edge):
```

In `settings/values.py` replace

```python
    session's check rejects it with the shell's text)."""
    try:
        kind = widget_kind(widget)
    except KeyError:
        kind = "edge"
```

with

```python
    session's check rejects it with the shell's text)."""
    try:
        kind = supported_kinds(widget)[0]
    except KeyError:
        kind = "edge"
```

In `settings/view.py` replace

```python
from shell.config.models import ConfigError
from shell.outputs import Output
from shell.registry import requests_for, widget_kind, widget_names

Edit = Callable[[UserDocument], Any]
```

with

```python
from shell.config.models import ConfigError
from shell.outputs import Output
from shell.registry import requests_for, supported_kinds, widget_names

Edit = Callable[[UserDocument], Any]
```

In `settings/view.py` replace

```python
        self.outputs = {o.name: o for o in outputs}
        names = tuple(widget_names())
        corner = tuple(n for n in names if widget_kind(n) == "corner")
        self.form = config_form(names, corner)
        self.rows: list[FieldRow] = []
```

with

```python
        self.outputs = {o.name: o for o in outputs}
        names = tuple(widget_names())
        corner = tuple(n for n in names if supported_kinds(n)[0] == "corner")
        self.form = config_form(names, corner)
        self.rows: list[FieldRow] = []
```

In `shell/panel_spec.py` replace

```python

from shell.config.models import Align, Corner, Edge, HandleShape, PanelState

LengthSpec = int | str  # px, "fill", "content" or "NN%" (validated by shell.config.models)
```

with

```python

from shell.config.models import Align, Corner, Edge, HandleShape, PanelState
from shell.widget import NO_PROPS, WidgetProps

LengthSpec = int | str  # px, "fill", "content" or "NN%" (validated by shell.config.models)
```

In `shell/panel_spec.py` replace

```python
    # Not part of the layout (PanelGeometry): a change is applied to the live panel in place.
    handle: HandleSpec = HandleSpec()
    interaction: Interaction = Interaction()


@dataclass(frozen=True)
```

with

```python
    # Not part of the layout (PanelGeometry): a change is applied to the live panel in place.
    handle: HandleSpec = HandleSpec()
    interaction: Interaction = Interaction()
    # Not part of the layout either; a change rebuilds the panel (shell.config.diff).
    name: str = ""
    props: WidgetProps = NO_PROPS


@dataclass(frozen=True)
```

In `shell/panel_spec.py` replace

```python
def default_edge(corner: Corner) -> Edge:
    """The edge a corner panel opens from unless told otherwise: the corner's top or bottom
    edge (the spec's widget_panel rises out of the bottom edge)."""
    return corner.split("-")[0]  # type: ignore[return-value]

```

with

```python
def default_edge(corner: Corner) -> Edge:
    """The edge a corner panel opens from unless told otherwise: the corner's top or bottom
    edge (the summary block rises out of the bottom edge)."""
    return corner.split("-")[0]  # type: ignore[return-value]

```

In `shell/panel_spec.py` replace

```python
    label: str
    handle: HandleSpec = HandleSpec()
    interaction: Interaction = Interaction()


@dataclass(frozen=True)
```

with

```python
    label: str
    handle: HandleSpec = HandleSpec()
    interaction: Interaction = Interaction()
    name: str = ""  # as PanelRequest: a change rebuilds the panel
    props: WidgetProps = NO_PROPS


@dataclass(frozen=True)
```

Create (or replace entirely) `shell/registry.py`:

```python
"""Widget registry: id -> widget class, display title, property model and per-kind default
geometry (panel/widget spec 3.4-3.5). Pure (no GTK)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from types import UnionType
from typing import Annotated, Literal, Union, get_args, get_origin

from pydantic import ValidationError

from shell.config.models import (
    CORNER_ONLY_KEYS,
    CORNERS,
    EDGE_ONLY_KEYS,
    FRAMEWORK_KEYS,
    Config,
    ConfigError,
    HandleConfig,
    InteractionConfig,
    PanelConfig,
    PanelState,
    check_panel_name,
)
from shell.panel_spec import (
    CornerDefaults,
    CornerRequest,
    HandleSpec,
    Interaction,
    PanelDefaults,
    PanelRequest,
    corner_has_edge,
    default_edge,
)
from shell.widget import WidgetProps


@dataclass(frozen=True)
class WidgetInfo:
    """One registration: the class, its display title, its property model and the defaults
    of each panel kind it can be shown in (None: not in that kind)."""

    cls: type
    title: str
    props: type[WidgetProps]
    edge: PanelDefaults | None
    corner: CornerDefaults | None


_WIDGETS: dict[str, WidgetInfo] = {}
# The property types the settings window has a row for (settings.form: a text row, a spin
# button, a switch; a Literal of strings is a combo): anything else is refused at registration.
FORM_TYPES = (str, int, bool)
FORM_TYPES_TEXT = "str, int, bool, a Literal of strings, or one of these | None"
_PLACEMENT = ("pos", "align", "offset")
_KINDS = ("edge", "corner")  # the order supported_kinds lists them in


def register_widget(
    widget_id: str,
    *,
    title: str,
    props: type[WidgetProps] = WidgetProps,
    edge: PanelDefaults | None = None,
    corner: CornerDefaults | None = None,
) -> Callable[[type], type]:
    """Register a widget class. It can be shown in an edge panel when it has `edge` defaults
    and in a corner panel when it has `corner` defaults (both may be given). `title` is its
    name in the settings window and a new panel's name; `props` its property model. Bad
    defaults, a bad title or a property named like a panel key fail here, at import, before
    any window exists."""
    _check_registration(widget_id, title, props, edge, corner)

    def decorate(cls: type) -> type:
        if widget_id in _WIDGETS:
            raise ValueError(f"widget {widget_id!r} is already registered")
        _WIDGETS[widget_id] = WidgetInfo(cls, title, props, edge, corner)
        return cls

    return decorate


def form_type_ok(annotation: object) -> bool:
    """True when the settings window can show a property of this type (FORM_TYPES_TEXT)."""
    origin = get_origin(annotation)
    if origin is Annotated:
        return form_type_ok(get_args(annotation)[0])
    if origin in (Union, UnionType):
        options = [a for a in get_args(annotation) if a is not type(None)]
        return len(options) == 1 and form_type_ok(options[0])
    if origin is Literal:
        return all(isinstance(v, str) for v in get_args(annotation))
    return annotation in FORM_TYPES


def _check_registration(
    widget_id: str,
    title: str,
    props: type[WidgetProps],
    edge: PanelDefaults | None,
    corner: CornerDefaults | None,
) -> None:
    if edge is None and corner is None:
        raise ValueError(f"widget {widget_id!r}: give edge or corner defaults (or both)")
    if edge is not None and not isinstance(edge, PanelDefaults):
        raise ValueError(f"widget {widget_id!r}: edge defaults must be PanelDefaults")
    if corner is not None and not isinstance(corner, CornerDefaults):
        raise ValueError(f"widget {widget_id!r}: corner defaults must be CornerDefaults")
    if not 1 <= len(title) <= 40:
        raise ValueError(f"widget {widget_id!r}: title must be 1-40 characters")
    check_panel_name(title)  # it becomes a new panel's name
    if not (isinstance(props, type) and issubclass(props, WidgetProps)):
        raise ValueError(f"widget {widget_id!r}: props must be a WidgetProps model")
    clash = sorted(set(props.model_fields) & (FRAMEWORK_KEYS | {"widget_props"}))
    if clash:
        raise ValueError(
            f"widget {widget_id!r}: property {clash[0]!r} has the name of a panel key; rename it"
        )
    for name, field in props.model_fields.items():
        if not form_type_ok(field.annotation):
            kind = field.annotation
            kind = kind.__name__ if isinstance(kind, type) else repr(kind).replace("typing.", "")
            raise ValueError(
                f"widget {widget_id!r}: property {name!r} is of type {kind}, which the settings "
                f"window cannot show; use {FORM_TYPES_TEXT}"
            )
    try:
        props()
    except ValidationError as exc:
        raise ValueError(f"widget {widget_id!r}: every property needs a default: {exc}") from None
    for d in (edge, corner):
        if d is not None:
            _check_defaults(widget_id, d)


def _check_defaults(name: str, defaults: PanelDefaults | CornerDefaults) -> None:
    """Widget defaults do not pass through the config models: check the handle and interaction
    ones with the same rules as a config entry (spec 15: shape, size 4-40, weight 1-8, offset,
    #rrggbb[aa] colours, strict booleans)."""
    try:
        HandleConfig.model_validate(asdict(defaults.handle))
        InteractionConfig.model_validate(asdict(defaults.interaction))
    except ValidationError as exc:
        raise ValueError(f"widget {name!r}: invalid handle or interaction default: {exc}") from exc
    if isinstance(defaults, CornerDefaults):
        if defaults.corner not in CORNERS:
            raise ValueError(
                f"widget {name!r}: corner {defaults.corner!r} must be one of {', '.join(CORNERS)}"
            )
        states = get_args(PanelState)
        if defaults.state not in states:
            raise ValueError(
                f"widget {name!r}: state {defaults.state!r} must be {' or '.join(states)}"
            )
        if defaults.edge is not None and not corner_has_edge(defaults.corner, defaults.edge):
            raise ValueError(
                f"widget {name!r}: edge {defaults.edge!r} is not an edge of {defaults.corner}"
            )
        if not (60 <= defaults.width <= 4000 and 60 <= defaults.height <= 4000):
            raise ValueError(f"widget {name!r}: width and height must be 60-4000 px")


def widget_names() -> list[str]:
    return sorted(_WIDGETS)


def widget_class(name: str) -> type:
    """KeyError for an unknown widget (like every lookup here)."""
    return _WIDGETS[name].cls


def widget_title(name: str) -> str:
    """The display name: the settings window's widget list and a new panel's name."""
    return _WIDGETS[name].title


def widget_props_model(name: str) -> type[WidgetProps]:
    """The widget's property model (the settings window builds its Widget rows from it)."""
    return _WIDGETS[name].props


def supported_kinds(name: str) -> tuple[str, ...]:
    """The panel kinds the widget can be shown in, edge before corner."""
    info = _WIDGETS[name]
    return tuple(k for k in _KINDS if getattr(info, k) is not None)


def defaults(name: str, kind: str) -> PanelDefaults | CornerDefaults:
    """The widget's registered defaults for a panel kind (the settings window shows them; it
    never reads _WIDGETS). KeyError for an unknown widget or a kind it does not support."""
    d = getattr(_WIDGETS[name], kind) if kind in _KINDS else None
    if d is None:
        raise KeyError(f"{name} has no {kind} panel defaults")
    return d


def widget_props(cfg: PanelConfig) -> WidgetProps:
    """The entry's widget keys, validated by the widget's model (defaults filled in)."""
    try:
        return _WIDGETS[cfg.widget].props.model_validate(cfg.widget_props)
    except ValidationError as exc:
        raise ConfigError(f"{cfg.widget} properties: {exc}") from None


def _in_a(kind: str) -> str:
    return f"{'an' if kind == 'edge' else 'a'} {kind} panel"


def request_for(cfg: PanelConfig) -> PanelRequest | CornerRequest:
    """The defaults of the entry's panel kind overlaid with the entry. Placement is taken as a
    whole: if the entry sets any of pos / align / offset, the widget's default placement is
    dropped and the keys it leaves out are align = "center", offset = 0 (`pos = "center"` is
    align = "center"). Without any of them the widget's default placement applies."""
    info = _WIDGETS.get(cfg.widget)
    if info is None:
        known = ", ".join(widget_names()) or "none"
        raise ConfigError(f"unknown widget {cfg.widget!r} (known: {known})")
    if cfg.panel not in supported_kinds(cfg.widget):
        raise ConfigError(f"{cfg.widget} cannot be shown in {_in_a(cfg.panel)}")
    props = widget_props(cfg)
    if cfg.panel == "corner":
        return _corner_request(cfg, info.corner, props)
    d = info.edge
    if any(getattr(cfg, key) is not None for key in _PLACEMENT):
        pos = None if cfg.pos in (None, "center") else cfg.pos
        align, offset = cfg.align or "center", cfg.offset or 0
    else:
        pos, align, offset = d.pos, d.align, d.offset
    return PanelRequest(
        widget=cfg.widget,
        edge=cfg.edge or d.edge,
        align=align,
        offset=offset,
        pos=pos,
        order=cfg.order or 0,
        length=d.length if cfg.length is None else cfg.length,
        min_length=cfg.min_length,
        max_length=cfg.max_length,
        depth=cfg.depth or d.depth,
        state=cfg.state or d.state,
        label=d.label,
        fallback_length=d.length,
        handle=_handle(cfg, d.handle),
        interaction=_interaction(cfg, d.interaction),
        name=cfg.name,
        props=props,
    )


def _corner_request(cfg: PanelConfig, d: CornerDefaults, props: WidgetProps) -> CornerRequest:
    """A corner widget's defaults overlaid with one entry. The edge it opens from: the entry's,
    else the widget's when it is an edge of the corner, else the corner's top or bottom edge
    (so moving a panel to another corner never leaves it with an impossible edge)."""
    corner = cfg.corner or d.corner
    edge = cfg.edge or d.edge
    if edge is None or not corner_has_edge(corner, edge):
        edge = default_edge(corner)
    return CornerRequest(
        widget=cfg.widget,
        corner=corner,
        edge=edge,
        width=cfg.width or d.width,
        height=cfg.height or d.height,
        state=cfg.state or d.state,
        label=d.label,
        handle=_handle(cfg, d.handle),
        interaction=_interaction(cfg, d.interaction),
        name=cfg.name,
        props=props,
    )


def _handle(cfg: PanelConfig, default: HandleSpec) -> HandleSpec:
    """Key by key: the entry's [handle] value, else the widget's default (None = the theme's)."""
    own = cfg.handle
    return HandleSpec(
        **{
            key: getattr(default, key) if getattr(own, key) is None else getattr(own, key)
            for key in ("shape", "size", "weight", "offset", "color", "hover_color")
        }
    )


def _interaction(cfg: PanelConfig, default: Interaction) -> Interaction:
    own = cfg.interaction
    return Interaction(
        **{
            key: getattr(default, key) if getattr(own, key) is None else getattr(own, key)
            for key in ("click", "hover", "drag")
        }
    )


def requests_for(config: Config, monitor: str) -> list[PanelRequest | CornerRequest]:
    return [request_for(p) for p in config.monitor(monitor).panels]


def deprecated_pos_paths(config: Config) -> list[str]:
    """Key paths of the panel entries that still use the deprecated `pos` (decision 2:
    EdgeShellApp logs them once per config load; never notified)."""
    return [
        f"monitors.{name}.panels.{i}.pos"
        for name, mon in config.monitors.items()
        for i, panel in enumerate(mon.panels)
        if panel.pos is not None
    ]


def moved_default_paths(config: Config) -> list[str]:
    """Key paths of the `system_bar` entries whose old default place changed: they set edge,
    length or depth but none of pos / align / offset, so the built-in default placement
    (align = "end", offset = 142; it was pos = 600) applies to a bar that is no longer the
    default size or edge. Logged once per config load by EdgeShellApp."""
    return [
        f"monitors.{name}.panels.{i}"
        for name, mon in config.monitors.items()
        for i, panel in enumerate(mon.panels)
        if panel.widget == "system_bar"
        and panel.panel == "edge"
        and any(v is not None for v in (panel.edge, panel.length, panel.depth))
        and all(getattr(panel, k) is None for k in _PLACEMENT)
    ]


_ALL_OFF = Interaction(click=False, hover=False, drag=False)


def _supports(panel: PanelConfig) -> bool:
    return panel.widget in _WIDGETS and panel.panel in supported_kinds(panel.widget)


def all_off_paths(config: Config) -> list[str]:
    """Key paths of the panel entries whose click, hover and drag are all off (entry over the
    widget's default): they open and close only through `state` (decision 7). EdgeShellApp
    logs them once per config load; unknown widgets and kinds are left to validate_widgets."""
    return [
        f"monitors.{name}.panels.{i}"
        for name, mon in config.monitors.items()
        for i, panel in enumerate(mon.panels)
        if _supports(panel)
        and _interaction(panel, defaults(panel.widget, panel.panel).interaction) == _ALL_OFF
    ]


def _kind_problems(where: str, panel: PanelConfig) -> list[str]:
    """Keys an entry sets that its panel kind does not take (spec 19)."""
    if panel.panel == "corner":
        wrong = [k for k in EDGE_ONLY_KEYS if getattr(panel, k) is not None]
        problems = [
            f"{where}.{key}: a corner panel takes corner, edge, width and height, not {key}"
            for key in wrong
        ]
        corner = panel.corner or defaults(panel.widget, "corner").corner
        if panel.edge is not None and not corner_has_edge(corner, panel.edge):
            first, second = corner.split("-")
            problems.append(
                f"{where}.edge: {panel.edge!r} is not an edge of the {corner} corner "
                f"(use {first} or {second})"
            )
        return problems
    return [
        f"{where}.{key}: an edge panel takes no {key}; corner, width and height only apply "
        "to corner panels"
        for key in CORNER_ONLY_KEYS
        if getattr(panel, key) is not None
    ]


def _props_problems(where: str, panel: PanelConfig) -> list[str]:
    """The entry's widget keys against the widget's property model."""
    try:
        _WIDGETS[panel.widget].props.model_validate(panel.widget_props)
    except ValidationError as exc:
        problems = []
        for error in exc.errors():
            key = ".".join(str(p) for p in error["loc"])
            if error["type"] == "extra_forbidden":
                problems.append(f"{where}.{key}: unknown key for widget {panel.widget!r}")
            else:
                problems.append(f"{where}.{key}: {error['msg']}")
        return problems
    return []


def _name_problems(where: str, panels: list[PanelConfig]) -> list[str]:
    """A name used twice on one monitor: reported at every later use, naming the first."""
    first: dict[str, int] = {}
    problems = []
    for i, panel in enumerate(panels):
        if panel.name in first:
            problems.append(
                f"{where}[{i}].name: names must be unique: {panel.name!r} is used by "
                f"panels[{first[panel.name]}] and panels[{i}]"
            )
        else:
            first[panel.name] = i
    return problems


def _entry_problems(where: str, panel: PanelConfig) -> list[str]:
    if panel.panel == "float":
        return [f"{where}.panel: float panels are not implemented yet"]
    if panel.widget not in _WIDGETS:
        return [f"{where}.widget: unknown widget {panel.widget!r}"]
    kinds = supported_kinds(panel.widget)
    if panel.panel not in kinds:
        return [
            f"{where}.panel: {panel.widget} cannot be shown in {_in_a(panel.panel)} "
            f"(it supports: {', '.join(kinds)})"
        ]
    return _kind_problems(where, panel) + _props_problems(where, panel)


def validate_widgets(config: Config) -> None:
    problems = []
    for name, mon in config.monitors.items():
        for i, panel in enumerate(mon.panels):
            problems.extend(_entry_problems(f"monitors.{name}.panels[{i}]", panel))
        problems.extend(_name_problems(f"monitors.{name}.panels", mon.panels))
    if problems:
        known = ", ".join(widget_names()) or "none"
        raise ConfigError("\n".join(problems) + f"\nknown widgets: {known}")
```

Create (or replace entirely) `shell/widget.py`:

```python
"""What a panel shows: a Widget and its property model (panel/widget spec 3.4). Pure: no GTK
import here (a widget's build() creates its Gtk widgets; widgets/ holds the real ones)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class WidgetProps(BaseModel):
    """A widget's own properties: the keys of a panel entry that are not panel keys
    (shell.config.models.FRAMEWORK_KEYS), validated by shell.registry.validate_widgets. Every
    property has a default (an entry may leave any of them out); unknown keys are rejected."""

    model_config = ConfigDict(extra="forbid", frozen=True)


NO_PROPS = WidgetProps()  # the properties of a widget that has none


class Widget:
    """The content of one panel. The panel window (shell.edge_panel.EdgePanel, or CornerPanel
    for a corner panel) gets a new instance, calls build(props) once for its content and
    destroy() once when the window is destroyed (a config reload rebuilds panels, a hot-plug
    closes a monitor): stop timers and watches there."""

    def build(self, props: WidgetProps) -> Any:
        """The content: a Gtk.Widget, centred in the panel's body."""
        raise NotImplementedError

    def destroy(self) -> None:
        """Stop what build() started. The default has nothing to stop."""
```

In `widgets/clock.py` replace

```python
from shell.edge_panel import EdgePanel
from shell.panel_spec import PanelDefaults
from shell.registry import register

REFRESH_MS = 1000  # the minute rolls over within a second of the real change
```

with

```python
from shell.edge_panel import EdgePanel
from shell.panel_spec import PanelDefaults
from shell.registry import register_widget

REFRESH_MS = 1000  # the minute rolls over within a second of the real change
```

In `widgets/clock.py` replace

```python


@register("clock", PanelDefaults(edge="top", length=168, depth=46, label="clock"))
class ClockPanel(EdgePanel):
    def build_content(self):
```

with

```python


@register_widget(
    "clock", title="Clock", edge=PanelDefaults(edge="top", length=168, depth=46, label="clock")
)
class ClockPanel(EdgePanel):
    def build_content(self):
```

In `widgets/dock.py` replace

```python
from shell.edge_panel import EdgePanel
from shell.panel_spec import PanelDefaults
from shell.registry import register

APPS = [  # (tooltip, icon name, command)
```

with

```python
from shell.edge_panel import EdgePanel
from shell.panel_spec import PanelDefaults
from shell.registry import register_widget

APPS = [  # (tooltip, icon name, command)
```

In `widgets/dock.py` replace

```python


@register("dock", PanelDefaults(edge="bottom", length=560, depth=64, label="dock"))
class DockPanel(EdgePanel):
    def build_content(self):
```

with

```python


@register_widget(
    "dock", title="Dock", edge=PanelDefaults(edge="bottom", length=560, depth=64, label="dock")
)
class DockPanel(EdgePanel):
    def build_content(self):
```

In `widgets/system_bar.py` replace

```python
from shell.edge_panel import EdgePanel
from shell.panel_spec import PanelDefaults
from shell.registry import register


@register(
    "system_bar",
    # y = 600 on a 1080 px tall monitor (free span ends at 1042: 1042 - 142 - 300 = 600).
    # Same as the old pos = 600 only with edge right (or left), length 300, depth >= 28 and
    # the default thickness/radius; an entry overriding edge, length or depth moves (the app
    # logs those entries).
    PanelDefaults(edge="right", length=300, depth=56, label="system bar", align="end", offset=142),
)
class SystemBarPanel(EdgePanel):
```

with

```python
from shell.edge_panel import EdgePanel
from shell.panel_spec import PanelDefaults
from shell.registry import register_widget


@register_widget(
    "system_bar",
    title="System bar",
    # y = 600 on a 1080 px tall monitor (free span ends at 1042: 1042 - 142 - 300 = 600).
    # Same as the old pos = 600 only with edge right (or left), length 300, depth >= 28 and
    # the default thickness/radius; an entry overriding edge, length or depth moves (the app
    # logs those entries).
    edge=PanelDefaults(
        edge="right", length=300, depth=56, label="system bar", align="end", offset=142
    ),
)
class SystemBarPanel(EdgePanel):
```

In `widgets/widget_panel.py` replace

```python
from shell.corner_panel import CornerPanel
from shell.panel_spec import CornerDefaults
from shell.registry import register
from widgets.clock import format_time

```

with

```python
from shell.corner_panel import CornerPanel
from shell.panel_spec import CornerDefaults
from shell.registry import register_widget
from widgets.clock import format_time

```

In `widgets/widget_panel.py` replace

```python


@register(
    "summary",
    CornerDefaults(corner="bottom-left", width=300, height=390, label="summary"),
)
class WidgetPanel(CornerPanel):
```

with

```python


@register_widget(
    "summary",
    title="Summary",
    corner=CornerDefaults(corner="bottom-left", width=300, height=390, label="summary"),
)
class WidgetPanel(CornerPanel):
```


- [ ] **Step 4: Run the tests to verify they pass**

Run: `scripts/py -m pytest -q tests/test_widget_registry.py tests/test_registry.py tests/test_corner_requests.py tests/test_handle_requests.py tests/test_widget_kinds.py tests/test_widget_panel.py`
Expected: all pass (`tests/test_widget_registry.py`: 38 tests).

- [ ] **Step 5: VERIFY and commit**

Run VERIFY. Expected: `1960 passed`, `All checks passed!`. Also `grep -rn "widget_kind\|_DEFAULTS\|registry.register(" shell settings widgets tests` prints nothing.

```bash
git add shell/widget.py shell/registry.py shell/panel_spec.py widgets/dock.py widgets/clock.py widgets/system_bar.py widgets/widget_panel.py settings/values.py settings/panels.py settings/view.py settings/form.py tests/test_widget_registry.py tests/conftest.py tests/test_registry.py tests/test_corner_requests.py tests/test_handle_requests.py tests/test_widget_kinds.py tests/test_widget_panel.py
git commit -m "feat(registry): register_widget with a title, a property model and per-kind defaults" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

**Reviewer mutations:** the kind taken from the widget's first registration instead of `cfg.panel` (`test_a_widget_for_both_kinds_takes_the_defaults_of_the_entrys_kind`); the property-name collision check removed (`test_a_bad_registration_fails_at_import`); `props` left off the request (`test_requests_carry_the_name_and_the_validated_properties`, `test_a_name_or_property_change_rebuilds_the_panel`); the widget-key errors dropped from `validate_widgets` (`test_widget_keys_are_checked_against_the_widgets_model`); the property-type check removed (`test_a_property_the_settings_window_cannot_show_is_refused`).

---

### Task 4: Panel windows host a `Widget`; the four widgets are ported

`EdgePanel` and `CornerPanel` stop being base classes for widgets. `MonitorShell._new_panel` picks the window class from the geometry (`panel_class`: `CornerPanel` for a corner panel, else `EdgePanel`), creates a new instance of the request's widget and passes it with the request's props; `EdgePanel.build_content` (still the one seam) returns `widget.build(props)`, and the window's `destroy` signal calls `widget.destroy()` once. `widget_panel.py` becomes `summary.py`.

**Files:**
- Modify: `shell/edge_panel.py` (`widget` / `props` kwargs, `build_content`, `_on_destroy`), `shell/corner_panel.py` (docstring), `shell/monitors.py` (`panel_class`, the widget instance), `shell/theme.py` (`#summary-time`)
- Modify: `widgets/dock.py`, `widgets/clock.py`, `widgets/system_bar.py` (Widget classes), `widgets/__init__.py`
- Rename + rewrite: `widgets/widget_panel.py` -> `widgets/summary.py`; `tests/test_widget_panel.py` -> `tests/test_summary.py`
- Modify: `tests/test_widget_kinds.py` (rewritten), `tests/test_clock.py`, `tests/test_monitor_shell.py`

**Interfaces:**
- Consumes: `Widget`, `WidgetProps`, `NO_PROPS` (`shell/widget.py`), `register_widget`, `widget_class`, `supported_kinds`, `widget_title` (Task 3), `PanelRequest.props` / `CornerRequest.props`.
- Produces: `EdgePanel.__init__(..., on_settings=None, widget: Widget | None = None, props: WidgetProps = NO_PROPS)`; `EdgePanel.build_content() -> Gtk.Widget` (`widget.build(props)`, an empty `Box` without a widget); `EdgePanel._on_destroy(*args)` (calls `widget.destroy()` once); `shell.monitors.panel_class(geo: PanelGeometry | CornerGeometry) -> type[EdgePanel]`; widget classes `widgets.dock.DockWidget`, `widgets.clock.ClockWidget`, `widgets.system_bar.SystemBarWidget`, `widgets.summary.SummaryWidget` (title `"Summary"`; each with `build(props)` and, where it has a timer, `destroy()`); the debug log line `building panel <i> '<name>' (<widget>) on <monitor>`.

- [ ] **Step 1: Write the failing tests**

Create (or replace entirely) `tests/test_clock.py`:

```python
from datetime import datetime

import pytest

pytest.importorskip("gi")
pytest.importorskip("fabric")

import widgets.clock as ck  # noqa: E402
import widgets.system_bar as sb  # noqa: E402
from widgets.clock import REFRESH_MS, format_time  # noqa: E402


def test_format_is_24h_zero_padded():
    assert format_time(datetime(2026, 1, 2, 3, 4, 59)) == "03:04"
    assert format_time(datetime(2026, 1, 2, 23, 59, 0)) == "23:59"


def test_refresh_is_fast_enough_for_minute_rollover():
    assert REFRESH_MS <= 1000


@pytest.mark.parametrize("module, cls", [(ck, "ClockWidget"), (sb, "SystemBarWidget")])
def test_destroy_stops_the_timer_once(monkeypatch, module, cls):
    removed = []
    monkeypatch.setattr(module.GLib, "source_remove", removed.append)
    widget = getattr(module, cls)()
    widget._repeater_id = 9
    widget.destroy()
    widget.destroy()
    assert removed == [9] and widget._destroyed
    assert widget._refresh() is False  # a refresh already queued does nothing
```

In `tests/test_monitor_shell.py` replace

```python
    monkeypatch.setattr(mon_mod, "ShapeCanvas", FakeCanvas)
    monkeypatch.setattr(mon_mod, "FrameEdge", FakeWindow)
    monkeypatch.setattr(mon_mod, "widget_class", lambda _w: FakeWindow)
    monkeypatch.setattr(mon_mod.MonitorShell, "_check_monitor", lambda self, w: None)
    timers, idles, removed = [], [], []
```

with

```python
    monkeypatch.setattr(mon_mod, "ShapeCanvas", FakeCanvas)
    monkeypatch.setattr(mon_mod, "FrameEdge", FakeWindow)
    monkeypatch.setattr(mon_mod, "panel_class", lambda _geo: FakeWindow)
    monkeypatch.setattr(mon_mod.MonitorShell, "_check_monitor", lambda self, w: None)
    timers, idles, removed = [], [], []
```

In `tests/test_monitor_shell.py` replace

```python
    shell, _, _ = build(edge({"panel": "edge", "name": "dock", "widget": "dock"}))
    built = [r.getMessage() for r in caplog.records if "building panel" in r.getMessage()]
    assert built == ["building panel 0 (dock) on HDMI-A-1"]
    caplog.clear()
    shell.apply(
```

with

```python
    shell, _, _ = build(edge({"panel": "edge", "name": "dock", "widget": "dock"}))
    built = [r.getMessage() for r in caplog.records if "building panel" in r.getMessage()]
    assert built == ["building panel 0 'dock' (dock) on HDMI-A-1"]
    caplog.clear()
    shell.apply(
```

In `tests/test_monitor_shell.py` replace

```python
        [Change("panel-rebuild", "HDMI-A-1", 0)],
    )
    assert "building panel 0 (dock) on HDMI-A-1" in caplog.text


```

with

```python
        [Change("panel-rebuild", "HDMI-A-1", 0)],
    )
    assert "building panel 0 'dock' (dock) on HDMI-A-1" in caplog.text


```

Rename: `git mv tests/test_widget_panel.py tests/test_summary.py`

Create (or replace entirely) `tests/test_summary.py`:

```python
"""The summary corner widget (spec 19; it was widget_panel): registration, text and refresh (no
window)."""

from datetime import datetime
from types import SimpleNamespace

import pytest

pytest.importorskip("gi")
pytest.importorskip("fabric")

import widgets.summary as sm  # noqa: E402
from shell import registry  # noqa: E402
from shell.panel_spec import CornerDefaults  # noqa: E402
from shell.widget import Widget  # noqa: E402


class FakeLabel:
    def __init__(self, text=""):
        self.text, self.sets = text, 0

    def get_label(self):
        return self.text

    def set_label(self, text):
        self.text, self.sets = text, self.sets + 1


def test_it_is_registered_as_the_spec_corner_widget():
    assert registry.widget_class("summary") is sm.SummaryWidget
    assert issubclass(sm.SummaryWidget, Widget)
    assert registry.supported_kinds("summary") == ("corner",)
    assert registry.widget_title("summary") == "Summary"
    assert registry.defaults("summary", "corner") == CornerDefaults(
        corner="bottom-left", width=300, height=390, label="summary"
    )


def test_date_and_stats_text():
    assert sm.format_date(datetime(2026, 10, 14, 9, 5)) == "Wed 14 Oct"
    assert sm.stats_lines(12.4, 56.6) == ("CPU 12%", "RAM 57%")


def test_refresh_updates_the_time_every_tick_and_the_stats_every_second(monkeypatch):
    monkeypatch.setattr(sm, "datetime", SimpleNamespace(now=lambda: datetime(2026, 10, 14, 9, 5)))
    monkeypatch.setattr(sm, "read_cpu_times", lambda: (100, 50))  # (total, idle) jiffies
    monkeypatch.setattr(sm, "read_meminfo_percent", lambda: 40.0)
    s = SimpleNamespace(
        _destroyed=False,
        _ticks=0,
        _prev=(0, 0),
        _time=FakeLabel(),
        _date=FakeLabel(),
        _cpu=FakeLabel("CPU --%"),
        _mem=FakeLabel("RAM --%"),
    )
    assert sm.SummaryWidget._refresh(s) is True
    assert s._time.sets == 1 and s._cpu.text == "CPU --%"  # stats wait for the second tick
    assert sm.SummaryWidget._refresh(s) is True
    assert s._time.sets == 1  # the same minute: no relayout
    assert (s._cpu.text, s._mem.text) == ("CPU 50%", "RAM 40%")  # (100 - 50) / 100 busy


def test_a_destroyed_widget_stops_refreshing():
    assert sm.SummaryWidget._refresh(SimpleNamespace(_destroyed=True)) is False


def test_destroy_stops_the_timer(monkeypatch):
    removed = []
    monkeypatch.setattr(sm.GLib, "source_remove", removed.append)
    w = sm.SummaryWidget()
    w._repeater_id = 7
    w.destroy()
    assert w._destroyed and removed == [7] and w._repeater_id == 0
    w.destroy()  # twice: nothing more to stop
    assert removed == [7]


def test_destroy_before_build_is_harmless(monkeypatch):
    removed = []
    monkeypatch.setattr(sm.GLib, "source_remove", removed.append)
    sm.SummaryWidget().destroy()
    assert removed == []
```

Create (or replace entirely) `tests/test_widget_kinds.py`:

```python
"""The built-in widgets are Widgets (content), never panel windows; the panel window class
comes from the panel kind (panel/widget spec 3.4-3.5)."""

from types import SimpleNamespace

import pytest

pytest.importorskip("gi")
pytest.importorskip("fabric")

import shell.edge_panel as ep  # noqa: E402
import shell.monitors as mon_mod  # noqa: E402
import widgets  # noqa: E402,F401  (registers the built-in widgets)
from shell import registry  # noqa: E402
from shell.corner_panel import CornerPanel  # noqa: E402
from shell.panel_spec import CornerGeometry, PanelGeometry  # noqa: E402
from shell.widget import NO_PROPS, Widget  # noqa: E402

BUILT_IN = {
    "clock": ("Clock", ("edge",)),
    "dock": ("Dock", ("edge",)),
    "summary": ("Summary", ("corner",)),
    "system_bar": ("System bar", ("edge",)),
}


def test_the_built_in_widgets_and_their_kinds():
    assert {
        n: (registry.widget_title(n), registry.supported_kinds(n)) for n in registry.widget_names()
    } == BUILT_IN


def test_every_widget_is_a_widget_not_a_panel_window():
    for name in registry.widget_names():
        cls = registry.widget_class(name)
        assert issubclass(cls, Widget) and not issubclass(cls, ep.EdgePanel), name


def test_the_window_class_follows_the_panel_kind():
    edge = PanelGeometry("dock", "bottom", 680, 560, 64, "extended", "dock")
    corner = CornerGeometry("summary", "bottom-left", "bottom", 300, 290, 380, "extended", "s")
    assert mon_mod.panel_class(edge) is ep.EdgePanel
    assert mon_mod.panel_class(corner) is CornerPanel


class Recorder(Widget):
    def __init__(self):
        self.built, self.destroyed = [], 0

    def build(self, props):
        self.built.append(props)
        return "content"

    def destroy(self):
        self.destroyed += 1


def test_the_panel_builds_its_widget_with_the_props():
    w = Recorder()
    panel = SimpleNamespace(_widget=w, _props=NO_PROPS)
    assert ep.EdgePanel.build_content(panel) == "content" and w.built == [NO_PROPS]


def test_a_panel_without_a_widget_is_empty():
    content = ep.EdgePanel.build_content(SimpleNamespace(_widget=None, _props=NO_PROPS))
    assert content.get_children() == []


def test_destroying_the_panel_destroys_its_widget_once():
    w = Recorder()
    panel = SimpleNamespace(_widget=w)
    ep.EdgePanel._on_destroy(panel)
    ep.EdgePanel._on_destroy(panel)  # GTK may emit destroy more than once
    assert w.destroyed == 1 and panel._widget is None


def test_the_destroy_handler_is_connected_before_the_content_is_built():
    # a build that fails half way must still have its timers stopped when the window goes;
    # building a real panel would map a window on Phil's screen, so check the source order
    import inspect

    src = inspect.getsource(ep.EdgePanel.__init__)
    assert src.index('self.connect("destroy", self._on_destroy)') < src.index(
        "self.build_content()"
    )
```


- [ ] **Step 2: Run them to verify they fail**

Run: `scripts/py -m pytest -q tests/test_summary.py tests/test_widget_kinds.py tests/test_clock.py tests/test_monitor_shell.py`
Expected: a collection error, `ModuleNotFoundError: No module named 'widgets.summary'`.

- [ ] **Step 3: Implement**

In `shell/corner_panel.py` replace

```python

class CornerPanel(EdgePanel):
    """Base class for corner widgets: register them with CornerDefaults (shell.registry)."""

    spec: CornerGeometry
```

with

```python

class CornerPanel(EdgePanel):
    """The window of a corner panel: an EdgePanel with a corner geometry."""

    spec: CornerGeometry
```

In `shell/edge_panel.py` replace

```python
"""EdgePanel: the content, handle and input window of one panel. Its body is drawn by the
monitor's shape canvas; the panel reports its animated depth through `on_depth`."""

from __future__ import annotations
```

with

```python
"""EdgePanel: the content, handle and input window of one panel. Its body is drawn by the
monitor's shape canvas; the panel reports its animated depth through `on_depth`. The
content is a Widget (shell.widget): the panel builds it and destroys it with itself."""

from __future__ import annotations
```

In `shell/edge_panel.py` replace

```python
    PanelGeometry,
)

log = logging.getLogger(__name__)
```

with

```python
    PanelGeometry,
)
from shell.widget import NO_PROPS, Widget, WidgetProps

log = logging.getLogger(__name__)
```

In `shell/edge_panel.py` replace

```python

class EdgePanel(WaylandWindow):
    """Base class for panels. Subclasses implement build_content()."""

    wants_keyboard = False
```

with

```python

class EdgePanel(WaylandWindow):
    """The window of an edge panel; CornerPanel is the corner one. It shows a Widget."""

    wants_keyboard = False
```

In `shell/edge_panel.py` replace

```python
        interaction: Interaction = ALL_INTERACTIONS,
        on_settings: Callable[[], None] | None = None,
    ):
        """`spec` is resolved by shell.panel_layout (exact pos and length in px); `on_depth(d)`
```

with

```python
        interaction: Interaction = ALL_INTERACTIONS,
        on_settings: Callable[[], None] | None = None,
        widget: Widget | None = None,
        props: WidgetProps = NO_PROPS,
    ):
        """`spec` is resolved by shell.panel_layout (exact pos and length in px); `on_depth(d)`
```

In `shell/edge_panel.py` replace

```python
        the canvas). `handle` and `interaction` come from the PanelRequest (spec 15); both can
        change later in place (set_handle). `on_settings()` is called on a right-click on the
        handle (EdgeShellApp.open_settings)."""
        # resolved before the window exists: a bad look fails without leaving a half-built window
        look = hd.resolve_handle(handle, interaction, theme)
```

with

```python
        the canvas). `handle` and `interaction` come from the PanelRequest (spec 15); both can
        change later in place (set_handle). `on_settings()` is called on a right-click on the
        handle (EdgeShellApp.open_settings). `widget` is the content, built with `props` (None:
        an empty panel)."""
        # resolved before the window exists: a bad look fails without leaving a half-built window
        look = hd.resolve_handle(handle, interaction, theme)
```

In `shell/edge_panel.py` replace

```python
        self._on_depth = on_depth
        self._on_settings = on_settings  # a right-click on the handle opens the settings
        self._handle_spec = handle
        self._interaction = interaction
```

with

```python
        self._on_depth = on_depth
        self._on_settings = on_settings  # a right-click on the handle opens the settings
        self._widget = widget
        self._props = props
        self.connect("destroy", self._on_destroy)  # the widget stops with the window
        self._handle_spec = handle
        self._interaction = interaction
```

In `shell/edge_panel.py` replace

```python
        self._sync_handle()

    # ---- override in subclasses ------------------------------------------------
    def build_content(self) -> Gtk.Widget:
        return Box()

    @classmethod
```

with

```python
        self._sync_handle()

    # ---- content ---------------------------------------------------------------
    def build_content(self) -> Gtk.Widget:
        """The content: the widget's build(props); an empty box without a widget."""
        if self._widget is None:
            return Box()
        return self._widget.build(self._props)

    def _on_destroy(self, *_args) -> None:
        """The window is going (a reload rebuilds it, a hot-plug closes the monitor): stop
        the widget's timers. Once only."""
        widget, self._widget = self._widget, None
        if widget is not None:
            widget.destroy()

    @classmethod
```

In `shell/monitors.py` replace

```python
from shell.config.diff import Change
from shell.config.models import Config
from shell.edge_panel import EdgePanel
from shell.frame import EDGES, FrameEdge
```

with

```python
from shell.config.diff import Change
from shell.config.models import Config
from shell.corner_panel import CornerPanel
from shell.edge_panel import EdgePanel
from shell.frame import EDGES, FrameEdge
```

In `shell/monitors.py` replace

```python
    g = monitor.get_geometry()
    return (g.x, g.y, g.width, g.height)


```

with

```python
    g = monitor.get_geometry()
    return (g.x, g.y, g.width, g.height)


def panel_class(geo: PanelGeometry | CornerGeometry) -> type[EdgePanel]:
    """The window class of a panel kind: CornerPanel for a corner panel, else EdgePanel."""
    return CornerPanel if isinstance(geo, CornerGeometry) else EdgePanel


```

In `shell/monitors.py` replace

```python
        self, index: int, geo: PanelGeometry | CornerGeometry, theme, raise_later: bool
    ) -> EdgePanel:
        """Build one panel window (edge or corner: a CornerPanel is an EdgePanel) and its
        canvas shape. The class comes from the widget's registration (`widget_class`), not from
        the geometry type."""
        self._remeasure.add(index)  # measured when idle if it is a "content" panel
        key = next(self._keys)
        self.canvas.add_panel(key, shape_for(geo))
        req = self._requests[index]
        log.debug("building panel %d (%s) on %s", index, geo.widget, self.name)
        try:
            panel = widget_class(geo.widget)(
                geo,
                theme,
```

with

```python
        self, index: int, geo: PanelGeometry | CornerGeometry, theme, raise_later: bool
    ) -> EdgePanel:
        """Build one panel window (edge or corner: `panel_class` of the geometry) showing a
        new instance of the request's widget (`widget_class`), and its canvas shape."""
        self._remeasure.add(index)  # measured when idle if it is a "content" panel
        key = next(self._keys)
        self.canvas.add_panel(key, shape_for(geo))
        req = self._requests[index]
        log.debug("building panel %d %r (%s) on %s", index, req.name, geo.widget, self.name)
        try:
            panel = panel_class(geo)(
                geo,
                theme,
```

In `shell/monitors.py` replace

```python
                interaction=req.interaction,
                on_settings=self._on_settings,
            )
        except Exception:
```

with

```python
                interaction=req.interaction,
                on_settings=self._on_settings,
                widget=widget_class(geo.widget)(),
                props=req.props,
            )
        except Exception:
```

In `shell/theme.py` replace

```python
{s} .active {{ color: {c["accent"]}; }}
{s} #clock-time {{ font-size: 20px; font-weight: 500; }}
{s} #widget-panel-time {{ font-size: 32px; font-weight: 500; }}
"""  # noqa: E501
```

with

```python
{s} .active {{ color: {c["accent"]}; }}
{s} #clock-time {{ font-size: 20px; font-weight: 500; }}
{s} #summary-time {{ font-size: 32px; font-weight: 500; }}
"""  # noqa: E501
```

In `widgets/__init__.py` replace

```python
"""Built-in panel widgets. Importing this package registers them."""

from widgets import clock, dock, system_bar, widget_panel  # noqa: F401
```

with

```python
"""Built-in panel widgets. Importing this package registers them."""

from widgets import clock, dock, summary, system_bar  # noqa: F401
```

Create (or replace entirely) `widgets/clock.py`:

```python
"""Clock: time of day on the top edge."""

from __future__ import annotations

from datetime import datetime

from fabric.utils import invoke_repeater
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from gi.repository import GLib

from shell.panel_spec import PanelDefaults
from shell.registry import register_widget
from shell.widget import Widget, WidgetProps

REFRESH_MS = 1000  # the minute rolls over within a second of the real change


def format_time(now: datetime) -> str:
    return now.strftime("%H:%M")


@register_widget(
    "clock", title="Clock", edge=PanelDefaults(edge="top", length=168, depth=46, label="clock")
)
class ClockWidget(Widget):
    def __init__(self) -> None:
        self._destroyed = False
        self._repeater_id = 0

    def build(self, props: WidgetProps):
        self._time = Label(name="clock-time", label=format_time(datetime.now()))
        self._repeater_id = invoke_repeater(REFRESH_MS, self._refresh)
        return Box(name="clock", h_align="center", v_align="center", children=self._time)

    def destroy(self) -> None:
        # Panels are rebuilt on config reload and hot-plug: stop the timer with them.
        self._destroyed = True
        if self._repeater_id:
            GLib.source_remove(self._repeater_id)
            self._repeater_id = 0

    def _refresh(self) -> bool:
        if self._destroyed:
            return False
        text = format_time(datetime.now())
        if text != self._time.get_label():  # avoid a relayout every second
            self._time.set_label(text)
        return True
```

Create (or replace entirely) `widgets/dock.py`:

```python
"""Dock: a row of app launchers on the bottom edge."""

from __future__ import annotations

from fabric.utils import exec_shell_command_async
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image

from shell.panel_spec import PanelDefaults
from shell.registry import register_widget
from shell.widget import Widget, WidgetProps

APPS = [  # (tooltip, icon name, command)
    ("Terminal", "utilities-terminal-symbolic", "konsole"),
    ("Files", "folder-symbolic", "dolphin"),
    ("Settings", "preferences-system-symbolic", "systemsettings"),
]


@register_widget(
    "dock", title="Dock", edge=PanelDefaults(edge="bottom", length=560, depth=64, label="dock")
)
class DockWidget(Widget):
    def build(self, props: WidgetProps):
        return Box(
            name="dock",
            orientation="h",
            spacing=8,
            h_align="center",
            v_align="center",
            children=[
                Button(
                    style_classes="icon-button",
                    tooltip_text=tip,
                    child=Image(icon_name=icon, icon_size=20),
                    on_clicked=lambda *_, c=cmd: exec_shell_command_async(c),
                )
                for tip, icon, cmd in APPS
            ],
        )
```

Rename: `git mv widgets/widget_panel.py widgets/summary.py`

Create (or replace entirely) `widgets/summary.py`:

```python
"""Summary: the spec's corner panel (spec 3 and 19) in the bottom-left corner, rising out
of the bottom edge, 300 x 390 px from the corner (both frame bands included): the time, the
date, CPU and RAM in one column. (It was the `widget_panel` widget.)"""

from __future__ import annotations

from datetime import datetime

from fabric.utils import invoke_repeater
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from gi.repository import GLib

from services.sysinfo import cpu_percent, read_cpu_times, read_meminfo_percent
from shell.panel_spec import CornerDefaults
from shell.registry import register_widget
from shell.widget import Widget, WidgetProps
from widgets.clock import format_time

REFRESH_MS = 1000  # the minute rolls over within a second of the real change
STATS_EVERY = 2  # CPU and RAM every second tick (the system bar's 2 s)


def format_date(now: datetime) -> str:
    return now.strftime("%a %d %b")


def stats_lines(cpu: float, ram: float) -> tuple[str, str]:
    return f"CPU {cpu:.0f}%", f"RAM {ram:.0f}%"


def _set(label, text: str) -> None:
    if label.get_label() != text:  # avoid a relayout every tick
        label.set_label(text)


@register_widget(
    "summary",
    title="Summary",
    corner=CornerDefaults(corner="bottom-left", width=300, height=390, label="summary"),
)
class SummaryWidget(Widget):
    def __init__(self) -> None:
        self._destroyed = False
        self._repeater_id = 0

    def build(self, props: WidgetProps):
        self._ticks = 0
        self._prev = read_cpu_times()
        now = datetime.now()
        self._time = Label(name="summary-time", label=format_time(now))
        self._date = Label(style_classes="secondary", label=format_date(now))
        self._cpu = Label(style_classes="secondary", label="CPU --%")
        self._mem = Label(style_classes="secondary", label="RAM --%")
        self._repeater_id = invoke_repeater(REFRESH_MS, self._refresh)
        return Box(
            name="summary",
            orientation="v",
            spacing=8,
            h_align="center",
            v_align="center",
            children=[self._time, self._date, self._cpu, self._mem],
        )

    def destroy(self) -> None:
        # Panels are rebuilt on config reload and hot-plug: stop the timer with them.
        self._destroyed = True
        if self._repeater_id:
            GLib.source_remove(self._repeater_id)
            self._repeater_id = 0

    def _refresh(self) -> bool:
        if self._destroyed:
            return False
        now = datetime.now()
        _set(self._time, format_time(now))
        _set(self._date, format_date(now))
        self._ticks += 1
        if self._ticks % STATS_EVERY == 0:
            cur = read_cpu_times()
            cpu, ram = stats_lines(cpu_percent(self._prev, cur), read_meminfo_percent())
            self._prev = cur
            _set(self._cpu, cpu)
            _set(self._mem, ram)
        return True
```

Create (or replace entirely) `widgets/system_bar.py`:

```python
"""System bar: CPU and memory on the right edge."""

from __future__ import annotations

from fabric.utils import invoke_repeater
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from gi.repository import GLib

from services.sysinfo import cpu_percent, read_cpu_times, read_meminfo_percent
from shell.panel_spec import PanelDefaults
from shell.registry import register_widget
from shell.widget import Widget, WidgetProps


@register_widget(
    "system_bar",
    title="System bar",
    # y = 600 on a 1080 px tall monitor (free span ends at 1042: 1042 - 142 - 300 = 600).
    # Same as the old pos = 600 only with edge right (or left), length 300, depth >= 28 and
    # the default thickness/radius; an entry overriding edge, length or depth moves (the app
    # logs those entries).
    edge=PanelDefaults(
        edge="right", length=300, depth=56, label="system bar", align="end", offset=142
    ),
)
class SystemBarWidget(Widget):
    def __init__(self) -> None:
        self._destroyed = False
        self._repeater_id = 0

    def build(self, props: WidgetProps):
        self._cpu = Label(style_classes="secondary")
        self._mem = Label(style_classes="secondary")
        self._prev = read_cpu_times()
        self._repeater_id = invoke_repeater(2000, self._refresh)
        return Box(
            name="system-bar",
            orientation="v",
            spacing=12,
            h_align="center",
            v_align="center",
            children=[self._cpu, self._mem],
        )

    def destroy(self) -> None:
        # Panels are rebuilt on config reload and monitor hot-plug: stop the timer with them.
        self._destroyed = True
        if self._repeater_id:
            GLib.source_remove(self._repeater_id)  # no-op (False) if it already ended
            self._repeater_id = 0

    def _refresh(self) -> bool:
        if self._destroyed:
            return False
        cur = read_cpu_times()
        self._cpu.set_label(f"CPU\n{cpu_percent(self._prev, cur):.0f}%")
        self._prev = cur
        self._mem.set_label(f"RAM\n{read_meminfo_percent():.0f}%")
        return True  # keep repeating
```


- [ ] **Step 4: Run the tests to verify they pass**

Run: `scripts/py -m pytest -q tests/test_summary.py tests/test_widget_kinds.py tests/test_clock.py tests/test_monitor_shell.py`
Expected: all pass.

- [ ] **Step 5: VERIFY and commit**

Run VERIFY. Expected: `1969 passed`, `All checks passed!`. Also `scripts/py -m shell.canvas.simulate --config examples/corner-test.toml --frames 2` prints `simulated 2 frames ...` (the real widgets register; no window is created).

```bash
git add shell/edge_panel.py shell/corner_panel.py shell/monitors.py shell/theme.py widgets/dock.py widgets/clock.py widgets/system_bar.py widgets/summary.py widgets/__init__.py tests/test_summary.py tests/test_widget_kinds.py tests/test_clock.py tests/test_monitor_shell.py
git status --short
git commit -m "refactor(widgets): panels host Widget instances; widget_panel becomes summary" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

(`git mv` already staged the two renames; `git status --short` must show `R` for both and nothing else unstaged.)

**Reviewer mutations:** `_on_destroy` not calling `widget.destroy()` (`test_destroying_the_panel_destroys_its_widget_once`); `panel_class` always `EdgePanel` (`test_the_window_class_follows_the_panel_kind`); the props not passed to the window (`test_a_panel_gets_a_new_instance_of_its_widget_and_the_props`, Task 5, and `test_the_panel_builds_its_widget_with_the_props`).

---
### Task 5: Rebuild on a name or property change; contain a widget that fails to build

`MonitorShell._sync_panels` compares the resolved geometry only, so a panel whose name or widget properties changed (the diff's `panel-rebuild`) kept its old window. It now also keeps each index's `(name, props)` and rebuilds when they differ. A panel window or widget that raises while it is built no longer takes the monitor down: `_new_panel` logs it, removes the canvas shape, records a message naming the panel in `build_failures` and returns None (the panel is not shown; the next sync tries again). `EdgePanel.__init__` destroys its own half-built window when `build_content` raises. The app notifies "Panel not shown" when a monitor's failure list changes. A panel that failed is not tried again on every re-sync: `MonitorShell._failed` remembers the entry it failed for (kind, widget, name, props) and skips it, still listing its message, until a reload changes one of those.

**Files:**
- Modify: `shell/monitors.py` (`_contents`, `build_failures`, `_sync_panels`, `_new_panel`, `close`), `shell/edge_panel.py` (`build_content` failure), `shell/app.py` (`_report_layout` notifies the failures)
- Modify: `tests/test_monitor_shell.py`, `tests/test_app_sync.py`, `tests/test_widget_kinds.py`

**Interfaces:**
- Consumes: `PanelRequest.name` / `props`, `CornerRequest.name` / `props` (Task 3); `panel_class`, `widget_class` in `shell.monitors` (Task 4); `EdgeShellApp._notify`, `_report_layout`.
- Produces: `MonitorShell.build_failures: list[str]` (reset by every sync; one entry per panel left out: `"<monitor>: panel '<name>' (<widget>) could not be built and is not shown: <error>"`); `MonitorShell._new_panel(...) -> EdgePanel | None`; `MonitorShell._contents: list[tuple[str, WidgetProps] | None]` and `MonitorShell._failed: dict[int, tuple[tuple, str]]` (a test stand-in `bare_shell` sets both); `shell.monitors._entry_key(req) -> tuple` (`(type(req).__name__, req.widget, req.name, req.props)`); `EdgeShellApp._failures_reported: dict[str, list[str]]`; notification title `"Panel not shown"`; log line `building panel <i> '<name>' (<widget>) on <monitor> failed` with the traceback.

- [ ] **Step 1: Write the failing tests**

In `tests/test_app_sync.py` replace

```python
    fail_apply: set = set()
    layout_warnings: list = []
    measure_pending = False
    fail_open: set = set()
```

with

```python
    fail_apply: set = set()
    layout_warnings: list = []
    build_failures: list = []
    measure_pending = False
    fail_open: set = set()
```

In `tests/test_app_sync.py` replace

```python
        ("fail_open", set()),
        ("layout_warnings", []),
        ("measure_pending", False),
    ):
```

with

```python
        ("fail_open", set()),
        ("layout_warnings", []),
        ("build_failures", []),
        ("measure_pending", False),
    ):
```

In `tests/test_app_sync.py` replace

```python
    assert app.shells == {} and len(app.app.stylesheets) == 2
    assert all(css.strip() for css in app.app.stylesheets)
```

with

```python
    assert app.shells == {} and len(app.app.stylesheets) == 2
    assert all(css.strip() for css in app.app.stylesheets)


def test_panels_that_could_not_be_built_are_notified_by_name_once(renv, monkeypatch):
    app, _, _, _, _ = renv
    notes = []
    monkeypatch.setattr(
        app_mod.EdgeShellApp, "_notify", lambda self, title, msg: notes.append((title, msg))
    )
    shell = app.shells["HDMI-A-1"]
    failure = "HDMI-A-1: panel 'Top clock' (clock) could not be built and is not shown: boom"
    for failures in ([failure], [failure], [], [failure]):
        shell.build_failures = failures
        app._report_layout("HDMI-A-1", shell)
    assert notes == [("Panel not shown", failure), ("Panel not shown", failure)]
```

In `tests/test_monitor_shell.py` replace

```python
import shell.monitors as mon_mod  # noqa: E402
from shell.config.diff import Change  # noqa: E402


```

with

```python
import shell.monitors as mon_mod  # noqa: E402
from shell.config.diff import Change  # noqa: E402
from shell.panel_spec import PanelDefaults  # noqa: E402
from shell.widget import Widget, WidgetProps  # noqa: E402


```

In `tests/test_monitor_shell.py` replace

```python
    shell._resolved = [None] * len(shell.panels)
    shell._handles = [None] * len(shell.panels)
    shell.canvas = FakeCanvas()
    shell.strips = []
```

with

```python
    shell._resolved = [None] * len(shell.panels)
    shell._handles = [None] * len(shell.panels)
    shell._contents = [None] * len(shell.panels)
    shell._failed = {}
    shell.canvas = FakeCanvas()
    shell.strips = []
```

In `tests/test_monitor_shell.py` replace

```python


def test_failed_panel_construction_leaves_no_scene_shape(build, make_config, monkeypatch):
    shell, _, _ = build(edge())

    def explode(*a, **k):
        raise RuntimeError("widget broke")

    monkeypatch.setattr(mon_mod, "widget_class", lambda _w: explode)
    with pytest.raises(RuntimeError):
        shell.apply(
            make_config(monitors=edge({"panel": "edge", "name": "dock", "widget": "dock"})), []
        )
    assert shell.canvas.shapes == {}


def test_failed_construction_closes_everything_already_built(
    make_config, monkeypatch, fake_registry
):
```

with

```python


def test_a_panel_that_fails_to_build_is_left_out_and_named(build, make_config, monkeypatch, caplog):
    """Spec 4: a widget build failure is logged and that panel skipped (no window, no scene
    shape); the monitor and its other panels stay; the failure names the panel."""
    shell, tracked, _ = build(edge({"panel": "edge", "name": "Dock", "widget": "dock"}))
    dock = shell.panels[0]

    def explode(*a, **k):
        raise RuntimeError("widget broke")

    real = mon_mod.widget_class
    monkeypatch.setattr(mon_mod, "widget_class", lambda w: explode if w == "clock" else real(w))
    shell.apply(
        make_config(
            monitors=edge(
                {"panel": "edge", "name": "Dock", "widget": "dock"},
                {"panel": "edge", "name": "Top clock", "widget": "clock"},
            )
        ),
        [Change("panel-add", "HDMI-A-1", 1)],
    )
    assert shell.panels == [dock, None] and not dock.destroyed
    assert len(shell.canvas.shapes) == 1  # the failed panel left no shape behind
    assert shell.build_failures == [
        "HDMI-A-1: panel 'Top clock' (clock) could not be built and is not shown: widget broke"
    ]
    assert "building panel 1 'Top clock' (clock) on HDMI-A-1 failed" in caplog.text
    assert "RuntimeError: widget broke" in caplog.text  # with the traceback
    monkeypatch.setattr(mon_mod, "widget_class", real)
    same = edge(
        {"panel": "edge", "name": "Dock", "widget": "dock"},
        {"panel": "edge", "name": "Top clock", "widget": "clock"},
    )
    shell.apply(make_config(monitors=same), [])  # the same entry: not tried again
    assert shell.panels[1] is None and len(shell.build_failures) == 1
    renamed = edge(
        {"panel": "edge", "name": "Dock", "widget": "dock"},
        {"panel": "edge", "name": "Clock", "widget": "clock"},
    )
    shell.apply(make_config(monitors=renamed), [])  # the entry changed: tried again
    assert shell.panels[1] is not None and shell.build_failures == []


def test_a_failure_while_the_monitor_is_built_keeps_the_frame(
    make_config, monkeypatch, fake_registry
):
```

In `tests/test_monitor_shell.py` replace

```python
    monkeypatch.setattr(mon_mod.GLib, "timeout_add", lambda *a: 1)
    monkeypatch.setattr(mon_mod.GLib, "idle_add", lambda *a: 1)
    registered, unregistered = [], []
    cfg = make_config(monitors=edge({"panel": "edge", "name": "dock", "widget": "dock"}))
    with pytest.raises(RuntimeError, match="panel broke"):
        mon_mod.MonitorShell("HDMI-A-1", MONITOR, cfg, registered.append, unregistered.append)
    assert len(registered) == 5  # canvas + 4 strips were on screen
```

with

```python
    monkeypatch.setattr(mon_mod.GLib, "timeout_add", lambda *a: 1)
    monkeypatch.setattr(mon_mod.GLib, "idle_add", lambda *a: 1)
    registered = []
    cfg = make_config(monitors=edge({"panel": "edge", "name": "Dock", "widget": "dock"}))
    shell = mon_mod.MonitorShell("HDMI-A-1", MONITOR, cfg, registered.append)
    assert len(registered) == 5 and shell.panels == [None]  # canvas + 4 strips, no panel
    assert shell.build_failures and "'Dock'" in shell.build_failures[0]


def test_failed_construction_closes_everything_already_built(
    make_config, monkeypatch, fake_registry
):
    def explode(*a, **k):
        raise RuntimeError("layout broke")

    monkeypatch.setattr(mon_mod, "ShapeCanvas", FakeCanvas)
    monkeypatch.setattr(mon_mod, "FrameEdge", FakeWindow)
    monkeypatch.setattr(mon_mod, "layout_monitor", explode)  # not a widget: nothing contains it
    monkeypatch.setattr(mon_mod.MonitorShell, "_check_monitor", lambda self, w: None)
    monkeypatch.setattr(mon_mod.GLib, "timeout_add", lambda *a: 1)
    monkeypatch.setattr(mon_mod.GLib, "idle_add", lambda *a: 1)
    registered, unregistered = [], []
    cfg = make_config(monitors=edge({"panel": "edge", "name": "dock", "widget": "dock"}))
    with pytest.raises(RuntimeError, match="layout broke"):
        mon_mod.MonitorShell("HDMI-A-1", MONITOR, cfg, registered.append, unregistered.append)
    assert len(registered) == 5  # canvas + 4 strips were on screen
```

In `tests/test_monitor_shell.py` replace

```python

    def explode(*a, **k):
        raise RuntimeError("widget broke")

    monkeypatch.setattr(mon_mod, "widget_class", lambda _w: explode)  # the rebuild raises
    assert shell.test_idles[0]() is False  # never raises into the main loop
    assert errors == [shell] and reports == []
    assert "widget broke" in caplog.text


```

with

```python

    def explode(*a, **k):
        raise RuntimeError("layout broke")

    monkeypatch.setattr(mon_mod, "layout_monitor", explode)  # the re-layout raises
    assert shell.test_idles[0]() is False  # never raises into the main loop
    assert errors == [shell] and reports == []
    assert "layout broke" in caplog.text


```

In `tests/test_monitor_shell.py` replace

```python

    def explode(*a, **k):
        raise RuntimeError("widget broke")

    monkeypatch.setattr(mon_mod, "widget_class", lambda _w: explode)
    assert shell.test_idles[0]() is False
    assert "handler broke" in caplog.text
```

with

```python

    def explode(*a, **k):
        raise RuntimeError("layout broke")

    monkeypatch.setattr(mon_mod, "layout_monitor", explode)
    assert shell.test_idles[0]() is False
    assert "handler broke" in caplog.text
```

In `tests/test_monitor_shell.py` replace

```python

    def explode(*a, **k):
        raise RuntimeError("widget broke")

    monkeypatch.setattr(mon_mod, "widget_class", lambda _w: explode)  # the rebuild raises
    monitor.width, monitor.height = 1280, 720
    handler(monitor, None)
    assert timers[-1][1]() is False  # never raises into the main loop
    assert errors == [shell] and reports == []
    assert "widget broke" in caplog.text


```

with

```python

    def explode(*a, **k):
        raise RuntimeError("layout broke")

    monkeypatch.setattr(mon_mod, "layout_monitor", explode)  # the re-layout raises
    monitor.width, monitor.height = 1280, 720
    handler(monitor, None)
    assert timers[-1][1]() is False  # never raises into the main loop
    assert errors == [shell] and reports == []
    assert "layout broke" in caplog.text


```

In `tests/test_monitor_shell.py` replace

```python
    assert box.destroyed and shell.panels[0].args[0].along == 282  # 320 - (10 + 14) - 14
    assert "width 300 px does not fit the bottom edge; shrunk to 282" in shell.layout_warnings[0]
```

with

```python
    assert box.destroyed and shell.panels[0].args[0].along == 282  # 320 - (10 + 14) - 14
    assert "width 300 px does not fit the bottom edge; shrunk to 282" in shell.layout_warnings[0]


# ---- the widget a panel shows (panel/widget spec 3.5) --------------------------------


class Big(WidgetProps):
    size: int = 10


@pytest.fixture
def big(fake_registry):
    """A widget with one property: a change of it must rebuild the panel."""
    fake_registry.register_widget(
        "big",
        title="Big",
        props=Big,
        edge=PanelDefaults(edge="top", length=200, depth=50, label="big"),
    )(type("BigWidget", (Widget,), {}))
    return fake_registry


def test_a_panel_gets_a_new_instance_of_its_widget_and_the_props(build, big):
    shell, _, _ = build(
        edge(
            {"panel": "edge", "name": "A", "widget": "big", "size": 20},
            {"panel": "edge", "name": "B", "widget": "big"},
        )
    )
    a, b = shell.panels
    assert type(a.kwargs["widget"]).__name__ == "BigWidget"
    assert a.kwargs["widget"] is not b.kwargs["widget"]
    assert (a.kwargs["props"], b.kwargs["props"]) == (Big(size=20), Big())


@pytest.mark.parametrize(
    "change",
    [{"name": "Renamed"}, {"size": 30}],
    ids=["name", "property"],
)
def test_a_name_or_property_change_rebuilds_the_panel_in_the_same_place(
    build, big, make_config, change
):
    entry = {"panel": "edge", "name": "A", "widget": "big"}
    shell, _, _ = build(edge(entry))
    (old,) = shell.panels
    shell.apply(make_config(monitors=edge({**entry, **change})), [])
    (new,) = shell.panels
    assert new is not old and old.destroyed
    assert new.args[0] == old.args[0]  # the same geometry: only the content changed
    if "size" in change:
        assert new.kwargs["props"] == Big(size=30)


def test_an_unchanged_entry_is_not_rebuilt(build, big, make_config):
    entry = {"panel": "edge", "name": "A", "widget": "big", "size": 12}
    shell, _, _ = build(edge(entry))
    (old,) = shell.panels
    shell.apply(make_config(monitors=edge(entry)), [])
    assert shell.panels == [old] and not old.destroyed


def test_a_failed_panel_is_not_retried_by_a_relayout_only_by_an_entry_change(
    build, make_config, monkeypatch
):
    calls = []

    def explode(*a, **k):
        calls.append(1)
        raise RuntimeError("widget broke")

    monitor = FakeMonitor()
    monkeypatch.setattr(mon_mod, "widget_class", lambda _w: explode)
    entry = {"panel": "edge", "name": "Dock", "widget": "dock", "length": "content"}
    shell, _, timers = build(edge(entry), monitor=monitor)
    assert calls == [1] and shell.panels == [None]
    ((_, handler),) = monitor.handlers.values()
    monitor.width, monitor.height = 1280, 720  # a resolution change re-lays out the monitor
    handler(monitor, None)
    assert timers[-1][1]() is False
    shell.apply(make_config(monitors=edge(entry)), [])  # an unrelated reload
    assert calls == [1] and len(shell.build_failures) == 1  # never tried again
    for change in ({"depth": 80}, {"widget": "clock"}, {"panel": "edge", "name": "Dock 2"}):
        shell.apply(make_config(monitors=edge({**entry, **change})), [])
    assert len(calls) == 3  # depth alone is a move: not retried; widget and name changes are
```

In `tests/test_widget_kinds.py` replace

```python
        "self.build_content()"
    )
```

with

```python
        "self.build_content()"
    )


def test_a_build_that_fails_destroys_the_half_built_window():
    # EdgePanel.__init__ creates the window before the content; a widget that raises in
    # build() must not leave that window behind (MonitorShell then skips the panel)
    import inspect

    src = inspect.getsource(ep.EdgePanel.__init__)
    build = src.index("inner = self.build_content()")
    assert src.rindex("try:", 0, build) > src.rindex("super().__init__(", 0, build)
    assert src.index("self.destroy()", build) < src.index("raise", build)
```


- [ ] **Step 2: Run them to verify they fail**

Run: `scripts/py -m pytest -q tests/test_monitor_shell.py tests/test_app_sync.py tests/test_widget_kinds.py`
Expected: `7 failed, 120 passed`: `test_panels_that_could_not_be_built_are_notified_by_name_once` (no notification yet), `test_a_panel_that_fails_to_build_is_left_out_and_named`, `test_a_failed_panel_is_not_retried_by_a_relayout_only_by_an_entry_change` and `test_a_failure_while_the_monitor_is_built_keeps_the_frame` (the RuntimeError escapes), both cases of `test_a_name_or_property_change_rebuilds_the_panel_in_the_same_place` (the old window is kept), `test_a_build_that_fails_destroys_the_half_built_window`.

- [ ] **Step 3: Implement**

In `shell/app.py` replace

```python
        self._sync_timers: list[int] = []  # pending hot-plug sync timer ids
        self._layout_reported: dict[str, list[str]] = {}  # last notified warnings per monitor
        self._relayout_rebuilt: set[str] = set()  # rebuilt after a failed re-layout, until a reload
        self._log_deprecated(store.config)
```

with

```python
        self._sync_timers: list[int] = []  # pending hot-plug sync timer ids
        self._layout_reported: dict[str, list[str]] = {}  # last notified warnings per monitor
        self._failures_reported: dict[str, list[str]] = {}  # last notified build failures
        self._relayout_rebuilt: set[str] = set()  # rebuilt after a failed re-layout, until a reload
        self._log_deprecated(store.config)
```

In `shell/app.py` replace

```python

    def _report_layout(self, name: str, shell) -> None:
        """Notify panels moved, shrunk or hidden by the layout rules (shell.panel_layout), but
        only when that monitor's warnings changed, not on every unrelated reload."""
        warnings = list(shell.layout_warnings)
        if warnings == self._layout_reported.get(name, []):
```

with

```python

    def _report_layout(self, name: str, shell) -> None:
        """Notify panels moved, shrunk or hidden by the layout rules (shell.panel_layout), and
        panels whose widget could not be built (by name), but only when that monitor's list
        changed, not on every unrelated reload."""
        failures = list(shell.build_failures)
        if failures != self._failures_reported.get(name, []):
            self._failures_reported[name] = failures
            if failures:
                self._notify("Panel not shown", "\n".join(failures))
        warnings = list(shell.layout_warnings)
        if warnings == self._layout_reported.get(name, []):
```

In `shell/edge_panel.py` replace

```python
        # Centring container: the widget's own content is centred inside the body box
        # that _place_content sizes and positions (a Box packs children at the start).
        inner = self.build_content()
        inner.set_hexpand(True)
        inner.set_vexpand(True)
```

with

```python
        # Centring container: the widget's own content is centred inside the body box
        # that _place_content sizes and positions (a Box packs children at the start).
        try:
            inner = self.build_content()
        except Exception:
            self.destroy()  # never leave a half-built window behind (its widget stops too)
            raise
        inner.set_hexpand(True)
        inner.set_vexpand(True)
```

In `shell/monitors.py` replace

```python
from shell.registry import requests_for, widget_class
from shell.theme import scope_class

log = logging.getLogger(__name__)
```

with

```python
from shell.registry import requests_for, widget_class
from shell.theme import scope_class
from shell.widget import WidgetProps

log = logging.getLogger(__name__)
```

In `shell/monitors.py` replace

```python
        # Each index's (handle, interaction) as last given to its panel (changed in place).
        self._handles: list[tuple[HandleSpec, Interaction] | None] = []
        self.layout_warnings: list[str] = []
        self._keys = itertools.count()  # scene keys for the canvas
        self._config = config
```

with

```python
        # Each index's (handle, interaction) as last given to its panel (changed in place).
        self._handles: list[tuple[HandleSpec, Interaction] | None] = []
        # Each index's (name, widget properties) as last built: a change rebuilds the panel.
        self._contents: list[tuple[str, WidgetProps] | None] = []
        self.layout_warnings: list[str] = []
        # Panels whose window or widget could not be built (not shown), as of the last sync.
        self.build_failures: list[str] = []
        # index -> (the entry it failed for, the message): not tried again until it changes
        self._failed: dict[int, tuple[tuple, str]] = {}
        self._keys = itertools.count()  # scene keys for the canvas
        self._config = config
```

In `shell/monitors.py` replace

```python

    def _sync_panels(self, config: Config, theme, startup: bool) -> None:
        """Make the panels match the resolved layout: rebuild a panel whose resolved geometry
        changed (also when a neighbour's change moved or hid it), retarget a state change.
        Does nothing while the monitor reports no size (being unplugged: the hot-plug sync
        closes this shell), so no 0 px layout hides every panel."""
        g = self.monitor.get_geometry()
        if g.width <= 0 or g.height <= 0:
```

with

```python

    def _sync_panels(self, config: Config, theme, startup: bool) -> None:
        """Make the panels match the resolved layout: rebuild a panel whose resolved geometry,
        name or widget properties changed (also when a neighbour's change moved or hid it),
        retarget a state change. A panel that could not be built is left out (None) and
        listed in `build_failures`; it is tried again only when its entry (kind, widget, name
        or properties) changes. Does nothing while the
        monitor reports no size (being unplugged: the hot-plug sync closes this shell), so no
        0 px layout hides every panel."""
        g = self.monitor.get_geometry()
        if g.width <= 0 or g.height <= 0:
```

In `shell/monitors.py` replace

```python
        layout = self._layout(config, theme)
        self.layout_warnings = list(layout.warnings)
        for message in layout.warnings:
            log.warning("%s", message)
```

with

```python
        layout = self._layout(config, theme)
        self.layout_warnings = list(layout.warnings)
        self.build_failures = []
        for message in layout.warnings:
            log.warning("%s", message)
```

In `shell/monitors.py` replace

```python
            self._resolved.pop()
            self._handles.pop()
        for i, geo in enumerate(wanted):
            if i == len(self.panels):
```

with

```python
            self._resolved.pop()
            self._handles.pop()
            self._contents.pop()
            self._failed.pop(len(self.panels), None)
        for i, geo in enumerate(wanted):
            if i == len(self.panels):
```

In `shell/monitors.py` replace

```python
                self._resolved.append(None)
                self._handles.append(None)
            old, panel = self._resolved[i], self.panels[i]
            req = self._requests[i]
            handles = (req.handle, req.interaction)
            if geo is None:
                if panel is not None:
                    self._destroy_panel(i)
            elif panel is None or old is None or replace(old, state=geo.state) != geo:
                if panel is not None:
                    self._destroy_panel(i)
                self.panels[i] = self._new_panel(i, geo, theme, raise_later=not startup)
            else:  # same geometry: the live panel changes in place (spec 15: never a rebuild)
                if self._handles[i] != handles:
```

with

```python
                self._resolved.append(None)
                self._handles.append(None)
                self._contents.append(None)
            old, panel = self._resolved[i], self.panels[i]
            req = self._requests[i]
            handles = (req.handle, req.interaction)
            content = (req.name, req.props)
            if geo is None:
                if panel is not None:
                    self._destroy_panel(i)
            elif (
                panel is None
                or old is None
                or replace(old, state=geo.state) != geo
                or self._contents[i] != content
            ):
                if panel is not None:
                    self._destroy_panel(i)
                failed = self._failed.get(i)
                if failed is not None and failed[0] == _entry_key(req):
                    self.build_failures.append(failed[1])  # same entry: not tried again
                else:
                    self._failed.pop(i, None)
                    self.panels[i] = self._new_panel(i, geo, theme, raise_later=not startup)
            else:  # same geometry: the live panel changes in place (spec 15: never a rebuild)
                if self._handles[i] != handles:
```

In `shell/monitors.py` replace

```python
            self._resolved[i] = geo
            self._handles[i] = handles
        self._schedule_measure()

```

with

```python
            self._resolved[i] = geo
            self._handles[i] = handles
            self._contents[i] = content
        self._schedule_measure()

```

In `shell/monitors.py` replace

```python
    def _new_panel(
        self, index: int, geo: PanelGeometry | CornerGeometry, theme, raise_later: bool
    ) -> EdgePanel:
        """Build one panel window (edge or corner: `panel_class` of the geometry) showing a
        new instance of the request's widget (`widget_class`), and its canvas shape."""
        self._remeasure.add(index)  # measured when idle if it is a "content" panel
        key = next(self._keys)
```

with

```python
    def _new_panel(
        self, index: int, geo: PanelGeometry | CornerGeometry, theme, raise_later: bool
    ) -> EdgePanel | None:
        """Build one panel window (edge or corner: `panel_class` of the geometry) showing a
        new instance of the request's widget (`widget_class`), and its canvas shape. A window
        or widget that fails to build is logged, listed in `build_failures` (the app notifies
        it by the panel's name) and left out: None, never an exception that would take the
        monitor's other panels down."""
        self._remeasure.add(index)  # measured when idle if it is a "content" panel
        key = next(self._keys)
```

In `shell/monitors.py` replace

```python
                props=req.props,
            )
        except Exception:
            self.canvas.remove_panel(key)
            raise
        panel.scene_key = key
        self._track(panel)
```

with

```python
                props=req.props,
            )
        except Exception as exc:
            self.canvas.remove_panel(key)
            log.exception(
                "building panel %d %r (%s) on %s failed", index, req.name, geo.widget, self.name
            )
            message = (
                f"{self.name}: panel {req.name!r} ({geo.widget}) could not be built and is not "
                f"shown: {exc}"
            )
            self.build_failures.append(message)
            self._failed[index] = (_entry_key(req), message)
            return None
        panel.scene_key = key
        self._track(panel)
```

In `shell/monitors.py` replace

```python
        self._resolved.clear()
        self._handles.clear()


```

with

```python
        self._resolved.clear()
        self._handles.clear()
        self._contents.clear()
        self._failed.clear()


def _entry_key(req: PanelRequest | CornerRequest) -> tuple:
    """What a failed build is remembered by: the entry's kind, widget, name and properties.
    A change of any of them (a reload) tries the panel again; a move does not."""
    return type(req).__name__, req.widget, req.name, req.props


```


- [ ] **Step 4: Run the tests to verify they pass**

Run: `scripts/py -m pytest -q tests/test_monitor_shell.py tests/test_app_sync.py tests/test_widget_kinds.py`
Expected: all pass.

- [ ] **Step 5: VERIFY and commit**

Run VERIFY. Expected: `1977 passed`, `All checks passed!`.

```bash
git add shell/monitors.py shell/edge_panel.py shell/app.py tests/test_monitor_shell.py tests/test_app_sync.py tests/test_widget_kinds.py
git commit -m "fix(shell): rebuild a panel whose name or properties changed; skip a widget that fails to build" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

**Reviewer mutations:** the `(name, props)` comparison removed from `_sync_panels` (`test_a_name_or_property_change_rebuilds_the_panel_in_the_same_place`); `_new_panel` re-raising instead of returning None (`test_a_panel_that_fails_to_build_is_left_out_and_named`); the notification dropped (`test_panels_that_could_not_be_built_are_notified_by_name_once`); `build_failures` not reset per sync, a failed panel retried on every sync, never retried, or retried on a move (`test_a_panel_that_fails_to_build_is_left_out_and_named`, `test_a_failed_panel_is_not_retried_by_a_relayout_only_by_an_entry_change`). Note for the reviewer: the three tests that used a raising `widget_class` to make a measurement or a re-layout fail now patch `layout_monitor` instead (a widget failure no longer escapes, which is the point of this task); `test_failed_construction_closes_everything_already_built` keeps its meaning with a raising layout.

---

### Task 6: The clock's `format`, `font` and `font_size`

The clock gets a property model. `format` is tokenised by a pure, fixed table in `services/clock_format.py`, with text in single quotes taken literally (`''` is one quote; an unclosed quote is an error); the widget formats per token and never hands user text to strftime. `font` (checked by the theme's font-name rule, now public) and `font_size` (points, emitted as `pt`) become a CSS provider on the clock's label, above the app's stylesheet.

**Files:**
- Create: `services/clock_format.py`, `tests/test_clock_format.py`
- Modify: `widgets/clock.py` (rewritten: `ClockProps`, the provider, the tokenised refresh), `shell/config/models.py` (`check_font_name`), `shell/theme.py` (`label_font_css`)
- Modify: `tests/test_clock.py` (rewritten)

**Interfaces:**
- Consumes: `register_widget(..., props=)`, `WidgetProps` (Task 3); `Widget` (Task 4).
- Produces: `services.clock_format.TOKENS` (the 11 tokens), `parse_clock_format(text: str) -> tuple[tuple[bool, str], ...]` (ValueError `unknown token 'Y' at position 2; use HH, mm, ..., or put text in single quotes` / `unterminated quote at position 4; close it with ' (write '' for a quote)`), `format_clock(parts, now: datetime) -> str`; `shell.config.models.check_font_name(name: str) -> str`; `shell.theme.label_font_css(font: str | None, size: int | None) -> str` (`font-size` in `pt`; `""` when both are None); `widgets.clock.ClockProps` (`format: str = "HH:mm"` 1-64 characters, `font: str | None` 1-100 characters, `font_size: int | None` 6-96 points, each with a `Field(description=...)` the settings window shows as the row's hint); `widgets.clock.FONT_PRIORITY = Gtk.STYLE_PROVIDER_PRIORITY_USER + 1`; `format_time(now)` stays (`HH:mm`, the summary block's time).

- [ ] **Step 1: Write the failing tests**

Create (or replace entirely) `tests/test_clock.py`:

```python
from datetime import datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

gi = pytest.importorskip("gi")
pytest.importorskip("fabric")

import widgets.clock as ck  # noqa: E402
import widgets.system_bar as sb  # noqa: E402
from shell import registry  # noqa: E402
from shell.config.models import ConfigError  # noqa: E402
from shell.theme import label_font_css  # noqa: E402
from widgets.clock import REFRESH_MS, ClockProps, format_time  # noqa: E402


def test_format_is_24h_zero_padded():
    assert format_time(datetime(2026, 1, 2, 3, 4, 59)) == "03:04"
    assert format_time(datetime(2026, 1, 2, 23, 59, 0)) == "23:59"


def test_refresh_is_fast_enough_for_minute_rollover():
    assert REFRESH_MS <= 1000


@pytest.mark.parametrize("module, cls", [(ck, "ClockWidget"), (sb, "SystemBarWidget")])
def test_destroy_stops_the_timer_once(monkeypatch, module, cls):
    removed = []
    monkeypatch.setattr(module.GLib, "source_remove", removed.append)
    widget = getattr(module, cls)()
    widget._repeater_id = 9
    widget.destroy()
    widget.destroy()
    assert removed == [9] and widget._destroyed
    assert widget._refresh() is False  # a refresh already queued does nothing


# ---- properties (panel/widget spec 3.4) ---------------------------------------------


def test_the_clock_registers_its_properties():
    assert registry.widget_props_model("clock") is ClockProps
    assert ClockProps() == ClockProps(format="HH:mm", font=None, font_size=None)


@pytest.mark.parametrize(
    ("keys", "words"),
    [
        ({"format": "%Y"}, "unknown token 'Y'"),
        ({"format": ""}, "at least 1 character"),
        ({"font": 'Hack"; } * { color: red'}, "must not contain a double quote"),
        ({"font": ""}, "at least 1 character"),
        ({"font_size": 5}, "greater than or equal to 6"),
        ({"font_size": 97}, "less than or equal to 96"),
    ],
)
def test_bad_properties_are_refused(keys, words):
    with pytest.raises(ValidationError, match=words):
        ClockProps(**keys)


def test_bad_properties_name_the_key_path_in_a_config(make_config):
    entry = {"panel": "edge", "name": "Clock", "widget": "clock", "format": "HH:MM:SS"}
    with pytest.raises(ConfigError) as exc:
        registry.validate_widgets(make_config(monitors={"HDMI-A-1": {"panels": [entry]}}))
    assert "monitors.HDMI-A-1.panels[0].format: Value error, unknown token 'S'" in str(exc.value)


def test_the_label_font_css():
    assert label_font_css(None, None) == ""
    assert label_font_css("Hack", None) == 'label { font-family: "Hack"; }'
    assert label_font_css(None, 14) == "label { font-size: 14pt; }"  # points
    assert label_font_css("monospace", 9) == "label { font-family: monospace; font-size: 9pt; }"


def test_the_refresh_uses_the_format(monkeypatch):
    monkeypatch.setattr(ck, "datetime", SimpleNamespace(now=lambda: datetime(2026, 1, 2, 21, 7)))
    w = ck.ClockWidget()
    w._parts = ck.parse_clock_format("h:mm a")
    w._time = SimpleNamespace(text="", get_label=lambda: "", set_label=lambda t: sets.append(t))
    sets = []
    assert w._refresh() is True and sets == ["9:07 PM"]


# ---- the built label (plain Gtk widgets, no window) ---------------------------------


@pytest.fixture
def gtk():
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk

    if not Gtk.init_check()[0]:
        pytest.skip("no display")
    return Gtk


def build(monkeypatch, props):
    monkeypatch.setattr(ck, "datetime", SimpleNamespace(now=lambda: datetime(2026, 1, 2, 9, 5, 7)))
    widget = ck.ClockWidget()
    box = widget.build(props)
    widget.destroy()  # no timer left behind
    return box, widget._time


def test_the_built_label_shows_the_format(gtk, monkeypatch):
    _box, label = build(monkeypatch, ClockProps(format="ddd HH:mm:ss"))
    assert label.get_label() == "Fri 09:05:07"


def test_font_and_size_reach_the_label(gtk, monkeypatch):
    _box, label = build(monkeypatch, ClockProps(font="Hack Nerd Font Mono", font_size=30))
    from gi.repository import Pango

    font = label.get_style_context().get_property("font", gtk.StateFlags.NORMAL)
    assert font.get_family() == "Hack Nerd Font Mono"
    assert font.get_size() / Pango.SCALE == 30  # points


def test_without_font_properties_the_label_keeps_the_theme_font(gtk, monkeypatch):
    added = []
    monkeypatch.setattr(
        gtk.StyleContext, "add_provider", lambda self, p, prio: added.append(prio), raising=True
    )
    build(monkeypatch, ClockProps())
    assert added == []
    build(monkeypatch, ClockProps(font_size=12))
    assert added == [ck.FONT_PRIORITY] and ck.FONT_PRIORITY > gtk.STYLE_PROVIDER_PRIORITY_USER
```

Create (or replace entirely) `tests/test_clock_format.py`:

```python
"""The clock's format tokens (panel/widget spec 3.4): a fixed table, never strftime on user
text."""

from datetime import datetime

import pytest

from services.clock_format import TOKENS, format_clock, parse_clock_format

NOW = datetime(2026, 10, 14, 9, 5, 7)  # a Wednesday
EVENING = datetime(2026, 1, 2, 21, 30, 0)  # a Friday


def fmt(text, now=NOW):
    return format_clock(parse_clock_format(text), now)


def test_the_token_table_is_fixed():
    assert set(TOKENS) == {"HH", "mm", "ss", "H", "h", "a", "ddd", "dd", "MMM", "MM", "yyyy"}


@pytest.mark.parametrize(
    ("text", "morning", "evening"),
    [
        ("HH:mm", "09:05", "21:30"),
        ("HH:mm:ss", "09:05:07", "21:30:00"),
        ("H:mm", "9:05", "21:30"),
        ("h:mm a", "9:05 AM", "9:30 PM"),
        ("ddd dd MMM", "Wed 14 Oct", "Fri 02 Jan"),
        ("dd.MM.yyyy", "14.10.2026", "02.01.2026"),
        ("yyyy-MM-dd HH:mm", "2026-10-14 09:05", "2026-01-02 21:30"),
    ],
)
def test_tokens_are_replaced_and_the_rest_is_kept(text, morning, evening):
    assert (fmt(text), fmt(text, EVENING)) == (morning, evening)


def test_midnight_and_noon_on_the_12_hour_clock():
    assert fmt("h a", datetime(2026, 1, 1, 0, 0)) == "12 AM"
    assert fmt("h a", datetime(2026, 1, 1, 12, 0)) == "12 PM"


def test_strftime_sequences_are_plain_text():
    # `%` is literal: no user text ever reaches strftime ("%%", "%n" stay as typed)
    assert fmt("%% %- HH") == "%% %- 09"
    assert fmt("[HH]") == "[09]" and fmt("HH–mm") == "09–05"  # non-ASCII punctuation is text


@pytest.mark.parametrize(
    ("text", "letter", "position"),
    [
        ("%Y", "Y", 2),  # a strftime letter is not a token
        ("HH:m", "m", 4),  # one m is not a token
        ("yy", "y", 1),
        ("MMMM", "M", 4),  # MMM then a lone M
        ("HH at mm", "t", 5),  # unquoted: a is a token, then a lone t
    ],
)
def test_any_other_letter_is_an_error_naming_it(text, letter, position):
    with pytest.raises(ValueError) as exc:
        parse_clock_format(text)
    assert f"unknown token {letter!r} at position {position}" in str(exc.value)
    assert "HH, mm, ss" in str(exc.value) and "single quotes" in str(exc.value)


@pytest.mark.parametrize(
    ("text", "shown"),
    [
        ("HH 'at' mm", "09 at 05"),
        ("'Uhr' HH", "Uhr 09"),
        ("'%Y %n' HH", "%Y %n 09"),  # quoted strftime codes stay text
        ("HH''mm", "09'05"),  # two quotes outside quoted text: one quote
        ("'it''s' HH", "it's 09"),  # two quotes inside quoted text: one quote
        ("''", "'"),
        ("HH ''", "09 '"),
        ("'' HH '' mm", "' 09 ' 05"),
        ("HH ''''", "09 ''"),
        ("'' 'x'", "' x"),
    ],
)
def test_quoted_text_is_shown_as_written(text, shown):
    assert fmt(text) == shown


@pytest.mark.parametrize(("text", "position"), [("HH 'at", 4), ("'", 1), ("HH 'it''s", 4)])
def test_an_unterminated_quote_is_an_error(text, position):
    with pytest.raises(ValueError, match=f"unterminated quote at position {position}"):
        parse_clock_format(text)


def test_literal_text_is_kept_together():
    assert parse_clock_format("HH'h'' '") == ((True, "HH"), (False, "h' "))
    assert parse_clock_format("HH h:mm") == (
        (True, "HH"),
        (False, " "),
        (True, "h"),
        (False, ":"),
        (True, "mm"),
    )
```


- [ ] **Step 2: Run them to verify they fail**

Run: `scripts/py -m pytest -q tests/test_clock_format.py tests/test_clock.py`
Expected: two collection errors, `ModuleNotFoundError: No module named 'services.clock_format'` and `ImportError: cannot import name 'label_font_css' from 'shell.theme'`.

- [ ] **Step 3: Implement**

Create (or replace entirely) `services/clock_format.py`:

```python
"""The clock's format: a fixed token table, never user text in strftime (panel/widget spec 3.4).
Pure.

Tokens: HH (hour 00-23), H (0-23), h (1-12), a (AM/PM), mm (minute), ss (second), dd (day
01-31), ddd (weekday, abbreviated), MM (month 01-12), MMM (month, abbreviated), yyyy (year).
Text in single quotes is shown as written, letters included ('at', 'Uhr'); two single quotes
('') are one quote, inside or outside quoted text; a quote that is never closed is an error.
Every other letter is an error; any other character (digits, spaces, punctuation, `%`, other
scripts) is shown as it is. The longest token wins: "MMM" is the month name, "MMMM" is MMM
then an M on its own, which is an error. Literal text never goes through strftime.
"""

from __future__ import annotations

from datetime import datetime

TOKENS = ("HH", "mm", "ss", "H", "h", "a", "ddd", "dd", "MMM", "MM", "yyyy")
_LONGEST_FIRST = sorted(TOKENS, key=len, reverse=True)
Part = tuple[bool, str]  # (is a token, the token or the literal text)


def _quoted(text: str, start: int) -> tuple[str, int]:
    """The text of the quote opened at `start` and the index after its closing quote."""
    out = []
    i = start + 1
    while i < len(text):
        if text.startswith("''", i):  # a quote inside quoted text
            out.append("'")
            i += 2
        elif text[i] == "'":
            return "".join(out), i + 1
        else:
            out.append(text[i])
            i += 1
    raise ValueError(
        f"unterminated quote at position {start + 1}; close it with ' (write '' for a quote)"
    )


def parse_clock_format(text: str) -> tuple[Part, ...]:
    """The format as tokens and literal text; ValueError naming the first unknown letter or
    an unterminated quote."""
    parts: list[Part] = []

    def literal(chars: str) -> None:
        if parts and not parts[-1][0]:
            parts[-1] = (False, parts[-1][1] + chars)
        elif chars:
            parts.append((False, chars))

    i = 0
    while i < len(text):
        if text.startswith("''", i):
            literal("'")
            i += 2
            continue
        if text[i] == "'":
            chars, i = _quoted(text, i)
            literal(chars)
            continue
        token = next((t for t in _LONGEST_FIRST if text.startswith(t, i)), None)
        if token is not None:
            parts.append((True, token))
            i += len(token)
            continue
        char = text[i]
        if char.isascii() and char.isalpha():
            raise ValueError(
                f"unknown token {char!r} at position {i + 1}; use {', '.join(TOKENS)}, or "
                "put text in single quotes"
            )
        literal(char)
        i += 1
    return tuple(parts)


def _token(token: str, now: datetime) -> str:
    match token:
        case "HH":
            return f"{now.hour:02d}"
        case "H":
            return str(now.hour)
        case "h":
            return str(now.hour % 12 or 12)
        case "a":
            return "AM" if now.hour < 12 else "PM"
        case "mm":
            return f"{now.minute:02d}"
        case "ss":
            return f"{now.second:02d}"
        case "dd":
            return f"{now.day:02d}"
        case "ddd":
            return now.strftime("%a")  # a fixed strftime string, never the user's text
        case "MM":
            return f"{now.month:02d}"
        case "MMM":
            return now.strftime("%b")
        case "yyyy":
            return f"{now.year:04d}"
    raise ValueError(f"unknown token {token!r}")


def format_clock(parts: tuple[Part, ...], now: datetime) -> str:
    return "".join(_token(value, now) if is_token else value for is_token, value in parts)
```

In `shell/config/models.py` replace

```python
class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


```

with

```python
class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def check_font_name(name: str) -> str:
    """A font family name: it goes unescaped into generated CSS (the theme's font list, a
    widget's font property), so CSS metacharacters are refused."""
    if _FONT_FORBIDDEN.search(name):
        raise ValueError(
            f"font name {name!r} must not contain a double quote, backslash, {{, }} or ;"
        )
    return name


```

In `shell/config/models.py` replace

```python
    def _font_names(cls, value: list[str]) -> list[str]:
        for name in value:
            if _FONT_FORBIDDEN.search(name):
                raise ValueError(
                    f"font name {name!r} must not contain a double quote, backslash, {{, }} or ;"
                )
        return value

```

with

```python
    def _font_names(cls, value: list[str]) -> list[str]:
        for name in value:
            check_font_name(name)
        return value

```

In `shell/theme.py` replace

```python


def to_css(theme: Theme, scope: str) -> str:
    s = f".{scope}"
```

with

```python


def label_font_css(font: str | None, size: int | None) -> str:
    """CSS for one label's own font (a widget's font and font_size properties; None: the
    theme's), for a provider on that label only; "" when both are None. The font name was
    checked by shell.config.models.check_font_name."""
    rules = []
    if font is not None:
        rules.append(f"font-family: {_font_stack([font])};")
    if size is not None:
        rules.append(f"font-size: {size}pt;")
    return f"label {{ {' '.join(rules)} }}" if rules else ""


def to_css(theme: Theme, scope: str) -> str:
    s = f".{scope}"
```

Create (or replace entirely) `widgets/clock.py`:

```python
"""Clock: time of day on the top edge. Its properties: format (a fixed token table,
services.clock_format), font and font_size (None: the theme's)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

import gi

gi.require_version("Gtk", "3.0")
from fabric.utils import invoke_repeater
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from gi.repository import GLib, Gtk
from pydantic import Field, field_validator

from services.clock_format import format_clock, parse_clock_format
from shell.config.models import check_font_name
from shell.panel_spec import PanelDefaults
from shell.registry import register_widget
from shell.theme import label_font_css
from shell.widget import Widget, WidgetProps

REFRESH_MS = 1000  # the minute rolls over within a second of the real change
# Above the app's stylesheet (Fabric adds it at USER priority): the label's own font wins.
FONT_PRIORITY = Gtk.STYLE_PROVIDER_PRIORITY_USER + 1


def format_time(now: datetime) -> str:
    """HH:mm (the summary block's time)."""
    return now.strftime("%H:%M")


class ClockProps(WidgetProps):
    format: Annotated[str, Field(min_length=1, max_length=64)] = Field(
        "HH:mm", description="HH mm ss H h a ddd dd MMM MM yyyy; other text in 'single quotes'"
    )
    font: Annotated[str, Field(min_length=1, max_length=100)] | None = Field(
        None, description="a font family; reset: the theme's font"
    )
    font_size: Annotated[int, Field(ge=6, le=96)] | None = Field(
        None, description="pt; reset: the theme's size"
    )

    @field_validator("format")
    @classmethod
    def _format(cls, value: str) -> str:
        parse_clock_format(value)
        return value

    @field_validator("font")
    @classmethod
    def _font(cls, value: str | None) -> str | None:
        return None if value is None else check_font_name(value)


@register_widget(
    "clock",
    title="Clock",
    props=ClockProps,
    edge=PanelDefaults(edge="top", length=168, depth=46, label="clock"),
)
class ClockWidget(Widget):
    def __init__(self) -> None:
        self._destroyed = False
        self._repeater_id = 0
        self._parts = parse_clock_format("HH:mm")

    def build(self, props: ClockProps):
        self._parts = parse_clock_format(props.format)
        self._time = Label(name="clock-time", label=self._text(datetime.now()))
        css = label_font_css(props.font, props.font_size)
        if css:
            provider = Gtk.CssProvider()
            provider.load_from_data(css.encode())
            self._time.get_style_context().add_provider(provider, FONT_PRIORITY)
        self._repeater_id = invoke_repeater(REFRESH_MS, self._refresh)
        return Box(name="clock", h_align="center", v_align="center", children=self._time)

    def _text(self, now: datetime) -> str:
        return format_clock(self._parts, now)

    def destroy(self) -> None:
        # Panels are rebuilt on config reload and hot-plug: stop the timer with them.
        self._destroyed = True
        if self._repeater_id:
            GLib.source_remove(self._repeater_id)
            self._repeater_id = 0

    def _refresh(self) -> bool:
        if self._destroyed:
            return False
        text = self._text(datetime.now())
        if text != self._time.get_label():  # avoid a relayout every second
            self._time.set_label(text)
        return True
```


- [ ] **Step 4: Run the tests to verify they pass**

Run: `scripts/py -m pytest -q tests/test_clock_format.py tests/test_clock.py`
Expected: `46 passed`.

- [ ] **Step 5: VERIFY and commit**

Run VERIFY. Expected: `2019 passed`, `All checks passed!`.

```bash
git add services/clock_format.py widgets/clock.py shell/config/models.py shell/theme.py tests/test_clock_format.py tests/test_clock.py
git commit -m "feat(clock): format from a fixed token table, font and font_size properties" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

**Reviewer mutations:** a lone letter accepted as text (`test_any_other_letter_is_an_error_naming_it`); `%` escaped or rewritten (`test_strftime_sequences_are_plain_text`); `h` at midnight giving 0 (`test_midnight_and_noon_on_the_12_hour_clock`); the font provider at APPLICATION priority, below the app's stylesheet (`test_without_font_properties_the_label_keeps_the_theme_font`); the font-name check dropped (`test_bad_properties_are_refused`); an unclosed quote accepted, `''` kept as two quotes, or quoted letters read as tokens (`test_an_unterminated_quote_is_an_error`, `test_quoted_text_is_shown_as_written`); the size written in px (`test_the_label_font_css`, `test_font_and_size_reach_the_label`).

---

### Task 7: The settings form and values on the new model

The form adds a `name` text row and the `panel` choice to both panel sections (name, widget and panel type first), marks the three required keys (no reset), and generates a "Widget" section for each widget from its own property model, reached through `WidgetChoice` values that `registry_widgets()` builds from the registry. Widget property rows are typed by their schema only. Values give `name`, `panel` and every widget property a value and a source; `panel_ops` turns a widget switch and a panel-type switch into one edit that drops the keys the new widget or kind does not take (the name stays); a new panel is named after the widget's title. `fields.py` gets the text row editor the new rows need.

**Files:**
- Modify: `settings/form.py` (the part above "value conversions" is replaced), `settings/values.py`, `settings/fields.py` (`TextEditor`), `settings/view.py` (`config_form(registry_widgets())`)
- Modify: `tests/test_settings_form.py`, `tests/test_settings_values.py`, `tests/test_settings_fields.py`, `tests/test_settings_panels.py`

**Interfaces:**
- Consumes: `registry.widget_names`, `widget_title`, `supported_kinds`, `widget_props_model`, `defaults(id, kind)` (Task 3); `PANEL_KINDS`, `FRAMEWORK_KEYS` (Task 1); `ClockProps` descriptions (Task 6); `PanelRequest.props` (Task 3).
- Produces: `settings.form.WidgetChoice(id: str, title: str = "", kinds: tuple[str, ...] = ("edge",), props: type[BaseModel] | None = None)` with `.label`; `registry_widgets() -> tuple[WidgetChoice, ...]`; `config_form(widgets: tuple[WidgetChoice, ...] = ()) -> ConfigForm`; `ConfigForm.panel_for(kind: str, corner: str | None = None, kinds: tuple[str, ...] = ()) -> SectionSpec` (the panel type row only when `len(kinds) > 1`, with `disabled` = the kinds not in `kinds`); `ConfigForm.widget_props(widget_id: str) -> SectionSpec | None` (key `""`, label `"Widget"`); `props_section(model) -> SectionSpec | None`; `FieldSpec.disabled: tuple[str, ...]`, `FieldSpec.required: bool`; field kind `"text"`; `widget_choices(widgets) -> (ids, labels)` sorted by title; `KIND_LABELS`, `LEAD_ROWS`, `CORNER_ROWS`. `settings.values`: `field_value` for `name`, `panel` and widget properties (source `"widget default"` when unset, `default` = the model default); `panel_ops(entry, "panel", kind)`; `new_panel_entry` names a panel after `widget_title`. `settings.fields.TextEditor` (sends on Enter, focus-out or flush; None shows as empty). In a widget's section (`text=True`) the form refuses, with ValueError, exactly what `registry.form_type_ok` refuses: a union of two types, a Literal of non-strings, an array, an object, a nested model, a number.

- [ ] **Step 1: Write the failing tests**

In `tests/test_settings_fields.py` replace

```python

import settings.fields as fields  # noqa: E402
from settings.form import FieldSpec, config_form  # noqa: E402
from settings.values import FieldValue  # noqa: E402

FORM = config_form(("clock", "dock", "system_bar"))
REAL_TIMEOUT_ADD = GLib.timeout_add

```

with

```python

import settings.fields as fields  # noqa: E402
from settings.form import FieldSpec, WidgetChoice, config_form  # noqa: E402
from settings.values import FieldValue  # noqa: E402

FORM = config_form(tuple(WidgetChoice(w) for w in ("clock", "dock", "system_bar")))
REAL_TIMEOUT_ADD = GLib.timeout_add

```

In `tests/test_settings_fields.py` replace

```python

def test_choices_show_their_labels():
    form = config_form(("box", "clock"), corner_widgets=("box",))
    row, _, _ = row_for(form.edge_panel.field("widget"), "clock")
    assert [r[0] for r in row.editor.widget.get_model()] == ["clock", "box (corner panel)"]
    row.editor.widget.set_active_id("box")
    assert row.editor.widget.get_active_text() == "box (corner panel)"


```

with

```python

def test_choices_show_their_labels():
    form = config_form(
        (WidgetChoice("summary", "Summary", ("corner",)), WidgetChoice("clock", "Clock"))
    )
    row, _, _ = row_for(form.edge_panel.field("widget"), "clock")
    assert [r[0] for r in row.editor.widget.get_model()] == ["Clock", "Summary"]
    row.editor.widget.set_active_id("summary")
    assert row.editor.widget.get_active_text() == "Summary"


```

In `tests/test_settings_fields.py` replace

```python
    row.show_value(FieldValue("bogus", False, "default"))
    assert row.editor.widget.get_active_id() is None
```

with

```python
    row.show_value(FieldValue("bogus", False, "default"))
    assert row.editor.widget.get_active_id() is None


def test_a_text_row_sends_on_enter_or_flush_only_when_changed():
    row, changes, _ = row_for(FORM.edge_panel.field("name"), "Dock")
    entry = row.editor.widget
    assert entry.get_text() == "Dock" and not row.editor.dirty()
    entry.emit("activate")
    assert changes == []
    entry.set_text("Dock 2")
    assert row.editor.dirty()
    entry.emit("activate")
    entry.set_text("Bottom dock")  # typed, Enter not pressed: the window is closing
    row.flush()
    assert changes == [(("theme", "x"), "Dock 2"), (("theme", "x"), "Bottom dock")]


def test_a_text_row_shows_an_unset_value_as_empty():
    row, changes, _ = row_for(FieldSpec("font", "Font", "text"), None)
    assert row.editor.widget.get_text() == "" and not row.editor.dirty() and changes == []
```

In `tests/test_settings_form.py` replace

```python
"""settings.form: the form description generated from the JSON schema (pure)."""

import pytest

from settings import form as form_module
```

with

```python
"""settings.form: the form description generated from the JSON schema (pure)."""

from typing import Annotated, Literal

import pytest
from pydantic import Field, create_model

from settings import form as form_module
```

In `tests/test_settings_form.py` replace

```python
    LABELS,
    MODE_HINTS,
    config_form,
    format_fonts,
    join_length,
    parse_fonts,
    rgba_to_hex,
    section_for,
```

with

```python
    LABELS,
    MODE_HINTS,
    WidgetChoice,
    config_form,
    format_fonts,
    join_length,
    parse_fonts,
    props_section,
    rgba_to_hex,
    section_for,
```

In `tests/test_settings_form.py` replace

```python
    PanelConfig,
)

WIDGETS = ("clock", "dock", "system_bar")


```

with

```python
    PanelConfig,
)
from shell.widget import WidgetProps

WIDGETS = (
    WidgetChoice("clock", "Clock"),
    WidgetChoice("dock", "Dock"),
    WidgetChoice("system_bar", "System bar"),
)


```

In `tests/test_settings_form.py` replace

```python
def test_panel_fields(form):
    p = form.panel_for("edge")
    assert p is form.edge_panel and not {"corner", "width", "height"} & {f.key for f in p.fields}
    assert p.field("widget").kind == "widget" and p.field("widget").choices == WIDGETS
    assert p.field("edge").choices == ("top", "bottom", "left", "right")
    assert p.field("align").choices == ("start", "center", "end")
```

with

```python
def test_panel_fields(form):
    p = form.panel_for("edge")
    keys = [f.key for f in p.fields]
    assert keys[:2] == ["name", "widget"] and "panel" not in keys  # one kind: no kind row
    assert not {"corner", "width", "height"} & set(keys)
    name = p.field("name")
    assert (name.kind, name.required, name.label) == ("text", True, "Name")
    widget = p.field("widget")
    assert widget.kind == "widget" and widget.required
    assert widget.choices == ("clock", "dock", "system_bar")
    assert widget.labels == ("Clock", "Dock", "System bar")
    assert not p.field("edge").required
    assert p.field("edge").choices == ("top", "bottom", "left", "right")
    assert p.field("align").choices == ("start", "center", "end")
```

In `tests/test_settings_form.py` replace

```python
    """A corner widget's entry (spec 19): SHARED_KEYS plus CORNER_ONLY_KEYS."""
    p = form.panel_for("corner")
    assert [f.key for f in p.fields] == ["widget", "corner", "edge", "width", "height", "state"]
    assert p.field("corner").choices == CORNERS
    width = p.field("width")
```

with

```python
    """A corner widget's entry (spec 19): SHARED_KEYS plus CORNER_ONLY_KEYS."""
    p = form.panel_for("corner")
    assert [f.key for f in p.fields] == [
        "name",
        "widget",
        "corner",
        "edge",
        "width",
        "height",
        "state",
    ]
    assert p.field("corner").choices == CORNERS
    width = p.field("width")
```

In `tests/test_settings_form.py` replace

```python
    edge = {f.key for f in form.edge_panel.fields} | {s.key for s in form.edge_panel.sections}
    corner = {f.key for f in form.corner_panel.fields} | {s.key for s in form.corner_panel.sections}
    no_rows = {"panel", "name", "widget_props"}  # not shown as rows (yet)
    assert edge & corner == set(SHARED_KEYS) - no_rows
    assert edge | corner == set(PanelConfig.model_fields) - no_rows
    assert edge - corner == set(EDGE_ONLY_KEYS) and corner - edge == set(CORNER_ONLY_KEYS)

```

with

```python
    edge = {f.key for f in form.edge_panel.fields} | {s.key for s in form.edge_panel.sections}
    corner = {f.key for f in form.corner_panel.fields} | {s.key for s in form.corner_panel.sections}
    assert edge & corner == set(SHARED_KEYS)
    assert edge | corner == set(PanelConfig.model_fields) - {"widget_props"}
    assert edge - corner == set(EDGE_ONLY_KEYS) and corner - edge == set(CORNER_ONLY_KEYS)

```

In `tests/test_settings_form.py` replace

```python


def test_corner_widgets_are_listed_after_edge_widgets_and_labelled():
    form = config_form(("bar", "box", "clock"), corner_widgets=("box",))
    widget = form.edge_panel.field("widget")
    assert widget.choices == ("bar", "clock", "box")
    assert widget.labels == ("bar", "clock", "box (corner panel)")
    assert form.corner_panel.field("widget").choices == widget.choices

```

with

```python


def test_widgets_are_listed_by_their_display_name():
    form = config_form(
        (
            WidgetChoice("system_bar", "System bar"),
            WidgetChoice("summary", "Summary", ("corner",)),
            WidgetChoice("dock", "Dock"),
            WidgetChoice("x"),  # no title: its id
        )
    )
    widget = form.edge_panel.field("widget")
    assert widget.choices == ("dock", "summary", "system_bar", "x")
    assert widget.labels == ("Dock", "Summary", "System bar", "x")
    assert form.corner_panel.field("widget").choices == widget.choices

```

In `tests/test_settings_form.py` replace

```python
    )
    rows = [f.key for f in config_form(WIDGETS).corner_panel.fields]
    assert rows == ["widget", "corner", "edge", "width", "height", "state", "order"]


```

with

```python
    )
    rows = [f.key for f in config_form(WIDGETS).corner_panel.fields]
    assert rows == [
        "name",
        "widget",
        "panel",
        "corner",
        "edge",
        "width",
        "height",
        "state",
        "order",
    ]


```

In `tests/test_settings_form.py` replace

```python
    assert format_fonts(["A", "b c"]) == "A, b c"
    assert parse_fonts("  ") == []
```

with

```python
    assert format_fonts(["A", "b c"]) == "A, b c"
    assert parse_fonts("  ") == []


# ---- panel type and widget properties (panel/widget spec 3.7) -------------------------


class TileProps(WidgetProps):
    text: str = Field("hi", description="what it says")
    size: Annotated[int, Field(ge=6, le=96)] | None = None
    mode: Literal["a", "b"] = "a"
    on: bool = False


TILE = WidgetChoice("tile", "Tile", ("edge", "corner"), TileProps)


def test_a_widget_with_properties_gets_a_widget_section():
    form = config_form((TILE, WidgetChoice("dock", "Dock", props=WidgetProps)))
    section = form.widget_props("tile")
    assert (section.key, section.label, section.sections) == ("", "Widget", ())
    assert [f.key for f in section.fields] == ["text", "size", "mode", "on"]
    text, size, mode, on = section.fields
    assert (text.kind, text.hint, text.label, text.required) == (
        "text",
        "what it says",
        "Text",
        False,
    )
    assert (size.kind, size.minimum, size.maximum) == ("int", 6, 96)
    assert (mode.kind, mode.choices) == ("enum", ("a", "b"))
    assert on.kind == "bool"
    assert form.widget_props("dock") is None  # no properties: no section
    assert form.widget_props("nope") is None


def test_the_panel_type_row_shows_only_for_a_widget_of_several_kinds(form):
    assert "panel" not in [f.key for f in form.panel_for("edge", kinds=("edge",)).fields]
    both = form.panel_for("corner", "top-left", kinds=("edge", "corner"))
    assert [f.key for f in both.fields][:3] == ["name", "widget", "panel"]
    kind = both.field("panel")
    assert kind.choices == ("edge", "corner", "float") and kind.required
    assert kind.labels == ("Edge", "Corner", "Float (coming soon)")
    assert kind.disabled == ("float",)  # float is listed, never chosen
    assert both.field("edge").choices == ("top", "left")
    corner_only = form.panel_for("corner", kinds=("corner", "edge"))
    assert corner_only.field("panel").disabled == ("float",)


def test_the_registry_widgets_for_the_form(corner_registry):
    from settings.form import registry_widgets

    got = {w.id: (w.label, w.kinds, w.props) for w in registry_widgets()}
    assert got["box"] == ("Box", ("corner",), WidgetProps)
    assert got["dock"] == ("Dock", ("edge",), WidgetProps)


class Inner(WidgetProps):
    size: int = 1


@pytest.mark.parametrize(
    "annotation",
    [
        str,
        int,
        bool,
        Literal["a", "b"],
        str | None,
        Annotated[int, Field(ge=1, le=9)] | None,
        float,
        float | None,
        list[str],
        dict[str, int],
        Literal[1, 2],
        int | str,
        Inner,
    ],
    ids=repr,
)
def test_the_registry_refuses_exactly_the_property_types_the_form_cannot_show(annotation):
    """shell.registry.form_type_ok (checked at registration) and props_section (the settings
    window) must agree, so a registered widget always gets its Widget rows."""
    from shell.registry import form_type_ok

    model = create_model("Props", __base__=WidgetProps, font=(annotation, None))
    try:
        props_section(model)
        shown = True
    except ValueError:
        shown = False
    assert form_type_ok(model.model_fields["font"].annotation) is shown
```

In `tests/test_settings_panels.py` replace

```python

from settings.document import UserDocument  # noqa: E402
from settings.form import config_form  # noqa: E402
from shell.registry import requests_for  # noqa: E402

FORM = config_form(("bar", "clock", "dock"))
USER = (
    '[[monitors.M.panels]]\npanel = "edge"\nname = "dock"\nwidget = "dock"\n'
```

with

```python

from settings.document import UserDocument  # noqa: E402
from settings.form import WidgetChoice, config_form  # noqa: E402
from shell.registry import requests_for  # noqa: E402

FORM = config_form(tuple(WidgetChoice(w) for w in ("bar", "clock", "dock")))
CORNER_FORM = config_form(
    (
        WidgetChoice("bar", "Bar"),
        WidgetChoice("box", "Box", ("corner",)),
        WidgetChoice("clock", "Clock"),
        WidgetChoice("dock", "Dock"),
    )
)
USER = (
    '[[monitors.M.panels]]\npanel = "edge"\nname = "dock"\nwidget = "dock"\n'
```

In `tests/test_settings_panels.py` replace

```python
    """Spec 19: a corner widget's entry shows corner, edge (only its corner's two), width and
    height, never align or length; its title names the corner, the edge and the size."""
    form = config_form(("bar", "box", "clock", "dock"), corner_widgets=("box",))
    entries = [
        {"panel": "edge", "name": "dock", "widget": "dock"},
```

with

```python
    """Spec 19: a corner widget's entry shows corner, edge (only its corner's two), width and
    height, never align or length; its title names the corner, the edge and the size."""
    form = CORNER_FORM
    entries = [
        {"panel": "edge", "name": "dock", "widget": "dock"},
```

In `tests/test_settings_panels.py` replace

```python
    dock, box, moved = sections
    assert "align" in {f.key for f in dock.fields} and "corner" not in {f.key for f in dock.fields}
    assert [f.key for f in box.fields] == ["widget", "corner", "edge", "width", "height", "state"]
    assert box.field("edge").choices == ("bottom", "left")
    assert moved.field("edge").choices == ("top", "right")
    assert [row[0] for row in ed.widget_choice.get_model()] == [
        "bar",
        "clock",
        "dock",
        "box (corner panel)",
    ]
    edits = []
    ed._on_edit = lambda edit, open_index: edits.append((edit, open_index))
```

with

```python
    dock, box, moved = sections
    assert "align" in {f.key for f in dock.fields} and "corner" not in {f.key for f in dock.fields}
    assert [f.key for f in box.fields] == [
        "name",
        "widget",
        "corner",
        "edge",
        "width",
        "height",
        "state",
    ]
    assert box.field("edge").choices == ("bottom", "left")
    assert moved.field("edge").choices == ("top", "right")
    assert [row[0] for row in ed.widget_choice.get_model()] == ["Bar", "Box", "Clock", "Dock"]
    edits = []
    ed._on_edit = lambda edit, open_index: edits.append((edit, open_index))
```

In `tests/test_settings_panels.py` replace

```python
    assert (
        doc.data
        == {"monitors": {"M": {"panels": [{"panel": "corner", "name": "box", "widget": "box"}]}}}
        and edits[0][1] == 3
    )
```

with

```python
    assert (
        doc.data
        == {"monitors": {"M": {"panels": [{"panel": "corner", "name": "Box", "widget": "box"}]}}}
        and edits[0][1] == 3
    )
```

In `tests/test_settings_panels.py` replace

```python

def test_add_panel_button_writes_a_corner_widgets_id_not_its_label(make_config, corner_registry):
    form = config_form(("bar", "box", "clock", "dock"), corner_widgets=("box",))
    ed, edits = three_panel_editor(make_config, form)
    ed.widget_choice.set_active_id("box")
    assert ed.widget_choice.get_active_text() == "box (corner panel)"
    click_add(ed)
    ((edit, open_index),) = edits
```

with

```python

def test_add_panel_button_writes_a_corner_widgets_id_not_its_label(make_config, corner_registry):
    form = CORNER_FORM
    ed, edits = three_panel_editor(make_config, form)
    ed.widget_choice.set_active_id("box")
    assert ed.widget_choice.get_active_text() == "Box"
    click_add(ed)
    ((edit, open_index),) = edits
```

In `tests/test_settings_panels.py` replace

```python
    edit(doc)
    assert doc.data == {
        "monitors": {"M": {"panels": [{"panel": "corner", "name": "box", "widget": "box"}]}}
    }

```

with

```python
    edit(doc)
    assert doc.data == {
        "monitors": {"M": {"panels": [{"panel": "corner", "name": "Box", "widget": "box"}]}}
    }

```

In `tests/test_settings_values.py` replace

```python
import pytest

from settings.form import config_form
from settings.values import (
    PLACEMENT_DEFAULT,
```

with

```python
import pytest

from settings.form import WidgetChoice, config_form
from settings.values import (
    PLACEMENT_DEFAULT,
```

In `tests/test_settings_values.py` replace

```python
from shell.config.models import ConfigError
from shell.outputs import Output
from shell.registry import validate_widgets

USER = {
```

with

```python
from shell.config.models import ConfigError
from shell.outputs import Output
from shell.panel_spec import CornerDefaults, PanelDefaults
from shell.registry import validate_widgets
from shell.widget import Widget, WidgetProps

USER = {
```

In `tests/test_settings_values.py` replace

```python
    """Every row of both panel sections, on every entry of either kind: a value, no KeyError
    (the view refreshes every row it built)."""
    form = config_form(("bar", "box", "clock", "dock"), corner_widgets=("box",))

    def paths(section, prefix):
```

with

```python
    """Every row of both panel sections, on every entry of either kind: a value, no KeyError
    (the view refreshes every row it built)."""
    form = config_form(
        (
            *(WidgetChoice(w) for w in ("bar", "clock", "dock")),
            WidgetChoice("box", kinds=("corner",)),
        )
    )

    def paths(section, prefix):
```

In `tests/test_settings_values.py` replace

```python
        }
    }
    assert new_panel_entry(user, "M", "dock") == {
        "panel": "edge",
        "name": "dock 3",
        "widget": "dock",
    }
    assert new_panel_entry(user, "M", "box") == {"panel": "corner", "name": "box", "widget": "box"}
    assert new_panel_entry(user, "N", "dock")["name"] == "dock"  # another monitor: free
    assert new_panel_entry({}, "M", "nope") == {"panel": "edge", "name": "nope", "widget": "nope"}
```

with

```python
        }
    }
    user["monitors"]["M"]["panels"][1]["name"] = "Dock"  # the title, as the window writes
    assert new_panel_entry(user, "M", "dock") == {
        "panel": "edge",
        "name": "Dock 2",
        "widget": "dock",
    }
    assert new_panel_entry(user, "M", "box") == {"panel": "corner", "name": "Box", "widget": "box"}
    assert new_panel_entry(user, "N", "dock")["name"] == "Dock"  # another monitor: free
    assert new_panel_entry({}, "M", "nope") == {"panel": "edge", "name": "nope", "widget": "nope"}


# ---- name, panel type and widget properties (panel/widget spec 3.7) -------------------


class TileProps(WidgetProps):
    text: str = "hi"
    size: int | None = None


@pytest.fixture
def tile(corner_registry):
    """corner_registry plus "tile": edge and corner, two properties."""
    corner_registry.register_widget(
        "tile",
        title="Tile",
        props=TileProps,
        edge=PanelDefaults(edge="top", length=200, depth=50, label="tile"),
        corner=CornerDefaults(corner="top-right", width=240, height=200, label="tile"),
    )(type("Tile", (Widget,), {}))
    return corner_registry


def test_name_panel_and_widget_property_values(tile, make_config):
    entry = {"panel": "corner", "name": "T", "widget": "tile", "size": 12}
    config = make_config(monitors={"M": {"panels": [entry]}})
    user = {"monitors": {"M": {"panels": [entry]}}}
    p = ("monitors", "M", "panels", 0)
    assert field_value(config, user, (*p, "name")) == FieldValue("T", True, "your config")
    assert field_value(config, user, (*p, "panel")) == FieldValue("corner", True, "your config")
    size = field_value(config, user, (*p, "size"))
    assert size == FieldValue(12, True, "your config") and size.default is None
    text = field_value(config, user, (*p, "text"))
    assert text == FieldValue("hi", False, "widget default") and text.default == "hi"
    with pytest.raises(KeyError):
        field_value(config, user, (*p, "colour"))


def test_a_new_widget_drops_the_old_widgets_keys(tile, make_config):
    entry = {"panel": "edge", "name": "T", "widget": "tile", "text": "x", "size": 9, "depth": 80}
    ops = panel_ops(entry, "widget", "dock")
    assert ops == [("set", "widget", "dock"), ("unset", "text", None), ("unset", "size", None)]
    result = _applied(entry, ops)
    assert result == {"panel": "edge", "name": "T", "widget": "dock", "depth": 80}
    _valid(make_config, result)


def test_a_widget_of_both_kinds_keeps_the_entrys_kind(tile, make_config):
    entry = {"panel": "corner", "name": "B", "widget": "box", "corner": "top-left"}
    assert panel_ops(entry, "widget", "tile") == [("set", "widget", "tile")]
    _valid(make_config, _applied(entry, panel_ops(entry, "widget", "tile")))


def test_a_new_panel_type_drops_the_old_kinds_keys(tile, make_config):
    entry = {"panel": "edge", "name": "T", "widget": "tile", "align": "end", "edge": "left"}
    ops = panel_ops(entry, "panel", "corner")
    assert ops == [("set", "panel", "corner"), ("unset", "align", None), ("unset", "edge", None)]
    _valid(make_config, _applied(entry, ops))  # left is not an edge of top-right: it goes
    back = {"panel": "corner", "name": "T", "widget": "tile", "corner": "top-left", "width": 300}
    ops = panel_ops(back, "panel", "edge")
    assert ops == [("set", "panel", "edge"), ("unset", "corner", None), ("unset", "width", None)]
    _valid(make_config, _applied(back, ops))


@pytest.mark.parametrize("kind", ["float", "corner"])
def test_a_panel_type_the_widget_cannot_take_is_a_plain_set_for_the_session(tile, kind):
    entry = {"panel": "edge", "name": "D", "widget": "dock", "align": "end"}
    assert panel_ops(entry, "panel", kind) == [("set", "panel", kind)]
```


- [ ] **Step 2: Run them to verify they fail**

Run: `scripts/py -m pytest -q tests/test_settings_form.py tests/test_settings_values.py tests/test_settings_fields.py tests/test_settings_panels.py`
Expected: four collection errors, `ImportError: cannot import name 'WidgetChoice' from 'settings.form'`.

- [ ] **Step 3: Implement**

In `settings/fields.py` replace

```python


class LengthEditor(_Editor):
    """A mode (px, fill, content, percent) and a number for px and percent. Switching to px or
```

with

```python


class TextEditor(_Editor):
    """A line of text (a panel's name, a widget's text property): sent on Enter or when the
    entry loses focus, like the font list."""

    def __init__(self, emit: Emit):
        self.widget = Gtk.Entry(width_chars=30)
        self._shown = ""
        self._emit = emit
        self.widget.connect("activate", lambda *_a: self.commit())
        self.widget.connect("focus-out-event", lambda *_a: self.commit() or False)

    def dirty(self) -> bool:
        return self.widget.get_text() != self._shown

    def commit(self) -> None:
        text = self.widget.get_text()
        if text != self._shown:
            self._shown = text
            self._emit(text)

    def set(self, value: str | None) -> None:
        self._shown = "" if value is None else str(value)
        self.widget.set_text(self._shown)


class LengthEditor(_Editor):
    """A mode (px, fill, content, percent) and a number for px and percent. Switching to px or
```

In `settings/fields.py` replace

```python
    if spec.kind == "fonts":
        return FontsEditor(emit)
    if spec.kind == "length":
        return LengthEditor(emit)
```

with

```python
    if spec.kind == "fonts":
        return FontsEditor(emit)
    if spec.kind == "text":
        return TextEditor(emit)
    if spec.kind == "length":
        return LengthEditor(emit)
```

Create (or replace entirely) `settings/form.py`:

```python
"""Form description generated from the config models' JSON schema. Pure: no GTK, no tomlkit.

A form is a tree of SectionSpec (one per TOML table) holding FieldSpec (one per key). The GTK
renderer (settings.fields, settings.window) turns each FieldSpec into one row; everything a
row needs (kind, bounds, choices) is here, so it is tested without a display. The values shown
in the rows come from settings.values.

Widget properties (panel/widget spec 3.4) are not in Config's schema: PanelConfig collects them
in a plain `widget_props` dict, so the schema cannot say which keys a widget has. The form
reads each widget's own property model instead (WidgetChoice.props, from the registry) and
walks its schema the same way: ConfigForm.widget_props(widget_id).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Literal

from pydantic import BaseModel

from shell.config.models import (
    COLOR_FIELDS,
    CORNER_ONLY_KEYS,
    EDGE_ONLY_KEYS,
    PANEL_KINDS,
    Config,
)

FieldKind = Literal[
    "color", "int", "bool", "enum", "fonts", "length", "widget", "deprecated", "text"
]

# Keys holding a #rrggbb / #rrggbbaa colour. The models check them with a field validator,
# which the JSON schema does not show, so they are recognised by name (pinned by a test).
COLOR_KEYS = frozenset(COLOR_FIELDS) | {"color", "hover_color"}
LENGTH_PX = (60, 4000)  # shell.config.models.check_length
LENGTH_PERCENT = (1, 100)
LENGTH_MODES = ("px", "fill", "content", "percent")
# The unit or meaning shown next to a row, by (model, key): one key can mean different things
# in different tables ("width" of the border vs the width of a corner panel). A widget
# property's hint is its Field(description=...).
HINTS = {
    ("Theme", "thickness"): "px",
    ("Theme", "radius"): "px",
    ("Theme", "peek"): "px",
    ("Theme", "hover_zone"): "px",
    ("Theme", "duration_ms"): "ms",
    ("Border", "width"): "px",
    ("Shadow", "elevation"): "% (100 % = 48 px)",
    ("HandleStyle", "size"): "px along the edge",
    ("HandleStyle", "weight"): "px",
    ("HandleConfig", "size"): "px along the edge",
    ("HandleConfig", "weight"): "px",
    ("HandleConfig", "offset"): "px from the middle of the panel",
    ("LayoutSettings", "gap"): "px between neighbouring panels",
    ("PanelConfig", "name"): "unique on this monitor; shown in logs, notifications and here",
    ("PanelConfig", "panel"): "the panel type (float panels are coming later)",
    ("PanelConfig", "offset"): "px from the aligned end",
    ("PanelConfig", "depth"): "px past the frame",
    ("PanelConfig", "min_length"): "px",
    ("PanelConfig", "max_length"): "px",
    ("PanelConfig", "order"): "within its align slot; equal orders keep the config order",
    ("PanelConfig", "pos"): "deprecated: reset it and use align and offset",
    ("PanelConfig", "width"): "px from the screen corner, frame included",
    ("PanelConfig", "height"): "px from the screen corner, frame included",
}
# Row labels; any other key reads "Some key" (pydantic's own titles read "Duration Ms").
LABELS = {
    "duration_ms": "Duration",
    "text_secondary": "Secondary text",
    "surface_hover": "Surface (hover)",
    "handle_hover": "Handle (hover)",
    "hover_color": "Hover colour",
    "color": "Colour",
    "min_length": "Minimum length",
    "max_length": "Maximum length",
    "pos": "Position (deprecated)",
    "shell": "Mode",
    "panel": "Panel type",
}
MODE_HINTS = {
    "edge": "Edge Shell frame and panels",
    "plasma": "no Edge Shell here; Plasma's panels stay as they are",
    "both": "Edge Shell frame and panels next to Plasma's panel: keep Edge Shell panels off "
    "the edge Plasma's panel uses",
    "none": "no Edge Shell here (the same as plasma until the Plasma panel toggle exists)",
}
KIND_LABELS = {"edge": "Edge", "corner": "Corner", "float": "Float (coming soon)"}
LEAD_ROWS = ("name", "widget", "panel")  # every panel section starts with these
CORNER_ROWS = (*LEAD_ROWS, "corner", "edge", "width", "height", "state")  # a corner panel


@dataclass(frozen=True)
class FieldSpec:
    key: str  # the key inside its table
    label: str
    kind: FieldKind
    choices: tuple[str, ...] = ()
    minimum: int | None = None
    maximum: int | None = None
    hint: str = ""
    labels: tuple[str, ...] = ()  # what the choices show (empty: the choices themselves)
    disabled: tuple[str, ...] = ()  # choices shown but not selectable ("coming soon")
    required: bool = False  # the entry needs it: no reset button


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


@dataclass(frozen=True)
class WidgetChoice:
    """A registered widget as the form needs it (settings.view builds them from the registry:
    registry_widgets)."""

    id: str
    title: str = ""  # "" = the id
    kinds: tuple[str, ...] = ("edge",)  # the panel kinds it can be shown in
    props: type[BaseModel] | None = None  # its property model (None: no properties)

    @property
    def label(self) -> str:
        return self.title or self.id


def registry_widgets() -> tuple[WidgetChoice, ...]:
    """Every registered widget (shell.registry), for config_form."""
    from shell import registry

    return tuple(
        WidgetChoice(
            name,
            registry.widget_title(name),
            registry.supported_kinds(name),
            registry.widget_props_model(name),
        )
        for name in registry.widget_names()
    )


def _options(prop: dict) -> list[dict]:
    """The non-null alternatives of a property (an optional key is anyOf [..., null])."""
    return [o for o in prop.get("anyOf", [prop]) if o.get("type") != "null"]


def label_for(key: str) -> str:
    return LABELS.get(key, key.replace("_", " ").capitalize())


def widget_choices(widgets: tuple[WidgetChoice, ...]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(ids, labels) of a widget combo: by display name (the registry's title)."""
    ordered = sorted(widgets, key=lambda w: (w.label.casefold(), w.id))
    return tuple(w.id for w in ordered), tuple(w.label for w in ordered)


def _field(
    model: str,
    key: str,
    prop: dict,
    widgets: tuple[WidgetChoice, ...],
    required: bool = False,
    text: bool = False,
) -> FieldSpec:
    """One row. `text` (a widget's properties): the row comes from the type alone, and any
    plain string is a text row. In the config models some keys are known by name (widget,
    panel, pos, length, the colours) and only `name` is a text row: every other string key
    must be classified here (pinned by a test)."""
    first = _options(prop)[0]
    hint = HINTS.get((model, key), prop.get("description", ""))
    common = {"key": key, "label": label_for(key), "hint": hint, "required": required}
    if not text:
        if key == "widget":
            choices, labels = widget_choices(widgets)
            return FieldSpec(kind="widget", choices=choices, labels=labels, **common)
        if key == "panel":
            labels = tuple(KIND_LABELS[k] for k in PANEL_KINDS)
            return FieldSpec(kind="enum", choices=PANEL_KINDS, labels=labels, **common)
        if key == "pos":
            return FieldSpec(kind="deprecated", **common)
        if key == "length":
            return FieldSpec(kind="length", minimum=LENGTH_PX[0], maximum=LENGTH_PX[1], **common)
        if key in COLOR_KEYS:
            return FieldSpec(kind="color", **common)
    if text and len(_options(prop)) != 1:
        raise ValueError(f"no form field for {key!r}: one type (or that type | None) only")
    if "enum" in first:
        if text and not all(isinstance(v, str) for v in first["enum"]):
            raise ValueError(f"no form field for {key!r}: a Literal of strings only")
        return FieldSpec(kind="enum", choices=tuple(first["enum"]), **common)
    if first.get("type") == "boolean":
        return FieldSpec(kind="bool", **common)
    if first.get("type") == "integer":
        return FieldSpec(
            kind="int", minimum=first.get("minimum"), maximum=first.get("maximum"), **common
        )
    if not text and key == "font" and first.get("type") == "array":
        return FieldSpec(kind="fonts", **common)
    if first.get("type") == "string" and (text or key == "name"):
        return FieldSpec(kind="text", **common)
    raise ValueError(f"no form field for {key!r}: {prop}")


def section_for(
    schema: dict,
    name: str,
    key: str = "",
    label: str = "",
    widgets: tuple[WidgetChoice, ...] = (),
    skip: tuple[str, ...] = (),
    text: bool = False,
    required: tuple[str, ...] = (),
) -> SectionSpec:
    """The section for the model `name` in `schema["$defs"]`. Nested models become
    sub-sections; keys in `skip` are left out (the panel list has its own editor; a panel
    section leaves out the other kind's keys); keys in `required` get no reset button (a
    panel entry's panel, name and widget: the file must have them, while a theme key the
    model requires comes from the defaults file)."""
    model = schema["$defs"][name]
    fields: list[FieldSpec] = []
    sections: list[SectionSpec] = []
    for fkey, prop in model["properties"].items():
        if fkey in skip:
            continue
        ref = _options(prop)[0].get("$ref")
        if ref is not None:
            if text:  # a widget property is one row, never a table
                raise ValueError(f"no form field for {fkey!r}: a nested model")
            sub = ref.rsplit("/", 1)[-1]
            title = fkey.replace("_", " ").capitalize()
            sections.append(section_for(schema, sub, fkey, title, widgets, text=text))
        else:
            fields.append(_field(name, fkey, prop, widgets, fkey in required, text))
    return SectionSpec(key, label or name, tuple(fields), tuple(sections))


def props_section(model: type[BaseModel]) -> SectionSpec | None:
    """The "Widget" section of a widget's property model: one row per property (keys of the
    panel entry itself, so the section key is ""); None when it has no properties."""
    schema = model.model_json_schema()
    if not schema.get("properties"):
        return None
    defs = {**schema.get("$defs", {}), model.__name__: schema}
    return section_for({"$defs": defs}, model.__name__, "", "Widget", text=True)


def _ranked(section: SectionSpec, order: tuple[str, ...]) -> SectionSpec:
    rank = {k: i for i, k in enumerate(order)}
    rows = sorted(section.fields, key=lambda f: rank.get(f.key, len(order)))
    return replace(section, fields=tuple(rows))


@dataclass(frozen=True)
class ConfigForm:
    theme: SectionSpec  # [theme], also the per-monitor [monitors.NAME.theme] override
    layout: SectionSpec  # [layout], also [monitors.NAME.layout]
    monitor: SectionSpec  # [monitors.NAME] keys other than its tables: the shell mode
    edge_panel: SectionSpec  # a [[monitors.NAME.panels]] entry of an edge panel
    corner_panel: SectionSpec  # ... of a corner panel (spec 19)
    # widget id -> its "Widget" section (only widgets that have properties)
    widget_sections: dict[str, SectionSpec] = field(default_factory=dict)

    def panel_for(
        self, kind: str, corner: str | None = None, kinds: tuple[str, ...] = ()
    ) -> SectionSpec:
        """The section of a panel entry of `kind` (its `panel` key: "edge" or "corner").
        Given the `corner` in effect, a corner panel's edge row offers only that corner's two
        edges (corner.split("-")). `kinds`: the kinds the entry's widget supports; with more
        than one the "Panel type" row is shown, the kinds it does not support (and float)
        greyed out; with one it is left out."""
        if kind == "edge":
            section = self.edge_panel
        elif kind == "corner":
            section = self.corner_panel
        else:
            raise ValueError(f"unknown panel kind {kind!r}")
        fields = []
        for f in section.fields:
            if f.key == "panel":
                if len(kinds) < 2:
                    continue
                f = replace(f, disabled=tuple(k for k in f.choices if k not in kinds))
            if f.key == "edge" and kind == "corner" and corner is not None:
                f = replace(f, choices=tuple(corner.split("-")))
            fields.append(f)
        return replace(section, fields=tuple(fields))

    def widget_props(self, widget_id: str) -> SectionSpec | None:
        """The "Widget" section of a widget's properties; None when it has none (or is not
        known)."""
        return self.widget_sections.get(widget_id)


def config_form(widgets: tuple[WidgetChoice, ...] = ()) -> ConfigForm:
    """Every section the settings window shows; `widgets`: the registered widgets
    (registry_widgets()).

    Per-monitor overrides use the base models (Theme, LayoutSettings), not ThemeOverride /
    LayoutOverride: those are built with create_model from the bare annotations and lose the
    bounds (their schema has no minimum / maximum). The two panel sections split PanelConfig
    by the models' own key sets: an edge panel skips CORNER_ONLY_KEYS, a corner panel skips
    EDGE_ONLY_KEYS (SHARED_KEYS are in both); `widget_props` is the widget keys' bag, shown
    per widget (widget_props(widget_id))."""
    schema = Config.model_json_schema()

    required = tuple(schema["$defs"]["PanelConfig"]["required"])  # panel, name, widget

    def panel(skip: tuple[str, ...]) -> SectionSpec:
        skip += ("widget_props",)
        return section_for(schema, "PanelConfig", "", "Panel", widgets, skip, required=required)

    sections = {}
    for w in widgets:
        section = None if w.props is None else props_section(w.props)
        if section is not None:
            sections[w.id] = section
    return ConfigForm(
        theme=section_for(schema, "Theme", "theme", "Theme"),
        layout=section_for(schema, "LayoutSettings", "layout", "Layout"),
        monitor=section_for(
            schema, "MonitorConfig", "", "Monitor", skip=("theme", "layout", "panels")
        ),
        edge_panel=_ranked(panel(CORNER_ONLY_KEYS), LEAD_ROWS),
        corner_panel=_ranked(panel(EDGE_ONLY_KEYS), CORNER_ROWS),
        widget_sections=sections,
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

In `settings/values.py` replace

```python
file sets that key (the row's reset button removes it); `source` names where an unset value
is inherited from. Panel entries are edge or corner panels (spec 19): the entry's `panel`
key is its kind and decides which keys the entry takes.
"""

```

with

```python
file sets that key (the row's reset button removes it); `source` names where an unset value
is inherited from. Panel entries are edge or corner panels (spec 19): the entry's `panel`
key is its kind and decides which keys the entry takes; every key that is not a panel key
(FRAMEWORK_KEYS) is a property of the entry's widget (registry.widget_props_model).
"""

```

In `settings/values.py` replace

```python
from typing import Any

from shell.config.models import CORNER_ONLY_KEYS, EDGE_ONLY_KEYS, Config
from shell.outputs import Output
from shell.panel_layout import layout_monitor
from shell.panel_spec import CornerDefaults, CornerRequest, corner_has_edge, default_edge
from shell.registry import defaults, request_for, requests_for, supported_kinds

# keys whose value in effect is the request's (the entry's, else the widget's default)
```

with

```python
from typing import Any

from shell.config.models import CORNER_ONLY_KEYS, EDGE_ONLY_KEYS, FRAMEWORK_KEYS, Config
from shell.outputs import Output
from shell.panel_layout import layout_monitor
from shell.panel_spec import CornerDefaults, CornerRequest, corner_has_edge, default_edge
from shell.registry import (
    defaults,
    request_for,
    requests_for,
    supported_kinds,
    widget_props_model,
    widget_title,
)

# keys whose value in effect is the request's (the entry's, else the widget's default)
```

In `settings/values.py` replace

```python
    d = defaults(entry.widget, entry.panel)  # public registry API: never _WIDGETS
    key = keys[0]
    if key == "interaction":
        # always "default": no widget registers interaction defaults today (if one does, the
```

with

```python
    d = defaults(entry.widget, entry.panel)  # public registry API: never _WIDGETS
    key = keys[0]
    if key in ("name", "panel"):  # required: always in the file
        return FieldValue(getattr(entry, key), is_set, _src(is_set, "not set"))
    if key not in FRAMEWORK_KEYS:  # a widget property: the entry's, else the model's default
        model = widget_props_model(entry.widget)
        if key not in model.model_fields:
            raise KeyError(f"{entry.widget} has no property {key!r}")
        default = model.model_fields[key].default
        source = _src(is_set, "widget default")
        return FieldValue(getattr(req.props, key), is_set, source, default)
    if key == "interaction":
        # always "default": no widget registers interaction defaults today (if one does, the
```

In `settings/values.py` replace

```python
    - A widget that cannot be shown in the entry's kind also sets `panel` to the first kind
      it supports and unsets the keys only the old kind takes (a dock turned into a corner
      widget loses its align, length, ...; spec 19), else the shell rejects it. The entry
      keeps its name.
    - `value` None for "corner" is a reset: the key is unset and the widget's corner applies.
    - An unknown widget is a plain set (the session's check rejects it, ConfigError).
    - A corner (or a corner widget whose corner) that does not contain the entry's edge also
      unsets that edge: the panel then opens from the widget's edge or the corner's default."""
```

with

```python
    - A widget that cannot be shown in the entry's kind also sets `panel` to the first kind
      it supports and unsets the keys only the old kind takes (a dock turned into a corner
      widget loses its align, length, ...; spec 19), else the shell rejects it. The widget
      keys the new widget does not have go too. The entry keeps its name.
    - A new `panel` kind unsets the keys only the old kind takes, as above.
    - `value` None for "corner" is a reset: the key is unset and the widget's corner applies.
    - An unknown widget, float or a kind the widget does not support is a plain set (the
      session's check rejects it with the shell's text, ConfigError).
    - A corner (or a corner widget whose corner) that does not contain the entry's edge also
      unsets that edge: the panel then opens from the widget's edge or the corner's default."""
```

In `settings/values.py` replace

```python
        if entry.get("panel") != kind:
            ops.append(("set", "panel", kind))
        stale = CORNER_ONLY_KEYS if kind == "edge" else EDGE_ONLY_KEYS
        ops += [("unset", k, None) for k in stale if k in entry]
        if kind == "corner":
            corner = entry.get("corner", defaults(value, "corner").corner)
    elif key == "corner":
        corner = value or defaults(entry["widget"], "corner").corner
```

with

```python
        if entry.get("panel") != kind:
            ops.append(("set", "panel", kind))
        props = widget_props_model(value).model_fields
        ops += [("unset", k, None) for k in entry if k not in FRAMEWORK_KEYS and k not in props]
        ops += _kind_ops(entry, kind)
        if kind == "corner":
            corner = entry.get("corner", defaults(value, "corner").corner)
    elif key == "panel":
        try:
            supported = value in supported_kinds(entry["widget"])
        except KeyError:  # unknown widget: the session's check says so
            supported = False
        if not supported:  # float, or a kind the widget lacks: rejected by the session
            return ops
        ops += _kind_ops(entry, value)
        if value == "corner":
            corner = entry.get("corner", defaults(entry["widget"], "corner").corner)
    elif key == "corner":
        corner = value or defaults(entry["widget"], "corner").corner
```

In `settings/values.py` replace

```python
        ops.append(("unset", "edge", None))
    return ops


```

with

```python
        ops.append(("unset", "edge", None))
    return ops


def _kind_ops(entry: dict, kind: str) -> list[tuple[str, str, Any]]:
    """Unset the keys of the other panel kind (spec 19)."""
    stale = CORNER_ONLY_KEYS if kind == "edge" else EDGE_ONLY_KEYS
    return [("unset", k, None) for k in stale if k in entry]


```

In `settings/values.py` replace

```python
def new_panel_entry(user: dict, monitor: str, widget: str) -> dict[str, str]:
    """The keys a new panel of `widget` on `monitor` is written with (`user`: the user file's
    plain data): its kind, a name not used on that monitor yet and the widget; every other key
    comes from the widget's defaults. An unknown widget is written as an edge panel (the
    session's check rejects it with the shell's text)."""
    try:
        kind = supported_kinds(widget)[0]
    except KeyError:
        kind = "edge"
    _, panels = lookup(user, ("monitors", monitor, "panels"))
    taken = [p.get("name") for p in panels or () if isinstance(p, dict)]
    return {"panel": kind, "name": unique_name(widget, taken), "widget": widget}


```

with

```python
def new_panel_entry(user: dict, monitor: str, widget: str) -> dict[str, str]:
    """The keys a new panel of `widget` on `monitor` is written with (`user`: the user file's
    plain data): the first kind the widget supports, a name made from its title that is not
    used on that monitor yet ("Clock", "Clock 2", ...) and the widget; every other key comes
    from the widget's defaults. An unknown widget is written as an edge panel named after its
    id (the session's check rejects it with the shell's text)."""
    try:
        kind, title = supported_kinds(widget)[0], widget_title(widget)
    except KeyError:
        kind, title = "edge", widget
    _, panels = lookup(user, ("monitors", monitor, "panels"))
    taken = [p.get("name") for p in panels or () if isinstance(p, dict)]
    return {"panel": kind, "name": unique_name(title, taken), "widget": widget}


```

In `settings/view.py` replace

```python
from settings.document import UserDocument
from settings.fields import FieldRow
from settings.form import MODE_HINTS, SectionSpec, config_form
from settings.panels import PanelEditor
from settings.session import ChangedOutside, SettingsSession, check_text
```

with

```python
from settings.document import UserDocument
from settings.fields import FieldRow
from settings.form import MODE_HINTS, SectionSpec, config_form, registry_widgets
from settings.panels import PanelEditor
from settings.session import ChangedOutside, SettingsSession, check_text
```

In `settings/view.py` replace

```python
from shell.config.models import ConfigError
from shell.outputs import Output
from shell.registry import requests_for, supported_kinds, widget_names

Edit = Callable[[UserDocument], Any]
```

with

```python
from shell.config.models import ConfigError
from shell.outputs import Output
from shell.registry import requests_for

Edit = Callable[[UserDocument], Any]
```

In `settings/view.py` replace

```python
        self.session = session
        self.outputs = {o.name: o for o in outputs}
        names = tuple(widget_names())
        corner = tuple(n for n in names if supported_kinds(n)[0] == "corner")
        self.form = config_form(names, corner)
        self.rows: list[FieldRow] = []
        self.previews: dict[str, Gtk.Label] = {}
```

with

```python
        self.session = session
        self.outputs = {o.name: o for o in outputs}
        self.form = config_form(registry_widgets())
        self.rows: list[FieldRow] = []
        self.previews: dict[str, Gtk.Label] = {}
```


- [ ] **Step 4: Run the tests to verify they pass**

Run: `scripts/py -m pytest -q tests/test_settings_form.py tests/test_settings_values.py tests/test_settings_fields.py tests/test_settings_panels.py tests/test_settings_view.py`
Expected: all pass.

- [ ] **Step 5: VERIFY and commit**

Run VERIFY. Expected: `2043 passed`, `All checks passed!`.

```bash
git add settings/form.py settings/values.py settings/fields.py settings/view.py tests/test_settings_form.py tests/test_settings_values.py tests/test_settings_fields.py tests/test_settings_panels.py
git commit -m "feat(settings): name and panel type rows, widget property rows from the widget's model" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

**Reviewer mutations:** the old widget's keys kept on a widget switch (`test_a_new_widget_drops_the_old_widgets_keys`); the panel type row shown for a one-kind widget (`test_panel_fields`, `test_the_panel_type_row_shows_only_for_a_widget_of_several_kinds`); float not disabled (`test_the_panel_type_row_shows_only_for_a_widget_of_several_kinds`); the config's colour-by-name rule applied to widget properties (`test_a_widget_with_properties_gets_a_widget_section`: a property called `text` must be a text row); the form or the registry accepting a type the other refuses (`test_the_registry_refuses_exactly_the_property_types_the_form_cannot_show`).

---

### Task 8: The panel list: titles by name, the Panel type row, the Widget frame

The GTK side of Task 7. A panel's expander title shows its name; a widget with properties gets a framed "Widget" block whose rows sit in the entry itself (same key path prefix); a widget of several kinds shows the Panel type row; a disabled choice (float) is greyed out in the combo and never sent; required rows have no reset button; renaming a panel or changing its type rebuilds the page and keeps the panel open.

**Files:**
- Modify: `settings/panels.py` (`panel_title`, `panel_section`, the Widget frame, docstrings), `settings/fields.py` (`ChoiceEditor` disabled choices, the reset rule), `settings/view.py` (`TITLE_KEYS`)
- Modify: `tests/test_settings_fields.py`, `tests/test_settings_panels.py`, `tests/test_settings_view.py`, `tests/test_settings_example.py`

**Interfaces:**
- Consumes: `ConfigForm.panel_for(kind, corner, kinds)`, `ConfigForm.widget_props(id)`, `FieldSpec.disabled` / `required`, `registry_widgets()` (Task 7); `registry.supported_kinds` (Task 3); `PanelRequest.name` (Task 3).
- Produces: `settings.panels.panel_title(index, req) -> str` (`"1. Dock: bottom, center"`, `"2. Summary: bottom-left, from bottom, 300x390"`); `panel_section(form, req) -> SectionSpec` (kinds from the registry); `ChoiceEditor(choices, emit, labels=(), disabled=())` with `.disabled` and `_grey_out(layout, cell, model, it, data=None)`; `settings.view.TITLE_KEYS == ("name", "widget", "panel", "edge", "align", "corner", "width", "height")`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_settings_example.py` replace

```python
    doc.set(("theme", "accent"), "#d3a68f")
    assert "# mint" in doc.text and 'accent = "#d3a68f"' in doc.text
```

with

```python
    doc.set(("theme", "accent"), "#d3a68f")
    assert "# mint" in doc.text and 'accent = "#d3a68f"' in doc.text


def test_the_real_widgets_make_a_form_and_the_clock_has_its_widget_rows():
    from settings.form import config_form, registry_widgets

    form = config_form(registry_widgets())
    widget = form.edge_panel.field("widget")
    assert widget.labels == ("Clock", "Dock", "Summary", "System bar")
    clock = form.widget_props("clock")
    assert [(f.key, f.kind) for f in clock.fields] == [
        ("format", "text"),
        ("font", "text"),
        ("font_size", "int"),
    ]
    assert (clock.field("font_size").minimum, clock.field("font_size").maximum) == (6, 96)
    assert clock.field("format").hint.startswith("HH mm ss")
    assert clock.field("font_size").hint.startswith("pt")  # the size is in points
    assert all(form.widget_props(w) is None for w in ("dock", "summary", "system_bar"))
```

In `tests/test_settings_fields.py` replace

```python
    row, changes, _ = row_for(FieldSpec("font", "Font", "text"), None)
    assert row.editor.widget.get_text() == "" and not row.editor.dirty() and changes == []
```

with

```python
    row, changes, _ = row_for(FieldSpec("font", "Font", "text"), None)
    assert row.editor.widget.get_text() == "" and not row.editor.dirty() and changes == []


def test_a_disabled_choice_is_greyed_out_and_never_sent():
    spec = FieldSpec(
        "panel",
        "Panel type",
        "enum",
        choices=("edge", "corner", "float"),
        labels=("Edge", "Corner", "Float (coming soon)"),
        disabled=("float",),
        required=True,
    )
    row, changes, _ = row_for(spec, "edge")
    combo = row.editor.widget
    model, (cell,) = combo.get_model(), combo.get_cells()
    sensitive = []
    for i in range(3):
        row.editor._grey_out(combo, cell, model, model.get_iter(i))
        sensitive.append(cell.get_property("sensitive"))
    assert sensitive == [True, True, False]
    combo.set_active_id("float")  # chosen anyway (the keyboard): not sent, edge comes back
    assert changes == [] and combo.get_active_id() == "edge"
    combo.set_active_id("corner")
    assert changes == [(("theme", "x"), "corner")]


def test_a_required_key_has_no_reset_button():
    row, _, _ = row_for(FORM.edge_panel.field("name"), "Dock", is_set=True)
    assert not row.reset.get_sensitive()
```

In `tests/test_settings_panels.py` replace

```python

from settings.document import UserDocument  # noqa: E402
from settings.form import WidgetChoice, config_form  # noqa: E402
from shell.registry import requests_for  # noqa: E402

FORM = config_form(tuple(WidgetChoice(w) for w in ("bar", "clock", "dock")))
```

with

```python

from settings.document import UserDocument  # noqa: E402
from settings.form import WidgetChoice, config_form, registry_widgets  # noqa: E402
from shell.panel_spec import CornerDefaults, PanelDefaults  # noqa: E402
from shell.registry import requests_for  # noqa: E402
from shell.widget import Widget, WidgetProps  # noqa: E402

FORM = config_form(tuple(WidgetChoice(w) for w in ("bar", "clock", "dock")))
```

In `tests/test_settings_panels.py` replace

```python
        "1. dock: bottom, center",
        "2. box: bottom-left, from bottom, 300x390",
        "3. box: top-right, from top, 300x390",
    ]
    dock, box, moved = sections
```

with

```python
        "1. dock: bottom, center",
        "2. box: bottom-left, from bottom, 300x390",
        "3. box 2: top-right, from top, 300x390",  # the name, not the widget
    ]
    dock, box, moved = sections
```

In `tests/test_settings_panels.py` replace

```python
    ed.widget_choice.emit("scroll-event", event)
    assert ed.widget_choice.get_active() == 0
```

with

```python
    ed.widget_choice.emit("scroll-event", event)
    assert ed.widget_choice.get_active() == 0


class TileProps(WidgetProps):
    size: int = 10


@pytest.fixture
def tile(corner_registry):
    """A widget for both kinds, with one property."""
    corner_registry.register_widget(
        "tile",
        title="Tile",
        props=TileProps,
        edge=PanelDefaults(edge="top", length=200, depth=50, label="tile"),
        corner=CornerDefaults(corner="top-right", width=240, height=200, label="tile"),
    )(type("Tile", (Widget,), {}))
    return corner_registry


def test_titles_use_the_panel_name_and_a_widget_frame_shows_its_properties(make_config, tile):
    entries = [
        {"panel": "edge", "name": "Bottom dock", "widget": "dock"},
        {"panel": "corner", "name": "My tile", "widget": "tile", "corner": "top-left"},
    ]
    config = make_config(monitors={"M": {"panels": entries}})
    made = []

    def make_rows(section, prefix):
        made.append((section, prefix))
        return Gtk.Box()

    form = config_form(registry_widgets())
    ed = panels.PanelEditor(form, "M", requests_for(config, "M"), make_rows, lambda *_a: None)
    assert [e.get_label() for e in ed.expanders] == [
        "1. Bottom dock: bottom, center",
        "2. My tile: top-left, from top, 240x200",
    ]
    (dock, p0), (tile_rows, p1), (widget, p2) = made
    assert "panel" not in [f.key for f in dock.fields]  # the dock has one kind
    kind = tile_rows.field("panel")  # the tile has two: the panel type row
    assert kind.choices == ("edge", "corner", "float") and kind.disabled == ("float",)
    assert (widget.label, [f.key for f in widget.fields]) == ("Widget", ["size"])
    assert p1 == p2 == ("monitors", "M", "panels", 1)  # widget keys sit in the entry itself
    frames = [w for w in walk(ed.expanders[1]) if isinstance(w, Gtk.Frame)]
    assert [f.get_label() for f in frames] == ["Widget"]
    assert not [w for w in walk(ed.expanders[0]) if isinstance(w, Gtk.Frame)]


def walk(widget):
    yield widget
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            yield from walk(child)
```

In `tests/test_settings_view.py` replace

```python

import os

import pytest

gi = pytest.importorskip("gi")
```

with

```python

import os
from typing import Annotated

import pytest
from pydantic import Field

gi = pytest.importorskip("gi")
```

In `tests/test_settings_view.py` replace

```python
from settings.view import SettingsView  # noqa: E402
from shell.outputs import Output  # noqa: E402

USER = """\
```

with

```python
from settings.view import SettingsView  # noqa: E402
from shell.outputs import Output  # noqa: E402
from shell.panel_spec import CornerDefaults, PanelDefaults  # noqa: E402
from shell.widget import Widget, WidgetProps  # noqa: E402

USER = """\
```

In `tests/test_settings_view.py` replace

```python
    assert not any(r.path == (*P0, "align") for r in view.rows)
    expander = panel_editor(view).expanders[0]
    assert expander.get_label() == "1. box: bottom-left, from bottom, 300x390"
    assert expander.get_expanded()

```

with

```python
    assert not any(r.path == (*P0, "align") for r in view.rows)
    expander = panel_editor(view).expanders[0]
    assert expander.get_label() == "1. dock: bottom-left, from bottom, 300x390"  # its name stays
    assert expander.get_expanded()

```

In `tests/test_settings_view.py` replace

```python
    old.flush()
    assert "Typed Font" not in path.read_text() and not view.session.history
```

with

```python
    old.flush()
    assert "Typed Font" not in path.read_text() and not view.session.history


TILE_USER = """\
[monitors.HDMI-A-1]
shell = "edge"

[[monitors.HDMI-A-1.panels]]
panel = "edge"
name = "Tile"
widget = "tile"
size = 12
"""


class TileProps(WidgetProps):
    size: Annotated[int, Field(ge=6, le=96)] = 10


@pytest.fixture
def tile_view(tmp_path, corner_registry):
    corner_registry.register_widget(
        "tile",
        title="Tile",
        props=TileProps,
        edge=PanelDefaults(edge="top", length=200, depth=50, label="tile"),
        corner=CornerDefaults(corner="top-right", width=240, height=200, label="tile"),
    )(type("Tile", (Widget,), {}))
    path = tmp_path / "config.toml"
    path.write_text(TILE_USER)
    return SettingsView(SettingsSession(path), [HDMI]), path


def test_renaming_a_panel_retitles_it_and_keeps_it_open(make):
    view, path = make()
    view._on_change((*P0, "name"), "Bottom dock")
    expander = panel_editor(view).expanders[0]
    assert expander.get_label() == "1. Bottom dock: bottom, center" and expander.get_expanded()
    assert 'name = "Bottom dock"' in path.read_text()


def test_a_name_used_twice_is_not_written(make):
    view, path = make()
    panel_editor(view).add("clock")  # a new panel named after the widget's title: "Clock"
    assert 'name = "Clock"' in path.read_text()
    name = ("monitors", "HDMI-A-1", "panels", 1, "name")
    view._on_change(name, "dock")
    assert "names must be unique: 'dock' is used by panels[0] and panels[1]" in (
        row(view, name).error.get_text()
    )
    assert path.read_text().count('name = "dock"') == 1


def test_a_widget_property_is_a_row_and_a_key_of_the_entry(tile_view):
    view, path = tile_view
    size = (*P0, "size")
    assert row(view, size).editor.widget.get_value() == 12
    view._on_change(size, 30)
    assert "size = 30" in path.read_text()
    view._on_change(size, 2)  # below the model's bound: refused under the row
    assert "greater than or equal to 6" in row(view, size).error.get_text()
    assert "size = 30" in path.read_text()


def test_switching_the_widget_drops_its_property_keys_in_one_write(tile_view):
    view, path = tile_view
    view._on_change((*P0, "widget"), "dock")
    text = path.read_text()
    assert 'widget = "dock"' in text and "size" not in text and 'name = "Tile"' in text
    assert len(view.session.history) == 1
    assert not any(r.path == (*P0, "size") for r in view.rows)  # the Widget rows went too


def test_the_panel_type_of_a_two_kind_widget_is_switched_in_one_write(tile_view):
    view, path = tile_view
    view._on_change((*P0, "panel"), "corner")
    assert 'panel = "corner"' in path.read_text() and len(view.session.history) == 1
    assert panel_editor(view).expanders[0].get_label() == "1. Tile: top-right, from top, 240x200"
    view._on_change((*P0, "panel"), "float")  # listed, greyed out; refused if it gets through
    assert "float panels are not implemented yet" in row(view, (*P0, "panel")).error.get_text()
```


- [ ] **Step 2: Run them to verify they fail**

Run: `scripts/py -m pytest -q tests/test_settings_example.py tests/test_settings_fields.py tests/test_settings_panels.py tests/test_settings_view.py`
Expected: `8 failed, 90 passed`: `test_a_disabled_choice_is_greyed_out_and_never_sent`, `test_a_required_key_has_no_reset_button`, `test_corner_panels_get_their_own_rows_title_and_edges`, `test_titles_use_the_panel_name_and_a_widget_frame_shows_its_properties`, `test_a_dock_turned_into_a_corner_widget_is_one_edit`, `test_renaming_a_panel_retitles_it_and_keeps_it_open`, `test_a_widget_property_is_a_row_and_a_key_of_the_entry`, `test_the_panel_type_of_a_two_kind_widget_is_switched_in_one_write`. (`test_a_name_used_twice_is_not_written` and `test_switching_the_widget_drops_its_property_keys_in_one_write` already pass on Task 7's logic; they pin it through the view.)

- [ ] **Step 3: Implement**

In `settings/fields.py` replace

```python

class ChoiceEditor(_Editor):
    def __init__(self, choices: tuple[str, ...], emit: Emit, labels: tuple[str, ...] = ()):
        self.widget = Gtk.ComboBoxText()
        for choice, label in zip(choices, labels or choices, strict=True):
            self.widget.append(choice, label)
        wheel_scrolls_the_page(self.widget)
        self.widget.connect("changed", self._on_changed, emit)

    @staticmethod
    def _on_changed(combo: Gtk.ComboBoxText, emit: Emit) -> None:
        if combo.get_active_id() is not None:
            emit(combo.get_active_id())

    def set(self, value: str) -> None:
        if not self.widget.set_active_id(value):
            self.widget.set_active(-1)  # not a choice: show none, never the previous one
```

with

```python

class ChoiceEditor(_Editor):
    """A combo box. `disabled` choices are listed greyed out and are never sent (float panels:
    "coming soon"); if one gets chosen anyway (the keyboard), the shown value comes back."""

    def __init__(
        self,
        choices: tuple[str, ...],
        emit: Emit,
        labels: tuple[str, ...] = (),
        disabled: tuple[str, ...] = (),
    ):
        self.widget = Gtk.ComboBoxText()
        self.disabled = disabled
        self._shown: str | None = None
        for choice, label in zip(choices, labels or choices, strict=True):
            self.widget.append(choice, label)
        if disabled:
            (cell,) = self.widget.get_cells()
            self.widget.set_cell_data_func(cell, self._grey_out)
        wheel_scrolls_the_page(self.widget)
        self.widget.connect("changed", self._on_changed, emit)

    def _grey_out(self, _layout, cell, model, it, _data=None) -> None:
        cell.set_property("sensitive", model[it][1] not in self.disabled)  # column 1: the id

    def _on_changed(self, combo: Gtk.ComboBoxText, emit: Emit) -> None:
        active = combo.get_active_id()
        if active in self.disabled:
            self.set(self._shown)
            return
        if active is not None:
            emit(active)

    def set(self, value: str) -> None:
        self._shown = value
        if not self.widget.set_active_id(value):
            self.widget.set_active(-1)  # not a choice: show none, never the previous one
```

In `settings/fields.py` replace

```python
        return BoolEditor(emit)
    if spec.kind in ("enum", "widget"):
        return ChoiceEditor(spec.choices, emit, spec.labels)
    if spec.kind == "fonts":
        return FontsEditor(emit)
```

with

```python
        return BoolEditor(emit)
    if spec.kind in ("enum", "widget"):
        return ChoiceEditor(spec.choices, emit, spec.labels, spec.disabled)
    if spec.kind == "fonts":
        return FontsEditor(emit)
```

In `settings/fields.py` replace

```python
        note = value.source if not self.spec.hint else f"{self.spec.hint} · {value.source}"
        self.source.set_text(note)
        self.reset.set_sensitive(value.is_set and self.spec.kind != "widget")

    def show_error(self, message: str | None) -> None:
```

with

```python
        note = value.source if not self.spec.hint else f"{self.spec.hint} · {value.source}"
        self.source.set_text(note)
        self.reset.set_sensitive(value.is_set and not self.spec.required)  # name, widget, panel

    def show_error(self, message: str | None) -> None:
```

In `settings/panels.py` replace

```python
"""GTK editor for one monitor's panel list: an expander per [[panels]] entry with its fields,
plus add, remove and reorder buttons. Edge and corner panels (spec 19) share the list; each
entry shows the rows of its widget's kind. Structural edits go through `on_edit` (the window
applies them with the session and rebuilds); field rows come from the window's `make_rows`."""

from __future__ import annotations
```

with

```python
"""GTK editor for one monitor's panel list: an expander per [[panels]] entry with its fields,
plus add, remove and reorder buttons. Edge and corner panels (spec 19) share the list; each
entry shows the rows of its kind, the panel type row when its widget can be shown in more than
one kind, and a "Widget" frame with the widget's own properties (panel/widget spec 3.7).
Structural edits go through `on_edit` (the window applies them with the session and rebuilds);
field rows come from the window's `make_rows`."""

from __future__ import annotations
```

In `settings/panels.py` replace

```python
from settings.values import new_panel_entry
from shell.panel_spec import CornerRequest, PanelRequest

Edit = Callable[[UserDocument], Any]
```

with

```python
from settings.values import new_panel_entry
from shell.panel_spec import CornerRequest, PanelRequest
from shell.registry import supported_kinds

Edit = Callable[[UserDocument], Any]
```

In `settings/panels.py` replace

```python

def panel_title(index: int, req: PanelRequest | CornerRequest) -> str:
    """'1. dock: bottom, center', or for a corner panel '2. widget_panel: bottom-left, from
    bottom, 300x390' (1-based, as the list reads)."""
    if isinstance(req, CornerRequest):
        where = f"{req.corner}, from {req.edge}, {req.width}x{req.height}"
        return f"{index + 1}. {req.widget}: {where}"
    return f"{index + 1}. {req.widget}: {req.edge}, {req.align}"


def panel_section(form: ConfigForm, req: PanelRequest | CornerRequest) -> SectionSpec:
    """The rows of one entry: its widget's kind; a corner panel's edge row offers only the two
    edges of the corner it is in."""
    corner = req.corner if isinstance(req, CornerRequest) else None
    return form.panel_for("edge" if corner is None else "corner", corner)


```

with

```python

def panel_title(index: int, req: PanelRequest | CornerRequest) -> str:
    """'1. Dock: bottom, center', or for a corner panel '2. Summary: bottom-left, from bottom,
    300x390': the entry's name (1-based, as the list reads)."""
    if isinstance(req, CornerRequest):
        where = f"{req.corner}, from {req.edge}, {req.width}x{req.height}"
        return f"{index + 1}. {req.name}: {where}"
    return f"{index + 1}. {req.name}: {req.edge}, {req.align}"


def panel_section(form: ConfigForm, req: PanelRequest | CornerRequest) -> SectionSpec:
    """The rows of one entry: its kind's; a corner panel's edge row offers only the two edges
    of the corner it is in; the panel type row only when the widget supports several kinds."""
    corner = req.corner if isinstance(req, CornerRequest) else None
    kind = "edge" if corner is None else "corner"
    return form.panel_for(kind, corner, supported_kinds(req.widget))


```

In `settings/panels.py` replace

```python
                buttons.pack_start(button, False, False, 0)
            body.pack_start(buttons, False, False, 0)
            rows = make_rows(panel_section(form, req), ("monitors", monitor, "panels", i))
            body.pack_start(rows, False, False, 0)
            expander.add(body)
            self.expanders.append(expander)
```

with

```python
                buttons.pack_start(button, False, False, 0)
            body.pack_start(buttons, False, False, 0)
            prefix = ("monitors", monitor, "panels", i)
            body.pack_start(make_rows(panel_section(form, req), prefix), False, False, 0)
            props = form.widget_props(req.widget)
            if props is not None:  # the widget's own keys: in the same entry (same prefix)
                frame = Gtk.Frame(label=props.label)
                inner = make_rows(props, prefix)
                inner.set_margin_start(8)
                inner.set_margin_end(8)
                inner.set_margin_bottom(8)
                frame.add(inner)
                body.pack_start(frame, False, False, 6)
            expander.add(body)
            self.expanders.append(expander)
```

In `settings/panels.py` replace

```python

    def add(self, widget: str | None) -> None:
        """A new entry with its kind, a name unique on this monitor and its widget, edge or
        corner kind alike (a corner widget's entry is {"panel": "corner", "name": "summary",
        "widget": "summary"}: its corner and size are the widget's)."""
        if widget:
            self._on_edit(
```

with

```python

    def add(self, widget: str | None) -> None:
        """A new entry with its widget's first kind, a name made from the widget's title that
        is unique on this monitor, and the widget (a summary block's entry is {"panel":
        "corner", "name": "Summary", "widget": "summary"}: its corner and size are the
        widget's)."""
        if widget:
            self._on_edit(
```

In `settings/view.py` replace

```python

Edit = Callable[[UserDocument], Any]
# shown in a panel's expander title (panel_title), or deciding its rows (widget: the kind;
# corner: the edge choices): a change rebuilds the page and keeps that panel open
TITLE_KEYS = ("widget", "edge", "align", "corner", "width", "height")


```

with

```python

Edit = Callable[[UserDocument], Any]
# shown in a panel's expander title (panel_title), or deciding its rows (widget: the kind
# and the Widget rows; panel: the kind's rows; corner: the edge choices): a change rebuilds
# the page and keeps that panel open
TITLE_KEYS = ("name", "widget", "panel", "edge", "align", "corner", "width", "height")


```


- [ ] **Step 4: Run the tests to verify they pass**

Run: `scripts/py -m pytest -q tests/test_settings_example.py tests/test_settings_fields.py tests/test_settings_panels.py tests/test_settings_view.py`
Expected: all pass.

- [ ] **Step 5: VERIFY and commit**

Run VERIFY. Expected: `2052 passed`, `All checks passed!`.

```bash
git add settings/panels.py settings/fields.py settings/view.py tests/test_settings_fields.py tests/test_settings_panels.py tests/test_settings_view.py tests/test_settings_example.py
git commit -m "feat(settings): panel titles by name, panel type row, widget frame, float greyed out" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

**Reviewer mutations:** a disabled choice sent anyway (`test_a_disabled_choice_is_greyed_out_and_never_sent`); titles by widget id (`test_titles_use_the_panel_name_and_a_widget_frame_shows_its_properties`); `name` missing from `TITLE_KEYS` (`test_renaming_a_panel_retitles_it_and_keeps_it_open`); no Widget frame (`test_titles_use_the_panel_name_and_a_widget_frame_shows_its_properties`).

---
### Task 9: Docs and the gate example

**Files:**
- Create: `examples/widget-props-test.toml` (the gate's config; `tests/test_examples.py` picks it up)
- Modify: `README.md` (Run, Features, Configure with a new "Panels" section, the examples, Settings window, Develop, Known limitations)
- Modify: `docs/superpowers/specs/2026-10-11-edge-shell-design.md` (sections 3, 6, 8, 19; new section 20)
- Modify: `docs/superpowers/specs/2026-10-14-panel-widget-model-design.md` (3.8 links the plan and section 20)

**Interfaces:**
- Consumes: everything above (documentation only, plus one example file).
- Produces: the README section "Panels" that the old-format message points to (`see the README, "Panels"`); main spec section 20 with the line `Gate results: see the plan's Tasks 10-11 (recorded below after the gate).` that Task 11 replaces.

- [ ] **Step 1: The gate example**

Create (or replace entirely) `examples/widget-props-test.toml`:

```toml
# Gate (panel/widget plan): panel names, widgets and the clock's properties, on HDMI-A-1
# only. DP-1 is listed as "plasma" so the settings window shows it; never change it.
#   cp examples/widget-props-test.toml /tmp/edge-widgets.toml
#   scripts/py main.py --config /tmp/edge-widgets.toml -v              (terminal 1: the shell)
#   scripts/py main.py --settings --config /tmp/edge-widgets.toml      (terminal 2: the window)
[monitors.HDMI-A-1]
shell = "edge"

[[monitors.HDMI-A-1.panels]]    # 0: the summary block in the bottom-left corner
panel = "corner"
name = "Summary"
widget = "summary"

[[monitors.HDMI-A-1.panels]]    # 1: dock, bottom centre
panel = "edge"
name = "Dock"
widget = "dock"

[[monitors.HDMI-A-1.panels]]    # 2: clock, top centre: weekday and seconds, 18 pt
panel = "edge"
name = "Clock"
widget = "clock"
length = "content"
format = "ddd HH:mm:ss"
font_size = 18

[[monitors.HDMI-A-1.panels]]    # 3: system bar, right edge
panel = "edge"
name = "System bar"
widget = "system_bar"

[monitors.DP-1]
shell = "plasma"     # holds the Plasma panel: leave it alone
```


Run: `scripts/py -m pytest -q tests/test_examples.py`
Expected: `12 passed` (one more example). Then `scripts/py -m shell.canvas.simulate --config examples/widget-props-test.toml --frames 2` prints four `panel N:` lines and no `layout:` line (nothing shrunk or hidden at 1920x1080).

- [ ] **Step 2: README and spec**

In `README.md` replace

```markdown
scripts/py main.py --config examples/corner-test.toml -v      # corner panels next to edge panels
```

with

```markdown
scripts/py main.py --config examples/corner-test.toml -v      # corner panels next to edge panels
scripts/py main.py --config examples/widget-props-test.toml -v  # panel names, clock properties
```

In `README.md` replace

```markdown
- Panels: `dock` (bottom), `clock` (top), `system_bar` (right).
- Corner panels: a rectangular panel in a screen corner, joined to both frame bands (`widget_panel`: time, date, CPU and RAM in the bottom-left corner).
```

with

```markdown
- Panels and widgets: a panel is the surface (`edge` or `corner`; `float` is reserved), a
  widget is what it shows: `dock` (bottom), `clock` (top; its format, font and font size are
  properties), `system_bar` (right), `summary` (a corner block: time, date, CPU and RAM).
  Every panel has a name, used in logs, notifications and the settings window.
- Corner panels: a rectangular panel in a screen corner, joined to both frame bands.
```

In `README.md` replace

````markdown
[[monitors.HDMI-A-1.panels]]
widget = "dock"           # dock | clock | system_bar
depth = 80                # edge, length, depth, state, align, offset, order override the defaults
```
````

with

````markdown
[[monitors.HDMI-A-1.panels]]
panel = "edge"            # edge | corner (float: not implemented yet)
name = "Dock"             # unique on this monitor
widget = "dock"           # dock | clock | system_bar | summary
depth = 80                # edge, length, depth, state, align, offset, order override the defaults
```

### Panels

Each `[[monitors.NAME.panels]]` entry starts with three required keys:

- `panel`: the panel type. `edge` panels sit on one screen edge, `corner` panels in a screen
  corner (see Corner panels). `float` is reserved for later and rejected ("float panels are not
  implemented yet").
- `name`: 1-40 characters, no control characters, no space (or other whitespace) at the
  start or end, unique on its monitor (case-sensitive). It names the panel in logs, notifications and the settings window; panels are still matched by
  their place in the list, so a rename rebuilds the panel.
- `widget`: what the panel shows: `dock`, `clock`, `system_bar` (edge panels) or `summary`
  (corner panels). A widget on a panel type it does not support is rejected
  (`clock cannot be shown in a corner panel (it supports: edge)`).

Every other key is either a key of the panel type (below) or a property of the widget, written
in the same table. The clock's properties:

```toml
[[monitors.HDMI-A-1.panels]]
panel = "edge"
name = "Clock"
widget = "clock"
format = "ddd HH:mm:ss"   # tokens: HH mm ss H h a ddd dd MMM MM yyyy; 'quoted text'
font = "JetBrains Mono"   # a font family (default: the theme's font)
font_size = 14            # points, 6-96 (default: the theme's size)
```

The format takes only the tokens listed: `HH` hour 00-23, `H` 0-23, `h` 1-12, `a` AM/PM, `mm`
minute, `ss` second, `dd` day, `ddd` weekday, `MM` month, `MMM` month name, `yyyy` year.
Text in single quotes is shown as written (`"HH 'h' mm"`), two single quotes (`''`) are one
quote, and a quote that is not closed is an error. Any other letter is an error naming its
position; digits, spaces, punctuation and `%` are shown as written (never through strftime).
Errors name the entry's index in brackets (`monitors.HDMI-A-1.panels[2].format: ...`). A key
the widget does not have (`format: unknown key for widget 'dock'`), a bad
value, a duplicate name or a missing `panel` is reported with its key path; the shell keeps
the previous layout and sends a "Config not applied" notification. A file in the old format
(entries with only `widget`) gets one line saying what to add. A panel whose widget fails to
build is left out (a "Panel not shown" notification names it); the monitor's other panels stay,
and it is tried again only when its `panel`, `widget`, `name` or a widget property changes.
Changing `panel`, `widget`, `name` or a widget property rebuilds that panel.
````

In `README.md` replace

```markdown
[[monitors.HDMI-A-1.panels]]
widget = "clock"
edge = "bottom"
align = "end"             # start | center (default) | end of the edge
```

with

```markdown
[[monitors.HDMI-A-1.panels]]
panel = "edge"
name = "Bottom clock"
widget = "clock"
edge = "bottom"
align = "end"             # start | center (default) | end of the edge
```

In `README.md` replace

```markdown
[[monitors.HDMI-A-1.panels]]
widget = "widget_panel"      # a corner widget (registered with CornerDefaults)
corner = "bottom-left"       # top-left | top-right | bottom-left | bottom-right
```

with

```markdown
[[monitors.HDMI-A-1.panels]]
panel = "corner"
name = "Summary"
widget = "summary"           # a widget registered with corner defaults
corner = "bottom-left"       # top-left | top-right | bottom-left | bottom-right
```

In `README.md` replace

```markdown
[[monitors.HDMI-A-1.panels]]
widget = "clock"
handle.shape = "chevron"     # auto | dots | bar | chevron | none
```

with

```markdown
[[monitors.HDMI-A-1.panels]]
panel = "edge"
name = "Clock"
widget = "clock"
handle.shape = "chevron"     # auto | dots | bar | chevron | none
```

In `README.md` replace

```markdown
- Corner panels (for example `widget_panel`) are in the same panel list, labelled
  "(corner panel)" in the add list. Their rows are corner, edge (only the corner's two edges),
  width and height instead of align, offset, length and depth. Switching a panel's widget
  between an edge and a corner widget removes the keys the new kind does not take in the same
  change; moving a corner panel to a corner without its edge removes that edge.
```

with

```markdown
- Each panel is listed by its name. The add list shows the widgets by their display names
  (Clock, Dock, Summary, System bar); a new panel gets the widget's first panel type
  and a name made from its display name that is free on that monitor (`Clock`, `Clock 2`).
  The rows start with Name, Widget and, for a widget that can be shown in more than one panel
  type, Panel type (float is listed and greyed out). A widget with properties gets a
  **Widget** frame with one row per property (the clock: Format, Font, Font size).
- Corner panels (for example `summary`) are in the same panel list. Their rows are corner,
  edge (only the corner's two edges), width and height instead of align, offset, length and
  depth. Switching a panel's widget, or its panel type, removes the keys the new kind or
  widget does not take in the same change (the name stays); moving a corner panel to a corner
  without its edge removes that edge. A name already used on the monitor is refused under the
  Name row.
```

In `README.md` replace

```markdown
shells over it. New widgets go in `widgets/` and register with `@register`; they never call
cairo or layer-shell directly.
```

with

```markdown
shells over it. New widgets go in `widgets/`: a `shell.widget.Widget` subclass (`build(props)`
returns its Gtk content, `destroy()` stops its timers) registered with
`@register_widget(id, title=..., props=..., edge=PanelDefaults(...), corner=CornerDefaults(...))`;
the property model (a `WidgetProps` subclass) gives the config keys and the settings window's
Widget rows. A property must be `str`, `int`, `bool`, a `Literal` of strings, or one of these
`| None` (the types the settings window has a row for): any other type, or a property named like
a panel key, is refused at import. Widgets never call cairo or layer-shell directly.
```

In `README.md` replace

```markdown
- Corner panels: one per corner; only corner widgets (`widget_panel`) can sit in a corner;
```

with

```markdown
- Corner panels: one per corner; only widgets registered for corners (`summary`) can sit in a corner;
```

In `README.md` replace

```markdown
- Corner panel watch items: the `widget_panel`'s first stats appear after about 1 s
```

with

```markdown
- Corner panel watch items: the `summary` block's first stats appear after about 1 s
```

In `README.md` replace

```markdown
- Moving a panel (a layout change on reload or a resolution change) rebuilds its window; there
```

with

```markdown
- Panel/widget model: float panels are reserved, not built; only the clock has properties so
  far; widget properties are limited to `str`, `int`, `bool` and string `Literal`s (no lists or
  floats yet); a renamed panel is rebuilt, not renamed in place.
- Moving a panel (a layout change on reload or a resolution change) rebuilds its window; there
```

In `docs/superpowers/specs/2026-10-11-edge-shell-design.md` replace

```markdown
| widget_panel | bottom-left corner | x = 0 | 300 (incl. left frame) | 380 | extended |
```

with

```markdown
| summary (was widget_panel) | bottom-left corner | x = 0 | 300 (incl. left frame) | 380 | extended |
```

In `docs/superpowers/specs/2026-10-11-edge-shell-design.md` replace

```markdown
**Corner panels (section 19, implemented).** The widget_panel is a rectangle
```

with

```markdown
**Corner panels (section 19, implemented).** The summary block (the `summary` widget, was `widget_panel`; section 20) is a rectangle
```

In `docs/superpowers/specs/2026-10-11-edge-shell-design.md` replace

```markdown
- **Known limitations.** The `widget_panel`'s first stats appear after
```

with

```markdown
- **Known limitations.** The summary block's (was `widget_panel`) first stats appear after
```

In `docs/superpowers/specs/2026-10-11-edge-shell-design.md` replace

```markdown
[[monitors.HDMI-A-1.panels]]
widget = "clock"
edge = "top"                  # omitted keys fall back to the widget's defaults
```

with

```markdown
[[monitors.HDMI-A-1.panels]]
panel = "edge"                # edge | corner | float (float: reserved, rejected)
name = "Clock"                # required, unique per monitor
widget = "clock"
format = "HH:mm"              # a widget property (section 20)
edge = "top"                  # omitted keys fall back to the widget's defaults
```

In `docs/superpowers/specs/2026-10-11-edge-shell-design.md` replace

````markdown
- **Widget registry.** A widget registers by name with default geometry and a `build_content()` method. The registry also feeds the settings UI's widget list. Adding a widget means adding a file under `widgets/`.

  ```python
  @register("clock")
  class ClockPanel(EdgePanel):
      defaults = PanelSpec(edge="top", length=168, depth=46, label="clock")
      def build_content(self): ...
  ```
````

with

````markdown
- **Widget registry.** A widget is a `Widget` class (`build(props)`, `destroy()`) registered with a display title, a property model and default geometry per panel kind; the panel classes (`EdgePanel`, `CornerPanel`) are never subclassed by widgets. The registry also feeds the settings UI's widget list and Widget rows. Adding a widget means adding a file under `widgets/` (section 20).

  ```python
  @register_widget("clock", title="Clock", props=ClockProps,
                   edge=PanelDefaults(edge="top", length=168, depth=46, label="clock"))
  class ClockWidget(Widget):
      def build(self, props: ClockProps): ...
      def destroy(self): ...
  ```
````

In `docs/superpowers/specs/2026-10-11-edge-shell-design.md` replace

```markdown
  | Panel `corner`, `edge`, `width` or `height` (corner panels) | Rebuild that panel, and any edge panel whose place changed (section 19) |
```

with

```markdown
  | Panel `corner`, `edge`, `width` or `height` (corner panels) | Rebuild that panel, and any edge panel whose place changed (section 19) |
  | Panel `panel`, `widget`, `name` or a widget property | Rebuild that panel (section 20) |
```

In `docs/superpowers/specs/2026-10-11-edge-shell-design.md` replace

```markdown
├── widgets/                  # clock, dock, system_bar, workspaces, widget_panel
```

with

```markdown
├── widgets/                  # clock, dock, system_bar, summary (workspaces later)
```

In `docs/superpowers/specs/2026-10-11-edge-shell-design.md` replace

```markdown
- **Config.** In `[[monitors.X.panels]]`; the kind comes from the widget (CornerDefaults);
  keys `corner`, `edge`, `width`, `height`; mixing kinds is rejected with the key path. Reload:
  `panel-state`, `panel-handle` in place; size or corner changes rebuild.
- **Content.** `widget_panel`: time, date, CPU, RAM.
```

with

```markdown
- **Config.** In `[[monitors.X.panels]]` with `panel = "corner"` (section 20; before it the
  kind came from the widget); keys `corner`, `edge`, `width`, `height`; mixing kinds is
  rejected with the key path. Reload: `panel-state`, `panel-handle` in place; size or corner
  changes rebuild.
- **Content.** `summary` (was `widget_panel`): time, date, CPU, RAM.
```

Append to `docs/superpowers/specs/2026-10-11-edge-shell-design.md`:

```markdown

## 20. Implemented: the panel/widget model

Spec: `docs/superpowers/specs/2026-10-14-panel-widget-model-design.md` (sections 3-5). Plan:
`docs/superpowers/plans/2026-10-14-panel-widget-model.md`.

- **Entries.** Every `[[monitors.X.panels]]` entry has `panel` (edge | corner | float; float is
  reserved and rejected), `name` (1-40 characters, no control characters, no leading or
  trailing whitespace, unique per monitor)
  and `widget`. Other keys are the panel kind's keys or the widget's properties, flat in the
  same table; `PanelConfig` collects the latter in `widget_props` and
  `registry.validate_widgets` checks them against the widget's model. No aliases, no migration
  tool: the old format fails with one line saying what to add.
- **Widgets.** `Widget` classes (`shell/widget.py`) with a `WidgetProps` model, registered with
  `register_widget(id, title=, props=, edge=PanelDefaults|None, corner=CornerDefaults|None)`;
  `request_for` picks the defaults by `cfg.panel`; requests carry `name` and the validated
  props. Built in: `dock`, `clock`, `system_bar` (edge) and `summary` (corner; was
  `widget_panel`). The clock's `format` uses a fixed token table (`services/clock_format.py`:
  HH mm ss H h a ddd dd MMM MM yyyy, plus 'quoted text'), never strftime on user text; `font`
  (checked like the theme fonts) and `font_size` (6-96 pt) go into a provider on the clock's
  label. A property type the settings window cannot show is refused at registration. Every
  panel error writes the index in brackets (`monitors.X.panels[0].name: ...`).
- **Shell.** `MonitorShell` builds `EdgePanel` or `CornerPanel` by kind with a new widget
  instance; a change of name or props rebuilds that panel; a widget that fails to build is
  logged and left out, and the app sends "Panel not shown" naming it; it is tried again only
  when its entry (kind, widget, name or props) changes.
- **Settings window.** Panel titles use `name`; the add list shows widget titles and writes
  `{panel, name, widget}` with a free name; a Panel type row for widgets of several kinds
  (float greyed out); a Widget frame generated from the widget's property model; switching
  widget or kind is one edit that drops the keys the new one does not take.

Gate results: see the plan's Tasks 10-11 (recorded below after the gate).
```

In `docs/superpowers/specs/2026-10-14-panel-widget-model-design.md` replace

```markdown
A single live gate: the converted examples run on HDMI-A-1
```

with

```markdown
Implemented by `docs/superpowers/plans/2026-10-14-panel-widget-model.md`; recorded in the main
spec, section 20. A single live gate: the converted examples run on HDMI-A-1
```


- [ ] **Step 3: VERIFY and commit**

Run VERIFY. Expected: `2053 passed`, `All checks passed!` (ruff skips the Markdown). Check that no old name is left in the README: `grep -n "widget_panel\|@register\b\|widget_kind" README.md` prints nothing (the main spec keeps `widget_panel` only in its history and in "(was `widget_panel`)" notes).

```bash
git add examples/widget-props-test.toml README.md docs/superpowers/specs/2026-10-11-edge-shell-design.md docs/superpowers/specs/2026-10-14-panel-widget-model-design.md
git commit -m "docs: panel/widget model in the README and the spec; gate example" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Gate (Phil, live on HDMI-A-1 only)

No code. The controller prepares the commands; **Phil runs them** (subagents never launch the shell or the window). **DP-1 is never touched**: its page in the window shows `plasma`; leave it, and never scroll over its rows.

**Prepare (Phil):**

```bash
cp examples/widget-props-test.toml /tmp/edge-widgets.toml
scripts/py main.py --config /tmp/edge-widgets.toml -v              # terminal 1: the shell
```

Keep terminal 1 visible: each save prints `config reloaded: N change(s): <kinds>`; with `-v` every built panel logs `building panel <i> '<name>' (<widget>) on HDMI-A-1`. Edit `/tmp/edge-widgets.toml` in any text editor (save after each change). Notifications appear through `notify-send`.

**Checklist** (Phil answers each with pass / what was seen):

1. **Start.** On HDMI-A-1: the frame, the summary block in the bottom-left corner (time, date, CPU, RAM), the dock at the bottom, the clock at the top showing the weekday and seconds (for example `Wed 14:05:07`, ticking every second, at 18 pt: a little larger than the old 20 px, which is 15 pt) and the system bar on the right. Terminal 1 shows exactly four `building panel` lines (each panel is built once: the clock's length is a fixed 320 px, not `content`) with the names `'Summary'`, `'Dock'`, `'Clock'`, `'System bar'`. DP-1 and its Plasma panel are unchanged. *On failure:* copy the first 30 lines of terminal 1; a missing panel with a "Panel not shown" notification means a widget failed to build (copy the traceback).
2. **A property by hand.** Change the clock's `format = "ddd HH:mm:ss"` to `format = "h:mm a"`: one `config reloaded: 1 change(s): panel-rebuild`, exactly one new `building panel 2 'Clock' (clock)` line (no other panel rebuilt), the clock shows for example `2:05 PM`. Then `format = "HH 'Uhr' mm"`: the clock shows for example `14 Uhr 05` (quoted text is shown as written). Then add `font = "JetBrains Mono"`: the clock's font changes (one rebuild); set `font_size = 30` (points): the text grows and still fits the clock's fixed 320 px length (the panel does not change size). Remove the `font` and `font_size` lines: the theme's font and the default size come back. *On failure:* copy the reload line and the `building panel` lines; note what the clock showed.
3. **A rename by hand.** Change the clock's `name = "Clock"` to `name = "Top clock"`: `panel-rebuild` of panel 2 only, the next `building panel 2 'Top clock' (clock)` line shows the new name. *On failure:* copy the lines.
4. **Errors keep the previous layout.** Make each change below, save, check that a "Config not applied" notification shows the quoted text (terminal 1 logs `config not applied (keeping the previous config)` with the same text) and that nothing on screen changed, then undo that change and save again (the next reload applies normally):
   a. the dock's `name = "Dock"` to `name = "Top clock"`: `monitors.HDMI-A-1.panels[2].name: names must be unique: 'Top clock' is used by panels[1] and panels[2]`;
   b. delete the dock's `panel = "edge"` line: `monitors.HDMI-A-1.panels[1].panel: missing; use "edge", "corner" or "float"` and the line `panel entries start with panel = "edge" | "corner" | "float", ...`;
   c. the dock's `panel = "edge"` to `panel = "float"`: `monitors.HDMI-A-1.panels[1].panel: float panels are not implemented yet`;
   d. the clock's `panel = "edge"` to `panel = "corner"`: `monitors.HDMI-A-1.panels[2].panel: clock cannot be shown in a corner panel (it supports: edge)`;
   e. the clock's `format` to `format = "%Y"`: `monitors.HDMI-A-1.panels[2].format: Value error, unknown token 'Y' at position 2; use HH, mm, ss, ..., or put text in single quotes`; then `format = "HH 'Uhr"`: `... unterminated quote at position 4; close it with ' (write '' for a quote)`;
   f. add `colour = "red"` to the dock: `monitors.HDMI-A-1.panels[1].colour: unknown key for widget 'dock'`;
   g. add `font_size = 200` to the clock: `monitors.HDMI-A-1.panels[2].font_size: Input should be less than or equal to 96`;
   h. change the dock's name to `name = "Dock "` (a trailing space): `monitors.HDMI-A-1.panels[1].name: Value error, must not start or end with whitespace (a space, a no-break space, ...)`.
   *On failure:* note which item applied (or crashed) and copy terminal 1's last lines.
5. **The settings window.** `cp /tmp/edge-widgets.toml /tmp/edge-widgets.at-open.toml`, then in terminal 2: `scripts/py main.py --settings --config /tmp/edge-widgets.toml`. The HDMI-A-1 page lists `1. Summary: bottom-left, from bottom, 300x390`, `2. Dock: bottom, center`, `3. Top clock: top, center`, `4. System bar: right, end`. Open entry 3: the rows start with Name (`Top clock`, reset button greyed out), Widget (`Clock`, reset button greyed out), then edge, align, ...; a **Widget** frame holds Format (`h:mm a`), Font and Font size with their hints (`HH mm ss H h a ...`, `a font family; reset: the theme's font`, `pt; reset: the theme's size`, the size row reading `pt · ...`). The add list shows `Clock`, `Dock`, `Summary`, `System bar`. *On failure:* note the rows or labels that differ (screenshot with `spectacle`).
6. **Add panels with free names.** Add `Clock`: entry `5. Clock: top, center` opens (the name `Clock` is free since item 3), a second clock appears at the top (`panel-add`). Add `Clock` again: `6. Clock 2: top, center`. Remove entry 6 (its clock disappears). *On failure:* note the names written (`grep -n 'name =' /tmp/edge-widgets.toml`).
7. **Widget properties from the window.** In entry 5's Widget frame: Format `HH:mm:ss` + Enter (the new clock shows seconds, `panel-rebuild`), Font size 30 with the arrows (one rebuild 0.4 s after the last click), Font `JetBrains Mono` + Enter; then the Font row's reset button: the theme's font returns and `grep -n font /tmp/edge-widgets.toml` shows no `font =` line for entry 5 (only `font_size`). Type Format `%Y` + Enter: a red "Not saved: ... unknown token 'Y' ..." under the Format row, the file keeps `HH:mm:ss`. *On failure:* copy the message or the grep output.
8. **Names in the window.** Set entry 5's Name to `Top clock` + Enter: a red "Not saved: ... names must be unique: 'Top clock' is used by panels[2] and panels[4]" under Name, nothing written. Set it to `Seconds` + Enter: the title becomes `5. Seconds: top, center` and the entry stays open; terminal 1 shows `building panel 4 'Seconds' (clock)`. *On failure:* note the title and the file's name line.
9. **Switching the widget.** Set entry 5's Widget to `Dock`: one reload (`panel-rebuild`), the entry shows the dock's rows and no Widget frame, and `grep -n -A8 'name = "Seconds"' /tmp/edge-widgets.toml` shows `widget = "dock"` and no `format` or `font_size`. Then set its Widget to `Summary`: the file shows `panel = "corner"` for it and no edge-only keys; its rows become corner, edge, width, height; the bottom-left corner is already taken by entry 1, so the window's preview shows "... the bottom-left corner already holds ...; not shown" and the shell sends "Panels adjusted". Remove entry 5. *On failure:* copy the grep output and the preview text.
10. **Revert all** (the window's top bar) → OK: the file goes back to how it was when the window opened (the Top clock keeps `h:mm a`: that hand edit came before the window opened; the panels added in items 6-9 are already gone), and `cmp /tmp/edge-widgets.toml /tmp/edge-widgets.at-open.toml` prints nothing. *On failure:* run `diff` instead of `cmp` and copy it.
11. **A hand edit while the window is open.** In the text editor change the dock's `name = "Dock"` to `name = "Bottom dock"` and save: the window shows the blue "changed outside" banner and the title `2. Bottom dock: bottom, center`; terminal 1 shows one `panel-rebuild` and `building panel 1 'Bottom dock' (dock)`. *On failure:* note which side missed it.
12. **The other examples.** Close the window, stop the shell (Ctrl+C), then run `scripts/py main.py --config examples/corner-test.toml -v` for a few seconds: two summary blocks (bottom-left, and top-right collapsed), dock, clock, system bar as at the corner plan's Gate B, with `building panel` lines naming `'Summary'`, `'Dock'`, `'Clock'`, `'System bar'`, `'Summary top-right'`. Ctrl+C. *On failure:* copy the log.
13. **DP-1.** Throughout, DP-1 kept its Plasma panel and no Edge Shell frame; the window's DP-1 page still shows `plasma`. *On failure:* stop everything; restore with `scripts/py main.py --restore-config --config /tmp/edge-widgets.toml` if the window wrote anything for DP-1, and report.

Not checked live (covered by tests): a widget whose build raises and is then not retried until its entry changes (`test_a_panel_that_fails_to_build_is_left_out_and_named`, `test_a_failed_panel_is_not_retried_by_a_relayout_only_by_an_entry_change`), a widget property type the window cannot show refused at import (`test_a_property_the_settings_window_cannot_show_is_refused`), the Panel type row and the greyed-out float (no built-in widget supports two panel types yet: `test_the_panel_type_of_a_two_kind_widget_is_switched_in_one_write`).

---

### Task 11: Record the gate results

**Files:**
- Modify: `docs/superpowers/specs/2026-10-11-edge-shell-design.md` (section 20), `docs/superpowers/specs/2026-10-14-panel-widget-model-design.md` (3.8); `README.md` only if a gate item changed behaviour.

- [ ] **Step 1: Write the results**

In the main spec, section 20, replace the line

```markdown
Gate results: see the plan's Tasks 10-11 (recorded below after the gate).
```

with a "**Results.**" paragraph: Gate (Phil, HDMI-A-1): for each of the 13 items, "passed" or what was seen and what was changed, quoting Phil's words where he gave them. In the panel/widget spec, append to section 3.8 one line: `Results (2026-10-14 or the gate's date): see the main spec, section 20.` If a gate item led to a fix, that fix is its own task with a test first (added to this plan as Task 10a, ...), done before this step.

- [ ] **Step 2: VERIFY and commit**

Run VERIFY. Expected: all tests pass; record the real total in the results (the gate adds none unless a fix task does), `All checks passed!`.

```bash
git add docs/superpowers/specs/2026-10-11-edge-shell-design.md docs/superpowers/specs/2026-10-14-panel-widget-model-design.md
git commit -m "docs: record the panel/widget model gate results" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Self-review

- **Spec coverage.** 3.1 entry keys: Tasks 1-2 (`panel`, `name`, `widget`, flat widget keys; missing `panel` message plus the once-per-file old-format line, Task 2). 3.2 validation: Tasks 1-3 (the bag, unknown widget, unsupported kind, kind keys reworded, widget keys against the model, duplicate names, float; collision at registration, Task 3). 3.3 kinds: `float` in the schema and rejected (Task 1), offered greyed out in the window (Tasks 7-8). 3.4 widgets: `Widget` with `build` / `destroy` (Tasks 3-4), `register_widget` with title / props / per-kind defaults (Task 3), `summary` (Tasks 2, 4), a fake widget for both kinds (`tile`, Tasks 3, 7, 8), the clock's three properties with the fixed token table and the font rule in generated CSS (Task 6). 3.5 registry and shell: `request_for` by `cfg.panel`, `widget_kind` removed, `widget_title` / `widget_props_model` / `supported_kinds` added, requests carry name and props (Task 3); `_new_panel` builds by kind with the widget instance (Task 4); reload kinds (Task 3's diff tests, Task 5's live rebuild); no `shell` change. 3.6: every example and test converted, a test loads every example (Task 2), the listed new tests (Tasks 1-8: missing panel, bad kind, float, duplicates, unsupported kind, unknown and bad widget keys, name rules, collision, per-kind defaults, both-kinds fake, clock tokens, font/size reach the label, destroy stops the timer, rebuild on name/prop change), README and spec 6/19 plus the link (Task 9). 3.7 settings: form by `panel` kind, `name` row, Widget section from the model, `panel_for` kept and `widget_props(widget_id)` added (Task 7); `panel_ops` for `panel` and `widget` (Tasks 2, 7); add list by title, `{panel, name, widget}` with a unique name from the title, kind selector for multi-kind widgets, titles by name (Tasks 2, 7, 8); hints and labels, float "coming soon" (Tasks 7-8); handle right-click, undo/redo, reset and the document editor unchanged (no task touches them; their tests still pass). 3.8 gate: Task 10. Section 4: errors name key paths and are never written by the window (Tasks 1-3, 7-8 tests), widget build failures log and skip the panel and notify by name (Task 5). Section 5: test-first per task, pure tests for models/registry/form/values, GTK tests on plain widgets, mutation lists per task.
- **Placeholders.** None: every code step carries the full file or the exact text to replace; the two one-off scripts are given in full; every test is written out.
- **Type consistency.** `WidgetProps` / `NO_PROPS` / `Widget` (Task 3) are what `PanelRequest.props`, `EdgePanel(widget=, props=)` (Task 4), `MonitorShell._contents` (Task 5), `ClockProps` (Task 6) and `WidgetChoice.props` (Task 7) use. `register_widget(id, *, title, props, edge, corner)` (Task 3) is the call in every widget (Tasks 3, 4, 6) and in `conftest.py`. `defaults(id, kind)` (Task 3) is what `settings.values` calls (Tasks 3, 7). `new_panel_entry(user, monitor, widget)` (Task 2) is what `PanelEditor.add` calls (Task 2) and what Task 7 renames by title. `ConfigForm.panel_for(kind, corner, kinds)` (Task 7) is what `panel_section` calls with `supported_kinds` (Task 8). `FieldSpec.disabled` / `required` (Task 7) feed `ChoiceEditor` and `FieldRow` (Task 8). `build_failures` (Task 5) is read by `EdgeShellApp._report_layout` (Task 5) and stubbed on `FakeShell`.
- **Review Focus.** Five classes listed; each line's tests are in the owning task's Step 1 (Tasks 2, 3, 5, 6, 7, 8).
- **Prototype.** Every task was applied in order to a scratch copy of this branch: the totals in the File Structure table are the measured ones, `ruff check` and `ruff format --check` were clean after each task, each task's Step 2 output is the measured red run, and every "replace" text and file in this plan was generated from that prototype and re-applied to the previous task's tree to check it reproduces the next one exactly (Task 2: the converter and the fix-up script reproduced the hand-converted tests byte for byte). The reviewer mutations listed per task were run against the finished prototype: all 44 (31 from the first draft, 13 for Phil's answers) turned their tests red. After Phil's answers every task was re-applied and re-measured the same way; the totals, red outputs and code blocks above are the revised ones.

## Resolved by Phil

The first draft's eight open questions; Phil answered "all as recommended" (2026-10-14). Each answer is built into the tasks above.

1. **Path style:** every panel error, the loader's included, writes the entry's index in brackets (`monitors.HDMI-A-1.panels[0].panel: missing; ...`): `shell.config.loader.key_path` (Task 2, decision 4). Layout warnings and log lines keep their dotted paths.
2. **Names:** a leading or trailing space (any whitespace) is rejected with "must not start or end with whitespace (a space, a no-break space, ...)", never trimmed silently (Task 1, decision 3).
3. **Clock format:** text in single quotes is literal (`HH 'Uhr' mm`), `''` is one quote, an unclosed quote is a validation error naming its position; literal text never reaches strftime (Task 6, decision 8).
4. **`font_size`:** points, 6-96, emitted as `pt`; the settings row's hint says "pt" (Task 6, decision 9).
5. **Add list:** stays sorted by the widget's title, without the "(corner panel)" suffix (Task 7, decision 10).
6. **A panel whose widget fails to build:** not tried again on every re-sync; skipped until its entry (`panel`, `widget`, `name` or a widget property) changes, and a reload that changes it retries (Task 5, decision 7).
7. **Titles and new panel names:** the summary widget's title is "Summary"; new panels are named `Summary`, `System bar`, `Dock`, `Clock` (numbered when taken) (Tasks 3-4, decision 12).
8. **Property types:** `register_widget` refuses, at import, a property whose type the settings window cannot show; the window shows `str`, `int`, `bool`, a `Literal` of strings, or one of these `| None` (no floats, lists, dicts, number literals, unions of two types or nested models). The ValueError names the widget, the property and its type (Task 3), and a test keeps the registry and the form in agreement (Task 7, decision 10).
