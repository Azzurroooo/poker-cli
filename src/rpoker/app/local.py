from __future__ import annotations

import random

from rpoker.actors.bot import BOT_NAMES, BotActor
from rpoker.app.table_loop import play_hand
from rpoker.engine.table import Table
from rpoker.ui.prompts import FrameView, Option, Terminal
from rpoker.ui.table_view import render
from rpoker.ui.tokens import THEMES, Theme


async def run_local(terminal: Terminal, nickname: str, settings) -> None:
    theme = THEMES[settings.theme]
    console = terminal.console
    names = [nickname] + BOT_NAMES[:3]
    rng = random.Random()
    table = Table(names, [settings.starting_stack] * len(names), settings.blinds, rng, act_seconds=settings.act_seconds)
    console.clear()
    with terminal.frame_view() as frames:

        async def broadcast(t: Table, result=None) -> None:
            frames.update(render(t.seat_view(0), theme, result=result, title="本地练习", viewer=nickname))

        actors: dict[int, object] = {i: BotActor(rng) for i in range(1, len(names))}
        actors[0] = _human(terminal, theme, frames)

        while not table.finished:
            await play_hand(table, actors, broadcast, _result_publisher(broadcast))
            frames.pause()
            try:
                choice = await terminal.menu("本手结束", [Option("下一手"), Option("回到主菜单")], cancellable=False)
            finally:
                frames.resume()
                console.clear()
                frames.update(render(table.seat_view(0), theme, title="本地练习", viewer=nickname))
            if choice != 0:
                break
    if table.finished:
        console.print("牌桌结束：只剩一名有筹码的玩家。", style=theme.gold)


def _result_publisher(broadcast):
    async def publish_result(table: Table) -> None:
        await broadcast(table, table.hand_result)

    return publish_result


def _human(terminal: Terminal, theme: Theme, frames: FrameView):
    async def actor(view):
        frames.pause()
        try:
            return await terminal.action(view, theme)
        finally:
            frames.resume()

    return actor
