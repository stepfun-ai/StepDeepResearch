"""ToolSet for managing and executing tools."""

import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional, Type

from agentkit.trace import get_current_context

from .agent_tool import AgentTool
from .base import Tool, ToolSchema
from .channel import Channel
from .client_tool import ClientTool
from .function_tool import FunctionTool
from .mcp import MCPClient
from .mcp_tool import MCPTool
from .session_tool import SessionTool
from .types import ToolConfig, ToolParameters, ToolType

logger = logging.getLogger(__name__)


class ToolSet:
    """Tool collection that manages tool registration, initialization, and invocation."""

    _client_tool_results: dict[str, Any] = {}

    def __init__(
        self,
        channel: Optional[Channel] = None,
        on_send: Optional[
            Callable[[str, ToolSchema, ToolParameters], Awaitable[None]]
        ] = None,
    ):
        """
        Initialize ToolSet.

        Args:
            channel: Shared Channel instance (optional)
            on_send: Callback function for sending requests, passed to Channel
                    (if channel is not provided, a new Channel will be created with this callback)
        """
        self._tools: Dict[str, Tool] = {}
        self._tool_factories: Dict[ToolType, Type[Tool]] = {
            ToolType.MCP: MCPTool,
            ToolType.FUNCTION: FunctionTool,
            ToolType.SESSION: SessionTool,
            ToolType.CLIENT: ClientTool,
            ToolType.AGENT: AgentTool,
            ToolType.ASK_INPUT: ClientTool,  # ASK_INPUT uses ClientTool implementation
        }

        if channel:
            self.channel = channel
            # If on_send parameter is provided, set it (overrides existing)
            if on_send:
                self.channel.set_on_send(on_send)
        else:
            # If no channel is provided, create a new channel with on_send
            self.channel = Channel(on_send=on_send)

    def set_on_send(
        self, on_send: Callable[[str, ToolSchema, ToolParameters], Awaitable[None]]
    ) -> None:
        """
        Set the on_send callback function for ToolSet.

        Args:
            on_send: Callback function for sending requests,
                    receives (tool_name, tool_schema, tool_parameters) and sends data asynchronously

        Returns:
            None
        """
        self.channel.set_on_send(on_send)

    def register(self, tool: Tool, name: Optional[str] = None) -> None:
        """
        Register a tool.

        Args:
            tool: Tool instance
            name: Tool name (if not provided, uses tool.name)
        """
        tool_name = name or tool.name

        if tool_name in self._tools:
            raise ValueError(f"Tool '{tool_name}' is already registered")

        # If it's a ClientTool or AgentTool without a channel, set the shared channel
        if isinstance(tool, (ClientTool, AgentTool)) and tool.channel != self.channel:
            tool.channel = self.channel

        self._tools[tool_name] = tool
        logger.info(f"✓ Registered tool: {tool_name} ({tool.tool_type.value})")

    async def register_from_mcp_server(
        self, mcp_server: str, tool_names: list[str] | None = None
    ) -> None:
        """
        Register tools from an MCP server.

        Args:
            mcp_server: The MCP server URL
            tool_names: Optional list of tool names to register. If None, all available tools will be registered.
        """
        try:
            mcp_client = MCPClient(mcp_server)
            await mcp_client.initialize()
            mcp_tools = await mcp_client.list_tools()
            if tool_names is not None:
                mcp_tools = [tool for tool in mcp_tools if tool.name in tool_names]
            for mcp_tool in mcp_tools:
                # Extract properties and required from inputSchema
                input_schema = mcp_tool.inputSchema or {}
                mcp_params = {
                    "properties": input_schema.get("properties", {}),
                    "required": input_schema.get("required", []),
                }

                server_tool = MCPTool(
                    name=mcp_tool.name,
                    description=mcp_tool.description,
                    mcp_server=mcp_server,
                    mcp_params=mcp_params,
                )
                self.register(server_tool, mcp_tool.name)
        finally:
            await mcp_client.aclose()

    def register_from_config(self, config: ToolConfig) -> Tool:
        """
        Initialize and register a tool from configuration.

        Args:
            config: Tool configuration

        Returns:
            Tool: Created tool instance
        """
        factory = self._tool_factories.get(config.tool_type)
        if not factory:
            raise ValueError(f"Unknown tool type: {config.tool_type}")

        # Prepare initialization parameters
        init_params = config.params or {}

        if config.tool_type == ToolType.MCP:
            init_params.setdefault("endpoint", init_params.get("endpoint"))
        elif (
            config.tool_type == ToolType.CLIENT
            or config.tool_type == ToolType.ASK_INPUT
        ):
            # ClientTool and ASK_INPUT must use channel, use ToolSet's channel if not provided
            if "channel" not in init_params:
                init_params["channel"] = self.channel
        elif config.tool_type == ToolType.AGENT:
            # AgentTool must use channel, use ToolSet's channel if not provided
            if "channel" not in init_params:
                init_params["channel"] = self.channel
        elif config.tool_type == ToolType.FUNCTION:
            if "func" not in init_params:
                raise ValueError("Function tool requires 'func' parameter")

        # Create tool instance
        tool = factory(
            name=config.name,
            description=init_params.get("description", ""),
            **init_params,
        )

        # Register tool
        self.register(tool, config.name)

        return tool

    def get_tool(self, name: str) -> Optional[Tool]:
        """
        Get a tool by name.

        Args:
            name: Tool name

        Returns:
            Tool: Tool instance, or None if not found
        """
        return self._tools.get(name)

    def list_tools(self) -> List[str]:
        """
        List all registered tool names.

        Returns:
            List[str]: List of tool names
        """
        return list(self._tools.keys())

    async def call(self, tool_name: str, parameters: str, **kwargs) -> Any:
        """
        Call a tool.

        Args:
            tool_name: Tool name
            parameters: Tool parameters
            **kwargs: Additional parameters

        Returns:
            Any: Tool execution result

        Raises:
            ValueError: Tool not found
        """
        ctx = get_current_context()
        with ctx.tool_span(name=f"ToolSet.call {tool_name}") as span:
            span.update_payload_data(
                request=kwargs,
            )
            tool = self.get_tool(tool_name)
            if not tool:
                raise ValueError(f"Tool '{tool_name}' is not registered")

            logger.info(
                f"ToolSet.call {tool_name} parameters: {parameters} kwargs: {kwargs}"
            )
            resp = await tool.call(parameters, **kwargs)

            span.update_payload_data(
                response=resp,
            )
            return resp

    def get_schema(self, tool_name: str) -> Any:
        """
        Get tool schema.

        Args:
            tool_name: Tool name

        Returns:
            Any: Tool schema

        Raises:
            ValueError: Tool not found
        """
        tool = self.get_tool(tool_name)
        if not tool:
            raise ValueError(f"Tool '{tool_name}' is not registered")

        return tool.get_schema()

    def get_all_schemas(self) -> Dict[str, Any]:
        """
        Get schemas for all tools.

        Returns:
            Dict[str, Any]: Mapping of tool names to schemas
        """
        return {name: tool.get_schema() for name, tool in self._tools.items()}

    def get_client_tool_call_result(self, tool_call_id: str) -> Any:
        """
        Get the result of a ClientTool call.

        Args:
            tool_call_id: Tool call ID

        Returns:
            Any: Tool call result
        """
        result, error = self._client_tool_results.get(tool_call_id, (None, None))
        if error:
            raise Exception(error)
        return result

    def set_client_tool_call_result(
        self, tool_call_id: str, result: Any, error: Optional[str] = None
    ):
        """
        Set the result of a ClientTool call.
        """
        self._client_tool_results[tool_call_id] = (result, error)

    def set_response(self, request_id: str, data: Any, error: Optional[str] = None):
        """
        Set ClientTool response.

        Args:
            request_id: Request ID
            data: Response data
            error: Error message (if any)

        Raises:
            ValueError: Tool not found or not a ClientTool
        """
        # tool = self.get_tool(tool_name)
        # if not tool:
        #     raise ValueError(f"Tool '{tool_name}' is not registered")

        # if not isinstance(tool, ClientTool):
        #     raise ValueError(
        #         f"Tool '{tool_name}' is not a ClientTool, cannot set response"
        #     )

        # Set response through Channel
        self.channel.set_response(request_id, data, error)
        self.set_client_tool_call_result(request_id, data, error)
