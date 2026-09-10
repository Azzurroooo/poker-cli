"""UI showcase: render every card, seat and frame state from fixed samples.

Run: uv run python -m rpoker.ui.showcase
"""
from __future__ import annotations

from rich.console import Console
from rich.text import Text

from rpoker.domain.actions import LegalActions
from rpoker.domain.cards import Card, Suit
from rpoker.domain.views import SeatInfo, SeatView, Street
from rpoker.ui.cards import MINI, STANDARD, WIDE, card_lines, cards_row, parse_card
from rpoker.ui.panels import ActionPanel
from rpoker.ui.render import FrameContext, UiState, rich_frame, simple_frame
from rpoker.ui.tokens import THEMES

SAMPLES = ["A♠", "K♥", "Q♦", "J♣", "10♠", "7♥", "2♦"]


def cards(spec: str) -> tuple[Card, ...]:
    ranks = {**{str(r): r for r in range(2, 10)}, "10": 10, "J": 11, "Q": 12, "K": 13, "A": 14}
    suits = {"c": Suit.CLUBS, "d": Suit.DIAMONDS, "h": Suit.HEARTS, "s": Suit.SPADES}
    return tuple(Card(ranks[token[:-1]], suits[token[-1]]) for token in spec.split())


def _print_card_rows(console: Console, size: tuple[int, int], theme, state: str, chunk: int) -> None:
    samples = [None] if state == "hidden" else [parse_card(s) for s in SAMPLES]
    lines = [card_lines(card, size, theme, state) for card in samples]
    for start in range(0, len(lines), chunk):
        for row in range(size[1]):
            line = Text()
            for i, card in enumerate(lines[start:start + chunk]):
                if i:
                    line.append("  ")
                line += card[row]
            console.print(line)


def show_cards(console: Console) -> None:
    for theme_name, theme in THEMES.items():
        console.print(f"[bold]{theme_name}[/bold]")
        for label, size, chunk in (("wide 11x9", WIDE, 5), ("standard 6x5", STANDARD, 7), ("mini 5x4", MINI, 7)):
            console.print(f"  [dim]{label}[/dim]")
            for state in ("normal", "winning", "dim", "hidden"):
                _print_card_rows(console, size, theme, state, chunk)
        console.print(f"  [dim]inline[/dim]  {cards_row([parse_card(s) for s in SAMPLES], theme)}"
                      f"   [dim]back[/dim]  {cards_row([None], theme)}")
        console.print()


def sample_view() -> SeatView:
    names = ["你", "老周", "阿棠", "石头", "绵绵"]
    seats = tuple(
        SeatInfo(i, n, 1000 - (40 if i == 0 else 0), 40 if i == 0 else (20 if i == 2 else 0),
                 i == 3, i == 2, i == 1)
        for i, n in enumerate(names)
    )
    return SeatView(7, Street.FLOP, 1, cards("Qd 2h Js"), 365, seats, cards("Ah As"), 0,
                    LegalActions(False, 40, 80, 960), None,
                    ("—— 第 7 手 ——", "老周 小盲 5 · 阿棠 大盲 10", "你 加注至 40", "阿棠 跟注 40",
                     "石头 弃牌", "—— flop Q♦ 2♥ J♠", "阿棠 过牌"))


def show_frames(console: Console) -> None:
    theme = THEMES["onedark"]
    ctx = FrameContext(theme, "测试房", "你", (5, 10))
    view = sample_view()
    acting = UiState(panel=ActionPanel.build(view.legal), countdown=21)
    raising = UiState(panel=ActionPanel.build(view.legal), countdown=21)
    raising.panel.handle("r", view.pot_total)
    console.print("[bold]rich frame · acting (100x34)[/bold]")
    console.print(rich_frame(view, acting, ctx, 100, 34))
    console.print()
    console.print("[bold]rich frame · raising slider[/bold]")
    console.print(rich_frame(view, raising, ctx, 100, 34))
    console.print()
    console.print("[bold]rich frame · compact (80x24)[/bold]")
    console.print(rich_frame(view, acting, ctx, 80, 24))
    console.print()
    console.print("[bold]simple frame (80)[/bold]")
    console.print(simple_frame(view, acting, ctx, 80))
    console.print()


def main() -> None:
    console = Console(highlight=False)
    console.print("[bold reverse] rpoker UI showcase [/bold reverse]")
    console.print()
    show_cards(console)
    show_frames(console)


if __name__ == "__main__":
    main()
