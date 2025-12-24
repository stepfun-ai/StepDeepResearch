"""Base Agent class, provides run() interface as the base class for all Agents."""

import asyncio
import copy
import logging
from abc import abstractmethod
from typing import Any, AsyncGenerator

from cortex.model.definition import ChatMessage, ChatToolCall, ContentBlockType

from cortex.agents.input.input import InputChannel
from cortex.agents.types import AgentConfig, AgentResponse
from cortex.model import ModelAPI
from cortex.model.provider import ModelProvider
from cortex.model.stepfun_provider import StepFunModelProvider
from cortex.tools.toolset import ToolSet

logger = logging.getLogger(__name__)


class BaseAgent:
    """Base Agent class, provides run() interface."""

    model: Any
    name: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    max_steps: int | None = 5
    _input_channel: InputChannel[ChatMessage] | None = None
    provider: ModelAPI

    def update_from_config(self):
        """Update agent properties from config."""
        # Iterate config attributes and update self if attribute exists
        for key, _ in self.config.model_dump().items():
            setattr(self, key, copy.deepcopy(getattr(self.config, key)))

        self.name = self.name or self.__class__.__name__
        self.description = (
            self.description
            or f"Call the {self.name} sub-agent to handle specific tasks"
        )

    def __init__(
        self,
        provider: ModelProvider | None = None,
        config: AgentConfig | None = None,
        toolset: ToolSet | None = None,
    ):
        self.config = config
        self.update_from_config()

        self._toolset = toolset

        if provider is None:
            provider = StepFunModelProvider(model_params=self.model)
        self.provider = ModelAPI(provider)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        """Async context manager exit."""

    async def run(
        self,
        messages: list[ChatMessage] | InputChannel[ChatMessage],
        additional_kwargs: dict | None = None,
    ) -> AsyncGenerator[AgentResponse, None]:
        """Run agent, returns AgentResponse generator."""
        async for response in self._run(messages, additional_kwargs):
            if response.agent_name is None:
                response.agent_name = self.name
            yield response

    @abstractmethod
    async def _run(
        self,
        messages: list[ChatMessage] | InputChannel[ChatMessage],
        additional_kwargs: dict | None = None,
    ) -> AsyncGenerator[AgentResponse, None]:
        """
        Run agent, subclasses must implement this method.

        Args:
            messages: Input message list or input channel
            additional_kwargs: Additional parameters

        Yields:
            AgentResponse: Agent response object
        """
        raise NotImplementedError("Subclasses must implement this method")

    def model_api(self) -> ModelAPI:
        return self.provider

    def toolset(self) -> ToolSet | None:
        """
        Get toolset.

        Returns:
            ToolSet | None: Toolset
        """
        return self._toolset

    def as_tool(self, timeout: float | None = None) -> dict[str, Any]:
        """
        Convert Agent to parameters needed for Tool creation.

        Returns a dictionary containing parameters for creating AgentTool:
        - name: Tool name (uses agent's name)
        - description: Tool description (uses agent's description)
        - agent_name: Agent name (used to specify which agent to call, as metadata)
        - timeout: Timeout (optional, if provided)

        Note: When creating AgentTool, channel parameter is also required, which is not included in this method.

        Args:
            timeout: Timeout in seconds, if None it won't be included in the returned dictionary

        Returns:
            dict: Dictionary containing parameters for creating AgentTool:
                {
                    "name": str,           # Tool name
                    "description": str,    # Tool description
                    "agent_name": str,     # Agent name (metadata)
                    "timeout": float,      # Timeout (optional)
                }

        Example:
            >>> agent = MathAgent(config)
            >>> tool_params = agent.as_tool(timeout=60.0)
            >>> # Channel is also required when creating AgentTool
            >>> tool = AgentTool(**tool_params, channel=channel)
            >>> toolset.register(tool)
        """
        agent_name = self.name or self.__class__.__name__

        tool_params: dict[str, Any] = {
            "name": agent_name,
            "description": self.description
            or f"Call {agent_name} Agent to handle specific tasks",
            "agent_name": agent_name,  # As metadata, caller knows which agent this tool corresponds to
        }

        if timeout is not None:
            tool_params["timeout"] = timeout

        logger.debug(
            "BaseAgent.as_tool returns tool params: name=%s, agent_name=%s, has_timeout=%s",
            tool_params["name"],
            tool_params["agent_name"],
            "timeout" in tool_params,
        )

        return tool_params

    @staticmethod
    def has_tool_call(message: ChatMessage) -> bool:
        """
        Check if message contains tool calls.

        Args:
            message: ChatMessage object

        Returns:
            bool: True if message contains tool calls, False otherwise
        """
        if not message:
            return False
        tool_calls = getattr(message, "tool_calls", None)
        return (
            tool_calls is not None and len(tool_calls) > 0
            if isinstance(tool_calls, (list, tuple))
            else tool_calls is not None
        )

    async def _execute_single_tool(self, tool_call: ChatToolCall) -> ChatMessage | None:
        """
        Execute a single tool call.

        Args:
            tool_call: Tool call object containing function.name, function.arguments, id, etc.

        Returns:
            ChatMessage: Tool call result message with role "tool"
        """
        tool_name = tool_call.function.name
        tool_args = tool_call.function.arguments
        tool_call_id = tool_call.id

        try:
            # Execute tool call
            result = await self._toolset.call(
                tool_name=tool_name, parameters=tool_args, tool_call_id=tool_call_id
            )
            logger.info(f"@{self.name} Tool {tool_name} result: {result}")
            if result is None:
                return None

            return ChatMessage(
                role="tool",
                content=result,
                tool_call_id=tool_call_id,
            )

        except Exception as e:
            error_msg = f"Error calling tool {tool_name}: {str(e)}"
            logger.error(f"@{self.name} {error_msg}")

            tool_result_content = [
                {
                    "type": ContentBlockType.TEXT.value,
                    ContentBlockType.TEXT.value: error_msg,
                }
            ]

            return ChatMessage(
                role="tool",
                content=tool_result_content,
                tool_call_id=tool_call_id,
            )

    async def run_tool_call(self, message: ChatMessage) -> list[ChatMessage]:
        """
        Extract tool calls from message and execute them, returning list of tool call result messages.

        Args:
            message: ChatMessage object

        Returns:
            list[ChatMessage]: List of tool call result messages, each with role "tool"
        """
        if not message:
            return []

        if not self._toolset:
            logger.warning(f"@{self.name} run_tool_call: toolset not initialized")
            return []

        tool_calls = getattr(message, "tool_calls", None)
        if not tool_calls:
            return []

        # Ensure tool_calls is a list
        if isinstance(tool_calls, (list, tuple)):
            toolcalls_list = list(tool_calls)
        else:
            toolcalls_list = [tool_calls]

        # Execute all tool calls sequentially
        tool_result_messages = []
        for tool_call in toolcalls_list:
            result_message = await self._execute_single_tool(tool_call)
            if result_message is not None:
                tool_result_messages.append(result_message)

        return tool_result_messages

    async def run_tool_call_concurrency(
        self, message: ChatMessage
    ) -> list[ChatMessage]:
        """
        Extract concurrent tool calls from message and execute them (when there are multiple tool calls).

        Args:
            message: ChatMessage object

        Returns:
            list[ChatMessage]: List of concurrent tool call result messages, only returned when tool call count > 1
        """
        if not message:
            return []

        if not self._toolset:
            logger.warning(f"@{self.name} run_tool_call_concurrency: toolset not initialized")
            return []

        tool_calls = getattr(message, "tool_calls", None)
        if not tool_calls:
            return []

        # Ensure tool_calls is a list
        if isinstance(tool_calls, (list, tuple)):
            toolcalls_list = list(tool_calls)
        else:
            toolcalls_list = [tool_calls]

        # Only return when there are multiple tool calls (concurrent scenario)
        if len(toolcalls_list) <= 1:
            return []

        # Execute all tool calls concurrently
        tool_result_messages = await asyncio.gather(
            *[self._execute_single_tool(tc) for tc in toolcalls_list]
        )

        # Filter out None results
        return [msg for msg in tool_result_messages if msg is not None]
