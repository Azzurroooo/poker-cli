from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

from rpoker.domain.actions import Action
from rpoker.domain.views import SeatView
from rpoker.engine.table import HandResult
from rpoker.ui.layout import Mode, effective_mode
from rpoker.ui.panels import ActionPanel, action_line, auto_action, parse_action
from rpoker.ui.prompts import Option, QuitApp, Terminal
from rpoker.ui.render import (
    FrameContext,
    OverlayState,
    UiState,
    interlude_summary,
    rich_frame,
    simple_frame,
)

_POLL_SECONDS = 0.25
_NOTICE_SECONDS = 3.0
DISPLAY_LABELS = {"rich": "丰富", "simple": "简单"}


class GameScreen:
    """Single-frame game UI: owns UI state, the only key router, and frame refresh."""

    def __init__(
        self,
        terminal: Terminal,
        ctx: FrameContext,
        act_seconds: float,
        display: str = "rich",
        chat_send: Callable[[str], Awaitable[None]] | None = None,
        on_display_change: Callable[[str], None] | None = None,
    ) -> None:
        self.terminal = terminal
        self.ctx = ctx
        self.act_seconds = act_seconds
        self.display = display
        self.chat_send = chat_send
        self.on_display_change = on_display_change
        self.frames = terminal.frame_view()
        self._view: SeatView | None = None
        self._result: HandResult | None = None
        self._chat: list[str] = []
        self._panel: ActionPanel | None = None
        self._countdown: int | None = None
        self._confirm_quit = False
        self._quit = False
        self._belled = False
        self._overlay: OverlayState | None = None
        self._draft: str | None = None
        self._notice: str | None = None
        self._notice_until = 0.0
        self._keys: asyncio.Queue[str] = asyncio.Queue()
        self._router: asyncio.Task | None = None

    async def start(self) -> None:
        self.frames.start()
        if self.terminal.tty:
            self._router = asyncio.create_task(self._route())

    async def close(self) -> None:
        if self._router is not None:
            self._router.cancel()
            try:
                await self._router
            except asyncio.CancelledError:
                pass
            self._router = None
        self.frames.stop()

    def add_chat(self, line: str) -> None:
        self._chat.append(line)
        if self.frames.active:
            self._refresh()
        else:
            self.terminal.print(line)

    async def show(self, view: SeatView, result: HandResult | None = None) -> None:
        self._check_quit()
        self._view = view
        self._result = result
        self._refresh()

    def actor(self) -> Callable[[SeatView], Awaitable[Action]]:
        async def act(view: SeatView) -> Action:
            return await self.act(view)

        return act

    async def act(self, view: SeatView) -> Action:
        self._check_quit()
        if not self.terminal.tty:
            return await self._static_act(view)
        self._panel = ActionPanel.build(view.legal)
        self._belled = False
        deadline = view.deadline if view.deadline is not None else time.monotonic() + self.act_seconds
        while not self._keys.empty():
            self._keys.get_nowait()
        try:
            while True:
                self._check_quit()
                self._set_countdown(deadline)
                self._refresh()
                if time.monotonic() >= deadline:
                    return auto_action(view.legal)
                try:
                    key = await asyncio.wait_for(self._keys.get(), timeout=_POLL_SECONDS)
                except TimeoutError:
                    continue
                action = self._panel.handle(key, view.pot_total)
                if action is not None:
                    return action
        finally:
            self._panel = None
            self._countdown = None
            self._refresh()

    async def interlude(self, result: HandResult, title: str, options: list[Option]) -> int:
        self._check_quit()
        self._router_pause()
        self.frames.stop()
        self.terminal.print(interlude_summary(result, self.ctx.theme))
        choice = await self.terminal.menu(title, options, cancellable=False)
        self.frames.start()
        self._router_resume()
        return choice

    def _check_quit(self) -> None:
        if self._quit:
            raise QuitApp

    async def _route(self) -> None:
        while True:
            key = await self.terminal.key(_POLL_SECONDS)
            if key == "ctrl-c":
                self._confirm_quit = not self._confirm_quit
                self._refresh()
                continue
            if self._confirm_quit:
                if key == "enter":
                    self._quit = True
                    return
                if key == "escape":
                    self._confirm_quit = False
                    self._refresh()
                continue
            if self._overlay is not None:
                self._overlay_key(key)
                continue
            if self._draft is not None:
                await self._draft_key(key)
                continue
            if key is None:
                self._expire_notice()
                continue
            match key:
                case "v":
                    self._switch_display()
                case "l":
                    self._overlay = OverlayState("history", 0)
                    self._refresh()
                case "?":
                    self._overlay = OverlayState("help", 0)
                    self._refresh()
                case "m" if self.chat_send is not None:
                    self._draft = ""
                    self._refresh()
                case _:
                    if self._panel is not None:
                        self._keys.put_nowait(key)

    def _overlay_key(self, key: str) -> None:
        if key in ("escape", "q", "?", "l"):
            self._overlay = None
        elif key == "up" and self._overlay is not None:
            self._overlay = OverlayState(self._overlay.kind, self._overlay.scroll + 1)
        elif key == "down" and self._overlay is not None and self._overlay.scroll > 0:
            self._overlay = OverlayState(self._overlay.kind, self._overlay.scroll - 1)
        else:
            return
        self._refresh()

    async def _draft_key(self, key: str) -> None:
        if key == "enter":
            text, self._draft = self._draft, None
            if text and self.chat_send is not None:
                await self.chat_send(text)
        elif key == "escape":
            self._draft = None
        elif key == "backspace":
            self._draft = self._draft[:-1]
        elif key == "ctrl-c":
            self._confirm_quit = True
            self._draft = None
        elif len(key) == 1:
            self._draft += key
        else:
            return
        self._refresh()

    def _switch_display(self) -> None:
        self.display = "simple" if self.display == "rich" else "rich"
        if self.on_display_change is not None:
            self.on_display_change(self.display)
        self._notify(f"已切换为{DISPLAY_LABELS[self.display]}模式")
        self._refresh()

    def _notify(self, text: str) -> None:
        self._notice = text
        self._notice_until = time.monotonic() + _NOTICE_SECONDS

    def _expire_notice(self) -> None:
        if self._notice is not None and time.monotonic() >= self._notice_until:
            self._notice = None
            self._refresh()

    def _set_countdown(self, deadline: float) -> None:
        self._countdown = max(int(deadline - time.monotonic()), 0)
        if self._countdown in (1, 2, 3, 4, 5) and not self._belled:
            self._belled = True
            self.terminal.console.bell()

    def _refresh(self) -> None:
        if self._view is None:
            return
        ui = UiState(
            panel=self._panel,
            countdown=self._countdown,
            confirm_quit=self._confirm_quit,
            chat=tuple(self._chat),
            notice=self._notice,
            overlay=self._overlay,
            draft=self._draft,
        )
        console = self.terminal.console
        if self.frames.active and effective_mode(self.display, console.width, console.height) is Mode.RICH:
            self.frames.update(rich_frame(self._view, ui, self.ctx, console.width, console.height))
        else:
            self.frames.update(simple_frame(self._view, ui, self.ctx, console.width))

    def _router_pause(self) -> None:
        if self._router is not None:
            self._router.cancel()
            self._router = None

    def _router_resume(self) -> None:
        if self.terminal.tty and self._router is None:
            self._router = asyncio.create_task(self._route())

    async def _static_act(self, view: SeatView) -> Action:
        legal = view.legal
        self.terminal.print()
        self.terminal.print(action_line(legal))
        while True:
            answer = await self.terminal.key(None)
            if answer is None:
                return auto_action(legal)
            action = parse_action(answer, legal)
            if action is not None:
                return action
            self.terminal.print("[dim]无效输入[/dim]" + action_line(legal))
