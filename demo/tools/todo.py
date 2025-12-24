"""
Todo Tool - Agent Task and Plan Management

Minimalist design: read, write, and update operations through a single interface.
- Empty dict: Read all tasks
- Complete dict: Rewrite all tasks
- Partial dict: Incremental update tasks
- value is None: Delete task

Data structure:
{
    step_id: {
        "task": "Task description",
        "status": "pending|in_progress|completed|blocked",
        "priority": "low|medium|high|critical",
        "details": "Additional notes",
        "dependencies": [dependent step IDs],
        "tags": ["tag list"],
        ...any custom fields
    }
}
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from loguru import logger
from pydantic import ConfigDict
from typing_extensions import NotRequired, TypedDict

from cortex.model.definition import ContentBlockType
from demo.tools.utils import json_dumps
from cortex.tools.function_tool import FunctionTool

# Todo data file path template (local /tmp directory)
TODO_DIR = Path("/tmp/todo_tool")
TODO_FILE_TEMPLATE = str(TODO_DIR / ".agent_todo_{}.json")

# Status icon mapping
STATUS_ICONS: dict[str, str] = {
    "pending": "⏳",
    "in_progress": "🔄",
    "completed": "✅",
    "blocked": "🚫",
}

# Priority icon mapping
PRIORITY_ICONS: dict[str, str] = {
    "low": "🔵",
    "medium": "🟡",
    "high": "🟠",
    "critical": "🔴",
}

# Special fields set (displayed first)
SPECIAL_FIELDS: frozenset[str] = frozenset({
    # Main description fields
    "task", "title", "name", "description", "summary",
    # Status fields
    "status", "state", "progress", "phase",
    # Priority fields
    "priority", "level", "importance", "urgency",
    # Details fields
    "details", "notes", "comments", "remarks",
    # Relationship fields
    "dependencies", "depends_on", "blocks", "parent", "children",
    # Tag fields
    "tags", "labels", "categories", "type",
})

# Timestamp fields
TIMESTAMP_FIELDS: frozenset[str] = frozenset({
    "created_at", "updated_at", "modified_at", "completed_at"
})


def _ensure_todo_dir():
    """Ensure todo directory exists."""
    TODO_DIR.mkdir(parents=True, exist_ok=True)


# Define Todo item type structure
class TodoItemHint(TypedDict):
    """Todo item type definition, provides clear schema example for MCP tool, for reference only."""

    __pydantic_config__ = ConfigDict(
extra="allow")  # type: ignore Standard implementation per https://docs.pydantic.dev/2.3/usage/types/dicts_mapping/

    task: str  # Required: task description
    status: NotRequired[
        Literal["pending", "in_progress", "completed", "blocked"]
    ]  # Task status
    priority: NotRequired[Literal["low", "medium", "high", "critical"]]  # Priority
    details: NotRequired[str]  # Detailed notes or remarks
    dependencies: NotRequired[list[str]]  # IDs of dependent steps
    tags: NotRequired[list[str]]  # Tag list
    # Note: Other custom fields can also be included in actual use


# 类型定义
TodoItemDict = dict[str, Any]
UPDATE_TYPE = dict[str, TodoItemDict | None]
UPDATE_HINT_TYPE = dict[str, TodoItemHint | TodoItemDict | None]


@dataclass
class TodoItem:
    """Single Todo item."""

    step_id: str
    data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Automatically manage metadata."""
        self.data["step"] = self.step_id
        now = datetime.now().isoformat(timespec="seconds")
        self.data.setdefault("created_at", now)
        self.data.setdefault("updated_at", now)
        self.data.setdefault("status", "pending")
        self.data.setdefault("priority", "medium")

    def update(self, updates: dict[str, Any]) -> None:
        """Update content."""
        self.data.update(updates)
        self.data["updated_at"] = datetime.now().isoformat(timespec="seconds")
        self.data["step"] = self.step_id  # Keep step consistent


@dataclass
class TodoCollection:
    """Todo collection."""

    items: dict[str, TodoItem] = field(default_factory=dict)

    def merge_updates(self, updates: UPDATE_TYPE) -> None:
        """Merge updates."""
        for step_id, step_updates in updates.items():
            if step_updates is None:
                self.items.pop(step_id, None)
            elif step_id in self.items:
                self.items[step_id].update(step_updates)
            else:
                self.items[step_id] = TodoItem(step_id, dict(step_updates))

    def to_dict(self) -> dict[str, dict[str, Any]]:
        """Convert to dictionary format."""
        return {k: v.data for k, v in self.items.items()}

    @classmethod
    def from_dict(cls, data: dict[str, dict[str, Any]]) -> "TodoCollection":
        """Create from dictionary."""
        collection = cls()
        for step_id, todo_data in data.items():
            collection.items[step_id] = TodoItem(step_id, todo_data)
        return collection


