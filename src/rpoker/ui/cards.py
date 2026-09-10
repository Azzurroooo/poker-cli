from __future__ import annotations

from collections.abc import Sequence

from rich.text import Text

from rpoker.domain.cards import Card, Suit, rank_label
from rpoker.ui.tokens import Theme

LABEL_RANK = {"10": 10, "J": 11, "Q": 12, "K": 13, "A": 14}

# Card ladder: (total width, total height) including the 1-cell border ring.
# wide serves the hero hand, standard the board and compact hero hand,
# mini reveal cards and tight boards; inline is the 4-cell log/pipe form.
WIDE = (11, 9)
STANDARD = (6, 5)
MINI = (5, 4)

NORMAL, DIM, WINNING, HIDDEN = "normal", "dim", "winning", "hidden"

# Pip positions for ranks 2-10 on the wide card: (row 0-4, column L/C/R)
# mapped onto content rows 1-5 with columns 2/4/6 of the 9-cell interior.
_PIPS: dict[int, tuple[tuple[int, str], ...]] = {
    2: ((0, "C"), (4, "C")),
    3: ((0, "C"), (2, "C"), (4, "C")),
    4: ((0, "L"), (0, "R"), (4, "L"), (4, "R")),
    5: ((0, "L"), (0, "R"), (2, "C"), (4, "L"), (4, "R")),
    6: ((0, "L"), (0, "R"), (2, "L"), (2, "R"), (4, "L"), (4, "R")),
    7: ((0, "L"), (0, "R"), (2, "L"), (2, "R"), (3, "C"), (4, "L"), (4, "R")),
    8: ((0, "L"), (0, "R"), (1, "C"), (2, "L"), (2, "R"), (3, "C"), (4, "L"), (4, "R")),
    9: ((0, "L"), (0, "C"), (0, "R"), (2, "L"), (2, "C"), (2, "R"), (4, "L"), (4, "C"), (4, "R")),
    10: ((0, "L"), (0, "C"), (0, "R"), (1, "C"), (2, "L"), (2, "R"), (3, "C"), (4, "L"), (4, "C"), (4, "R")),
}
_PIP_COLUMN = {"L": 2, "C": 4, "R": 6}
_SHADE = "░▒▓█▓▒"


def card_text(card: Card | None, theme: Theme, state: str = NORMAL) -> Text:
    if card is None:
        return Text("[▓▓]", style=theme.dim)
    return Text(f"[{rank_label(card.rank)}{card.suit}]", style=suit_style(card, theme, state))


def cards_row(cards: Sequence[Card | None], theme: Theme) -> Text:
    row = Text()
    for i, card in enumerate(cards):
        if i:
            row.append(" ")
        row += card_text(card, theme)
    return row


def card_lines(card: Card | None, size: tuple[int, int], theme: Theme, state: str = NORMAL) -> list[Text]:
    width, height = size
    inner = width - 2
    if card is None or state == HIDDEN:
        style, body = theme.dim, _shade_rows(inner, height - 2)
    else:
        style = suit_style(card, theme, state)
        body = _face_rows(card, inner, height - 2)
    top = Text("╭" + "─" * inner + "╮", style=style)
    bottom = Text("╰" + "─" * inner + "╯", style=style)
    return [top, *(Text("│" + row + "│", style=style) for row in body), bottom]


def parse_card(text: str) -> Card:
    rank = LABEL_RANK.get(text[:-1]) or int(text[:-1])
    return Card(rank, Suit(text[-1]))


def suit_style(card: Card, theme: Theme, state: str = NORMAL) -> str:
    if state == WINNING:
        return theme.gold
    if state == DIM:
        return theme.dim
    return {"♣": theme.club, "♦": theme.diamond, "♥": theme.heart, "♠": theme.spade}[card.suit]


def _face_rows(card: Card, inner: int, rows: int) -> list[str]:
    label = rank_label(card.rank)
    if inner >= 9:
        return _face_rows_wide(card, label, inner, rows)
    if inner >= 4:
        return _face_rows_standard(card, label, inner)
    return _face_rows_mini(card, label, inner)


def _face_rows_wide(card: Card, label: str, inner: int, rows: int) -> list[str]:
    suit = card.suit.value
    grid = [[" "] * inner for _ in range(rows)]
    _place(grid[0], 0, f"{label}{suit}")
    _place(grid[-1], inner - len(label), label)
    if card.rank == 14 or card.rank >= 11:
        _center(grid[rows // 2], suit)
    else:
        for row, column in _PIPS[card.rank]:
            grid[row + 1][_PIP_COLUMN[column]] = suit
    return ["".join(row) for row in grid]


def _face_rows_standard(card: Card, label: str, inner: int) -> list[str]:
    suit = card.suit.value
    top = [" "] * inner
    _place(top, 0, f"{label}{suit}")
    mid = [" "] * inner
    _center(mid, suit)
    bottom = [" "] * inner
    _place(bottom, inner - len(label) - 1, f"{suit}{label}")
    return ["".join(top), "".join(mid), "".join(bottom)]


def _face_rows_mini(card: Card, label: str, inner: int) -> list[str]:
    top = [" "] * inner
    _center(top, label)
    bottom = [" "] * inner
    _center(bottom, card.suit.value)
    return ["".join(top), "".join(bottom)]


def _place(row: list[str], start: int, text: str) -> None:
    row[start:start + len(text)] = list(text)


def _center(row: list[str], text: str) -> None:
    _place(row, (len(row) - len(text)) // 2, text)


def _shade_rows(inner: int, rows: int) -> list[str]:
    return ["".join(_SHADE[(r + c) % len(_SHADE)] for c in range(inner)) for r in range(rows)]
