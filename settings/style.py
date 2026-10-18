"""The settings window's own stylesheet: one CssProvider at USER priority on the screen,
installed once (install_css). Every rule is scoped by a style class this window puts on its
own widgets, never a bare element selector, so nothing else on the screen changes. A higher
provider priority wins over the theme's rules whatever their specificity (GTK cascades by
priority first), so one rule per node holds in every state (:checked, :backdrop, :disabled,
:hover) of KDE's Breeze and of Adwaita alike.

The CSS text is plain data: it is tested without GTK; install_css imports GTK when it runs."""

from __future__ import annotations

from typing import Any

# The once-only info note must not depend on the theme: GTK's own infobar colours turn the
# text orange in a focused window and white in an unfocused one. A blue background with light
# text, with the :backdrop (unfocused) state spelled out, reads the same either way.
INFO_NOTE_CLASS = "info-note"
INFO_NOTE_CSS = """
infobar.info-note,
infobar.info-note > revealer > box,
infobar.info-note:backdrop,
infobar.info-note:backdrop > revealer > box {
    background-color: #2b5c8a;
    background-image: none;
}
infobar.info-note label,
infobar.info-note:backdrop label {
    color: #ffffff;
}
"""

# Toggles (Phil: thinner, with a round knob, not an oval). GTK 3.24 gives the knob (the
# `slider` node) half the switch's content width and its whole content height, so the knob is
# a circle exactly when the content box is twice as wide as it is high. GTK never makes the
# content smaller than 32 x 16 px (measured with Breeze and Adwaita, whatever the font size),
# so the knob is 16 px across, its 1 px border included. Every size is set here (the theme's
# borders would add to them); the theme keeps its colours. The switch is centred in its row (a
# row is about 30 px high: a stretched switch made the knob a tall oval). Outside: 38 x 22 px
# (Breeze's own switch is 52 x 24).
SWITCH_CLASS = "edge-switch"
KNOB_PX = 16  # the knob's diameter, border included
BORDER_PX = 1
TRACK_PADDING_PX = 2
SWITCH_CSS = f"""
switch.{SWITCH_CLASS} {{
    min-width: {2 * KNOB_PX}px;
    min-height: {KNOB_PX}px;
    padding: {TRACK_PADDING_PX}px;
    border-width: {BORDER_PX}px;
    margin: 0;
    border-radius: {KNOB_PX}px;
}}
switch.{SWITCH_CLASS} slider {{
    min-width: {KNOB_PX - 2 * BORDER_PX}px;
    min-height: {KNOB_PX - 2 * BORDER_PX}px;
    border-width: {BORDER_PX}px;
    margin: 0;
    padding: 0;
    border-radius: 50%;
}}
"""

# The tree's row buttons (Move up, Move down, Remove): the theme's button is 30 px square at
# the least (Breeze), so a smaller icon alone changes nothing; 27 px (25 inside a 1 px
# border) is about 10% smaller.
ROW_BUTTON_CLASS = "tree-row-button"
ROW_BUTTON_PX = 27
ROW_BUTTON_CSS = f"""
button.{ROW_BUTTON_CLASS} {{
    min-width: {ROW_BUTTON_PX - 2}px;
    min-height: {ROW_BUTTON_PX - 2}px;
    padding: 0;
    border-width: 1px;
    margin: 0;
}}
"""

STYLESHEET = INFO_NOTE_CSS + SWITCH_CSS + ROW_BUTTON_CSS
_provider: Any = None  # the installed Gtk.CssProvider (None: not installed yet)


def install_css():
    """Add STYLESHEET to the default screen at USER priority, once; later calls return the
    same provider. With no screen (no display) the provider is made but not added."""
    global _provider
    if _provider is None:
        import gi

        gi.require_version("Gtk", "3.0")
        gi.require_version("Gdk", "3.0")
        from gi.repository import Gdk, Gtk

        provider = Gtk.CssProvider()
        provider.load_from_data(STYLESHEET.encode())
        screen = Gdk.Screen.get_default()
        if screen is not None:
            Gtk.StyleContext.add_provider_for_screen(
                screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_USER
            )
        _provider = provider
    return _provider
