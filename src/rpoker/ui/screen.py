from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

from rpoker.domain.actions import Action
from rpoker.domain.views import SeatView
from rpoker.engine.table import HandResult
from rpoker.ui.panels import ActionPanel, action_line, auto_action, parse_action
from rpoker.ui.prompts import Option, QuitApp, Terminal
from rpoker.ui.render import FrameContext, UiState, interlude_summary, simple_frame

_POLL_SECONDS = 0.25


class GameScreen:
    """Single-frame game UI: owns UI state, the only key router, and frame refresh."""

    def __init__(self, terminal: Terminal, ctx: FrameContext, act_seconds: float) -> None:
        self.terminal = terminal
        self.ctx = ctx
        self.act_seconds = act_seconds
        self.frames = terminal.frame_view()
        self._view: SeatView | None = None
        self._result: HandResult | None = None
        self._chat: list[str] = []
        self._panel: ActionPanel | None = None
        self._countdown: int | None = None
        self._confirm_quit = False
        self._quit = False
        self._belled = False
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
            if key is None:
                continue
            if self._panel is not None:
                self._keys.put_nowait(key)

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
        )
        self.frames.update(simple_frame(self._view, self._result, ui, self.ctx))

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
