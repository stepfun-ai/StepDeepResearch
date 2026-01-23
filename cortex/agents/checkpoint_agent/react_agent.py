"""ReActAgent - An Agent specifically designed to execute tasks in ReAct (Reasoning + Acting) mode, capable of calling tools to complete tasks."""

import logging
from typing import AsyncGenerator
from uuid import uuid4

from cortex.model.definition import ChatMessage

from cortex.agents.checkpoint_agent.checkpoint_agent import CheckpointAgent
from cortex.agents.checkpoint_agent.checkpointer import CheckpointStorage
from cortex.agents.react_agent import process_messages
from cortex.agents.types import (
    AgentConfig,
    AgentMessageType,
    AgentResponse,
    AgentRunningStatus,
)
from cortex.model.provider import ModelProvider
from cortex.tools.toolset import ToolSet

logger = logging.getLogger(__name__)


class CheckpointReActAgent(CheckpointAgent):
    """ReActAgent - An Agent specifically designed to execute tasks in ReAct (Reasoning + Acting) mode.

    Features:
    - Can call tools to complete tasks
    - Can call tools multiple times to complete complex tasks
    - Can provide detailed task execution process description
    - Can provide detailed task execution results
    """

    def __init__(
        self,
        storage: CheckpointStorage,
        context_id: str | None = None,
        provider: ModelProvider | None = None,
        config: AgentConfig | None = None,
        toolset: ToolSet | None = None,
    ):
        # If no toolset is provided, create a default math toolset
        if toolset is None:
            # Note: Cannot call async functions directly here, need to initialize externally
            raise ValueError(
                "ReActAgent requires a toolset, please use init_react_tools() to create one"
            )

        if not context_id:
            context_id = uuid4().hex
        super().__init__(
            storage=storage,
            thread_id=context_id,
            provider=provider,
            config=config,
            toolset=toolset,
        )

    async def _step(
        self,
        messages: list[ChatMessage],
        additional_kwargs: dict | None = None,
    ) -> AsyncGenerator[AgentResponse, None]:
        """
        Execute a single step, can yield multiple responses.

        Args:
            messages: Current message history
            additional_kwargs: Additional parameters

        Yields:
            AgentResponse: Response for the current step
        """
        try:
            async for response_message in process_messages(
                self.system_prompt,
                messages,
                self.toolset(),
                self.model_api(),
                getattr(self.model, "infer_kwargs", {}).get("stream", False),
                trace_messages=list(messages) if messages else [],
            ):
                yield response_message
        except Exception as e:
            err_text = str(e) or repr(e)
            logger.error("@%s execution error: %s", self.name, err_text, exc_info=True)
            error_response = AgentResponse(
                message=None,
                status=AgentRunningStatus.ERROR.value,
                error_msg=err_text,
                message_type=AgentMessageType.FINAL.value,
            )
            yield error_response

    async def _tool_call_handler(
        self, messages: list[ChatMessage], tool_results: list[ChatMessage]
    ) -> AsyncGenerator[AgentResponse, None]:
        """
        Handle tool calls.
        """

        for result in tool_results:
            yield AgentResponse(
                message=result,
                status=AgentRunningStatus.RUNNING.value,
                message_type=AgentMessageType.ACCUMULATED.value,
            )
