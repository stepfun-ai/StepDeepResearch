"""Channel usage example: Demonstrates complete async communication flow."""

import asyncio
import logging
import time
from typing import Any, Dict

from cortex.tools.base import ToolSchema
from cortex.tools.channel import Channel
from cortex.tools.types import ToolParameters

logger = logging.getLogger(__name__)


# Mock external processing system (server, message queue, etc.)
class MockExternalServer:
    """Mock external server for processing requests."""

    def __init__(self):
        """Initialize mock server."""
        self.received_requests: Dict[str, Dict[str, Any]] = {}

    async def process_request(self, tool_name: str, request_id: str, data: Any) -> Any:
        """
        Process request (mock async processing).

        Args:
            tool_name: Tool name
            request_id: Request ID
            data: Request data

        Returns:
            Any: Processing result
        """
        # Simulate network delay
        await asyncio.sleep(0.5)

        # Store request
        self.received_requests[request_id] = {
            "tool_name": tool_name,
            "data": data,
            "timestamp": time.time(),
        }

        # Mock processing logic
        if tool_name == "calculator":
            if "operation" in data and "operands" in data:
                operation = data["operation"]
                operands = data["operands"]
                if operation == "add":
                    result = sum(operands)
                elif operation == "multiply":
                    result = 1
                    for x in operands:
                        result *= x
                else:
                    result = f"Unknown operation: {operation}"
                return {"result": result, "operation": operation}

        elif tool_name == "data_processor":
            if "data" in data:
                processed = f"Processed: {data['data']}"
                return {"output": processed, "length": len(data["data"])}

        # Default return
        return {"status": "success", "data": data}


async def demo_basic_usage():
    """Demo 1: Basic usage flow."""
    logger.info("=" * 60)
    logger.info("Demo 1: Basic usage flow - Send and wait for response")
    logger.info("=" * 60)

    # Create mock server
    server = MockExternalServer()

    # Define send callback function
    async def send_to_server(
        tool_name: str, tool_schema: ToolSchema, tool_parameters: ToolParameters
    ):
        """Callback function to send data to server."""
        # Extract request_id from tool_parameters.kwargs
        request_id = tool_parameters.kwargs.pop("_request_id", None)
        if request_id is None:
            request_id = f"req_{hash(tool_name)}_{hash(tool_parameters.parameters)}"

        # Build request data
        request_data = {
            "parameters": tool_parameters.parameters,
            **tool_parameters.kwargs,
        }

        logger.info(
            f"  [Send] tool={tool_name}, request_id={request_id}, data={request_data}"
        )
        result = await server.process_request(tool_name, request_id, request_data)

        # Simulate setting response via Channel
        # In real scenarios, this might be done asynchronously via network, message queue, etc.
        channel.set_response(request_id, result)

    # Create Channel and register send callback
    channel = Channel(on_send=send_to_server)

    # Send request 1: Calculator tool
    logger.info("\nSend request 1: Calculator - Addition")
    request_id1, response1 = await channel.send_request(
        tool_name="calculator",
        data=ToolParameters(
            parameters="", kwargs={"operation": "add", "operands": [10, 20, 30]}
        ),
        tool_schema=ToolSchema(name="calculator", description="Calculator tool"),
        timeout=5.0,
    )
    logger.info(f"  Request ID: {request_id1}")
    logger.info(f"  Response: {response1}")

    # Send request 2: Data processor
    logger.info("\nSend request 2: Data processor")
    request_id2, response2 = await channel.send_request(
        tool_name="data_processor",
        data=ToolParameters(parameters="", kwargs={"data": "Hello, World!"}),
        tool_schema=ToolSchema(name="data_processor", description="Data processor tool"),
        timeout=5.0,
    )
    logger.info(f"  Request ID: {request_id2}")
    logger.info(f"  Response: {response2}")

    logger.info(f"\nNumber of requests received by server: {len(server.received_requests)}")


