from __future__ import annotations

import asyncio
import random

from rpoker.domain.actions import Action
from rpoker.domain.cards import STANDARD_52, find_best_hand
from rpoker.domain.views import SeatView


def win_probability(hole: tuple, community: tuple, rng: random.Random, samples: int = 150) -> float:
    known = set(hole) | set(community)
    remaining = [c for c in STANDARD_52 if c not in known]
    need = 5 - len(community)
    score = 0.0
    for _ in range(samples):
        picked = rng.sample(remaining, 2 + need)
        board = tuple(community) + tuple(picked[2:])
        mine = find_best_hand((*hole, *board))
        theirs = find_best_hand((picked[0], picked[1], *board))
        if mine > theirs:
            score += 1.0
        elif mine == theirs:
            score += 0.5
    return score / samples


class BotActor:
    def __init__(self, rng: random.Random, speed: float = 1.0) -> None:
        self._rng = rng
        self._speed = speed

    async def __call__(self, view: SeatView) -> Action:
        legal = view.legal
        await asyncio.sleep(self._rng.uniform(0.5, 1.4) * self._speed)
        if legal.can_check:
            if legal.max_raise_to is not None and self._rng.random() < 0.25:
                return Action("raise", self._bet_size(view, legal))
            return Action("check")
        strength = win_probability(view.hole, view.community, self._rng)
        odds = legal.to_call / (view.pot_total + legal.to_call)
        if strength > 0.78 and legal.max_raise_to is not None and self._rng.random() < 0.5:
            return Action("raise", self._bet_size(view, legal))
        if strength >= odds + 0.02:
            return Action("call")
        if legal.to_call <= view.pot_total // 20 and strength > 0.35:
            return Action("call")
        return Action("fold")

    def _bet_size(self, view: SeatView, legal) -> int:
        target = view.pot_total // 2 + legal.to_call
        target = max(target, legal.min_raise_to)
        jitter = self._rng.choice([1.0, 1.0, 1.5])
        return min(int(target * jitter), legal.max_raise_to)
