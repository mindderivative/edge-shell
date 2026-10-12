from shell.plan import desired_shells, reconcile


def test_only_connected_edge_monitors(make_config):  # Review Focus 2
    cfg = make_config(
        monitors={
            "HDMI-A-1": {"shell": "edge"},
            "DP-1": {"shell": "plasma"},
            "DP-3": {"shell": "edge"},  # configured but not connected
            "DP-4": {"shell": "both"},
        }
    )
    assert desired_shells(cfg, ["HDMI-A-1", "DP-1", "DP-4"]) == ["DP-4", "HDMI-A-1"]


def test_unlisted_connected_monitor_gets_nothing(make_config):
    assert desired_shells(make_config(), ["HDMI-A-1"]) == []


def test_reconcile_is_stable_when_only_gdk_order_changes():  # Review Focus 5
    a, b = object(), object()
    assert reconcile({"A": a, "B": b}, {"B": b, "A": a}) == ([], [])


def test_replugged_connector_is_rebuilt():
    old, new = object(), object()
    assert reconcile({"A": old}, {"A": new}) == (["A"], ["A"])


def test_removed_and_added():
    a, b = object(), object()
    assert reconcile({"A": a}, {"B": b}) == (["A"], ["B"])
    assert reconcile({}, {"B": b}) == ([], ["B"])
    assert reconcile({"A": a}, {}) == (["A"], [])
