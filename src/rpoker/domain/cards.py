from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from itertools import combinations
from typing import Sequence


class Suit(StrEnum):
    CLUBS = "♣"
    DIAMONDS = "♦"
    HEARTS = "♥"
    SPADES = "♠"


def rank_label(rank: int) -> str:
    return {11: "J", 12: "Q", 13: "K", 14: "A"}.get(rank, str(rank))


@dataclass(frozen=True, slots=True, order=True)
class Card:
    rank: int
    suit: Suit

    def __str__(self) -> str:
        return f"{rank_label(self.rank)}{self.suit}"


STANDARD_52 = tuple(Card(rank, suit) for suit in Suit for rank in range(2, 15))


class Deck:
    def __init__(self, rng: random.Random, order: Sequence[Card] | None = None) -> None:
        self._cards = list(order) if order is not None else list(STANDARD_52)
        if order is None:
            rng.shuffle(self._cards)

    def deal(self, count: int) -> tuple[Card, ...]:
        if count > len(self._cards):
            raise ValueError("deck exhausted")
        dealt = self._cards[-count:]
        del self._cards[-count:]
        return tuple(dealt)


class HandKind(IntEnum):
    HIGH_CARD = 1
    PAIR = 2
    TWO_PAIR = 3
    TRIPS = 4
    STRAIGHT = 5
    FLUSH = 6
    FULL_HOUSE = 7
    QUADS = 8
    STRAIGHT_FLUSH = 9


@dataclass(frozen=True, slots=True, order=True)
class HandScore:
    kind: HandKind
    tiebreak: tuple[int, ...]

    def label(self) -> str:
        top = rank_label(self.tiebreak[0])
        match self.kind:
            case HandKind.HIGH_CARD:
                return f"高牌 {top}"
            case HandKind.PAIR:
                return f"一对 {top}"
            case HandKind.TWO_PAIR:
                return f"两对 {top} 和 {rank_label(self.tiebreak[1])}"
            case HandKind.TRIPS:
                return f"三条 {top}"
            case HandKind.STRAIGHT:
                return f"顺子（{top} 高）"
            case HandKind.FLUSH:
                return f"同花（{top} 高）"
            case HandKind.FULL_HOUSE:
                return f"葫芦（{top} 带 {rank_label(self.tiebreak[1])}）"
            case HandKind.QUADS:
                return f"四条 {top}"
            case _:
                return "皇家同花顺" if self.tiebreak[0] == 14 else f"同花顺（{top} 高）"


def _straight_top(distinct: tuple[int, ...]) -> int | None:
    if len(distinct) != 5:
        return None
    if distinct[0] - distinct[4] == 4:
        return distinct[0]
    if distinct == (14, 5, 4, 3, 2):
        return 5
    return None


def _score_five(cards: tuple[Card, ...]) -> HandScore:
    ranks = tuple(sorted((c.rank for c in cards), reverse=True))
    is_flush = len({c.suit for c in cards}) == 1
    top = _straight_top(tuple(sorted(set(ranks), reverse=True)))
    if is_flush and top:
        return HandScore(HandKind.STRAIGHT_FLUSH, (top,))
    counts = Counter(ranks)
    groups = sorted(counts.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)
    if groups[0][1] == 4:
        return HandScore(HandKind.QUADS, (groups[0][0], groups[1][0]))
    if groups[0][1] == 3 and groups[1][1] == 2:
        return HandScore(HandKind.FULL_HOUSE, (groups[0][0], groups[1][0]))
    if is_flush:
        return HandScore(HandKind.FLUSH, ranks)
    if top:
        return HandScore(HandKind.STRAIGHT, (top,))
    if groups[0][1] == 3:
        kickers = tuple(r for r in ranks if r != groups[0][0])
        return HandScore(HandKind.TRIPS, (groups[0][0], *kickers))
    if groups[0][1] == 2 and groups[1][1] == 2:
        pairs = [r for r, n in groups if n == 2]
        kicker = next(r for r in ranks if r not in pairs)
        return HandScore(HandKind.TWO_PAIR, (max(pairs), min(pairs), kicker))
    if groups[0][1] == 2:
        kickers = tuple(r for r in ranks if r != groups[0][0])
        return HandScore(HandKind.PAIR, (groups[0][0], *kickers))
    return HandScore(HandKind.HIGH_CARD, ranks)


def best_five(cards: Sequence[Card]) -> tuple[HandScore, tuple[Card, ...]]:
    if len(cards) < 5:
        raise ValueError("need at least 5 cards")
    if len(cards) == 5:
        hand = tuple(cards)
        return _score_five(hand), hand
    hand = max(combinations(cards, 5), key=_score_five)
    return _score_five(hand), hand


def find_best_hand(cards: Sequence[Card]) -> HandScore:
    return best_five(cards)[0]
