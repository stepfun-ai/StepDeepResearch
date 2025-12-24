"""Runner interface definition."""

from abc import ABC, abstractmethod
from typing import AsyncGenerator

from cortex.agents.types import AgentConfig
from cortex.orchestrator.types import AgentEvent


class Runner(ABC):
    """Runner interface for handling AgentEvent sending and running."""

    def __init__(
        self,
        task_id: str,
        parent_task_id: str | None = None,
        root_task_id: str | None = None,
    ):
        """
        Initialize Runner.

        Args:
            task_id: Task ID
            parent_task_id: Parent task ID
            root_task_id: Root task ID
        """
        self._task_id: str = task_id
        self._parent_task_id: str | None = parent_task_id
        self._root_task_id: str | None = root_task_id

    def get_parent_task_id(self) -> str | None:
        """
        Get parent task ID.

        Returns:
            str | None: Parent task ID
        """
        return self._parent_task_id

    def get_root_task_id(self) -> str | None:
        """
        Get root task ID.

        Returns:
            str | None: Root task ID
        """
        return self._root_task_id

    @abstractmethod
    async def init(
        self,
        agent_name: str,
        context_id: str | None = None,
        config: AgentConfig | None = None,
    ) -> None:
        """
        Initialize Runner.

        Args:
            agent_name: Agent name
            context_id: Context ID
            config: AgentConfig
        """
        raise NotImplementedError

    @abstractmethod
    async def send(self, event: AgentEvent) -> None:
        """
        Send AgentEvent.

        Args:
            event: The AgentEvent to send
        """
        raise NotImplementedError

    @abstractmethod
    async def run(self) -> AsyncGenerator[AgentEvent, None]:
        """
        Run and return an AgentEvent generator.

        Yields:
            AgentEvent: Agent events
        """
        raise NotImplementedError

    @abstractmethod
    def get_result(self) -> AgentEvent:
        """
        Get AgentEvent.

        Returns:
            AgentEvent: AgentEvent
        """
        raise NotImplementedError
