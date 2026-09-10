"""E2E driver: two real processes (host + client) play a LAN hand over TCP.

Run: uv run python tests/e2e_lan.py
"""
# ruff: noqa: BLE001
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Player:
    def __init__(self, name: str, appdata: str):
        self.name = name
        env = dict(os.environ, APPDATA=appdata, PYTHONPATH=os.path.join(ROOT, "src"), PYTHONIOENCODING="utf-8")
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "rpoker.app.main"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=env, cwd=ROOT, text=True, encoding="utf-8", bufsize=1,
        )
        self.buffer = ""
        self.lock = threading.Lock()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        try:
            for line in iter(self.proc.stdout.readline, ""):
                with self.lock:
                    self.buffer += line
        except Exception as exc:
            with self.lock:
                self.buffer += f"\n[READER DIED: {type(exc).__name__}: {exc}]"

    def send(self, text: str) -> None:
        self.proc.stdin.write(text + "\n")
        self.proc.stdin.flush()

    def seen(self, text: str) -> bool:
        with self.lock:
            return text in self.buffer


def wait_for(player: Player, text: str, timeout: float = 60, other: Player | None = None) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if player.seen(text):
            return
        time.sleep(0.1)
    other_dump = ""
    if other is not None:
        other_dump = (
            f"\n=== other ({other.name}, alive={other.proc.poll() is None}, buflen={len(other.buffer)}) ===\n"
            f"{other.buffer[-800:]!r}"
        )
    raise SystemExit(
        f"[FAIL] {player.name}: waiting for {text!r} timed out (alive={player.proc.poll() is None}, "
        f"buflen={len(player.buffer)}).\n=== {player.name} raw tail ===\n{player.buffer[-600:]!r}{other_dump}"
    )


def main() -> None:
    tmp = tempfile.mkdtemp(prefix="rp-e2e-")
    room_name = f"e2e-{os.getpid()}"
    host = Player("host", tmp)

    host.send("Player")
    wait_for(host, "1. 创建房间")
    host.send("1")
    wait_for(host, "房间名")
    host.send(room_name)
    wait_for(host, "桌子人数")
    host.send("1")                                  # 2 players
    wait_for(host, "选择盲注")
    host.send("2")                                  # 5/10
    wait_for(host, "等待牌友加入")

    found = subprocess.run(
        [sys.executable, "-c",
         ("import asyncio, json; from rpoker.net.beacon import discover; "
         "rooms = asyncio.run(discover(4.0)); "
         "print(json.dumps([{'name': r.name, 'ip': r.ip, 'port': r.port} for r in rooms]))")],
        env=dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"), PYTHONIOENCODING="utf-8"),
        cwd=ROOT, capture_output=True, text=True, timeout=30, check=True,
    )
    rooms = json.loads(found.stdout.strip().splitlines()[-1])
    mine = [r for r in rooms if r["name"] == room_name and r["ip"] == "127.0.0.1"]
    assert mine, f"discovery failed to find {room_name}: {rooms}"
    print(f"[OK] UDP discovery found room {room_name} on port {mine[0]['port']}")

    # launched after host saved config → same APPDATA, same saved nickname "Player":
    # must be auto-renamed by the host, not rejected as "table full"
    client = Player("client", tmp)
    wait_for(client, "1. 创建房间")
    client.send("2")                                # 加入房间
    wait_for(client, "选择要加入的房间")
    import re

    option_numbers = re.findall(r"^\s*(\d+)\. .*(手动输入 IP 加入)", client.buffer, re.MULTILINE)
    if option_numbers:
        client.send(option_numbers[0][0])
        wait_for(client, "房间地址")
        client.send(f"127.0.0.1:{mine[0]['port']}")
    else:
        raise SystemExit(f"[FAIL] manual option not found.\nClient output:\n{client.buffer[-2000:]}")
    wait_for(client, "已加入")
    if "昵称 player2" not in client.buffer.lower():
        raise SystemExit(f"[FAIL] rename missing. Client tail:\n{client.buffer[-500:]!r}\nHost tail:\n{host.buffer[-300:]!r}")
    print("[OK] duplicate nickname auto-renamed to player2")

    host.send("")                                   # start the game
    wait_for(host, "第 1 手", timeout=30)
    wait_for(client, "第 1 手", timeout=30, other=host)

    class Feeder:
        def __init__(self, player: Player):
            self.player = player
            self.last_send = 0.0

        def tick(self) -> None:
            buffer = self.player.buffer
            tail_index = max(buffer.rfind("f=弃牌"), buffer.rfind("c=过牌"))
            if tail_index < 0:
                return
            if time.time() - self.last_send < 2.0:
                return
            self.last_send = time.time()
            self.player.send("c")

    host_feeder = Feeder(host)
    client_feeder = Feeder(client)
    deadline = time.time() + 150
    ended = False
    while time.time() < deadline:
        if not ended and host.seen("本手结束"):
            host.send("2")                          # 结束牌局并显示排名
            ended = True
        host_feeder.tick()
        client_feeder.tick()
        if ended and host.seen("最终排名"):
            break
        time.sleep(0.2)
    else:
        raise SystemExit(f"[FAIL] hand did not finish.\nHost:\n{host.buffer[-2000:]}\nClient:\n{client.buffer[-2000:]}")

    assert not host.seen("Traceback"), "host crashed"
    assert not client.seen("Traceback"), "client crashed"
    wait_for(client, "已与房间断开", timeout=60)
    print("[OK] hand completed, standings shown, client disconnected cleanly")

    host.send("")                                   # 回主菜单 confirm
    wait_for(host, "1. 创建房间")
    host.send("5")                                  # 退出
    client.send("5")
    time.sleep(1)
    host.proc.kill()
    client.proc.kill()
    print("[PASS] E2E LAN battle: create → discover → join → play → settle → exit")


if __name__ == "__main__":
    main()
