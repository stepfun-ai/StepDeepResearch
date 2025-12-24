"""SearchAgent - An Agent that can integrate search information"""

import logging
from uuid import uuid4

from cortex.agents.base_agent import BaseAgent
from cortex.agents.react_agent import ReActAgent
from cortex.agents.types import AgentConfig
from cortex.context import make_simple_context
from cortex.model import ModelParams
from cortex.tools.toolset import ToolSet

logger = logging.getLogger(__name__)


async def init_search_tools() -> ToolSet:
    """Initialize search tools"""
    toolset = ToolSet()
    await toolset.register_from_mcp_server(
        mcp_server="http://xxx/mcp",
        tool_names=["web_search"],
    )
    return toolset


async def make_search_agent(
    config: AgentConfig, context_id: str | None = None
) -> BaseAgent:
    """Create SearchAgent"""
    toolset = await init_search_tools()
    if context_id is None:
        context_id = uuid4().hex
    context = make_simple_context(context_id)
    return ReActAgent(context=context, config=config, toolset=toolset)


def get_search_agent_config() -> AgentConfig:
    """Get SearchAgent configuration"""
    return AgentConfig(
        name="SearchAgent",
        description="An Agent specialized in searching and integrating information. Uses search tools to find latest information, integrates multiple search results, provides comprehensive and accurate answers with citations. Suitable for finding latest information, integrating information from multiple sources, answering questions requiring real-time data, and information retrieval and organization.",
        system_prompt="You are a professional information search and integration assistant.",
        model=ModelParams(
            name="gpt-4o-mini",
            infer_kwargs={"max_tokens": 2000, "temperature": 0.7, "stream": False},
        ),
    )
