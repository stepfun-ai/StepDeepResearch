"""Deep Research Agent

Configured with shell, web_surfer, and todo tools for executing deep research tasks.
"""

import logging
import os
from uuid import uuid4

from cortex.agents.base_agent import BaseAgent
from cortex.agents.base_step_agent import (
    DEFAULT_FORCE_FINAL_ANSWER_PROMPT,
)
from cortex.agents.react_agent import ReActAgent
from cortex.agents.types import AgentConfig
from cortex.context import make_simple_context
from cortex.model import ModelParams
from cortex.model.stepfun_provider import StepFunModelProvider
from cortex.tools.toolset import ToolSet
from demo.tools.batch_web_surfer import create_batch_web_surfer_tool
from demo.tools.file import create_file_tool
from demo.tools.shell import create_shell_tool
from demo.tools.todo import create_todo_tool

logger = logging.getLogger(__name__)


async def init_dr_tools(context_id: str | None = None) -> ToolSet:
    """Initialize deep research toolset.
    
    Contains four tools:
    - shell: Execute shell commands
    - web_surfer: Search and open web pages
    - file: Read/write/list local files
    - todo: Task and plan management
    
    Args:
        context_id: Context ID for isolating todo files.
    """
    toolset = ToolSet()

    # 1. Shell tool
    shell_tool = create_shell_tool()
    toolset.register(shell_tool)

    # 2. Web Surfer tool (requires STEP_SEARCH_API_KEY or STEP_API_KEY)
    web_surfer_tool = create_batch_web_surfer_tool()
    if web_surfer_tool:
        toolset.register(web_surfer_tool)
    else:
        logger.warning(
            "web_surfer tool not registered, please check STEP_SEARCH_API_KEY/STEP_API_KEY"
        )

    # 3. File tool (read/write/list local files)
    file_tool = create_file_tool()
    toolset.register(file_tool)

    # 4. Todo tool (pass context_id to isolate different sessions)
    todo_tool = create_todo_tool(context_id=context_id)
    toolset.register(todo_tool)

    logger.info(f"Registered tools: {toolset.list_tools()}")
    return toolset


async def make_dr_agent(
        config: AgentConfig,
        context_id: str | None = None,
        provider_type: str | None = None,
) -> BaseAgent:
    """Create Deep Research Agent.
    
    Args:
        config: Agent configuration.
        context_id: Context ID, auto-generated if None.
        provider_type: Model provider type, "stepfun" or "vllm". 
                       If None, reads from MODEL_PROVIDER env var, defaults to "stepfun".
        
    Returns:
        BaseAgent: ReActAgent configured with shell, web_surfer, and todo tools.
    """
    # Get provider_type from environment variable if not specified
    if provider_type is None:
        provider_type = os.getenv("MODEL_PROVIDER", "stepfun")
    if context_id is None:
        context_id = uuid4().hex
    
    # Pass context_id to isolate todo files
    toolset = await init_dr_tools(context_id=context_id)
    context = make_simple_context(context_id)

    # Select model provider based on provider_type
    provider = StepFunModelProvider(model_params=config.model)

    return ReActAgent(context=context, config=config, toolset=toolset, provider=provider)


