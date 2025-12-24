import logging
from contextvars import ContextVar

trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)


def set_trace_id(trace_id: str):
    trace_id_var.set(trace_id)


def get_trace_id() -> str | None:
    return trace_id_var.get()


class TraceIdFilter(logging.Filter):
    """Automatically inject trace_id from contextvars into LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = get_trace_id() or "-"
        return True
