import logging
from contextlib import AsyncExitStack
from typing import Any, final

from mcp import ClientSession, Tool
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import CallToolResult

logger = logging.getLogger(__name__)


class MCPNotInitializedError(Exception):
    """Exception raised when MCP client is not initialized."""

    def __init__(self) -> None:
        super().__init__("MCP client is not initialized")


@final
class MCPClient:
    def __init__(self, server_url: str) -> None:
        self.server_url = server_url
        self.session = None
        self.exit_stack = AsyncExitStack()

    async def initialize(self) -> None:
        read_stream, write_stream, _ = await self.exit_stack.enter_async_context(
            streamablehttp_client(self.server_url)
        )
        self.session = await self.exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        logger.info(f"Connected to server: {self.server_url}")
        await self.session.initialize()
        logger.info("Initialized session")

    async def aclose(self) -> None:
        """Close all resources opened via the exit stack.

        This must be called from the same task that created the contexts to
        avoid AnyIO cancel scope errors during shutdown.
        """
        try:
            await self.exit_stack.aclose()
        finally:
            self.session = None

    async def list_tools(self) -> list[Tool]:
        if self.session is None:
            raise MCPNotInitializedError()

        result = await self.session.list_tools()
        return result.tools

    async def call_tool(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> CallToolResult:
        if self.session is None:
            raise MCPNotInitializedError()
        return await self.session.call_tool(tool_name, arguments)
