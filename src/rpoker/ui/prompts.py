from __future__ import annotations

import asyncio
import sys
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from prompt_toolkit.input import create_input
from prompt_toolkit.keys import Keys
from rich.console import Console
from rich.text import Text

from rpoker.domain.actions import Action, LegalActions
from rpoker.domain.views import SeatView
from rpoker.ui.tokens import Theme

_KEY_NAMES = {
    Keys.Up: "up", Keys.Down: "down", Keys.Left: "left", Keys.Right: "right",
    Keys.Enter: "enter", Keys.Escape: "escape", Keys.Tab: "tab",
    Keys.ControlC: "ctrl-c", Keys.Backspace: "backspace",
}


class KeyReader:
    def __init__(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._input = create_input()
        self._raw = self._input.raw_mode()
        self._raw.__enter__()
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()

    def _pump(self) -> None:
        while True:
            try:
                keys = self._input.read_keys()
            except Exception:
                break
            for key in keys:
                name = _KEY_NAMES.get(key.key, key.key)
                self._loop.call_soon_threadsafe(self._queue.put_nowait, name)

    async def get(self, timeout: float | None) -> str | None:
        if timeout is None:
            return await self._queue.get()
        try:
            return await asyncio.wait_for(self._queue.get(), timeout)
        except TimeoutError:
            return None

    def close(self) -> None:
        self._raw.__exit__(None, None, None)
        self._input.close()


@dataclass(frozen=True, slots=True)
class Option:
    label: str
    hint: str = ""


class Terminal:
    def __init__(self, console: Console) -> None:
        self.console = console
        self.tty = sys.stdin.isatty() and console.is_terminal
        self._keys: KeyReader | None = KeyReader() if self.tty else None

    def close(self) -> None:
        if self._keys is not None:
            self._keys.close()

    async def key(self, timeout: float | None) -> str | None:
        if self._keys is not None:
            return await self._keys.get(timeout)
        if timeout is None:
            return await self._line()
        try:
            return await asyncio.wait_for(self._line(), timeout)
        except TimeoutError:
            return None

    async def _line(self) -> str:
        line = await asyncio.get_running_loop().run_in_executor(None, sys.stdin.readline)
        return line.strip().lower()

    def print(self, *renderables) -> None:
        self.console.print(*renderables)

    def _write(self, text: str) -> None:
        self.console.file.write(text)
        self.console.file.flush()

    def _erase_above(self, lines: int) -> None:
        self._write(f"\x1b[{lines}A\x1b[J")

    async def ask(self, prompt: str, default: str = "") -> str:
        self.console.print(prompt + (f" [dim]（回车 = {default}）[/dim]" if default else ""))
        if not self.tty:
            answer = await self._line()
            return answer or default
        buffer = ""
        self._write("❯ ")
        while True:
            key = await self.key(None)
            if key == "enter":
                self._write("\n")
                return buffer or default
            if key == "backspace":
                if buffer:
                    buffer = buffer[:-1]
                    self._write("\b \b")
                continue
            if key == "escape":
                self._write("\n")
                return default
            if key == "ctrl-c":
                self._write("\n")
                return default
            if len(key) == 1:
                buffer += key
                self._write(key)

    async def confirm(self, prompt: str, default: bool = True) -> bool:
        suffix = "（Y/n）" if default else "（y/N）"
        self.print(f"{prompt}[dim]{suffix}[/dim]")
        while True:
            key = await self.key(None) if self.tty else await self._line()
            match key:
                case "" | "enter":
                    return default
                case "y" | "yes":
                    return True
                case "n" | "no" | "escape":
                    return False
                case "ctrl-c":
                    return False

    async def menu(self, title: str, options: list[Option], cancellable: bool = True) -> int | None:
        self.print()
        self.print(f"[bold]{title}[/bold]")
        if not self.tty:
            for i, option in enumerate(options, 1):
                self.print(f"  {i}. {option.label}" + (f"  [dim]{option.hint}[/dim]" if option.hint else ""))
            self.print(f"[dim]输入 1-{len(options)} 的编号{'，q 返回' if cancellable else ''}[/dim]")
            while True:
                answer = await self._line()
                if answer.isdigit() and 1 <= int(answer) <= len(options):
                    return int(answer) - 1
                if cancellable and answer in ("q", "b"):
                    return None
                self.print(f"[dim]无效编号，请输入 1-{len(options)}[/dim]")
        selected = 0
        height = len(options) + 1
        while True:
            self._erase_above(height) if height else None
            block = 0
            for i, option in enumerate(options):
                cursor = "[reverse] ▶ [/reverse]" if i == selected else "   "
                hint = f"  [dim]{option.hint}[/dim]" if option.hint else ""
                self.print(f"{cursor} {option.label}{hint}")
                block += 1
            self.print("[dim]↑↓ 选择 · Enter 确认" + (" · Esc 返回" if cancellable else "") + "[/dim]")
            block += 1
            height = block
            key = await self.key(None)
            match key:
                case "up" | "w":
                    selected = (selected - 1) % len(options)
                case "down" | "s":
                    selected = (selected + 1) % len(options)
                case "enter":
                    self._erase_above(height)
                    return selected
                case "escape":
                    if cancellable:
                        self._erase_above(height)
                        return None
                case "ctrl-c":
                    self._erase_above(height)
                    return None
                case digit if digit.isdigit() and 1 <= int(digit) <= len(options):
                    self._erase_above(height)
                    return int(digit) - 1

    async def action(self, view: SeatView, theme: Theme, send_chat: Callable[[str], Awaitable[None]] | None = None) -> Action:
        legal: LegalActions = view.legal
        if not self.tty:
            self.print()
            self.print(self._action_line(legal, theme))
            while True:
                answer = await self._line()
                action = self._parse_action(answer, legal)
                if action is not None:
                    return action
                self.print("[dim]无效输入[/dim]" + self._action_line(legal, theme))
        while True:
            key = await self._action_bar(legal, theme, view)
            if key is None:
                return self._auto(legal)
            match key:
                case "f":
                    return Action("fold")
                case "c":
                    return Action("check") if legal.can_check else Action("call")
                case "a" if not legal.can_check:
                    return Action("allin")
                case "r" if legal.max_raise_to is not None:
                    amount = await self._raise_page(legal, theme, view)
                    if amount is not None:
                        return Action("raise", amount)
                case "m" if send_chat is not None:
                    text = await self.ask("聊天：")
                    if text:
                        await send_chat(text)

    def _action_line(self, legal: LegalActions, theme: Theme) -> str:
        parts = []
        if legal.to_call > 0:
            parts.append("f=弃牌")
            parts.append(f"c=跟注 {legal.to_call}")
            parts.append("a=全下")
        else:
            parts.append("c=过牌")
        if legal.max_raise_to is not None:
            parts.append(f"r=加注 {legal.min_raise_to}-{legal.max_raise_to}")
        return "  ".join(parts) + "  （如 r120 表示加注至 120）"

    def _parse_action(self, answer: str, legal: LegalActions) -> Action | None:
        if answer == "f":
            return Action("fold")
        if answer == "c":
            return Action("check") if legal.can_check else Action("call")
        if answer == "a":
            return Action("allin")
        if answer.startswith("r") and legal.max_raise_to is not None and answer[1:].isdigit():
            amount = int(answer[1:])
            if legal.min_raise_to <= amount <= legal.max_raise_to:
                return Action("raise", amount)
        return None

    def _auto(self, legal: LegalActions) -> Action:
        return Action("check") if legal.can_check else Action("fold")

    async def _action_bar(self, legal: LegalActions, theme: Theme, view: SeatView) -> str | None:
        buttons: list[tuple[str, str]] = []
        if legal.to_call > 0:
            buttons.append(("F", "弃牌"))
            buttons.append(("C", f"跟注 {legal.to_call}"))
        else:
            buttons.append(("C", "过牌"))
        if legal.max_raise_to is not None:
            buttons.append(("R", "加注"))
        if not legal.can_check:
            buttons.append(("A", "全下"))
        while True:
            bar = Text()
            for i, (hotkey, label) in enumerate(buttons):
                if i:
                    bar.append("  ")
                bar.append(f"[{hotkey}] ", style=theme.accent)
                bar.append(label, style=theme.fg)
            bar.append("   M 聊天", style=theme.dim)
            if view.deadline is not None:
                remaining = max(int(view.deadline - time.monotonic()), 0)
                gauge = "█" * min(remaining // 3, 10) + "░" * max(10 - remaining // 3, 0)
                bar.append(f"   ⏱ {gauge} {remaining}s", style=theme.bad if remaining <= 5 else theme.dim)
            self.print(bar)
            key = await self.key(0.25)
            if key is None:
                self._erase_above(1)
                continue
            return key

    async def _raise_page(self, legal: LegalActions, theme: Theme, view: SeatView) -> int | None:
        step = max(view.pot_total // 20, 1)
        amount = legal.min_raise_to
        presets = [
            ("1", "最小", legal.min_raise_to),
            ("2", "半池", min(max(legal.to_call + view.pot_total // 2, legal.min_raise_to), legal.max_raise_to)),
            ("3", "满池", min(max(legal.to_call + view.pot_total, legal.min_raise_to), legal.max_raise_to)),
            ("4", "全下", legal.max_raise_to),
        ]
        if not self.tty:
            while True:
                answer = await self._line()
                action = self._parse_action("r" + answer, legal)
                if action is not None:
                    return action.amount
                if answer in ("q", "escape"):
                    return None
        while True:
            span = max(legal.max_raise_to - legal.min_raise_to, 1)
            filled = round((amount - legal.min_raise_to) / span * 20)
            slider = "━" * filled + "●" + "━" * (20 - filled)
            line = Text()
            line.append("加注至 ", style=theme.fg)
            line.append(f"{amount:,}", style=theme.gold)
            line.append(f"  ←{slider}→  ", style=theme.dim)
            line.append(f"{legal.max_raise_to:,}", style=theme.dim)
            self.print(line)
            hint = Text(style=theme.dim)
            hint.append("   ".join(f"[{k}] {label} {value:,}" for k, label, value in presets))
            hint.append("   Enter 确认 · Esc 取消")
            self.print(hint)
            key = await self.key(None)
            self._erase_above(2)
            match key:
                case "left":
                    amount = max(legal.min_raise_to, amount - step)
                case "right":
                    amount = min(legal.max_raise_to, amount + step)
                case "1" | "2" | "3" | "4":
                    amount = {k: v for k, _, v in presets}[key]
                case "enter":
                    return amount
                case "escape" | "q":
                    return None
                case "ctrl-c":
                    return None
                case digit if digit.isdigit() and 1 <= int(digit) <= 9:
                    scaled = legal.min_raise_to + span * int(digit) // 10
                    amount = min(max(scaled, legal.min_raise_to), legal.max_raise_to)
