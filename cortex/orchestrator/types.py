from enum import Enum
from uuid import uuid4

from cortex.model.definition import ChatMessage, Function
from pydantic import BaseModel, Field

from cortex.agents.types import AgentConfig, AgentResponse


class AgentEventType(str, Enum):
    """Agent event type enum."""

    REQUEST = "request"
    RESPONSE = "response"
    ERROR = "error"
    SIGNAL = "signal"
    CLIENT_TOOL_CALL = "client_tool_call"
    CLIENT_TOOL_RESULT = "client_tool_result"


class AgentRequest(BaseModel):
    """Agent request model."""

    agent_name: str
    config: AgentConfig | None = None
    messages: list[ChatMessage] | None = None


class ClientToolCallType(str, Enum):
    """Client tool call type enum."""

    AGENT = "agent"
    TOOL = "tool"
    ASK_INPUT = "ask_input"


class ClientToolCall(BaseModel):
    """Client tool call model."""

    tool_call_id: str
    function: Function
    type: ClientToolCallType
    extra: dict | None = None


class AgentEvent(BaseModel):
    """Agent event model."""

    event_id: str = Field(default_factory=lambda: f"{uuid4().hex}")
    task_id: str | None = None
    parent_task_id: str | None = None
    root_task_id: str | None = None
    type: AgentEventType
    metadata: dict | None = None
    agent_name: str | None = None

    # Input
    request: AgentRequest | None = None

    # Output
    response: AgentResponse | None = None
    error: str | None = None

    # client tool call
    client_tool_call: ClientToolCall | None = None
    client_tool_result: AgentResponse | None = None
