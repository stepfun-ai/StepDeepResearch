"""Function Tool implementation."""

import inspect
import json
from typing import Any, Callable, Optional

from agents.function_schema import function_schema

from .base import Tool, ToolSchema
from .types import ToolType


class FunctionTool(Tool):
    """Function tool implementation."""

    def __init__(
        self, name: str, func: Callable, description: Optional[str] = None, **kwargs
    ):
        """
        Initialize function tool.

        Args:
            name: Tool name
            func: Function to wrap
            description: Tool description
            **kwargs: Additional parameters
        """
        self.func = func
        description = description or func.__doc__ or ""

        super().__init__(
            name=name, description=description, tool_type=ToolType.FUNCTION, **kwargs
        )

    def _define_schema(self) -> ToolSchema:
        """Define function tool schema."""
        # Infer parameters from function signature
        # strict_json_schema=False to preserve default value behavior for optional parameters
        data = function_schema(self.func, strict_json_schema=False)
        return ToolSchema(
            name=data.name,
            description=data.description,
            parameters=data.params_json_schema,
            return_type="any",
        )

    async def _call(self, parameters: str, **kwargs) -> Any:
        """
        Call the function tool.

        Args:
            parameters: Tool parameters (string format)
            **kwargs: Additional parameters

        Returns:
            Any: Function execution result
        """
        # Convert parameters to dictionary
        parameters_dict = json.loads(parameters)
        # If the function is async
        if inspect.iscoroutinefunction(self.func):
            return await self.func(**parameters_dict)
        else:
            # Call sync function in async context
            import asyncio

            return await asyncio.to_thread(self.func, **parameters_dict)
