"""Client Tool implementation - uses Channel for communication."""

import logging
from typing import Any, Optional

from .base import Tool, ToolSchema
from .channel import Channel
from .types import ToolParameters, ToolType

logger = logging.getLogger(__name__)


class UnblockClientTool(Tool):
    """Client tool implementation using Channel for asynchronous communication."""

    def __init__(
        self,
        name: str,
        description: str = "",
        tool_type: Optional[ToolType] = None,
        channel: Optional[Channel] = None,
        timeout: Optional[float] = None,
        **kwargs,
    ):
        """
        Initialize Client tool.

        Args:
            name: Tool name
            description: Tool description
            channel: Channel instance (for async communication)
            timeout: Default timeout in seconds
            **kwargs: Additional parameters
        """
        # If tool_type is not specified, default to CLIENTd, default to CLIENT
        # But if name is "ask_input", use ASK_INPUT
        if tool_type is None:
            if name == "ask_input":
                tool_type = ToolType.ASK_INPUT
            else:
                tool_type = ToolType.CLIENT

        super().__init__(
            name=name, description=description, tool_type=tool_type, **kwargs
        )

        self.timeout = timeout or 30.0
        self._client_params = kwargs.get("client_params", {})
        self.channel = channel

    def _define_schema(self) -> ToolSchema:
        """Define Client tool schema."""
        properties = self._client_params.get("properties", {})
        required = self._client_params.get("required", [])

        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": properties,
                "required": required,
            },
            return_type="client_response",
            tool_type=self.tool_type,
        )

    async def _call(self, parameters: str, **kwargs) -> Any:
        """
        Call the Client tool.

        Send request through Channel and wait for response.

        Args:
            parameters: Tool parameters (string format)
            **kwargs: Additional parameters

        Returns:
            Any: Execution result
        """
        # Build request data, convert parameters and kwargs to ToolParameters
        tool_parameters = ToolParameters(parameters=parameters, kwargs=kwargs)

        tool_call_id = kwargs.get("tool_call_id")
        if tool_call_id is None:
            tool_call_id = f"tool_call_{hash(self.name)}_{hash(parameters)}"

        logger.debug(
            "ClientTool._call: tool=%s, parameters=%s, tool_call_id=%s",
            self.name,
            parameters,
            tool_call_id,
        )

        await self.channel._on_send(self.name, self.get_schema(), tool_parameters)
        return None
