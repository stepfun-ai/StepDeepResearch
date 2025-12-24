"""Agent TUI - TUI interface built with Textual and Rich, displaying AgentEvent"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Callable, Optional

from agentkit.trace import SpanContext, Tracer
from cortex.model.definition import ChatMessage
from rich.console import Group, RenderableType
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.events import Key
from textual.widgets import Input, Label, ListItem, ListView, Static

from cortex.agents.types import AgentConfig, AgentResponse, AgentRunningStatus
from cortex.orchestrator import AgentEvent
from cortex.orchestrator.orchestrator import Orchestrator
from cortex.orchestrator.types import AgentEventType, AgentRequest, ClientToolCallType

logger = logging.getLogger(__name__)


def _content_to_string(content) -> str:
    """Convert content to string

    Args:
        content: Can be string, list, or dict

    Returns:
        str: Converted string
    """
    if content is None:
        return ""

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        # Handle list format content, e.g., [{"type": "text", "text": "..."}]
        text_parts = []
        for item in content:
            if isinstance(item, dict):
                # Try various possible key names to get text content
                text = None
                # Common key names
                for key in ["text", "content", "value"]:
                    if key in item:
                        text = item[key]
                        break
                # If not found, try to find fields with string values
                if not text:
                    for key, value in item.items():
                        if key != "type" and isinstance(value, str):
                            text = value
                            break
                if text:
                    text_parts.append(str(text))
            elif isinstance(item, str):
                text_parts.append(item)
        return "\n".join(text_parts)

    if isinstance(content, dict):
        # Handle dict format
        # Try various possible key names
        for key in ["text", "content", "value"]:
            if key in content:
                return str(content[key])
        # If not found, return string representation of entire dict
        return str(content)

    return str(content)


class EventItem(ListItem):
    """Event list item"""

    def __init__(self, event: AgentEvent, index: int):
        self.event = event
        self.index = index
        super().__init__()

    def render(self) -> RenderableType:
        """Render event item"""
        event = self.event
        event_type = event.type.value
        agent_name = event.agent_name or "N/A"
        task_id = (
            event.task_id[:8] + "..."
            if event.task_id and len(event.task_id) > 8
            else (event.task_id or "N/A")
        )

        # Set color based on event type
        type_colors = {
            "request": "blue",
            "response": "green",
            "error": "red",
            "signal": "yellow",
            "client_tool_call": "cyan",
            "client_tool_result": "magenta",
        }
        color = type_colors.get(event_type, "white")

        # Build display text
        lines = [
            Text(f"[{self.index}] ", style="dim"),
            Text(f"[{event_type}]", style=f"bold {color}"),
            Text(f" Agent: {agent_name}", style="cyan"),
            Text(f" Task: {task_id}", style="dim"),
        ]

        # Add response content
        if event.response and event.response.message:
            # Check if there are tool calls
            tool_calls = getattr(event.response.message, "tool_calls", None)
            has_tool_calls = False
            if tool_calls:
                if isinstance(tool_calls, (list, tuple)) and len(tool_calls) > 0:
                    has_tool_calls = True
                elif not isinstance(tool_calls, (list, tuple)):
                    has_tool_calls = True

            raw_content = event.response.message.content or ""
            content = _content_to_string(raw_content)

            # If no tool calls, show full markdown content
            if not has_tool_calls and content:
                # Use markdown to render full content
                header = Text.assemble(
                    Text(f"[{self.index}] ", style="dim"),
                    Text(f"[{event_type}]", style=f"bold {color}"),
                    Text(f" Agent: {agent_name}", style="cyan"),
                    Text(f" Task: {task_id}", style="dim"),
                )
                markdown_content = Markdown(content)
                return Panel(
                    Group(header, markdown_content),
                    border_style=color,
                    title=f"Event #{self.index}",
                )
            else:
                # With tool calls, only show preview
                if content:
                    preview = content[:50] + "..." if len(content) > 50 else content
                    lines.append(Text(f"\n  {preview}", style="dim"))

            # Add tool call info
            if tool_calls:
                if isinstance(tool_calls, (list, tuple)):
                    tool_names = []
                    for tool_call in tool_calls:
                        # Try to get tool name
                        if hasattr(tool_call, "function"):
                            if hasattr(tool_call.function, "name"):
                                tool_names.append(tool_call.function.name)
                            elif isinstance(tool_call.function, dict):
                                tool_names.append(
                                    tool_call.function.get("name", "unknown")
                                )
                        elif isinstance(tool_call, dict):
                            func = tool_call.get("function", {})
                            tool_names.append(
                                func.get("name", "unknown")
                                if isinstance(func, dict)
                                else "unknown"
                            )
                    if tool_names:
                        tools_str = ", ".join(tool_names)
                        lines.append(Text(f"\n  🔧 Tools: {tools_str}", style="yellow"))
                else:
                    # Single tool_call
                    if hasattr(tool_calls, "function"):
                        if hasattr(tool_calls.function, "name"):
                            lines.append(
                                Text(
                                    f"\n  🔧 Tool: {tool_calls.function.name}",
                                    style="yellow",
                                )
                            )

        # Add client_tool_call info
        if event.client_tool_call:
            tool_name = "unknown"
            tool_call_id = (
                getattr(event.client_tool_call, "tool_call_id", None) or "N/A"
            )

            if hasattr(event.client_tool_call, "function"):
                if hasattr(event.client_tool_call.function, "name"):
                    tool_name = event.client_tool_call.function.name
                elif isinstance(event.client_tool_call.function, dict):
                    tool_name = event.client_tool_call.function.get("name", "unknown")

            # Check if it's ask_input type
            tool_type = getattr(event.client_tool_call, "type", None)

            # Get function.arguments
            args_dict = {}
            context_content = None
            prompt_content = None
            if hasattr(event.client_tool_call, "function"):
                func = event.client_tool_call.function
                if hasattr(func, "arguments"):
                    args = func.arguments
                    if isinstance(args, str):
                        try:
                            args_dict = json.loads(args)
                        except json.JSONDecodeError:
                            args_dict = {"raw": args}
                    elif isinstance(args, dict):
                        args_dict = args
                    else:
                        args_dict = {}

                    # Check if context field exists
                    if isinstance(args_dict, dict) and "context" in args_dict:
                        context_content = args_dict.get("context")
                        # Remove context from args_dict, handle separately
                        args_dict = {
                            k: v for k, v in args_dict.items() if k != "context"
                        }

                    # Check if prompt field exists
                    if isinstance(args_dict, dict) and "prompt" in args_dict:
                        prompt_content = args_dict.get("prompt")
                        # Remove prompt from args_dict, handle separately
                        args_dict = {
                            k: v for k, v in args_dict.items() if k != "prompt"
                        }

            # Set icon and style based on type
            if tool_type == ClientToolCallType.ASK_INPUT:
                icon = "❓"
                style_color = "bold yellow"
                type_label = "Ask Input"
            elif tool_type == ClientToolCallType.AGENT:
                icon = "🤖"
                style_color = "bold cyan"
                type_label = "Agent Tool"
            else:
                icon = "🔧"
                style_color = "bold cyan"
                type_label = "Client Tool"

            # Show tool call basic info
            lines.append(
                Text(f"\n  {icon} {type_label}: {tool_name}", style=style_color)
            )
            lines.append(Text(f"  Tool Call ID: {tool_call_id}", style="dim"))

            # Show all parameters (except context)
            if args_dict:
                lines.append(
                    Text("\n  Parameters:", style=f"bold {style_color.split()[-1]}")
                )
                for key, value in args_dict.items():
                    value_str = (
                        json.dumps(value, ensure_ascii=False, indent=2)
                        if isinstance(value, (dict, list))
                        else str(value)
                    )
                    # If parameter value is too long, display on multiple lines
                    if len(value_str) > 200:
                        lines.append(Text(f"    {key}:", style=style_color))
                        # Display long content on multiple lines
                        for line in value_str.split("\n"):
                            if line.strip():
                                lines.append(Text(f"      {line}", style="dim"))
                    else:
                        lines.append(Text(f"    {key}: {value_str}", style="dim"))

            # If context exists, display with markdown
            if context_content is not None:
                context_str = _content_to_string(context_content)
                if context_str:
                    lines.append(
                        Text("\n  Context:", style=f"bold {style_color.split()[-1]}")
                    )
                    # Add context content to lines, will be rendered with Markdown later
                    # Add a marker here to indicate markdown rendering is needed
                    lines.append(("markdown_context", context_str))

            # If prompt exists, display with markdown
            if prompt_content is not None:
                prompt_str = _content_to_string(prompt_content)
                if prompt_str:
                    lines.append(
                        Text("\n  Prompt:", style=f"bold {style_color.split()[-1]}")
                    )
                    # Add prompt content to lines, will be rendered with Markdown later
                    lines.append(("markdown_prompt", prompt_str))

            # Show extra info
            if (
                hasattr(event.client_tool_call, "extra")
                and event.client_tool_call.extra
            ):
                lines.append(
                    Text("\n  Extra Info:", style=f"bold {style_color.split()[-1]}")
                )
                for key, value in event.client_tool_call.extra.items():
                    value_str = (
                        json.dumps(value, ensure_ascii=False, indent=2)
                        if isinstance(value, (dict, list))
                        else str(value)
                    )
                    if len(value_str) > 200:
                        lines.append(Text(f"    {key}:", style=style_color))
                        for line in value_str.split("\n"):
                            if line.strip():
                                lines.append(Text(f"      {line}", style="dim"))
                    else:
                        lines.append(Text(f"    {key}: {value_str}", style="dim"))

        # Add client_tool_result info
        if event.client_tool_result and event.client_tool_result.message:
            result_content = None
            tool_call_id = None

            # Get tool_call_id
            if hasattr(event.client_tool_result.message, "tool_call_id"):
                tool_call_id = event.client_tool_result.message.tool_call_id

            # Get user input content
            raw_content = event.client_tool_result.message.content or ""
            result_content = _content_to_string(raw_content)

            # Show tool call result
            lines.append(Text("\n  📥 Tool Call Result:", style="bold magenta"))
            if tool_call_id:
                lines.append(Text(f"  Tool Call ID: {tool_call_id}", style="dim"))

            # If content exists, display with markdown
            if result_content:
                lines.append(Text("\n  User Input:", style="bold magenta"))
                # Add user input content to lines, will be rendered with Markdown later
                lines.append(("markdown_result", result_content))

        # Add error info
        if event.error:
            lines.append(Text(f"\n  Error: {event.error}", style="red"))

        # Add completion signal info
        if event.type == AgentEventType.SIGNAL and event.metadata:
            status = event.metadata.get("status", "")
            message = event.metadata.get("message", "")
            if status == "completed":
                lines.append(Text(f"\n  ✅ {message}", style="green"))

        # Check if there's markdown content (context, prompt or result)
        markdown_context = None
        markdown_prompt = None
        markdown_result = None
        text_lines = []
        for item in lines:
            if isinstance(item, tuple) and len(item) == 2:
                if item[0] == "markdown_context":
                    markdown_context = item[1]
                elif item[0] == "markdown_prompt":
                    markdown_prompt = item[1]
                elif item[0] == "markdown_result":
                    markdown_result = item[1]
                else:
                    text_lines.append(item)
            else:
                text_lines.append(item)

        # If there's markdown content, combine Text and Markdown
        markdown_parts = []
        if markdown_context:
            markdown_parts.append(Markdown(markdown_context))
        if markdown_prompt:
            markdown_parts.append(Markdown(markdown_prompt))
        if markdown_result:
            markdown_parts.append(Markdown(markdown_result))

        if markdown_parts:
            header = Text.assemble(*text_lines)
            # If there are multiple markdown contents, combine with Group
            if len(markdown_parts) == 1:
                return Panel(
                    Group(header, markdown_parts[0]),
                    border_style=color,
                    title=f"Event #{self.index}",
                )
            else:
                return Panel(
                    Group(header, *markdown_parts),
                    border_style=color,
                    title=f"Event #{self.index}",
                )
        else:
            return Panel(
                Text.assemble(*text_lines),
                border_style=color,
                title=f"Event #{self.index}",
            )


class CommandItem(ListItem):
    """Command list item"""

    def __init__(self, command: str):
        self.command = command
        super().__init__()

    def render(self) -> RenderableType:
        """Render command item"""
        return Text(f"/{self.command}", style="cyan")


class AgentItem(ListItem):
    """Agent list item"""

    def __init__(self, agent_config: AgentConfig):
        self.agent_config = agent_config
        super().__init__()

    def render(self) -> RenderableType:
        """Render Agent item"""
        name = self.agent_config.name or "N/A"
        description = self.agent_config.description or "No description"
        agent_type = self.agent_config.agent_type or "N/A"

        lines = [
            Text(f"Name: {name}", style="bold cyan"),
            Text(f"  Type: {agent_type}", style="dim"),
            Text(f"  Description: {description}", style="dim"),
        ]

        return Panel(
            Text.assemble(*lines),
            border_style="blue",
            title=f"Agent: {name}",
        )


class ProcessView(Container):
    """Process view - displays event list"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.events: list[AgentEvent] = []
        self.list_view = ListView(id="event-list")
        self.json_view = Static("", id="process-json-view")

    def compose(self) -> ComposeResult:
        with Horizontal():
            with Container(id="process-list-container"):
                yield Label("Agent Event Stream", id="process-title")
                yield self.list_view
            with VerticalScroll(id="process-json-container"):
                yield Label("Event Details (JSON)", id="process-json-title")
                yield self.json_view

    def add_event(self, event: AgentEvent) -> None:
        """Add event to list"""
        self.events.append(event)
        index = len(self.events)
        item = EventItem(event, index)
        self.list_view.append(item)
        # Auto scroll to bottom
        self.list_view.scroll_end(animate=False)

    @on(ListView.Selected, "#event-list")
    def on_list_item_selected(self, event: ListView.Selected) -> None:
        """Handle list item selection"""
        if hasattr(event, "item") and isinstance(event.item, EventItem):
            event_obj = event.item.event
            json_text = event_obj.model_dump_json(indent=2, ensure_ascii=False)
            self.json_view.update(
                Panel(json_text, title="Event JSON", border_style="blue")
            )
            # Notify main app to update placeholder
            app = self.app
            if app and hasattr(app, "_update_placeholder_by_focus"):
                app._update_placeholder_by_focus()

    def clear_events(self) -> None:
        """Clear event list"""
        self.events.clear()
        self.list_view.clear()


