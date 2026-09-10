"""Frame invariants under random play: constant height, bounded width (军规 3/4)."""
from __future__ import annotations

import random
from collections.abc import Callable

from rich.cells import cell_len

from rpoker.domain.actions import Action, LegalActions
from rpoker.domain.views import SeatView, Street
from rpoker.engine.table import Table
from rpoker.ui.layout import rich_budget, rich_tier
from rpoker.ui.panels import ActionPanel
from rpoker.ui.render import FrameContext, UiState, rich_frame, simple_frame
from rpoker.ui.tokens import THEMES

THEME = THEMES["onedark"]
CTX = FrameContext(THEME, "测试房", "P0", (5, 10))
TIERS = [(100, 34), (90, 32), (80, 24), (120, 40)]


def _random_action(rng: random.Random, legal: LegalActions) -> Action:
    options: list[Callable[[], Action]] = []
    options.append(lambda: Action("fold"))
    options.append(lambda: Action("check") if legal.can_check else Action("call"))
    if legal.max_raise_to is not None:
        options.append(lambda: Action("raise", rng.randint(legal.min_raise_to, legal.max_raise_to)))
        options.append(lambda: Action("allin"))
    return rng.choice(options)()


def collect_views(seed: int, seats: int, hands: int = 3) -> list[SeatView]:
    rng = random.Random(seed)
    table = Table([f"P{i}" for i in range(seats)], [300] * seats, (5, 10), rng)
    views: list[SeatView] = []
    for _ in range(hands):
        if table.finished:
            break
        table.start_hand()
        views.append(table.seat_view(0))
        guard = 0
        while table.street is not Street.HAND_OVER and guard < 400:
            guard += 1
            if table.to_act is None:
                table.advance_street()
            else:
                seat = table.to_act
                legal = table.seat_view(seat).legal
                assert legal is not None
                table.apply(seat, _random_action(rng, legal))
            views.append(table.seat_view(0))
    return views


def test_frame_height_is_constant_within_a_hand() -> None:
    for seed in range(8):
        for seats in (2, 3, 5, 9):
            views = collect_views(seed, seats)
            assert views, "random hand produced no frames"
            tier = rich_tier(100, 34)
            budget = rich_budget(tier, seats)
            for view in views:
                ui = UiState(panel=ActionPanel.build(view.legal) if view.legal else None, countdown=30)
                frame = rich_frame(view, ui, CTX, 100, 34)
                assert len(frame.plain.split("\n")) == budget.height, (
                    f"seed={seed} seats={seats} hand={view.hand_no} street={view.street}"
                )


def test_no_frame_line_exceeds_terminal_width() -> None:
    for seed in range(8):
        for seats in (2, 5, 9):
            for width, height in TIERS:
                for view in collect_views(seed, seats, hands=1):
                    for ui in (UiState(), UiState(panel=ActionPanel.build(view.legal) if view.legal else None)):
                        frame = rich_frame(view, ui, CTX, width, height)
                        for line in frame.plain.split("\n"):
                            assert cell_len(line) <= width, (
                                f"seed={seed} seats={seats} {width}x{height}: {line!r}"
                        )


def test_log_growth_does_not_change_height() -> None:
    views = collect_views(1, 4, hands=2)
    heights = set()
    for view in views:
        plain = simple_frame(view, UiState(), CTX, 80).plain
        heights.add(len(plain.split("\n")))
    assert len(heights) <= 1, f"simple frame height varies within session: {heights}"
