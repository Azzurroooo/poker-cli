from __future__ import annotations

import random
from typing import Mapping, Sequence

from rpoker.domain.cards import STANDARD_52, Card, Suit, find_best_hand


def card(spec: str) -> Card:
    label_to_rank = {"T": 10, "J": 11, "Q": 12, "K": 13, "A": 14}
    suit_map = {"c": Suit.CLUBS, "d": Suit.DIAMONDS, "h": Suit.HEARTS, "s": Suit.SPADES}
    rank = int(spec[0]) if spec[0].isdigit() else label_to_rank[spec[0]]
    return Card(rank, suit_map[spec[1]])


def cards(specs: str) -> tuple[Card, ...]:
    return tuple(card(s) for s in specs.split())


def build_deck(
    button: int,
    seat_count: int,
    holes: Mapping[int, Sequence[Card]],
    community: Sequence[Card],
) -> list[Card]:
    seats = [(button + 1 + step) % seat_count for step in range(seat_count)]
    pops = [holes[seat][round_no] for round_no in range(2) for seat in seats]
    pops += list(community)
    deck = [c for c in STANDARD_52 if c not in pops]
    deck += list(reversed(pops))
    return deck


def scripted_table(
    table_factory,
    names: list[str],
    button: int,
    holes: Mapping[int, Sequence[Card]],
    community: Sequence[Card] = (),
    stacks: list[int] | None = None,
    blinds: tuple[int, int] = (5, 10),
):
    stacks = stacks or [1000] * len(names)
    rng = random.Random(7)
    deck_order = build_deck(button, len(names), holes, community)
    table = table_factory(names, stacks, blinds, rng, deck_order=deck_order)
    table.start_hand()
    return table