class AgentsListView(Container):
    """Agents list view - displays registered Agents"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.list_view = ListView(id="agents-list")
        self.json_view = Static("", id="agents-json-view")
        self.selection_callback: Optional[Callable[[str], None]] = None

    def set_selection_callback(self, callback: Callable[[str], None]) -> None:
        """Set selection callback function"""
        self.selection_callback = callback

    def compose(self) -> ComposeResult:
        with Horizontal():
            with Container(id="agents-list-container"):
                yield Label("Registered Agents", id="agents-title")
                yield self.list_view
            with VerticalScroll(id="agents-json-container"):
                yield Label("Agent Details (JSON)", id="agents-json-title")
                yield self.json_view

    def update_agents(self, agents: list[AgentConfig]) -> None:
        """Update Agents list"""
        self.list_view.clear()
        for agent_config in agents:
            item = AgentItem(agent_config)
            self.list_view.append(item)

    @on(ListView.Selected, "#agents-list")
    def on_list_item_selected(self, event: ListView.Selected) -> None:
        """Handle list item selection"""
        if hasattr(event, "item") and isinstance(event.item, AgentItem):
            agent_config = event.item.agent_config
            json_text = agent_config.model_dump_json(indent=2, ensure_ascii=False)
            self.json_view.update(
                Panel(json_text, title="Agent Config JSON", border_style="green")
            )
            # Call callback to notify main app
            if self.selection_callback:
                self.selection_callback(agent_config.name)
            # Notify main app to update placeholder
            app = self.app
            if app and hasattr(app, "_update_placeholder_by_focus"):
                app._update_placeholder_by_focus()


class TaskItem(ListItem):
    """Task list item"""

    def __init__(self, task_id: str, request_data: dict):
        self.task_id = task_id
        self.request_data = request_data
        super().__init__()

    def render(self) -> RenderableType:
        """Render Task item"""
        task_id_short = (
            self.task_id[:16] + "..." if len(self.task_id) > 16 else self.task_id
        )
        messages = self.request_data.get("messages", [])
        content_preview = ""
        if messages and len(messages) > 0:
            first_msg = messages[0] if isinstance(messages, list) else messages
            if isinstance(first_msg, dict):
                content = first_msg.get("content", "")
            else:
                content = getattr(first_msg, "content", "")
            content_str = _content_to_string(content)
            content_preview = (
                content_str[:50] + "..." if len(content_str) > 50 else content_str
            )

        lines = [
            Text(f"Task ID: {task_id_short}", style="bold cyan"),
            Text(f"  Content: {content_preview}", style="dim"),
        ]

        return Panel(
            Text.assemble(*lines),
            border_style="green",
            title=f"Task: {task_id_short}",
        )


class TasksListView(Container):
    """Tasks list view - displays saved Tasks"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.list_view = ListView(id="tasks-list")
        self.json_view = Static("", id="tasks-json-view")
        self.selection_callback: Optional[Callable[[str], None]] = None

    def set_selection_callback(self, callback: Callable[[str], None]) -> None:
        """Set selection callback function"""
        self.selection_callback = callback

    def compose(self) -> ComposeResult:
        with Horizontal():
            with Container(id="tasks-list-container"):
                yield Label("Saved Tasks", id="tasks-title")
                yield self.list_view
            with VerticalScroll(id="tasks-json-container"):
                yield Label("Task Details (JSON)", id="tasks-json-title")
                yield self.json_view

    def update_tasks(self, tasks: list[tuple[str, dict]]) -> None:
        """Update Tasks list

        Args:
            tasks: [(task_id, request_data), ...] list
        """
        self.list_view.clear()
        for task_id, request_data in tasks:
            item = TaskItem(task_id, request_data)
            self.list_view.append(item)

    @on(ListView.Selected, "#tasks-list")
    def on_list_item_selected(self, event: ListView.Selected) -> None:
        """Handle list item selection"""
        if hasattr(event, "item") and isinstance(event.item, TaskItem):
            task_id = event.item.task_id
            request_data = event.item.request_data
            json_text = json.dumps(request_data, indent=2, ensure_ascii=False)
            self.json_view.update(
                Panel(json_text, title="Request JSON", border_style="green")
            )
            # Call callback to notify main app
            if self.selection_callback:
                self.selection_callback(task_id)


