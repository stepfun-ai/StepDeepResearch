"""Agent Tool implementation - calls agents through Orchestrator."""

import json
import logging
from typing import Any, Optional

from cortex.model.definition import ChatMessage

from .base import Tool, ToolSchema
from .channel import Channel
from .types import ToolParameters, ToolType

logger = logging.getLogger(__name__)


class UnblockAgentTool(Tool):
    """Agent tool implementation for calling other Agents through Channel communication with Orchestrator."""

    share_context: bool = False

    def __init__(
        self,
        name: str,
        description: str = "",
        channel: Optional[Channel] = None,
        timeout: Optional[float] = None,
        share_context: bool = False,
        **kwargs,
    ):
        """
        Initialize Agent tool.

        Args:
            name: Tool name.
            description: Tool description.
            channel: Channel instance (for async communication).
            timeout: Default timeout in seconds.
            share_context: Whether to share context.
            **kwargs: Other parameters.
        """
        super().__init__(
            name=name, description=description, tool_type=ToolType.AGENT, **kwargs
        )
        if channel is None:
            raise ValueError("AgentTool requires a Channel instance")
        self.channel = channel
        self.timeout = timeout or 30.0
        logger.debug(
            "AgentTool initialized: name=%s, description=%s, timeout=%s",
            name,
            description,
            self.timeout,
        )

    def _define_schema(self) -> ToolSchema:
        """Define Agent tool schema."""
        schema = ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "Specific instruction content to send to Agent (optional, ignored if messages is provided)",
                    },
                    "messages": {
                        "type": "array",
                        "description": "List of messages to send to Agent (optional, ChatMessage format with role and content fields)",
                        "items": {
                            "type": "object",
                            "properties": {
                                "role": {
                                    "type": "string",
                                    "description": "Message role, e.g., 'user', 'assistant', 'system'",
                                    "enum": ["user", "assistant", "system", "tool"],
                                },
                                "content": {
                                    "type": "string",
                                    "description": "Message content (string format)",
                                },
                            },
                            "required": ["role", "content"],
                        },
                    },
                    "timeout": {
                        "type": "number",
                        "description": "Timeout in seconds (optional)",
                    },
                },
                "required": [],
            },
            return_type="agent_response",
            tool_type=self.tool_type,
        )
        logger.debug(
            "AgentTool schema defined: name=%s, parameters=%s", self.name, schema.parameters
        )
        return schema

    async def _call(self, parameters: str, **kwargs) -> Any:
        """
        Call Agent tool.

        Send request to Orchestrator through Channel, which creates new Agent and executes task.

        Args:
            parameters: Tool parameters (JSON string format), containing:
                - content: Specific instruction content (optional, ignored if messages is provided)
                - messages: Message list (optional, ChatMessage format with role and content fields)
                - timeout: Timeout in seconds (optional)
            **kwargs: Other parameters (unused)

        Returns:
            Any: Agent execution result

        Raises:
            ValueError: Invalid parameters format
            TimeoutError: Request timeout
        """
        tool_call_id = kwargs.get("tool_call_id")
        agent_name = self.name
        # Process messages: prefer messages, use content to create ChatMessage if not available
        messages = UnblockAgentTool.parse_messages(parameters)

        # Build request data in orchestrator expected format
        request_data = {
            "agent_name": agent_name,
        }

        if messages:
            request_data["messages"] = messages

        request_data.update(kwargs)

        logger.debug(
            "UnblockAgentTool._call: tool=%s, agent=%s, messages=%d, tool_call_id=%s",
            self.name,
            agent_name,
            len(messages) if messages else 0,
            tool_call_id,
        )

        # Send request through Channel and wait for response
        tool_parameters = ToolParameters(parameters=parameters, kwargs=request_data)
        await self.channel._on_send(self.name, self.get_schema(), tool_parameters)
        return None

    @staticmethod
    def parse_messages(parameters: str) -> list[ChatMessage]:
        """
        Prepare message list.

        Args:
            parameters: Tool parameters (JSON string format)

        Returns:
            list[ChatMessage]: Processed message list
        """
        # Parse parameters JSON string
        try:
            params_dict = json.loads(parameters) if parameters else {}
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid parameters JSON format: {e}") from e

        # Prefer messages
        messages = params_dict.get("messages", [])
        if messages:
            processed = []
            for msg in messages:
                if isinstance(msg, dict):
                    processed.append(ChatMessage(**msg))
                elif isinstance(msg, ChatMessage):
                    processed.append(msg)
                else:
                    processed.append(msg)
            return processed

        # If no messages, try to use content
        content = params_dict.get("content")
        if content:
            return [ChatMessage(role="user", content=content)]

        return []
