from __future__ import annotations

import random

from rpoker.domain.actions import Action
from rpoker.domain.views import Street
from rpoker.engine.table import Table
from tests.engine.helpers import build_deck, cards


def make_table(names, stacks=None, blinds=(5, 10), deck_order=None, button=None):
    rng = random.Random(1)
    table = Table(
        names,
        stacks or [1000] * len(names),
        blinds,
        rng,
        deck_order=deck_order or cards("2c 3c 4c 5c 6c 7c 8c 9c Th Tc Td Th Jc Jd Jh Qc Qd Qh Kc Kd Kh Ac Ad Ah 2d 2h 2s 3d 3h 3s 4d 4h 4s 5d 5h 5s 6d 6h 6s 7d 7h 7s 8d 8h 8s 9d 9h 9s"),
    )
    if button is not None:
        table.button = button - 1
    table.start_hand()
    return table


def test_blinds_and_heads_up_button_is_sb():
    table = make_table(["A", "B"], button=2)
    assert table.seat_view(None).seats[0].street_bet == 5
    assert table.seat_view(None).seats[1].street_bet == 10
    assert table.seat_view(None).seats[0].is_button
    assert table.to_act == 0


def test_preflop_order_three_way():
    table = make_table(["A", "B", "C"], button=3)
    assert table.to_act == 0
    table.apply(0, Action("call"))
    assert table.to_act == 1
    table.apply(1, Action("call"))
    assert table.to_act == 2
    legal = table.seat_view(2).legal
    assert legal.can_check and legal.to_call == 0
    table.apply(2, Action("check"))
    assert table.to_act is None
    table.advance_street()
    assert table.street is Street.FLOP
    assert len(table.community) == 3
    assert table.to_act == 1


def test_postflop_first_actor_is_after_button():
    table = make_table(["A", "B", "C"], button=1)
    for _ in range(3):
        legal = table.seat_view(table.to_act).legal
        table.apply(table.to_act, Action("check") if legal.can_check else Action("call"))
    table.advance_street()
    assert table.to_act == 2


def test_check_raises_reopen_betting():
    table = make_table(["A", "B", "C"], button=3)
    table.apply(0, Action("call"))
    table.apply(1, Action("call"))
    table.apply(2, Action("check"))
    table.advance_street()
    table.apply(1, Action("check"))
    table.apply(2, Action("check"))
    table.apply(0, Action("raise", 20))
    assert table.to_act == 1
    table.apply(1, Action("raise", 60))
    assert table.to_act == 2
    table.apply(2, Action("fold"))
    assert table.to_act == 0
    assert table.seat_view(0).legal.to_call == 40
    table.apply(0, Action("call"))
    assert table.to_act is None


def test_min_raise_enforced():
    table = make_table(["A", "B", "C"], button=3)
    table.apply(0, Action("raise", 30))
    legal = table.seat_view(1).legal
    assert legal.min_raise_to == 50
    assert legal.max_raise_to == 1000


def test_short_allin_does_not_reopen():
    table = make_table(["A", "B", "C"], stacks=[1000, 1000, 85], button=3)
    table.apply(0, Action("raise", 50))
    table.apply(1, Action("call"))
    table.apply(2, Action("allin"))
    assert table._current_bet == 85
    assert table.to_act == 0
    legal = table.seat_view(0).legal
    assert legal.max_raise_to is None
    assert legal.to_call == 35


def test_bb_option_can_raise():
    table = make_table(["A", "B", "C"], button=3)
    table.apply(0, Action("call"))
    table.apply(1, Action("call"))
    legal = table.seat_view(2).legal
    assert legal.min_raise_to == 20


def test_blind_shortfall_is_allin():
    table = make_table(["A", "B"], stacks=[3, 1000], button=1)
    assert table.seat_view(None).seats[0].street_bet == 3
    assert table.seat_view(None).seats[0].allin


def test_fold_win_returns_uncalled():
    table = make_table(["A", "B", "C"], button=3)
    table.apply(0, Action("raise", 30))
    table.apply(1, Action("fold"))
    table.apply(2, Action("fold"))
    result = table.hand_result
    assert result.fold_win
    assert result.awards[0].name == "A"
    assert result.awards[0].amount == 25
    assert table.seat_view(None).seats[0].stack == 1015


def test_allin_runout_reaches_showdown():
    table = make_table(["A", "B"], stacks=[500, 500], blinds=(10, 20), button=1)
    table.apply(1, Action("allin"))
    table.apply(0, Action("call"))
    while table.street is not Street.HAND_OVER:
        table.advance_street()
    assert len(table.community) == 5
    assert table.hand_result is not None
    total = sum(s.stack for s in table.seat_view(None).seats)
    assert total == 1000


def test_side_pots_three_way():
    table = make_table(["A", "B", "C"], stacks=[300, 300, 300], blinds=(10, 20), button=3)
    table.apply(0, Action("allin"))
    table.apply(1, Action("allin"))
    table.apply(2, Action("call"))
    while table.street is not Street.HAND_OVER:
        table.advance_street()
    result = table.hand_result
    assert sum(a.amount for a in result.awards) == 900
    total = sum(s.stack for s in table.seat_view(None).seats)
    assert total == 900


def test_odd_chip_goes_to_first_after_button():
    table = make_table(["A", "B", "C"], button=3)
    for street_rounds in range(5):
        if table.to_act is None:
            table.advance_street()
        while table.to_act is not None:
            table.apply(table.to_act, Action("check") if table.seat_view(table.to_act).legal.can_check else Action("call"))
        if table.street is Street.HAND_OVER:
            break
    result = table.hand_result
    assert not result.fold_win
    assert sum(amount for amount, _ in result.pots) == sum(a.amount for a in result.awards)
    total = sum(s.stack for s in table.seat_view(None).seats)
    assert total == 3000


def test_hole_cards_deal_two_rounds():
    deck = build_deck(1, 3, {0: cards("As Ah"), 1: cards("Ks Kh"), 2: cards("Qs Qh")}, cards("2c 3c 4c 5c 6c"))
    table = make_table(["A", "B", "C"], deck_order=deck, button=1)
    assert table.seat_view(0).hole == cards("As Ah")
    assert table.seat_view(1).hole == cards("Ks Kh")
    assert table.seat_view(2).hole == cards("Qs Qh")
