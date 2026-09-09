from __future__ import annotations

from dataclasses import dataclass

from rpoker.domain.views import SeatView
from rpoker.engine.table import HandResult

PROTOCOL_VERSION = 1

TCP_PORT = 45691
PORT_RANGE = 9


@dataclass(frozen=True, slots=True)
class Hello:
    name: str


@dataclass(frozen=True, slots=True)
class Welcome:
    seat: int
    room: str
    names: list[str]
    blinds: list[int]
    stack: int
    act_seconds: float


@dataclass(frozen=True, slots=True)
class Act:
    kind: str
    amount: int | None = None


@dataclass(frozen=True, slots=True)
class Chat:
    text: str
    sender: str = ""


@dataclass(frozen=True, slots=True)
class Leave:
    pass


@dataclass(frozen=True, slots=True)
class State:
    view: SeatView


@dataclass(frozen=True, slots=True)
class Result:
    result: HandResult


@dataclass(frozen=True, slots=True)
class Error:
    code: str


Message = Hello | Welcome | Act | Chat | Leave | State | Result | Error
