from __future__ import annotations

import random

from rpoker.domain.actions import Action
from rpoker.domain.views import Street
from rpoker.engine.table import Table


def random_action(rng: random.Random, legal):
    choices = []
    if legal.can_check:
        choices.append(Action("check"))
    if legal.to_call > 0:
        choices.append(Action("call"))
    if legal.max_raise_to is not None:
        choices.append(Action("raise", legal.min_raise_to))
        choices.append(Action("raise", legal.max_raise_to))
        midpoint = (legal.min_raise_to + legal.max_raise_to) // 2
        if midpoint > legal.min_raise_to:
            choices.append(Action("raise", midpoint))
    if legal.to_call > 0:
        choices.append(Action("fold"))
    return rng.choice(choices)


def play_hands(names, stacks, blinds, seed, hands=30):
    rng = random.Random(seed)
    table = Table(names, stacks, blinds, rng)
    for _ in range(hands):
        if table.finished:
            break
        table.start_hand()
        guard = 0
        while table.street is not Street.HAND_OVER:
            guard += 1
            assert guard < 10000, "hand loop stuck"
            if table.to_act is None:
                table.advance_street()
            else:
                table.apply(table.to_act, random_action(rng, table.seat_view(table.to_act).legal))
        yield table


def test_chips_conserved_over_many_random_hands():
    names = ["A", "B", "C", "D"]
    total_start = 4 * 1000
    for table in play_hands(names, [1000] * 4, (5, 10), seed=42):
        total = sum(s.stack for s in table.seat_view(None).seats)
        assert total == total_start, f"hand {table.hand_no}: {total}"


def test_replay_determinism():
    def run() -> list:
        return [t.log for t in play_hands(["A", "B", "C"], [1000] * 3, (5, 10), seed=7, hands=15)]

    assert run() == run()


def test_no_crash_on_odd_stacks():
    names = ["A", "B", "C", "D", "E"]
    stacks = [7, 13, 999, 3, 250]
    total = sum(stacks)
    for table in play_hands(names, stacks, (5, 10), seed=99, hands=50):
        assert sum(s.stack for s in table.seat_view(None).seats) == total


def test_finish_condition():
    table = Table(["A", "B"], [0, 500], (5, 10), random.Random(1))
    assert table.finished
