"""
Context management and utility functions for Span and Event.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from functools import wraps
try:  # Python 3.11+ has HTTPMethod in stdlib
    from http import HTTPMethod
except ImportError:  # pragma: no cover - fallback for Python 3.10
    from enum import Enum

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
from typing import Any, Callable, Literal, Optional

from ulid import ULID

from .default import get_default, get_default_settings, set_default
from .span import (
    Event,
    EventType,
    FunctionSpanPayload,
    HTTPSpanPayload,
    LLMSpanPayload,
    OtherEventPayload,
    OtherSpanPayload,
    Span,
    SpanType,
    ToolSpanPayload,
)
from .tracer import Tracer
from .types import Error

# Use contextvars to manage the current context
_current_context: ContextVar[Optional["SpanContext"]] = ContextVar(
    "current_context", default=None
)


class SpanContext:
    """
    Manages the current active span context, supporting nested parent-child relationships.

    Supports cross-service span reconstruction: trace_id and parent_id can be specified at creation time.
    """

    def __init__(
        self,
        app_name: Optional[str] = None,
        tags: Optional[dict[str, str]] = None,
        trace_id: Optional[str] = None,
        parent_id: Optional[str] = None,
        tracer: Optional[Tracer] = None,
    ):
        if tracer is None:
            self.tracer = get_default("tracer")
        else:
            self.tracer = tracer
        self.app_name = app_name or get_default("app_name")
        self.tags = tags
        self._span_stack: list[Span] = []
        self._current_trace_id: Optional[str] = trace_id
        self._root_parent_id: Optional[str] = parent_id  # Root parent node for cross-service reconstruction

    def get_current_span(self) -> Optional[Span]:
        """Get the current active span."""
        return self._span_stack[-1] if self._span_stack else None

    def get_current_trace_id(self) -> str:
        """Get or create the current trace_id."""
        if self._current_trace_id is None:
            self._current_trace_id = str(ULID())
        return self._current_trace_id

    def set_trace_id(self, trace_id: str):
        """Set the current trace_id."""
        self._current_trace_id = trace_id

    def merge_tags(self, tags: dict[str, str]) -> dict[str, str]:
        """Merge tags."""
        merged_tags = self.tags or {}
        if tags:
            merged_tags.update(tags)
        return merged_tags

    @contextmanager
    def span(
        self,
        name: str,
        tags: Optional[dict[str, str]] = None,
        payload: Optional[
            HTTPSpanPayload
            | LLMSpanPayload
            | ToolSpanPayload
            | FunctionSpanPayload
            | OtherSpanPayload
        ] = None,
    ):
        """
        Context manager for creating a span.

        Usage:
            with ctx.span("my_operation", SpanType.FUNCTION):
                # your code
                pass
        """
        parent_span = self.get_current_span()
        trace_id = self.get_current_trace_id()

        # Determine parent_id: prioritize span in current stack, otherwise use root parent_id (cross-service scenario)
        parent_id = None
        if parent_span:
            parent_id = parent_span.id
        elif self._root_parent_id:
            parent_id = self._root_parent_id

        span = Span(
            name=name,
            trace_id=trace_id,
            app_name=self.app_name,
            tags=self.merge_tags(tags),
            payload=payload,
            parent_id=parent_id,
        )

        self._span_stack.append(span)
        token = _current_context.set(self)

        try:
            yield span
        except Exception as e:
            # Record error
            span.tags["error"] = str(e)
            raise
        finally:
            # Set end time
            span.end_time = datetime.now()
            self._span_stack.pop()

            # Record span
            if self.tracer:
                self.tracer.record_span(span)
            _current_context.reset(token)

    def record_event(
        self,
        name: str,
        data: Any,
        tags: Optional[dict[str, str]] = None,
    ):
        """
        Record an event to the current span.

        Usage:
            ctx.record_event("user_input", {"text": "hello"})
        """
        parent_span = self.get_current_span()
        trace_id = self.get_current_trace_id()

        payload = OtherEventPayload(type=EventType.OTHER, data=data)

        event = Event(
            name=name,
            trace_id=trace_id,
            tags=self.merge_tags(tags),
            payload=payload,
            parent_id=parent_span.id if parent_span else None,
            app_name=self.app_name,
        )

        if self.tracer:
            self.tracer.record_event(event)

        return event

    @contextmanager
    def function_span(
        self,
        name: str,
        arguments: dict[str, Any],
        tags: Optional[dict[str, str]] = None,
    ):
        """
        Create a span for a function call.

        Usage:
            with ctx.function_span("calculate", {"x": 1, "y": 2}) as span:
                result = calculate(1, 2)
                span.update_payload_data(return_value=result)
        """
        payload = FunctionSpanPayload(
            type=SpanType.FUNCTION,
            name=name,
            arguments=arguments,
            return_value=None,
        )

        with self.span(name, tags, payload) as span:
            try:
                yield span
            except Exception as e:
                if isinstance(span.payload, FunctionSpanPayload):
                    span.payload.error = Error(code=-1, message=str(e))
                raise

    @contextmanager
    def llm_span(
        self,
        name: str = "llm_call",
        request: Any = None,
        tags: Optional[dict[str, str]] = None,
    ):
        """
        Create a span for an LLM call.

        Usage:
            with ctx.llm_span("openai_call", request=messages) as span:
                response = client.chat.completions.create(...)
                span.update_payload_data(response=response)
        """
        payload = LLMSpanPayload(
            type=SpanType.LLM,
            request=request,
        )

        with self.span(name, tags, payload) as span:
            try:
                yield span
            except Exception as e:
                if isinstance(span.payload, LLMSpanPayload):
                    span.payload.error = Error(code=-1, message=str(e))
                raise

    @contextmanager
    def tool_span(
        self,
        name: str = "tool_call",
        request: Any = None,
        tags: Optional[dict[str, str]] = None,
    ):
        """
        Create a span for a tool call.

        Usage:
            with ctx.tool_span("search_tool", request=tool_call) as span:
                result = search(query)
                span.update_payload_data(response=result)
        """
        payload = ToolSpanPayload(type=SpanType.TOOL, request=request)

        with self.span(name, tags, payload) as span:
            try:
                yield span
            except Exception as e:
                if isinstance(span.payload, ToolSpanPayload):
                    span.payload.error = Error(code=-1, message=str(e))
                raise

    @contextmanager
    def http_span(
        self,
        url: str,
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
        ],
        name: Optional[str] = None,
        headers: Optional[dict[str, list[str]]] = None,
        body: Optional[str | bytes] = None,
        tags: Optional[dict[str, str]] = None,
    ):
        """
        Create a span for an HTTP request.

        Usage:
            with ctx.http_span("https://api.example.com", "POST", body=data) as span:
                response = requests.post(url, data=data)
                span.update_payload_data(response=response.text)
        """
        span_name = name or f"{method} {url}"
        payload = HTTPSpanPayload(
            type=SpanType.HTTP,
            url=url,
            method=method,
            headers=headers or {},
            body=body,
        )

        with self.span(span_name, tags, payload) as span:
            try:
                yield span
            except Exception as e:
                if isinstance(span.payload, HTTPSpanPayload):
                    span.payload.error = Error(code=-1, message=str(e))
                raise


def get_current_context() -> SpanContext:
    """Get the current SpanContext, creating a default one if it doesn't exist."""
    context = _current_context.get()
    if context is None:
        context = SpanContext()
        _current_context.set(context)
    return context


