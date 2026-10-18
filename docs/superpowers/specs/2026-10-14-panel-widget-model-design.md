# Panel/widget model and the settings window redesign: design

Date: 2026-10-14. Status: approved by Phil in chat (design page, 2026-10-14); this file is the written spec for review.
Builds on: `2026-10-11-edge-shell-design.md` (sections 5.3, 6, 13, 15-19) and the merged-to-be settings window (PR 7, `feat/settings-window`).

## 1. Goal

Make Edge Shell's config say what each part is: a **panel** is the framework surface (edge, corner, later float), a **widget** is what a panel shows (clock, dock, system bar, summary block). Give every panel a name. Let a widget declare its own properties in Python, so the settings window shows them without per-widget UI code. Then redesign the settings window as a conventional desktop application on top of that model.

Who it is for: Phil now, other people who use the shell later. Success: a config reads like the settings window looks (`panel`, `name`, `widget`, widget properties); adding a widget does not need a new panel class or new settings code; the window has menus, a per-screen toolbar, a tree and tabbed pages.

## 2. Scope and order

Four plans, each with its own reviewed tasks, mutation-checked tests and a live gate on HDMI-A-1 (DP-1 is never touched):

1. **Panel/widget model** (this spec in full detail, section 3-5).
2. **Menus and file operations** (section 6).
3. **Toolbar, tree and tabbed pages** (section 7).
4. **Input styles** (section 8).

Out of scope here, planned later: float panels (section 3.3 reserves the name), more widget properties, a Plasma-panel hide/show spike, width/height and scrolling for every panel kind (memory: `future-panel-sizing-and-scrolling`). The work starts on `feat/panel-widget-model`, stacked on `feat/settings-window` until PR 7 merges, then rebased onto `main`.

## 3. Plan 1: the config model

### 3.1 A panel entry

```toml
[[monitors.HDMI-A-1.panels]]
panel = "edge"            # edge | corner | float   (required)
name = "Clock"            # required, unique per monitor
widget = "clock"          # a registered widget id (required)
edge = "top"              # panel-kind keys, validated by the kind
align = "center"
format = "HH:mm"          # widget keys, validated by the widget's own model
font = "Hack Nerd Font Mono"
font_size = 12
```

- `panel` is required. A file without it fails with `monitors.X.panels[i].panel: missing; use "edge", "corner" or "float"` (and names the old format in the message once per file). There are no aliases and no migration tool: Phil has no saved configs, and the examples and tests are rewritten.
- `name` is required, 1-40 characters, no control characters, no leading or trailing whitespace (rejected with a message, never trimmed silently), unique per monitor (case-sensitive). It is the panel's label in logs, notifications, the settings tree and tab bar. It is not an identity: panels are still tracked by list index, as today.
- `widget` must be a registered widget id that has defaults for the chosen `panel` kind (3.4).
- Keys fall in three groups. **Shared** (`panel`, `name`, `widget`, `edge`, `state`, `handle`, `interaction`) apply to every kind. **Kind keys**: edge panels take `pos` (deprecated, unchanged), `align`, `offset`, `order`, `length`, `min_length`, `max_length`, `depth`; corner panels take `corner`, `width`, `height` (`edge` is the edge it opens from). Mixing the two kinds' keys is rejected as today. **Widget keys** are everything else, validated against the widget's property model.

### 3.2 Validation

`PanelConfig` keeps `extra="forbid"` for the framework keys and accepts unknown keys into a separate bag (`model_config` extra allow, collected in a `widget_props: dict` field by a before-validator that moves every key not in the framework set). `shell.registry.validate_widgets` then checks, per entry, with key paths in `monitors.X.panels[i].<key>` form:

- unknown widget id; widget has no defaults for this `panel` kind (`clock cannot be shown in a corner panel (it supports: edge)`);
- kind keys that do not belong to the kind (existing messages, reworded for `panel`);
- widget keys against the widget model (`format: unknown key for widget 'dock'` or the pydantic error text for a bad value);
- duplicate `name` on one monitor (`names must be unique: 'Clock' is used by panels[0] and panels[3]`);
- `panel = "float"`: `float panels are not implemented yet`.

