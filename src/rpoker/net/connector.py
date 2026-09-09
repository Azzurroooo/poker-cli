from __future__ import annotations

import asyncio
from typing import Protocol

from rpoker.net.codec import ProtocolError, decode, encode
from rpoker.net.messages import Message


class Connector(Protocol):
    async def send(self, message: Message) -> None: ...
    async def recv(self) -> Message | None: ...
    async def close(self) -> None: ...


class TcpConnector:
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._reader = reader
        self._writer = writer

    async def send(self, message: Message) -> None:
        self._writer.write(encode(message))
        await self._writer.drain()

    async def recv(self) -> Message | None:
        line = await self._reader.readline()
        if not line:
            return None
        try:
            return decode(line)
        except ProtocolError:
            await self.close()
            return None

    async def close(self) -> None:
        self._writer.close()
        try:
            await self._writer.wait_closed()
        except (ConnectionError, OSError):
            pass


async def connect(host: str, port: int) -> TcpConnector:
    reader, writer = await asyncio.open_connection(host, port)
    return TcpConnector(reader, writer)
