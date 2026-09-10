from __future__ import annotations

from dataclasses import dataclass

from rich.console import Group
from rich.panel import Panel
from rich.table import Table as RichTable
from rich.text import Text

from rpoker.domain.cards import find_best_hand, rank_label
from rpoker.domain.views import SeatInfo, SeatView, Street
from rpoker.engine.table import HandResult
from rpoker.ui.cards import card_text, suit_style
from rpoker.ui.panels import ActionPanel
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

_LOG_LINES = 4
_GAUGE_CELLS = 10
_SLIDER_CELLS = 16


@dataclass(frozen=True, slots=True)
class FrameContext:
    theme: Theme
    title: str
    viewer: str | None
    blinds: tuple[int, int]


@dataclass(frozen=True, slots=True)
class UiState:
    panel: ActionPanel | None = None
    countdown: int | None = None
    confirm_quit: bool = False
    chat: tuple[str, ...] = ()


def simple_frame(view: SeatView, result: HandResult | None, ui: UiState, ctx: FrameContext) -> Group:
    theme = ctx.theme
    parts: list = [
        _header(view, ctx),
        Text(),
        _seats_block(view, ctx.viewer, theme),
        Text(),
        _board(view, theme),
        Text(),
        *_hole_block(view, theme),
        Text(),
        _log_block(view, ui.chat, theme),
        _action_slot(view, ui, ctx),
        _keybar(theme),
    ]
    return Group(*parts)


def interlude_summary(result: HandResult, theme: Theme) -> Panel:
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


def _fmt(n: int) -> str:
    return f"{n:,}"


def _header(view: SeatView, ctx: FrameContext) -> Text:
    header = Text()
    header.append("♠ ♥ ♦ ♣ ", style=ctx.theme.accent)
    header.append(f"{ctx.title} · 第 {_fmt(view.hand_no)} 手 · {STREET_LABELS[view.street]}"
                  f" · 盲注 {ctx.blinds[0]}/{ctx.blinds[1]}", style=ctx.theme.fg)
    return header


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


def _hole_block(view: SeatView, theme: Theme) -> list:
    if not view.hole:
        return [Text(), Text(), Text()]
    cards = Text()
    for i, card in enumerate(view.hole):
        if i:
            cards.append("  ")
        cards.append(f" {rank_label(card.rank)}{card.suit} ", style=f"bold {suit_style(card, theme)}")
    label = Text("你的手牌", style=theme.dim)
    if len(view.community) >= 3:
        mine = Text(find_best_hand((*view.hole, *view.community)).label(), style=theme.dim)
    else:
        mine = Text()
    return [label, cards, mine]


def _log_block(view: SeatView, chat: tuple[str, ...], theme: Theme) -> Text:
    entries = [*view.log, *chat]
    lines = entries[-_LOG_LINES:]
    block = Text()
    for i, entry in enumerate(lines):
        if i:
            block.append("\n")
        style = theme.fg if i == len(lines) - 1 else theme.dim
        block.append(entry, style=style)
    return block


def _action_slot(view: SeatView, ui: UiState, ctx: FrameContext) -> Text:
    theme = ctx.theme
    if ui.confirm_quit:
        return Text("再按 Enter / Ctrl-C 确认退出 · Esc 取消", style=theme.bad)
    if ui.panel is not None:
        return _panel_slot(ui.panel, ui.countdown, theme)
    if view.to_act is not None:
        return Text(f"等待 {view.seats[view.to_act].name} 行动…", style=theme.dim)
    return Text()


def _panel_slot(panel: ActionPanel, countdown: int | None, theme: Theme) -> Text:
    line = Text()
    if panel.raising:
        low, high = panel.legal.min_raise_to, panel.legal.max_raise_to
        span = max(high - low, 1)
        filled = round((panel.amount - low) / span * _SLIDER_CELLS)
        line.append("加注至 ", style=theme.fg)
        line.append(f"{panel.amount:,}", style=theme.gold)
        line.append(" ◀" + "━" * filled + "●" + "━" * (_SLIDER_CELLS - filled) + "▶ ", style=theme.dim)
        line.append(f"{high:,}", style=theme.dim)
        line.append("  1最小 2半池 3满池 4全下 · Enter 确认 · Esc 返回", style=theme.dim)
    else:
        for i, item in enumerate(panel.items()):
            if i:
                line.append("  ")
            if i == panel.selected:
                line.append("▸ ", style=theme.accent)
            line.append(f"[{item.hotkey}]", style=theme.accent)
            line.append(f" {item.label}", style=theme.fg)
    if countdown is not None:
        filled = min(countdown // 3, _GAUGE_CELLS)
        gauge = "█" * filled + "░" * (_GAUGE_CELLS - filled)
        line.append(f"  {gauge} {countdown}s", style=theme.bad if countdown <= 5 else theme.dim)
    return line


def _keybar(theme: Theme) -> Text:
    return Text("Ctrl-C 退出", style=theme.dim)