async def demo_custom_request_id():
    """Demo 2: Using custom request_id."""
    logger.info("\n" + "=" * 60)
    logger.info("Demo 2: Using custom request_id")
    logger.info("=" * 60)

    server = MockExternalServer()
    channel = Channel()

    # Define send callback
    async def send_handler(
        tool_name: str, tool_schema: ToolSchema, tool_parameters: ToolParameters
    ):
        """Send handler."""
        # Extract request_id from tool_parameters.kwargs
        request_id = tool_parameters.kwargs.pop("_request_id", None)
        if request_id is None:
            request_id = f"req_{hash(tool_name)}_{hash(tool_parameters.parameters)}"

        # Build request data
        request_data = {
            "parameters": tool_parameters.parameters,
            **tool_parameters.kwargs,
        }

        logger.info(f"  [Send] request_id={request_id}, data={request_data}")
        result = await server.process_request(tool_name, request_id, request_data)
        channel.set_response(request_id, result)

    # Send request with custom request_id
    custom_id = "req_custom_001"
    logger.info(f"\nUsing custom request_id: {custom_id}")
    request_id, response = await channel.send_request(
        tool_name="calculator",
        data=ToolParameters(
            parameters="", kwargs={"operation": "multiply", "operands": [2, 3, 4]}
        ),
        tool_schema=ToolSchema(name="calculator", description="Calculator tool"),
        request_id=custom_id,
        on_send=send_handler,
        timeout=5.0,
    )
    logger.info(f"  Returned request_id: {request_id}")
    logger.info(f"  Response: {response}")


async def demo_manual_response():
    """Demo 3: Manually set response."""
    logger.info("\n" + "=" * 60)
    logger.info("Demo 3: Manually set response (separate send and response)")
    logger.info("=" * 60)

    channel = Channel()
    saved_request_id = {"id": None}  # Used to save request_id

    # Define send callback (only send, don't set response immediately)
    async def send_only(
        tool_name: str, tool_schema: ToolSchema, tool_parameters: ToolParameters
    ):
        """Only send data, don't set response."""
        # Extract request_id from tool_parameters.kwargs
        request_id = tool_parameters.kwargs.pop("_request_id", None)
        if request_id is None:
            request_id = f"req_{hash(tool_name)}_{hash(tool_parameters.parameters)}"

        saved_request_id["id"] = request_id  # Save request_id for later use

        # Build request data
        request_data = {
            "parameters": tool_parameters.parameters,
            **tool_parameters.kwargs,
        }

        logger.info(f"  [Send only] request_id={request_id}, data={request_data}")
        # In real scenarios, this might be sent to message queue, WebSocket, etc.
        # Response is set asynchronously by another thread/process/service

    # Start a background task to simulate async response
    async def delayed_response(delay: float = 1.0):
        """Delayed response setting."""
        await asyncio.sleep(delay)
        req_id = saved_request_id["id"]
        if req_id:
            result = {
                "status": "completed",
                "request_id": req_id,
                "data": "processed_data",
            }
            logger.info(f"  [Set response] request_id={req_id}, response={result}")
            channel.set_response(req_id, result)

    # Create send request task
    send_task = asyncio.create_task(
        channel.send_request(
            tool_name="async_processor",
            data=ToolParameters(parameters="", kwargs={"task": "process_data"}),
            tool_schema=ToolSchema(
                name="async_processor", description="Async processor tool"
            ),
            on_send=send_only,
            timeout=5.0,
        )
    )

    # Start delayed response task (auto-processed after request is sent)
    response_task = asyncio.create_task(delayed_response(delay=0.8))

    # Wait for request to complete
    request_id, response = await send_task
    logger.info(f"  Request ID: {request_id}")
    logger.info(f"  Response: {response}")

    await response_task


