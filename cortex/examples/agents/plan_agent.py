"""PlanAgent - Creates plans based on task objectives, and finalizes plans after user confirmation or modification"""

import logging

from cortex.agents.base_agent import BaseAgent
from cortex.agents.react_agent import ReActAgent
from cortex.agents.types import AgentConfig
from cortex.context import make_simple_context
from cortex.model import ModelParams
from cortex.tools.client_tool import ClientTool
from cortex.tools.toolset import ToolSet
from cortex.tools.types import ToolType

logger = logging.getLogger(__name__)


async def init_plan_tools() -> ToolSet:
    """Initialize plan toolset"""
    toolset = ToolSet()

    # Register web_search tool
    await toolset.register_from_mcp_server(
        mcp_server="http://xxx/mcp",
        tool_names=["web_search"],
    )

    # Register ask_input tool (ClientTool)
    ask_input_tool = ClientTool(
        name="ask_input",
        description="Ask users for input, confirmation, or modification suggestions. Used for scenarios requiring user interaction such as obtaining user feedback, confirming plans, modifying suggestions, etc. Parameters: prompt (required) - prompt message to display to the user; context (optional) - context information to help users understand the current situation.",
        tool_type=ToolType.ASK_INPUT,
        channel=toolset.channel,
        timeout=300.0,  # User input may take a long time
        client_params={
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Prompt message to display to the user, explaining what the user needs to do (confirm, modify, provide information, etc.)",
                },
                "context": {
                    "type": "string",
                    "description": "Context information to help users understand the current situation, such as current plan content, items that need confirmation, etc.",
                },
            },
            "required": ["prompt"],
        },
    )
    toolset.register(ask_input_tool)
    logger.info("Registered ask_input tool")

    return toolset


async def make_plan_agent(context_id: str, config: AgentConfig) -> BaseAgent:
    """Create PlanAgent"""
    toolset = await init_plan_tools()
    context = make_simple_context(context_id)
    return ReActAgent(context=context, config=config, toolset=toolset)


def get_plan_agent_config() -> AgentConfig:
    """Get PlanAgent configuration"""
    return AgentConfig(
        name="PlanAgent",
        description="An Agent specialized in creating plans based on task objectives. Capable of analyzing task requirements, searching for relevant information, creating detailed plans, and finalizing plans after user confirmation or modification. Suitable for project planning, task decomposition, action plan creation, and similar scenarios.",
        system_prompt="""You are a professional planning assistant. Your responsibility is to create detailed, feasible plans based on the task objectives provided by the user.

Workflow:
1. **Understand Task Objectives**: Carefully analyze the task objectives provided by the user, understand the core requirements, expected results, and constraints of the task.

2. **Information Collection** (if needed):
   - If the task involves the need for latest information or professional knowledge, use the web_search tool to search for relevant information
   - Collect background knowledge, best practices, case references, etc. related to the task

3. **User Confirmation and Modification**:
   - Break down the task into clear steps
   - Use the ask_input tool to show the preliminary plan to the user
   - Clearly explain the plan content in the prompt and ask the user if modifications are needed
   - Provide detailed plan content in context for the user to review
   - Adjust the plan based on user feedback (confirmation, modification suggestions, etc.)

4. **Create Final Plan**:
   - Create the final plan based on user confirmation or modification feedback
   - Ensure the plan is complete, clear, and executable
   - Provide a summary of the plan and execution suggestions

Important Principles:
- Be sure to use the ask_input tool to show the preliminary plan to the user and adjust the plan based on user feedback
- Be sure to output the final plan; the final plan does not need modification, just output it directly
- Plans should be specific and executable, avoiding being too abstract
- Consider practical feasibility and resource constraints""",
        model=ModelParams(
            name="gpt-5.1",
            infer_kwargs={"max_tokens": 2000, "temperature": 0.7, "stream": False},
        ),
    )
