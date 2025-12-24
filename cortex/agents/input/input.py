import asyncio
import logging
from typing import Generic, TypeVar

from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class InputChannel(Generic[T]):
    queue: asyncio.Queue[T]

    def __init__(self, queue: asyncio.Queue[T]) -> None:
        self.queue = queue

    async def get(self) -> list[T]:
        """Blocks until at least one message is available, then returns all available messages."""
        logger.debug("InputChannel waiting for first data")
        first = await self.queue.get()
        data_list: list[T] = [first]
        count = 1
        while True:
            try:
                data = self.queue.get_nowait()
                data_list.append(data)
                count += 1
            except asyncio.QueueEmpty:
                break
        logger.debug(f"InputChannel returning {count} data(s)")
        return data_list

    async def get_no_wait(self) -> list[T]:
        data_list: list[T] = []
        count = 0
        while True:
            try:
                data = self.queue.get_nowait()
                data_list.append(data)
                count += 1
            except asyncio.QueueEmpty:
                break
        logger.debug(f"InputChannel returning {count} data(s)")
        return data_list
