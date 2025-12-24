from typing import List

from cortex.model.definition import ChatMessage

from cortex.context import BaseContext

simple_contexts: dict[str, list[ChatMessage]] = {}


class SimpleContext(BaseContext):
    """Simple context management class for managing session messages."""

    def __init__(self, session_id: str):
        super().__init__(session_id)

    def add(self, msg: list[ChatMessage]) -> None:
        """Add chat message list to context."""
        if self.session_id in simple_contexts:
            simple_contexts[self.session_id].extend(msg)
        else:
            simple_contexts[self.session_id] = msg

    def get_all(self) -> List[ChatMessage]:
        """Get all chat messages."""
        return simple_contexts.get(self.session_id, [])
