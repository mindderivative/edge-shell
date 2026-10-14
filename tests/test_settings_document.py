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


def test_adding_to_an_inline_panel_array_is_refused():
    text = '[monitors.X]\npanels = [{ widget = "dock" }]\n'
    doc = UserDocument(text)
    with pytest.raises(DocumentError, match="inline array.*by hand"):
        doc.add_panel("X", "clock")
    assert doc.text == text


COMMENTED = """\
[theme]
accent = "#8fd3b6"

# wide gaps on purpose
[layout]
gap = 4

# the test monitor
[monitors.HDMI-A-1]
shell = "edge"

[[monitors.HDMI-A-1.panels]]
widget = "dock"

[[monitors.HDMI-A-1.panels]]
widget = "clock"

# DP-1 holds the Plasma panel
[monitors.DP-1]
shell = "plasma"
"""


@pytest.mark.parametrize(
    "text, edit, comment",
    [
        (COMMENTED, lambda d: d.unset(("layout", "gap")), "# the test monitor"),
        (  # the end of the file counts like a header
            '[theme]\naccent = "#111111"\n\n[layout]\ngap = 4\n# vim: ft=toml\n',
            lambda d: d.unset(("layout", "gap")),
            "# vim: ft=toml",
        ),
    ],
)
def test_an_edit_that_would_lose_a_comment_above_a_table_is_refused(text, edit, comment):
    """tomlkit keeps the comment lines above a header (or at the end of the file) in the table
    before it: pruning [layout] would delete them with it (the comment census)."""
    doc = UserDocument(text)
    with pytest.raises(DocumentError, match=f"losing the comment '{comment}'.*by hand"):
        edit(doc)
    assert doc.text == text


def test_comments_inside_a_removed_entry_may_go():
    text = '[[monitors.X.panels]]\n# the dock\nwidget = "dock"\n'
    doc = UserDocument(text + '[[monitors.X.panels]]\nwidget = "clock"\n')
    doc.remove_panel("X", 0)
    assert "# the dock" not in doc.text


def test_a_comment_above_a_table_can_move_but_stays():
    """Pinned as it is today (decision 2): a key added at the end of the table before a
    commented header lands below the comment; the comment is kept, the edit is allowed."""
    doc = UserDocument(COMMENTED)
    doc.set(("theme", "thickness"), 12)
    lines = doc.text.splitlines()
    assert lines[lines.index("# wide gaps on purpose") + 1] == "thickness = 12"


@pytest.mark.parametrize(
    "edit",
    [
        lambda d: d.add_panel("HDMI-A-1", "bar"),
        lambda d: d.move_panel("HDMI-A-1", 1, 0),
        lambda d: d.remove_panel("HDMI-A-1", 1),
    ],
)
def test_a_panel_edit_keeps_the_comment_above_the_next_table_in_place(edit):
    """The comment above [monitors.DP-1] stays above it (it used to move above an added or moved
    panel, and removing the last panel was refused for it)."""
    doc = UserDocument(COMMENTED)
    edit(doc)
    lines = doc.text.splitlines()
    assert lines[lines.index("# DP-1 holds the Plasma panel") + 1] == "[monitors.DP-1]"


# ---- labels: whole-line comments directly above a [[panels]] header travel with the entry ----
LABELLED = """\
[monitors.HDMI-A-1]
shell = "edge"

# the dock
[[monitors.HDMI-A-1.panels]]
widget = "dock"

# the clock
[[monitors.HDMI-A-1.panels]]
widget = "clock"
handle.shape = "bar"

# the bar
[[monitors.HDMI-A-1.panels]]
widget = "system_bar"

# DP-1 holds the Plasma panel
[monitors.DP-1]
shell = "plasma"
"""


def labels(text):
    """{comment: what it labels}: the next header, plus the widget of a [[panels]] entry."""
    lines = [line.strip() for line in text.splitlines()]
    found = {}
    for i, line in enumerate(lines):
        if not line.startswith("#"):
            continue
        j = next((j for j in range(i + 1, len(lines)) if lines[j] and lines[j][0] != "#"), None)
        if j is None:
            found[line] = "end of file"
        elif lines[j].startswith("[["):
            found[line] = lines[j] + " " + lines[j + 1]
        else:
            found[line] = lines[j]
    return found


LABELS = {
    "# the dock": '[[monitors.HDMI-A-1.panels]] widget = "dock"',
    "# the clock": '[[monitors.HDMI-A-1.panels]] widget = "clock"',
    "# the bar": '[[monitors.HDMI-A-1.panels]] widget = "system_bar"',
    "# DP-1 holds the Plasma panel": "[monitors.DP-1]",
}


