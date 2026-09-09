from __future__ import annotations

from typing import Protocol

from rpoker.domain.actions import Action
from rpoker.domain.views import SeatView


class Actor(Protocol):
    async def __call__(self, view: SeatView) -> Action: ...
