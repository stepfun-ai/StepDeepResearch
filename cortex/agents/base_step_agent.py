import copy
import json
import logging
import re
from abc import abstractmethod
from typing import Any, AsyncGenerator, Callable

from agentkit.trace import create_span
from cortex.agents.base_agent import BaseAgent
from cortex.agents.input.input import InputChannel
from cortex.agents.types import (
    AgentConfig,
    AgentMessageType,
    AgentResponse,
    AgentRunningStatus,
)
from cortex.context import BaseContext
from cortex.model.definition import ChatMessage
from cortex.model.provider import ModelProvider
from cortex.tools.toolset import ToolSet
from cortex.runtime_config import get_context_limit_overrides

try:
    import tiktoken
except Exception:  # noqa: BLE001
    tiktoken = None

logger = logging.getLogger(__name__)

DEFAULT_FORCE_FINAL_ANSWER_UPPER_LIMIT = 100_000
DEFAULT_FORCE_FINAL_ANSWER_THRESHOLD = DEFAULT_FORCE_FINAL_ANSWER_UPPER_LIMIT
DEFAULT_FORCE_FINAL_ANSWER_LOWER_LIMIT_RATIO = 0.9
DEFAULT_FORCE_FINAL_ANSWER_LOWER_LIMIT = max(
    int(DEFAULT_FORCE_FINAL_ANSWER_UPPER_LIMIT * DEFAULT_FORCE_FINAL_ANSWER_LOWER_LIMIT_RATIO),
    1,
)
DEFAULT_FORCE_FINAL_ANSWER_PROMPT = (
    "你现在已经达到了你所能处理的最大上下文长度。你应该停止进行工具调用，"
    "并基于以上所有信息重新思考，然后按照以下格式提供你认为最可能的答案："
    "<think>你的最终思考</think>\n<answer>你的答案</answer>"
)
_AVG_CHARS_PER_TOKEN = 3


def _get_encoding(model_name: str | None):
    if not tiktoken:
        return None
    if not model_name:
        try:
            return tiktoken.get_encoding("cl100k_base")
        except Exception:  # noqa: BLE001
            return None
    try:
        return tiktoken.encoding_for_model(model_name)
    except Exception:  # noqa: BLE001
        try:
            return tiktoken.get_encoding("cl100k_base")
        except Exception:  # noqa: BLE001
            return None


def _estimate_token_length(messages: list[ChatMessage], model_name: str | None) -> int:
    """Token estimator with tiktoken fallback."""
    encoding = _get_encoding(model_name)
    total_tokens = 0
    for message in messages:
        try:
            payload = message.model_dump(exclude_none=True)
        except Exception:
            payload = {
                "role": getattr(message, "role", None),
                "content": getattr(message, "content", None),
            }
        serialized = json.dumps(payload, ensure_ascii=False)
        if encoding:
            try:
                total_tokens += len(encoding.encode(serialized))
                continue
            except Exception:  # noqa: BLE001
                encoding = None
        total_tokens += len(serialized) // _AVG_CHARS_PER_TOKEN
    return total_tokens


def _compress_batch_search_result(content: str) -> str:
    """Strip verbose content and mark compressed."""
    compressed = re.sub(r"<content>.*?</content>\s*", "", content, flags=re.S)
    compressed = compressed.replace(
        "<batch_search_results>", "<batch_search_results_compressed>", 1
    )
    compressed = compressed.replace(
        "</batch_search_results>", "</batch_search_results_compressed>", 1
    )
    return compressed


