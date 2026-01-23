"""Model system for Agent components."""

from enum import Enum
from typing import AsyncGenerator

from agentkit.trace import get_current_context
from .definition import ChatMessage, ModelParams
from cortex.model.utils import merge_delta_message
from pydantic import BaseModel

from cortex.model.provider import ModelProvider

__all__ = [
    "ModelAPI",
    "ModelMessage",
    "MessageType",
    "ModelParams",
]


class MessageType(str, Enum):
    """Message type enumeration"""

    DELTA = "delta"  # Streaming output
    ACCUMULATED = "accumulated"  # Accumulated output


class ModelMessage(BaseModel):
    """Model message"""

    message: ChatMessage
    message_type: MessageType


class ModelAPI:
    """Model API"""

    def __init__(self, provider: ModelProvider):
        self.provider = provider

    async def chat_completion(
        self,
        messages: list[ChatMessage],
        tools: list | None = None,
        log_file: str | None = None,
        trace_request: dict | None = None,
    ) -> ModelMessage:
        """Call model API, return accumulated message"""
        ctx = get_current_context()
        with ctx.llm_span(name="ModelAPI.chat_completion") as span:
            span.update_payload_data(
                request=trace_request
                or {
                    # "model_params": self.params(),
                    "messages": messages,
                    "tools": tools,
                },
                tools=tools,
            )
            response = await self.provider.chat_completion(
                messages=messages, tools=tools, log_file=log_file
            )
            span.update_payload_data(
                response=ModelMessage(
                    message=response, message_type=MessageType.ACCUMULATED
                ),
            )
            return ModelMessage(message=response, message_type=MessageType.ACCUMULATED)

    async def chat_completion_stream(
        self,
        messages: list[ChatMessage],
        tools: list | None = None,
        log_file: str | None = None,
        trace_request: dict | None = None,
    ) -> AsyncGenerator[ModelMessage, None]:
        """Call model API, return streaming messages"""
        accumulated_message = None
        async for event in self.provider.chat_completion_stream(
            messages=messages, tools=tools, log_file=log_file
        ):
            merged_dict = merge_delta_message(
                accumulated_message.model_dump() if accumulated_message else None,
                event.model_dump() if event else None,
            )
            accumulated_message = ChatMessage(**merged_dict)
            yield ModelMessage(message=event, message_type=MessageType.DELTA)

        # Yield the accumulated complete message
        if accumulated_message:
            yield ModelMessage(
                message=accumulated_message, message_type=MessageType.ACCUMULATED
            )

        ctx = get_current_context()
        with ctx.llm_span(name="ModelAPI.chat_completion_stream") as span:
            span.update_payload_data(
                request=trace_request
                or {
                    # "model_params": self.params(),
                    "messages": messages,
                    "tools": tools,
                },
            )
            span.update_payload_data(
                response=ModelMessage(
                    message=accumulated_message, message_type=MessageType.ACCUMULATED
                ),
            )
