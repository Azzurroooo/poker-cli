"""UI showcase: render every card, seat and frame state from fixed samples.

Run: uv run python -m rpoker.ui.showcase
"""
from __future__ import annotations

from rich.console import Console
from rich.text import Text

from rpoker.ui.cards import MINI, STANDARD, WIDE, card_lines, cards_row, parse_card
from rpoker.ui.tokens import THEMES

SAMPLES = ["A♠", "K♥", "Q♦", "J♣", "10♠", "7♥", "2♦"]


def show_cards(console: Console) -> None:
    for theme_name, theme in THEMES.items():
        console.print(f"[bold]{theme_name}[/bold]")
        for label, size, chunk in (("wide 11x9", WIDE, 5), ("standard 6x5", STANDARD, 7), ("mini 5x4", MINI, 7)):
            console.print(f"  [dim]{label}[/dim]")
            for state in ("normal", "winning", "dim", "hidden"):
                _print_row(console, size, theme, state, chunk)
        console.print(f"  [dim]inline[/dim]  {cards_row([parse_card(s) for s in SAMPLES], theme)}"
                      f"   [dim]back[/dim]  {cards_row([None], theme)}")
        console.print()


def _print_row(console: Console, size: tuple[int, int], theme, state: str, chunk: int) -> None:
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


def main() -> None:
    console = Console(highlight=False)
    console.print("[bold reverse] rpoker UI showcase [/bold reverse]")
    console.print()
    show_cards(console)


if __name__ == "__main__":
    main()
