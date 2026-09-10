"""User-perspective smoke: play a full local session through a pipe, drive menus and actions.

Run: uv run python tests/smoke_local.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


consumed = 0


def main() -> None:
    tmp = tempfile.mkdtemp(prefix="rp-smoke-")
    env = dict(os.environ, APPDATA=tmp, PYTHONPATH=os.path.join(ROOT, "src"), PYTHONIOENCODING="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "rpoker.app.main"], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, cwd=ROOT,
        text=True, encoding="utf-8", bufsize=1)
    buffer: list[str] = []

    def reader() -> None:
        buffer.extend(proc.stdout)

    threading.Thread(target=reader, daemon=True).start()

    def send(text: str) -> None:
        proc.stdin.write(text + "\n")
        proc.stdin.flush()

    def fresh() -> str:
        """Output produced after the last consumed marker."""
        return "".join(buffer)[consumed:]

    def wait_for(text: str, timeout: float = 30) -> str:
        global consumed
        end = time.time() + timeout
        while time.time() < end:
            new = fresh()
            if text in new:
                consumed += new.index(text) + len(text)
                return new
            time.sleep(0.1)
        raise SystemExit(f"[FAIL] timeout waiting for {text!r}; tail={(''.join(buffer))[-1500:]!r}")

    def play_hand() -> None:
        """Spam call/check until this hand's hand-over menu appears."""
        global consumed
        deadline = time.time() + 120
        last = 0.0
        while time.time() < deadline:
            new = fresh()
            if "1. 下一手" in new:  # the hand-over menu option, unique to the interlude
                consumed += new.index("1. 下一手") + len("1. 下一手")
                return
            if time.time() - last > 1.5 and ("f=弃牌" in new or "c=过牌" in new):
                send("c")
                last = time.time()
            time.sleep(0.2)
        raise SystemExit("[FAIL] hand never finished")

    send("玩家甲")
    wait_for("1. 创建房间")
    send("3")                                   # 本地练习
    play_hand()
    send("1")                                   # 下一手
    play_hand()
    send("2")                                   # 回到主菜单
    wait_for("1. 创建房间")
    send("4")                                   # 主题与设置
    wait_for("展示形式")
    send("2")                                   # 展示形式
    wait_for("简单（紧凑文本，信息不减）")
    send("2")                                   # 选简单
    wait_for("展示形式已切换为 simple")
    send("q")                                   # 返回上级
    time.sleep(0.3)
    send("5")                                   # 退出
    time.sleep(0.5)

    text = "".join(buffer)
    assert "Traceback" not in text, text[-3000:]
    assert "展示形式已切换为 simple" in text
    print("[OK] local session smoke: hands played, settings switched, clean exit")
    proc.kill()


if __name__ == "__main__":
    main()
