from __future__ import annotations

import asyncio
import sys

from rich.console import Console

from rpoker.app import lobby
from rpoker.app.settings import Settings
from rpoker.ui.prompts import QuitApp, Terminal


def main() -> None:
    console = Console(highlight=False)
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        console.print("[yellow]提示：当前控制台编码不是 UTF-8，牌面符号可能乱码。")
        console.print("[yellow]建议执行 chcp 65001 或改用 Windows Terminal 后再运行。")
        console.print()
    settings = Settings.load()
    terminal = Terminal(console)
    try:
        asyncio.run(lobby.run(terminal, settings))
    except (KeyboardInterrupt, QuitApp):
        pass
    finally:
        terminal.close()
        console.print("再见，下次再来！")


if __name__ == "__main__":
    main()
