from __future__ import annotations

import getpass

from rich.text import Text

from rpoker.app import client, local, room
from rpoker.app.settings import Settings
from rpoker.net import beacon
from rpoker.net.messages import TCP_PORT
from rpoker.ui.prompts import Option, Terminal
from rpoker.ui.tokens import THEMES

BANNER = """
██████╗  ██████╗ ██╗  ██╗███████╗██████╗        ██████╗██╗     ██╗
██╔══██╗██╔═══██╗██║ ██╔╝██╔════╝██╔══██╗      ██╔════╝██║     ██║
██████╔╝██║   ██║█████╔╝ █████╗  ██████╔╝█████╗██║     ██║     ██║
██╔═══╝ ██║   ██║██╔═██╗ ██╔══╝  ██╔══██╗╚════╝██║     ██║     ██║
██║     ╚██████╔╝██║  ██╗███████╗██║  ██║      ╚██████╗███████╗██║
╚═╝      ╚═════╝ ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝       ╚═════╝╚══════╝╚═╝
"""

BLIND_CHOICES = [(2, 5), (5, 10), (10, 25), (25, 50), (50, 100)]


async def run(terminal: Terminal, settings: Settings) -> None:
    console = terminal.console
    console.print(Text(BANNER, style="bold cyan"))
    if not settings.nickname:
        settings.nickname = await terminal.ask("你的昵称", getpass.getuser() or "玩家")
        settings.save()
    while True:
        choice = await terminal.menu(
            f"你好，{settings.nickname}！今天想玩点什么？",
            [
                Option("创建房间（局域网牌友可直接看到并加入）"),
                Option("加入房间（自动发现局域网房间）"),
                Option("本地练习（对 3 个 bot）"),
                Option("主题与设置"),
                Option("退出"),
            ],
            cancellable=False,
        )
        match choice:
            case 0:
                await _create(terminal, settings)
            case 1:
                await _join(terminal, settings)
            case 2:
                await local.run_local(terminal, settings.nickname, settings)
            case 3:
                await _settings_menu(terminal, settings)
            case 4:
                return


async def _create(terminal: Terminal, settings: Settings) -> None:
    room_name = await terminal.ask("房间名", f"{settings.nickname}的牌局")
    if not room_name:
        return
    table_size = await _pick_number(terminal, "桌子人数（空位由 bot 补齐）", [2, 3, 4, 5, 6, 7, 8, 9], settings.table_size)
    blinds = await _pick_blinds(terminal, settings)
    if table_size is None or blinds is None:
        return
    settings.table_size = table_size
    settings.blinds = blinds
    settings.save()
    console = terminal.console
    console.clear()
    await room.Room(terminal, settings, room_name).run()


async def _join(terminal: Terminal, settings: Settings) -> None:
    console = terminal.console
    console.print("[dim]正在扫描局域网房间…[/dim]")
    rooms = [r for r in await beacon.discover(3.0) if not r.full and not r.in_hand]
    options = [
        Option(f"{r.name}  [dim]{r.ip} · {r.seats}/{r.max_seats} 人 · 等待中[/dim]")
        for r in rooms
    ]
    options.append(Option("手动输入 IP 加入"))
    choice = await terminal.menu("选择要加入的房间", options)
    if choice is None:
        return
    if choice == len(rooms):
        address = await terminal.ask("房间地址（IP:端口）")
        if not address:
            return
        ip, _, port_text = address.partition(":")
        port = int(port_text) if port_text.isdigit() else TCP_PORT
        console.clear()
        await client.join_room(terminal, settings, ip, port)
        return
    target = rooms[choice]
    console.clear()
    await client.join_room(terminal, settings, target.ip, target.port)


async def _pick_blinds(terminal: Terminal, settings: Settings) -> tuple[int, int] | None:
    choice = await terminal.menu(
        "选择盲注",
        [Option(f"{sb}/{bb}", hint="（当前）" if (sb, bb) == settings.blinds else "") for sb, bb in BLIND_CHOICES],
    )
    return None if choice is None else BLIND_CHOICES[choice]


async def _pick_number(terminal: Terminal, title: str, values: list[int], current: int) -> int | None:
    choice = await terminal.menu(title, [Option(str(v), hint="（当前）" if v == current else "") for v in values])
    return None if choice is None else values[choice]


async def _settings_menu(terminal: Terminal, settings: Settings) -> None:
    choice = await terminal.menu("设置", [Option("主题"), Option("展示形式（丰富 / 简单）")])
    if choice == 0:
        names = list(THEMES)
        theme_choice = await terminal.menu("选择主题", [Option(name) for name in names])
        if theme_choice is not None:
            settings.theme = names[theme_choice]
            settings.save()
            terminal.print(f"主题已切换为 {settings.theme}")
    elif choice == 1:
        modes = [("rich", "丰富（卡牌与座位盒完整呈现）"), ("simple", "简单（紧凑文本，信息不减）")]
        mode_choice = await terminal.menu(
            "选择展示形式",
            [Option(label, hint="（当前）" if settings.display == value else "") for value, label in modes],
        )
        if mode_choice is not None:
            settings.display = modes[mode_choice][0]
            settings.save()
            terminal.print(f"展示形式已切换为 {settings.display}")
