import asyncio
import logging
from uuid import uuid4

from cortex.agents.agent_factory import AgentFactory
from cortex.agents.base_agent import BaseAgent
from cortex.agents.checkpoint_agent.checkpointer import (
    CheckpointStorage,
    SqliteCheckPointer,
)
from cortex.agents.checkpoint_agent.react_agent import CheckpointReActAgent
from cortex.agents.types import (
    AgentConfig,
)
from cortex.examples.agents.math_agent import init_math_tools
from cortex.examples.agents.search_agent import init_search_tools
from cortex.model import ModelParams
from cortex.orchestrator.orchestrator import Orchestrator
from cortex.server.http_server import HttpServer
from cortex.tools.toolset import ToolSet
from cortex.tools.ublock_agent_tool import UnblockAgentTool

logger = logging.getLogger(__name__)


def make_storage() -> CheckpointStorage:
    return SqliteCheckPointer(db_path="cp.db")


def get_search_agent_config() -> AgentConfig:
    return AgentConfig(
        name="SearchAgent",
        description="Agent specialized in searching and aggregating information. Uses search tools to find the latest information, aggregates multiple search results, provides comprehensive and accurate answers with source citations. Suitable for finding latest information, aggregating information from multiple sources, answering questions requiring real-time data, and information retrieval organization.",
        system_prompt="You are a professional information search and aggregation assistant.",
        model=ModelParams(
            name="gpt-4o-mini",
            infer_kwargs={"max_tokens": 10000, "temperature": 0.7, "stream": False},
        ),
    )


def get_math_agent_config() -> AgentConfig:
    return AgentConfig(
        name="MathAgent",
        description="Agent specialized in mathematical calculations. Supports basic math operations (addition, subtraction, multiplication, division, exponentiation, square root, etc.), can handle complex mathematical expressions, supports multi-step calculations, and provides detailed calculation process explanations. Suitable for arithmetic operations, algebraic calculations, geometric calculations, and mathematical expression solving.",
        system_prompt="You are a professional mathematical calculation assistant.",
        model=ModelParams(
            name="gpt-4o-mini",
            infer_kwargs={"max_tokens": 10000, "temperature": 0.7, "stream": False},
        ),
    )


async def make_search_agent(
    config: AgentConfig, context_id: str | None = None
) -> BaseAgent:
    """Create SearchAgent"""
    toolset = await init_search_tools()
    if context_id is None:
        context_id = uuid4().hex

    return CheckpointReActAgent(
        storage=make_storage(),
        context_id=context_id,
        config=config,
        toolset=toolset,
    )


async def make_math_agent(
    config: AgentConfig, context_id: str | None = None
) -> BaseAgent:
    toolset = await init_math_tools()
    if context_id is None:
        context_id = uuid4().hex

    return CheckpointReActAgent(
        storage=make_storage(),
        context_id=context_id,
        config=config,
        toolset=toolset,
    )


async def make_main_agent(
    config: AgentConfig, context_id: str | None = None
) -> BaseAgent:
    """Create MainAgent"""
    toolset = ToolSet()

    # toolset.register(
    #     UnblockClientTool(
    #         name="ask_for_user",
    #         description="Ask user for input. Used to get user feedback, confirmation, modification suggestions, etc. Parameters: prompt (required) - message shown to user; context (optional) - context information to help user understand the situation.",
    #         channel=toolset.channel,
    #         tool_type=ToolType.ASK_INPUT,
    #         timeout=300.0,
    #         client_params={
    #             "properties": {
    #                 "prompt": {
    #                     "type": "string",
    #                     "description": "Message shown to user, explaining what user needs to do (confirm, modify, provide information, etc.)",
    #                 },
    #                 "context": {
    #                     "type": "string",
    #                     "description": "Context information to help user understand the current situation, e.g., current plan content, items to confirm, etc.",
    #                 },
    #             },
    #             "required": ["prompt"],
    #         },
    #     )
    # )

    search_agent = await make_search_agent(config=get_search_agent_config())
    math_agent = await make_math_agent(config=get_math_agent_config())

    search_tool_params = search_agent.as_tool()
    math_tool_params = math_agent.as_tool()
    toolset.register(
        UnblockAgentTool(
            name=search_tool_params["name"],
            description=search_tool_params["description"],
            timeout=search_tool_params["timeout"]
            if "timeout" in search_tool_params
            else 300,
            channel=toolset.channel,
        )
    )
    toolset.register(
        UnblockAgentTool(
            name=math_tool_params["name"],
            description=math_tool_params["description"],
            timeout=math_tool_params["timeout"]
            if "timeout" in math_tool_params
            else 300,
            channel=toolset.channel,
        )
    )

    if context_id is None:
        context_id = uuid4().hex
    return CheckpointReActAgent(
        storage=make_storage(),
        context_id=context_id,
        config=config,
        toolset=toolset,
    )


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(filename)s:%(lineno)d %(message)s",
        encoding="utf-8",  # Add UTF-8 encoding support
    )

    agent_factory = AgentFactory()
    agent_factory.register_agent(
        name="MainAgent",
        make_agent_func=make_main_agent,
        default_config=AgentConfig(
            name="MainAgent",
            description="Main coordination Agent responsible for coordinating and calling other specialized Agents to complete tasks. Can select appropriate Agents based on task requirements (e.g., MathAgent for mathematical calculations, SearchAgent for information search) and coordinate multiple Agents to complete complex tasks.",
            system_prompt="You are a main coordination Agent responsible for coordinating and calling other specialized Agents to complete tasks. You can select appropriate Agents based on task requirements (e.g., MathAgent for mathematical calculations, SearchAgent for information search) and coordinate multiple Agents to complete complex tasks.",
            model=ModelParams(
                name="gpt-4o-mini",
                infer_kwargs={"max_tokens": 10000, "temperature": 0.7, "stream": False},
            ),
            unfinished_mode=False,
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

    # with open("graph.mermaid", "w", encoding="utf-8") as f:
    #     g = GraphReActAgent(
    #         make_checkpointer=lambda: AsyncSqliteSaver.from_conn_string(
    #             "checkpoints.db"
    #         ),
    #         config=get_search_agent_config(),
    #         toolset=ToolSet(),
    #     )
    #     f.write(g.draw())

    orch = Orchestrator(agent_factory)
    http_server = HttpServer(orch)
    await http_server.start()


if __name__ == "__main__":
    asyncio.run(main())