@pytest.mark.parametrize(
    "index, to, order",
    [
        (2, 0, ["system_bar", "dock", "clock"]),
        (0, 1, ["clock", "dock", "system_bar"]),
        (0, 2, ["clock", "system_bar", "dock"]),
        (1, 2, ["dock", "system_bar", "clock"]),
    ],
)
def test_a_moved_panel_takes_its_label_with_it(index, to, order):
    text, data = edited(lambda d: d.move_panel("HDMI-A-1", index, to), LABELLED)
    assert widgets(data) == order
    assert labels(text) == LABELS
    assert data["monitors"]["HDMI-A-1"]["panels"][order.index("clock")]["handle"] == {
        "shape": "bar"
    }
    assert data["monitors"]["DP-1"] == {"shell": "plasma"}
    assert "\n\n\n" not in text  # the blank lines stay where they were


@pytest.mark.parametrize("index", [0, 1, 2])
def test_a_removed_panel_takes_only_its_own_label(index):
    text, data = edited(lambda d: d.remove_panel("HDMI-A-1", index), LABELLED)
    gone = ["# the dock", "# the clock", "# the bar"][index]
    assert labels(text) == {k: v for k, v in LABELS.items() if k != gone}
    assert data["monitors"]["DP-1"] == {"shell": "plasma"}


def test_an_added_panel_goes_below_the_last_one_not_below_the_next_label():
    doc = UserDocument(LABELLED)
    assert doc.add_panel("HDMI-A-1", "clock") == 3
    assert labels(doc.text) == LABELS
    assert widgets(doc.data) == ["dock", "clock", "system_bar", "clock"]
    assert '[[monitors.HDMI-A-1.panels]]\nwidget = "clock"\n\n# DP-1' in doc.text


def test_the_first_panel_of_a_monitor_goes_below_its_tables_not_below_the_next_label():
    text = '[monitors.DP-1]\nshell = "plasma"\n\n# the test monitor\n[monitors.HDMI-A-1]\n'
    doc = UserDocument(text + 'shell = "edge"\n')
    doc.add_panel("DP-1", "dock")
    assert labels(doc.text) == {"# the test monitor": "[monitors.HDMI-A-1]"}
    assert doc.data["monitors"]["DP-1"] == {"shell": "plasma", "panels": [{"widget": "dock"}]}


def test_the_comment_at_the_end_of_the_file_stays_at_the_end():
    text = '[[monitors.X.panels]]\nwidget = "dock"\n\n[[monitors.X.panels]]\nwidget = "clock"\n'
    doc = UserDocument(text + "# vim: ft=toml\n")
    doc.move_panel("X", 1, 0)
    assert doc.text.endswith('widget = "dock"\n# vim: ft=toml\n')
    doc.remove_panel("X", 1)
    assert doc.text.endswith('widget = "clock"\n# vim: ft=toml\n')


# ---- removing the last panel of a monitor ----------------------------------------------------
@pytest.mark.parametrize(
    "text, expected",
    [
        ('[[monitors.X.panels]]\nwidget = "dock"\n', {}),
        (
            '[[monitors.X.panels]]\nwidget = "dock"\n\n[monitors.Y]\nshell = "edge"\n',
            {"monitors": {"Y": {"shell": "edge"}}},
        ),
        (
            '[monitors.Y]\nshell = "edge"\n\n[monitors.X]\n\n[[monitors.X.panels]]\nwidget = "a"\n',
            {"monitors": {"Y": {"shell": "edge"}}},
        ),
    ],
)
def test_removing_the_last_panel_of_a_monitor_with_only_panels_removes_the_monitor(text, expected):
    _, data = edited(lambda d: d.remove_panel("X", 0), text)
    assert data == expected


# ---- layouts that used to crash or be refused ------------------------------------------------
SPLIT = """\
[theme]
accent = "#8fd3b6"

[monitors.X]
shell = "edge"

[monitors.Y]
shell = "plasma"

[monitors.X.theme]
accent = "#111111"

[theme.shadow]
elevation = 3
"""


@pytest.mark.parametrize(
    "path, part, expected",
    [
        (
            ("theme", "handle_style", "shape"),
            "theme",
            {"accent": "#8fd3b6", "shadow": {"elevation": 3}, "handle_style": {"shape": "bar"}},
        ),
        (
            ("monitors", "X", "layout", "gap"),
            "X",
            {"shell": "edge", "theme": {"accent": "#111111"}, "layout": {"gap": "bar"}},
        ),
    ],
)
def test_a_table_split_across_the_file_takes_a_new_nested_key(path, part, expected):
    _, data = edited(lambda d: d.set(path, "bar"), SPLIT)
    got = data["theme"] if part == "theme" else data["monitors"]["X"]
    assert got == expected


