# Finding: Gdk monitors do not expose connector names

Date: 2026-10-11 · Spike 1 (spec section 11)

**Question:** does `Gdk.Monitor.get_model()` return the connector name under GTK3 on KWin Wayland?

**Answer: no.** On this machine both monitors return the panel model, `G24M2020G`
(manufacturer `AMZ`), so it cannot tell them apart.

| Gdk index | model | geometry |
| --- | --- | --- |
| 0 | G24M2020G | 0,0 1920x1080 (= HDMI-A-1) |
| 1 | G24M2020G | 0,1080 1920x1080 (= DP-1) |

**Decision:** map Gdk monitors to connector names by geometry against
`kscreen-doctor -j`, which reports for each output `name`, `enabled`, `pos{x,y}`,
`size{width,height}` and `scale`. Logical size = `round(size / scale)`. Match on
position + logical size, falling back to position alone.
