"""settings.fonts: the font pickers' lists (pure: no GTK, no installed fonts)."""

from settings.fonts import (
    GENERIC_FAMILIES,
    first_match,
    font_families,
    matches,
    picker_entries,
)


def test_installed_families_are_cleaned_deduplicated_and_sorted_without_case():
    names = [
        "Noto Sans",
        "  JetBrains Mono ",
        "noto sans",  # the same family twice
        "Monospace",  # fontconfig's aliases: the generic names stand for them
        "Sans",
        "Serif",
        "System-ui",
        "",
        'Bad "Quote" Font',  # cannot go into CSS: check_font_name refuses it
        "Semi;colon",
        "abyssinica SIL",
    ]
    assert font_families(names) == ("abyssinica SIL", "JetBrains Mono", "Noto Sans")


def test_a_picker_lists_inherit_missing_system_generics_then_families():
    assert GENERIC_FAMILIES == ("monospace", "sans-serif", "serif")  # the order listed
    families = ("DejaVu Sans", "Hack Nerd Font", "JetBrains Mono")
    entries = picker_entries(families, "Hack Nerd Font", "Gone Font", "Theme font")
    assert entries == (
        (None, "Theme font"),
        ("Gone Font", "Gone Font (not installed)"),  # kept and shown, never dropped
        ("Hack Nerd Font", "Hack Nerd Font (system font)"),
        *((g, g) for g in GENERIC_FAMILIES),
        ("DejaVu Sans", "DejaVu Sans"),
        ("JetBrains Mono", "JetBrains Mono"),  # the system font is not listed twice
    )


def test_an_installed_or_generic_current_value_is_not_marked_missing():
    families = ("JetBrains Mono",)
    for current in ("JetBrains Mono", "jetbrains mono", "monospace", None):
        labels = [label for _v, label in picker_entries(families, "", current)]
        assert not any(label.endswith("(not installed)") for label in labels), current
    assert [v for v, _l in picker_entries(families, "", None)] == [
        *GENERIC_FAMILIES,
        "JetBrains Mono",
    ]  # no system font known, no inherited row


def test_typing_finds_any_part_of_a_name_without_case():
    assert matches("Hack Nerd Font Mono", "mono")
    assert matches("monospace", " MONO ")
    assert matches("Anything", "")
    assert not matches("Noto Sans", "mono")


def test_enter_picks_the_first_row_shown():
    entries = picker_entries(("Fira Mono", "Noto Sans"), "Noto Sans", None, "Theme font")
    assert first_match(entries, "mono") == ("monospace", "monospace")
    assert first_match(entries, "") == (None, "Theme font")
    assert first_match(entries, "zzz") is None


def labels(entries):
    return [label for _v, label in entries]


def test_the_system_font_is_filtered_and_mapped_like_the_installed_ones():
    families = ("Fira Mono", "Noto Sans")
    # GTK's default "Sans 10": the alias is the generic family, listed once, never "missing"
    for alias, generic in (("Sans", "sans-serif"), ("MONOSPACE", "monospace"), ("serif", "serif")):
        entries = picker_entries(families, alias, generic)
        assert entries[0] == (generic, generic + " (system font)"), alias
        assert [v for v, _l in entries].count(generic) == 1, alias
        assert not any(label.endswith("(not installed)") for label in labels(entries)), alias
    # a name the config could not hold, or two families in one name: no system row
    for bad in ('Bad"Font', "Cantarell,Noto Sans", "Semi;colon"):
        entries = picker_entries(families, bad, "Fira Mono")
        assert not any(label.endswith("(system font)") for label in labels(entries)), bad
        assert [v for v, _l in entries] == [*GENERIC_FAMILIES, *families], bad
    # the system name is known: a configured value naming it is never also "not installed"
    entries = picker_entries(families, "Cantarell", "cantarell")
    assert labels(entries) == ["Cantarell (system font)", *GENERIC_FAMILIES, *families]


def test_clean_system_family_maps_aliases_and_drops_what_the_config_refuses():
    from settings.fonts import system_font

    assert system_font(" Sans ") == "sans-serif"
    assert system_font("Noto Sans") == "Noto Sans"
    assert system_font('Bad"Font') == "" and system_font("A,B") == "" and system_font("") == ""
    assert system_font(system_font("Sans")) == "sans-serif"  # idempotent


def test_typing_searches_the_family_name_not_the_suffix():
    assert not matches("Noto Sans (system font)", "font")
    assert not matches("Gone (not installed)", "install")
    assert matches("Noto Sans (system font)", "noto")
    assert matches("Theme font", "font")
    assert matches("Hack Nerd Font", "font")
    entries = picker_entries(("Hack Nerd Font",), "Noto Sans", None)
    assert first_match(entries, "font") == ("Hack Nerd Font", "Hack Nerd Font")
