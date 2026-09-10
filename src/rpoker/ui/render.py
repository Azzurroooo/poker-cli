from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from rich.cells import cell_len
from rich.panel import Panel
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
def _blank() -> Text:
    return Text(" ")


@dataclass(frozen=True, slots=True)
class FrameContext:
    theme: Theme
    title: str
    viewer: str | None
    blinds: tuple[int, int]
    act_seconds: float = 30.0


@dataclass(frozen=True, slots=True)
class OverlayState:
    kind: str  # "history" | "help"
    scroll: int


@dataclass(frozen=True, slots=True)
class UiState:
    panel: ActionPanel | None = None
    countdown: int | None = None
    confirm_quit: bool = False
    chat: tuple[str, ...] = ()
    notice: str | None = None
    overlay: OverlayState | None = None
    draft: str | None = None


def simple_frame(view: SeatView, ui: UiState, ctx: FrameContext, width: int) -> Text:
    theme = ctx.theme
    rows = (len(view.seats) + 1) // 2
    lines = [
        _header(view, ui, ctx),
        _blank(),
        *_seats_lines(view, ctx, width, rows),
        _blank(),
        _board_line(view, theme),
        _blank(),
        *_hole_lines(view, theme),
        _blank(),
        *_log_lines(view, ui.chat, theme, _LOG_LINES),
        _action_line_slot(view, ui, ctx),
        _keybar(ui, theme),
    ]
    return _join(lines, width)


def rich_frame(view: SeatView, ui: UiState, ctx: FrameContext, width: int, height: int) -> Text:
    tier = rich_tier(width, height)
    budget = rich_budget(tier, len(view.seats))
    theme = ctx.theme
    mid_budget = budget.seats + budget.community + budget.hero
    if ui.overlay is not None:
        mid = _overlay_lines(view, ui, ctx, mid_budget, width)
    else:
        mid = [
            *_seats_box_lines(view, ui, ctx, tier, width, budget),
            *_community_lines(view, ctx, tier, width, budget),
            *_hero_lines(view, ctx, tier, width, budget),
        ]
    lines = [
        _header(view, ui, ctx),
        *mid,
        *_log_lines(view, ui.chat, theme, budget.log),
        *_action_box_lines(view, ui, ctx, budget),
        _keybar(ui, theme),
    ]
    return _join(lines, width)


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


def _join(lines: Sequence[Text], width: int) -> Text:
    return Text("\n").join(_crop(line, width) for line in lines)


def _crop(line: Text, width: int) -> Text:
    if cell_len(line.plain) <= width:
        return line
    keep, used = 0, 0
    for ch in line.plain:
        if used + cell_len(ch) > width:
            break
        used += cell_len(ch)
        keep += 1
    out = Text(line.plain[:keep])
    for span in line.spans:
        if span.start < keep:
            out.span(span.start, min(span.end, keep), span.style)
    return out


def _fmt(n: int) -> str:
    return f"{n:,}"


def _fit(text: str, width: int) -> str:
    if cell_len(text) <= width:
        return text
    return text[:max(width - 1, 0)] + "…"


def _pad(line: Text, width: int) -> Text:
    line.append(" " * max(width - cell_len(line.plain), 0))
    return line


