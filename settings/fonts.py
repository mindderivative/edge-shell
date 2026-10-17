"""The font lists of the settings window's font pickers (settings.fontpicker). Pure: the
installed families come in as plain names (from Pango there), so this is tested without GTK
and without depending on the fonts of the machine.

A picker lists, in order: the inherited value (a widget's font: "Theme font"; its value is
None, choosing it resets the key), a configured name that is not installed (kept and shown, so
that it is never dropped by opening the list), the desktop's own font ("Noto Sans (system
font)", Phil: the default should be the system font), the CSS generic families the shell keeps
unquoted, then every installed family, sorted without case."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from shell.config.models import check_font_name

GENERIC_FAMILIES = ("monospace", "sans-serif", "serif")  # shell.theme writes them unquoted
# Pango lists fontconfig's aliases as families ("Monospace", "Sans", "Serif", "System-ui");
# the generic names above stand for them
_ALIASES = frozenset(
    {"monospace", "sans", "sans-serif", "serif", "system-ui", "cursive", "fantasy", "emoji"}
)
SYSTEM_SUFFIX = " (system font)"
MISSING_SUFFIX = " (not installed)"

Entry = tuple[str | None, str]  # (the value written, the label shown)


def font_families(names: Iterable[str]) -> tuple[str, ...]:
    """Installed family names as a picker lists them: stripped, without the aliases, without
    a name the config could not hold (check_font_name: it goes into CSS), one per name
    regardless of case, sorted without case."""
    kept: dict[str, str] = {}
    for raw in names:
        name = raw.strip()
        key = name.casefold()
        if not name or key in _ALIASES or key in kept:
            continue
        try:
            check_font_name(name)
        except ValueError:
            continue
        kept[key] = name
    return tuple(sorted(kept.values(), key=lambda n: (n.casefold(), n)))


def picker_entries(
    families: Sequence[str],
    system: str,
    current: str | None,
    inherit_label: str | None = None,
) -> tuple[Entry, ...]:
    """The rows of a picker, in order (see the module text). `families`: font_families();
    `system`: the desktop font's family ("" when unknown); `current`: the value shown;
    `inherit_label`: the label of the inherited value's row (None: no such row)."""
    entries: list[Entry] = []
    if inherit_label is not None:
        entries.append((None, inherit_label))
    known = {f.casefold() for f in (*families, *GENERIC_FAMILIES)}
    if current is not None and current.casefold() not in known:
        entries.append((current, current + MISSING_SUFFIX))
    if system:
        entries.append((system, system + SYSTEM_SUFFIX))
    entries += [(g, g) for g in GENERIC_FAMILIES]
    entries += [(f, f) for f in families if f.casefold() != system.casefold()]
    return tuple(entries)


def matches(label: str, text: str) -> bool:
    """A row is shown when its label holds the typed text, ignoring case and the spaces
    around it ("mono" finds "Hack Nerd Font Mono" and "monospace")."""
    return text.strip().casefold() in label.casefold()


def first_match(entries: Sequence[Entry], text: str) -> Entry | None:
    """The row Enter picks: the first one shown for `text`."""
    return next((e for e in entries if matches(e[1], text)), None)
