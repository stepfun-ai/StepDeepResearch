"""File tool for local sandbox.

Provides read/write/append/list/stat operations with an action + path schema.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from loguru import logger

from cortex.model.definition import ContentBlockType
from cortex.tools.function_tool import FunctionTool

MAX_PREVIEW_BYTES = 12000
MAX_LIST_ENTRIES = 200


def _wrap_tool_result(text: str) -> list[dict]:
    return [
        {
            "type": ContentBlockType.TOOLRESULT.value,
            "content": [
                {
                    "type": ContentBlockType.TEXT.value,
                    ContentBlockType.TEXT.value: text,
                }
            ],
        }
    ]


def _safe_decode(data: bytes, encoding: str) -> tuple[str, bool]:
    try:
        return data.decode(encoding), False
    except UnicodeDecodeError:
        decoded = data.decode(encoding, errors="replace")
        decoded = decoded.replace("\ufffd", "?")
        return decoded, True


def _format_bytes(size: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.2f}{unit}"
        value /= 1024
    return f"{size}B"


def _format_read_result(
    path: Path,
    text: str,
    size_bytes: int,
    truncated: bool,
    limit: int,
    had_decode_issue: bool,
) -> str:
    lines: list[str] = ["<file_result>"]
    lines.append(f"action: read")
    lines.append(f"path: {path}")
    lines.append(f"size: {_format_bytes(size_bytes)}")
    if had_decode_issue:
        lines.append("note: binary or non-utf8 data was replaced with '?'")
    if truncated:
        lines.append(f"note: output truncated to first {limit} bytes")
    lines.append("")
    lines.append("```")
    lines.append(text)
    lines.append("```")
    lines.append("</file_result>")
    return "\n".join(lines)


def _format_write_result(path: Path, action: str, size: int) -> str:
    lines = ["<file_result>"]
    lines.append(f"action: {action}")
    lines.append(f"path: {path}")
    lines.append(f"size: {_format_bytes(size)}")
    lines.append(f"message: {action} successful")
    lines.append("</file_result>")
    return "\n".join(lines)


def _format_stat_result(path: Path, stat_result: os.stat_result) -> str:
    lines = ["<file_result>"]
    lines.append("action: stat")
    lines.append(f"path: {path}")
    lines.append(f"size: {_format_bytes(stat_result.st_size)}")
    modified = datetime.fromtimestamp(stat_result.st_mtime).isoformat(
        sep=" ", timespec="seconds"
    )
    created = datetime.fromtimestamp(stat_result.st_ctime).isoformat(
        sep=" ", timespec="seconds"
    )
    lines.append(f"modified: {modified}")
    lines.append(f"created: {created}")
    lines.append("</file_result>")
    return "\n".join(lines)


def _format_list_result(path: Path, entries: list[os.DirEntry]) -> str:
    lines = ["<file_result>"]
    lines.append("action: list")
    lines.append(f"path: {path}")
    lines.append(f"entries: showing {len(entries)} item(s)")
    lines.append("")
    lines.append("name | type | size | modified")
    lines.append("-" * 60)
    for entry in entries:
        try:
            stat_result = entry.stat()
        except FileNotFoundError:
            continue
        kind = "dir" if entry.is_dir() else "file"
        size = _format_bytes(stat_result.st_size)
        mtime = datetime.fromtimestamp(stat_result.st_mtime).isoformat(
            sep=" ", timespec="seconds"
        )
        lines.append(f"{entry.name} | {kind} | {size} | {mtime}")
    lines.append("</file_result>")
    return "\n".join(lines)


async def file(
    action: Annotated[
        Literal["read", "write", "append", "list", "stat"],
        (
            "文件操作动作："
            "read 读取；write 覆盖写入；append 追加；"
            "list 列目录；stat 元信息。"
        ),
    ],
    path: Annotated[
        str,
        "目标文件或目录的路径（支持相对或绝对路径）",
    ],
    content: Annotated[str, "write/append 时写入的文本内容"] = "",
    encoding: Annotated[str, "读写使用的文本编码"] = "utf-8",
    limit: Annotated[
        int,
        "读取时最多返回的字节数，0 表示不截断",
    ] = MAX_PREVIEW_BYTES,
):
    """本地文件工具，支持读写/列目录/查看元信息。"""
    resolved_path = Path(path).expanduser()
    if not resolved_path.is_absolute():
        resolved_path = (Path.cwd() / resolved_path).resolve()

    action_normalized = action.lower()
    if action_normalized == "read":
        if not resolved_path.exists():
            msg = (
                "<file_result>action: read\n"
                f"path: {resolved_path}\nerror: file not found</file_result>"
            )
            return _wrap_tool_result(msg)
        if not resolved_path.is_file():
            msg = (
                "<file_result>action: read\n"
                f"path: {resolved_path}\nerror: target is not a file</file_result>"
            )
            return _wrap_tool_result(msg)
        data = resolved_path.read_bytes()
        preview_limit = limit if limit and limit > 0 else None
        preview = data if preview_limit is None else data[:preview_limit]
        decoded, had_decode_issue = _safe_decode(preview, encoding)
        truncated = preview_limit is not None and len(data) > preview_limit
        formatted = _format_read_result(
            resolved_path,
            decoded,
            len(data),
            truncated,
            preview_limit or 0,
            had_decode_issue,
        )
        return _wrap_tool_result(formatted)

    if action_normalized in {"write", "append"}:
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if action_normalized == "append" else "w"
        resolved_path.open(mode, encoding=encoding).write(content)
        size = resolved_path.stat().st_size
        formatted = _format_write_result(resolved_path, action_normalized, size)
        return _wrap_tool_result(formatted)

    if action_normalized == "stat":
        if not resolved_path.exists():
            msg = (
                "<file_result>action: stat\n"
                f"path: {resolved_path}\nerror: file not found</file_result>"
            )
            return _wrap_tool_result(msg)
        stat_result = resolved_path.stat()
        formatted = _format_stat_result(resolved_path, stat_result)
        return _wrap_tool_result(formatted)

    if action_normalized == "list":
        target = resolved_path
        if not target.exists():
            msg = (
                "<file_result>action: list\n"
                f"path: {target}\nerror: path not found</file_result>"
            )
            return _wrap_tool_result(msg)
        if target.is_file():
            target = target.parent
        try:
            entries = sorted(
                list(target.iterdir()),
                key=lambda e: e.name.lower(),
            )[:MAX_LIST_ENTRIES]
        except PermissionError as exc:
            logger.warning(f"list permission error on {target}: {exc}")
            msg = (
                "<file_result>action: list\n"
                f"path: {target}\nerror: permission denied</file_result>"
            )
            return _wrap_tool_result(msg)
        formatted = _format_list_result(target, entries)
        return _wrap_tool_result(formatted)

    msg = (
        "<file_result>"
        f"error: unsupported action '{action}'."
        " supported: read, write, append, list, stat"
        "</file_result>"
    )
    return _wrap_tool_result(msg)


def create_file_tool() -> FunctionTool:
    """Create a file tool with action + path schema."""
    function_tool = FunctionTool(
        name="file",
        func=file,
        description=(
            "本地文件工具，支持 read/write/append/list/stat 操作，"
            "使用 action + path 的参数格式。"
        ),
    )
    logger.info("file tool created successfully")
    return function_tool
