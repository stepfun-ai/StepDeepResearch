"""
Builder pattern for constructing Span and Event objects.
"""

from datetime import datetime
from typing import Any, Optional

from ulid import ULID

from .default import get_default
from .span import (
    Event,
    EventType,
    FunctionSpanPayload,
    HTTPSpanPayload,
    OtherEventPayload,
    Span,
    SpanType,
)


class SpanBuilder:
    """
    Span builder providing a fluent API to construct complex Spans.

    Usage:
        span = (SpanBuilder()
                .with_name("my_operation")
                .with_app_name("my_app")
                .with_type(SpanType.FUNCTION)
                .with_tag("user", "alice")
                .with_parent(parent_span)
                .build())
    """

    def __init__(self, trace_id: Optional[str] = None, app_name: Optional[str] = None):
        self._trace_id = trace_id or str(ULID())
        self._app_name = app_name or get_default("app_name")
        self._id = str(ULID())
        self._name = ""
        self._start_time = datetime.now()
        self._end_time = None
        self._tags: dict[str, str] = {}
        self._payload: Optional[Any] = None
        self._parent_id: Optional[str] = None

    def with_id(self, span_id: str) -> "SpanBuilder":
        """Set span ID."""
        self._id = span_id
        return self

    def with_name(self, name: str) -> "SpanBuilder":
        """Set span name."""
        self._name = name
        return self

    def with_trace_id(self, trace_id: str) -> "SpanBuilder":
        """Set trace ID."""
        self._trace_id = trace_id
        return self

    def with_start_time(self, start_time: datetime) -> "SpanBuilder":
        """Set start time."""
        self._start_time = start_time
        return self

    def with_end_time(self, end_time: datetime) -> "SpanBuilder":
        """Set end time."""
        self._end_time = end_time
        return self

    def with_tag(self, key: str, value: str) -> "SpanBuilder":
        """Add a tag."""
        self._tags[key] = value
        return self

    def with_tags(self, tags: dict[str, str]) -> "SpanBuilder":
        """Add multiple tags."""
        self._tags.update(tags)
        return self

    def with_payload(self, payload: Any) -> "SpanBuilder":
        """Set payload."""
        self._payload = payload
        return self

    def with_parent(self, parent: Span) -> "SpanBuilder":
        """Set parent span."""
        self._parent_id = parent.id
        # Automatically inherit trace_id from parent span
        if parent:
            self._trace_id = parent.trace_id
        return self

    def with_parent_id(self, parent_id: str) -> "SpanBuilder":
        """Set parent span ID."""
        self._parent_id = parent_id
        return self

    def with_app_name(self, app_name: str) -> "SpanBuilder":
        """Set application name."""
        self._app_name = app_name
        return self

    def build(self) -> Span:
        """Build Span object."""
        span = Span(
            id=self._id,
            name=self._name,
            trace_id=self._trace_id,
            app_name=self._app_name,
            start_time=self._start_time,
            end_time=self._end_time,
            tags=self._tags,
            payload=self._payload,
            parent_id=self._parent_id,
        )
        return span


class FunctionSpanBuilder(SpanBuilder):
    """
    Specialized builder for Function Spans.

    Usage:
        span = (FunctionSpanBuilder()
                .with_name("calculate")
                .with_function_name("calculate_total")
                .with_arguments({"x": 1, "y": 2})
                .with_return_value(3)
                .build())
    """

    def __init__(self, trace_id: Optional[str] = None, app_name: Optional[str] = None):
        super().__init__(trace_id, app_name)
        self._function_name = ""
        self._arguments: dict[str, Any] = {}
        self._ret: Any = None
        self._error = None

    def with_function_name(self, name: str) -> "FunctionSpanBuilder":
        """Set function name."""
        self._function_name = name
        if not self._name:
            self._name = name
        return self

    def with_arguments(self, arguments: dict[str, Any]) -> "FunctionSpanBuilder":
        """Set function arguments."""
        self._arguments = arguments
        return self

    def with_return_value(self, ret: Any) -> "FunctionSpanBuilder":
        """Set return value."""
        self._ret = ret
        return self

    def with_error(self, code: int, message: str) -> "FunctionSpanBuilder":
        """Set error information."""
        self._error = {"code": code, "message": message}
        return self

    def build(self) -> Span:
        """Build Function Span."""
        payload = FunctionSpanPayload(
            type=SpanType.FUNCTION,
            name=self._function_name,
            arguments=self._arguments,
            ret=self._ret,
            error=self._error,
        )
        self._payload = payload
        return super().build()


