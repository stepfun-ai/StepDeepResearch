"""Tool types and enums."""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ToolParameters(BaseModel):
    """Tool parameters model."""

    parameters: str = Field(description="Tool parameters", default="")
    kwargs: Dict[str, Any] = Field(description="Additional parameters", default={})


class ToolType(Enum):
    """Tool type enum."""

    MCP = "mcp"
    FUNCTION = "function"
    SESSION = "session"
    CLIENT = "client"
    AGENT = "agent"
    ASK_INPUT = "ask_input"


class ExecutionType(Enum):
    """Execution type enum."""

    SYNC = "sync"
    ASYNC = "async"


@dataclass
class ToolConfig:
    """Tool configuration."""

    name: str
    tool_type: ToolType
    params: Optional[Dict[str, Any]] = None
    schema: Optional[Dict[str, Any]] = None
