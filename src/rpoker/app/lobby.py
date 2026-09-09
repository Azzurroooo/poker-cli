from __future__ import annotations

import getpass

from rich.text import Text

from rpoker.app import local
from rpoker.app.settings import Settings
from rpoker.ui.prompts import Option, Terminal
from rpoker.ui.tokens import THEMES

BANNER = """
██████╗ ███████╗ █████╗ ██╗     ██████╗  ██████╗ ██╗  ██╗███████╗██████╗
██╔══██╗██╔════╝██╔══██╗██║     ██╔══██╗██╔═══██╗██║ ██╔╝██╔════╝██╔══██╗
██████╔╝█████╗  ███████║██║     ██████╔╝██║   ██║█████╔╝ █████╗  ██████╔╝
██╔══██╗██╔══╝  ██╔══██║██║     ██╔══██╗██║   ██║██╔═██╗ ██╔══╝  ██╔═══╝
██║  ██║███████╗██║  ██║███████╗██║  ██║╚██████╔╝██║  ██╗███████╗██║
╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝╚══════╝╚═╝
"""


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
                Option("创建房间（局域网牌友加入）", hint="即将开放"),
                Option("加入房间（自动发现）", hint="即将开放"),
                Option("本地练习（对 3 个 bot）"),
                Option("主题与设置"),
                Option("退出"),
            ],
            cancellable=False,
        )
        match choice:
            case 0:
                console.print("[dim]房间功能将在下一版本开放，先试试本地练习吧。[/dim]")
            case 1:
                console.print("[dim]房间功能将在下一版本开放，先试试本地练习吧。[/dim]")
            case 2:
                await local.run_local(terminal, settings.nickname, settings)
            case 3:
                await _settings_menu(terminal, settings)
            case 4:
                return


async def _settings_menu(terminal: Terminal, settings: Settings) -> None:
    names = list(THEMES)
    choice = await terminal.menu("选择主题", [Option(name) for name in names])
    if choice is not None:
        settings.theme = names[choice]
        settings.save()
        terminal.print(f"主题已切换为 {settings.theme}")
