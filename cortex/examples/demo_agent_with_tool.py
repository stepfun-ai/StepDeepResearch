"""Demo Agent with Tool implementation."""

import argparse
import asyncio
import logging
import math
import random
import string
import uuid

from agentkit.trace import LocalStorageTracer, SpanContext
from cortex.model.definition import ChatMessage

from cortex.agents.react_agent import ReActAgent
from cortex.agents.types import AgentConfig
from cortex.context.simple_context import SimpleContext
from cortex.model import ModelParams
from cortex.tools.function_tool import FunctionTool
from cortex.tools.toolset import ToolSet

logger = logging.getLogger(__name__)


def add_numbers(a: int, b: int) -> int:
    """Add two numbers.

    Args:
        a: First number
        b: Second number

    Returns:
        Sum of the two numbers
    """
    return a + b


async def multiply_numbers(a: int, b: int) -> int:
    """Multiply two numbers.

    Args:
        a: First number
        b: Second number

    Returns:
        Product of the two numbers
    """
    await asyncio.sleep(5)
    return a * b


def get_random_string(length: int = 10) -> str:
    """Generate a random string.

    Args:
        length: String length, defaults to 10

    Returns:
        Randomly generated string
    """
    return "".join(random.choices(string.ascii_letters + string.digits, k=length))


def calculate_area(radius: float) -> float:
    """Calculate the area of a circle.

    Args:
        radius: Circle radius

    Returns:
        Area of the circle
    """
    return math.pi * radius * radius


async def init_tools():
    """Initialize toolset."""
    toolset = ToolSet()
    available_functions = [
        ("add_numbers", add_numbers, "Addition tool"),
        ("multiply_numbers", multiply_numbers, "Multiplication tool"),
        ("get_random_string", get_random_string, "Random string generator tool"),
        ("calculate_area", calculate_area, "Circle area calculator tool"),
    ]

    # Register function tools to ToolSet
    for tool_name, tool_func, tool_desc in available_functions:
        function_tool = FunctionTool(
            name=tool_name,
            func=tool_func,
            description=tool_desc,
        )
        toolset.register(function_tool)
        logger.info("Registered tool: %s", tool_name)

    await toolset.register_from_mcp_server(
        mcp_server="http://xxx/mcp",
        tool_names=["web_search"],
    )
    return toolset


async def main(user_input: str):
    """Main function demonstrating how to use DemoAgentWithTool."""
    # agent config
    agent_config = AgentConfig(
        name="demo_agent:ReActAgent",
        description="Agent demonstrating how to use ToolSet and anymodel.",
        system_prompt="You are a helpful assistant that can use the provided tools to help users.",
        model=ModelParams(
            name="gpt-4o-mini",
            infer_kwargs={"max_tokens": 2000, "temperature": 0.7, "stream": False},
        ),
        max_steps=10,
    )

    # toolset
    toolset = await init_tools()

    # agent instance
    context = SimpleContext(session_id=str(uuid.uuid4()))
    agent = ReActAgent(context=context, config=agent_config, toolset=toolset)

    logger.info("=== %s ===\n", agent.name)
    logger.info("Registered tools: %s\n", agent.toolset().list_tools())
    logger.info("Tool schema: %s\n", agent.toolset().get_all_schemas())

    # messages
    messages = [
        ChatMessage(role="user", content=user_input),
    ]

    # run agent
    async for response in agent.run(messages):
        logger.info("------ response: %s", response.model_dump_json())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Demo Agent with Tool")
    parser.add_argument(
        "--input",
        "-i",
        type=str,
        default="China central bank gold reserves 2025",
        help="User input query (optional, defaults to 'China central bank gold reserves 2025')",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(filename)s:%(lineno)d %(message)s",
        encoding="utf-8",  # Add UTF-8 encoding support
    )
    tracer = LocalStorageTracer(storage_dir="./traces")
    ctx = SpanContext(tracer=tracer, app_name="demo_agent_with_tool")
    with ctx.span(name="demo_agent_with_tool") as span:
        asyncio.run(main(args.input))
