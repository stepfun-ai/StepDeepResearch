from abc import ABC, abstractmethod
from typing import AsyncGenerator

from .definition import ChatMessage


class ModelProvider(ABC):
    @abstractmethod
    async def chat_completion_stream(
            self,
            messages: list[ChatMessage],
            tools: list | None = None,
            log_file: str | None = None,
    ) -> AsyncGenerator[ChatMessage, None]:
        pass

    @abstractmethod
    async def chat_completion(
            self,
            messages: list[ChatMessage],
            tools: list | None = None,
            log_file: str | None = None,
    ) -> ChatMessage:
        pass
