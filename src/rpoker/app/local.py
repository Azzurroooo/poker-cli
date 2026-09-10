from __future__ import annotations

import random

from rpoker.actors.bot import BOT_NAMES, BotActor
from rpoker.app.table_loop import play_hand
from rpoker.engine.table import Table
from rpoker.ui.prompts import Option, Terminal
from rpoker.ui.render import FrameContext
from rpoker.ui.screen import GameScreen
from rpoker.ui.tokens import THEMES


async def run_local(terminal: Terminal, nickname: str, settings) -> None:
    theme = THEMES[settings.theme]
    console = terminal.console
    names = [nickname] + BOT_NAMES[:3]
    rng = random.Random()
    table = Table(names, [settings.starting_stack] * len(names), settings.blinds, rng, act_seconds=settings.act_seconds)
    console.clear()
    screen = GameScreen(
        terminal,
        FrameContext(theme, "本地练习", nickname, settings.blinds),
        settings.act_seconds,
        display=settings.display,
        on_display_change=_save_display(settings),
    )
    await screen.start()
    try:

        async def broadcast(t: Table, result=None) -> None:
            await screen.show(t.seat_view(0), result)

        actors: dict[int, object] = {0: screen.actor()}
        actors.update({i: BotActor(rng) for i in range(1, len(names))})

        options = [Option("下一手"), Option("回到主菜单")]
        while not table.finished:
            await play_hand(table, actors, broadcast, _result_publisher(broadcast))
            choice = await screen.interlude(table.hand_result, "本手结束", options)
            if choice != 0:
                break
    finally:
        await screen.close()
    if table.finished:
        console.print("牌桌结束：只剩一名有筹码的玩家。", style=theme.gold)


def _save_display(settings):
    def apply(display: str) -> None:
        settings.display = display
        settings.save()

    return apply


def _result_publisher(broadcast):
    async def publish_result(table: Table) -> None:
        await broadcast(table, table.hand_result)

    return publish_result
