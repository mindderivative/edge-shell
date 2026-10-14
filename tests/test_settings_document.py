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
    assert doc.add_panel("HDMI-A-1", {"widget": "clock"}) == 3
    data = tomllib.loads(doc.text)
    assert widgets(data) == ["dock", "clock", "system_bar", "clock"]
    assert data["monitors"]["HDMI-A-1"]["panels"][3] == {"widget": "clock"}


def test_add_the_first_panel_of_a_monitor():
    doc = UserDocument(USER)
    assert doc.add_panel("DP-1", {"widget": "dock"}) == 0
    assert tomllib.loads(doc.text)["monitors"]["DP-1"] == {
        "shell": "plasma",
        "panels": [{"widget": "dock"}],
    }
    doc = UserDocument("")
    assert doc.add_panel("HDMI-A-1", {"widget": "dock"}) == 0
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


@pytest.mark.parametrize("index, to", [(5, 0), (0, 3), (0, 99), (0, -1), (2, -3)])
def test_move_panel_out_of_range_is_an_error(index, to):
    """`to` is a position in the list (0 to 2 here), not clamped like list.insert."""
    doc = UserDocument(USER)
    with pytest.raises(DocumentError):
        doc.move_panel("HDMI-A-1", index, to)
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
        doc.add_panel("X", {"widget": "clock"})
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
    "text, path, comment",
    [
        ("# t\n[theme]\na = 1\n\n# l\n[layout]\ngap = 1\n", ("theme",), "# l"),
        (  # a banner with a blank line under it counts too
            "[theme]\na = 1\n\n# ---- banner ----\n\n[layout]\ngap = 1\n",
            ("theme",),
            "# ---- banner ----",
        ),
        (  # the closing comment of the file counts like one above a header
            "[theme]\na = 1\n\n[layout]\ngap = 1\n# vim: ft=toml\n",
            ("layout",),
            "# vim: ft=toml",
        ),
        (
            "[theme]\na = 1\n\n[layout]\ngap = 1\n\n# vim: ft=toml\n",
            ("layout",),
            "# vim: ft=toml",
        ),
    ],
)
def test_an_edit_that_would_lose_a_comment_above_a_table_is_refused(text, path, comment):
    """tomlkit keeps the comment lines above a header in the table before it: removing that
    whole table would delete the next table's label with it (the comment census)."""
    doc = UserDocument(text)
    with pytest.raises(DocumentError, match=f"losing the comment '{comment}'.*by hand"):
        doc.unset(path)
    assert doc.text == text


# ---- resetting a table's only key ------------------------------------------------------------
@pytest.mark.parametrize(
    "text, path, expected",
    [
        (
            COMMENTED,
            ("layout", "gap"),
            COMMENTED.replace("# wide gaps on purpose\n[layout]\ngap = 4\n\n", ""),
        ),
        (  # the end of the file
            '[theme]\naccent = "#111111"\n\n# gaps\n[layout]\ngap = 4\n# vim: ft=toml\n',
            ("layout", "gap"),
            '[theme]\naccent = "#111111"\n\n# vim: ft=toml\n',
        ),
        (  # a monitor's theme override
            '[monitors.X]\nshell = "edge"\n\n# X theme\n[monitors.X.theme]\naccent = "#ffffff"\n'
            '\n# the Y screen\n[monitors.Y]\nshell = "edge"\n',
            ("monitors", "X", "theme", "accent"),
            '[monitors.X]\nshell = "edge"\n\n# the Y screen\n[monitors.Y]\nshell = "edge"\n',
        ),
        (  # a table known only from dotted keys under a [monitors] header
            '[theme]\naccent = "#111111"\n\n# all screens\n[monitors]\nX.theme.accent = 1\n# end\n',
            ("monitors", "X", "theme", "accent"),
            '[theme]\naccent = "#111111"\n\n# end\n',
        ),
        (  # a comment at the top of the file may be the file's head comment: it stays
            '# my config\n[layout]\ngap = 4\n\n# colours\n[theme]\naccent = "#111111"\n',
            ("layout", "gap"),
            '# my config\n\n# colours\n[theme]\naccent = "#111111"\n',
        ),
        (  # a panel entry's sub-table (found inside that entry, not the other one's)
            '[[monitors.X.panels]]\nwidget = "a"\n\n# a handle\n[monitors.X.panels.handle]\n'
            'shape = "pill"\n\n# b\n[[monitors.X.panels]]\nwidget = "b"\n\n# b handle\n'
            '[monitors.X.panels.handle]\nshape = "bar"\n\n# the Y screen\n[monitors.Y]\n'
            'shell = "edge"\n',
            ("monitors", "X", "panels", -1, "handle", "shape"),
            '[[monitors.X.panels]]\nwidget = "a"\n\n# a handle\n[monitors.X.panels.handle]\n'
            'shape = "pill"\n\n# b\n[[monitors.X.panels]]\nwidget = "b"\n\n# the Y screen\n'
            '[monitors.Y]\nshell = "edge"\n',
        ),
        (  # no label, at the top of the file: no leading blank line
            '[layout]\ngap = 4\n\n# colours\n[theme]\naccent = "#111111"\n',
            ("layout", "gap"),
            '# colours\n[theme]\naccent = "#111111"\n',
        ),
    ],
)
def test_resetting_a_tables_only_key_drops_its_header_and_own_label(text, path, expected):
    """The emptied table's header goes with its own label; the next table's label stays (this
    used to be refused for the next table's label, which tomlkit keeps in the emptied table)."""
    doc = UserDocument(text)
    doc.unset(path)
    assert doc.text == expected