def format_todo_result(todos: TodoCollection) -> tuple[str, dict[str, Any]]:
    """Format todo output."""
    todos_dict = todos.to_dict()

    # Single pass to calculate statistics
    stats: dict[str, int] = {"total": len(todos.items), "pending": 0, "in_progress": 0, "completed": 0, "blocked": 0}
    for item in todos.items.values():
        status = item.data.get("status", "pending")
        if status in stats:
            stats[status] += 1

    # Build formatted text
    lines = ["<todo_result>"]

    # Show summary (compatible with tests)
    lines.append(f"📊 Total: {stats['total']} tasks")

    # If there are status statistics, show details
    status_parts = [
        f"{STATUS_ICONS[s]} {stats[s]}"
        for s in ("completed", "in_progress", "pending", "blocked")
        if stats[s] > 0
    ]
    if status_parts:
        lines.append(f"Status: {' | '.join(status_parts)}")

    lines.append("=" * 60)

    # Format each task
    for step_id, item in todos.items.items():
        todo = item.data
        # Get status and priority icons
        status = todo.get("status", "pending")
        priority = todo.get("priority", "medium")
        status_icon = STATUS_ICONS.get(status, "📌")
        priority_icon = PRIORITY_ICONS.get(priority, "")

        # Show step title
        task_title = todo.get("task") or todo.get("title") or todo.get("name") or f"Step {step_id}"
        lines.append(f"\n{status_icon} Step {step_id}: {task_title} {priority_icon}".strip())

        # Fields already shown in title
        displayed_fields: set[str] = {"task", "title", "name", "status", "priority"}

        # 1. Show special fields first (maintain insertion order)
        for f, value in todo.items():
            if f not in SPECIAL_FIELDS or f in displayed_fields:
                continue
            displayed_fields.add(f)
            _append_field_line(lines, f, value)

        # 2. Show timestamp fields
        for f in TIMESTAMP_FIELDS:
            if f in todo and f not in displayed_fields:
                lines.append(f"  {f}: {todo[f]}")
                displayed_fields.add(f)

        # 3. Remaining fields as JSON
        displayed_fields.add("step")  # step field doesn't need to be shown again
        other_fields = {k: v for k, v in todo.items() if k not in displayed_fields}

        if other_fields:
            lines.append("  --- other fields ---")
            json_str = json_dumps(other_fields, ensure_ascii=False, indent=4)
            # Add indentation
            indented = "\n".join(f"  {line}" for line in json_str.split("\n"))
            lines.append(indented)

    lines.append("</todo_result>")

    # Build structured data to return
    return "\n".join(lines), {"todos": todos_dict, "stats": stats}


def _append_field_line(lines: list[str], field_name: str, value: Any) -> None:
    """Format and append field line."""
    if field_name == "details":
        lines.append(f"  📝 {value}")
    elif field_name == "dependencies":
        if isinstance(value, list) and value:
            deps_str = ", ".join(str(d) for d in value)
            lines.append(f"  🔗 Depends on: [{deps_str}]")
    elif field_name == "tags":
        if isinstance(value, list) and value:
            tags_str = ", ".join(f"#{tag}" for tag in value)
            lines.append(f"  🏷️  {tags_str}")
    elif isinstance(value, (str, int, float, bool)):
        lines.append(f"  {field_name}: {value}")
    else:
        # Complex types use JSON
        json_compact = json.dumps(value, ensure_ascii=False)
        if len(json_compact) > 80:
            json_str = json.dumps(value, ensure_ascii=False, indent=2)
            lines.append(f"  {field_name}: {json_str}")
        else:
            lines.append(f"  {field_name}: {json_compact}")


def seems_like_complete_rewrite(updates: UPDATE_TYPE, current: dict[str, Any]) -> bool:
    """Determine if this is a complete rewrite."""
    if not current:
        return True

    non_null = {k: v for k, v in updates.items() if v is not None}
    new_keys = set(non_null.keys()) - set(current.keys())
    return len(new_keys) > len(current) * 0.8 and not (
            set(non_null.keys()) & set(current.keys())
    )