def set_default_tracer(tracer: Tracer):
    """Set the global default Tracer."""
    set_default(tracer=tracer)


def set_default_app_name(app_name: str):
    """Set the global default app_name."""
    set_default(app_name=app_name)


def get_default_tracer() -> Tracer:
    """Get the global default Tracer."""
    return get_default_settings().tracer


def get_default_app_name() -> str:
    """Get the global default app_name."""
    return get_default_settings().app_name


# Convenient global functions
def trace_function(
    name: Optional[str] = None,
    tags: Optional[dict[str, str]] = None,
    context: Optional[SpanContext] = None,
):
    """
    Decorator: automatically trace function calls.

    Usage:
        @trace_function(name="my_function", tags={"category": "business"})
        def my_function(x, y):
            return x + y
    """

    def decorator(func: Callable) -> Callable:
        func_name = name or func.__name__

        @wraps(func)
        def wrapper(*args, **kwargs):
            ctx = context or get_current_context()

            # Build arguments dictionary
            arguments = {"args": args, "kwargs": kwargs}

            with ctx.function_span(func_name, arguments, tags) as span:
                result = func(*args, **kwargs)

                # Record return value
                if isinstance(span.payload, FunctionSpanPayload):
                    span.payload.return_value = result

                return result

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            ctx = context or get_current_context()

            # Build arguments dictionary
            arguments = {"args": args, "kwargs": kwargs}

            with ctx.function_span(func_name, arguments, tags) as span:
                result = await func(*args, **kwargs)

                # Record return value
                if isinstance(span.payload, FunctionSpanPayload):
                    span.payload.return_value = result

                return result

        # Return corresponding wrapper based on function type
        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return wrapper

    return decorator


def start_trace(trace_id: Optional[str] = None, context: Optional[SpanContext] = None):
    """
    Start a new trace.

    Usage:
        trace_id = start_trace()
    """
    ctx = context or get_current_context()
    if trace_id:
        ctx.set_trace_id(trace_id)
    else:
        trace_id = ctx.get_current_trace_id()
    return trace_id


def record_event(
    name: str,
    data: Any,
    tags: Optional[dict[str, str]] = None,
    context: Optional[SpanContext] = None,
):
    """
    Record an event.

    Usage:
        record_event("user_action", {"action": "click", "button": "submit"})
    """
    ctx = context or get_current_context()
    return ctx.record_event(name, data, tags=tags)


@contextmanager
def create_span(
    name: str,
    tags: Optional[dict[str, str]] = None,
    context: Optional[SpanContext] = None,
):
    """
    Convenient function to create a span.

    Usage:
        with create_span("my_operation"):
            # your code
            pass
    """
    ctx = context or get_current_context()
    with ctx.span(name, tags) as span:
        yield span
