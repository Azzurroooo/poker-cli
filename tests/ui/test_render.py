from __future__ import annotations

import io

from rich.console import Console

from rpoker.ui.layout import rich_budget, rich_tier
from rpoker.ui.render import (
    FrameContext,
    OverlayState,
    UiState,
    rich_frame,
    simple_frame,
)
from tests.ui.test_screen import THEME, build_view

CTX = FrameContext(THEME, "测试房", "你", (5, 10))


def frame_height(renderable, width: int) -> int:
    buffer = io.StringIO()
    Console(file=buffer, force_terminal=True, width=width, highlight=False).print(renderable)
    return len(buffer.getvalue().rstrip("\n").split("\n"))


def test_overlay_keeps_rich_frame_height() -> None:
    view = build_view()
    width, height = 100, 34
    plain = rich_frame(view, UiState(), CTX, width, height)
    history = rich_frame(view, UiState(overlay=OverlayState("history", 0)), CTX, width, height)
    help_ = rich_frame(view, UiState(overlay=OverlayState("help", 2)), CTX, width, height)
    assert frame_height(plain, width) == frame_height(history, width) == frame_height(help_, width)


def test_overlay_keeps_simple_frame_height() -> None:
    view = build_view()
    plain = simple_frame(view, UiState(), CTX, 80)
    history = simple_frame(view, UiState(overlay=OverlayState("history", 0)), CTX, 80)
    assert frame_height(plain, 80) == frame_height(history, 80)


def test_history_overlay_shows_log_and_chat() -> None:
    view = build_view()
    ui = UiState(overlay=OverlayState("history", 0), chat=("老周：打得漂亮",))
    buffer = io.StringIO()
    Console(file=buffer, force_terminal=True, width=100, highlight=False).print(rich_frame(view, ui, CTX, 100, 34))
    out = buffer.getvalue()
    assert "历史" in out
    assert "打得漂亮" in out
    assert "第 1 手" in out


def test_draft_renders_in_keybar() -> None:
    view = build_view()
    buffer = io.StringIO()
    Console(file=buffer, force_terminal=True, width=100, highlight=False).print(
        simple_frame(view, UiState(draft="大家好"), CTX, 80))
    assert "聊天：大家好▌" in buffer.getvalue()


def test_rich_budget_matches_rendered_height() -> None:
    view = build_view()
    width, height = 100, 34
    budget = rich_budget(rich_tier(width, height), len(view.seats))
    rendered = frame_height(rich_frame(view, UiState(), CTX, width, height), width)
    assert rendered == budget.height
