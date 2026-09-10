from __future__ import annotations

from dataclasses import dataclass

from rich.align import Align
from rich.box import ROUNDED
from rich.cells import cell_len
from rich.console import Group
from rich.panel import Panel
from rich.table import Table as RichTable
from rich.text import Text

from rpoker.domain.cards import find_best_hand, rank_label
from rpoker.domain.views import SeatInfo, SeatView, Street
from rpoker.engine.table import HandResult
from rpoker.ui.cards import MINI, STANDARD, WIDE, card_lines, card_text, suit_style
from rpoker.ui.layout import (
    Budget,
    Tier,
    rich_budget,
    rich_tier,
    seat_box_width,
    seat_order,
)
from rpoker.ui.panels import ActionPanel
from rpoker.ui.tokens import SYMBOLS, Theme

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
    notice: str | None = None


def simple_frame(view: SeatView, ui: UiState, ctx: FrameContext) -> Group:
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


def rich_frame(view: SeatView, ui: UiState, ctx: FrameContext, width: int, height: int) -> Group:
    tier = rich_tier(width, height)
    budget = rich_budget(tier, len(view.seats))
    lines = [
        *_header_slot(view, ui, ctx, budget),
        *_seats_slot(view, ctx, tier, width, budget),
        *_community_slot(view, ctx, tier, budget),
        *_hero_slot(view, ctx, tier, budget),
        *_log_slot(view, ui, ctx, budget),
        *_action_rich_slot(view, ui, ctx, budget),
        *_keybar_slot(ui, ctx, budget),
    ]
    return Group(*lines)


def _header_slot(view: SeatView, ui: UiState, ctx: FrameContext, budget: Budget) -> list:
    line = _header(view, ctx)
    if ui.notice:
        line.append("  ")
        line.append(ui.notice, style=ctx.theme.accent)
    return [line]


def _anchor(view: SeatView, ctx: FrameContext) -> int:
    if ctx.viewer is not None:
        for info in view.seats:
            if info.name == ctx.viewer:
                return info.index
    return view.button


def _seats_slot(view: SeatView, ctx: FrameContext, tier: Tier, width: int, budget: Budget) -> list:
    theme = ctx.theme
    n = len(view.seats)
    boxed = n <= 6 and tier is not Tier.COMPACT
    order = seat_order(n, _anchor(view, ctx))
    if not boxed:
        cells = [_seat_cell(view.seats[i], view, ctx.viewer, theme) for i in order]
        rows = []
        for half in range(0, n, 2):
            pair = cells[half:half + 2]
            if len(pair) == 1:
                pair.append(Text())
            rows.append(Text("   ").join(pair))
        return [*rows, *[Text()] * (budget.seats - len(rows))]
    box_w = seat_box_width([info.name for info in view.seats], width, boxed=True)
    boxes = [_seat_box(view.seats[i], view, ctx, box_w) for i in order]
    rows = []
    for half in range(0, len(boxes), 2):
        pair = boxes[half:half + 2]
        if len(pair) == 1:
            pair = _blank_box(box_w, theme), pair[0]
        for row in range(3):
            line = Text()
            for j, box in enumerate(pair):
                if j:
                    line.append("  ")
                line += box[row]
            rows.append(line)
    return [*rows, *[Text()] * (budget.seats - len(rows))]


def _seat_box(info: SeatInfo, view: SeatView, ctx: FrameContext, w: int) -> list[Text]:
    theme = ctx.theme
    inner = w - 2
    is_viewer = ctx.viewer is not None and info.name == ctx.viewer
    acting = info.index == view.to_act
    out = info.folded and info.stack == 0 and view.street is not Street.HAND_OVER
    folded = info.folded and not out
    left = Text()
    if is_viewer:
        left.append(f"{SYMBOLS['hero']} ", style=theme.accent)
    elif acting:
        left.append(f"{SYMBOLS['to_act']} ", style=theme.accent)
    if info.is_button:
        left.append(f"{SYMBOLS['button']} ", style=theme.gold)
    if out:
        left.append(_fit(f"{info.name}（出局）", inner), style=theme.dim)
        body = left
    else:
        status = ""
        if info.allin:
            status = " 全下"
        elif folded:
            status = " 弃牌"
        right_w = len(f"{info.stack:,}") + (len(status) if status else 0) + 2
        name_style = theme.dim if folded else theme.fg
        name = _fit(info.name, max(inner - visible(left) - right_w - 1, 4))
        left.append(name, style=f"strike {theme.dim}" if folded else name_style)
        body = left
        body.append("  ", style=theme.dim)
        body.append(f"{info.stack:,}", style=theme.gold if info.allin else theme.fg)
        if info.street_bet > 0:
            body.append(f" 注{info.street_bet}", style=theme.gold)
        if status:
            body.append(status, style=theme.bad if info.allin else theme.dim)
    top_style = theme.accent if (acting or is_viewer) else theme.gold if info.allin else theme.dim if (folded or out) else theme.border
    if acting or is_viewer:
        top, bottom = f"╭{'─' * inner}╮", f"╰{'─' * inner}╯"
    else:
        top, bottom = f"┌{'─' * inner}┐", f"└{'─' * inner}┘"
    return [Text(top, style=top_style), _pad_line(body, inner), Text(bottom, style=top_style)]


