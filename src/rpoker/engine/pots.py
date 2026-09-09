from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Pot:
    amount: int
    eligible: frozenset[int]


def uncalled_refund(committed: Mapping[int, int]) -> tuple[int, int | None]:
    ordered = sorted(committed.items(), key=lambda kv: kv[1], reverse=True)
    if len(ordered) >= 2 and ordered[0][1] > ordered[1][1]:
        return ordered[0][1] - ordered[1][1], ordered[0][0]
    return 0, None


def build_pots(contributors: Mapping[int, int], folded: set[int]) -> list[Pot]:
    pots: list[Pot] = []
    previous = 0
    for level in sorted(set(contributors.values())):
        layer = level - previous
        in_layer = [seat for seat, amount in contributors.items() if amount >= level]
        amount = layer * len(in_layer)
        eligible = frozenset(s for s in in_layer if s not in folded)
        if amount > 0:
            pots.append(Pot(amount, eligible))
        previous = level
    return pots
