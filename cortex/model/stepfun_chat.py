"""StepFun Chat API Client with reasoning support."""

import json
from typing import Any, AsyncGenerator, Iterable

import httpx
from pydantic import BaseModel


# StepFun API supported infer_kwargs parameters
SUPPORTED_INFER_KWARGS = frozenset([
    "temperature",       # 0.0-2.0, default 0.5
    "top_p",            # default 0.9
    "max_tokens",
    "n",                # default 1
    "stop",
    "frequency_penalty",  # 0.0-1.0, default 0
    "response_format",
    "reasoning_format",  # StepFun specific: "general" or "deepseek-style"
])


# ============ Structured Response Types ============

class Function(BaseModel):
    """Function call in tool_calls."""
    name: str | None = None
    arguments: str | None = None


class ToolCall(BaseModel):
    """Tool call object."""
    id: str | None = None
    index: int | None = None
    type: str = "function"
    function: Function | None = None


class Message(BaseModel):
    """Chat completion message with reasoning support."""
    role: str | None = None
    content: str | None = None
    reasoning: str | None = None  # StepFun specific
    tool_calls: list[ToolCall] | None = None


class Delta(BaseModel):
    """Streaming delta with reasoning support."""
    role: str | None = None
    content: str | None = None
    reasoning: str | None = None  # StepFun specific
    tool_calls: list[ToolCall] | None = None


class Choice(BaseModel):
    """Chat completion choice."""
    index: int = 0
    message: Message | None = None
    finish_reason: str | None = None


class StreamChoice(BaseModel):
    """Streaming choice with delta."""
    index: int = 0
    delta: Delta | None = None
    finish_reason: str | None = None


class Usage(BaseModel):
    """Token usage information."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletion(BaseModel):
    """Chat completion response."""
    id: str | None = None
    object: str = "chat.completion"
    created: int | None = None
    model: str | None = None
    choices: list[Choice] = []
    usage: Usage | None = None


class ChatCompletionChunk(BaseModel):
    """Streaming chat completion chunk."""
    id: str | None = None
    object: str = "chat.completion.chunk"
    created: int | None = None
    model: str | None = None
    choices: list[StreamChoice] = []
    usage: Usage | None = None


# ============ Client ============

class StepFunClient:
    """StepFun API client using httpx.
    
    Returns raw OpenAI format data, with an additional reasoning field in message.
    """

    DEFAULT_API_BASE = "https://api.stepfun.com"
    CHAT_COMPLETIONS_ENDPOINT = "/v1/chat/completions"

    def __init__(
        self,
        api_key: str,
        api_base: str | None = None,
        timeout: float = 120.0,
    ):
        self.api_key = api_key
        self.api_base = (api_base or self.DEFAULT_API_BASE).rstrip("/")
        self.timeout = timeout

    def _build_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _build_request_body(
        self,
        model: str,
        messages: Iterable[dict[str, Any]],
        tools: Iterable[dict[str, Any]] | None = None,
        infer_kwargs: dict[str, Any] | None = None,
        stream: bool = False,
    ) -> dict[str, Any]:
        """Build request body for chat completion."""
        body: dict[str, Any] = {
            "model": model,
            "messages": list(messages),
            "stream": stream,
        }

        if tools:
            body["tools"] = list(tools)

        # Add supported parameters from infer_kwargs
        if infer_kwargs:
            for key in SUPPORTED_INFER_KWARGS:
                if key in infer_kwargs:
                    body[key] = infer_kwargs[key]

        return body

    async def chat_completion(
        self,
        model: str,
        messages: Iterable[dict[str, Any]],
        tools: Iterable[dict[str, Any]] | None = None,
        infer_kwargs: dict[str, Any] | None = None,
    ) -> ChatCompletion:
        """Make a non-streaming chat completion request.
        
        Returns:
            ChatCompletion structured object, choices[0].message contains reasoning field
        """
        url = f"{self.api_base}{self.CHAT_COMPLETIONS_ENDPOINT}"
        body = self._build_request_body(
            model=model,
            messages=messages,
            tools=tools,
            infer_kwargs=infer_kwargs,
            stream=False,
        )

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                url,
                headers=self._build_headers(),
                json=body,
            )
            response.raise_for_status()
            data = response.json()

        return ChatCompletion.model_validate(data)

    async def chat_completion_stream(
        self,
        model: str,
        messages: Iterable[dict[str, Any]],
        tools: Iterable[dict[str, Any]] | None = None,
        infer_kwargs: dict[str, Any] | None = None,
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        """Make a streaming chat completion request.
        
        Yields:
            ChatCompletionChunk structured object, delta contains reasoning field
        """
        url = f"{self.api_base}{self.CHAT_COMPLETIONS_ENDPOINT}"
        body = self._build_request_body(
            model=model,
            messages=messages,
            tools=tools,
            infer_kwargs=infer_kwargs,
            stream=True,
        )

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                url,
                headers=self._build_headers(),
                json=body,
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue

                    data = line[6:]  # Remove "data: " prefix
                    if data == "[DONE]":
                        break

                    try:
                        chunk = json.loads(data)
                        yield ChatCompletionChunk.model_validate(chunk)
                    except json.JSONDecodeError:
                        continue
