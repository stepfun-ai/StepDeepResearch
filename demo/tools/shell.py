"""Shell Tool - Execute Shell Commands

Supports executing shell commands on macOS and Linux, returning structured output results.
"""

import asyncio
import os
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Annotated, cast

from loguru import logger

from cortex.model.definition import ContentBlockType
from cortex.tools.function_tool import FunctionTool

# Maximum output length (characters)
MAX_OUTPUT_LENGTH = 10240

# Shell output temporary file directory
SHELL_TMP_DIR = Path("/tmp/shell/output")


@dataclass
class ShellOutput:
    """Shell command execution output result."""
    exit_code: int | None
    stdout: str
    stderr: str
    message: str | None = None


def _truncate_from_end(content: str, max_length: int = MAX_OUTPUT_LENGTH) -> tuple[str, bool]:
    """Truncate from end, keeping the last content (more consistent with actual terminal behavior)."""
    if len(content) <= max_length:
        return content, False
    return content[-max_length:], True


def _format_shell_output(
    cmd: str,
    output: ShellOutput,
    cmd_max_length: int = 1024,
) -> str:
    """Format shell output to XML format."""
    # Truncation handling
    truncated_cmd, cmd_truncated = _truncate_from_end(cmd, cmd_max_length)
    truncated_stdout, stdout_truncated = _truncate_from_end(output.stdout)
    truncated_stderr, stderr_truncated = _truncate_from_end(output.stderr)

    # If truncated, save full output to file
    extra_message = ""
    if cmd_truncated or stdout_truncated or stderr_truncated:
        SHELL_TMP_DIR.mkdir(parents=True, exist_ok=True)
        unique_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        tmp_file = SHELL_TMP_DIR / f"{unique_name}_output.txt"

        full_output = (
            f"<cmd>{cmd}</cmd>\n"
            f"<exit_code>{output.exit_code}</exit_code>\n"
            f"<stdout>{output.stdout}</stdout>\n"
            f"<stderr>{output.stderr}</stderr>\n"
        )
        if output.message:
            full_output += f"<message>{output.message}</message>"

        tmp_file.write_text(full_output, encoding="utf-8")

        extra_message = (
            f'\n\n⚠️ [Output truncated due to length, full output saved to: "{tmp_file}"]\n'
            f'📌 **Please use file tools to read "{tmp_file}" for complete information**\n'
        )

    # Build result
    result = (
        f"<cmd>{truncated_cmd}</cmd>\n"
        f"<exit_code>{output.exit_code}</exit_code>\n"
        f"<stdout>{truncated_stdout}</stdout>\n"
        f"<stderr>{truncated_stderr}</stderr>\n"
    )

    if output.message:
        result += f"<message>{output.message}</message>"

    return result + extra_message


async def _execute_shell(
    cmd: str,
    timeout: int,
    cwd: str,
    env: dict[str, str],
) -> ShellOutput:
    """Core implementation for executing shell commands."""
    # Merge environment variables
    merged_env = {**os.environ, **env}

    # Create subprocess
    process = await asyncio.create_subprocess_shell(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=cwd,
        env=merged_env,
    )

    is_timeout = False
    try:
        # Wait for process to complete
        effective_timeout = timeout if timeout > 0 else None
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(),
            timeout=effective_timeout,
        )
    except asyncio.TimeoutError:
        is_timeout = True
        # Try graceful termination
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=0.5)
        except asyncio.TimeoutError:
            # Force kill
            process.kill()
            await process.wait()

        # Read existing output
        stdout_bytes = await cast(asyncio.StreamReader, process.stdout).read() if process.stdout else b""
        stderr_bytes = await cast(asyncio.StreamReader, process.stderr).read() if process.stderr else b""

    # Decode output, use errors='replace' to handle non-UTF-8 characters
    stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
    stderr = stderr_bytes.decode("utf-8", errors="replace").strip()

    message = f"Execution exceeded {timeout}s, force terminated." if is_timeout else None

    return ShellOutput(
        exit_code=process.returncode,
        stdout=stdout,
        stderr=stderr,
        message=message,
    )


async def shell(
    cmd: Annotated[str, "要执行的 Shell 命令字符串，支持 bash 语法"],
    timeout: Annotated[int, "命令最大执行时长（秒），为 0 表示不限时"] = 60,
    cwd: Annotated[str, "命令执行的工作目录，默认为用户主目录"] = "",
    env: Annotated[str, "传入的环境变量 JSON 字符串，会与当前环境合并，格式如 '{\"KEY\": \"value\"}'"] = "",
):
    """使用 /bin/bash 执行一个 Shell 命令，支持 cwd、env、timeout 配置，返回 stdout、stderr 和 exit_code。"""
    import json as json_module
    
    # Handle default values
    if not cwd:
        cwd = os.path.expanduser("~")
    
    # Parse env JSON string
    env_dict: dict[str, str] = {}
    if env:
        try:
            env_dict = json_module.loads(env)
        except json_module.JSONDecodeError:
            logger.warning(f"Failed to parse env parameter, using empty environment variables: {env}")

    # Execute command
    output = await _execute_shell(cmd, timeout, cwd, env_dict)

    # Format output
    formatted = _format_shell_output(cmd, output)
    result = [
        {
            "type": ContentBlockType.TOOLRESULT.value,
            "content": [
                {
                    "type": ContentBlockType.TEXT.value,
                    ContentBlockType.TEXT.value: formatted,
                }
            ]
        }
    ]
    return result


def create_shell_tool() -> FunctionTool:
    """Create shell tool.

    Returns:
        FunctionTool: shell tool instance.
    """
    function_tool = FunctionTool(
        name="shell",
        func=shell,
        description="使用 /bin/bash 执行一个 Shell 命令，支持 cwd、env、timeout 配置，返回 stdout、stderr 和 exit_code。",
    )

    logger.info("shell tool created successfully")
    return function_tool

