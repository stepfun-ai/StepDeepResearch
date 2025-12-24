"""Demo Agent with Orchestrator - Demonstrates how to use the Orchestrator pattern to coordinate multiple Agents"""

import argparse
import asyncio
import logging

from agentkit.trace import LocalStorageTracer, SpanContext
from cortex.model.definition import ChatMessage

from cortex.agents.agent_factory import AgentFactory
from cortex.examples.agents.main_agent import get_main_agent_config, make_main_agent
from cortex.examples.agents.math_agent import get_math_agent_config, make_math_agent
from cortex.examples.agents.search_agent import (
    get_search_agent_config,
    make_search_agent,
)
from cortex.orchestrator import AgentEvent
from cortex.orchestrator.orchestrator import Orchestrator
from cortex.orchestrator.types import AgentEventType, AgentRequest

logger = logging.getLogger(__name__)


async def main(
    request: str | None = None,
    output_file: str | None = None,
):
    """
    Main function demonstrating how to use Orchestrator

    Args:
        request: User request content. If None, uses default test message
        output_file: Output file path. If None, outputs to stdout
    """

    agent_factory = AgentFactory()
    agent_factory.register_agent(
        name="MainAgent",
        make_agent_func=make_main_agent,
        default_config=get_main_agent_config(),
    )
    agent_factory.register_agent(
        name="SearchAgent",
        make_agent_func=make_search_agent,
        default_config=get_search_agent_config(),
    )
    agent_factory.register_agent(
        name="MathAgent",
        make_agent_func=make_math_agent,
        default_config=get_math_agent_config(),
    )
    orchestrator = Orchestrator(agent_factory)

    messages = [ChatMessage(role="user", content=request)]
    async for event in orchestrator.run(
        agent_name="MainAgent",
        event=AgentEvent(
            type=AgentEventType.REQUEST,
            request=AgentRequest(
                agent_name="MainAgent",
                messages=messages,
            ),
        ),
        agent_config=None,
    ):
        logger.info("------ event: %s", event.model_dump_json())
        if output_file:
            with open(output_file, "a", encoding="utf-8") as f:
                f.write(event.model_dump_json(ensure_ascii=False) + "\n")
        else:
            print(event.model_dump_json(ensure_ascii=False))


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Demo Agent with Orchestrator - Demonstrates how to use the Orchestrator pattern to coordinate multiple Agents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example usage:
  # Use default request, output to stdout
  python cortex/examples/demo_agent_with_orchestrator.py

  # Specify request content
  python cortex/examples/demo_agent_with_orchestrator.py --request "Please calculate the result of 123 + 456 + 789"

  # Output to file
  python cortex/examples/demo_agent_with_orchestrator.py --request "Please calculate the result of 123 + 456 + 789" --output result.txt

  # Use grep to filter responses (stdout with prefix)
  python cortex/examples/demo_agent_with_orchestrator.py | grep "\\[RESPONSE\\]"

Demo examples (can be uncommented in code or specified via --request parameter):
  1. Math calculation - Simple addition: "Please calculate the result of 123 + 456 + 789"
  2. Math calculation - Complex operation: "Please calculate the result of (123 + 456) * 789 / 100"
  3. Math calculation - Multi-step: "Please calculate 15 + 27 + 39 + 41 step by step, first calculate the sum of the first two numbers, then add the remaining numbers"
  4. Information search: "Please search for the latest information about China's central bank gold reserves in 2025"
  5. Mixed task: "Please first search for China's GDP growth rate in 2024, then calculate what the GDP would be if it grows by 5% in 2025"
        """,
    )
    parser.add_argument(
        "--request",
        "-r",
        type=str,
        default=None,
        help="User request content (if not specified, uses default test message)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Output file path (if not specified, outputs to stdout with prefix for grep)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="DEBUG",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level (default: INFO)",
    )

    args = parser.parse_args()

    # Set log level and corresponding source file and line number
    log_level = getattr(logging, args.log_level.upper())
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s %(filename)s:%(lineno)d %(message)s",
        encoding="utf-8",  # Add UTF-8 encoding support for proper character display
    )

    print("-----------------------------------------------------")
    tracer = LocalStorageTracer(storage_dir="./traces")
    ctx = SpanContext(tracer=tracer, app_name="demo_agent_with_orchestrator")
    with ctx.span(name="demo_agent_with_orchestrator") as span:
        trace_id = ctx.get_current_trace_id()
        logger.info("agent_cortex trace_id %s", trace_id)
        asyncio.run(main(request=args.request, output_file=args.output))
