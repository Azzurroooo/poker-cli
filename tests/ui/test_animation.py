from __future__ import annotations

import asyncio

from rpoker.domain.views import SeatView, Street
from rpoker.engine.table import Award, HandResult
from rpoker.ui.render import FrameContext, UiState, rich_frame
from rpoker.ui.screen import diff_views
from rpoker.ui.tokens import THEMES
from tests.engine.helpers import cards
from tests.ui.test_screen import build_view, make_screen

CTX = FrameContext(THEMES["onedark"], "测试房", "你", (5, 10))


def flop_view() -> SeatView:
    view = build_view()
    return SeatView(
        hand_no=view.hand_no,
        street=Street.FLOP,
        button=view.button,
        community=cards("Qd 2h Js"),
        pot_total=100,
        seats=view.seats,
        hole=view.hole,
        to_act=view.to_act,
        legal=None,
        deadline=None,
        log=view.log,
    )


def test_diff_views_first_show_starts_hand() -> None:
    changes = diff_views(None, build_view())
    assert changes.hand_started and changes.new_community == 0 and changes.to_act_changed


def test_diff_views_same_hand() -> None:
    changes = diff_views(build_view(), flop_view())
    assert not changes.hand_started
    assert changes.new_community == 3
    assert changes.pot_delta == 70
    assert not changes.to_act_changed


def test_diff_views_new_hand_resets_community_delta() -> None:
    changes = diff_views(flop_view(), build_view(hand_no=2))
    assert changes.hand_started
    assert changes.new_community == 0


def test_showdown_presentation_reveals_then_highlights() -> None:
    screen = make_screen()

    async def run() -> None:
        await screen.start()
        view = build_view()
        await screen.show(view)
        hand = HandResult(
            fold_win=False,
            awards=(Award("你", 100, None),),
            reveal={"你": view.hole, "老周（bot）": cards("Qd Qh")},
            best={},
            pots=((100, ("你",)),),
        )
        await screen.show(view, hand)
        assert screen._reveal_lines == ("你 亮牌 A♥ K♠", "老周（bot） 亮牌 Q♦ Q♥")
        assert screen._winners == frozenset({"你"})
        frame = rich_frame(screen._view, screen._build_ui(), CTX, 100, 34)
        assert "★" in frame.plain  # winner seat carries the star marker
        assert "老周（bot） 亮牌 Q♦ Q♥" in frame.plain
        await screen.close()

    asyncio.run(run())


def test_new_hand_clears_winner_state() -> None:
    screen = make_screen()

    async def run() -> None:
        await screen.start()
        screen._winners = frozenset({"你"})
        screen._reveal_lines = ("x 亮牌 A♠ A♥",)
        await screen.show(build_view(hand_no=2))
        assert screen._winners == frozenset()
        assert screen._reveal_lines == ()
        await screen.close()

    asyncio.run(run())


def test_thinking_indicator_targets_bot_seat() -> None:
    screen = make_screen()

    async def run() -> None:
        await screen.start()
        await screen.show(build_view())  # to_act = 1 老周（bot）
        assert screen._thinking == 1
        screen._tick = 1
        frame = rich_frame(screen._view, screen._build_ui(), CTX, 100, 34)
        assert "行动中 ●·" in frame.plain
        await screen.close()

    asyncio.run(run())


def test_human_turn_clears_thinking() -> None:
    screen = make_screen()

    async def run() -> None:
        await screen.start()
        await screen.show(build_view(to_act=0))  # 你
        assert screen._thinking is None
        await screen.close()

    asyncio.run(run())


def test_pot_pulse_and_hidden_hero_are_rendered() -> None:
    view = build_view()
    frame = rich_frame(view, UiState(hero_hidden=True, pot_pulse=True), CTX, 100, 34)
    assert "◈" in frame.plain
    assert "A♥" not in frame.plain  # hole cards still face down
    frame2 = rich_frame(flop_view(), UiState(reveal_upto=2), CTX, 100, 34)
    assert "J♠" not in frame2.plain  # third board card still hidden
    assert frame2.plain.count("▓") > 0
