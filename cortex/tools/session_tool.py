"""Session Tool implementation."""

from typing import Any, Dict, Optional

from .base import Tool, ToolSchema
from .types import ToolType


class SessionTool(Tool):
    """Session tool implementation for maintaining session state."""

    def __init__(
        self,
        name: str,
        description: str = "",
        session_id: Optional[str] = None,
        **kwargs,
    ):
        """
        Initialize session tool.

        Args:
            name: Tool name
            description: Tool description
            session_id: Session ID
            **kwargs: Additional parameters
        """
        super().__init__(
            name=name, description=description, tool_type=ToolType.SESSION, **kwargs
        )
        self.session_id = session_id
        self._session_state: Dict[str, Any] = {}

    def _define_schema(self) -> ToolSchema:
        """Define session tool schema."""
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "Session action (get, set, update, clear)",
                        "enum": ["get", "set", "update", "clear"],
                    },
                    "key": {"type": "string", "description": "Session key"},
                    "value": {"type": "any", "description": "Session value"},
                },
                "required": ["action"],
            },
            return_type="session_response",
        )

    async def _call(self, parameters: str, **kwargs) -> Any:
        """
        Call session tool.

        Args:
            parameters: Tool parameters (string format)
            **kwargs: Additional parameters

        Returns:
            Any: Execution result
        """
        action = kwargs.get("action", "get")

        if action == "get":
            key = kwargs.get("key")
            if key:
                return self._session_state.get(key)
            return self._session_state
        elif action == "set":
            key = kwargs.get("key")
            value = kwargs.get("value")
            if key:
                self._session_state[key] = value
                return {"status": "ok", "key": key, "value": value}
        elif action == "update":
            updates = kwargs.get("value", {})
            self._session_state.update(updates)
            return {"status": "ok", "updated": list(updates.keys())}
        elif action == "clear":
            self._session_state.clear()
            return {"status": "ok", "message": "session cleared"}
        else:
            raise ValueError(f"Unknown action: {action}")
