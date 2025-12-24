"""Client Tool implementation - uses Channel for communication."""

import logging
from typing import Any, Optional

from .base import Tool, ToolSchema
from .channel import Channel
from .types import ToolParameters, ToolType

logger = logging.getLogger(__name__)


class ClientTool(Tool):
    """Client tool implementation, uses Channel for async communication."""

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
        Initialize client tool.

        Args:
            name: Tool name
            description: Tool description
            channel: Channel instance (for async communication)
            timeout: Default timeout in seconds
            **kwargs: Additional parameters
        """
        # If tool_type is not specified, default to CLIENT
        # But if name is "ask_input", use ASK_INPUT
        if tool_type is None:
            if name == "ask_input":
                tool_type = ToolType.ASK_INPUT
            else:
                tool_type = ToolType.CLIENT

        super().__init__(
            name=name, description=description, tool_type=tool_type, **kwargs
        )
        if channel is None:
            raise ValueError("ClientTool requires a Channel instance")
        self.channel = channel
        self.timeout = timeout or 30.0
        self._client_params = kwargs.get("client_params", {})

    def _define_schema(self) -> ToolSchema:
        """Define client tool schema."""
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
        Call the client tool.

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

        # Send request through Channel and wait for response
        _, response = await self.channel.send_request(
            tool_name=self.name,
            data=tool_parameters,
            tool_schema=self.get_schema(),
            request_id=kwargs.get("tool_call_id"),
            timeout=kwargs.get("timeout") or self.timeout,
        )

        return response
