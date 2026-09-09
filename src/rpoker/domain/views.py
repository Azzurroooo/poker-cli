from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from rpoker.domain.actions import LegalActions
from rpoker.domain.cards import Card


class Street(StrEnum):
    WAITING = "waiting"
    PREFLOP = "preflop"
    FLOP = "flop"
    TURN = "turn"
    RIVER = "river"
    HAND_OVER = "hand_over"


@dataclass(frozen=True, slots=True)
class SeatInfo:
    index: int
    name: str
    stack: int
    street_bet: int
    folded: bool
    allin: bool
    is_button: bool


@dataclass(frozen=True, slots=True)
class SeatView:
    hand_no: int
    street: Street
    button: int
    community: tuple[Card, ...]
    pot_total: int
    seats: tuple[SeatInfo, ...]
    hole: tuple[Card, ...] | None
    to_act: int | None
    legal: LegalActions | None
    deadline: float | None
    log: tuple[str, ...]
