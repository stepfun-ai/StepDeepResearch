from abc import ABC, abstractmethod
from typing import Optional

from .span import Event, Span


class Tracer(ABC):
    @abstractmethod
    def record_span(self, span: Span) -> None:
        pass

    @abstractmethod
    def record_event(self, event: Event) -> None:
        pass

    @abstractmethod
    def get_spans(self, trace_id: str) -> list[Span]:
        pass

    @abstractmethod
    def get_events(self, trace_id: str) -> list[Event]:
        pass

    @abstractmethod
    def get_trace(self, trace_id: str) -> Optional[dict]:
        pass

    @abstractmethod
    def list_traces(self, limit: int = 100, offset: int = 0) -> list[dict]:
        pass

    def get_trace_raw(self, trace_id: str) -> Optional[dict]:
        """
        Get raw trace data (optional implementation).
        Default behavior is to call get_trace().
        """
        return self.get_trace(trace_id)
