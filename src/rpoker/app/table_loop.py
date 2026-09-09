from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping

from rpoker.actors.protocols import Actor
from rpoker.domain.actions import Action
from rpoker.domain.views import Street
from rpoker.engine.table import Table


def auto_action(legal) -> Action:
    return Action("check") if legal.can_check else Action("fold")


async def play_hand(
    table: Table,
    actors: Mapping[int, Actor],
    broadcast: Callable[[Table], Awaitable[None]],
    publish_result: Callable[[Table], Awaitable[None]],
) -> None:
    table.start_hand()
    await broadcast(table)
    while table.street is not Street.HAND_OVER:
        if table.to_act is None:
            table.advance_street()
            await broadcast(table)
            continue
        seat = table.to_act
        view = table.seat_view(seat)
        try:
            action = await asyncio.wait_for(actors[seat](view), timeout=table.act_seconds + 3)
        except TimeoutError:
            action = auto_action(view.legal)
        except Exception:
            action = auto_action(view.legal)
        table.apply(seat, action)
        await broadcast(table)
    await publish_result(table)
