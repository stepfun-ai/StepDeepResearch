"""AskInputAgent - Fixed-flow Agent for asking user input and repeating what the user says"""

import json
import logging
import uuid
from typing import AsyncGenerator
from uuid import uuid4

from cortex.model.definition import ChatMessage, ChatToolCall, ContentBlockType, Function

from cortex.agents.base_agent import BaseAgent
from cortex.agents.input.input import InputChannel
from cortex.agents.types import (
    AgentConfig,
    AgentMessageType,
    AgentResponse,
    AgentRunningStatus,
)
from cortex.context import BaseContext, make_simple_context
from cortex.model import ModelParams
from cortex.tools.client_tool import ClientTool
from cortex.tools.toolset import ToolSet
from cortex.tools.types import ToolType

logger = logging.getLogger(__name__)


async def init_ask_input_tools() -> ToolSet:
    """Initialize ask_input toolset"""
    toolset = ToolSet()

    # Register ask_input tool (ClientTool)
    ask_input_tool = ClientTool(
        name="ask_input",
        description="Ask user for input. Used for scenarios requiring user interaction such as obtaining user feedback, confirmation, modification suggestions, etc. Parameters: prompt (required) - prompt message to display to the user; context (optional) - context information to help users understand the current situation.",
        tool_type=ToolType.ASK_INPUT,
        channel=toolset.channel,
        timeout=300.0,  # User input may take a long time
        client_params={
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Prompt message to display to the user, explaining what the user needs to do (confirm, modify, provide information, etc.)",
                },
                "context": {
                    "type": "string",
                    "description": "Context information to help users understand the current situation, such as current plan content, items that need confirmation, etc.",
                },
            },
            "required": ["prompt"],
        },
    )
    toolset.register(ask_input_tool)
    logger.info("Registered ask_input tool")

    return toolset


class AskInputAgent(BaseAgent):
    """AskInputAgent - Fixed-flow Agent for asking user input and repeating what the user says

    Fixed flow:
    1. Send a function call with tool_name as ask_input
    2. After receiving ask_input result, send a message repeating what the user said
    """

    def __init__(
        self, context: BaseContext, config: AgentConfig, toolset: ToolSet | None = None
    ):
        super().__init__(config=config, toolset=toolset)
        self.context = context

    async def _run(
        self,
        messages: list[ChatMessage] | InputChannel[ChatMessage],
        additional_kwargs: dict | None = None,
    ) -> AsyncGenerator[AgentResponse, None]:
        """
        Run agent, execute fixed flow

        Args:
            messages: Input message list or input channel
            additional_kwargs: Additional parameters

        Yields:
            AgentResponse: Agent response object
        """
        try:
            # Step 1: Create a ChatMessage containing tool_calls, call ask_input tool
            tool_call_id = f"call_{uuid.uuid4().hex[:8]}"

            # Create tool call arguments
            tool_args = json.dumps({"prompt": "Please enter some content"})

            # Create ChatToolCall
            tool_call = ChatToolCall(
                id=tool_call_id,
                function=Function(
                    name="ask_input",
                    arguments=tool_args,
                ),
            )

            # Create ChatMessage containing tool_calls
            tool_call_message = ChatMessage(
                role="assistant",
                tool_calls=[tool_call],
            )

            # Yield tool call response
            tool_call_response = AgentResponse(
                message=tool_call_message,
                status=AgentRunningStatus.RUNNING.value,
                message_type=AgentMessageType.FINAL.value,
            )
            yield tool_call_response

            # Execute tool call
            tool_result_messages = await self.run_tool_call(tool_call_message)

            if not tool_result_messages:
                error_response = AgentResponse(
                    message=None,
                    status=AgentRunningStatus.ERROR.value,
                    error_msg="ask_input tool call failed, no result returned",
                    message_type=AgentMessageType.FINAL.value,
                )
                yield error_response
                return

            # Yield tool result response
            tool_result_message = tool_result_messages[0]
            tool_result_response = AgentResponse(
                message=tool_result_message,
                status=AgentRunningStatus.RUNNING.value,
                message_type=AgentMessageType.FINAL.value,
            )
            yield tool_result_response

            # Step 2: Get user input from tool result and repeat what the user said
            user_input = None
            if tool_result_message.content:
                # Extract user input
                if isinstance(tool_result_message.content, list):
                    for block in tool_result_message.content:
                        if isinstance(block, dict):
                            text_content = block.get(
                                ContentBlockType.TEXT.value
                            ) or block.get("text")
                            if text_content:
                                user_input = str(text_content)
                                break
                        elif isinstance(block, str):
                            user_input = block
                            break
                elif isinstance(tool_result_message.content, str):
                    user_input = tool_result_message.content

            if user_input is None:
                user_input = "Failed to get user input"

            # Create message repeating what the user said
            repeat_message = ChatMessage(
                role="assistant",
                content=[
                    {
                        "type": ContentBlockType.TEXT.value,
                        ContentBlockType.TEXT.value: f"You said: {user_input}",
                    }
                ],
            )

            # Yield final response
            final_response = AgentResponse(
                message=repeat_message,
                status=AgentRunningStatus.FINISHED.value,
                message_type=AgentMessageType.FINAL.value,
            )
            yield final_response

        except Exception as e:
            logger.error(f"@{self.name} execution error: {e}", exc_info=True)
            error_response = AgentResponse(
                message=None,
                status=AgentRunningStatus.ERROR.value,
                error_msg=str(e),
                message_type=AgentMessageType.FINAL.value,
            )
            yield error_response


async def make_ask_input_agent(
    config: AgentConfig, context_id: str | None = None
) -> BaseAgent:
    """Create AskInputAgent"""
    toolset = await init_ask_input_tools()
    context = make_simple_context(context_id)
    if context_id is None:
        context_id = uuid4().hex
    return AskInputAgent(context=context, config=config, toolset=toolset)


def get_ask_input_agent_config() -> AgentConfig:
    """Get AskInputAgent configuration"""
    return AgentConfig(
        name="AskInputAgent",
        description="Fixed-flow Agent for asking user input and repeating what the user says. Does not require model calls.",
        system_prompt=None,  # No system prompt needed
        model=ModelParams(
            name="gpt-4o-mini",  # Although model calls are not needed, configuration requires it
            infer_kwargs={"max_tokens": 100, "temperature": 0.7, "stream": False},
        ),
    )
