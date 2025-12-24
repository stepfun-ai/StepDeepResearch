"""Demo Agent CLI - TUI interface built using TUI module to display AgentEvent."""

import asyncio
import logging
from pathlib import Path

from agentkit.trace import LocalStorageTracer

from cortex.agents.agent_factory import AgentFactory
from cortex.examples.agents.ask_input_agent import (
    get_ask_input_agent_config,
    make_ask_input_agent,
)
from cortex.examples.agents.deep_reasearch_agent import (
    get_deep_research_agent_config,
    make_deep_research_agent,
)
from cortex.examples.agents.main_agent import get_main_agent_config, make_main_agent
from cortex.examples.agents.math_agent import get_math_agent_config, make_math_agent
from cortex.examples.agents.plan_agent import get_plan_agent_config, make_plan_agent
from cortex.examples.agents.search_agent import (
    get_search_agent_config,
    make_search_agent,
)
from cortex.orchestrator.orchestrator import Orchestrator
from cortex.tui import AgentTUIApp

logger = logging.getLogger(__name__)


async def main():
    """
    Main function.

    Example:
    python -m cortex.examples.demo_agent_cli
    """
    # Create logs directory
    logs_dir = Path("./logs")
    logs_dir.mkdir(exist_ok=True)

    # Configure logger to output to file
    log_file = logs_dir / "demo_agent_cli.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(filename)s:%(lineno)d %(message)s"
        )
    )

    # Configure root logger to output only to file, not console
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.handlers.clear()  # Clear default console handler
    root_logger.addHandler(file_handler)

    # Initialize Orchestrator
    agent_factory = AgentFactory()
    agent_factory.register_agent(
        name="DeepResearchAgent",
        make_agent_func=make_deep_research_agent,
        default_config=get_deep_research_agent_config(),
    )
    agent_factory.register_agent(
        name="PlanAgent",
        make_agent_func=make_plan_agent,
        default_config=get_plan_agent_config(),
    )
    agent_factory.register_agent(
        name="AskInputAgent",
        make_agent_func=make_ask_input_agent,
        default_config=get_ask_input_agent_config(),
    )

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

    tracer = LocalStorageTracer(storage_dir="./traces")
    app = AgentTUIApp(orchestrator=orchestrator, workdir="./logs", tracer=tracer)
    await app.run_async()


if __name__ == "__main__":
    asyncio.run(main())
