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
