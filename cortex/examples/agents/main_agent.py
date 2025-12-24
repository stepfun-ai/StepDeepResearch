"""MainAgent - Main coordination Agent."""

import logging
from uuid import uuid4

from cortex.agents.base_agent import BaseAgent
from cortex.agents.react_agent import ReActAgent
from cortex.agents.types import AgentConfig
from cortex.context import make_simple_context
from cortex.examples.agents.math_agent import get_math_agent_config, make_math_agent
from cortex.examples.agents.search_agent import (
    get_search_agent_config,
    make_search_agent,
)
from cortex.model import ModelParams
from cortex.tools.agent_tool import AgentTool
from cortex.tools.toolset import ToolSet

logger = logging.getLogger(__name__)


async def init_main_tools() -> ToolSet:
    """Initialize main coordination tools."""
    toolset = ToolSet()
    search_agent = await make_search_agent(config=get_search_agent_config())
    math_agent = await make_math_agent(config=get_math_agent_config())

    search_tool_params = search_agent.as_tool()
    math_tool_params = math_agent.as_tool()
    toolset.register(
        AgentTool(
            name=search_tool_params["name"],
            description=search_tool_params["description"],
            timeout=search_tool_params["timeout"]
            if "timeout" in search_tool_params
            else 300,
            channel=toolset.channel,
        )
    )
    toolset.register(
        AgentTool(
            name=math_tool_params["name"],
            description=math_tool_params["description"],
            timeout=math_tool_params["timeout"]
            if "timeout" in math_tool_params
            else 300,
            channel=toolset.channel,
        )
    )
    return toolset


async def make_main_agent(
    config: AgentConfig, context_id: str | None = None
) -> BaseAgent:
    """Create MainAgent."""
    toolset = await init_main_tools()
    if context_id is None:
        context_id = uuid4().hex
    context = make_simple_context(context_id)
    return ReActAgent(context=context, config=config, toolset=toolset)


def get_main_agent_config() -> AgentConfig:
    """Get MainAgent configuration."""
    return AgentConfig(
        name="MainAgent",
        description="Main coordination Agent responsible for coordinating and calling other specialized Agents to complete tasks. Can select appropriate Agents based on task requirements (e.g., MathAgent for mathematical calculations, SearchAgent for information search) and coordinate multiple Agents to complete complex tasks.",
        system_prompt="You are a main coordination Agent responsible for coordinating and calling other specialized Agents to complete tasks.",
        model=ModelParams(
            name="gpt-4o-mini",
            infer_kwargs={"max_tokens": 2000, "temperature": 0.7, "stream": False},
        ),
    )
