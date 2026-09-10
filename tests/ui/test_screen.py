from __future__ import annotations

import asyncio
import io

import pytest
from rich.console import Console

from rpoker.domain.actions import Action, LegalActions
from rpoker.domain.views import SeatInfo, SeatView, Street
from rpoker.ui.panels import ActionPanel
from rpoker.ui.prompts import QuitApp, Terminal
from rpoker.ui.render import FrameContext, UiState, simple_frame
from rpoker.ui.screen import GameScreen
from rpoker.ui.tokens import THEMES
from tests.engine.helpers import cards

THEME = THEMES["onedark"]
FACING_BET = LegalActions(False, 40, 80, 1000)
FREE_CHECK = LegalActions(True, 0, 20, 990)


def build_view(to_act=1, legal=None, hand_no=1, pot=30) -> SeatView:
    seats = tuple(
        SeatInfo(i, name, 1000 - (10 if i < 2 else 0), 10 if i < 2 else 0, False, False, i == 0)
        for i, name in enumerate(["你", "老周（bot）", "阿棠（bot）"])
    )
    return SeatView(
        hand_no=hand_no,
        street=Street.PREFLOP,
        button=0,
        community=(),
        pot_total=pot,
        seats=seats,
        hole=cards("Ah Ks"),
        to_act=to_act,
        legal=legal,
        deadline=None,
        log=("—— 第 1 手 ——", "你 小盲 10 · 老周（bot） 大盲 10"),
    )


def make_screen(act_seconds: float = 30) -> GameScreen:
    console = Console(file=io.StringIO(), force_terminal=True, width=100, height=40,
                      color_system="truecolor", highlight=False, legacy_windows=False)
    terminal = Terminal(console)
    terminal.tty = True  # simulate a TTY without touching the real stdin
    return GameScreen(terminal, FrameContext(THEME, "本地练习", "你", (5, 10)), act_seconds)


def output(screen: GameScreen) -> str:
    return screen.terminal.console.file.getvalue()


def test_frame_refreshes_only_when_content_changes() -> None:
    screen = make_screen()

    async def run() -> None:
        await screen.start()
        view = build_view()
        await screen.show(view)
        after_first = output(screen)
        assert after_first, "frame never rendered"
        await screen.show(build_view())  # identical state → zero new bytes (军规 2)
        assert output(screen) == after_first
        await screen.show(build_view(pot=45))
        assert output(screen) != after_first
        await screen.close()

    asyncio.run(run())


def test_act_consumes_injected_keys_until_action() -> None:
    screen = make_screen()

    async def run() -> None:
        await screen.start()
        task = asyncio.create_task(screen.act(build_view(to_act=0, legal=FACING_BET)))
        await asyncio.sleep(0.05)
        screen._keys.put_nowait("down")
        await asyncio.sleep(0.05)
        screen._keys.put_nowait("enter")
        action = await asyncio.wait_for(task, 2)
        assert action == Action("call")
        await screen.close()

    asyncio.run(run())


def test_act_timeout_returns_auto_action() -> None:
    screen = make_screen(act_seconds=0.05)

    async def run() -> None:
        await screen.start()
        action = await asyncio.wait_for(screen.act(build_view(to_act=0, legal=FREE_CHECK)), 2)
        assert action == Action("check")
        await screen.close()

    asyncio.run(run())


def test_act_raises_when_quit_confirmed() -> None:
    screen = make_screen()

    async def run() -> None:
        await screen.start()
        task = asyncio.create_task(screen.act(build_view(to_act=0, legal=FREE_CHECK)))
        await asyncio.sleep(0.05)
        screen._quit = True
        with pytest.raises(QuitApp):
            await asyncio.wait_for(task, 2)
        await screen.close()

    asyncio.run(run())


def test_frame_line_height_is_constant_across_turns() -> None:
    ctx = FrameContext(THEME, "本地练习", "你", (5, 10))
    view = build_view()
    acting = UiState(panel=ActionPanel.build(FACING_BET), countdown=30)
    idle = UiState()

    def height(ui: UiState) -> int:
        buffer = io.StringIO()
        Console(file=buffer, force_terminal=True, width=100, highlight=False).print(simple_frame(view, None, ui, ctx))
        return len(buffer.getvalue().rstrip("\n").split("\n"))

    assert height(acting) == height(idle), "frame height must not change when the turn passes"
