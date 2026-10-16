"""settings.queue: the edit queue's order, coalescing and the text of dropped edits (pure)."""

from settings.queue import RESET, EditQueue, describe, path_text

A, B, C = ("theme", "a"), ("theme", "b"), ("monitors", "M", "panels", 0, "depth")


def order(queue):
    return [(e.path, e.value) for e in queue]


def test_edits_come_out_in_arrival_order():
    q = EditQueue()
    q.push(A, 1)
    q.push(B, 2)
    q.push(C, RESET)
    assert [q.pop().path for _ in range(3)] == [A, B, C]
    assert q.pop() is None and len(q) == 0


def test_a_new_edit_of_a_queued_path_replaces_it_and_moves_to_the_end():
    q = EditQueue()
    q.push(A, 1)
    q.push(B, 2)
    q.push(A, 3)
    assert order(q) == [(B, 2), (A, 3)] and len(q) == 2


def test_an_edit_back_to_the_shown_value_takes_the_path_out():
    q = EditQueue()
    q.push(A, 11, base=10)
    q.push(A, 12, base=11)  # the base stays the first one: 10
    q.push(A, 10, base=12)
    assert not q.pending(A) and len(q) == 0
    q.push(A, 10, base=10)  # a no-op is never queued
    assert len(q) == 0


def test_a_base_compares_type_and_value():
    q = EditQueue()
    q.push(A, 1, base=True)  # 1 == True in Python, but it is another value here
    assert q.pending(A)


def test_without_a_base_every_edit_is_queued():
    q = EditQueue()
    q.push(A, 10)
    q.push(A, 10)
    assert order(q) == [(A, 10)]


def test_drop_empties_the_queue_and_returns_what_it_held():
    q = EditQueue()
    q.push(A, 1)
    q.push(B, RESET)
    dropped = q.drop()
    assert [(e.path, e.value) for e in dropped] == [(A, 1), (B, RESET)] and len(q) == 0


def test_dropped_edits_are_named_with_their_paths():
    q = EditQueue()
    q.push(C, 120)
    q.push(A, RESET)
    q.push(B, "#112233")
    assert describe(q.drop()) == (
        "monitors.M.panels[0].depth = 120, theme.a (reset), theme.b = '#112233'"
    )
    assert path_text(("theme",)) == "theme"
