from __future__ import annotations

from rpoker.domain.views import SeatView
from rpoker.net.connector import connect
from rpoker.net.messages import Act, Error, Hello, Result, State, Welcome
from rpoker.ui.prompts import Terminal
from rpoker.ui.render import FrameContext
from rpoker.ui.screen import GameScreen
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
    await _game(terminal, connector, welcome=reply, display=assigned, theme=theme)
    terminal.print("[yellow]已与房间断开。[/yellow]")


async def _game(terminal: Terminal, connector, welcome: Welcome, display: str, theme) -> None:
    console = terminal.console
    console.clear()
    screen = GameScreen(
        terminal,
        FrameContext(theme, welcome.room, display, (welcome.blinds[0], welcome.blinds[1])),
        welcome.act_seconds,
    )
    await screen.start()
    closed = False
    last_view: SeatView | None = None
    try:
        while True:
            message = await connector.recv()
            if message is None or isinstance(message, Error):
                closed = True
                break
            if isinstance(message, State):
                last_view = message.view
                await screen.show(message.view)
                if message.view.to_act == welcome.seat:
                    action = await screen.act(message.view)
                    await connector.send(Act(action.kind, action.amount))
            elif isinstance(message, Result) and last_view is not None:
                await screen.show(last_view, message.result)
    finally:
        await screen.close()
    if closed:
        console.print("[yellow]房主已关闭房间。[/yellow]")
    await connector.close()
