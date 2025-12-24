from enum import Enum

from cortex.model.definition import ChatMessage, ModelParams
from cortex.model.utils import merge_delta_message
from pydantic import BaseModel, Field

from cortex.tools.base import ToolSchema


class RunnerType(str, Enum):
    """Agent runner type enum."""

    LOCAL = "local"
    REMOTE = "remote"


class AgentRunningStatus(str, Enum):
    """Agent running status enum."""

    FINISHED = "finished"
    STOPPED = "stopped"
    ERROR = "error"
    RUNNING = "running"


class AgentMessageType(str, Enum):
    """Agent message type enum."""

    STREAM = "stream"  # Streaming output
    ACCUMULATED = "accumulated"  # Accumulated output
    FINAL = "final"  # Final output


class AgentResponseType(str, Enum):
    """Agent response type enum."""

    RESPONSE = "response"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"


class AgentConfig(BaseModel):
    """Declarative configuration for Agent."""

    model: ModelParams
    name: str = Field(default="")
    agent_type: str | None = None
    system_prompt: str | None = None
    description: str | None = None
    tools: list[ToolSchema | str] = Field(default_factory=list)
    max_steps: int = 10
    extra_config: dict | None = None
    runner_type: RunnerType = RunnerType.LOCAL
    endpoint: str | None = None
    unfinished_mode: bool = False
    use_share_context: bool = False


class AgentResponse(BaseModel):
    """Agent response model."""

    agent_name: str | None = None
    message: ChatMessage | None = None
    message_type: AgentMessageType = (
        AgentMessageType.FINAL
    )  # delta: streaming output, accumulated: accumulated output, final: final output
    status: AgentRunningStatus = AgentRunningStatus.RUNNING
    error_msg: str | None = None
    metadata: dict[str, object] | None = None

    def get_type(self) -> AgentResponseType:
        """Get response type."""
        if self.message is None:
            return AgentResponseType.RESPONSE
        if self.message.tool_call_id is not None:
            return AgentResponseType.TOOL_CALL
        if self.message.tool_calls is not None:
            return AgentResponseType.TOOL_CALL
        return AgentResponseType.RESPONSE

    def __add__(self, other: "AgentResponse") -> "AgentResponse":
        if not isinstance(other, AgentResponse):
            return NotImplemented

        # Merge delta_message dictionaries
        merged_delta_dict = merge_delta_message(
            self.message.model_dump() if self.message else None,
            other.message.model_dump() if other.message else None,
        )
        merged_delta = ChatMessage(**merged_delta_dict)

        # Create new field dictionary, default to self's fields
        new_fields = self.model_dump()
        new_fields["message"] = merged_delta

        # Iterate other fields, override with other's value if present
        for field, _ in self.model_dump().items():
            if field == "message":
                continue  # Already processed
            other_value = getattr(other, field)
            if other_value:
                new_fields[field] = other_value

        return AgentResponse(**new_fields)
