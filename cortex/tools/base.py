"""Base Tool class."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .types import ToolType


@dataclass
class ToolSchema:
    """Tool schema definition."""

    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    return_type: Optional[str] = None
    tool_type: Optional[ToolType] = None


class Tool(ABC):
    """Base class for tools."""

    def __init__(
        self,
        name: str,
        description: str = "",
        tool_type: Optional[ToolType] = None,
        **kwargs,  # noqa: ARG002
    ):
        """
        Initialize the tool.

        Args:
            name: Tool name
            description: Tool description
            tool_type: Tool type
            **kwargs: Additional parameters (passed to subclasses)
        """
        self.name = name
        self.description = description
        self.tool_type = tool_type
        self._schema: Optional[ToolSchema] = None

    def get_schema(self) -> ToolSchema:
        """
        Get tool schema.

        Returns:
            ToolSchema: Tool schema object
        """
        if self._schema is None:
            self._schema = self._define_schema()
        return self._schema

    @abstractmethod
    def _define_schema(self) -> ToolSchema:
        """
        Define tool schema (must be implemented by subclasses).

        Returns:
            ToolSchema: Tool schema object
        """
        pass  # pragma: no cover

    async def call(self, parameters: str, **kwargs) -> Any:
        """
        Call the tool (async).

        Args:
            parameters: Tool parameters (string format)
            **kwargs: Additional parameters

        Returns:
            Any: Tool execution result
        """
        return await self._call(parameters, **kwargs)

    @abstractmethod
    async def _call(self, parameters: str, **kwargs) -> Any:
        """
        Tool call implementation (must be implemented by subclasses).

        Args:
            parameters: Tool parameters (string format)
            **kwargs: Additional parameters

        Returns:
            Any: Tool execution result
        """
