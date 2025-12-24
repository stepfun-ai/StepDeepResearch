"""Local Runner implementation"""

import asyncio
from typing import AsyncGenerator, Optional
from uuid import uuid4

from cortex.model.definition import ChatMessage, Function
from cortex.agents.agent_factory import AgentFactory
from cortex.agents.base_agent import BaseAgent
from cortex.agents.input.input import InputChannel
from cortex.agents.types import (
    AgentConfig,
    AgentMessageType,
    AgentResponse,
    AgentRunningStatus,
)
from cortex.orchestrator.runner import Runner
from cortex.orchestrator.types import (
    AgentEvent,
    AgentEventType,
    ClientToolCall,
    ClientToolCallType,
)
from cortex.tools.base import ToolSchema
from cortex.tools.types import ToolParameters, ToolType
from cortex.utils.generator_merger import GeneratorMerger


class LocalRunner(Runner):
    """Local Agent runner."""

    _continue_input: bool = False

    def __init__(
        self,
        agent_factory: AgentFactory,
        task_id: str,
        parent_task_id: str | None = None,
        root_task_id: str | None = None,
        tool_call_id: str | None = None,
    ):
        """Initialize LocalRunner.

        Args:
            task_id: Task ID
            parent_task_id: Parent task ID
            root_task_id: Root task ID
            continue_input: Whether to continue input
            tool_call_id: Tool call ID
        """
        super().__init__(task_id, parent_task_id, root_task_id)
        self._agent_factory = agent_factory
        self._tool_call_id = tool_call_id
        self._task_id = task_id
        self._merger = GeneratorMerger(
            on_generator_complete=self._on_generator_complete
        )
        self._agent_factory = agent_factory
        self._agent: BaseAgent | None = None
        self._agent_name: str | None = None

        self._result: AgentEvent | None = None

    async def init(
        self,
        agent_name: str,
        context_id: str | None = None,
        config: AgentConfig | None = None,
    ) -> None:
        """Initialize Runner.

        Args:
            agent_name: Agent name
            context_id: Context ID
            config: AgentConfig
        """
        if config is not None and not config.use_share_context:
            context_id = uuid4().hex

        self._agent_name = agent_name
        self._agent = await self._agent_factory.make_agent(
            agent_name, context_id, config
        )
        if self._agent.config.unfinished_mode:
            self._continue_input = True
            self._message_queue: asyncio.Queue[ChatMessage] = asyncio.Queue()
            self._messages: InputChannel[ChatMessage] = InputChannel(
                self._message_queue
            )
        else:
            self._messages: list[ChatMessage] = []

        self._agent.toolset().set_on_send(self._on_client_tool_send)

    async def send(self, event: AgentEvent) -> None:
        """Send AgentEvent.

        Args:
            event: AgentEvent to send
        """
        if event.type == AgentEventType.REQUEST:
            # Add messages from request to queue
            if event.request and event.request.messages:
                for message in event.request.messages:
                    if self._continue_input:
                        await self._message_queue.put(message)
                    else:
                        self._messages.append(message)
        if event.type == AgentEventType.CLIENT_TOOL_RESULT:
            result = event.client_tool_result
            if result is not None:
                self._agent.toolset().set_response(
                    result.message.tool_call_id,
                    result.message.content,
                    result.error_msg,
                )

    async def run(self) -> AsyncGenerator[AgentEvent, None]:
        """Run and return AgentEvent generator.

        Yields:
            AgentEvent: Agent event
        """
        if self._task_id is None:
            raise ValueError("task_id not set, please call send() first to send REQUEST event")

        async def agent_generator() -> AsyncGenerator[AgentEvent, None]:
            if self._agent is None:
                raise ValueError("Agent not initialized, please call init() first")

            async for response in self._agent.run(self._messages):
                self._on_agent_finished(response)
                yield AgentEvent(
                    agent_name=self._agent_name,
                    task_id=self._task_id,
                    parent_task_id=self._parent_task_id,
                    root_task_id=self._root_task_id,
                    type=AgentEventType.RESPONSE,
                    response=response,
                )

            self._messages = []

        self._merger.add_async_generator(
            agent_generator, generator_id=f"local_runner_{self._task_id}"
        )

        async for event in self._merger.merge():
            yield event

    def _on_agent_finished(self, response: AgentResponse) -> None:
        """Handle Agent finished event.

        Args:
            response: AgentResponse
        """
        if response.status != AgentRunningStatus.FINISHED:
            return

        if response.message_type == AgentMessageType.STREAM:
            return

        if self._tool_call_id is None:
            self._result = AgentEvent(
                agent_name=self._agent_name,
                task_id=self._task_id,
                parent_task_id=self._parent_task_id,
                root_task_id=self._root_task_id,
                type=AgentEventType.RESPONSE,
                response=response,
            )
            return

        response.message.tool_call_id = self._tool_call_id
        self._result = AgentEvent(
            agent_name=self._agent_name,
            task_id=self._task_id,
            parent_task_id=self._parent_task_id,
            root_task_id=self._root_task_id,
            type=AgentEventType.CLIENT_TOOL_RESULT,
            client_tool_result=response,
        )

    async def _on_generator_complete(
        self, generator_id: str, generator_type: str, error: Optional[Exception]
    ) -> None:
        """Handle generator complete event.

        Args:
            generator_id: Generator ID
            generator_type: Generator Type
            error: Error
        """
        # Generator complete event handling (no special handling needed currently)

    async def _on_client_tool_send(
        self, tool_name: str, tool_schema: ToolSchema, tool_parameters: ToolParameters
    ) -> None:
        """Handle client tool send event.

        Args:
            tool_name: Tool name
            tool_schema: Tool Schema
            tool_parameters: Tool Parameters (contains tool_call_id in kwargs)
        """
        # Extract tool_call_id from tool_parameters.kwargs
        tool_call_id = tool_parameters.kwargs.get("tool_call_id")
        if tool_call_id is None:
            tool_call_id = (
                f"tool_call_{hash(tool_name)}_{hash(tool_parameters.parameters)}"
            )

        async def tool_generator() -> AsyncGenerator[AgentResponse, None]:
            tool_type = ClientToolCallType.TOOL
            if tool_schema.tool_type == ToolType.AGENT:
                tool_type = ClientToolCallType.AGENT
            elif tool_schema.tool_type == ToolType.ASK_INPUT:
                tool_type = ClientToolCallType.ASK_INPUT

            # tool params event
            yield AgentEvent(
                task_id=self._task_id,
                parent_task_id=self._parent_task_id,
                root_task_id=self._root_task_id,
                agent_name=self._agent_name,
                type=AgentEventType.CLIENT_TOOL_CALL,
                client_tool_call=ClientToolCall(
                    tool_call_id=tool_call_id,
                    function=Function(
                        arguments=tool_parameters.parameters,
                        name=tool_schema.name,
                    ),
                    type=tool_type,
                    extra=tool_parameters.kwargs,
                ),
            )

        self._merger.add_async_generator(tool_generator, generator_id=tool_call_id)

    def get_result(self) -> AgentEvent:
        """Get AgentEvent.

        Returns:
            AgentEvent: AgentEvent
        """
        return self._result