def test_resetting_the_only_key_of_a_monitor_split_across_the_file_keeps_the_next_label():
    """[monitors.X] still holds the panels further down: its header stays (empty), and the
    label of the table after it is kept (tomlkit used to drop the emptied part with it)."""
    text = (
        '# lx\n[monitors.X]\nshell = "edge"\n\n# ly\n[monitors.Y]\nshell = "e"\n\n'
        '# xp\n[[monitors.X.panels]]\nwidget = "a"\n'
    )
    doc = UserDocument(text)
    doc.unset(("monitors", "X", "shell"))
    assert doc.text == text.replace('shell = "edge"\n', "")


def test_comments_inside_a_removed_entry_may_go():
    text = '[[monitors.X.panels]]\n# the dock\nwidget = "dock"\n'
    doc = UserDocument(text + '[[monitors.X.panels]]\nwidget = "clock"\n')
    doc.remove_panel("X", 0)
    assert "# the dock" not in doc.text


# ---- a new key goes below the table's last line, above the next table's label ---------------
@pytest.mark.parametrize(
    "text, path, value, expected",
    [
        (  # tomlkit wrote it below "# wide gaps on purpose", between the label and [layout]
            COMMENTED,
            ("theme", "thickness"),
            12,
            COMMENTED.replace('accent = "#8fd3b6"\n', 'accent = "#8fd3b6"\nthickness = 12\n'),
        ),
        (  # a sub-table, the next one labelled
            "[theme.border]\nwidth = 2\n\n# soft shadow\n[theme.shadow]\nelevation = 3\n",
            ("theme", "border", "color"),
            "#ffffff",
            '[theme.border]\nwidth = 2\ncolor = "#ffffff"\n\n# soft shadow\n[theme.shadow]\n'
            "elevation = 3\n",
        ),
        (  # a table split across the file: the new dotted key goes into its first part
            "[theme]\naccent = 1\n\n# layout\n[layout]\ngap = 4\n\n[theme.shadow]\nelevation = 3\n",
            ("theme", "border", "width"),
            2,
            "[theme]\naccent = 1\nborder.width = 2\n\n# layout\n[layout]\ngap = 4\n\n"
            "[theme.shadow]\nelevation = 3\n",
        ),
        (  # a banner and a label: both stay above the next header
            "[theme]\naccent = 1\n\n# ---- screens ----\n\n# the test monitor\n[monitors.X]\n"
            'shell = "edge"\n',
            ("theme", "thickness"),
            12,
            "[theme]\naccent = 1\nthickness = 12\n\n# ---- screens ----\n\n# the test monitor\n"
            '[monitors.X]\nshell = "edge"\n',
        ),
        (  # the closing comment stays the last line
            "[layout]\ngap = 4\n\n# vim: ft=toml\n",
            ("layout", "inner"),
            1,
            "[layout]\ngap = 4\ninner = 1\n\n# vim: ft=toml\n",
        ),
        (  # a new monitor table too
            "[layout]\ngap = 4\n\n# vim: ft=toml\n",
            ("monitors", "X", "shell"),
            "edge",
            '[layout]\ngap = 4\n\n[monitors.X]\nshell = "edge"\n\n# vim: ft=toml\n',
        ),
        (  # a [monitors] header tomlkit adds above the first monitor goes above its label
            '# my screens\n\n# the X screen\n[monitors.X]\nshell = "edge"\n',
            ("monitors", "radius"),
            12,
            "# my screens\n\n[monitors]\nradius = 12\n\n# the X screen\n[monitors.X]\n"
            'shell = "edge"\n',
        ),
    ],
)
def test_a_new_key_goes_above_the_next_tables_label(text, path, value, expected):
    """tomlkit adds a new key at the end of the table's body, below the comments there, so
    between the next table's label and its header; the label must stay directly above it."""
    assert edited(lambda d: d.set(path, value), text)[0] == expected


