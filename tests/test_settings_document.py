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
    "edit, comment",
    [
        (lambda d: d.remove_panel("HDMI-A-1", 1), "# DP-1 holds the Plasma panel"),
        (lambda d: d.unset(("layout", "gap")), "# the test monitor"),
    ],
)
def test_an_edit_that_would_lose_a_comment_above_a_table_is_refused(edit, comment):
    """tomlkit keeps the comment lines above a header in the table before it: removing the
    last panel, or pruning [layout], would delete them with it (the comment census)."""
    doc = UserDocument(COMMENTED)
    with pytest.raises(DocumentError, match=f"losing the comment '{comment}'.*by hand"):
        edit(doc)
    assert doc.text == COMMENTED


def test_comments_inside_a_removed_entry_may_go():
    text = '[[monitors.X.panels]]\n# the dock\nwidget = "dock"\n'
    doc = UserDocument(text + '[[monitors.X.panels]]\nwidget = "clock"\n')
    doc.remove_panel("X", 0)
    assert "# the dock" not in doc.text


@pytest.mark.parametrize(
    "edit, before",
    [
        (lambda d: d.set(("theme", "thickness"), 12), "thickness = 12"),
        (lambda d: d.add_panel("HDMI-A-1", "bar"), "[[monitors.HDMI-A-1.panels]]"),
        (lambda d: d.move_panel("HDMI-A-1", 1, 0), "[[monitors.HDMI-A-1.panels]]"),
    ],
)
def test_a_comment_above_a_table_can_move_but_stays(edit, before):
    """Pinned as it is today (decision 2): a key or panel added at the end of the table before a
    commented header lands below the comment; the comment is kept, the edit is allowed."""
    doc = UserDocument(COMMENTED)
    edit(doc)
    comment = "# wide gaps on purpose" if "thickness" in before else "# DP-1 holds the Plasma panel"
    lines = doc.text.splitlines()
    assert lines[lines.index(comment) + 1] == before