def create_todo_tool(context_id: str = "default"):
    """Create todo tool.
    
    Args:
        context_id: Context ID for isolating todo files between different sessions, defaults to "default".
        
    Returns:
        FunctionTool: todo tool instance.
    """
    # Ensure directory exists
    _ensure_todo_dir()
    
    # Use context_id as session_id
    todo_file_path = TODO_FILE_TEMPLATE.format(context_id)

    def load_todos() -> dict[str, dict[str, Any]]:
        """Load todo data from local file system."""
        try:
            with open(todo_file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            logger.debug(f"Todo file {todo_file_path} does not exist, returning empty dict")
        except Exception as e:
            logger.debug(f"Failed to read todo file (possibly first use): {e}")
        return {}

    def save_todos(todos: dict[str, dict[str, Any]]) -> None:
        """Save todo data to local file system."""
        try:
            _ensure_todo_dir()
            with open(todo_file_path, "w", encoding="utf-8") as f:
                json.dump(todos, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save todo file: {e}")
            raise

    async def todo(
            updates: Annotated[
                dict,
                "Todo updates indexed by step ID.\n"
                "Todo 任务管理的统一接口，支持读取、创建、更新和删除操作。\n\n"
                "📖 操作模式：\n"
                "• 空字典 {} - 读取所有任务\n"
                "• 完整字典 - 完全重写任务列表（删除旧的，创建新的）\n"
                "• 部分字典 - 增量更新（只修改指定的任务）\n"
                "• 值为 None - 删除指定任务\n\n"
                "🔑 Step ID 说明：\n"
                "• 可以是任意字符串，用作任务的唯一标识\n"
                "• 推荐使用数字字符串（'1', '2', '3'...）以便自动排序\n"
                "• 也可使用描述性 ID（'setup', 'test', 'deploy'）\n\n"
                "📝 任务字段：\n"
                "• task: str (必需) - 任务描述\n"
                "• status: 'pending'|'in_progress'|'completed'|'blocked' - 任务状态\n"
                "• priority: 'low'|'medium'|'high'|'critical' - 优先级\n"
                "• details: str - 详细说明或备注\n"
                "• dependencies: list[str] - 依赖的其他步骤 ID\n"
                "• tags: list[str] - 标签列表\n"
                "• 支持任意自定义字段\n\n"
                "💡 使用示例：\n"
                "1. 读取所有任务: {}\n"
                "2. 创建新任务列表: {'1': {'task': '分析需求', 'status': 'pending'}, '2': {'task': '编写代码'}}\n"
                "3. 更新特定任务: {'2': {'status': 'in_progress', 'details': '开始实现'}}\n"
                "4. 删除任务: {'3': None}\n"
                "5. 复杂示例: {'1': {'task': '设计架构', 'status': 'completed', 'priority': 'high', "
                "'tags': ['backend', 'design']}, '2': {'task': '实现功能', 'dependencies': ['1']}}"
            ] = None,
    ):
        """Task and plan management tool for maintaining structured todo lists with step tracking.

        任务和计划管理工具，用于维护结构化的待办事项列表，支持步骤跟踪、状态管理、优先级设置和依赖关系。
        通过单一接口实现 CRUD 操作，自动处理时间戳和数据验证。
        """

        # Use empty dict if updates is None
        updates_dict: UPDATE_TYPE = updates if updates else {}

        # Load current todo from local (dictionary format)
        current_todos_dict = load_todos()

        # Convert to TodoCollection
        current_collection = TodoCollection.from_dict(current_todos_dict)

        # Decide operation based on updates_dict
        if not updates_dict:
            # Empty dict = read only
            result_collection = current_collection
            operation = "read"
        elif seems_like_complete_rewrite(updates_dict, current_todos_dict):
            # Complete rewrite
            result_collection = TodoCollection()
            result_collection.merge_updates(updates_dict)
            operation = "rewrite"
        else:
            # Incremental update
            result_collection = TodoCollection.from_dict(current_todos_dict)
            result_collection.merge_updates(updates_dict)
            operation = "update"

        # Save to local (only save when there are updates)
        if operation != "read":
            # Convert back to dictionary format for saving
            save_todos(result_collection.to_dict())

        # Format result
        formatted_text, structured_data = format_todo_result(result_collection)

        # Add operation info to structured data
        structured_data["operation"] = operation
        result = [
            {
                "type": ContentBlockType.TOOLRESULT.value,
                "content": [
                    {
                        "type": ContentBlockType.TEXT.value,
                        ContentBlockType.TEXT.value: formatted_text,
                    }
                ]
            }
        ]
        return result

    function_tool = FunctionTool(
        name="todo",
        func=todo,
        description="Task and plan management tool for maintaining structured todo lists with step tracking. 任务和计划管理工具，用于维护结构化的待办事项列表，支持步骤跟踪、状态管理、优先级设置和依赖关系。通过单一接口实现 CRUD 操作，自动处理时间戳和数据验证。",
    )

    logger.info("todo tool registered successfully")
    return function_tool