class BaseStepAgent(BaseAgent):
    """
    Base class for step-based Agent

    Implements run() method, executes tasks by calling step() in a loop
    step() method returns a tuple containing a flag indicating whether to stop
    """

    def __init__(
        self,
        context: BaseContext,
        config: AgentConfig,
        provider: ModelProvider | None = None,
        toolset: ToolSet | None = None,
    ):
        super().__init__(config=config, toolset=toolset, provider=provider)
        self.current_round = 0
        self.context = context
        extra_cfg = config.extra_config if config and config.extra_config else {}
        self._force_final_answer_enabled = extra_cfg.get("force_final_answer", False)
        threshold_override = extra_cfg.get("final_answer_context_threshold")
        upper_override = extra_cfg.get("final_answer_context_upper_limit")
        lower_override = extra_cfg.get("final_answer_context_lower_limit")
        upper_from_extra = upper_override is not None
        lower_from_extra = lower_override is not None
        if not upper_from_extra or not lower_from_extra:
            runtime_upper, runtime_lower = get_context_limit_overrides()
            if not upper_from_extra and runtime_upper is not None:
                upper_override = runtime_upper
            # Only apply runtime lower default when upper isn't explicitly overridden;
            # otherwise keep the existing "derive lower from upper" behavior.
            if (
                not lower_from_extra
                and not upper_from_extra
                and runtime_lower is not None
            ):
                lower_override = runtime_lower

        def _normalize_limit(value: Any) -> int | None:
            if isinstance(value, (int, float)):
                return int(value)
            return None

        upper_limit = _normalize_limit(upper_override)
        if upper_limit is None:
            upper_limit = _normalize_limit(threshold_override)
        if upper_limit is None or upper_limit <= 0:
            upper_limit = DEFAULT_FORCE_FINAL_ANSWER_UPPER_LIMIT
        upper_limit = max(upper_limit, 2)

        lower_limit = _normalize_limit(lower_override)
        if lower_limit is None or lower_limit <= 0:
            derived = int(upper_limit * DEFAULT_FORCE_FINAL_ANSWER_LOWER_LIMIT_RATIO)
            lower_limit = derived if derived > 0 else DEFAULT_FORCE_FINAL_ANSWER_LOWER_LIMIT
        lower_limit = max(lower_limit, 1)
        if lower_limit >= upper_limit:
            lower_limit = max(upper_limit - 1, 1)

        self._force_final_answer_upper_limit = upper_limit
        self._force_final_answer_lower_limit = lower_limit
        self._force_final_answer_prompt = extra_cfg.get(
            "final_answer_prompt", DEFAULT_FORCE_FINAL_ANSWER_PROMPT
        )
        self._force_prompt_inserted = False
        self._model_name = getattr(config.model, "name", None) if config and config.model else None

    def _insert_final_prompt(self) -> None:
        """Activate the force-final-answer prompt for subsequent model calls.

        Kept for backward compatibility; this does not mutate persisted context history.
        """
        if not self._force_final_answer_enabled or self._force_prompt_inserted:
            return
        self._force_prompt_inserted = True
        logger.info("@%s Final answer prompt activated", self.name)

    def _make_force_final_answer_message(self) -> ChatMessage:
        prompt = self._force_final_answer_prompt or DEFAULT_FORCE_FINAL_ANSWER_PROMPT
        return ChatMessage(role="system", content=prompt)

    def _ensure_final_prompt(self, messages: list[ChatMessage]) -> None:
        """Ensure the force-final-answer prompt is present in model input.

        This should not mutate the persisted context history.
        """
        if not self._force_final_answer_enabled or not self._force_prompt_inserted:
            return
        prompt_message = self._make_force_final_answer_message()
        if messages:
            last = messages[-1]
            if (
                getattr(last, "role", None) == prompt_message.role
                and getattr(last, "content", None) == prompt_message.content
            ):
                return
        messages.append(prompt_message)

    @staticmethod
    def _copy_messages(messages: list[ChatMessage]) -> list[ChatMessage]:
        """Deep-copy messages so we can mutate model input without touching stored history."""
        copied: list[ChatMessage] = []
        for message in messages:
            try:
                copied.append(message.model_copy(deep=True))
            except Exception:
                copied.append(copy.deepcopy(message))
        return copied

    @classmethod
    def _compress_batch_search_in_block(cls, block: dict) -> bool:
        """Compress batch_search XML in the first text block found (in-place)."""
        if block.get("type") == "text":
            text_value = block.get("text")
            if (
                isinstance(text_value, str)
                and "<batch_search_results" in text_value
                and "batch_search_results_compressed" not in text_value
            ):
                block["text"] = _compress_batch_search_result(text_value)
                return True

        nested = block.get("content")
        if isinstance(nested, list):
            for item in nested:
                if isinstance(item, dict) and cls._compress_batch_search_in_block(item):
                    return True
        return False

    @classmethod
    def _compress_batch_search_in_content(cls, content: Any) -> tuple[Any, bool]:
        if isinstance(content, str):
            if (
                "<batch_search_results" in content
                and "batch_search_results_compressed" not in content
            ):
                return _compress_batch_search_result(content), True
            return content, False

        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and cls._compress_batch_search_in_block(item):
                    return content, True
            return content, False

        return content, False

    def _prepare_messages_for_model(self) -> list[ChatMessage]:
        """Build the message list sent to the model, without mutating stored history."""
        raw_messages = self.context.get_all()
        messages: list[ChatMessage] = list(raw_messages)

        if not self._force_final_answer_enabled:
            return messages

        # If final-answer mode has been activated before, always include the prompt in model input.
        self._ensure_final_prompt(messages)

        token_estimate = _estimate_token_length(messages, self._model_name)
        if token_estimate < self._force_final_answer_upper_limit:
            return messages

        # We are going to mutate messages for context management: deep-copy first.
        messages = self._copy_messages(messages)

        self._handle_context_overflow(messages)
        self._ensure_final_prompt(messages)
        self._ensure_context_within_upper_limit(messages)
        return messages

    def _shrink_batch_search_results(self, messages: list[ChatMessage]) -> bool:
        """Compress earliest uncompressed batch_search_result content (model-input only)."""
        for message in messages:
            content = getattr(message, "content", None)
            new_content, changed = self._compress_batch_search_in_content(content)
            if changed:
                message.content = new_content
                logger.info("@%s Compressed batch_search_results to save tokens", self.name)
                return True
        return False

    @staticmethod
    def _parse_tool_call_arguments(raw_arguments: Any) -> dict[str, Any]:
        """Safely parse tool call arguments JSON."""
        if not isinstance(raw_arguments, str) or not raw_arguments.strip():
            return {}
        try:
            parsed = json.loads(raw_arguments)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:  # noqa: BLE001
            return {}

    def _is_search_tool_call(self, tool_name: str | None, tool_args: dict[str, Any]) -> bool:
        """Identify whether a tool call is search-related."""
        if not tool_name:
            return False
        lowered = tool_name.lower()
        if "search" in lowered:
            return True
        if lowered == "batch_web_surfer":
            action = tool_args.get("action")
            if isinstance(action, str) and action.lower() == "batch_search":
                return True
        return False

    def _drop_oldest_tool_cycle(
        self,
        messages: list[ChatMessage],
        predicate: Callable[[str | None, dict[str, Any]], bool] | None = None,
        log_context: str = "tool",
    ) -> bool:
        """Drop earliest tool call message plus all corresponding tool results."""
        drop_indices: set[int] = set()
        for idx, message in enumerate(messages):
            tool_calls = getattr(message, "tool_calls", None)
            if not tool_calls:
                continue
            matched_any = False
            for tc in tool_calls:
                try:
                    tool_name = tc.function.name
                    raw_arguments = tc.function.arguments
                except Exception:
                    tool_name = None
                    raw_arguments = None
                parsed_args = self._parse_tool_call_arguments(raw_arguments)
                if predicate and not predicate(tool_name, parsed_args):
                    continue
                matched_any = True

            if not matched_any:
                continue

            drop_indices.add(idx)

            # Find corresponding tool results for all tool calls in this message.
            for tc in tool_calls:
                tc_id = getattr(tc, "id", None)
                if not tc_id:
                    continue
                for j in range(idx + 1, len(messages)):
                    tool_msg = messages[j]
                    if getattr(tool_msg, "role", None) != "tool":
                        continue
                    if getattr(tool_msg, "tool_call_id", None) == tc_id:
                        drop_indices.add(j)
                        break

            break

        if not drop_indices:
            return False

        for del_idx in sorted(drop_indices, reverse=True):
            messages.pop(del_idx)

        logger.warning(
            "@%s Dropped earliest %s tool call/results to shrink context", self.name, log_context
        )
        return True

    def _trim_oldest_messages(self, messages: list[ChatMessage]) -> bool:
        """Drop oldest non-system messages until under threshold."""
        if not messages or len(messages) <= 1:
            return False
        removed = False
        idx = 0
        while (
            idx < len(messages)
            and _estimate_token_length(messages, self._model_name)
            > self._force_final_answer_upper_limit
        ):
            if getattr(messages[idx], "role", None) == "system":
                idx += 1
                continue
            messages.pop(idx)
            removed = True
        if removed:
            logger.warning("@%s Trimmed oldest messages to satisfy context budget", self.name)
        return removed

    def _ensure_context_within_upper_limit(self, messages: list[ChatMessage]) -> None:
        """Ensure context is below the configured upper limit before forcing final answer."""
        if not self._force_final_answer_enabled:
            return
        while True:
            token_estimate = _estimate_token_length(messages, self._model_name)
            if token_estimate <= self._force_final_answer_upper_limit:
                return
            if self._drop_oldest_tool_cycle(messages, log_context="any"):
                continue
            if self._trim_oldest_messages(messages):
                continue
            break

        final_tokens = _estimate_token_length(messages, self._model_name)
        if final_tokens > self._force_final_answer_upper_limit:
            logger.warning(
                "@%s Unable to trim context below upper limit (%s tokens remaining)",
                self.name,
                final_tokens,
            )

    def _handle_context_overflow(self, messages: list[ChatMessage]) -> None:
        """Enforce two-threshold hysteresis for search results before triggering final answer."""
        if not self._force_final_answer_enabled:
            return

        token_estimate = _estimate_token_length(messages, self._model_name)
        if token_estimate < self._force_final_answer_upper_limit:
            return

        logger.warning(
            (
                "@%s Context %s tokens reached upper limit %s; processing search tool payloads "
                "until below lower limit %s"
            ),
            self.name,
            token_estimate,
            self._force_final_answer_upper_limit,
            self._force_final_answer_lower_limit,
        )

        while True:
            token_estimate = _estimate_token_length(messages, self._model_name)
            if token_estimate < self._force_final_answer_lower_limit:
                break

            if self._shrink_batch_search_results(messages):
                continue

            if self._drop_oldest_tool_cycle(messages, self._is_search_tool_call, "search"):
                continue

            break

        final_tokens = _estimate_token_length(messages, self._model_name)
        if final_tokens < self._force_final_answer_lower_limit:
            return

        logger.warning(
            (
                "@%s Exhausted search tool cleanup but context still %s tokens (>= lower limit %s); "
                "forcing final answer workflow"
            ),
            self.name,
            final_tokens,
            self._force_final_answer_lower_limit,
        )

        if not self._force_prompt_inserted:
            self._force_prompt_inserted = True
            logger.info("@%s Final answer prompt activated", self.name)

    async def _run(
        self,
        messages: list[ChatMessage] | InputChannel[ChatMessage],
        additional_kwargs: dict | None = None,
    ) -> AsyncGenerator[AgentResponse, None]:
        """
        Run agent, calls step() method in a loop

        Args:
            messages: Input message list or input channel
            additional_kwargs: Additional parameters

        Yields:
            AgentResponse: Agent response object
        """
        if additional_kwargs is None:
            additional_kwargs = {}

        input_messages = []
        # Handle input messages
        if isinstance(messages, list):
            input_messages = messages
        elif isinstance(messages, InputChannel):
            input_messages = await messages.get()

        self.current_round = 0
        # Initialize history messages as member variable
        self.context.add(input_messages)
        should_stop = False

        # Loop calling step() until stop or reach max steps
        while self.current_round < self.max_steps:
            with create_span(
                name=f"@{self.name} Round {self.current_round}/{self.max_steps}"
            ):
                if should_stop and not self.config.unfinished_mode:
                    break
                if should_stop:
                    if isinstance(messages, InputChannel):
                        input_messages = await messages.get()
                        self.context.add(input_messages)
                        should_stop = False
                else:
                    if isinstance(messages, InputChannel):
                        input_messages = await messages.get_no_wait()
                        self.context.add(input_messages)

                self.current_round += 1
                logger.info(f"@{self.name} Round {self.current_round}/{self.max_steps}")

                try:
                    # Call step() method (now an async generator)
                    last_response = None
                    model_messages = self._prepare_messages_for_model()
                    async for response in self._step(model_messages, additional_kwargs):
                        # Update history messages (using member variable)
                        # Only add complete messages to history (has role field and not STREAM type)
                        logger.info(f"@{self.name} Response: {response}")
                        if response is None:
                            continue
                        if response.message:
                            # STREAM type messages are incremental updates, should not be added to history
                            if response.message_type == AgentMessageType.STREAM.value:
                                # Skip streaming incremental messages, they will be handled in accumulated messages
                                pass
                            else:
                                # For non-streaming messages, ensure role field exists
                                message_to_add = None
                                if isinstance(response.message, ChatMessage):
                                    if (
                                        hasattr(response.message, "role")
                                        and response.message.role
                                    ):
                                        message_to_add = response.message
                                elif isinstance(response.message, dict):
                                    if response.message.get("role"):
                                        message_to_add = ChatMessage(**response.message)

                                # Only add message to history when it has a valid role
                                if message_to_add and message_to_add.role:
                                    self.context.add([message_to_add])
                                else:
                                    logger.warning(
                                        f"@{self.name} Skipping message without role: {response.message_type}"
                                    )

                        # Set metadata (only includes round, history_messages uses member variable)
                        if response.metadata is None:
                            response.metadata = {}
                        response.metadata["step_count"] = self.current_round

                        # Return response
                        yield response
                        last_response = response

                        # Check if error occurred
                        if response.status == AgentRunningStatus.ERROR.value:
                            logger.error(
                                f"@{self.name} Error at round {self.current_round}: {response.error_msg}"
                            )
                            should_stop = True
                            break

                    # Check last response status, decide whether to stop
                    if last_response:
                        if last_response.status == AgentRunningStatus.FINISHED.value:
                            should_stop = True
                            logger.info(
                                f"@{self.name} Finished at round {self.current_round}"
                            )
                        elif last_response.status == AgentRunningStatus.ERROR.value:
                            should_stop = True
                        elif last_response.status == AgentRunningStatus.RUNNING.value:
                            # If still running, may need to continue (e.g., has tool calls)
                            # Here can decide whether to stop based on actual situation
                            pass

                except Exception as e:
                    err_text = str(e) or repr(e)
                    logger.error(
                        f"@{self.name} Exception at round {self.current_round}: {err_text}",
                        exc_info=True,
                    )
                    error_response = AgentResponse(
                        status=AgentRunningStatus.ERROR.value,
                        error_msg=err_text,
                        metadata={
                            "step_count": self.current_round,
                        },
                    )
                    yield error_response
                    should_stop = True
                    break

                # If max steps reached and not stopped yet
                if self.current_round >= self.max_steps and not should_stop:
                    logger.warning(
                        f"@{self.name} Reached max steps ({self.max_steps}) without stopping"
                    )
                    # Generate final response
                    final_response = AgentResponse(
                        status=AgentRunningStatus.STOPPED.value,
                        metadata={
                            "step_count": self.current_round,
                        },
                    )
                    yield final_response

    @abstractmethod
    async def _step(
        self,
        messages: list[ChatMessage],
        additional_kwargs: dict | None = None,
    ) -> AsyncGenerator[AgentResponse, None]:
        """
        Execute a single step, subclasses must implement this method.

        Args:
            messages: Current message history.
            additional_kwargs: Additional parameters.

        Yields:
            AgentResponse: Response for current step, can yield multiple responses.
                - Last response with status FINISHED indicates completion.
                - Status ERROR indicates an error occurred.
                - Status RUNNING indicates continue execution.
        """
        raise NotImplementedError("Subclasses must implement this method")
