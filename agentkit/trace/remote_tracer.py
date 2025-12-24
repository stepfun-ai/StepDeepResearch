import logging
from datetime import datetime
from typing import Optional

import httpx
from pydantic import BaseModel

from .span import DataType, Event, Span
from .tracer import Tracer

logger = logging.getLogger(__name__)


class RemoteEvent(BaseModel):
    id: str
    data_type: DataType
    timestamp: datetime
    app_name: str
    data: Span | Event


class RemoteTracer(Tracer):
    """
    A tracer that sends trace data to a remote API.

    According to API docs: /trace/agent/event
    """

    def __init__(
        self,
        base_url: str = "",
        timeout: float = 10.0,
        enable_span: bool = True,
        enable_event: bool = True,
    ):
        """
        Initialize RemoteTracer.

        Args:
            base_url: API base URL.
            timeout: Request timeout in seconds.
            enable_span: Whether to enable span sending (default True).
            enable_event: Whether to enable event sending (default True).
        """
        self.base_url = base_url.rstrip("/")
        self.event_endpoint = f"{self.base_url}/trace/agent/event"
        self.timeout = timeout
        self.enable_span = enable_span
        self.enable_event = enable_event
        self.client = httpx.Client(timeout=timeout)

    def __del__(self):
        """Clean up resources."""
        try:
            self.client.close()
        except Exception:
            pass

    def _send_to_api(self, data: str) -> bool:
        """
        Send data to remote API.

        Args:
            data: Data to send.

        Returns:
            Whether the send was successful.
        """
        try:
            response = self.client.post(
                self.event_endpoint,
                data=data,
                headers={"Content-Type": "application/json"},
            )

            if response.status_code == 200:
                result = response.json()
                if result.get("code") == 0:
                    logger.debug(f"Successfully sent trace data: {data}")
                    return True
                else:
                    logger.error(
                        f"API returned error code {result.get('code')}: {result.get('msg')}"
                    )
                    return False
            else:
                logger.error(f"HTTP error {response.status_code}: {response.text}")
                return False

        except httpx.TimeoutException:
            logger.error(f"Request timeout when sending trace data: {data}")
            return False
        except Exception as e:
            logger.error(f"Failed to send trace data: {e}")
            return False

    def record_span(self, span: Span) -> None:
        """Record a span to the remote service."""
        if not self.enable_span:
            return

        remote_event = RemoteEvent(
            id=span.id,
            data_type=DataType.SPAN,
            timestamp=span.start_time,
            app_name=span.app_name,
            data=span,
        )

        self._send_to_api(remote_event.model_dump_json(exclude_none=True))

    def record_event(self, event: Event) -> None:
        """Record an event to the remote service."""
        if not self.enable_event:
            return

        remote_event = RemoteEvent(
            id=event.id,
            data_type=DataType.EVENT,
            timestamp=event.timestamp,
            app_name=event.app_name,
            data=event,
        )

        self._send_to_api(remote_event.model_dump_json(exclude_none=True))

    def get_spans(self, trace_id: str) -> list[Span]:
        """
        RemoteTracer does not support read operations.

        Note: The current remote API only provides write interface, query is not supported.
        """
        logger.warning("RemoteTracer does not support reading spans")
        return []

    def get_events(self, trace_id: str) -> list[Event]:
        """
        RemoteTracer does not support read operations.

        Note: The current remote API only provides write interface, query is not supported.
        """
        logger.warning("RemoteTracer does not support reading events")
        return []

    def get_trace(self, trace_id: str) -> Optional[dict]:
        """
        RemoteTracer does not support read operations.

        Note: The current remote API only provides write interface, query is not supported.
        """
        logger.warning("RemoteTracer does not support reading traces")
        return None

    def list_traces(self, limit: int = 100, offset: int = 0) -> list[dict]:
        """
        RemoteTracer does not support read operations.

        Note: The current remote API only provides write interface, query is not supported.
        """
        logger.warning("RemoteTracer does not support listing traces")
        return []


class HybridTracer(Tracer):
    """
    Hybrid tracer: sends data to both remote service and local storage.

    Usage:
        from agentkit.trace.local_tracer import LocalStorageTracer
        from agentkit.trace.remote_tracer import RemoteTracer, HybridTracer

        local_tracer = LocalStorageTracer("./traces")
        remote_tracer = RemoteTracer("xxx")
        hybrid_tracer = HybridTracer(local_tracer, remote_tracer)
    """

    def __init__(self, local_tracer: Tracer, remote_tracer: RemoteTracer):
        """
        Initialize hybrid tracer.

        Args:
            local_tracer: Local tracer (for reading and local storage).
            remote_tracer: Remote tracer (for remote reporting).
        """
        self.local_tracer = local_tracer
        self.remote_tracer = remote_tracer

    def record_span(self, span: Span) -> None:
        """Record to both local and remote."""
        self.local_tracer.record_span(span)
        self.remote_tracer.record_span(span)

    def record_event(self, event: Event) -> None:
        """Record to both local and remote."""
        self.local_tracer.record_event(event)
        self.remote_tracer.record_event(event)

    def get_spans(self, trace_id: str) -> list[Span]:
        """Read spans from local."""
        return self.local_tracer.get_spans(trace_id)

    def get_events(self, trace_id: str) -> list[Event]:
        """Read events from local."""
        return self.local_tracer.get_events(trace_id)

    def get_trace(self, trace_id: str) -> Optional[dict]:
        """Read trace from local."""
        return self.local_tracer.get_trace(trace_id)

    def get_trace_raw(self, trace_id: str) -> Optional[dict]:
        """Read raw trace from local."""
        return self.local_tracer.get_trace_raw(trace_id)

    def list_traces(self, limit: int = 100, offset: int = 0) -> list[dict]:
        """List traces from local."""
        return self.local_tracer.list_traces(limit, offset)
