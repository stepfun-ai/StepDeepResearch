"""MCP (Model Context Protocol) Tool implementation."""

import json
from typing import Any

from .base import Tool, ToolSchema
from .mcp import MCPClient
from .types import ToolType


class MCPTool(Tool):
    """MCP tool implementation."""

    def __init__(
        self, name: str, description: str = "", mcp_server: str = None, **kwargs
    ):
        """
        Initialize MCP tool.

        Args:
            name: Tool name
            description: Tool description
            mcp_server: MCP server
            **kwargs: Additional parameters
        """
        super().__init__(
            name=name, description=description, tool_type=ToolType.MCP, **kwargs
        )
        self.mcp_server = mcp_server
        self._mcp_params = kwargs.get("mcp_params", {})
        # MCP tool can handle directly, no Channel needed

    def _define_schema(self) -> ToolSchema:
        """Define MCP tool schema."""
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": self._mcp_params.get("properties", {}),
                "required": self._mcp_params.get("required", []),
            },
            return_type="mcp_response",
        )

    async def _call(self, parameters: str, **kwargs) -> Any:
        """
        Call MCP tool.

        Args:
            parameters: Tool parameters (string format)
            **kwargs: Additional parameters

        Returns:
            Any: Execution result
        """
        arguments = json.loads(parameters)
        mcp_client = MCPClient(self.mcp_server)
        await mcp_client.initialize()
        try:
            result = await mcp_client.call_tool(self.name, arguments)
            return result
        finally:
            await mcp_client.aclose()
