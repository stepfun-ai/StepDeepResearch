"""Channel for async tool execution communication."""

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

from .base import ToolSchema
from .types import ToolParameters


class MessageType(Enum):
    """Message type."""

    REQUEST = "request"
    RESPONSE = "response"
    ERROR = "error"


@dataclass
class ChannelMessage:
    """Channel message."""

    message_type: MessageType
    tool_name: str
    request_id: str
    data: Any
    error: Optional[str] = None


class Channel:
    """Channel for async tool execution communication."""

    def __init__(
        self,
        on_send: Optional[
            Callable[[str, ToolSchema, ToolParameters], Awaitable[None]]
        ] = None,
    ):
        """
        Initialize Channel.

        Args:
            on_send: Callback function for sending requests,
                    receives (tool_name, tool_schema, data) and sends data asynchronously
        """
        self._pending_requests: Dict[str, asyncio.Future] = {}
        self._request_counter = 0
        self._on_send = on_send

    def set_on_send(
        self,
        on_send: Optional[Callable[[str, ToolSchema, ToolParameters], Awaitable[None]]],
    ):
        """
        Set the send callback function.

        Args:
            on_send: Callback function for sending requests,
                    receives (tool_name, tool_schema, tool_parameters) and sends data asynchronously
        """
        self._on_send = on_send

    def create_request_id(self) -> str:
        """
        Create a request ID.

        Returns:
            str: Request ID
        """
        self._request_counter += 1
        return f"req_{self._request_counter}"

    async def send_request(
        self,
        tool_name: str,
        data: ToolParameters,
        tool_schema: ToolSchema,
        request_id: Optional[str] = None,
        timeout: Optional[float] = None,
        on_send: Optional[
            Callable[[str, ToolSchema, ToolParameters], Awaitable[None]]
        ] = None,
    ) -> Tuple[str, Any]:
        """
        Send request and wait for response.

        Args:
            tool_name: Tool name
            data: Request data (ToolParameters object)
            tool_schema: Tool schema
            request_id: Request ID (auto-generated if not provided)
            timeout: Timeout in seconds
            on_send: Callback function for sending requests,
                    receives (tool_name, tool_schema, tool_parameters) and sends data asynchronously.
                    If provided, overrides the on_send set during initialization.

        Returns:
            Tuple[str, Any]: (request_id, response data)

        Raises:
            TimeoutError: Request timeout
            Exception: Tool execution error
        """
        # Auto-generate request_id if not provided
        if request_id is None:
            request_id = self.create_request_id()

        future = asyncio.Future()
        self._pending_requests[request_id] = future

        try:
            # Send data to external system
            send_handler = on_send or self._on_send
            if send_handler:
                # Create a copy of data to avoid modifying the original object
                tool_parameters = ToolParameters(
                    parameters=data.parameters, kwargs={**data.kwargs}
                )

                # Add request_id to kwargs
                tool_parameters.kwargs["_request_id"] = request_id

                await send_handler(tool_name, tool_schema, tool_parameters)

            # Wait for response (response is set via set_response)
            if timeout:
                response = await asyncio.wait_for(future, timeout=timeout)
            else:
                response = await future

            return (request_id, response)

        except asyncio.TimeoutError as exc:
            self._pending_requests.pop(request_id, None)
            raise TimeoutError(
                f"Request {request_id} for tool {tool_name} timed out"
            ) from exc
        except Exception:
            self._pending_requests.pop(request_id, None)
            raise
        finally:
            self._pending_requests.pop(request_id, None)

    def set_response(self, request_id: str, data: Any, error: Optional[str] = None):
        """
        Set response data.

        Args:
            request_id: Request ID
            data: Response data
            error: Error message (if any)
        """
        if request_id not in self._pending_requests:
            return

        future = self._pending_requests[request_id]

        # Check if future has already been set
        if future.done():
            return

        try:
            if error:
                future.set_exception(Exception(error))
            else:
                future.set_result(data)
        except Exception:
            # Ignore if future has already been set or cancelled
            # This may happen in concurrent scenarios
            pass