HAND = """\
[monitors.HDMI-A-1]
shell = "edge"

[[monitors.HDMI-A-1.panels]]    # 0: dock
widget = "dock"

[[monitors.HDMI-A-1.panels]]    # 1: clock
widget = "clock"

# DP-1 holds the Plasma panel
[monitors.DP-1]
shell = "plasma"
"""
_DOCK = '[[monitors.HDMI-A-1.panels]]    # 0: dock\nwidget = "dock"\n'
_CLOCK = '[[monitors.HDMI-A-1.panels]]    # 1: clock\nwidget = "clock"\nedge = "left"\n'
_DP1 = '# DP-1 holds the Plasma panel\n[monitors.DP-1]\nshell = "plasma"\n'
_TOP = '[monitors.HDMI-A-1]\nshell = "edge"\n\n'


@pytest.mark.parametrize(
    "edit, expected",
    [
        (lambda d: d.remove_panel("HDMI-A-1", 1), _TOP + _DOCK + "\n" + _DP1),
        (lambda d: d.move_panel("HDMI-A-1", 1, 0), _TOP + _CLOCK + "\n" + _DOCK + "\n" + _DP1),
        (
            lambda d: d.add_panel("HDMI-A-1", {"widget": "bar"}),
            _TOP
            + _DOCK
            + "\n"
            + _CLOCK
            + '\n[[monitors.HDMI-A-1.panels]]\nwidget = "bar"\n\n'
            + _DP1,
        ),
    ],
)
def test_a_key_set_on_the_last_panel_keeps_the_next_label_through_panel_edits(edit, expected):
    """A new key on the last entry used to sit between the DP-1 label and its header: the label
    then counted as the entry's body and went with a remove, a move or an add."""
    doc = UserDocument(HAND)
    doc.set(("monitors", "HDMI-A-1", "panels", 1, "edge"), "left")
    assert doc.text == HAND.replace('widget = "clock"\n', 'widget = "clock"\nedge = "left"\n')
    edit(doc)
    assert doc.text == expected