Every panel error, the loader's included (`monitors.X.panels[0].panel: missing; ...`), writes the entry's index in brackets; layout warnings and log lines keep their dotted paths. Widget property names must not collide with framework keys, and every property must have a type the settings window can show (`str`, `int`, `bool`, a `Literal` of strings, or one of these `| None`): both checked at registration (`ValueError` at import naming the widget and the property, like bad defaults today).

### 3.3 Panel kinds

| `panel` | Class | Status |
| --- | --- | --- |
| `edge` | `EdgePanel` | exists, unchanged behaviour |
| `corner` | `CornerPanel` | exists, unchanged behaviour |
| `float` | none | name reserved: the schema accepts the value so the settings window can list it as "coming soon", validation rejects it. Its intended behaviour (recorded for the later plan): a popup separate from the frame with width, height, rounded corners, border colour and thickness, shadow, no title bar, not draggable; opens animated from a button or icon (volume, calendar from the clock, hidden applications), respects the frame and other panels, collapses on click-away, unfocus or desktop click. |

### 3.4 Widgets

A widget is a class with a content builder and a property model, registered with display metadata and per-kind defaults:

```python
class ClockProps(WidgetProps):             # pydantic model, extra forbid, frozen
    format: str = "HH:mm"
    font: str | None = None                # None = the theme font
    font_size: Annotated[int, Field(ge=6, le=96)] | None = None   # points

@register_widget(
    "clock", title="Clock", props=ClockProps,
    edge=PanelDefaults(edge="top", length=168, depth=46, label="clock"),
)
class ClockWidget(Widget):
    def build(self, props: ClockProps) -> Gtk.Widget: ...
    def destroy(self) -> None: ...         # stop timers; called with the panel
```

- `Widget` replaces the `EdgePanel`/`CornerPanel` subclassing: the panel classes are no longer subclassed by widgets. `EdgePanel` and `CornerPanel` receive a widget instance and call `build` for their content (they keep `build_content` as the single seam, now delegating).
- A widget supports a panel kind by registering defaults for it (`edge=PanelDefaults(...)`, `corner=CornerDefaults(...)`); both may be given. Registered now: `dock` (edge), `clock` (edge), `system_bar` (edge), `summary` (corner; the old `widget_panel`, same content: time, date, CPU, RAM). A test registers a fake widget for both kinds to prove the path.
- `title` is the display name used in the settings window's widget list (`Dock`, `Clock`, `System bar`, `Summary`) and the default for a new panel's `name` (`Clock`, `Clock 2`, ...).
- The clock gets `format`, `font`, `font_size` to prove properties end to end (format uses strftime-style tokens translated from `HH:mm`-style: the spec fixes the accepted tokens to `HH`, `mm`, `ss`, `H`, `h`, `a`, `ddd`, `dd`, `MMM`, `MM`, `yyyy`; text in single quotes is literal (`'at'`), `''` is one quote, an unterminated quote is a validation error, and any other letter is a validation error; literal text never goes through strftime). `font_size` is in points (6-96), emitted as `pt`. Dock, system bar and summary have empty property models for now.
- Widget font properties are emitted in generated CSS under the existing font-name rule (`_FONT_FORBIDDEN`).

### 3.5 Registry, layout, shell

- `registry.request_for(cfg)` picks edge/corner defaults by `cfg.panel`, not by the widget. `widget_kind` is removed; `registry.widget_title`, `registry.widget_props_model`, `registry.supported_kinds(widget)` are added. Requests carry `name` and the validated widget props (a frozen mapping) so a change of either is a panel rebuild.
- `panel_layout` and the canvas are unchanged: they see requests/geometry as before.
- `MonitorShell._new_panel` builds the panel class for the request's kind with the widget instance; the widget gets its props.
- Reload kinds (`shell/config/diff.py`): a change of `panel`, `widget`, `name` or any widget property is `panel-rebuild` (a rename could be in place later; not now). Handle/state/interaction stay in place as today.
- Per-screen mode: **no config change**. `shell` keeps `edge | plasma | both | none`. Section 7 below maps the toolbar's two checkboxes to it. (`both` already means: Edge Shell windows built, Plasma untouched, the bottom edge must be free of Edge Shell panels; hiding Plasma's panel stays deferred.)

### 3.6 Examples, tests, docs

