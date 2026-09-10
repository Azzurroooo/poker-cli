"""Simple and rich modes must carry the same facts (§3.3 information parity), plus snapshots."""
from __future__ import annotations

import re
from io import StringIO
from pathlib import Path

from rich.console import Console

from rpoker.domain.actions import LegalActions
from rpoker.domain.views import SeatInfo, SeatView, Street
from rpoker.ui.panels import ActionPanel
from rpoker.ui.render import (
    FrameContext,
    OverlayState,
    UiState,
    rich_frame,
    simple_frame,
)
from rpoker.ui.tokens import THEMES
from tests.engine.helpers import cards

THEME = THEMES["onedark"]
CTX = FrameContext(THEME, "测试房", "你", (5, 10))
SNAPSHOTS = Path(__file__).parent / "snapshots"

ACTING = LegalActions(False, 40, 80, 960)


def sample_view(seats: int = 5) -> SeatView:
    names = ["你", "老周", "阿棠", "石头", "绵绵", "大熊", "飞飞"][:seats]
    view_seats = tuple(
        SeatInfo(i, n, 1000 - (40 if i == 0 else 0), 40 if i == 0 else (20 if i == 2 else 0),
                 i == 3, i == 2, i == 1)
        for i, n in enumerate(names)
    )
    return SeatView(7, Street.FLOP, 1, cards("Qd 2h Js"), 365, view_seats, cards("Ah As"), 0,
                    ACTING, None,
                    ("—— 第 7 手 ——", "老周 小盲 5 · 阿棠 大盲 10", "你 加注至 40", "阿棠 跟注 40",
                     "石头 弃牌", "—— flop Q♦ 2♥ J♠", "阿棠 过牌"))


def plain(renderable, width: int) -> str:
    console = Console(file=StringIO(), force_terminal=False, width=width, highlight=False)
    console.print(renderable)
    return console.file.getvalue()


def facts(plain_text: str, names: list[str]) -> set[str]:
    numbers = set(re.findall(r"\d[\d,]*", plain_text))
    present = {name for name in names if name in plain_text}
    labels = {word for word in ("弃牌", "全下", "底池", "翻牌圈", "一对 A") if word in plain_text}
    return numbers | present | labels


def test_information_parity_between_modes() -> None:
    for seats in (5, 9):
        view = sample_view(seats)
        names = [info.name for info in view.seats]
        ui = UiState(panel=ActionPanel.build(ACTING),
                     countdown=21, chat=("老周：打得漂亮",))
        rich = facts(rich_frame(view, ui, CTX, 100, 34).plain, names)
        simple = facts(simple_frame(view, ui, CTX, 80).plain, names)
        missing_in_rich = simple - rich - {"◆"}
        missing_in_simple = rich - simple - {"◈", "★", "▸"}
        assert not missing_in_rich, f"simple-only facts: {missing_in_rich}"
        assert not missing_in_simple, f"rich-only facts: {missing_in_simple}"


def _snapshot(name: str, renderable, width: int) -> None:
    text = plain(renderable, width)
    path = SNAPSHOTS / name
    if not path.exists():
        SNAPSHOTS.mkdir(exist_ok=True)
        path.write_text(text, encoding="utf-8")
    assert text == path.read_text(encoding="utf-8"), f"snapshot {name} drifted"


def test_snapshots() -> None:
    view = sample_view()
    acting = UiState(panel=ActionPanel.build(ACTING),
                     countdown=21)
    _snapshot("rich-acting-5p.txt", rich_frame(view, acting, CTX, 100, 34), 100)
    _snapshot("rich-idle-9p.txt", rich_frame(sample_view(9), UiState(), CTX, 100, 34), 100)
    _snapshot("rich-compact.txt", rich_frame(view, acting, CTX, 80, 24), 80)
    _snapshot("rich-overlay-help.txt", rich_frame(view, UiState(overlay=OverlayState("help", 0)), CTX, 100, 34), 100)
    _snapshot("simple-acting.txt", simple_frame(view, acting, CTX, 80), 80)
