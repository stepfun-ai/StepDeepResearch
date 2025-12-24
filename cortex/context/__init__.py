"""Context module for managing conversation and session context."""

from cortex.context.base_context import BaseContext
from cortex.context.file_context import FileContext
from cortex.context.simple_context import SimpleContext

__all__ = ["BaseContext", "make_simple_context", "make_file_context"]


def make_simple_context(session_id: str) -> BaseContext:
    return SimpleContext(session_id)


def make_file_context(path: str, session_id: str) -> BaseContext:
    return FileContext(session_id, path)
