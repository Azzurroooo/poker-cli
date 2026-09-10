"""Temporary debug: why do two identical renders produce different ANSI?"""
import asyncio
import io

from rich.console import Console

from rpoker.domain.views import SeatInfo, SeatView, Street
from rpoker.ui.prompts import Terminal
from rpoker.ui.render import FrameContext
from rpoker.ui.screen import GameScreen
from rpoker.ui.tokens import THEMES
from tests.engine.helpers import cards

THEME = THEMES["onedark"]


def build_view(pot=30):
    seats = tuple(
        SeatInfo(i, n, 1000 - (10 if i < 2 else 0), 10 if i < 2 else 0, False, False, i == 0)
        for i, n in enumerate(["你", "老周（bot）", "阿棠（bot）"])
    )
    return SeatView(1, Street.PREFLOP, 0, (), pot, seats, cards("Ah Ks"), 1, None, None,
                    ("—— 第 1 手 ——", "你 小盲 10 · 老周（bot） 大盲 10"))


def main() -> None:
    console = Console(file=io.StringIO(), force_terminal=True, width=100, height=40,
                      color_system="truecolor", highlight=False, legacy_windows=False)
    terminal = Terminal(console)
    terminal.tty = True
    screen = GameScreen(terminal, FrameContext(THEME, "本地练习", "你", (5, 10)), 30)

    async def run() -> None:
        await screen.start()
        v1, v2 = build_view(), build_view()
        screen._view = v1
        screen._refresh()
        t1 = screen.frames._last
        screen._view = v2
        screen._refresh()
        t2 = screen.frames._last
        print("equal:", t1 == t2)
        if t1 != t2:
            print("len", len(t1), len(t2))
            for i, (a, b) in enumerate(zip(t1, t2)):
                if a != b:
                    print("first diff at", i)
                    print("t1:", repr(t1[max(0, i - 60):i + 20]))
                    print("t2:", repr(t2[max(0, i - 60):i + 20]))
                    break
            else:
                print("common prefix equal, tail differs")
                print("t1 tail:", repr(t1[min(len(t1), len(t2)) - 1:][:80]))
                print("t2 tail:", repr(t2[min(len(t1), len(t2)) - 1:][:80]))

    asyncio.run(run())


if __name__ == "__main__":
    main()