def _pad_line(line: Text, inner: int) -> Text:
    line.append(" " * max(inner - visible(line), 0))
    return line


def _blank_box(w: int, theme: Theme) -> list[Text]:
    inner = w - 2
    blank = Text(" " * inner)
    return [Text(f"┌{'─' * inner}┐", style=theme.border), blank, Text(f"└{'─' * inner}┘", style=theme.border)]


def visible(line: Text) -> int:
    return cell_len(line.plain)


def _fit(text: str, width: int) -> str:
    if cell_len(text) <= width:
        return text
    return text[:max(width - 1, 0)] + "…"


def _community_slot(view: SeatView, ctx: FrameContext, tier: Tier, budget: Budget) -> list:
    theme = ctx.theme
    slots = _COMMUNITY_SLOTS[view.street]
    shown: list = list(view.community) + [None] * (slots - len(view.community))
    if tier is Tier.COMPACT:
        lines = [card_lines(card, MINI, theme) for card in shown]
        rows = []
        for row in range(MINI[1]):
            line = Text()
            for i, card in enumerate(lines):
                if i:
                    line.append(" ")
                line += card[row]
            if row == 1:
                line.append(f"  底池 {_fmt(view.pot_total)}", style=theme.gold)
            rows.append(line)
        return rows
    card_rows = []
    for row in range(STANDARD[1]):
        line = Text()
        for i, card in enumerate([card_lines(card, STANDARD, theme) for card in shown]):
            if i:
                line.append(" ")
            line += card[row]
        card_rows.append(line)
    panel = Panel(
        Group(*card_rows),
        title=f"底池 {_fmt(view.pot_total)}",
        title_align="center",
        border_style=theme.border,
        box=ROUNDED,
        expand=False,
        padding=0,
    )
    return [Align.center(panel), *[Text()] * (budget.community - 7)]


def _hero_slot(view: SeatView, ctx: FrameContext, tier: Tier, budget: Budget) -> list:
    theme = ctx.theme
    if not view.hole:
        return [Text()] * budget.hero
    size = WIDE if tier is Tier.WIDE else STANDARD
    lines = [card_lines(card, size, theme) for card in view.hole]
    rows = []
    for row in range(size[1]):
        line = Text()
        for i, card in enumerate(lines):
            if i:
                line.append("   ")
            line += card[row]
        rows.append(line)
    if len(view.community) >= 3:
        rows.append(Text(find_best_hand((*view.hole, *view.community)).label(), style=theme.dim))
    else:
        rows.append(Text())
    return [Align.center(Group(*rows)), *[Text()] * (budget.hero - len(rows))]


def _log_slot(view: SeatView, ui: UiState, ctx: FrameContext, budget: Budget) -> list:
    theme = ctx.theme
    entries = [*view.log, *ui.chat]
    lines = entries[-budget.log:]
    block = Text()
    for i, entry in enumerate(lines):
        if i:
            block.append("\n")
        style = theme.fg if i == len(lines) - 1 else theme.dim
        block.append(entry, style=style)
    return [block, *[Text()] * (budget.log - len(lines))]


def _action_rich_slot(view: SeatView, ui: UiState, ctx: FrameContext, budget: Budget) -> list:
    theme = ctx.theme
    if ui.confirm_quit:
        body = Text("再按 Enter / Ctrl-C 确认退出 · Esc 取消", style=theme.bad)
        title = "退出"
        border = theme.bad
    elif ui.panel is not None:
        body = _panel_lines(ui.panel, ui.countdown, theme)
        title = "你的行动"
        border = theme.accent
    else:
        waiting = view.seats[view.to_act].name if view.to_act is not None else ""
        body = Text(f"{SYMBOLS['to_act']} {waiting} 行动中…", style=theme.dim)
        title = "等待"
        border = theme.border
    panel = Panel(
        body if isinstance(body, Text) else Group(*body),
        title=title,
        border_style=border,
        box=ROUNDED,
        expand=False,
        padding=(0, 2),
    )
    return [Align.left(panel), *[Text()] * (budget.action - 4)]


def _panel_lines(panel: ActionPanel, countdown: int | None, theme: Theme) -> list[Text]:
    row1 = _panel_slot(panel, None, theme)
    row2 = Text(style=theme.dim)
    if panel.raising:
        row2.append("←→ 调额 · 1-4 档位 · Enter 确认 · Esc 返回")
    else:
        row2.append("↑↓ 选择 · Enter 确认")
    if countdown is not None:
        filled = min(countdown // 3, _GAUGE_CELLS)
        gauge = "█" * filled + "░" * (_GAUGE_CELLS - filled)
        row2.append(f"  {gauge} {countdown}s", style=theme.bad if countdown <= 5 else theme.dim)
    return [row1, row2]


def _keybar_slot(ui: UiState, ctx: FrameContext, budget: Budget) -> list:
    return [_keybar(ctx.theme)]
