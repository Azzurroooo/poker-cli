from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from rich.cells import cell_len

RICH_MIN = (90, 32)
WIDE_MIN = (120, 40)
COMPACT_MIN = (70, 24)


class Mode(StrEnum):
    RICH = "rich"
    SIMPLE = "simple"


class Tier(StrEnum):
    WIDE = "wide"
    NORMAL = "normal"
    COMPACT = "compact"


def effective_mode(display: str, width: int, height: int) -> Mode:
    """User preference downgraded to simple when the terminal cannot hold a rich frame."""
    if display == "simple" or width < COMPACT_MIN[0] or height < COMPACT_MIN[1]:
        return Mode.SIMPLE
    return Mode.RICH


def rich_tier(width: int, height: int) -> Tier:
    if (width, height) >= WIDE_MIN:
        return Tier.WIDE
    if (width, height) >= RICH_MIN:
        return Tier.NORMAL
    return Tier.COMPACT


def seat_order(n: int, anchor: int) -> list[int]:
    """Display order with the anchored seat (hero, or button for spectators) bottom-right."""
    return [(anchor + 1 + i) % n for i in range(n - 1)] + [anchor]


def seat_box_width(names: list[str], terminal_width: int, boxed: bool) -> int:
    longest = max((cell_len(name) for name in names), default=4)
    if not boxed:
        return 0
    half = (terminal_width - 6) // 2
    return max(20, min(longest + 14, 30, half))


@dataclass(frozen=True, slots=True)
class Budget:
    header: int
    seats: int
    community: int
    hero: int
    log: int
    action: int
    keybar: int

    @property
    def height(self) -> int:
        return self.header + self.seats + self.community + self.hero + self.log + self.action + self.keybar


def rich_budget(tier: Tier, n_seats: int) -> Budget:
    boxed = n_seats <= 6 and tier is not Tier.COMPACT
    rows = (n_seats + 1) // 2
    seats = rows * 3 if boxed else rows
    community = 7 if tier is not Tier.COMPACT else 4  # panel(5-card) vs inline mini row
    hero = 10 if tier is Tier.WIDE else 6
    log = 5 if tier is Tier.WIDE else 2 if tier is Tier.COMPACT else 3
    return Budget(1, seats, community, hero, log, 4, 1)
