from abc import ABC, abstractmethod


class Channel(ABC):
    def __init__(self, context_id: str) -> None:
        self.context_id: str = context_id

    @abstractmethod
    async def send(self, event: dict[str, object]):
        pass

    @abstractmethod
    async def receive(self) -> dict[str, object]:
        pass

    @abstractmethod
    async def heartbeat(self):
        pass

    @abstractmethod
    async def close(self):
        pass
