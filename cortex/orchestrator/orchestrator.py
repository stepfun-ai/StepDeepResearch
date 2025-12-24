"""Orchestrator for coordinating execution of multiple Agents."""

import logging
from enum import Enum
from typing import AsyncGenerator, Optional
from uuid import uuid4

from cortex.agents.agent_factory import AgentFactory
from cortex.agents.types import AgentConfig, AgentResponse, AgentRunningStatus
from cortex.orchestrator.local_runner import LocalRunner
from cortex.orchestrator.runner import Runner
from cortex.orchestrator.types import (
    AgentEvent,
    AgentEventType,
    AgentRequest,
    ClientToolCallType,
)
from cortex.tools.agent_tool import AgentTool
from cortex.utils.generator_merger import GeneratorMerger

logger = logging.getLogger(__name__)


class OrchMode(str, Enum):
    """Orchestrator mode."""

    MULTI = "multi"
    SINGLE = "single"


class Orchestrator:
    """Orchestrator for coordinating execution of multiple Agents."""

    def __init__(self, agent_factory: AgentFactory):
        """Initialize Orchestrator.

        Args:
            agent_factory: AgentFactory instance for creating Agents
        """
        self._agent_factory = agent_factory
        # Manage runner by task_id
        self._runners: dict[str, Runner] = {}
        # Manage generator_merger by root_task_id
        self._mergers: dict[str, GeneratorMerger] = {}
        # Record task_id to root_task_id mapping
        self._task_to_root: dict[str, str] = {}
        # Record task_id to parent_task_id mapping
        self._task_to_parent: dict[str, str] = {}
        # Record runner's task_id (for cleanup)
        self._runner_task_ids: dict[str, str] = {}  # runner_id -> task_id

    def list_agents(self) -> list[AgentConfig]:
        """List all Agent configurations."""
        return self._agent_factory.list_agents()

    async def run(
        self,
        agent_name: str,
        event: AgentEvent,
        agent_config: AgentConfig | None = None,
        mode: OrchMode = OrchMode.MULTI,
        context_id: str | None = None,
    ) -> AsyncGenerator[AgentEvent, None]:
        """Run Agent and return response stream.

        Args:
            agent_name: Agent name
            messages: Message list
            agent_config: Agent configuration

        Yields:
            AgentEvent: Agent event
        """
        task_id = event.task_id or f"root_{uuid4().hex}"
        root_task_id = event.root_task_id or task_id
        parent_task_id = event.parent_task_id or None
        event.task_id = task_id
        event.root_task_id = root_task_id
        event.parent_task_id = parent_task_id
        if context_id is None:
            context_id = task_id

        # Create root runner
        runner = await self._create_runner(
            task_id=task_id,
            parent_task_id=parent_task_id,
            root_task_id=root_task_id,
        )

        # Initialize runner
        await runner.init(agent_name, context_id, agent_config)

        async def on_generator_complete_with_mode(
            generator_id: str, _generator_type: str, error: Optional[Exception]
        ) -> None:
            await self._on_generator_complete(
                generator_id, _generator_type, error, mode
            )

        # Create generator_merger to merge events
        merger = GeneratorMerger(on_generator_complete=on_generator_complete_with_mode)
        self._mergers[root_task_id] = merger

        need_run_root_runner = True
        while need_run_root_runner:
            need_run_root_runner = False
            await self.run_root_runner(runner, merger, root_task_id, event)
            event = None

            # Get events from merger and yield AgentResponse
            async for event in merger.merge():
                if not isinstance(event, AgentEvent):
                    continue

                # Handle client tool call
                if (
                    mode == OrchMode.MULTI
                    and event.type == AgentEventType.CLIENT_TOOL_CALL
                ):
                    # Check if it's AGENT type, only AGENT type needs special handling
                    client_tool_call = event.client_tool_call
                    if (
                        client_tool_call
                        and client_tool_call.type == ClientToolCallType.AGENT
                    ):
                        await self._handle_client_tool_call(
                            context_id, event, root_task_id
                        )
                        need_run_root_runner = True
                    else:
                        # Non-AGENT type CLIENT_TOOL_CALL (e.g., ASK_INPUT, TOOL) yield directly
                        yield event
                else:
                    yield event

        self._cleanup_runner(task_id)

    async def run_root_runner(
        self,
        runner: Runner,
        merger: GeneratorMerger,
        root_task_id: str,
        event: AgentEvent,
    ):
        # Add runner's run() to merger
        async def runner_generator() -> AsyncGenerator[AgentEvent, None]:
            async for event in runner.run():
                yield event

        merger.add_async_generator(runner_generator, generator_id=root_task_id)
        if event is None:
            return
        if event.type == AgentEventType.REQUEST and len(event.request.messages) > 0:
            # Send REQUEST event
            await runner.send(event)
        elif event.type == AgentEventType.CLIENT_TOOL_RESULT:
            await runner.send(event)

    async def send_event(self, event: AgentEvent) -> None:
        """Receive external input AgentEvent, find runner by task_id and send.

        Args:
            event: AgentEvent
        """
        task_id = event.task_id
        runner = self._runners.get(task_id)
        if runner is None:
            logger.error("Cannot find runner for task_id=%s", task_id)
            raise ValueError("Cannot find runner for task_id=%s", task_id)
        await runner.send(event)

    async def _create_runner(
        self,
        task_id: str,
        parent_task_id: str | None = None,
        root_task_id: str | None = None,
        tool_call_id: str | None = None,
    ) -> Runner:
        """Create Runner instance.

        Args:
            task_id: Task ID
            parent_task_id: Parent task ID
            root_task_id: Root task ID
            tool_call_id: Tool call ID
        Returns:
            Runner instance
        """
        runner = LocalRunner(
            agent_factory=self._agent_factory,
            task_id=task_id,
            parent_task_id=parent_task_id,
            root_task_id=root_task_id,
            tool_call_id=tool_call_id,
        )
        self._runners[task_id] = runner
        if root_task_id:
            self._task_to_root[task_id] = root_task_id
        if parent_task_id:
            self._task_to_parent[task_id] = parent_task_id
        return runner

    async def _handle_client_tool_call(
        self, context_id: str, event: AgentEvent, root_task_id: str
    ):
        """Handle client tool call event.

        Args:
            event: AgentEvent, type is CLIENT_TOOL_CALL
            context_id: Context ID
            root_task_id: Root task ID

        Returns:
            None
        """
        client_tool_call = event.client_tool_call
        if client_tool_call is None:
            return

        # Determine if it's an agent based on client_tool_call.type
        is_agent = client_tool_call.type == ClientToolCallType.AGENT
        if not is_agent:
            # Not an agent, return directly
            return

        agent_name = client_tool_call.function.name
        # Get agent config
        try:
            agent_config = self._agent_factory.get_default_agent_config(agent_name)
        except ValueError:
            agent_config = None

        if agent_config is None:
            return

        child_task_id = f"child_{uuid4().hex}"
        # Create child runner
        child_runner = await self._create_runner(
            task_id=child_task_id,
            parent_task_id=event.task_id,
            root_task_id=root_task_id,
            tool_call_id=client_tool_call.tool_call_id,
        )

        # Initialize child runner
        await child_runner.init(agent_name, context_id, agent_config)

        # Get merger for root_task_id
        merger = self._mergers.get(root_task_id)
        if merger is None:
            raise ValueError(f"Cannot find merger for root_task_id={root_task_id}")

        # Prepare messages (convert tool call to user message)
        tool_call_messages = AgentTool.parse_messages(
            client_tool_call.function.arguments
        )
        if tool_call_messages is None:
            tool_call_messages = []

        # Add child runner's run() to merger
        async def child_runner_generator() -> AsyncGenerator[AgentEvent, None]:
            # Send REQUEST event to child runner
            await child_runner.send(
                AgentEvent(
                    task_id=child_task_id,
                    parent_task_id=event.task_id,
                    root_task_id=root_task_id,
                    type=AgentEventType.REQUEST,
                    request=AgentRequest(
                        agent_name=agent_name,
                        config=agent_config,
                        messages=tool_call_messages,
                    ),
                )
            )

            # Run child runner and yield events
            async for child_event in child_runner.run():
                yield child_event

        merger.add_async_generator(child_runner_generator, generator_id=child_task_id)
        self._runner_task_ids[child_task_id] = child_task_id

    async def _on_generator_complete(
        self,
        generator_id: str,
        _generator_type: str,
        error: Optional[Exception],
        mode: OrchMode,
    ) -> None:
        """Handle generator complete event (callback).

        Args:
            generator_id: Generator ID (usually task_id)
            _generator_type: Generator Type (unused, kept for interface compatibility)
            error: Error message (if any)
        """
        # Find corresponding runner
        task_id = generator_id
        runner = self._runners.get(task_id)
        if runner is None:
            return

        if mode == OrchMode.SINGLE:
            self._cleanup_runner(task_id)
            return

        # Get parent_task_id
        parent_task_id = self._task_to_parent.get(task_id)
        if parent_task_id is None:
            # No parent, means this is root runner, no need to send result
            return

        # Has parent, need to send result to parent runner
        parent_runner = self._runners.get(parent_task_id)
        if parent_runner is None:
            # Parent runner doesn't exist, cleanup current runner
            self._cleanup_runner(task_id)
            return

        # Create result response
        if error:
            result_response = AgentResponse(
                status=AgentRunningStatus.ERROR,
                error_msg=str(error),
            )
        else:
            # Completed normally
            runner_result = runner.get_result()
            if runner_result is None:
                result_response = AgentResponse(
                    status=AgentRunningStatus.ERROR,
                    error_msg=f"runner {task_id} did not return result",
                )
            else:
                result_response = runner_result.client_tool_result

        # Send CLIENT_TOOL_RESULT event to parent runner
        await parent_runner.send(
            AgentEvent(
                task_id=parent_task_id,
                parent_task_id=parent_runner.get_parent_task_id(),
                root_task_id=parent_runner.get_root_task_id(),
                type=AgentEventType.CLIENT_TOOL_RESULT,
                client_tool_result=result_response,
            )
        )

        # Cleanup completed runner
        self._cleanup_runner(task_id)

    def _cleanup_runner(self, task_id: str) -> None:
        """Cleanup completed runner.

        Args:
            task_id: Task ID
        """
        # Remove from runners
        if task_id in self._runners:
            del self._runners[task_id]

        # Remove from mappings
        if task_id in self._task_to_root:
            del self._task_to_root[task_id]

        if task_id in self._task_to_parent:
            del self._task_to_parent[task_id]

        if task_id in self._runner_task_ids:
            del self._runner_task_ids[task_id]

        # If it's root_task_id, cleanup merger
        if task_id in self._mergers:
            del self._mergers[task_id]