class CommandSelector(Container):
    """Command selector - displays command list and supports up/down key selection"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.command_list_view = ListView(id="command-list")
        self.matched_commands: list[str] = []

    def compose(self) -> ComposeResult:
        yield self.command_list_view

    def update_commands(self, commands: list[str]) -> None:
        """Update command list"""
        self.matched_commands = commands
        self.command_list_view.clear()
        for cmd in commands:
            item = CommandItem(cmd)
            self.command_list_view.append(item)
        # If there are commands, select the first one
        if commands:
            self.command_list_view.index = 0

    def get_selected_command(self) -> Optional[str]:
        """Get currently selected command"""
        if not self.matched_commands:
            return None
        # Get current selected index
        try:
            index = self.command_list_view.index
            if 0 <= index < len(self.matched_commands):
                return self.matched_commands[index]
        except Exception:
            pass
        # If no selected item, return the first one
        if self.matched_commands:
            return self.matched_commands[0]
        return None


class AgentTUIApp(App):
    """Agent TUI Application"""

    CSS = """
    #process-title, #process-json-title, #agents-title, #agents-json-title {
        text-style: dim;
        padding: 0 1;
        margin-bottom: 1;
        height: 1;
        text-align: left;
    }

    #process-view, #agents-view {
        height: 1fr;
    }
    
    #process-list-container, #agents-list-container {
        width: 50%;
        border-right: wide $primary;
        height: 1fr;
    }
    
    #process-json-container, #agents-json-container {
        width: 50%;
        height: 1fr;
    }
    
    #process-json-view, #agents-json-view {
        padding: 1;
    }
    
    #event-list, #agents-list {
        height: 1fr;
    }
    
    #input-container {
        height: auto;
        min-height: 3;
        border-top: wide $primary;
        margin-top: 1;
        padding-top: 1;
    }
    
    #selected-agent-label {
        height: 1;
        padding: 0 1;
        margin-bottom: 1;
        text-style: bold;
        background: $surface;
    }
    
    #input-box {
        width: 1fr;
    }
    
    #command-selector {
        height: auto;
        max-height: 10;
        border-top: wide $primary;
        background: $surface;
        margin-top: 1;
        margin-bottom: 1;
    }
    
    #command-list {
        height: auto;
        max-height: 10;
    }
    
    .hidden {
        display: none;
    }
    
    #main-container {
        height: 1fr;
        overflow: hidden;
    }
    
    Screen {
        layout: vertical;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("ctrl+c", "quit", "Quit"),
    ]

    def __init__(
        self,
        orchestrator: Orchestrator,
        workdir: Optional[str | Path] = None,
        tracer: Optional[Tracer] = None,
    ):
        super().__init__()
        self.process_view: Optional[ProcessView] = None
        self.agents_view: Optional[AgentsListView] = None
        self.tasks_view: Optional[TasksListView] = None
        self.command_selector: Optional[CommandSelector] = None
        self.input_box: Optional[Input] = None
        self.selected_agent_label: Optional[Label] = None
        self.orchestrator: Orchestrator = orchestrator
        self.running_task: Optional[asyncio.Task] = None
        self.commands = [
            "quit",
            "clear",
            "help",
            "ls agents",
            "ls tasks",
            "view process",
        ]
        self.show_command_selector = False
        self.current_view = (
            "agents"  # "process" or "agents" or "tasks", default to agents view
        )
        self.selected_agent_name: Optional[str] = None  # Currently selected agent name
        self.events: list[AgentEvent] = []  # Store all events in memory
        self.default_placeholder = "/command or input..."  # Default placeholder
        self.workdir: Optional[Path] = Path(workdir) if workdir else None
        if self.workdir:
            self.workdir.mkdir(parents=True, exist_ok=True)
        self.pending_ask_input_event: Optional[AgentEvent] = (
            None  # Pending ask_input event
        )
        self.tracer = tracer

    def compose(self) -> ComposeResult:
        """Compose application interface"""
        with Vertical():
            with Container(id="main-container"):
                process_view = ProcessView(id="process-view")
                process_view.add_class("hidden")
                yield process_view
                agents_view = AgentsListView(id="agents-view")
                yield agents_view
                tasks_view = TasksListView(id="tasks-view")
                tasks_view.add_class("hidden")
                yield tasks_view
            command_selector = CommandSelector(id="command-selector")
            command_selector.add_class("hidden")
            yield command_selector
            with Container(id="input-container"):
                yield Label("Current Agent: Not selected", id="selected-agent-label")
                yield Input(placeholder=self.default_placeholder, id="input-box")

    def on_mount(self) -> None:
        """Initialize on app mount"""
        self.process_view = self.query_one("#process-view", ProcessView)
        self.agents_view = self.query_one("#agents-view", AgentsListView)
        self.tasks_view = self.query_one("#tasks-view", TasksListView)
        self.command_selector = self.query_one("#command-selector", CommandSelector)
        self.input_box = self.query_one("#input-box", Input)
        self.selected_agent_label = self.query_one("#selected-agent-label", Label)

        # Set callbacks
        self.agents_view.set_selection_callback(self._on_agent_selected)
        self.tasks_view.set_selection_callback(self._on_task_selected)

        # Initialize agents list (default to agents view)
        agents = self.orchestrator.list_agents()
        self.agents_view.update_agents(agents)

        # Select first agent by default
        if agents:
            first_agent = agents[0]
            if first_agent.name:
                self._on_agent_selected(first_agent.name)
                # Select first item in list
                self.agents_view.list_view.index = 0

        # Focus input box
        self._focus_input()

    @on(Input.Changed, "#input-box")
    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input changes"""
        value = event.value
        if value == "/":
            # Show all commands
            self.show_command_selector = True
            self.command_selector.update_commands(self.commands)
            self.command_selector.remove_class("hidden")
            # Keep input focus, user can continue typing to filter
        elif value.startswith("/"):
            # Filter matching commands
            query = value[1:].lower()
            matched = [cmd for cmd in self.commands if cmd.startswith(query)]
            if matched:
                self.show_command_selector = True
                self.command_selector.update_commands(matched)
                self.command_selector.remove_class("hidden")
            else:
                # No matching commands, hide selector
                self.show_command_selector = False
                self.command_selector.add_class("hidden")
        else:
            # Hide command selector
            self.show_command_selector = False
            self.command_selector.add_class("hidden")

    @on(ListView.Selected, "#command-list")
    def on_command_selected(self, event: ListView.Selected) -> None:
        """Handle command selection"""
        if hasattr(event, "item") and isinstance(event.item, CommandItem):
            command = event.item.command
            self._handle_command(command)
            self.input_box.value = ""
            self.command_selector.add_class("hidden")
            self.show_command_selector = False
            self._focus_input()

    def _focus_input(self) -> None:
        """Focus input box and update placeholder"""
        self.set_focus(self.input_box)
        if self.input_box:
            self.input_box.placeholder = self.default_placeholder

    def _update_placeholder_by_focus(self) -> None:
        """Update placeholder based on focus state"""
        if not self.input_box:
            return
        focused = self.screen.focused
        if focused == self.input_box:
            self.input_box.placeholder = self.default_placeholder
        else:
            self.input_box.placeholder = "ESC to return to input box"

    @on(Key)
    def on_key(self, event: Key) -> None:
        """Handle keyboard events"""
        # Global ESC handling: if focus is not on input box, press ESC to return to input
        if event.key == "escape":
            focused = self.screen.focused
            if focused != self.input_box:
                self._focus_input()
                event.prevent_default()
                return

        # If command selector is shown
        if self.show_command_selector and not self.command_selector.has_class("hidden"):
            focused = self.screen.focused

            # If focus is on input box, transfer to command list on up/down keys
            if focused == self.input_box:
                if event.key == "up" or event.key == "down":
                    # Transfer focus to command list
                    self.set_focus(self.command_selector.command_list_view)
                    self._update_placeholder_by_focus()
                    event.prevent_default()
                    return

            # If focus is on command list
            elif focused == self.command_selector.command_list_view:
                # Press enter in command list to execute selected command
                if event.key == "enter":
                    selected = self.command_selector.get_selected_command()
                    if selected:
                        self._handle_command(selected)
                        self.input_box.value = ""
                        self.command_selector.add_class("hidden")
                        self.show_command_selector = False
                        self._focus_input()
                    event.prevent_default()
                    return
                # Press Esc to return to input box
                elif event.key == "escape":
                    self.command_selector.add_class("hidden")
                    self.show_command_selector = False
                    self._focus_input()
                    event.prevent_default()
                    return

    @on(Input.Submitted, "#input-box")
    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submission"""
        value = event.value.strip()
        if not value:
            return

        # Check if there's a pending ask_input event
        if self.pending_ask_input_event:
            # Send user input as tool_call result
            self._send_ask_input_result(value)
            self.input_box.value = ""
            self.pending_ask_input_event = None
            # Restore default placeholder
            if self.input_box:
                self.input_box.placeholder = self.default_placeholder
            return

        # Handle commands
        if value.startswith("/"):
            # If command selector is shown, use selected command
            if self.show_command_selector and not self.command_selector.has_class(
                "hidden"
            ):
                selected = self.command_selector.get_selected_command()
                if selected:
                    command = selected
                else:
                    command = value[1:].lower()
            else:
                command = value[1:].lower()

            self._handle_command(command)
            self.input_box.value = ""
            self.command_selector.add_class("hidden")
            self.show_command_selector = False
            return

        # Execute user instruction
        self._run_agent(value)
        self.input_box.value = ""
        return

    def _handle_command(self, command: str) -> None:
        """Handle command"""
        if command == "quit" or command == "q":
            self.exit()
        elif command == "clear":
            self.events.clear()
            self.process_view.clear_events()
        elif command == "help":
            # Show help information
            help_text = "Available commands:\n"
            for cmd in self.commands:
                help_text += f"  /{cmd}\n"
            self.notify(help_text, title="Help", timeout=5)
        elif command == "ls agents" or command == "ls":
            # Switch to agents view
            self._switch_view("agents")
        elif command == "ls tasks":
            # Switch to tasks view
            self._switch_view("tasks")
        elif command == "view process" or command == "process":
            # Switch to process view
            self._switch_view("process")
        else:
            # Try fuzzy match
            if "quit" in command or "q" in command:
                self.exit()
            elif "clear" in command:
                self.events.clear()
                self.process_view.clear_events()
            elif "help" in command:
                help_text = "Available commands:\n"
                for cmd in self.commands:
                    help_text += f"  /{cmd}\n"
                self.notify(help_text, title="Help", timeout=5)
            elif "ls" in command and "agent" in command:
                self._switch_view("agents")
            elif "ls" in command and "task" in command:
                self._switch_view("tasks")
            elif ("view" in command and "process" in command) or command == "process":
                self._switch_view("process")

    def _switch_view(self, view_name: str) -> None:
        """Switch view"""
        self.current_view = view_name
        if view_name == "agents":
            # Show agents view
            self.process_view.add_class("hidden")
            self.tasks_view.add_class("hidden")
            self.agents_view.remove_class("hidden")
            # Update agents list
            agents = self.orchestrator.list_agents()
            self.agents_view.update_agents(agents)
        elif view_name == "tasks":
            # Show tasks view
            self.process_view.add_class("hidden")
            self.agents_view.add_class("hidden")
            self.tasks_view.remove_class("hidden")
            # Update tasks list
            self._load_tasks()
            # Auto focus to task list
            self.set_focus(self.tasks_view.list_view)
            self._update_placeholder_by_focus()
        else:
            # Show process view
            self.process_view.remove_class("hidden")
            self.agents_view.add_class("hidden")
            self.tasks_view.add_class("hidden")

    def _on_agent_selected(self, agent_name: str) -> None:
        """Handle Agent selection"""
        self.selected_agent_name = agent_name
        if self.selected_agent_label:
            self.selected_agent_label.update(f"Current Agent: {agent_name}")

    def _send_ask_input_result(self, user_input: str) -> None:
        """Send ask_input result"""
        if not self.pending_ask_input_event or not self.orchestrator:
            return

        ask_input_event = self.pending_ask_input_event

        # Get tool_call_id from ask_input_event
        tool_call_id = None
        if ask_input_event.client_tool_call:
            tool_call_id = ask_input_event.client_tool_call.tool_call_id

        # Create AgentResponse as tool_call result
        # role should be "tool" instead of "user", because this is the result of a tool call
        result_response = AgentResponse(
            agent_name=ask_input_event.agent_name,
            message=ChatMessage(
                role="tool", content=user_input, tool_call_id=tool_call_id
            ),
            status=AgentRunningStatus.FINISHED,
        )

        # Create CLIENT_TOOL_RESULT event
        result_event = AgentEvent(
            task_id=ask_input_event.task_id,
            parent_task_id=ask_input_event.parent_task_id,
            root_task_id=ask_input_event.root_task_id,
            type=AgentEventType.CLIENT_TOOL_RESULT,
            client_tool_result=result_response,
        )

        # Send event through orchestrator
        try:
            # Use send_event method to send event
            asyncio.create_task(self.orchestrator.send_event(result_event))

            # Save to memory and view
            self.events.append(result_event)
            self.process_view.add_event(result_event)

            # Save to file
            if ask_input_event.root_task_id and self.workdir:
                self._save_event(ask_input_event.root_task_id, result_event)
        except Exception as e:
            logger.error("Failed to send ask_input result: %s", e)
            self.notify(f"Failed to send ask_input result: {e}", title="Error", timeout=3)

    def _on_task_selected(self, task_id: str) -> None:
        """Handle Task selection"""
        # Switch to process view
        self._switch_view("process")
        # Load all events for this task
        self._load_task_events(task_id)

    def _load_tasks(self) -> None:
        """Load all tasks"""
        if not self.workdir:
            return

        tasks = []
        # Find all {task_id}_request.json files
        for request_file in self.workdir.glob("*_request.json"):
            task_id = request_file.stem.replace("_request", "")
            try:
                with open(request_file, "r", encoding="utf-8") as f:
                    request_data = json.load(f)
                # Get file modification time
                mtime = request_file.stat().st_mtime
                tasks.append((task_id, request_data, mtime))
            except Exception as e:
                logger.error(f"Failed to load task {task_id}: {e}")

        # Sort by file modification time (newest first)
        tasks.sort(key=lambda x: x[2], reverse=True)
        # Remove mtime, keep only (task_id, request_data)
        tasks = [(task_id, request_data) for task_id, request_data, _ in tasks]
        self.tasks_view.update_tasks(tasks)

    def _load_task_events(self, task_id: str) -> None:
        """Load all events for a task from file"""
        if not self.workdir:
            return

        jsonl_file = self.workdir / f"{task_id}.jsonl"
        if not jsonl_file.exists():
            self.notify(f"Event file not found for task {task_id}", title="Error", timeout=3)
            return

        # Clear current events
        self.events.clear()
        self.process_view.clear_events()

        # Load events from jsonl file
        try:
            with open(jsonl_file, "r", encoding="utf-8") as f:
                for line in f:
                    strip_line = line.strip()
                    if not strip_line:
                        continue
                    try:
                        event_data = json.loads(strip_line)
                        event = AgentEvent(**event_data)
                        self.events.append(event)
                        self.process_view.add_event(event)
                    except Exception as e:
                        logger.error(f"Failed to parse event: {e}")
        except Exception as e:
            logger.error(f"Failed to load task events: {e}")
            self.notify(f"Failed to load task events: {e}", title="Error", timeout=3)

    def _save_request(self, root_task_id: str, request: AgentRequest) -> None:
        """Save request to file"""
        if not self.workdir:
            return

        request_file = self.workdir / f"{root_task_id}_request.json"
        try:
            request_data = request.model_dump()
            with open(request_file, "w", encoding="utf-8") as f:
                json.dump(request_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save request: {e}")

    def _save_event(self, root_task_id: str, event: AgentEvent) -> None:
        """Save event to jsonl file"""
        if not self.workdir:
            return

        jsonl_file = self.workdir / f"{root_task_id}.jsonl"
        try:
            event_data = event.model_dump()
            with open(jsonl_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(event_data, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"Failed to save event: {e}")

    @work(exclusive=True)
    async def _run_agent(self, user_input: str) -> None:
        """Run Agent"""
        if not self.orchestrator:
            return

        # Check if agent is selected
        if not self.selected_agent_name:
            self.notify("Please select an Agent first (use /ls agents)", title="Error", timeout=3)
            return

        # Switch to process view to show execution
        self._switch_view("process")

        # Clear previous events
        self.events.clear()
        self.process_view.clear_events()

        messages = [ChatMessage(role="user", content=user_input)]
        request = AgentRequest(
            agent_name=self.selected_agent_name,
            messages=messages,
        )
        event = AgentEvent(
            type=AgentEventType.REQUEST,
            request=request,
        )

        # Get root_task_id (from the first event)
        root_task_id = None
        ctx = SpanContext(tracer=self.tracer, app_name=self.selected_agent_name)
        with ctx.span(name=f"{self.selected_agent_name}_run_agent"):
            try:
                async for agent_event in self.orchestrator.run(
                    agent_name=self.selected_agent_name,
                    event=event,
                    agent_config=None,
                ):
                    # Get root_task_id (from the first event)
                    if root_task_id is None:
                        root_task_id = agent_event.root_task_id or agent_event.task_id
                        # Save request to file
                        if root_task_id and self.workdir:
                            self._save_request(root_task_id, request)

                    # Check if it's ask_input type client_tool_call
                    if (
                        agent_event.client_tool_call
                        and getattr(agent_event.client_tool_call, "type", None)
                        == ClientToolCallType.ASK_INPUT
                    ):
                        # Save as pending ask_input event
                        self.pending_ask_input_event = agent_event
                        # Update placeholder to prompt user input
                        if self.input_box:
                            self.input_box.placeholder = (
                                "Please enter content (as ask_input response)..."
                            )

                    # Save to memory
                    self.events.append(agent_event)
                    # Add to view
                    self.process_view.add_event(agent_event)

                    # Save to file
                    if root_task_id and self.workdir:
                        self._save_event(root_task_id, agent_event)

                # After execution completes, add completion event
                completion_event = AgentEvent(
                    type=AgentEventType.SIGNAL,
                    agent_name=self.selected_agent_name,
                    metadata={"status": "completed", "message": "Execution completed"},
                )
                self.events.append(completion_event)
                self.process_view.add_event(completion_event)

                # Save completion event to file
                if root_task_id and self.workdir:
                    self._save_event(root_task_id, completion_event)
            except Exception as e:
                logger.error("Error running Agent: %s", e, exc_info=True)
                error_event = AgentEvent(
                    type=AgentEventType.ERROR,
                    error=str(e),
                )
                # Save to memory
                self.events.append(error_event)
                # Add to view
                self.process_view.add_event(error_event)

    async def action_quit(self) -> None:
        """Quit application"""
        self.exit()
