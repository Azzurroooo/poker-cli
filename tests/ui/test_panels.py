from __future__ import annotations

from rpoker.domain.actions import Action, LegalActions
from rpoker.ui.panels import ActionPanel, action_items, auto_action, parse_action


def legal(to_call=0, can_check=True, min_raise=None, max_raise=None) -> LegalActions:
    return LegalActions(can_check, to_call, min_raise, max_raise)


def test_items_face_bet_with_raise() -> None:
    items = action_items(legal(to_call=40, can_check=False, min_raise=80, max_raise=1000))
    assert [(i.hotkey, i.kind) for i in items] == [("F", "fold"), ("C", "call"), ("R", "raise"), ("A", "allin")]


def test_items_free_check_no_raise() -> None:
    items = action_items(legal())
    assert [(i.hotkey, i.kind) for i in items] == [("C", "check")]


def test_items_free_check_with_raise() -> None:
    items = action_items(legal(min_raise=20, max_raise=1000))
    assert [(i.hotkey, i.kind) for i in items] == [("C", "check"), ("R", "raise")]


def test_handle_arrows_wrap_and_enter_checks() -> None:
    panel = ActionPanel.build(legal(to_call=40, can_check=False, min_raise=80, max_raise=1000))
    assert panel.handle("up", 100) is None
    assert panel.selected == len(panel.items()) - 1
    panel.handle("down", 100)
    assert panel.selected == 0
    assert panel.handle("down", 100) is None
    assert panel.selected == 1
    assert panel.handle("enter", 100) == Action("call")


def test_handle_hotkeys() -> None:
    full = legal(to_call=40, can_check=False, min_raise=80, max_raise=1000)
    assert ActionPanel.build(full).handle("f", 100) == Action("fold")
    assert ActionPanel.build(full).handle("c", 100) == Action("call")
    assert ActionPanel.build(full).handle("a", 100) == Action("allin")
    free = legal()
    assert ActionPanel.build(free).handle("c", 100) == Action("check")
    assert ActionPanel.build(free).handle("a", 100) is None  # no all-in over no bet
    blocked = legal(to_call=40, can_check=False, min_raise=None, max_raise=None)
    assert ActionPanel.build(blocked).handle("r", 100) is None  # cannot raise


def test_handle_digits_select_items() -> None:
    panel = ActionPanel.build(legal(to_call=40, can_check=False, min_raise=80, max_raise=1000))
    assert panel.handle("1", 100) == Action("fold")
    panel = ActionPanel.build(legal(to_call=40, can_check=False, min_raise=80, max_raise=1000))
    assert panel.handle("2", 100) == Action("call")


def test_raise_submode_flow() -> None:
    panel = ActionPanel.build(legal(to_call=40, can_check=False, min_raise=80, max_raise=1000))
    assert panel.handle("r", 200) is None
    assert panel.raising and panel.amount == 80
    assert panel.handle("3", 200) is None  # pot-size preset = to_call + pot = 240
    assert panel.amount == 240
    assert panel.handle("left", 200) is None
    assert panel.amount == 240 - 200 // 20
    assert panel.handle("escape", 200) is None
    assert not panel.raising
    panel.handle("r", 200)
    panel.amount = 1000
    assert panel.handle("enter", 200) == Action("raise", 1000)
    panel2 = ActionPanel.build(legal(to_call=0, can_check=True, min_raise=20, max_raise=500))
    panel2.handle("r", 100)
    panel2.amount = 5
    panel2.handle("shift-left", 100)
    assert panel2.amount == 20  # clamped to min
    panel2.amount = 495
    panel2.handle("shift-right", 100)
    assert panel2.amount == 500  # clamped to max
    assert panel2.handle("enter", 100) == Action("raise", 500)


def test_parse_action_static_forms() -> None:
    full = legal(to_call=40, can_check=False, min_raise=80, max_raise=1000)
    assert parse_action("f", full) == Action("fold")
    assert parse_action("c", full) == Action("call")
    assert parse_action("a", full) == Action("allin")
    assert parse_action("r240", full) == Action("raise", 240)
    assert parse_action("r79", full) is None
    assert parse_action("r1001", full) is None
    assert parse_action("x", full) is None


def test_auto_action() -> None:
    assert auto_action(legal()) == Action("check")
    assert auto_action(legal(to_call=40, can_check=False)) == Action("fold")