def _center(line: Text, width: int) -> Text:
    pad = max((width - cell_len(line.plain)) // 2, 0)
    return Text(" " * pad) + line if pad else line


def _header(view: SeatView, ui: UiState, ctx: FrameContext) -> Text:
    header = Text()
    header.append("♠ ♥ ♦ ♣ ", style=ctx.theme.accent)
    header.append(f"{ctx.title} · 第 {_fmt(view.hand_no)} 手 · {STREET_LABELS[view.street]}"
                  f" · 盲注 {ctx.blinds[0]}/{ctx.blinds[1]}", style=ctx.theme.fg)
    if ui.notice:
        header.append("  ")
        header.append(ui.notice, style=ctx.theme.accent)
    return header


def _anchor(view: SeatView, ctx: FrameContext) -> int:
    if ctx.viewer is not None:
        for info in view.seats:
            if info.name == ctx.viewer:
                return info.index
    return view.button


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


def _seats_lines(view: SeatView, ctx: FrameContext, width: int, rows: int) -> list[Text]:
    n = len(view.seats)
    order = seat_order(n, _anchor(view, ctx))
    cells = [_seat_cell(view.seats[i], view, ctx.viewer, ctx.theme) for i in order]
    lines = []
    for half in range(0, n, 2):
        pair = cells[half:half + 2]
        line = Text("   ").join(pair) if len(pair) == 2 else pair[0]
        lines.append(_pad(line, width))
    return lines


def _seats_box_lines(view: SeatView, ui: UiState, ctx: FrameContext, tier: Tier, width: int, budget: Budget) -> list[Text]:
    theme = ctx.theme
    n = len(view.seats)
    order = seat_order(n, _anchor(view, ctx))
    if n > 6 or tier is Tier.COMPACT:
        lines = _seats_lines(view, ctx, width, (n + 1) // 2)
        return [*lines, *[_blank()] * (budget.seats - len(lines))]
    box_w = seat_box_width([info.name for info in view.seats], width, boxed=True)
    boxes = [_seat_box(view.seats[i], view, ui, ctx, box_w) for i in order]
    lines = []
    for half in range(0, len(boxes), 2):
        pair = boxes[half:half + 2]
        if len(pair) == 1:
            pair = [_blank_box(box_w, theme), pair[0]]
        for row in range(3):
            line = Text()
            for j, box in enumerate(pair):
                if j:
                    line.append("  ")
                line += box[row]
            lines.append(_pad(line, width))
    return [*lines, *[_blank()] * (budget.seats - len(lines))]


def _seat_box(info: SeatInfo, view: SeatView, ui: UiState, ctx: FrameContext, w: int) -> list[Text]:
    theme = ctx.theme
    inner = w - 2
    is_viewer = ctx.viewer is not None and info.name == ctx.viewer
    acting = info.index == view.to_act
    out = info.folded and info.stack == 0 and view.street is not Street.HAND_OVER
    folded = info.folded and not out
    body = Text()
    if is_viewer:
        body.append(f"{SYMBOLS['hero']} ", style=theme.accent)
    elif acting:
        body.append(f"{SYMBOLS['to_act']} ", style=theme.accent)
    if info.is_button:
        body.append(f"{SYMBOLS['button']} ", style=theme.gold)
    if out:
        body.append(_fit(f"{info.name}（出局）", inner - cell_len(body.plain)), style=theme.dim)
    else:
        status = " 全下" if info.allin else " 弃牌" if folded else ""
        bet = f" 注{info.street_bet}" if info.street_bet > 0 else ""
        tail = cell_len(_fmt(info.stack)) + cell_len(status) + cell_len(bet) + 2
        name_style = theme.dim if folded else theme.fg
        name = _fit(info.name, max(inner - cell_len(body.plain) - tail, 4))
        body.append(name, style=f"strike {theme.dim}" if folded else name_style)
        body.append("  ", style=theme.dim)
        body.append(_fmt(info.stack), style=theme.gold if info.allin else theme.fg)
        if bet:
            body.append(bet, style=theme.gold)
        if status:
            body.append(status, style=theme.bad if info.allin else theme.dim)
    border = theme.accent if (acting or is_viewer) else theme.gold if info.allin else theme.dim if (folded or out) else theme.border
    corner = ("╭", "╮", "╰", "╯") if (acting or is_viewer) else ("┌", "┐", "└", "┘")
    content = _pad(body, inner)
    return [
        Text(f"{corner[0]}{'─' * inner}{corner[1]}", style=border),
        Text("│", style=border) + content + Text("│", style=border),
        Text(f"{corner[2]}{'─' * inner}{corner[3]}", style=border),
    ]


def _blank_box(w: int, theme: Theme) -> list[Text]:
    inner = w - 2
    return [
        Text(f"┌{'─' * inner}┐", style=theme.border),
        Text(f"│{' ' * inner}│", style=theme.border),
        Text(f"└{'─' * inner}┘", style=theme.border),
    ]


def _community_lines(view: SeatView, ctx: FrameContext, tier: Tier, width: int, budget: Budget) -> list[Text]:
    theme = ctx.theme
    slots = _COMMUNITY_SLOTS[view.street]
    shown: list = list(view.community) + [None] * (slots - len(view.community))
    if tier is Tier.COMPACT:
        ladder = [card_lines(card, MINI, theme) for card in shown]
        rows = []
        for row in range(MINI[1]):
            line = Text()
            for i, card in enumerate(ladder):
                if i:
                    line.append(" ")
                line += card[row]
            if row == 1:
                line.append(f"  底池 {_fmt(view.pot_total)}", style=theme.gold)
            rows.append(line)
        return [*rows, *[_blank()] * (budget.community - len(rows))]
    ladder = [card_lines(card, STANDARD, theme) for card in shown]
    card_rows = []
    for row in range(STANDARD[1]):
        line = Text()
        for i, card in enumerate(ladder):
            if i:
                line.append(" ")
            line += card[row]
        card_rows.append(line)
    box_w = cell_len(card_rows[0].plain) + 2
    lines = _boxed(card_rows, f"底池 {_fmt(view.pot_total)}", theme.border, box_w)
    centered = [_center(line, width) for line in lines]
    return [*centered, *[_blank()] * (budget.community - len(centered))]


def _hero_lines(view: SeatView, ctx: FrameContext, tier: Tier, width: int, budget: Budget) -> list[Text]:
    theme = ctx.theme
    if not view.hole:
        return [_blank()] * budget.hero
    size = WIDE if tier is Tier.WIDE else STANDARD
    ladder = [card_lines(card, size, theme) for card in view.hole]
    rows = []
    for row in range(size[1]):
        line = Text()
        for i, card in enumerate(ladder):
            if i:
                line.append("   ")
            line += card[row]
        rows.append(_center(line, width))
    if len(view.community) >= 3:
        rows.append(_center(Text(find_best_hand((*view.hole, *view.community)).label(), style=theme.dim), width))
    else:
        rows.append(_blank())
    return [*rows, *[_blank()] * (budget.hero - len(rows))]


def _log_lines(view: SeatView, chat: tuple[str, ...], theme: Theme, count: int) -> list[Text]:
    entries = [*view.log, *chat]
    lines = []
    for i, entry in enumerate(entries[-count:]):
        style = theme.fg if i == count - 1 else theme.dim
        lines.append(Text(_fit(entry, 200), style=style))
    return [*lines, *[_blank()] * (count - len(lines))]


def _action_line_slot(view: SeatView, ui: UiState, ctx: FrameContext) -> Text:
    theme = ctx.theme
    if ui.confirm_quit:
        return Text("再按 Enter / Ctrl-C 确认退出 · Esc 取消", style=theme.bad)
    if ui.panel is not None:
        return Text(" ").join(part for part in _panel_rows(ui.panel, ui.countdown, theme) if part.plain)
    if view.to_act is not None:
        return Text(f"等待 {view.seats[view.to_act].name} 行动…", style=theme.dim)
    return _blank()


def _action_box_lines(view: SeatView, ui: UiState, ctx: FrameContext, budget: Budget) -> list[Text]:
    theme = ctx.theme
    if ui.confirm_quit:
        rows = [Text("再按 Enter / Ctrl-C 确认退出 · Esc 取消", style=theme.bad), _blank()]
        title, border = "退出", theme.bad
    elif ui.panel is not None:
        rows = _panel_rows(ui.panel, ui.countdown, theme)
        title, border = "你的行动", theme.accent
    else:
        waiting = view.seats[view.to_act].name if view.to_act is not None else ""
        rows = [Text(f"{SYMBOLS['to_act']} {waiting} 行动中…", style=theme.dim), _blank()]
        title, border = "等待", theme.border
    inner = max(cell_len(row.plain) for row in rows) + 4
    lines = _boxed(rows, title, border, inner)
    return [*lines, *[_blank()] * (budget.action - len(lines))]


def _panel_rows(panel: ActionPanel, countdown: int | None, theme: Theme) -> list[Text]:
    row1 = Text()
    if panel.raising:
        low, high = panel.legal.min_raise_to, panel.legal.max_raise_to
        span = max(high - low, 1)
        filled = round((panel.amount - low) / span * _SLIDER_CELLS)
        row1.append("加注至 ", style=theme.fg)
        row1.append(f"{panel.amount:,}", style=theme.gold)
        row1.append(" ◀" + "━" * filled + "●" + "━" * (_SLIDER_CELLS - filled) + "▶ ", style=theme.dim)
        row1.append(f"{high:,}", style=theme.dim)
        row2 = Text("←→ 调额 · 1最小 2半池 3满池 4全下 · Enter 确认 · Esc 返回", style=theme.dim)
    else:
        for i, item in enumerate(panel.items()):
            if i:
                row1.append("  ")
            if i == panel.selected:
                row1.append("▸ ", style=theme.accent)
            row1.append(f"[{item.hotkey}]", style=theme.accent)
            row1.append(f" {item.label}", style=theme.fg)
        row2 = Text("↑↓ 选择 · Enter 确认", style=theme.dim)
    if countdown is not None:
        filled = min(countdown // 3, _GAUGE_CELLS)
        gauge = "█" * filled + "░" * (_GAUGE_CELLS - filled)
        row2.append(f"  {gauge} {countdown}s", style=theme.bad if countdown <= 5 else theme.dim)
    return [row1, row2]


def _keybar(ui: UiState, theme: Theme) -> Text:
    if ui.draft is not None:
        line = Text()
        line.append(f"聊天：{ui.draft}▌", style=theme.fg)
        line.append("  （Enter 发送 · Esc 取消）", style=theme.dim)
        return line
    return Text("V 展示 · L 历史 · ? 帮助 · M 聊天 · Ctrl-C 退出", style=theme.dim)


def _overlay_lines(view: SeatView, ui: UiState, ctx: FrameContext, rows: int, width: int) -> list[Text]:
    theme = ctx.theme
    overlay = ui.overlay
    if overlay.kind == "history":
        title = "历史（本手动作与聊天）"
        entries = [*view.log, *ui.chat]
    else:
        title = "帮助"
        entries = [
            "F 弃牌 · C 过牌/跟注 · R 加注 · A 全下",
            "↑↓ 选动作 · ←→ 调注额（Shift 大步）· 1-4 快捷档位",
            "Enter 确认 · Esc 返回/关闭",
            "M 聊天 · V 切换展示形式 · L 历史 · ? 帮助",
            "Ctrl-C 退出（二次确认）",
            "",
            f"盲注 {ctx.blinds[0]}/{ctx.blinds[1]} · 行动限时 {ctx.act_seconds:.0f} 秒",
        ]
    avail = max(rows - 2, 1)
    scroll = min(overlay.scroll, max(0, len(entries) - avail))
    window = entries[max(0, len(entries) - avail - scroll):len(entries) - scroll] or [""]
    body = []
    for i, entry in enumerate(window):
        style = theme.fg if i == len(window) - 1 else theme.dim
        body.append(Text(_fit(entry, min(width - 8, 70)), style=style))
    inner = max(cell_len(row.plain) for row in body) + 2
    lines = _boxed(body, title, theme.accent, inner)
    centered = [_center(line, width) for line in lines]
    return [*centered, *[_blank()] * (rows - len(centered))]


def _boxed(body: list[Text], title: str, style: str, inner: int) -> list[Text]:
    label = f"─ {title} " if title else "─ "
    fill = max(inner - cell_len(label), 0)
    lines = [Text(f"╭{label}{'─' * fill}╮", style=style)]
    for row in body:
        lines.append(Text("│", style=style) + _pad(row, inner) + Text("│", style=style))
    lines.append(Text(f"╰{'─' * inner}╯", style=style))
    return lines


def _board_line(view: SeatView, theme: Theme) -> Text:
    slots = _COMMUNITY_SLOTS[view.street]
    shown: list = list(view.community) + [None] * (slots - len(view.community))
    row = Text()
    for i, card in enumerate(shown):
        if i:
            row.append(" ")
        row += card_text(card, theme)
    row.append(f"   底池 {_fmt(view.pot_total)}", style=theme.gold)
    return row


def _hole_lines(view: SeatView, theme: Theme) -> list[Text]:
    if not view.hole:
        return [_blank(), _blank(), _blank()]
    cards = Text()
    for i, card in enumerate(view.hole):
        if i:
            cards.append("  ")
        cards.append(f" {rank_label(card.rank)}{card.suit} ", style=f"bold {suit_style(card, theme)}")
    label = Text("你的手牌", style=theme.dim)
    if len(view.community) >= 3:
        mine = Text(find_best_hand((*view.hole, *view.community)).label(), style=theme.dim)
    else:
        mine = _blank()
    return [label, cards, mine]
