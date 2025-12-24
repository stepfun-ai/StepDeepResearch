import asyncio
from typing import Dict

from loguru import logger

from cortex.server.channel.channel import Channel
from cortex.server.channel.error import ChannelClosedError


class MemoryChannel(Channel):
    def __init__(self, context_id: str) -> None:
        super().__init__(context_id)
        self.send_queue = asyncio.Queue()
        self.receive_queue = asyncio.Queue()
        self.is_closed = False
        logger.debug(f"MemoryChannel created with context_id: {context_id}")

    async def send(self, event: Dict[str, object]):
        if self.is_closed:
            raise ChannelClosedError("Channel is closed")
        await self.send_queue.put(event)
        logger.debug(f"MemoryChannel {self.context_id}: sent event")

    async def receive(self) -> Dict[str, object]:
        if self.is_closed:
            raise ChannelClosedError("Channel is closed")

        data = await self.receive_queue.get()
        logger.debug(f"MemoryChannel {self.context_id}: received event")
        return data

    async def heartbeat(self):
        pass

    async def close(self):
        logger.debug(f"MemoryChannel {self.context_id}: closing")
        self.is_closed = True
