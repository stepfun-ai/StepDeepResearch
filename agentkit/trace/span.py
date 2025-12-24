from datetime import datetime
from enum import Enum
try:  # Python 3.11+ has HTTPMethod in stdlib
    from http import HTTPMethod
except ImportError:  # pragma: no cover - fallback for Python 3.10
    class HTTPMethod(str, Enum):
        GET = "GET"
        POST = "POST"
        PUT = "PUT"
        DELETE = "DELETE"
        PATCH = "PATCH"
        HEAD = "HEAD"
        OPTIONS = "OPTIONS"
        CONNECT = "CONNECT"
        TRACE = "TRACE"
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field
from ulid import ULID

from .types import Error


class DataType(str, Enum):
    SPAN = "span"
    EVENT = "event"


class SpanType(str, Enum):
    LLM = "llm_span"
    TOOL = "tool_span"
    HTTP = "http_span"
    FUNCTION = "function_span"
    OTHER = "other_span"


class LLMSpanPayload(BaseModel):
    type: Literal[SpanType.LLM]
    request: Any = None
    response: Any = None
    error: Optional[Error] = None


class ToolSpanPayload(BaseModel):
    type: Literal[SpanType.TOOL]
    request: Any = None
    response: Any = None
    error: Optional[Error] = None


class FunctionSpanPayload(BaseModel):
    type: Literal[SpanType.FUNCTION]
    name: str = ""
    arguments: dict[str, Any] = Field(default_factory=dict)
    return_value: Any = None
    error: Optional[Error] = None


class HTTPSpanPayload(BaseModel):
    type: Literal[SpanType.HTTP]
    url: str
    method: Literal[
        HTTPMethod.GET,
        HTTPMethod.POST,
        HTTPMethod.PUT,
        HTTPMethod.DELETE,
        HTTPMethod.PATCH,
        HTTPMethod.HEAD,
        HTTPMethod.OPTIONS,
        HTTPMethod.CONNECT,
        HTTPMethod.TRACE,
    ]
    headers: dict[str, list[str]] = Field(default_factory=dict)
    body: Optional[str | bytes] = None
    response: Optional[str | bytes] = None
    error: Optional[Error] = None


class OtherSpanPayload(BaseModel):
    type: Literal[SpanType.OTHER]
    data: Any


class Span(BaseModel):
    # use ulid
    id: str = Field(default_factory=lambda: str(ULID()))
    name: str = Field(default="")
    data_type: Literal[DataType.SPAN] = DataType.SPAN
    start_time: datetime = Field(default_factory=datetime.now)
    end_time: Optional[datetime] = Field(default=None)
    tags: dict[str, str] = Field(default_factory=dict)
    payload: (
        LLMSpanPayload
        | ToolSpanPayload
        | FunctionSpanPayload
        | OtherSpanPayload
        | HTTPSpanPayload
        | None
    ) = Field(default=None)
    parent_id: Optional[str] = Field(default=None)  # Parent span ID
    trace_id: str
    app_name: str

    def update_payload(
        self,
        payload: (
            LLMSpanPayload
            | ToolSpanPayload
            | FunctionSpanPayload
            | HTTPSpanPayload
            | OtherSpanPayload
            | None
        ),
    ) -> "Span":
        """Update span payload."""
        self.payload = payload
        return self

    def update_payload_data(self, **kwargs) -> "Span":
        """
        Update specific fields in payload.

        Usage:
            span.update_payload_data(ret=result, error=None)
        """
        if self.payload is not None and hasattr(self.payload, "model_copy"):
            # Use pydantic's model_copy to update fields
            self.payload = self.payload.model_copy(update=kwargs)
        return self

    def add_tag(self, key: str, value: str) -> "Span":
        """Add or update a tag."""
        self.tags[key] = value
        return self

    def add_tags(self, tags: dict[str, str]) -> "Span":
        """Add or update multiple tags."""
        self.tags.update(tags)
        return self


class EventType(str, Enum):
    DELTA = "delta_event"
    OTHER = "other_event"


class DeltaEventPayload(BaseModel):
    type: Literal[EventType.DELTA]
    delta: Any


class OtherEventPayload(BaseModel):
    type: Literal[EventType.OTHER]
    data: Any


class Event(BaseModel):
    id: str = Field(default_factory=lambda: str(ULID()))
    name: str = Field(default="")
    data_type: Literal[DataType.EVENT] = DataType.EVENT
    timestamp: datetime = Field(default_factory=datetime.now)
    tags: dict[str, str] = Field(default_factory=dict)
    payload: DeltaEventPayload | OtherEventPayload
    parent_id: Optional[str] = Field(default=None)  # Parent span ID
    trace_id: str
    app_name: str