@pytest.mark.parametrize(
    "edit",
    [
        lambda d: d.add_panel("HDMI-A-1", {"widget": "bar"}),
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
    assert doc.add_panel("HDMI-A-1", {"widget": "clock"}) == 3
    assert labels(doc.text) == LABELS
    assert widgets(doc.data) == ["dock", "clock", "system_bar", "clock"]
    assert '[[monitors.HDMI-A-1.panels]]\nwidget = "clock"\n\n# DP-1' in doc.text


def test_the_first_panel_of_a_monitor_goes_below_its_tables_not_below_the_next_label():
    text = '[monitors.DP-1]\nshell = "plasma"\n\n# the test monitor\n[monitors.HDMI-A-1]\n'
    doc = UserDocument(text + 'shell = "edge"\n')
    doc.add_panel("DP-1", {"widget": "dock"})
    assert labels(doc.text) == {"# the test monitor": "[monitors.HDMI-A-1]"}
    assert doc.data["monitors"]["DP-1"] == {"shell": "plasma", "panels": [{"widget": "dock"}]}


# a comment block separated from a header by a blank line belongs to the place, not the entry
HEAD_COMMENT = """\
# edge-shell config, written by Phil
# see README

[[monitors.DP-1.panels]]
widget = "dock"

[[monitors.DP-1.panels]]
widget = "clock"
"""

BANNER = """\
[theme]
accent = "#ffffff"

# ---- DP-1: the left screen ----

# the dock
[[monitors.DP-1.panels]] # 0: dock
widget = "dock"

# the clock
[[monitors.DP-1.panels]] # 1: clock
widget = "clock"

# the bar
[[monitors.DP-1.panels]] # 2: bar
widget = "bar"
"""


def _entry(widget, label=None, note=""):
    return (f"# the {widget}\n" if label else "") + (
        f'[[monitors.DP-1.panels]]{note}\nwidget = "{widget}"\n'
    )


@pytest.mark.parametrize(
    "edit, expected",
    [
        (
            lambda d: d.remove_panel("DP-1", 0),
            "# edge-shell config, written by Phil\n# see README\n\n" + _entry("clock"),
        ),
        (
            lambda d: d.move_panel("DP-1", 0, 1),
            "# edge-shell config, written by Phil\n# see README\n\n"
            + _entry("clock")
            + "\n"
            + _entry("dock"),
        ),
        (lambda d: d.add_panel("DP-1", {"widget": "bar"}), HEAD_COMMENT + "\n" + _entry("bar")),
    ],
)
def test_the_comment_at_the_head_of_the_file_stays_there(edit, expected):
    text, _ = edited(edit, HEAD_COMMENT)
    assert text == expected


@pytest.mark.parametrize(
    "edit, expected",
    [
        (
            lambda d: d.remove_panel("DP-1", 0),
            BANNER.replace(
                '# the dock\n[[monitors.DP-1.panels]] # 0: dock\nwidget = "dock"\n\n', ""
            ),
        ),
        (
            lambda d: d.move_panel("DP-1", 0, 2),
            '[theme]\naccent = "#ffffff"\n\n# ---- DP-1: the left screen ----\n\n'
            + _entry("clock", True, " # 1: clock")
            + "\n"
            + _entry("bar", True, " # 2: bar")
            + "\n"
            + _entry("dock", True, " # 0: dock"),
        ),
        (lambda d: d.add_panel("DP-1", {"widget": "clock"}), BANNER + "\n" + _entry("clock")),
    ],
)
def test_a_banner_above_a_label_stays_in_place(edit, expected):
    text, _ = edited(edit, BANNER)
    assert text == expected


def test_the_comment_at_the_end_of_the_file_stays_at_the_end():
    text = '[[monitors.X.panels]]\nwidget = "dock"\n\n[[monitors.X.panels]]\nwidget = "clock"\n'
    doc = UserDocument(text + "# vim: ft=toml\n")
    doc.move_panel("X", 1, 0)
    assert doc.text.endswith('widget = "dock"\n# vim: ft=toml\n')
    doc.remove_panel("X", 1)  # the blank line above the removed entry is its place's: it stays
    assert doc.text.endswith('widget = "clock"\n\n# vim: ft=toml\n')


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


_THEME = "[theme]\naccent = 1\n\n"
_NEXT = '\n# the Y screen\n[monitors.Y]\nshell = "edge"\n'


@pytest.mark.parametrize(
    "text",
    [
        _THEME + '# the X screen\n[monitors.X]\n\n[[monitors.X.panels]]\nwidget = "a"\n' + _NEXT,
        _THEME + '# the X screen\n[monitors.X]\npanels = [{ widget = "a" }]\n' + _NEXT,  # inline
    ],
)
def test_an_emptied_monitor_goes_with_its_own_label_and_keeps_the_next_one(text):
    text, data = edited(lambda d: d.remove_panel("X", 0), text)
    assert data == {"theme": {"accent": 1}, "monitors": {"Y": {"shell": "edge"}}}
    assert text == _THEME + _NEXT[1:]


def test_an_emptied_inline_monitor_at_the_end_of_the_file_takes_its_label():
    text = '[monitors.Y]\nshell = "edge"\n\n# the X screen\n[monitors.X]\n'
    text += 'panels = [{ widget = "a" }]\n'
    text, _ = edited(lambda d: d.remove_panel("X", 0), text)
    assert text == '[monitors.Y]\nshell = "edge"\n'


@pytest.mark.parametrize(
    "text, edit, expected",
    [
        (  # the first entry at the top of the file: no leading blank line
            '[[monitors.X.panels]]\nwidget = "a"\n\n[[monitors.X.panels]]\nwidget = "b"\n',
            lambda d: d.remove_panel("X", 0),
            '[[monitors.X.panels]]\nwidget = "b"\n',
        ),
        (  # a monitor with only panels at the top of the file
            '# the dock\n[[monitors.X.panels]]\nwidget = "dock"\n\n# theme\n[theme]\naccent = 1\n',
            lambda d: d.remove_panel("X", 0),
            "# theme\n[theme]\naccent = 1\n",
        ),
        (  # a file of only comments: the entry goes below them
            "# my config\n# nothing yet\n",
            lambda d: d.add_panel("X", {"widget": "dock"}),
            '# my config\n# nothing yet\n\n[[monitors.X.panels]]\nwidget = "dock"\n',
        ),
        (  # the new entry copies the blank line above the last one, not the head comment
            '# my config\n\n[[monitors.X.panels]]\nwidget = "a"\n',
            lambda d: d.add_panel("X", {"widget": "b"}),
            '# my config\n\n[[monitors.X.panels]]\nwidget = "a"\n\n[[monitors.X.panels]]\n'
            'widget = "b"\n',
        ),
        (  # a spaced header is copied as written (tomlkit reads a file back only then)
            '[[ monitors.X.panels ]]\nwidget = "a"\n',
            lambda d: d.add_panel("X", {"widget": "b"}),
            '[[ monitors.X.panels ]]\nwidget = "a"\n[[ monitors.X.panels ]]\nwidget = "b"\n',
        ),
        (  # a comment directly under the last entry stays under it; the new one goes below
            '[[monitors.X.panels]]\nwidget = "a"\n# note\n\n[monitors.Y]\nshell = "e"\n',
            lambda d: d.add_panel("X", {"widget": "b"}),
            '[[monitors.X.panels]]\nwidget = "a"\n# note\n\n[[monitors.X.panels]]\n'
            'widget = "b"\n\n[monitors.Y]\nshell = "e"\n',
        ),
        (  # also at the end of the file
            '[monitors.X]\nshell = "e"\n\n[[monitors.X.panels]]\nwidget = "a"\n# note\n',
            lambda d: d.add_panel("X", {"widget": "b"}),
            '[monitors.X]\nshell = "e"\n\n[[monitors.X.panels]]\nwidget = "a"\n# note\n\n'
            '[[monitors.X.panels]]\nwidget = "b"\n',
        ),
        (  # no blank line after the last entry: none above the new one either
            '[monitors.X]\nshell = "e"\n\n[[monitors.X.panels]]\nwidget = "a"\n# Y\n'
            '[monitors.Y]\nshell = "e"\n',
            lambda d: d.add_panel("X", {"widget": "b"}),
            '[monitors.X]\nshell = "e"\n\n[[monitors.X.panels]]\nwidget = "a"\n'
            '[[monitors.X.panels]]\nwidget = "b"\n# Y\n[monitors.Y]\nshell = "e"\n',
        ),
        (  # two blank runs that meet keep the longer one, not three blank lines
            '[theme]\na = 1\n\n\n[[monitors.X.panels]]\nwidget = "a"\n\n\n[[monitors.X.panels]]\n'
            'widget = "b"\n',
            lambda d: d.remove_panel("X", 0),
            '[theme]\na = 1\n\n\n[[monitors.X.panels]]\nwidget = "b"\n',
        ),
    ],
)
def test_panel_edits_leave_a_tidy_file(text, edit, expected):
    assert edited(edit, text)[0] == expected


@pytest.mark.parametrize(
    "text, monitor",
    [
        (HAND, "HDMI-A-1"),
        (LABELLED, "HDMI-A-1"),
        (COMMENTED, "HDMI-A-1"),
        (BANNER, "DP-1"),
        (HEAD_COMMENT, "DP-1"),
    ],
)
def test_adding_then_removing_a_panel_restores_the_file(text, monitor):
    doc = UserDocument(text)
    doc.add_panel(monitor, {"widget": "bar"})
    doc.remove_panel(monitor, -1)
    assert doc.text == text


def test_adding_then_removing_a_panel_below_a_comment_restores_the_file():
    text = '[[monitors.X.panels]]\nwidget = "a"\n# note\n\n[monitors.Y]\nshell = "e"\n'
    doc = UserDocument(text)
    doc.add_panel("X", {"widget": "b"})
    doc.remove_panel("X", 1)
    assert doc.text == text


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
        ("[monitors.X]\npanels = 3\n", lambda d: d.add_panel("X", {"widget": "dock"})),
        ("[monitors.X]\npanels = 3\n", lambda d: d.move_panel("X", 0, 1)),
        ("[monitors.X.panels]\na = 1\n", lambda d: d.move_panel("X", 0, 1)),
        ("[monitors.X.panels]\na = 1\n", lambda d: d.remove_panel("X", 0)),
        ("[monitors.X.panels]\na = 1\n", lambda d: d.add_panel("X", {"widget": "dock"})),
        ('monitors = { X = { shell = "edge" } }\n', lambda d: d.add_panel("Y", {"widget": "dock"})),
        ('monitors = { X = { shell = "edge" } }\n', lambda d: d.set(("monitors", "Y", "a"), 1)),
    ],
)
def test_an_edit_through_a_scalar_or_an_inline_table_is_a_document_error(text, edit):
    doc = UserDocument(text)
    with pytest.raises(DocumentError):
        edit(doc)
    assert doc.text == text


