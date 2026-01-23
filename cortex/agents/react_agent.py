"""ReActAgent - Specialized Agent for executing ReAct pattern, capable of calling tools to complete tasks."""

import logging
from typing import AsyncGenerator
from uuid import uuid4

from cortex.agents.base_agent import BaseAgent
from cortex.agents.base_step_agent import BaseStepAgent
from cortex.agents.types import (
    AgentConfig,
    AgentMessageType,
    AgentResponse,
    AgentRunningStatus,
)
from cortex.context import BaseContext
from cortex.context.simple_context import SimpleContext
from cortex.model import ChatMessage, MessageType, ModelAPI
from cortex.model.provider import ModelProvider
from cortex.tools.toolset import ToolSet

logger = logging.getLogger(__name__)


def _check_if_finished(response_message: ChatMessage | None) -> bool:
    """Check if task is finished based on model output."""
    if not response_message:
        return False

    # If there are tool calls, continue execution
    if BaseAgent.has_tool_call(response_message):
        return False

    return True


async def process_messages(
    system_prompt: str | None,
    messages: list[ChatMessage],
    toolset: ToolSet,
    model_api: ModelAPI,
    use_stream: bool,
    trace_messages: list[ChatMessage] | None = None,
) -> AsyncGenerator[AgentResponse, None]:
    if not system_prompt:
        system_prompt = """You are a professional task execution assistant capable of calling tools to complete tasks.
Your task is:
1. Understand the task proposed by the user
2. Use the provided tools to complete the task
3. Call tools multiple times to complete complex tasks
4. Provide detailed explanations of task execution process
5. Provide detailed task execution results

Please ensure:
- For complex tasks, use tools step by step
- Provide clear explanations of task execution steps
- Verify the correctness of task execution results
- When the task is complete, clearly state "Task completed"
"""

    # Prepare message list
    infer_messages = messages.copy()
    if system_prompt and not any(
        msg.role == "system" and msg.content == system_prompt for msg in infer_messages
    ):
        infer_messages.insert(0, ChatMessage(role="system", content=system_prompt))

    # Get all tool schemas
    tool_schemas = toolset.get_all_schemas()

    # Convert tool schemas to model-usable format
    tools_for_model = []
    for tool_name, schema in tool_schemas.items():
        tools_for_model.append(
            {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": schema.description,
                    "parameters": schema.parameters,
                },
            }
        )

    # Call model
    trace_request = None
    if trace_messages is not None:
        trace_infer_messages = trace_messages.copy()
        if system_prompt and not any(
            msg.role == "system" and msg.content == system_prompt
            for msg in trace_infer_messages
        ):
            trace_infer_messages.insert(
                0, ChatMessage(role="system", content=system_prompt)
            )
        trace_request = {
            "messages": trace_infer_messages,
            "sent_messages": infer_messages,
            "tools": tools_for_model if tools_for_model else None,
        }

    if use_stream:
        # Streaming output mode
        delta_count = 0
        response_message = None

        async for model_msg in model_api.chat_completion_stream(
            messages=infer_messages,
            tools=tools_for_model if tools_for_model else None,
            trace_request=trace_request,
        ):
            delta_count += 1
            event = model_msg.message
            response_message = (
                event  # Save last message (model yields accumulated_message at end)
            )

            if model_msg.message_type == MessageType.DELTA:
                # This is a delta event, yield directly
                delta_response = AgentResponse(
                    message=event,
                    status=AgentRunningStatus.RUNNING.value,
                    message_type=AgentMessageType.STREAM.value,
                )
                yield delta_response

    else:
        # Non-streaming output mode
        model_msg = await model_api.chat_completion(
            messages=infer_messages,
            tools=tools_for_model if tools_for_model else None,
            trace_request=trace_request,
        )
        response_message = model_msg.message

    is_finished = _check_if_finished(response_message)
    response_status = (
        AgentRunningStatus.FINISHED.value
        if is_finished
        else AgentRunningStatus.RUNNING.value
    )
    message_type = (
        AgentMessageType.FINAL.value
        if is_finished
        else AgentMessageType.ACCUMULATED.value
    )

    model_response = AgentResponse(
        message=response_message,
        status=response_status,
        message_type=message_type,
    )
    yield model_response


class ReActAgent(BaseStepAgent):
    """ReActAgent - Specialized Agent for executing ReAct pattern, capable of calling tools to complete tasks.

    Features:
    - Can call tools to complete tasks
    - Can call tools multiple times to complete complex tasks
    - Can provide detailed explanations of task execution process
    - Can provide detailed task execution results
    """

    def __init__(
        self,
        context: BaseContext | None = None,
        provider: ModelProvider | None = None,
        config: AgentConfig | None = None,
        toolset: ToolSet | None = None,
    ):
        if context is None:
            context = SimpleContext(uuid4().hex)
        # If toolset is not provided, create default math toolset
        if toolset is None:
            # Note: Cannot call async functions directly here, need to initialize externally
            raise ValueError(
                "ReActAgent requires a toolset, please use init_react_tools() to create one"
            )

        super().__init__(
            context=context, provider=provider, config=config, toolset=toolset
        )

    async def _step(
        self,
        messages: list[ChatMessage],
        additional_kwargs: dict | None = None,
    ) -> AsyncGenerator[AgentResponse, None]:
        """
        Execute single step operation, can yield multiple responses.

        Args:
            messages: Current message history
            additional_kwargs: Additional parameters

        Yields:
            AgentResponse: Response for current step
        """

        trace_messages: list[ChatMessage] | None = None
        try:
            trace_messages = list(self.context.get_all())
        except Exception:  # noqa: BLE001
            trace_messages = None

        if trace_messages is not None and self._force_final_answer_enabled and self._force_prompt_inserted:
            prompt_message = self._make_force_final_answer_message()
            if not trace_messages or not (
                getattr(trace_messages[-1], "role", None) == prompt_message.role
                and getattr(trace_messages[-1], "content", None) == prompt_message.content
            ):
                trace_messages.append(prompt_message)

        async for response_message in process_messages(
            self.system_prompt,
            messages,
            self.toolset(),
            self.model_api(),
            getattr(self.model, "infer_kwargs", {}).get("stream", False),
            trace_messages=trace_messages,
        ):
            try:
                yield response_message

                # Only check and execute tool calls for non-STREAM types (i.e., ACCUMULATED or FINAL)
                # In streaming output, STREAM type delta messages don't contain complete tool_call
                if response_message.message_type == AgentMessageType.STREAM.value:
                    continue

                # Check for tool calls and execute
                tool_result_messages = []
                message = response_message.message
                if self.has_tool_call(message):
                    tool_result_messages = await self.run_tool_call(message)
                    if tool_result_messages:
                        logger.info(
                            "@%s Detected %s tool call results",
                            self.name,
                            len(tool_result_messages),
                        )

                    # Yield tool result responses
                    for tool_result_msg in tool_result_messages:
                        tool_response = AgentResponse(
                            message=tool_result_msg,
                            status=AgentRunningStatus.RUNNING.value,
                            message_type=AgentMessageType.FINAL.value,
                        )
                        yield tool_response

            except Exception as e:
                err_text = str(e) or repr(e)
                logger.error("@%s Execution error: %s", self.name, err_text, exc_info=True)
                error_response = AgentResponse(
                    message=None,
                    status=AgentRunningStatus.ERROR.value,
                    error_msg=err_text,
                    message_type=AgentMessageType.FINAL.value,
                )
                yield error_response
