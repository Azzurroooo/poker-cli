from __future__ import annotations

import random

from rich.live import Live

from rpoker.actors.bot import BotActor
from rpoker.app.table_loop import play_hand
from rpoker.engine.table import Table
from rpoker.ui.prompts import Option, Terminal
from rpoker.ui.table_view import render
from rpoker.ui.tokens import THEMES, Theme

BOT_NAMES = ["小北", "阿棠", "老周", "绵绵", "大熊", "石头", "飞飞", "可可"]


async def run_local(terminal: Terminal, nickname: str, settings) -> None:
    theme = THEMES[settings.theme]
    console = terminal.console
    names = [nickname] + BOT_NAMES[:3]
    rng = random.Random()
    table = Table(names, [settings.starting_stack] * len(names), settings.blinds, rng, act_seconds=settings.act_seconds)
    console.clear()
    with Live(console=console, refresh_per_second=4, transient=False) as live:

        async def broadcast(t: Table, result=None) -> None:
            live.update(render(t.seat_view(0), theme, result=result, title="本地练习", viewer=nickname))

        actors: dict[int, object] = {i: BotActor(rng) for i in range(1, len(names))}
        actors[0] = _human(terminal, theme, live)

        while not table.finished:
            await play_hand(table, actors, broadcast, _result_publisher(broadcast))
            live.stop()
            try:
                choice = await terminal.menu("本手结束", [Option("下一手"), Option("回到主菜单")], cancellable=False)
            finally:
                live.start()
                console.clear()
                live.update(render(table.seat_view(0), theme, title="本地练习", viewer=nickname))
            if choice != 0:
                break
    if table.finished:
        console.print("牌桌结束：只剩一名有筹码的玩家。", style=theme.gold)


def _result_publisher(broadcast):
    async def publish_result(table: Table) -> None:
        await broadcast(table, table.hand_result)

    return publish_result


def _human(terminal: Terminal, theme: Theme, live: Live):
    async def actor(view):
        live.stop()
        try:
            return await terminal.action(view, theme)
        finally:
            live.start()

    return actor