def get_dr_agent_config() -> AgentConfig:
    """Get Deep Research Agent default configuration.
    Uses StepFun model with inference parameters configured via infer_kwargs.
    """
    return AgentConfig(
        name="DeepResearchAgent",
        description=(
            "Deep Research Agent with the following capabilities:\n"
            "1. shell - Execute shell commands, run scripts, install software, operate files\n"
            "2. web_surfer - Search internet information, open and read web page content\n"
            "3. file - Read/write/list local files to inspect outputs or assets\n"
            "4. todo - Manage task lists, track research progress and plans\n"
            "Suitable for complex research tasks requiring information collection, code execution, and task planning."
        ),
        system_prompt="""**任务目标:** 针对以下问题，请进行深入、详尽的调查与分析，并提供一个经过充分验证的、全面的答案。
**核心要求:** 在整个过程中，你需要**最大化地、策略性地使用你可用的工具** (例如：搜索引擎、代码执行器等)，并**清晰地展示你的思考、决策和验证过程**。不仅仅是给出最终答案，更要展现获得答案的严谨路径。
**行为指令:**
1.  **启动调查 (Initiate Investigation):** 首先分析问题，识别关键信息点和潜在的约束条件。初步规划你需要哪些信息（使用todo工具制定你的调查计划），并使用工具（如搜索）开始收集。
2.  **迭代式信息收集与反思 (Iterative Information Gathering & Reflection):**
    * **处理搜索失败:** 如果首次搜索（或后续搜索）未能找到相关结果或结果不佳，**必须**明确说明（例如："初步搜索未能找到关于'XXX'的直接信息，尝试调整关键词为'YYY'再次搜索。"），并调整策略（修改关键词、尝试不同搜索引擎或数据库、扩大搜索范围如增加top K结果数量并说明"之前的Top K结果不足，现在尝试查看更多页面获取信息"）。
    * **评估信息充分性:** 在获取部分信息后，**必须**停下来评估这些信息是否足以回答原始问题的所有方面（例如："已找到关于'AAA'的信息，但问题中提到的'BBB'方面尚未覆盖，需要继续搜索'BBB'相关内容。"）。
    * **追求信息深度:** 即使已有一些信息，如果觉得不够深入或全面，**必须**说明需要更多信息来源并继续搜索（例如："现有信息提供了基础，但为确保全面性，需要查找更多权威来源或不同角度的报道来深化理解。"）。
    * **信源考量:** 在引用信息时，**主动思考并简述**信息来源的可靠性或背景（例如："这个信息来自'XYZ网站'，该网站通常被认为是[领域]的权威来源/是一个用户生成内容平台，信息需要进一步核实。"）。
3.  **多源/多工具交叉验证 (Multi-Source/Multi-Tool Cross-Validation):**
    * **主动验证:** **不要**满足于单一来源的信息。**必须**尝试使用不同工具或搜索不同来源来交叉验证关键信息点（例如："为确认'CCC'数据的准确性，让我们尝试用另一个搜索引擎或查询官方数据库进行验证。" 或 "让我们用代码计算器/Python工具来验证刚才推理中得到的数值/字符串处理结果。"）。
    * **工具切换:** 如果一个工具不适用或效果不佳，**明确说明**并尝试使用其他可用工具（例如："搜索引擎未能提供结构化数据，尝试使用代码执行器分析或提取网页内容。"）。
4.  **约束条件检查 (Constraint Checklist):** 在整合信息和形成答案之前，**必须**明确回顾原始问题的所有约束条件，并逐一确认现有信息是否完全满足这些条件（例如："让我们检查一下：问题要求时间在'2023年后'，地点为'欧洲'，并且涉及'特定技术'。目前收集到的信息 A 满足时间，信息 B 满足地点，信息 C 涉及该技术... 所有约束均已覆盖。"）。
5.  **计算与操作验证 (Calculation & Operation Verification):** 如果在你的思考链（Chain of Thought）中进行了任何计算、数据提取、字符串操作或其他逻辑推导，**必须**在最终确定前使用工具（如代码执行器）进行验证，并展示验证步骤（例如："推理得出总和为 X，现在使用代码验证：`print(a+b)` ... 结果确认是 X。"）。
6.  **清晰的叙述:** 在每一步工具调用前后，用简短的语句**清晰说明你为什么要调用这个工具、期望获得什么信息、以及调用后的结果和下一步计划**。这包括上述所有反思和验证的插入语。
制定计划： 在开始收集信息之前，请先分析问题，并使用todo工具制定你的行动计划。
格式要求： 每次执行工具调用后，分析返回的的信息，如果已收集到足够的信息，可以直接回答用户请求，否则继续执行工具调用。在整个过程中，请始终明确你的目标是回答用户请求。当通过充分的工具调用获取并验证了所有必要信息后，在 <answer>...</answer> 中输出一个详尽全面的报告。如果报告中的某个句子参考了搜索信息，你需要引用搜索到的最相关的段落来支撑这句话，将LaTeX的\\cite{网页引用标签}作为链接引用符放到句子中来表示引用，结构为\\cite{web_xxxxxxxx}。
报告要求：请确保深度、全面地回答任务中的所有子问题，采用符合用户提问的语言风格和结构，使用逻辑清晰、论证充分的长段落，禁止碎片化罗列。论证需要基于具体的数字和最新的权威引用，进行必要的关联对比分析、利弊权衡、风险讨论，并确保事实准确、术语清晰，避免模糊和绝对化措辞。""",
        model=ModelParams(
            name="step-dr-1",
            infer_kwargs={
                "max_tokens": 16384,
                "temperature": 0.8,
                "stream": True,
                "reasoning_format": "deepseek-style",  # StepFun parameter
            },
            explicit_api_base=os.getenv("MODEL_BASE", "https://api.stepfun.com"),
            # Prefer the dedicated model key; fall back to legacy STEP_API_KEY for compatibility.
            explicit_api_key=os.getenv("STEP_MODEL_API_KEY") or os.getenv("STEP_API_KEY", ""),
        ),
        max_steps=50,
        extra_config={
            "force_final_answer": True,
            "final_answer_prompt": DEFAULT_FORCE_FINAL_ANSWER_PROMPT,
        },
    )
