import logging
from abc import abstractmethod
from typing import AsyncGenerator

from cortex.model.definition import ChatMessage, ContentBlockType
from pydantic import BaseModel

from cortex.agents.base_agent import BaseAgent
from cortex.agents.checkpoint_agent.checkpointer import CheckPointer, CheckpointStorage
from cortex.agents.types import (
    AgentConfig,
    AgentMessageType,
    AgentResponse,
    AgentRunningStatus,
)
from cortex.model.provider import ModelProvider
from cortex.tools.toolset import ToolSet

logger = logging.getLogger(__name__)


class PendingToolCall(BaseModel):
    """Pending tool call"""

    request: ChatMessage | None
    results: dict[str, ChatMessage] | None


class CheckpointState(BaseModel):
    """Checkpoint state definition"""

    messages: list[ChatMessage] | None
    pending_tool_calls: list[PendingToolCall] | None
    tool_call_results: list[ChatMessage] | None
    config: AgentConfig | None
    current_step: int
    max_steps: int | None
    finished: bool
    error: str | None


class CheckpointAgent(BaseAgent):
    """Checkpoint-based single-step execution Agent (without LangGraph)"""

    def __init__(
        self,
        config: AgentConfig,
        storage: CheckpointStorage,
        provider: ModelProvider | None = None,
        toolset: ToolSet | None = None,
        thread_id: str | None = None,
    ):
        super().__init__(config=config, toolset=toolset, provider=provider)
        self.thread_id = thread_id or f"{self.name}_main"
        self.storage = storage
        self._state: CheckpointState | None = None

    def _init_state(
        self,
    ) -> CheckpointState:
        """Initialize state"""
        return CheckpointState(
            messages=[],
            pending_tool_calls=[],
            tool_call_results=[],
            config=self.config,
            current_step=0,
            max_steps=getattr(self.config, "max_steps", 10),
            finished=False,
            error=None,
        )

    async def _process_tool_call_results(
        self, state: CheckpointState
    ) -> AsyncGenerator[AgentResponse, None]:
        """Process tool call results"""
        if not state.tool_call_results or len(state.tool_call_results) == 0:
            return

        logger.debug(
            "@%s Processing %d tool call results", self.name, len(state.tool_call_results)
        )
        async for response in self._tool_call_handler(
            state.messages, state.tool_call_results
        ):
            yield response
            if response.message:
                state.messages.append(response.message)

        # Clear processed results
        state.tool_call_results = []

    async def _execute_step(
        self, state: CheckpointState, additional_kwargs: dict | None = None
    ) -> AsyncGenerator[AgentResponse, None]:
        """Execute single step"""
        step_responses = []
        try:
            async for response in self._step(state.messages, additional_kwargs):
                step_responses.append(response)
                yield response

                # Handle message history update
                if response.message:
                    # STREAM type messages are incremental updates, should not be added to history
                    if response.message_type == AgentMessageType.STREAM.value:
                        pass
                    else:
                        # For non-streaming messages, ensure role field exists
                        message_to_add = None
                        if isinstance(response.message, ChatMessage):
                            if (
                                response.message.tool_calls
                                and len(response.message.tool_calls) > 0
                            ):
                                # Execute tool calls
                                results = await self.run_tool_call(response.message)
                                # Convert result list to dict with tool_call_id as key
                                state.pending_tool_calls.append(
                                    PendingToolCall(
                                        request=response.message,
                                        results={
                                            result.tool_call_id: result
                                            for result in results
                                        },
                                    )
                                )
                                message_to_add = response.message
                            elif response.message.tool_call_id:
                                # Tool call result
                                state.tool_call_results.append(response.message)
                            else:
                                message_to_add = response.message

                        elif isinstance(response.message, dict):
                            if response.message.get("role"):
                                message_to_add = ChatMessage(**response.message)

                        # Only add message to history when it has a valid role
                        if message_to_add and message_to_add.role:
                            state.messages.append(message_to_add)
                        else:
                            logger.warning(
                                "@%s Skipping message without role: %s",
                                self.name,
                                response.message_type,
                            )

            state.current_step += 1
            # Check if finished
            if step_responses:
                last_response = step_responses[-1]
                if last_response.status == AgentRunningStatus.FINISHED.value:
                    state.finished = True
                elif last_response.status == AgentRunningStatus.ERROR.value:
                    state.error = last_response.error_msg
                    state.finished = True

        except Exception as e:
            logger.error("@%s Error during step execution: %s", self.name, str(e))
            state.error = str(e)
            state.finished = True
            raise

    async def _update_client_tool_results(self, state: CheckpointState) -> bool:
        """
        Update client tool call results.
        Returns True if there are still pending tool calls.
        """
        if not state.pending_tool_calls or len(state.pending_tool_calls) == 0:
            return False

        new_pending_tool_calls = []
        for pending_item in state.pending_tool_calls:
            request = pending_item.request
            results = pending_item.results
            # Check if each tool_call has a corresponding result
            all_matched = True

            for tool_call in request.tool_calls:
                tool_call_id = tool_call.id
                # Check if result already exists
                if results.get(tool_call_id):
                    continue

                result_content = self.toolset().get_client_tool_call_result(
                    tool_call_id
                )

                if result_content is None:
                    all_matched = False
                    continue
                results[tool_call_id] = ChatMessage(
                    role="tool",
                    content=[
                        {
                            "type": ContentBlockType.TEXT.value,
                            ContentBlockType.TEXT.value: str(result_content),
                        }
                    ],
                    tool_call_id=tool_call_id,
                )

            if all_matched:
                # All tool_calls have corresponding results, move results to tool_call_results
                state.tool_call_results.extend(results.values())
            else:
                # Still have incomplete tool calls, update results and keep in pending
                pending_item.results = results
                new_pending_tool_calls.append(pending_item)

        state.pending_tool_calls = new_pending_tool_calls
        return len(new_pending_tool_calls) > 0

    def _should_continue(self, state: CheckpointState) -> bool:
        """Determine whether execution should continue"""

        if len(state.pending_tool_calls) > 0:
            return False  # Has pending tool calls, need to wait
        if len(state.tool_call_results) > 0:
            return True
        if state.finished:
            return False  # Already finished
        if state.error:
            return False  # Has error
        if state.current_step >= state.max_steps:
            return False  # Reached max steps
        return True

    async def _run(
        self,
        messages: list[ChatMessage],
        additional_kwargs: dict | None = None,
    ) -> AsyncGenerator[AgentResponse, None]:
        """
        Checkpoint-based run method (without LangGraph)

        Args:
            messages: Input message list or input channel
            additional_kwargs: Additional parameters

        Yields:
            AgentResponse: Agent response object
        """
        # Initialize or load state
        async with CheckPointer[CheckpointState](
            self.thread_id, self.storage, self._init_state(), CheckpointState
        ) as state:
            state.messages.extend(messages)

            # Main execution loop
            while True:
                # 1. Update client tool call results and check if there are pending tool calls
                has_pending = await self._update_client_tool_results(state)
                if has_pending:
                    logger.info("@%s Has pending tool calls, waiting for client response", self.name)
                    return

                # 2. Process completed tool call results
                if len(state.tool_call_results) > 0:
                    async for response in self._process_tool_call_results(state):
                        yield response

                # 3. Check whether execution should continue
                if not self._should_continue(state):
                    logger.info("@%s Execution completed", self.name)
                    break

                # 4. Execute next step
                logger.info("@%s Executing step %d", self.name, state.current_step + 1)
                async for response in self._execute_step(state, additional_kwargs):
                    yield response

    @abstractmethod
    async def _step(
        self,
        messages: list[ChatMessage],
        additional_kwargs: dict | None = None,
    ) -> AsyncGenerator[AgentResponse, None]:
        """
        Execute a single step, subclasses must implement this method.

        Args:
            messages: Current message history.
            additional_kwargs: Additional parameters.

        Yields:
            AgentResponse: Response for current step, can yield multiple responses.
                - Last response with status FINISHED indicates completion.
                - Status ERROR indicates an error occurred.
                - Status RUNNING indicates continue execution.
        """
        raise NotImplementedError("Subclasses must implement this method")

    @abstractmethod
    async def _tool_call_handler(
        self,
        messages: list[ChatMessage],
        tool_calls: list[ChatMessage],
    ) -> AsyncGenerator[AgentResponse, None]:
        """
        Handle tool calls, subclasses must implement this method.

        Args:
            messages: Current message history.
            tool_calls: List of tool call messages.

        Yields:
            AgentResponse: Response for current step, can yield multiple responses.
                - Last response with status FINISHED indicates completion.
                - Status ERROR indicates an error occurred.
                - Status RUNNING indicates continue execution.
        """
        raise NotImplementedError("Subclasses must implement this method")