WRITTEN_BY_HAND = "this edit cannot be written in place; edit the file by hand"
NESTED_ARRAY = (
    '[[monitors.X.panels]]\nwidget = "a"\ntags = [\n  ["x"]\n]\n\n'
    '[[monitors.X.panels]]\nwidget = "b"\n'
)


@pytest.mark.parametrize(
    "text, edit, message",
    [
        (
            'monitors = { X = { shell = "edge" } }\n',
            lambda d: d.add_panel("X", {"widget": "dock"}),
            WRITTEN_BY_HAND,
        ),
        (
            'monitors = { X = { shell = "edge" } }\n',
            lambda d: d.add_panel("Y", {"widget": "dock"}),
            WRITTEN_BY_HAND,
        ),
        (NESTED_ARRAY, lambda d: d.move_panel("X", 1, 0), WRITTEN_BY_HAND),
        (NESTED_ARRAY, lambda d: d.remove_panel("X", 0), WRITTEN_BY_HAND),
        (  # the result is valid TOML that tomlkit cannot read back (the next edit would fail)
            '[[monitors.X.panels]]\nwidget = "a"\n\n[extra]\nx = 1\n\n'
            '[[monitors."X".panels]]\nwidget = "b"\n',
            lambda d: d.unset(("extra", "x")),
            WRITTEN_BY_HAND,
        ),
        (  # the same, by removing the panel between two spellings of one monitor
            '[[monitors.X.panels]]\nwidget = "a"\n\n[[monitors.Y.panels]]\nwidget = "y"\n\n'
            '[[monitors."X".panels]]\nwidget = "b"\n',
            lambda d: d.remove_panel("Y", 0),
            WRITTEN_BY_HAND,
        ),
        (
            USER,
            lambda d: d.move_panel("HDMI-A-1", 0, 3),
            "cannot move the panel to position 3: monitors.HDMI-A-1 has 3 panels "
            "(positions 0 to 2)",
        ),
        (
            '[theme]\naccent = "#111111"\n',
            lambda d: d.set(("theme", "accent", "x"), 1),
            "theme.accent is a value, not a table: edit the file by hand",
        ),
        (
            "[monitors.X]\npanels = 3\n",
            lambda d: d.add_panel("X", {"widget": "dock"}),
            "monitors.X.panels is a value, not a table: edit the file by hand",
        ),
        (
            "[monitors.X]\npanels = 3\n",
            lambda d: d.remove_panel("X", 0),
            "monitors.X.panels is a value, not a table: edit the file by hand",
        ),
        (
            "[monitors.X]\npanels = 3\n",
            lambda d: d.move_panel("X", 0, 1),
            "monitors.X.panels is a value, not a table: edit the file by hand",
        ),
    ],
)
def test_refusals_say_what_to_do(text, edit, message):
    doc = UserDocument(text)
    with pytest.raises(DocumentError) as caught:
        edit(doc)
    assert str(caught.value) == message
    assert doc.text == text


# ---- CRLF ------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "edit",
    [
        lambda d: d.set(("layout", "gap"), 3),
        lambda d: d.set(("theme", "accent"), 2),
        lambda d: d.add_panel("X", {"widget": "dock"}),
    ],
)
def test_a_crlf_file_without_a_trailing_newline_stays_so(edit):
    text, _ = edited(edit, "[theme]\r\naccent = 1")
    assert not text.endswith("\n")


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
        (lambda d: d.add_panel("X", {"widget": "bar"}), ["dock", "clock", "bar"]),
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
        doc.add_panel("X", {"widget": "dock"})
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