async def demo_error_handling():
    """Demo 4: Error handling."""
    logger.info("\n" + "=" * 60)
    logger.info("Demo 4: Error handling")
    logger.info("=" * 60)

    channel = Channel()

    async def send_with_error(
        tool_name: str, tool_schema: ToolSchema, tool_parameters: ToolParameters
    ):
        """Send and set error response."""
        # Extract request_id from tool_parameters.kwargs
        request_id = tool_parameters.kwargs.pop("_request_id", None)
        if request_id is None:
            request_id = f"req_{hash(tool_name)}_{hash(tool_parameters.parameters)}"

        logger.info(f"  [Send] request_id={request_id}")
        await asyncio.sleep(0.3)
        # Simulate processing failure, set error response
        channel.set_response(request_id, None, error="Processing failed: Invalid input")

    logger.info("\nSending request (will return error)...")
    try:
        request_id, response = await channel.send_request(
            tool_name="failing_tool",
            data=ToolParameters(parameters="", kwargs={"invalid": "data"}),
            tool_schema=ToolSchema(name="failing_tool", description="Failing tool"),
            on_send=send_with_error,
            timeout=5.0,
        )
        logger.info(f"  Response: {response}")
    except Exception as e:
        logger.info(f"  Caught error: {type(e).__name__}: {e}")

    # Demo timeout
    logger.info("\nSending request (will timeout)...")

    async def slow_sender(
        tool_name: str, tool_schema: ToolSchema, tool_parameters: ToolParameters
    ):
        """Slow sender, won't set response."""
        # Extract request_id from tool_parameters.kwargs
        request_id = tool_parameters.kwargs.pop("_request_id", None)
        if request_id is None:
            request_id = f"req_{hash(tool_name)}_{hash(tool_parameters.parameters)}"

        logger.info(f"  [Send] request_id={request_id} (but won't set response)")
        await asyncio.sleep(2.0)  # Exceeds timeout

    try:
        request_id, response = await channel.send_request(
            tool_name="slow_tool",
            data=ToolParameters(parameters="", kwargs={"slow": "data"}),
            tool_schema=ToolSchema(name="slow_tool", description="Slow tool"),
            on_send=slow_sender,
            timeout=1.0,  # 1 second timeout
        )
    except TimeoutError as e:
        logger.info(f"  Caught timeout error: {e}")


async def demo_concurrent_requests():
    """Demo 5: Concurrent requests."""
    logger.info("\n" + "=" * 60)
    logger.info("Demo 5: Concurrent request handling")
    logger.info("=" * 60)

    server = MockExternalServer()
    channel = Channel()

    async def concurrent_sender(
        tool_name: str, tool_schema: ToolSchema, tool_parameters: ToolParameters
    ):
        """Concurrent send handler."""
        # Extract request_id from tool_parameters.kwargs
        request_id = tool_parameters.kwargs.pop("_request_id", None)
        if request_id is None:
            request_id = f"req_{hash(tool_name)}_{hash(tool_parameters.parameters)}"

        # Build request data
        request_data = {
            "parameters": tool_parameters.parameters,
            **tool_parameters.kwargs,
        }

        result = await server.process_request(tool_name, request_id, request_data)
        channel.set_response(request_id, result)

    # Create multiple concurrent requests
    logger.info("\nSending 5 concurrent requests...")
    tasks = []
    for i in range(5):
        task = channel.send_request(
            tool_name="calculator",
            data=ToolParameters(
                parameters="",
                kwargs={"operation": "add", "operands": [i, i + 1, i + 2]},
            ),
            tool_schema=ToolSchema(name="calculator", description="Calculator tool"),
            on_send=concurrent_sender,
            timeout=5.0,
        )
        tasks.append(task)

    # Wait for all requests to complete
    results = await asyncio.gather(*tasks)
    logger.info(f"\nCompleted {len(results)} requests:")
    for i, (req_id, response) in enumerate(results, 1):
        logger.info(
            f"  Request {i}: request_id={req_id}, result={response.get('result', 'N/A')}"
        )


async def main():
    """Main function: Run all demos."""
    logger.info("\n" + "=" * 60)
    logger.info("Channel Complete Usage Flow Demo")
    logger.info("=" * 60)

    await demo_basic_usage()
    await demo_custom_request_id()
    await demo_manual_response()
    await demo_error_handling()
    await demo_concurrent_requests()

    logger.info("\n" + "=" * 60)
    logger.info("All demos completed!")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