@pytest.mark.parametrize(
    "text, edit",
    [
        ('[theme]\naccent = "#111111"\n', lambda d: d.set(("theme", "accent", "x"), 1)),
        ("[monitors.X]\npanels = 3\n", lambda d: d.add_panel("X", "dock")),
        ("[monitors.X]\npanels = 3\n", lambda d: d.move_panel("X", 0, 1)),
        ("[monitors.X.panels]\na = 1\n", lambda d: d.move_panel("X", 0, 1)),
        ("[monitors.X.panels]\na = 1\n", lambda d: d.remove_panel("X", 0)),
        ("[monitors.X.panels]\na = 1\n", lambda d: d.add_panel("X", "dock")),
        ('monitors = { X = { shell = "edge" } }\n', lambda d: d.add_panel("Y", "dock")),
        ('monitors = { X = { shell = "edge" } }\n', lambda d: d.set(("monitors", "Y", "a"), 1)),
    ],
)
def test_an_edit_through_a_scalar_or_an_inline_table_is_a_document_error(text, edit):
    doc = UserDocument(text)
    with pytest.raises(DocumentError):
        edit(doc)
    assert doc.text == text


def test_a_new_nested_key_under_an_inline_table_is_refused_clearly():
    text = 'theme = { accent = "#111111" }\n'
    doc = UserDocument(text)
    with pytest.raises(DocumentError, match="nested keys under the inline table 'theme'.*by hand"):
        doc.set(("theme", "shadow", "elevation"), 80)
    assert doc.text == text


def test_a_byte_order_mark_is_named():
    with pytest.raises(ConfigError, match=r"byte order mark \(BOM\); remove it"):
        UserDocument('﻿[theme]\naccent = "#111111"\n')


def test_valid_toml_that_tomlkit_cannot_read_is_named():
    text = "[[monitors.A.panels]]\n[[monitors.B.panels]]\n[monitors.A.panels.handle]\n"
    tomllib.loads(text)  # valid TOML
    with pytest.raises(DocumentError, match="cannot be edited in place.*valid TOML.*by hand"):
        UserDocument(text)


# ---- files without a trailing newline --------------------------------------------------------
NO_NEWLINE = '[[monitors.X.panels]]\nwidget = "dock"\n\n[[monitors.X.panels]]\nwidget = "clock"'


@pytest.mark.parametrize(
    "edit, order",
    [
        (lambda d: d.add_panel("X", "bar"), ["dock", "clock", "bar"]),
        (lambda d: d.move_panel("X", 1, 0), ["clock", "dock"]),
        (lambda d: d.move_panel("X", 0, 1), ["clock", "dock"]),
        (lambda d: d.remove_panel("X", 1), ["dock"]),
    ],
)
def test_a_file_without_a_trailing_newline(edit, order):
    text, data = edited(edit, NO_NEWLINE)
    assert widgets(data, "X") == order
    assert not text.endswith("\n")


def test_an_unedited_end_without_a_trailing_newline_stays_so():
    doc = UserDocument(NO_NEWLINE)
    doc.set(("monitors", "X", "panels", 0, "depth"), 3)
    assert doc.text.endswith('widget = "clock"')


# ---- the guard -------------------------------------------------------------------------------
def test_the_guard_with_real_tomlkit_never_keeps_a_misplaced_panel():
    """tomlkit writes a panel for a monitor known only from dotted keys as a top-level
    [[X.panels]] (the guard is what stops it): refused, or a correct result."""
    text = '[monitors]\nX.shell = "edge"\n'
    doc = UserDocument(text)
    try:
        doc.add_panel("X", "dock")
    except DocumentError:
        assert doc.text == text
    else:
        expected = {"monitors": {"X": {"shell": "edge", "panels": [{"widget": "dock"}]}}}
        assert tomllib.loads(doc.text) == expected


@pytest.mark.parametrize("wanted, written", [(True, 1), (1, 1.0), (1, True)])
def test_the_guard_compares_types(monkeypatch, wanted, written):
    import settings.document as document

    real = document._set
    monkeypatch.setattr(document, "_set", lambda doc, path, value: real(doc, path, written))
    doc = UserDocument(USER)
    with pytest.raises(DocumentError, match="changing other keys"):
        doc.set(("theme", "thickness"), wanted)
    assert doc.text == USER
