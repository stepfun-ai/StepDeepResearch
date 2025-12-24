"""StepFun Model Provider implementation."""

import asyncio
import logging
import re
from typing import Any, AsyncGenerator, Callable, Awaitable

import httpx

from .definition import ChatMessage
from cortex.model.definition import ChatToolCall, ContentBlockType, ExtraInfo, MessageRole, ModelParams

from cortex.model.provider import ModelProvider

from .stepfun_chat import (
    ChatCompletion,
    ChatCompletionChunk,
    Message,
    Delta,
    StepFunClient,
)

# Regex pattern for matching <think>...</think> tags
THINK_TAG_PATTERN = re.compile(r"<think>(.*?)</think>", re.DOTALL)


class StepFunModelProvider(ModelProvider):
    """Model provider for StepFun API with reasoning support."""

    # Constants for matching tags
    _THINK_OPEN_TAG = "<think>"
    _THINK_CLOSE_TAG = "</think>"

    def __init__(self, model_params: ModelParams):
        self.model_params = model_params
        # Used to track <think> tag state in streaming scenarios
        self._stream_in_think_tag = False
        # Used to buffer potentially incomplete tags
        self._stream_tag_buffer = ""
        self._logger = logging.getLogger(__name__)

    async def _call_with_retry(
        self,
        description: str,
        func: Callable[[], Awaitable[Any]],
        max_attempts: int = 5,
    ) -> Any:
        """Retry wrapper with linear backoff (2s,4s,6s,8s)."""
        last_exc: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                return await func()
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                detail = ""
                if isinstance(exc, httpx.HTTPStatusError):
                    try:
                        detail = f" body={exc.response.text}"
                    except Exception:
                        detail = ""
                if attempt >= max_attempts:
                    break
                delay = 2 * attempt
                self._logger.warning(
                    "StepFun %s failed (attempt %s/%s): %s%s; retrying in %ss",
                    description,
                    attempt,
                    max_attempts,
                    exc,
                    detail,
                    delay,
                )
                await asyncio.sleep(delay)
        assert last_exc is not None
        raise last_exc

    async def _stream_with_retry(
        self,
        description: str,
        stream_factory: Callable[[], AsyncGenerator[Any, None]],
        max_attempts: int = 5,
    ) -> AsyncGenerator[Any, None]:
        """Retry wrapper for streaming calls."""
        last_exc: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                async for chunk in stream_factory():
                    yield chunk
                return
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt >= max_attempts:
                    break
                delay = 2 * attempt
                self._logger.warning(
                    "StepFun %s stream failed (attempt %s/%s): %s; retrying in %ss",
                    description,
                    attempt,
                    max_attempts,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
        assert last_exc is not None
        raise last_exc

    def _create_client(self) -> StepFunClient:
        """Create a StepFunClient from model params."""
        api_key = self.model_params.explicit_api_key
        if not api_key:
            raise ValueError("StepFun API key is required")

        transport_timeout = None
        if isinstance(self.model_params.infer_kwargs, dict):
            transport_timeout = (
                self.model_params.infer_kwargs.get("request_timeout")
                or self.model_params.infer_kwargs.get("timeout")
            )

        return StepFunClient(
            api_key=api_key,
            api_base=self.model_params.explicit_api_base,
            timeout=float(transport_timeout) if transport_timeout else 120.0,
        )

    def _chat_messages_to_openai(
        self,
        messages: list[ChatMessage] | list[dict],
    ) -> list[dict[str, Any]]:
        """Convert ChatMessage list to OpenAI format messages.
        
        References openai_model.py's chat_message_to_openai_messages implementation,
        handles complex ChatMessage formats (including content blocks, tool results, etc.).
        """
        openai_messages = []
        for message in messages:
            if isinstance(message, dict):
                message = ChatMessage(**message)

            if isinstance(message.content, str) or message.content is None:
                new_message = message.model_dump()
            elif isinstance(message.content, list):
                new_content = []
                for block in message.content:
                    if block["type"] == ContentBlockType.TEXT.value:
                        # Merge consecutive text blocks
                        if (
                            new_content
                            and new_content[-1]["type"] == ContentBlockType.TEXT.value
                        ):
                            new_content[-1]["text"] += block.get("text", block.get(block["type"], ""))
                        else:
                            new_content.append(block)

                    elif block["type"] == ContentBlockType.THINK.value:
                        # Convert thinking content to text wrapped in <think> tags
                        think_content = block.get(block["type"], "")
                        if (
                            new_content
                            and new_content[-1]["type"] == ContentBlockType.TEXT.value
                        ):
                            new_content[-1]["text"] += f"<think>{think_content}</think>"
                        else:
                            new_content.append({
                                "type": ContentBlockType.TEXT.value,
                                "text": f"<think>{think_content}</think>",
                            })

                    elif block["type"] == ContentBlockType.REDACTED_THINK.value:
                        redacted_content = block.get("data", "")
                        if (
                            new_content
                            and new_content[-1]["type"] == ContentBlockType.TEXT.value
                        ):
                            new_content[-1]["text"] += f"<redacted_think>{redacted_content}</redacted_think>"
                        else:
                            new_content.append({
                                "type": ContentBlockType.TEXT.value,
                                "text": f"<redacted_think>{redacted_content}</redacted_think>",
                            })

                    elif block["type"] == ContentBlockType.TOOLRESULT.value:
                        # Tool result requires special handling
                        tool_block_content = block.get("content", [])
                        if isinstance(tool_block_content, str):
                            tool_block_content = [{
                                "type": ContentBlockType.TEXT.value,
                                "text": tool_block_content,
                            }]
                        
                        # First text as tool role message
                        openai_messages.append({
                            "role": message.role,
                            "content": tool_block_content[0].get("text", "") if tool_block_content else "",
                            "tool_call_id": block.get("tool_use_id", message.tool_call_id),
                        })
                        
                        # Remaining content as user message
                        if len(tool_block_content) > 1:
                            extra_message = {
                                "role": MessageRole.USER.value,
                                "content": tool_block_content[1:],
                            }
                            openai_messages.append(extra_message)
                    else:
                        # Other block types (e.g., image_url, etc.) keep as is
                        new_content.append(block)

                new_message = message.model_dump()
                new_message["content"] = new_content

            # Handle tool_calls
            if message.tool_calls:
                normalized_tool_calls = []
                for tc in message.tool_calls:
                    tc_dict = tc.model_dump()
                    # Ensure function and arguments are present for API validation
                    func = tc_dict.get("function") or {}
                    if func.get("arguments") in (None, ""):
                        func["arguments"] = "{}"
                    if not func.get("name"):
                        func["name"] = tc_dict.get("id") or "unknown"
                    tc_dict["function"] = func
                    normalized_tool_calls.append(tc_dict)
                new_message["tool_calls"] = normalized_tool_calls
                openai_messages.append(new_message)
            elif new_message.get("content"):
                openai_messages.append(new_message)

        return openai_messages

    def _extract_think_from_content(self, content: str | None) -> tuple[str | None, str | None]:
        """Extract content from <think>...</think> tags in content.
        
        Args:
            content: Original content string
            
        Returns:
            tuple[reasoning, remaining_content]: 
            - reasoning: Content inside <think> tags, or None if not present
            - remaining_content: Content after removing <think> tags
        """
        if not content or not isinstance(content, str):
            return None, content
        
        # Find all <think>...</think> tags
        matches = THINK_TAG_PATTERN.findall(content)
        if not matches:
            return None, content
        
        # Merge all think content
        reasoning = "".join(matches)
        
        # Remove all <think>...</think> tags
        remaining_content = THINK_TAG_PATTERN.sub("", content).strip()
        
        return reasoning if reasoning else None, remaining_content if remaining_content else None

    def _message_to_chat_message(self, message: Message) -> ChatMessage:
        """Convert StepFun Message (with reasoning) to ChatMessage.
        
        StepFun message format:
        - role: str
        - content: str | None (may contain <think>...</think> tags)
        - reasoning: str | None (StepFun specific, may be empty)
        - tool_calls: list[ToolCall] | None
        
        reasoning may be in the standalone reasoning field or in <think> tags in content.
        """
        reasoning = message.reasoning
        content = message.content

        # If reasoning field is empty, try to extract <think> tag content from content
        if not reasoning and isinstance(content, str):
            extracted_reasoning, remaining_content = self._extract_think_from_content(content)
            if extracted_reasoning:
                reasoning = extracted_reasoning
                content = remaining_content

        # Process reasoning and content separately, build content blocks
        new_content: list[dict] = []
        
        # Handle reasoning field, convert to thinking content block
        if reasoning:
            new_content.append({
                "type": ContentBlockType.THINK.value,
                ContentBlockType.THINK.value: reasoning,
            })
        
        # Handle content field
        if isinstance(content, str) and content:
            new_content.append({
                "type": ContentBlockType.TEXT.value,
                "text": content,
            })
        elif isinstance(content, list):
            new_content.extend(content)

        # Determine final content: use list if there are blocks, otherwise keep original value
        final_content: str | list | None
        if new_content:
            final_content = new_content
        else:
            final_content = content  # Could be None or empty string

        # Handle tool_calls
        tool_calls = None
        if message.tool_calls:
            tool_calls = [
                ChatToolCall(**tc.model_dump(exclude_none=True))
                for tc in message.tool_calls
            ]

        return ChatMessage(
            role=message.role,
            content=final_content,
            tool_calls=tool_calls,
        )

    def _process_stream_content_for_think(self, content: str | None) -> tuple[str | None, str | None]:
        """Process content in streaming scenarios to identify <think> tags.
        
        Uses character-level state machine to handle <think> tags spanning multiple chunks:
        - Tags may be split across chunks (e.g., '<thi' + 'nk>')
        - Uses _stream_tag_buffer to cache potentially incomplete tag fragments
        - Uses _stream_in_think_tag to track whether inside a <think> tag
        
        Args:
            content: Current chunk's content
            
        Returns:
            tuple[reasoning, text_content]:
            - reasoning: If inside <think> tag, returns current reasoning content
            - text_content: If not inside <think> tag, returns plain text content
        """
        if not content:
            return None, None
        
        # Merge cached content with new content
        buffer = self._stream_tag_buffer + content
        self._stream_tag_buffer = ""
        
        reasoning_parts = []
        text_parts = []
        
        i = 0
        while i < len(buffer):
            if not self._stream_in_think_tag:
                # Not inside <think> tag, look for opening tag
                # Check if this could be the start of a <think> tag
                if buffer[i] == '<':
                    # Check if remaining content is sufficient to determine
                    remaining = buffer[i:]
                    if remaining.startswith(self._THINK_OPEN_TAG):
                        # Complete <think> tag
                        self._stream_in_think_tag = True
                        i += len(self._THINK_OPEN_TAG)
                    elif self._THINK_OPEN_TAG.startswith(remaining):
                        # Possibly incomplete <think> tag (e.g., '<thi')
                        # Cache it and wait for next chunk
                        self._stream_tag_buffer = remaining
                        break
                    else:
                        # Not a <think> tag, treat as plain text
                        text_parts.append(buffer[i])
                        i += 1
                else:
                    text_parts.append(buffer[i])
                    i += 1
            else:
                # Inside <think> tag, look for closing tag
                if buffer[i] == '<':
                    # Check if this could be a </think> tag
                    remaining = buffer[i:]
                    if remaining.startswith(self._THINK_CLOSE_TAG):
                        # Complete </think> tag
                        self._stream_in_think_tag = False
                        i += len(self._THINK_CLOSE_TAG)
                    elif self._THINK_CLOSE_TAG.startswith(remaining):
                        # Possibly incomplete </think> tag
                        self._stream_tag_buffer = remaining
                        break
                    else:
                        # Not a </think> tag, treat as reasoning content
                        reasoning_parts.append(buffer[i])
                        i += 1
                else:
                    reasoning_parts.append(buffer[i])
                    i += 1
        
        reasoning = "".join(reasoning_parts) if reasoning_parts else None
        text_content = "".join(text_parts) if text_parts else None
        
        return reasoning, text_content

    def _delta_to_chat_message(
        self,
        delta: Delta,
        chunk_id: str | None = None,
    ) -> ChatMessage:
        """Convert StepFun Delta (with reasoning) to ChatMessage.
        
        StepFun stream delta format:
        - role: str | None
        - content: str | None (may contain <think>...</think> tag fragments)
        - reasoning: str | None (StepFun specific, may be empty)
        - tool_calls: list[ToolCall] | None
        
        reasoning may be in the standalone reasoning field or in <think> tags in content.
        In streaming scenarios, <think> tags may span multiple chunks.
        """
        reasoning = delta.reasoning
        content = delta.content

        # If reasoning field is empty, try to extract <think> tag content from content
        if not reasoning and isinstance(content, str):
            extracted_reasoning, remaining_content = self._process_stream_content_for_think(content)
            reasoning = extracted_reasoning
            content = remaining_content

        # Process reasoning and content separately
        new_content: list[dict] = []
        
        if reasoning:
            new_content.append({
                "type": ContentBlockType.THINK.value,
                ContentBlockType.THINK.value: reasoning,
            })
        
        if isinstance(content, str) and content:
            new_content.append({
                "type": ContentBlockType.TEXT.value,
                "text": content,
            })

        # Determine final content
        final_content: str | list | None
        if new_content:
            final_content = new_content
        else:
            final_content = None  # Return None when streaming has no content

        # Handle tool_calls
        tool_calls = None
        if delta.tool_calls:
            tool_calls = [
                ChatToolCall(**tc.model_dump(exclude_none=True))
                for tc in delta.tool_calls
            ]

        return ChatMessage(
            id=chunk_id,
            role=delta.role,
            content=final_content,
            tool_calls=tool_calls,
        )

    async def chat_completion(
        self,
        messages: list[ChatMessage],
        tools: list | None = None,
        log_file: str | None = None,
    ) -> ChatMessage:
        """Make a non-streaming chat completion request."""
        client = self._create_client()
        openai_messages = self._chat_messages_to_openai(messages)
        infer_kwargs = dict(self.model_params.infer_kwargs or {})
        infer_kwargs.pop("request_timeout", None)
        infer_kwargs.pop("timeout", None)

        response: ChatCompletion = await self._call_with_retry(
            description="chat_completion",
            func=lambda: client.chat_completion(
                model=self.model_params.name,
                messages=openai_messages,
                tools=tools,
                infer_kwargs=infer_kwargs,
            ),
        )

        # Extract and convert message
        if not response.choices:
            return ChatMessage()

        choice = response.choices[0]
        if not choice.message:
            return ChatMessage()

        result = self._message_to_chat_message(choice.message)

        # Add usage and finish_reason
        result.extra_info = ExtraInfo()
        if response.usage:
            result.extra_info["usage"] = response.usage.model_dump()
        if choice.finish_reason:
            result.extra_info["finish_reason"] = choice.finish_reason

        return result

    async def chat_completion_stream(
        self,
        messages: list[ChatMessage],
        tools: list | None = None,
        log_file: str | None = None,
    ) -> AsyncGenerator[ChatMessage, None]:
        """Make a streaming chat completion request."""
        client = self._create_client()
        openai_messages = self._chat_messages_to_openai(messages)
        infer_kwargs = dict(self.model_params.infer_kwargs or {})
        infer_kwargs.pop("request_timeout", None)
        infer_kwargs.pop("timeout", None)

        async def stream_factory() -> AsyncGenerator[ChatCompletionChunk, None]:
            # Reset streaming state each attempt
            self._stream_in_think_tag = False
            self._stream_tag_buffer = ""
            async for chunk in client.chat_completion_stream(
                model=self.model_params.name,
                messages=openai_messages,
                tools=tools,
                infer_kwargs=infer_kwargs,
            ):
                yield chunk

        async for chunk in self._stream_with_retry(
            description="chat_completion_stream",
            stream_factory=stream_factory,
        ):
            chunk: ChatCompletionChunk
            if not chunk.choices:
                continue

            choice = chunk.choices[0]
            if not choice.delta:
                continue

            result = self._delta_to_chat_message(choice.delta, chunk.id)

            # Skip this chunk if no valid content
            if result.content is None and result.role is None and result.tool_calls is None:
                continue

            # Add usage and finish_reason (if present)
            if chunk.usage or choice.finish_reason:
                result.extra_info = ExtraInfo()
                if chunk.usage:
                    result.extra_info["usage"] = chunk.usage.model_dump()
                if choice.finish_reason:
                    result.extra_info["finish_reason"] = choice.finish_reason

            yield result
