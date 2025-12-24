"""File-based context management class."""

import asyncio
import json
import os
from pathlib import Path
from typing import List

from cortex.model.definition import ChatMessage

from cortex.context.base_context import BaseContext


class FileContext(BaseContext):
    """File-based context management class, each session_id corresponds to a file."""

    def __init__(
        self,
        session_id: str,
        storage_dir: str = "contexts",
        batch_size: int = 5,
        delay_seconds: float = 2.0,
    ):
        """
        Initialize file context.

        Args:
            session_id: Session ID
            storage_dir: Storage directory, defaults to "contexts"
            batch_size: Batch write size, write immediately when this count is reached
            delay_seconds: Delay write time (seconds)
        """
        super().__init__(session_id)
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(exist_ok=True)
        self.file_path = self.storage_dir / f"{session_id}.jsonl"
        self._messages: List[ChatMessage] = []
        self._pending_messages: List[ChatMessage] = []
        self._batch_size = batch_size
        self._delay_seconds = delay_seconds
        self._write_task = None
        self._load_messages()

    def __del__(self):
        """Automatically call flush when object is garbage collected"""
        try:
            self.flush()
        except Exception:
            # Ignore exceptions in destructor to avoid affecting garbage collection
            pass

    def _load_messages(self) -> None:
        """Load messages from file"""
        if self.file_path.exists():
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    self._messages = []
                    for line in f:
                        line = line.strip()
                        if line:
                            msg_data = json.loads(line)
                            self._messages.append(ChatMessage(**msg_data))
            except (json.JSONDecodeError, KeyError, TypeError):
                # If file is corrupted or format is incorrect, start fresh
                self._messages = []

    def _save_messages(self) -> None:
        """Save messages to file"""
        # Rewrite entire file
        all_messages = self._messages + self._pending_messages
        with open(self.file_path, "w", encoding="utf-8") as f:
            for msg in all_messages:
                json_line = json.dumps(msg.model_dump(), ensure_ascii=False)
                f.write(json_line + "\n")

        # Move pending messages to main message list
        self._messages.extend(self._pending_messages)
        self._pending_messages = []

    async def _delayed_write(self) -> None:
        """Delayed write task"""
        await asyncio.sleep(self._delay_seconds)
        if self._pending_messages:
            self._save_messages()
        self._write_task = None

    def _schedule_write(self) -> None:
        """Schedule write task"""
        # If batch size is reached, write immediately
        if len(self._pending_messages) >= self._batch_size:
            if self._write_task:
                self._write_task.cancel()
                self._write_task = None
            self._save_messages()
        else:
            # If no write task in progress, create a delayed write task
            if not self._write_task:
                self._write_task = asyncio.create_task(self._delayed_write())

    def add(self, messages: list[ChatMessage]) -> None:
        """Add chat messages to context

        Args:
            messages: List of chat messages to add
        """
        self._pending_messages.extend(messages)
        self._schedule_write()

    def get_all(self) -> List[ChatMessage]:
        """Get all chat messages

        Returns:
            List[ChatMessage]: List of all chat messages
        """
        return (self._messages + self._pending_messages).copy()

    def clear(self) -> None:
        """Clear context messages"""
        if self._write_task:
            self._write_task.cancel()
            self._write_task = None
        self._messages = []
        self._pending_messages = []
        if self.file_path.exists():
            os.remove(self.file_path)

    def flush(self) -> None:
        """Force write all pending messages"""
        if self._write_task:
            self._write_task.cancel()
            self._write_task = None
        if self._pending_messages:
            self._save_messages()
