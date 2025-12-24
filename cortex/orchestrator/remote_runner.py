from typing import AsyncGenerator

from cortex.agents.types import AgentConfig, AgentRunningStatus
from cortex.orchestrator.runner import Runner
from cortex.orchestrator.types import AgentEvent, AgentEventType
from cortex.server.channel.channel import Channel


class RemoteRunner(Runner):
    """Remote Agent runner that communicates with remote services through Channel."""

    def __init__(self, channel: Channel):
        """
        Initialize remote runner.

        Args:
            channel: Channel instance for communicating with remote services
        """
        self.channel = channel
        self._task_id: str | None = None
        self._running: bool = False

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
        # Remote runner doesn't need local configuration, configuration is on the remote server side
        # If needed, you can save config or perform other initialization here

    async def send(self, event: AgentEvent) -> None:
        """
        Send AgentEvent to remote service.

        Args:
            event: The AgentEvent to send
        """
        if event.type == AgentEventType.REQUEST:
            # Save task_id
            if self._task_id is None:
                self._task_id = event.task_id

        # Send event to remote service
        await self.channel.send(event.model_dump())

    async def run(self) -> AsyncGenerator[AgentEvent, None]:
        """
        Run and return an AgentEvent generator, receiving events from remote service.

        Yields:
            AgentEvent: Agent events
        """
        if self._task_id is None:
            raise ValueError("task_id is not set, please call send() to send REQUEST event first")

        self._running = True

        try:
            while self._running:
                # Receive events from remote service
                data = await self.channel.receive()
                event = AgentEvent.model_validate(data)

                # Only yield events related to current task_id
                if event.task_id == self._task_id:
                    yield event

                    # Stop receiving if error or completion signal is received
                    if event.type == AgentEventType.ERROR:
                        break
                    elif event.type == AgentEventType.RESPONSE and event.response:
                        if event.response.status in (
                            AgentRunningStatus.FINISHED,
                            AgentRunningStatus.STOPPED,
                            AgentRunningStatus.ERROR,
                        ):
                            break
        finally:
            self._running = False