class HTTPSpanBuilder(SpanBuilder):
    """
    Specialized builder for HTTP Spans.

    Usage:
        span = (HTTPSpanBuilder()
                .with_url("https://api.example.com/users")
                .with_method("GET")
                .with_header("Authorization", "Bearer token")
                .with_response('{"users": []}')
                .build())
    """

    def __init__(self, trace_id: Optional[str] = None, app_name: Optional[str] = None):
        super().__init__(trace_id, app_name)
        self._url = ""
        self._method = "GET"
        self._headers: dict[str, list[str]] = {}
        self._body: Optional[str | bytes] = None
        self._response: Optional[str | bytes] = None
        self._error = None

    def with_url(self, url: str) -> "HTTPSpanBuilder":
        """Set URL."""
        self._url = url
        if not self._name:
            self._name = f"{self._method} {url}"
        return self

    def with_method(self, method: str) -> "HTTPSpanBuilder":
        """Set HTTP method."""
        self._method = method
        if self._url:
            self._name = f"{method} {self._url}"
        return self

    def with_header(self, key: str, value: str | list[str]) -> "HTTPSpanBuilder":
        """Add HTTP header."""
        if isinstance(value, str):
            value = [value]
        self._headers[key] = value
        return self

    def with_headers(self, headers: dict[str, list[str]]) -> "HTTPSpanBuilder":
        """Add multiple HTTP headers."""
        self._headers.update(headers)
        return self

    def with_body(self, body: str | bytes) -> "HTTPSpanBuilder":
        """Set request body."""
        self._body = body
        return self

    def with_response(self, response: str | bytes) -> "HTTPSpanBuilder":
        """Set response body."""
        self._response = response
        return self

    def with_error(self, code: int, message: str) -> "HTTPSpanBuilder":
        """Set error information."""
        self._error = {"code": code, "message": message}
        return self

    def build(self) -> Span:
        """Build HTTP Span."""
        payload = HTTPSpanPayload(
            type=SpanType.HTTP,
            url=self._url,
            method=self._method,
            headers=self._headers,
            body=self._body,
            response=self._response,
            error=self._error,
        )
        self._payload = payload
        return super().build()


class EventBuilder:
    """
    Event builder.

    Usage:
        event = (EventBuilder()
                 .with_name("user_input")
                 .with_data({"text": "hello"})
                 .with_parent(span)
                 .build())
    """

    def __init__(self, trace_id: Optional[str] = None, app_name: Optional[str] = None):
        self._trace_id = trace_id or str(ULID())
        self._app_name = app_name or get_default("app_name")
        self._id = str(ULID())
        self._name = ""
        self._timestamp = datetime.now()
        self._tags: dict[str, str] = {}
        self._data: Any = None
        self._parent_id: Optional[str] = None

    def with_id(self, event_id: str) -> "EventBuilder":
        """Set event ID."""
        self._id = event_id
        return self

    def with_name(self, name: str) -> "EventBuilder":
        """Set event name."""
        self._name = name
        return self

    def with_trace_id(self, trace_id: str) -> "EventBuilder":
        """Set trace ID."""
        self._trace_id = trace_id
        return self

    def with_timestamp(self, timestamp: datetime) -> "EventBuilder":
        """Set timestamp."""
        self._timestamp = timestamp
        return self

    def with_tag(self, key: str, value: str) -> "EventBuilder":
        """Add a tag."""
        self._tags[key] = value
        return self

    def with_tags(self, tags: dict[str, str]) -> "EventBuilder":
        """Add multiple tags."""
        self._tags.update(tags)
        return self

    def with_data(self, data: Any) -> "EventBuilder":
        """Set data."""
        self._data = data
        return self

    def with_parent(self, parent: Span) -> "EventBuilder":
        """Set parent span."""
        self._parent_id = parent.id
        # Automatically inherit trace_id from parent span
        if parent:
            self._trace_id = parent.trace_id
        return self

    def with_parent_id(self, parent_id: str) -> "EventBuilder":
        """Set parent span ID."""
        self._parent_id = parent_id
        return self

    def build(self) -> Event:
        """Build Event object."""
        payload = OtherEventPayload(type=EventType.OTHER, data=self._data)

        event = Event(
            id=self._id,
            name=self._name,
            trace_id=self._trace_id,
            timestamp=self._timestamp,
            tags=self._tags,
            payload=payload,
            parent_id=self._parent_id,
            app_name=self._app_name,
        )
        return event
