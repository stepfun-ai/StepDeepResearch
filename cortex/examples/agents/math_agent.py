"""MathAgent - An Agent that can solve mathematical problems."""

import logging
import math
from uuid import uuid4

from cortex.agents.base_agent import BaseAgent
from cortex.agents.react_agent import ReActAgent
from cortex.agents.types import AgentConfig
from cortex.context import make_simple_context
from cortex.model import ModelParams
from cortex.tools.function_tool import FunctionTool
from cortex.tools.toolset import ToolSet

logger = logging.getLogger(__name__)


# Basic math operation tool functions
def add(a: float, b: float) -> float:
    """Add two numbers.

    Args:
        a: First number
        b: Second number

    Returns:
        Sum of the two numbers
    """
    return a + b


def subtract(a: float, b: float) -> float:
    """Subtract two numbers.

    Args:
        a: Minuend
        b: Subtrahend

    Returns:
        Difference of the two numbers
    """
    return a - b


def multiply(a: float, b: float) -> float:
    """Multiply two numbers.

    Args:
        a: First number
        b: Second number

    Returns:
        Product of the two numbers
    """
    return a * b


def divide(a: float, b: float) -> float:
    """Divide two numbers.

    Args:
        a: Dividend
        b: Divisor (cannot be 0)

    Returns:
        Quotient of the two numbers

    Raises:
        ValueError: When divisor is 0
    """
    if b == 0:
        raise ValueError("Divisor cannot be 0")
    return a / b


def power(base: float, exponent: float) -> float:
    """Calculate power operation.

    Args:
        base: Base number
        exponent: Exponent

    Returns:
        Base raised to the power of exponent
    """
    return base**exponent


def sqrt(number: float) -> float:
    """Calculate square root.

    Args:
        number: Number to calculate square root (must be >= 0)

    Returns:
        Square root of the number

    Raises:
        ValueError: When number is less than 0
    """
    if number < 0:
        raise ValueError("Cannot calculate square root of negative number")
    return math.sqrt(number)


def calculate_expression(expression: str) -> float:
    """Calculate a mathematical expression (using eval, for simple expressions only).

    Args:
        expression: Mathematical expression string, e.g., "2 + 3 * 4"

    Returns:
        Calculation result

    Warning:
        This function uses eval, only for simple mathematical expressions, do not use for untrusted input
    """
    # Only allow numbers, operators, and parentheses
    allowed_chars = set("0123456789+-*/.() ")
    if not all(c in allowed_chars for c in expression):
        raise ValueError("Expression contains disallowed characters")
    try:
        return float(eval(expression))
    except Exception as e:
        raise ValueError(f"Expression calculation error: {str(e)}")


async def init_math_tools() -> ToolSet:
    """Initialize math toolset."""
    toolset = ToolSet()

    # Register basic math operation tools
    math_functions = [
        ("add", add, "Addition: add two numbers"),
        ("subtract", subtract, "Subtraction: subtract two numbers"),
        ("multiply", multiply, "Multiplication: multiply two numbers"),
        ("divide", divide, "Division: divide two numbers"),
        ("power", power, "Power: calculate a number raised to a power"),
        ("sqrt", sqrt, "Square root: calculate the square root of a number"),
        (
            "calculate_expression",
            calculate_expression,
            "Calculate expression: evaluate a simple mathematical expression string",
        ),
    ]

    for tool_name, tool_func, tool_desc in math_functions:
        function_tool = FunctionTool(
            name=tool_name,
            func=tool_func,
            description=tool_desc,
        )
        toolset.register(function_tool)
        logger.info(f"Registered math tool: {tool_name}")

    return toolset


async def make_math_agent(
    config: AgentConfig, context_id: str | None = None
) -> BaseAgent:
    """Create MathAgent."""
    toolset = await init_math_tools()
    if context_id is None:
        context_id = uuid4().hex
    context = make_simple_context(context_id)
    return ReActAgent(context=context, config=config, toolset=toolset)


def get_math_agent_config() -> AgentConfig:
    """Get MathAgent configuration."""
    return AgentConfig(
        name="MathAgent",
        description="An Agent specialized for mathematical calculations. Supports basic math operations (addition, subtraction, multiplication, division, power, square root, etc.), can handle complex mathematical expressions, supports multi-step calculations, and provides detailed calculation process explanations. Suitable for arithmetic, algebra, geometry calculations, and mathematical expression solving.",
        system_prompt="You are a professional mathematical calculation assistant.",
        model=ModelParams(
            name="gpt-4o-mini",
            infer_kwargs={"max_tokens": 2000, "temperature": 0.7, "stream": False},
        ),
    )
