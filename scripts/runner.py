"""
Utility script for running DeepResearchAgent on ad-hoc tasks or task lists.

Usage examples:
    # Run a single ad-hoc prompt
    python -m eval.runner --task "列出最近的 AI 安全新闻"

    # Run multiple tasks defined in a JSON file
    python -m eval.runner --tasks-file eval/tasks.example.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import megfile
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

from cortex.agents.agent_factory import AgentFactory
from cortex.agents.types import AgentConfig, AgentMessageType, AgentRunningStatus
from cortex.model.definition import ChatMessage, ChatToolCall
from cortex.orchestrator.orchestrator import Orchestrator, OrchMode
from cortex.orchestrator.types import AgentEvent, AgentEventType, AgentRequest
from demo.dr_agent.dr_agent import get_dr_agent_config, make_dr_agent
from scripts.configs.prompt import SYSTEM_PROMPT

logger = logging.getLogger(__name__)


@dataclass
class EvalTask:
    """Simple container describing a single evaluation task."""

    id: str
    prompt: str


SLUG_REGEX = re.compile(r"[^a-zA-Z0-9_-]+")


def slugify(value: str | None, fallback_prefix: str = "task") -> str:
    """Generate a filesystem-friendly identifier."""
    if not value:
        return f"{fallback_prefix}_{uuid.uuid4().hex[:8]}"
    value = value.strip()
    if not value:
        return f"{fallback_prefix}_{uuid.uuid4().hex[:8]}"
    slug = SLUG_REGEX.sub("_", value).strip("_")
    return slug or f"{fallback_prefix}_{uuid.uuid4().hex[:8]}"


def _truncate(text: str, limit: int | None = 600) -> str:
    if limit is None:
        return text
    if len(text) <= limit:
        return text
    return f"{text[:limit]}... (truncated, {len(text)} chars)"


def _stringify_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                text_value = block.get("text") or block.get("content")
                if isinstance(text_value, str):
                    parts.append(text_value)
                    continue

                data_value = block.get("data")
                if isinstance(data_value, dict):
                    nested_text = data_value.get("text") or data_value.get("content")
                    if isinstance(nested_text, str):
                        parts.append(nested_text)
                        continue
                    nested_thinking = data_value.get("thinking")
                    if isinstance(nested_thinking, str):
                        continue
            else:
                parts.append(str(block))
        return "\n".join(parts) if parts else json.dumps(content, ensure_ascii=False)
    return json.dumps(content, ensure_ascii=False)


def _format_content_blocks(
    content: Any, max_block_chars: int | None = 800
) -> Any:
    if content is None:
        return None
    if isinstance(content, str):
        return _truncate(content, max_block_chars)
    if isinstance(content, list):
        formatted: list[dict[str, Any]] = []
        for block in content:
            if isinstance(block, dict):
                entry: dict[str, Any] = {}
                if "type" in block:
                    entry["type"] = block["type"]
                text_value = block.get("text") or block.get("content")
                if isinstance(text_value, str):
                    entry["text"] = (
                        text_value if max_block_chars is None else _truncate(text_value, max_block_chars)
                    )
                elif text_value is not None:
                    entry["data"] = text_value
                else:
                    entry["data"] = block
                formatted.append(entry)
            else:
                formatted.append({"data": block})
        return formatted
    return content


def _format_tool_calls(tool_calls: list[ChatToolCall] | None) -> list[dict[str, Any]] | None:
    if not tool_calls:
        return None
    formatted: list[dict[str, Any]] = []
    for tc in tool_calls:
        formatted.append(
            {
                "id": tc.id,
                "name": tc.function.name,
                "arguments": tc.function.arguments,
            }
        )
    return formatted


def _extract_answer_text(content: Any) -> str | None:
    """Extract only the <answer>...</answer> segment or strip <think> blocks."""
    text = _stringify_content(content)
    if not text:
        return None
    answer_match = re.search(r"<answer>(.*?)</answer>", text, flags=re.DOTALL | re.IGNORECASE)
    if answer_match:
        return answer_match.group(1).strip()
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE).strip()
    return cleaned or text


def _format_message(
    message: ChatMessage | None, max_block_chars: int | None = 800
) -> dict[str, Any] | None:
    if message is None:
        return None
    data: dict[str, Any] = {}
    if message.role:
        data["role"] = message.role
    content = _format_content_blocks(message.content, max_block_chars=max_block_chars)
    if content is not None:
        data["content"] = content
    if message.tool_call_id:
        data["tool_call_id"] = message.tool_call_id
    tool_calls = _format_tool_calls(message.tool_calls)
    if tool_calls:
        data["tool_calls"] = tool_calls
    if message.extra_info:
        data["extra_info"] = message.extra_info
    return data


def _format_event(event: AgentEvent, index: int, max_block_chars: int | None = 800) -> dict[str, Any]:
    formatted: dict[str, Any] = {
        "index": index,
        "event_type": event.type.value,
    }
    if event.agent_name:
        formatted["agent"] = event.agent_name
    if event.metadata:
        formatted["metadata"] = event.metadata

    if event.type == AgentEventType.RESPONSE and event.response:
        response = event.response
        formatted["status"] = response.status.value
        formatted["message_type"] = response.message_type.value
        if response.metadata:
            formatted["step_metadata"] = response.metadata
        if response.error_msg is not None:
            formatted["error"] = response.error_msg
        message = _format_message(response.message, max_block_chars=max_block_chars)
        if message:
            formatted["message"] = message
    elif event.type == AgentEventType.CLIENT_TOOL_CALL and event.client_tool_call:
        call = event.client_tool_call
        formatted["tool_call"] = {
            "tool_call_id": call.tool_call_id,
            "type": call.type.value,
            "function": {
                "name": call.function.name,
                "arguments": call.function.arguments,
            },
            "extra": call.extra,
        }
    elif event.type == AgentEventType.CLIENT_TOOL_RESULT and event.client_tool_result:
        formatted["tool_result"] = {
            "status": event.client_tool_result.status.value,
            "message": _format_message(
                event.client_tool_result.message, max_block_chars=max_block_chars
            ),
        }
    elif event.type == AgentEventType.ERROR and event.error:
        formatted["error"] = event.error
    return formatted


def load_tasks_from_file(path: Path) -> list[EvalTask]:
    """Load tasks from a JSON file.

    Supported formats:
      1. List of strings: ["task 1", "task 2"]
      2. List of objects with "prompt"/"task" keys (and optional "id")
      3. Object with a "tasks" field following format 1 or 2
    """
    with path.open("r", encoding="utf-8") as f:
        raw_payload = json.load(f)

    if isinstance(raw_payload, dict) and "tasks" in raw_payload:
        payload = raw_payload["tasks"]
    else:
        payload = raw_payload

    if not isinstance(payload, list):
        raise ValueError(
            f"Unsupported tasks file structure in {path}. "
            "Expected a list or an object with a 'tasks' field."
        )

    tasks: list[EvalTask] = []
    for idx, entry in enumerate(payload, start=1):
        if isinstance(entry, str):
            tasks.append(EvalTask(id=f"task_{idx}", prompt=entry))
            continue
        if isinstance(entry, dict):
            prompt = (
                entry.get("prompt")
                or entry.get("task")
                or entry.get("request")
                or entry.get("input")
            )
            if not isinstance(prompt, str):
                raise ValueError(
                    f"Task entry #{idx} missing 'prompt' content in {path}"
                )
            task_id = entry.get("id") or entry.get("name") or f"task_{idx}"
            tasks.append(EvalTask(id=str(task_id), prompt=prompt))
            continue
        raise ValueError(f"Unsupported task entry at index {idx}: {entry!r}")
    return tasks


def merge_tasks(
    single_task: str | None,
    single_task_id: str | None,
    tasks_file: Path | None,
) -> list[EvalTask]:
    """Combine inline task and file-based tasks into a unified list."""
    tasks: list[EvalTask] = []
    if single_task:
        tasks.append(
            EvalTask(
                id=single_task_id or slugify(single_task),
                prompt=single_task,
            )
        )
    if tasks_file:
        tasks.extend(load_tasks_from_file(tasks_file))

    if not tasks:
        raise ValueError("No tasks provided. Use --task or --tasks-file.")

    # Normalize IDs to be filesystem-safe and unique
    seen: dict[str, int] = {}
    for task in tasks:
        safe_id = slugify(task.id)
        counter = seen.get(safe_id, 0)
        if counter > 0:
            safe_id = f"{safe_id}_{counter+1}"
        seen[safe_id] = counter + 1
        task.id = safe_id
    return tasks


def build_orchestrator(agent_name: str) -> Orchestrator:
    """Instantiate an Orchestrator with DeepResearchAgent registered."""
    agent_factory = AgentFactory()
    agent_factory.register_agent(
        name=agent_name,
        make_agent_func=make_dr_agent,
        default_config=get_dr_agent_config(),
    )
    return Orchestrator(agent_factory)


def build_agent_config(
    streaming: bool = True,
    request_timeout: float | None = None,
    context_upper_limit: int | None = None,
    context_lower_limit: int | None = None,
) -> AgentConfig:
    """Create an AgentConfig for running standalone tasks."""
    config = get_dr_agent_config()
    config = config.model_copy(deep=True)
    model_params = config.model.model_copy(deep=True)
    infer_kwargs = dict(model_params.infer_kwargs or {})
    infer_kwargs["stream"] = streaming
    if request_timeout is not None:
        infer_kwargs["request_timeout"] = request_timeout
    model_params.infer_kwargs = infer_kwargs
    config.model = model_params
    extra_cfg = dict(config.extra_config or {})
    if context_upper_limit is not None:
        extra_cfg["final_answer_context_upper_limit"] = int(context_upper_limit)
    if context_lower_limit is not None:
        extra_cfg["final_answer_context_lower_limit"] = int(context_lower_limit)
    config.extra_config = extra_cfg
    return config


async def run_single_task(
    orchestrator: Orchestrator,
    agent_name: str,
    task: EvalTask,
    mode: OrchMode = OrchMode.MULTI,
    agent_config: AgentConfig | None = None,
    max_block_chars: int | None = None,
) -> dict[str, Any]:
    """Run a single evaluation task and capture the full event trace."""
    current_date = datetime.now(tz=timezone.utc).date().isoformat()
    system_prompt = SYSTEM_PROMPT.replace("__CURRENT_DATE__", current_date)
    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=task.prompt),
    ]
    request = AgentRequest(agent_name=agent_name, messages=messages)
    entry_event = AgentEvent(
        type=AgentEventType.REQUEST,
        agent_name=agent_name,
        request=request,
    )

    formatted_events: list[dict[str, Any]] = []
    final_answer: str | None = None
    final_message: ChatMessage | None = None
    final_status = AgentRunningStatus.RUNNING.value
    error_message = None
    last_assistant_message: ChatMessage | None = None
    finished_assistant_message: ChatMessage | None = None
    saw_finished = False
    saw_stopped = False
    saw_error = False
    start_monotonic = time.perf_counter()
    started_at = datetime.now(tz=timezone.utc).isoformat()

    try:
        idx = 1
        async for event in orchestrator.run(
            agent_name=agent_name,
            event=entry_event,
            agent_config=agent_config,
            mode=mode,
            context_id=task.id,
        ):
            formatted_events.append(_format_event(event, idx, max_block_chars=max_block_chars))
            idx += 1
            if event.type == AgentEventType.ERROR and event.error:
                error_message = event.error
                saw_error = True
            if event.type == AgentEventType.RESPONSE and event.response:
                final_status = event.response.status.value
                if event.response.error_msg is not None:
                    error_message = event.response.error_msg
                if event.response.status == AgentRunningStatus.FINISHED:
                    saw_finished = True
                elif event.response.status == AgentRunningStatus.STOPPED:
                    saw_stopped = True
                elif event.response.status == AgentRunningStatus.ERROR:
                    saw_error = True

                message = event.response.message
                if message is not None and message.role == "assistant":
                    last_assistant_message = message
                    if event.response.status == AgentRunningStatus.FINISHED:
                        finished_assistant_message = message

                if (
                    event.response.message_type == AgentMessageType.FINAL
                    and event.response.message is not None
                    and event.response.message.role == "assistant"
                ):
                    final_message = event.response.message
                    final_answer = _extract_answer_text(event.response.message.content)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.exception("Task %s failed: %s", task.id, exc)
        error_message = str(exc)
        final_status = AgentRunningStatus.ERROR.value
        saw_error = True

    duration = time.perf_counter() - start_monotonic
    completed_at = datetime.now(tz=timezone.utc).isoformat()

    if saw_error:
        final_status = AgentRunningStatus.ERROR.value
    elif saw_stopped:
        final_status = AgentRunningStatus.STOPPED.value
    elif saw_finished:
        final_status = AgentRunningStatus.FINISHED.value

    if final_message is None:
        final_message = finished_assistant_message or last_assistant_message
        if final_message is not None:
            final_answer = _extract_answer_text(final_message.content)

    formatted_final_message = _format_message(final_message, max_block_chars=None)

    task_section = {
        "id": task.id,
        "prompt": task.prompt,
        "input_messages": [msg.model_dump() for msg in messages],
    }

    output_section = {
        "status": final_status,
        "final_answer": final_answer,
        "final_message": formatted_final_message,
        "error": error_message,
    }

    trace_section = {
        "event_count": len(formatted_events),
        "events": formatted_events,
    }

    metadata_section = {
        "mode": mode.value,
        "agent_name": agent_name,
        "started_at": started_at,
        "completed_at": completed_at,
        "duration_seconds": duration,
    }
    base_result = {
        "task_id": task.id,
        "prompt": task.prompt,
        "task": task_section,
        "output": output_section,
        "metadata": metadata_section,
        "trace": trace_section,
    }
    return base_result


def save_result(
    result: dict[str, Any], output_dir: str | Path, overwrite: bool = False
) -> str | Path:
    """Persist a task result to disk or s3."""
    task_id = result.get("task_id")
    if not task_id:
        raise ValueError("Result missing task_id; cannot name output file")

    output_dir_str = str(output_dir)
    is_s3 = megfile.is_s3(output_dir_str)
    filename = f"{task_id}.json"
    if is_s3:
        megfile.smart_makedirs(output_dir_str, exist_ok=True)
        base_path = output_dir_str.rstrip("/") + "/" + filename
        target_path = base_path
        if megfile.smart_exists(base_path) and not overwrite:
            timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d%H%M%S")
            target_path = output_dir_str.rstrip("/") + f"/{task_id}_{timestamp}.json"
            logger.warning(
                "File %s exists, writing to %s instead. Use --overwrite to override.",
                base_path,
                target_path,
            )
        with megfile.smart_open(target_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        return target_path

    output_dir_path = Path(output_dir_str)
    output_dir_path.mkdir(parents=True, exist_ok=True)
    base_path = output_dir_path / filename
    target_path = base_path
    if base_path.exists() and not overwrite:
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d%H%M%S")
        target_path = output_dir_path / f"{task_id}_{timestamp}.json"
        logger.warning(
            "File %s exists, writing to %s instead. Use --overwrite to override.",
            base_path,
            target_path,
        )
    with target_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return target_path


async def run_tasks(
    tasks: Sequence[EvalTask],
    agent_name: str,
    output_dir: Path,
    mode: OrchMode,
    overwrite: bool,
    streaming: bool,
    request_timeout: float | None = None,
    context_upper_limit: int | None = None,
    context_lower_limit: int | None = None,
) -> list[str | Path]:
    """Run all tasks sequentially and store per-task traces."""
    orchestrator = build_orchestrator(agent_name)
    written_files: list[str | Path] = []
    for idx, task in enumerate(tasks, start=1):
        logger.info("Running task %s/%s: %s", idx, len(tasks), task.id)
        agent_config = build_agent_config(
            streaming=streaming,
            request_timeout=request_timeout,
            context_upper_limit=context_upper_limit,
            context_lower_limit=context_lower_limit,
        )
        result = await run_single_task(
            orchestrator,
            agent_name,
            task,
            mode,
            agent_config=agent_config,
        )
        output_path = save_result(result, output_dir, overwrite=overwrite)
        written_files.append(output_path)
        logger.info(
            "Task %s finished with status %s → %s",
            task.id,
            result["output"]["status"],
            output_path,
        )
    return written_files


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run tasks and capture per-task traces.",
        argument_default=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--config",
        type=str,
        help="YAML config file with defaults for runner options.",
    )
    parser.add_argument(
        "--task",
        type=str,
        help="Single ad-hoc task prompt.",
    )
    parser.add_argument(
        "--task-id",
        type=str,
        help="Identifier for --task (defaults to slugified prompt).",
    )
    parser.add_argument(
        "--tasks-file",
        type=str,
        help="Path to a JSON file describing multiple tasks.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        help="Directory to store per-task JSON traces (default: eval/results).",
    )
    parser.add_argument(
        "--agent-name",
        type=str,
        help="Registered agent to run (default: DeepResearchAgent).",
    )
    parser.add_argument(
        "--mode",
        choices=[m.value for m in OrchMode],
        help="Orchestrator mode (default: multi).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow overwriting existing result files.",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        help="Logging level (default: INFO).",
    )
    parser.add_argument(
        "--no-stream",
        action="store_true",
        help="Disable streaming completions (may break tool calls for some models).",
    )
    parser.add_argument(
        "--request-timeout",
        type=float,
        help="Per-request timeout in seconds.",
    )
    parser.add_argument(
        "--context-upper-limit",
        type=int,
        help="Force-final-answer context upper token limit (overrides agent default).",
    )
    parser.add_argument(
        "--context-lower-limit",
        type=int,
        help="Force-final-answer context lower token limit (overrides agent default).",
    )
    return parser.parse_args()


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def load_config_file(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config file {config_path} must contain a mapping/object.")
    return data


def merge_with_config(
    cli_args: argparse.Namespace,
    defaults: Mapping[str, Any],
) -> tuple[dict[str, Any], Path | None]:
    args = vars(cli_args).copy()
    config_path_raw = args.pop("config", None)
    config_path = Path(config_path_raw) if config_path_raw else None
    config_data: dict[str, Any] = {}
    if config_path:
        config_data = load_config_file(config_path)

    merged = dict(defaults)
    for key, value in config_data.items():
        if key in defaults and value is not None:
            merged[key] = value

    for key, value in args.items():
        merged[key] = value

    return merged, config_path


def main() -> None:
    defaults = {
        "task": None,
        "task_id": None,
        "tasks_file": None,
        "output_dir": "scripts/results",
        "agent_name": "DeepResearchAgent",
        "mode": OrchMode.MULTI.value,
        "overwrite": False,
        "log_level": "INFO",
        "no_stream": False,
        "request_timeout": None,
        "context_upper_limit": None,
        "context_lower_limit": None,
    }
    cli_args = parse_args()
    options, config_path = merge_with_config(cli_args, defaults)

    tasks_file = options.get("tasks_file")
    if isinstance(tasks_file, str):
        tf_path = Path(tasks_file)
        if not tf_path.is_absolute():
            tasks_file = str((REPO_ROOT / tf_path).resolve())

    configure_logging(str(options.get("log_level", defaults["log_level"])))
    output_dir = Path(options.get("output_dir", defaults["output_dir"]))

    tasks = merge_tasks(
        single_task=options.get("task"),
        single_task_id=options.get("task_id"),
        tasks_file=Path(tasks_file) if tasks_file else None,
    )
    mode = OrchMode(options.get("mode", defaults["mode"]))
    logger.info(
        "Starting run: %s task(s), output → %s, mode=%s",
        len(tasks),
        output_dir,
        mode.value,
    )
    asyncio.run(
        run_tasks(
            tasks=tasks,
            agent_name=options.get("agent_name", defaults["agent_name"]),
            output_dir=output_dir,
            mode=mode,
            overwrite=bool(options.get("overwrite", False)),
            streaming=not bool(options.get("no_stream", False)),
            request_timeout=options.get("request_timeout"),
            context_upper_limit=options.get("context_upper_limit"),
            context_lower_limit=options.get("context_lower_limit"),
        )
    )


if __name__ == "__main__":
    main()
