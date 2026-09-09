from __future__ import annotations

from collections.abc import Sequence

from rich.text import Text

from rpoker.domain.cards import Card, rank_label
from rpoker.ui.tokens import Theme, suit_color

_BORDER = "─"


def card_text(card: Card | None, theme: Theme) -> Text:
    if card is None:
        return Text("[▓▓]", style=theme.dim)
    color = suit_color(card.suit, theme)
    return Text(f"[{rank_label(card.rank)}{card.suit}]", style=color)


def cards_row(cards: Sequence[Card | None], theme: Theme) -> Text:
    row = Text()
    for i, card in enumerate(cards):
        if i:
            row.append(" ")
        row += card_text(card, theme)
    return row


def big_card_lines(cards: Sequence[Card], theme: Theme) -> list[Text]:
    line = Text()
    for i, card in enumerate(cards):
        if i:
            line.append("  ")
        color = suit_color(card.suit, theme)
        line.append(f" {rank_label(card.rank)}{card.suit} ", style=f"bold {color}")
    return [line]


def back_lines(count: int, theme: Theme) -> list[Text]:
    top = Text(style=theme.dim)
    body = Text(style=theme.dim)
    bottom = Text(style=theme.dim)
    for _ in range(count):
        top.append("╭────╮ ")
        body.append("│ ▓▓▓▓ │ ")
        bottom.append("╰────╯ ")
    return [top, body, bottom]
