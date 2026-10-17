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
