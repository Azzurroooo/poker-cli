from __future__ import annotations

import asyncio
import random
import socket
from dataclasses import dataclass, field

from rich.panel import Panel
from rich.text import Text

from rpoker.actors.bot import BOT_NAMES, BotActor
from rpoker.app.table_loop import play_hand
from rpoker.domain.actions import Action
from rpoker.engine.table import Table
from rpoker.net import beacon
from rpoker.net.connector import TcpConnector
from rpoker.net.messages import (
    PORT_RANGE,
    TCP_PORT,
    Act,
    Chat,
    Error,
    Hello,
    Leave,
    Result,
    State,
    Welcome,
)
from rpoker.ui.prompts import Option, Terminal
from rpoker.ui.render import FrameContext
from rpoker.ui.screen import GameScreen
from rpoker.ui.tokens import THEMES, Theme


@dataclass(slots=True)
class _Conn:
    connector: TcpConnector
    name: str
    seat: int
    queue: asyncio.Queue[Act] = field(default_factory=asyncio.Queue)
    alive: bool = True

    def new_turn(self) -> None:
        self.queue = asyncio.Queue()


class Room:
    def __init__(self, terminal: Terminal, settings, room_name: str) -> None:
        self.terminal = terminal
        self.settings = settings
        self.room_name = room_name
        self.theme: Theme = THEMES[settings.theme]
        self.names: list[str | None] = [None] * settings.table_size
        self.names[0] = settings.nickname
        self.conns: list[_Conn] = []
        self.started = False
        self.port = 0
        self.events: asyncio.Queue[str] = asyncio.Queue()
        self._lobby = False
        self._screen: GameScreen | None = None
        self._adv_task: asyncio.Task | None = None
        self._server: asyncio.Server | None = None

    async def run(self) -> None:
        if not self._bind():
            self.terminal.print("[red]本机端口被占用，无法创建房间。[/red]")
            return
        self._server = await asyncio.start_server(self._on_client, "", self.port)
        self._adv_task = asyncio.create_task(beacon.advertise(self.port, self.room_name, self._status))
        try:
            await self._waiting()
        finally:
            await self._shutdown()

    def _status(self) -> tuple[int, int, bool]:
        return sum(1 for n in self.names if n is not None), self.settings.table_size, self.started

    def _bind(self) -> bool:
        for port in range(TCP_PORT, TCP_PORT + PORT_RANGE):
            sock = socket.socket()
            try:
                sock.bind(("", port))
                self.port = port
                return True
            except OSError:
                continue
            finally:
                sock.close()
        return False

    async def _on_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        connector = TcpConnector(reader, writer)
        try:
            hello = await asyncio.wait_for(connector.recv(), timeout=5)
            if not isinstance(hello, Hello):
                raise TypeError("expected hello")
            if self.started:
                await connector.send(Error("started"))
                return
            seat = next((i for i, n in enumerate(self.names) if n is None), None)
            if seat is None:
                await connector.send(Error("table_full"))
                return
            base = hello.name.strip() or "玩家"
            name, n = base, 2
            while any(taken == name for taken in self.names):
                name = f"{base}{n}"
                n += 1
            conn = _Conn(connector, name, seat)
            self.names[seat] = name
            self.conns.append(conn)
            await connector.send(
                Welcome(seat, self.room_name, [n or "" for n in self.names], list(self.settings.blinds),
                        self.settings.starting_stack, self.settings.act_seconds)
            )
            await self._say(f"系统：{name} 加入了房间")
            await self._pump(conn)
        except (TimeoutError, TypeError, ConnectionError, OSError):
            await connector.close()

    async def _pump(self, conn: _Conn) -> None:
        while True:
            message = await conn.connector.recv()
            if message is None or isinstance(message, (Leave, Hello)):
                break
            if isinstance(message, Act):
                await conn.queue.put(message)
            elif isinstance(message, Chat):
                await self._say(f"{conn.name}：{message.text}")
        conn.alive = False
        if conn in self.conns:
            self.conns.remove(conn)
        if not self.started:
            self.names[conn.seat] = None
        await self._say(f"系统：{conn.name} 离开了房间")

    async def _say(self, line: str) -> None:
        if self._screen is not None:
            self._screen.add_chat(line)
        elif self._lobby:
            self.events.put_nowait(line)
        else:
            print(line)
        for conn in list(self.conns):
            if not conn.alive:
                continue
            try:
                await conn.connector.send(Chat(line))
            except (ConnectionError, OSError):
                conn.alive = False

    async def _waiting(self) -> None:
        terminal = self.terminal
        ip = _lan_ip()
        spinner = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        frame = 0
        printed = 0
        members: tuple[str | None, ...] | None = None
        self._lobby = True
        try:
            while True:
                while not self.events.empty():
                    terminal._erase_above(printed)
                    terminal.print(self.events.get_nowait())
                    printed = 0
                    members = None
                roster = self._roster(ip)
                height = _height(roster)
                if members != tuple(self.names):
                    if printed:
                        terminal._erase_above(printed)
                    terminal.print(roster)
                    printed = height
                    members = tuple(self.names)
                terminal._redraw_line(
                    Text(f"{spinner[frame % len(spinner)]} ", style=self.theme.accent)
                    .append("等待牌友加入…  ", style=self.theme.fg)
                    .append("Enter 开局 · M 聊天 · Q 关闭", style=self.theme.dim)
                )
                key = await terminal.key(0.15)
                frame += 1
                if key is None:
                    continue
                if key in ("enter", ""):
                    if sum(1 for n in self.names if n is not None) >= 2:
                        terminal._erase_above(printed)
                        await self._play()
                        return
                    terminal._erase_above(printed)
                    terminal.print("[red]至少需要 2 名玩家才能开局（空位开局时由 bot 补齐）。[/red]")
                    await terminal.key(1.5)
                elif key == "q":
                    terminal._erase_above(printed)
                    return
                elif key == "m":
                    terminal._erase_above(printed)
                    text = await terminal.ask("聊天：")
                    if text:
                        await self._say(f"{self.settings.nickname}：{text}")
                    printed = 0
                    members = None
        finally:
            self._lobby = False

    def _save_display(self, display: str) -> None:
        self.settings.display = display
        self.settings.save()

    def _roster(self, ip: str) -> str:
        lines = [f"房间「{self.room_name}」  {ip}:{self.port}"]
        for i, name in enumerate(self.names):
            marker = "●D" if i == 0 else "  "
            lines.append(f" {marker} {name or '（空位，开局由 bot 补齐）'}")
        return "\n".join(lines)

    async def _play(self) -> None:
        self.started = True
        self._adv_task_cancel()
        rng = random.Random()
        names = [n if n is not None else f"{BOT_NAMES[i % len(BOT_NAMES)]}（bot）" for i, n in enumerate(self.names)]
        table = Table(names, [self.settings.starting_stack] * len(names), self.settings.blinds, rng,
                      act_seconds=self.settings.act_seconds)
        console = self.terminal.console
        console.clear()
        screen = GameScreen(
            self.terminal,
            FrameContext(self.theme, self.room_name, self.settings.nickname, self.settings.blinds),
            self.settings.act_seconds,
            display=self.settings.display,
            chat_send=self._say,
            on_display_change=self._save_display,
        )
        self._screen = screen
        await screen.start()
        try:
            actors: dict[int, object] = {0: screen.actor()}
            for i, name in enumerate(names[1:], 1):
                if name.endswith("（bot）"):
                    actors[i] = BotActor(rng)
                else:
                    actors[i] = self._remote_actor(next(c for c in self.conns if c.seat == i))

            async def broadcast(t: Table, result=None) -> None:
                await screen.show(t.seat_view(0), result)
                for conn in list(self.conns):
                    if not conn.alive:
                        continue
                    conn.new_turn()
                    try:
                        await conn.connector.send(State(t.seat_view(conn.seat)))
                        if result is not None:
                            await conn.connector.send(Result(result))
                    except (ConnectionError, OSError):
                        conn.alive = False

            async def publish_result(t: Table) -> None:
                await broadcast(t, t.hand_result)

            options = [Option("下一手"), Option("结束牌局并显示排名")]
            while not table.finished:
                await play_hand(table, actors, broadcast, publish_result)
                choice = await screen.interlude(table.hand_result, "本手结束", options)
                if choice != 0:
                    break
        finally:
            self._screen = None
            await screen.close()
        self._standings(table)

    def _remote_actor(self, conn: _Conn):
        async def actor(view):
            message = await conn.queue.get()
            return Action(message.kind, message.amount)

        return actor

    def _standings(self, table: Table) -> None:
        stacks = sorted(((info.name, info.stack) for info in table.seat_view(None).seats),
                        key=lambda pair: -pair[1])
        lines = Text()
        for place, (name, stack) in enumerate(stacks, 1):
            lines.append(f"第 {place} 名   {name}   {stack:,}\n")
        self.terminal.print(Panel(lines, title="最终排名", border_style=self.theme.gold))

    def _adv_task_cancel(self) -> None:
        if self._adv_task is not None:
            self._adv_task.cancel()

    async def _shutdown(self) -> None:
        self._adv_task_cancel()
        for conn in list(self.conns):
            await conn.connector.close()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()


def _height(text: str) -> int:
    return text.count("\n") + 1


def _lan_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("10.255.255.255", 1))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()
