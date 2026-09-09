from __future__ import annotations

import asyncio
import json
import socket
import threading
from collections.abc import Callable
from dataclasses import dataclass

BEACON_PORT = 45692
ADV_INTERVAL = 3.0
_APP_TAG = "realpoker"


@dataclass(frozen=True, slots=True)
class RoomInfo:
    ip: str
    port: int
    name: str
    seats: int
    in_hand: bool


async def advertise(port: int, room_name: str, status: Callable[[], tuple[int, bool]]) -> None:
    loop = asyncio.get_running_loop()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setblocking(False)
    frame = {"app": _APP_TAG, "v": 1, "name": room_name, "tcp": port}
    try:
        while True:
            seats, in_hand = status()
            frame.update(seats=seats, in_hand=in_hand)
            data = json.dumps(frame).encode()
            await loop.sock_sendto(sock, data, ("255.255.255.255", BEACON_PORT))
            await loop.sock_sendto(sock, data, ("127.0.0.1", BEACON_PORT))
            await asyncio.sleep(ADV_INTERVAL)
    finally:
        sock.close()


async def discover(seconds: float = 3.0) -> list[RoomInfo]:
    rooms: dict[tuple[str, int], RoomInfo] = {}
    stop = threading.Event()

    def pump() -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", BEACON_PORT))
        sock.settimeout(0.3)
        while not stop.is_set():
            try:
                data, addr = sock.recvfrom(4096)
            except TimeoutError:
                continue
            except OSError:
                break
            try:
                frame = json.loads(data)
            except json.JSONDecodeError:
                continue
            if frame.get("app") != _APP_TAG:
                continue
            info = RoomInfo(
                ip=addr[0], port=int(frame.get("tcp", 0)), name=str(frame.get("name", "?")),
                seats=int(frame.get("seats", 0)), in_hand=bool(frame.get("in_hand", False)),
            )
            rooms[(info.ip, info.port)] = info
        sock.close()

    thread = threading.Thread(target=pump, daemon=True)
    thread.start()
    await asyncio.sleep(seconds)
    stop.set()
    thread.join()
    return sorted(rooms.values(), key=lambda r: (r.in_hand, -r.seats))
