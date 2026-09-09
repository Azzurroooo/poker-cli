from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class Action:
    kind: Literal["fold", "check", "call", "raise", "allin"]
    amount: int | None = None


@dataclass(frozen=True, slots=True)
class LegalActions:
    can_check: bool
    to_call: int
    min_raise_to: int | None
    max_raise_to: int | None
