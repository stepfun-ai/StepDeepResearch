import asyncio
import logging

from agentkit.trace import LocalStorageTracer

from cortex.agents.agent_factory import AgentFactory
from cortex.agents.types import AgentConfig
from cortex.examples.agents.main_agent import make_main_agent
from cortex.examples.agents.math_agent import get_math_agent_config, make_math_agent
from cortex.examples.agents.search_agent import (
    get_search_agent_config,
    make_search_agent,
)
from cortex.model import ModelParams
from cortex.orchestrator.orchestrator import Orchestrator
from cortex.server.http_server import HttpServer

logger = logging.getLogger(__name__)


async def main():
    agent_factory = AgentFactory()
    agent_factory.register_agent(
        name="MainAgent",
        make_agent_func=make_main_agent,
        default_config=AgentConfig(
            name="MainAgent",
            description="Main coordination Agent responsible for coordinating and calling other specialized Agents to complete tasks. Can select appropriate Agents based on task requirements (e.g., MathAgent for mathematical calculations, SearchAgent for information search) and coordinate multiple Agents to complete complex tasks.",
            system_prompt="You are a main coordination Agent responsible for coordinating and calling other specialized Agents to complete tasks.",
            model=ModelParams(
                name="gpt-4o-mini",
                infer_kwargs={"max_tokens": 2000, "temperature": 0.7, "stream": False},
            ),
        ),
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
    orch = Orchestrator(agent_factory)
    tracer = LocalStorageTracer(storage_dir="./traces")
    http_server = HttpServer(orch, tracer=tracer)
    await http_server.start()


if __name__ == "__main__":
    asyncio.run(main())
