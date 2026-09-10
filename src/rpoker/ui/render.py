from __future__ import annotations

from collections.abc import Sequence

from rich.console import Group
from rich.panel import Panel
from rich.table import Table as RichTable
from rich.text import Text

from rpoker.domain.cards import find_best_hand, rank_label
from rpoker.domain.views import SeatInfo, SeatView, Street
from rpoker.engine.table import HandResult
from rpoker.ui.cards import card_text, suit_style
from rpoker.ui.tokens import Theme

STREET_LABELS = {
    Street.WAITING: "等待中",
    Street.PREFLOP: "翻牌前",
    Street.FLOP: "翻牌圈",
    Street.TURN: "转牌圈",
    Street.RIVER: "河牌圈",
    Street.HAND_OVER: "本手结束",
}

_COMMUNITY_SLOTS = {Street.PREFLOP: 0, Street.FLOP: 3, Street.TURN: 4, Street.RIVER: 5, Street.HAND_OVER: 5}


def _fmt(n: int) -> str:
    return f"{n:,}"


def _seat_cell(info: SeatInfo, view: SeatView, viewer: str | None, theme: Theme) -> Text:
    if info.folded and info.stack == 0 and view.street is not Street.HAND_OVER:
        return Text(f"{info.name}（出局）", style=theme.dim)
    is_viewer = viewer is not None and info.name == viewer
    marker = Text()
    if info.is_button:
        marker.append("●D ", style=theme.gold)
    if info.index == view.to_act:
        marker.append("▶ ", style=theme.accent)
    name_style = theme.accent if info.index == view.to_act else theme.fg
    line = marker
    line.append(info.name, style=name_style)
    if is_viewer:
        line.append("（你）", style=theme.dim)
    if info.allin:
        line.append(" 全下", style=theme.bad)
    elif info.folded:
        line.append(" 弃牌", style=theme.dim)
    line.append(f"  {_fmt(info.stack)}")
    if info.street_bet > 0:
        line.append(f"  注 {_fmt(info.street_bet)}", style=theme.gold)
    return line


def _seats_block(view: SeatView, viewer: str | None, theme: Theme) -> RichTable:
    n = len(view.seats)
    order = [(view.button + 1 + i) % n for i in range(n)]
    grid = RichTable.grid(padding=(0, 3))
    for half in range(0, n, 2):
        row = []
        for seat_index in order[half:half + 2]:
            row.append(_seat_cell(view.seats[seat_index], view, viewer, theme))
        if len(row) == 1:
            row.append(Text())
        grid.add_row(*row)
    return grid


def _board(view: SeatView, theme: Theme) -> Text:
    slots = _COMMUNITY_SLOTS[view.street]
    shown: list = list(view.community) + [None] * (slots - len(view.community))
    row = Text()
    for i, card in enumerate(shown):
        if i:
            row.append(" ")
        row += card_text(card, theme)
    row.append(f"   底池 {_fmt(view.pot_total)}", style=theme.gold)
    return row


def _hero_cards(hole: Sequence, theme: Theme) -> Text:
    line = Text()
    for i, card in enumerate(hole):
        if i:
            line.append("  ")
        line.append(f" {rank_label(card.rank)}{card.suit} ", style=f"bold {suit_style(card, theme)}")
    return line


def _log_block(view: SeatView, theme: Theme) -> Text:
    lines = view.log[-7:]
    block = Text()
    for i, entry in enumerate(lines):
        if i:
            block.append("\n")
        style = theme.fg if i == len(lines) - 1 else theme.dim
        block.append(entry, style=style)
    return block


def _result_block(result: HandResult, theme: Theme) -> Panel:
    body = Text()
    for i, award in enumerate(result.awards):
        if i:
            body.append("\n")
        body.append(f"🏆 {award.name} +{_fmt(award.amount)}", style=theme.gold)
        if award.score is not None:
            body.append(f"  {award.score.label()}", style=theme.good)
    if not result.fold_win:
        body.append("\n")
        for name, hole in result.reveal.items():
            body.append(f"\n{name} ").append(
                " ".join(str(c) for c in hole), style=theme.fg
            ).append(f"  用 {result.best[name]}", style=theme.dim)
    return Panel(body, title="本手结算", border_style=theme.gold)


def render(view: SeatView, theme: Theme, result: HandResult | None = None, title: str = "牌局", viewer: str | None = None) -> Group:
    parts: list = []
    header = Text()
    header.append("♠ ♥ ♦ ♣ ", style=theme.accent)
    header.append(f"{title} · 第 {_fmt(view.hand_no)} 手 · {STREET_LABELS[view.street]}", style=theme.fg)
    parts.append(header)
    parts.append(Text())
    parts.append(_seats_block(view, viewer, theme))
    parts.append(Text())
    parts.append(_board(view, theme))
    if view.hole:
        parts.append(Text())
        parts.append(Text("你的手牌", style=theme.dim))
        parts.append(_hero_cards(view.hole, theme))
        if len(view.community) >= 3:
            parts.append(Text(find_best_hand((*view.hole, *view.community)).label(), style=theme.dim))
    parts.append(Text())
    parts.append(_log_block(view, theme))
    if result is not None:
        parts.append(Text())
        parts.append(_result_block(result, theme))
    return Group(*parts)