- All `examples/*.toml`, `config.default.toml` (no panels there) and every test that builds a panel config are converted to the new format. A test loads every example.
- New tests: missing `panel`, bad kind, float rejected, duplicate names, widget not supported on the kind, unknown widget key, bad widget value, name length/characters, widget property collision at registration, per-kind defaults selection, a both-kinds fake widget, clock format tokens, clock font/size reach the label, widget destroy stops its timer, panel-rebuild on name/prop change.
- README (config reference, examples) and spec section 6/19 updated; this file is linked from the main spec.

### 3.7 Settings window changes inside plan 1

The window keeps working on the new model; its layout is redesigned in plans 2-4.

- `settings/form.py`: panel sections by the entry's `panel` kind instead of `widget_kind`; shared rows gain `name`; a **widget section** generated from the widget's property model (same JSON-schema walk as the config models: bounds, enums, hints, labels). `ConfigForm.panel_for(kind, corner)` stays; `ConfigForm.widget_props(widget_id)` is added. **Tooltips (2026-10-17):** every settings field has a `Field(description=...)` in its model (config models and every widget's property model): one plain sentence, at most about 110 characters, what the property does and its unit. `FieldSpec.tooltip` carries it and `FieldRow` sets it on the label only (the editors, the note and the reset button keep their own tooltips). The note beside a widget property (`FieldSpec.hint`) is now `json_schema_extra={"hint": ...}`, no longer the description. Rule: every settings field has a description; `tests/test_settings_form.py` walks every row the form generates (all models, every registered widget) and fails for a field without one.
- `settings/values.py`: `panel_ops` handles `panel` and `widget` changes as compound edits (changing `widget` drops widget keys that the new widget does not have; changing `panel` drops the old kind's keys and a foreign edge, as today for corner changes).
- `settings/panels.py`: the add-panel combo lists widgets by display name (`registry.widget_title`), the new entry is `{panel, name, widget}` with `panel` = the widget's first supported kind and a unique `name` made from the title (`Clock`, `Clock 2`). A kind selector appears on the panel's rows when the widget supports more than one kind. Titles in the list use `name`.
- Hints and labels for the new keys; `float` is in the kind choice list, disabled ("coming soon").
- Right-click on a handle, undo/redo, reset and the document editor are unchanged.

### 3.8 Gate (Phil, HDMI-A-1)

Results (2026-10-14): passed; see the main spec, section 20.

Implemented by `docs/superpowers/plans/2026-10-14-panel-widget-model.md`; recorded in the main
spec, section 20. A single live gate: the converted examples run on HDMI-A-1 (edge and corner panels, names in logs); the clock's `format`, `font`, `font_size` apply live from the window and from a hand edit (`panel-rebuild`); duplicate name, missing `panel`, `float`, a widget on an unsupported kind and a bad widget value produce the notifications in section 3.2 and keep the previous layout; the window lists widgets by display name, adds a panel with a unique name, shows the Widget section for the clock, switches widget on a panel without leaving stale keys; DP-1 untouched. The checklist is written in the plan.

## 4. Data flow and error handling

Unchanged architecture: window → `UserDocument` (tomlkit) → file → shell watcher → `load_config` → `validate_widgets` → diff → in-place change or panel rebuild. Errors: any validation failure names the key path, is never written by the window, and in the shell keeps the previous layout and notifies. Widget `build` failures log and skip that panel (the panel is not shown; a notification names `name`), they do not take down the monitor. A failed panel is not tried again on every re-sync: only when its entry (`panel`, `widget`, `name` or a widget property) changes, so a reload that changes it retries.

## 5. Testing approach

Test-first per task; pure logic (models, registry, form, values) tested without GTK; GTK pieces with plain widgets and emitted signals (no toplevels); every fix mutation-checked on a scratch copy; independent reviews per task; whole-branch review; live gate by Phil.

## 6. Plan 2: menus and file operations

- **Menu bar** (Gtk.MenuBar with accelerators; application actions):
  - **File**: New (native `Gtk.FileChooserNative`, save mode, default folder `~/.config/edge-shell`; creates an empty file and opens it), Open (native, open mode), Save (Ctrl+S), Save As (native), Close (closes the open config; with changes since the last save, prompts Save / Discard / Cancel), Exit (same prompt, then quits the window).
  - **Edit**: Undo (Ctrl+Z, current behaviour), Redo (Ctrl+Shift+Z; new: `SettingsSession` keeps a redo stack cleared by any new edit), Cut / Copy / Paste (Ctrl+X/C/V on the focused `Gtk.Editable` or text view; insensitive elsewhere), Revert all (current behaviour and dialog).
  - **Help > About Edge Shell**: `Gtk.AboutDialog` (name, version from `pyproject`, licence, project URL, credits).
- **Saved point**: live apply and the atomic write stay. **Save** records the current file text as the saved point (and refreshes the session `.bak`). A **dirty** flag is "current text differs from the saved point". Close, Exit, New, Open and window close with a dirty config ask Save / Discard / Cancel; **Discard** writes the saved-point text back (the shell follows), exactly like Revert all but to the saved point. Opening or creating a config starts a fresh session (backup once, saved point = file text). Window title shows the path and `*` when dirty.
- The single-instance app id stays per config path; File > Open on another path opens that path in a second window (one window per file stays).
- No config open (after Close): the window shows an empty state with New / Open; the toolbar and tree are not shown (plan 3, decision 11: absent, not insensitive).

**Implemented (2026-10-15, `docs/superpowers/plans/2026-10-15-settings-menus.md`; the live gate results are recorded after it):** the menus as specified, with these readings (decisions in the plan): About is Help > About Edge Shell; New, Open and Save As open the chosen file in its own window and close this one (one window per file: a window never retargets its application id); Save As writes a copy, puts this file back to its saved point and opens the copy; New never replaces a file, adds `.toml` and writes one comment line; Cut, Copy and Paste act on the focused text field and their shortcuts stay the widget's own; a hand edit is the new saved point; Save also refreshes `config.toml.bak`; the native dialogs come through the desktop portal (`GTK_USE_PORTAL=1` in the settings process); a config other than the shell's own says so once; the licence is MIT (`LICENSE`, shown by About). The Undo and Revert all buttons stayed above the pages until plan 3 (section 7) moved them to the Edit menu.

Results (Phil, live on HDMI-A-1, 2026-10-15): all 15 gate items passed. Item 1 passed but the once-only "not the default config" note was not blue and its text was orange in a focused window and white in an unfocused one (GTK's theme infobar colours); fixed with a theme-independent style class (blue background, white text, with a `:backdrop` rule) installed once at USER priority. Item 15 (`GTK_USE_PORTAL=0` against the default): with `GTK_USE_PORTAL=0` the window looks very different (GTK's own dialogs and look); Phil prefers the default, so portal stays on and `os.environ.setdefault("GTK_USE_PORTAL", "1")` stays (`GTK_USE_PORTAL=0` still overrides it). Known limits: KDE's portal dialog may ask "overwrite?" for New on an existing name, after which the window refuses it (New never replaces a file); the Panel type row and the other panel-model items are unaffected.

## 7. Plan 3: toolbar, tree and tabbed pages

- **Toolbar** (per selected screen): the screen name; checkbox **Enable** (edge shell); checkbox labelled with the detected desktop (**KDE Plasma**, **Hyprland**, ...; from `XDG_CURRENT_DESKTOP`, first component, mapped through a small name table, fallback "Native desktop"); a **panel type** dropdown (display names, `float` disabled) with an **Add** button. Undo and Revert all leave the toolbar (Edit menu).
- **Mode mapping** onto the existing `shell` key: edge on + native off = `edge`; edge off + native on = `plasma`; both on = `both`; both off = `none`. The shell does not yet hide or show Plasma's panel (spec section 7, deferred), so `edge` and `both` behave the same at runtime today; the window shows a one-line note under the checkboxes ("Plasma's panel is not hidden or shown by Edge Shell yet; with both on, keep the bottom edge free of Edge Shell panels") and the checkbox pair writes exactly the four values.
- **Left tree** (minimum width 200 px): a button **Detect monitors** (re-runs `kscreen-doctor` and refreshes the list; connected monitors and monitors in the config); rows **Theme** and one expandable row per monitor whose children are its panels by `name`, each selectable; selecting a panel selects its page; the tree keeps its expansion across rebuilds.
- **Pages with tabs** (`Gtk.Notebook`): Theme: General, Borders, Shadows, Handle, Layout. Monitor: the same tabs, with a banner "These values override the Theme for HDMI-A-1" and the unset rows showing the inherited value as today. Panel: tabs tailored to the kind: **Panel** (name, widget, kind rows), **Position** (edge/align/offset/length or corner/edge/width/height), **Handle**, **Interaction**, and **Widget** (generated from the widget's property model; absent when the widget has none).
- Panel renaming is the `name` row; the tree and titles follow at once.

**Implemented (2026-10-15, `docs/superpowers/plans/2026-10-15-settings-tree.md`; the live gate results follow):** as specified, with these readings (decisions in the plan): the tree is a list box whose selected panel row shows Move up, Move down and Remove (Phil: on the tree and on the toolbar), with Left, Right, +, - and Delete (Delete removes only the panel row that has the keyboard focus); the theme keys are sorted onto tabs by what they relate to, and a new key lands on General; panel pages have Panel, Position, Handle, Interaction (state with click, hover, drag) and Widget, and replace the monitor page's former Panels tab; the panel type list names widget and kind ("Clock (edge panel)") and lists "Float panel (coming soon)" greyed out; the toolbar shows the screen of the page shown (a monitor's, or a panel's monitor), reads "No screen selected" and is insensitive on the Theme page, and holds the mode checkboxes (the shell row of the old monitor page is gone); the monitor page's override banner is always shown; Undo and Revert all are in the Edit menu only, and Ctrl+Z works with no field focused; every edit goes through one ordered queue (spin buttons wait 0.4 s on one shared timer; per setting the last edit wins; structural edits, Undo, Save, leaving the config and Detect monitors apply what is queued first; a hand edit drops what is queued and the banner names it); the shell warns once per change of unknown monitor names when the config names a monitor that is not connected and was never seen connected in that session (Phil, 2026-10-15), and Detect monitors says the same in the window with "(not connected)" rows. Known limits: no type-ahead search or context menu in the tree; Remove selects the monitor's row; a right-click on a handle opens the window but not that panel's page yet (follow-up). Widget discovery (a `widgets/<name>/<name>_widget.py` folder found by the shell) is a later plan; every widget list here comes from the registry.

**Results (Phil, live on HDMI-A-1 only, DP-1 untouched, 2026-10-16):** all 15 gate items passed ("Tree Gate all pass"): the per-screen toolbar and its mode checkboxes, the tree with its panel buttons and keys, tabbed Theme, monitor and panel pages, rename, the edit queue, Detect monitors, the shell's monitor-name warning and the narrow-window checks. No finding needed a change.

## 8. Plan 4: input styles

- **Toggles**: custom CSS-styled `Gtk.Switch` replacement (or restyled switch): thinner track, round knob (circle, not oval).
- **Sliders**: numeric fields whose schema has both `ge` and `le` become a `Gtk.Scale` with a value label and an editable entry for exact typing (px/length fields keep spin + unit); sliders keep the debounce and the wheel guard (a wheel never changes a slider unless it is focused and dragged; wheel scrolls the page).
- **Fonts**: a searchable dropdown (`Gtk.ComboBox` with entry completion, or a popover list with a search entry) over installed families (Pango font map, sorted, deduplicated); the unset state shows "System font" (resolved from `Gtk.Settings:gtk-font-name`) and writes nothing. The theme `font` list keeps its list editor with the same picker per entry.
- **Dropdown sizing**: investigate first (a spike task: reproduce under a plain Gtk3 combo on Wayland/KDE, check popup size request vs `set_wrap_width`/`popup-fixed-width`/CSS `min-height` on menu items, `Gtk.ComboBoxText` vs a `Gtk.MenuButton` + popover). Deliver the smallest fix that opens a combo at the size of its content on first show; if it is a GTK quirk with no clean fix, replace the choice editor with a popover list (also used by the font picker).

**Implemented (2026-10-16, `docs/superpowers/plans/2026-10-16-input-styles.md`; the live gate results follow):** with these readings (decisions in the plan):

- **Dropdowns** keep `Gtk.ComboBoxText` with `wrap_width` 1 (`fields.opens_below`). With wrap width 0 GTK 3.24 pops a combo's menu up over the combo with the active entry on it; on Wayland that puts the menu above its anchor, where the compositor shrinks it, and GtkMenu shows scroll arrows until a motion event. With a wrap width GTK anchors the menu below the combo (above when there is no room). The size request was never the cause (`popup-fixed-width` and a menu item's `min-height` change nothing on that path). The menu may be a little narrower than its combo. The popover list stays the fallback if a dropdown still opens short.
- **Toggles** are `Gtk.Switch` restyled by one class-scoped stylesheet (`settings/style.py`, USER priority, which also holds the info note's colours): 38 x 22 px, a 16 px round knob (GTK's own floor for the switch's content), centred in the row (a switch stretched to the row's height made the knob a tall oval).
- **Sliders**: an `int` with both bounds at most 500 apart (`SLIDER_MAX_SPAN`) is a 160 px `Gtk.Scale` and a spin button on one `Gtk.Adjustment`; the wider ranges (duration 0-5000 ms, offsets, order, depth, lengths, corner sizes) keep the spin button. A drag writes once, when the mouse button is released (through the edit queue; a drag that ends at the shown value writes nothing; keys and a click on the trough keep the 0.4 s pause); the wheel never edits.
- **Fonts**: a `Gtk.MenuButton` with a popover (a search entry above a list box, sized to its rows up to 360 px; a popover is drawn inside the window, not a compositor popup) over Pango's families (read once per process; aliases and CSS-unsafe names dropped; sorted without case). The list opens scrolled to the selected row once the list has its first allocation. Order: the desktop's font ("NAME (system font)", from `gtk-font-name`; `Sans`, `Sans-Serif` and `System-ui` become `sans-serif`), `monospace`, `sans-serif`, `serif`, then the families; a configured font that is not installed is listed "NAME (not installed)" and kept. The theme's `font` list is one picker per entry with Move up, Move down, Remove (greyed at one font) and Add font (adds the desktop's font; keyboard focus follows the moved or added font); the theme refuses empty names. A widget's `font` property (the clock) has a "Theme font" row that resets the key.
- **Deviation:** "the unset state shows System font and writes nothing" is not possible as written: an unset widget font is the theme's font, and the theme's `font` list is required and comes from `config.default.toml`. The desktop font is offered first and added by Add font instead (plan, open question 1); the shell does not follow the KDE font by itself.

**Results (Phil, live on HDMI-A-1, 2026-10-16):** all 13 gate items passed. Findings and what was done: slider updates now happen on mouse-button release, not while the pointer pauses (a slow mouse wrote too often; the number beside the slider still follows the drag, a keyboard change or a trough click keeps the pause, and Undo, Save or a structural edit during a drag apply the current value); Page Up and Page Down were inverted (GTK's binding for a horizontal slider) and now raise and lower the value; the tree's row buttons read Up, Down, Remove from left to right (Remove was first) and are 27 px instead of 30; item 12 (narrow window) is accepted as expected: at the narrowest width a horizontal scrollbar appears and the Reset buttons are reached by scrolling, at the default 860 px nothing scrolls sideways; the dropdown fix (`wrap_width` 1) is confirmed working live (item 1 passed).

## 9. Risks

- The widget/panel refactor touches every widget and the panel classes; the existing 1881 tests are the safety net, and plan 1's first task is the registry and widget base class with the old widgets ported one by one.
- `extra` keys for widget props weaken the single-model JSON schema; the settings form therefore reads widget models from the registry. Documented in the form module.
- Clock format tokens are a small custom grammar; kept to a fixed table (plus quoted literal text) to avoid strftime injection of `%` sequences.
- Gtk popup sizing may not have a clean fix on this GTK version (plan 4, spike first).

## 10. Decisions recorded from Phil (2026-10-14)

Save model: live apply plus a saved point. Mode checkboxes independent, written to the existing four-valued `shell`. Widget/panel split with new canonical ids and no aliases (`panel = edge | corner | float`, `name`, `widget`, widget properties in the same table). Float panels reserved, built later. No migration tool. One model plan plus three UI plans, each with its own gate. The settings branch (PR 7) is pushed first; this work is reviewed and pushed plan by plan after it.
