from __future__ import annotations

import asyncio
import io
import sys
import threading
from dataclasses import dataclass

from prompt_toolkit.input import create_input
from prompt_toolkit.keys import Keys
from rich.console import Console
from rich.live import Live

_KEY_NAMES = {
    Keys.Up: "up", Keys.Down: "down", Keys.Left: "left", Keys.Right: "right",
    Keys.ShiftLeft: "shift-left", Keys.ShiftRight: "shift-right",
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


class LineReader:
    def __init__(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._queue: asyncio.Queue[str | None] = asyncio.Queue()
        self._thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()

    def _pump(self) -> None:
        while True:
            try:
                line = sys.stdin.readline()
            except OSError:
                break
            if not line:
                break
            self._loop.call_soon_threadsafe(self._queue.put_nowait, line.strip().lower())
        self._loop.call_soon_threadsafe(self._queue.put_nowait, None)

    async def get(self, timeout: float | None) -> str | None:
        if timeout is None:
            return await self._queue.get()
        try:
            return await asyncio.wait_for(self._queue.get(), timeout)
        except TimeoutError:
            return None


class QuitApp(Exception):
    pass


@dataclass(frozen=True, slots=True)
class Option:
    label: str
    hint: str = ""


class FrameView:
    """Alternate-screen single frame on a TTY (refresh only when content changes);
    plain reprint on pipes where rich Live never refreshes."""

    def __init__(self, terminal: Terminal) -> None:
        self._console = terminal.console
        self._tty = terminal.tty
        self._live: Live | None = None
        self._last: str | None = None

    @property
    def active(self) -> bool:
        return self._live is not None

    def start(self) -> None:
        if self._tty and self._live is None:
            self._live = Live(console=self._console, screen=True, auto_refresh=False, transient=False)
            self._live.start()

    def stop(self) -> None:
        if self._live is not None:
            self._live.stop()
            self._live = None
        self._last = None

    def update(self, renderable) -> None:
        if self._live is None:
            self._console.print(renderable)
            return
        text = self._ansi(renderable)
        if text == self._last:
            return
        self._last = text
        self._live.update(renderable, refresh=True)

    def _ansi(self, renderable) -> str:
        buffer = io.StringIO()
        offscreen = Console(
            file=buffer,
            force_terminal=True,
            color_system=self._console.color_system or "truecolor",
            width=self._console.width,
            highlight=False,
            legacy_windows=False,
        )
        offscreen.print(renderable)
        return buffer.getvalue()


class Terminal:
    def __init__(self, console: Console) -> None:
        self.console = console
        self.tty = sys.stdin.isatty() and console.is_terminal
        self._keys: KeyReader | None = None
        self._lines: LineReader | None = None
        self._cursor_hidden = False

    def frame_view(self) -> FrameView:
        return FrameView(self)

    def close(self) -> None:
        self.show_cursor()
        if self._keys is not None:
            self._keys.close()

    def _reader(self) -> KeyReader | LineReader:
        if self.tty:
            if self._keys is None:
                self._keys = KeyReader()
            return self._keys
        if self._lines is None:
            self._lines = LineReader()
        return self._lines

    async def key(self, timeout: float | None) -> str | None:
        return await self._reader().get(timeout)

    def print(self, *renderables) -> None:
        self.show_cursor()
        self.console.print(*renderables)

    def _write(self, text: str) -> None:
        self.console.file.write(text)
        self.console.file.flush()

    def hide_cursor(self) -> None:
        if self.tty and not self._cursor_hidden:
            self._write("\x1b[?25l")
            self._cursor_hidden = True

    def show_cursor(self) -> None:
        if self._cursor_hidden:
            self._write("\x1b[?25h")
            self._cursor_hidden = False

    def _erase_above(self, lines: int) -> None:
        self.show_cursor()
        self._write(f"\x1b[{lines}A\x1b[J")

    def _redraw_line(self, renderable) -> None:
        """Atomic in-place line refresh: one write, no wrap, no blank frame, cursor hidden."""
        if not self.tty:
            self.console.print(renderable)
            return
        self.hide_cursor()
        self._write("\r" + self._ansi_line(renderable) + "\x1b[K")

    def _ansi_line(self, renderable) -> str:
        """Render to a single ANSI string, hard-cropped to terminal width so it never wraps."""
        buffer = io.StringIO()
        offscreen = Console(
            file=buffer,
            force_terminal=True,
            color_system=self.console.color_system or "truecolor",
            width=self.console.width,
            highlight=False,
            legacy_windows=False,
        )
        offscreen.print(renderable)
        return buffer.getvalue().split("\n", 1)[0]

    async def ask(self, prompt: str, default: str = "") -> str:
        self.console.print(prompt + (f" [dim]（回车 = {default}）[/dim]" if default else ""))
        if not self.tty:
            answer = await self.key(None)
            return default if answer is None or answer == "" else answer
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
            key = await self.key(None)
            if key is None:
                return False
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
        if not self.tty:
            self.print()
            self.print(f"[bold]{title}[/bold]")
            for i, option in enumerate(options, 1):
                self.print(f"  {i}. {option.label}" + (f"  [dim]{option.hint}[/dim]" if option.hint else ""))
            self.print(f"[dim]输入 1-{len(options)} 的编号{'，q 返回' if cancellable else ''}[/dim]")
            while True:
                answer = await self.key(None)
                if answer is None:
                    return None
                if answer.isdigit() and 1 <= int(answer) <= len(options):
                    return int(answer) - 1
                if cancellable and answer in ("q", "b"):
                    return None
                self.print(f"[dim]无效编号，请输入 1-{len(options)}[/dim]")
        selected = 0
        height = 0
        while True:
            if height:
                self._erase_above(height)
            self.print(f"[bold]{title}[/bold]")
            block = 1
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
