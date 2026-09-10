from __future__ import annotations

import dataclasses
import time

from rpoker.domain.views import SeatView
from rpoker.net.connector import connect
from rpoker.net.messages import Act, Chat, Error, Hello, Result, State, Welcome
from rpoker.ui.prompts import Terminal
from rpoker.ui.render import render
from rpoker.ui.tokens import THEMES

ERROR_TEXTS = {
    "table_full": "房间已满，无法加入。",
    "started": "牌局已开始，本局无法中途加入。",
}


async def join_room(terminal: Terminal, settings, ip: str, port: int) -> None:
    theme = THEMES[settings.theme]
    try:
        connector = await connect(ip, port)
    except (ConnectionError, OSError):
        terminal.print("[red]无法连接到该房间。[/red]")
        return
    await connector.send(Hello(settings.nickname))
    reply = await connector.recv()
    if isinstance(reply, Error):
        terminal.print(f"[red]{ERROR_TEXTS.get(reply.code, '无法加入：' + reply.code)}[/red]")
        await connector.close()
        return
    if not isinstance(reply, Welcome):
        await connector.close()
        return
    assigned = reply.names[reply.seat] or settings.nickname
    terminal.print(f"已加入「{reply.room}」（座位 {reply.seat + 1}/{len(reply.names)}，昵称 {assigned}），等待房主开始牌局…")
    await _game(terminal, settings, connector, reply, assigned, theme)
    terminal.print("[yellow]已与房间断开。[/yellow]")


async def _game(terminal: Terminal, settings, connector, welcome: Welcome, display: str, theme) -> None:
    console = terminal.console
    console.clear()
    last_view: SeatView | None = None
    with terminal.frame_view() as frames:
        while True:
            message = await connector.recv()
            if message is None or isinstance(message, Error):
                frames.pause()
                console.print("[yellow]房主已关闭房间。[/yellow]")
                break
            if isinstance(message, State):
                view = message.view
                if view.to_act == welcome.seat and view.deadline is None:
                    view = dataclasses.replace(view, deadline=time.monotonic() + welcome.act_seconds)
                last_view = view
                frames.update(render(view, theme, title=welcome.room, viewer=display))
                if view.to_act == welcome.seat:
                    frames.pause()
                    try:
                        action = await terminal.action(view, theme, send_chat=_chat_sender(connector))
                    finally:
                        frames.resume()
                    await connector.send(Act(action.kind, action.amount))
            elif isinstance(message, Result):
                if last_view is not None:
                    frames.update(render(last_view, theme, result=message.result, title=welcome.room,
                                         viewer=display))
            elif isinstance(message, Chat):
                frames.pause()
                console.print(message.text)
                frames.resume()
    await connector.close()


def _chat_sender(connector):
    async def send(text: str) -> None:
        await connector.send(Chat(text))

    return send
