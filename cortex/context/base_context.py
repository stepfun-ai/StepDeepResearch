"""Base context management class."""

from abc import ABC, abstractmethod
from typing import List

from cortex.model.definition import ChatMessage


class BaseContext(ABC):
    """Base context management class, providing basic interface for session message management."""

    def __init__(self, session_id: str):
        """
        Initialize base context.

        Args:
            session_id: Session ID
        """
        self.session_id = session_id

    @abstractmethod
    def add(self, messages: list[ChatMessage]) -> None:
        """
        Add chat messages to context.

        Args:
            messages: List of chat messages to add
        """
        ...

    @abstractmethod
    def get_all(self) -> List[ChatMessage]:
        """
        Get all chat messages.

        Returns:
            List[ChatMessage]: List of all chat messages
        """
        ...
