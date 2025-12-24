"""WebSocket channel implementation for agent communication."""

import asyncio
import logging
import time
from typing import cast

from fastapi import WebSocket, WebSocketDisconnect

from cortex.server.channel.channel import Channel
from cortex.server.channel.error import ChannelClosedError

logger = logging.getLogger(__name__)


class WebSocketChannel(Channel):
    _closed: bool = False
    last_heartbeat_time: float = time.time()

    def __init__(self, ws: WebSocket) -> None:
        self.ws: WebSocket = ws

    async def send(self, event: dict[str, object]) -> None:
        if self._closed:
            raise ChannelClosedError
        await self.ws.send_json(event)

    async def receive(self) -> dict[str, object]:
        if self._closed:
            raise ChannelClosedError
        while True:
            try:
                data = cast(dict[str, object], await self.ws.receive_json())
                self.last_heartbeat_time = time.time()
                if data.get("type") == "ping":
                    await self.ws.send_json({"type": "pong"})
                    continue

                if data.get("type") == "pong":
                    continue
                return data
            except WebSocketDisconnect:
                self._closed = True
                raise ChannelClosedError

    async def heartbeat(self) -> None:
        await asyncio.sleep(10)
        while not self._closed:
            await self.ws.send_json({"type": "ping"})
            await asyncio.sleep(10)
            # TODO Check if last_heartbeat_time has timed out

    async def close(self) -> None:
        logger.debug("WebSocketChannel closing")
        if not self._closed:
            self._closed = True
            await self.ws.close()
