"""Checkpoint storage implementation."""

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class CheckpointStorage:
    def save_state(self, checkpoint_id: str, state: dict[str, Any]):
        """Save state."""
        raise NotImplementedError("Subclass must implement this method")

    def load_state(self, checkpoint_id: str) -> dict[str, Any] | None:
        """Load state from storage."""
        raise NotImplementedError("Subclass must implement this method")

    def delete_state(self, checkpoint_id: str):
        """Delete the specified checkpoint."""
        raise NotImplementedError("Subclass must implement this method")

    async def asave_state(self, checkpoint_id: str, state: dict[str, Any]):
        """Save state asynchronously."""
        raise NotImplementedError("Subclass must implement this method")

    async def aload_state(self, checkpoint_id: str) -> dict[str, Any] | None:
        """Load state from storage asynchronously."""
        raise NotImplementedError("Subclass must implement this method")

    async def adelete_state(self, checkpoint_id: str):
        """Delete the specified checkpoint asynchronously."""
        raise NotImplementedError("Subclass must implement this method")


class CheckPointer(Generic[T]):
    """Checkpoint manager base class."""

    def __init__(
        self,
        checkpoint_id: str,
        storage: CheckpointStorage,
        init_state: T | None,
        state_type: type[T],
    ):
        """
        Initialize CheckPointer.

        Args:
            checkpoint_id: Checkpoint ID for identifying and loading specific checkpoints
            storage: Storage backend
            init_state: Initial state
            state_type: State type, must be a class inheriting from BaseModel
        """
        self.checkpoint_id = checkpoint_id
        self.storage = storage
        self.init_state = init_state
        self.state_type = state_type
        self._state: T | None = None

    def __enter__(self) -> T:
        state_dict = self.storage.load_state(self.checkpoint_id)
        if state_dict is None:
            self._state = self.init_state
        else:
            # Convert dict to pydantic model
            self._state = self.state_type.model_validate(state_dict)
        return self._state

    def __exit__(self, exc_type, exc_value, traceback):
        # Auto-save state on exit
        if self._state is not None and self.checkpoint_id is not None:
            try:
                # Use pydantic's model_dump method to convert to dict
                state_dict = self._state.model_dump()
                self.storage.save_state(self.checkpoint_id, state_dict)
                logger.debug("Auto-saved state on exit: checkpoint_id=%s", self.checkpoint_id)
            except Exception as e:
                logger.error("Failed to save state on exit: %s", str(e))
            # todo handle cancel error
        return False

    async def __aenter__(self):
        return self.__enter__()

    async def __aexit__(self, exc_type, exc_value, traceback):
        return self.__exit__(exc_type, exc_value, traceback)


class MemoryCheckPointer(CheckpointStorage):
    """Memory-based Checkpoint storage."""

    def __init__(self):
        self._storage: dict[str, dict[str, Any]] = {}

    def save_state(self, checkpoint_id: str, state: dict[str, Any]):
        """Save state to memory."""
        self._storage[checkpoint_id] = state
        logger.debug("State saved to memory: checkpoint_id=%s", checkpoint_id)

    def load_state(self, checkpoint_id: str) -> dict[str, Any] | None:
        """Load state from memory."""
        state = self._storage.get(checkpoint_id)
        if state:
            logger.debug("State loaded from memory: checkpoint_id=%s", checkpoint_id)
        return state

    def delete_state(self, checkpoint_id: str):
        """Delete the specified checkpoint."""
        if checkpoint_id in self._storage:
            del self._storage[checkpoint_id]
            logger.debug("Deleted checkpoint from memory: checkpoint_id=%s", checkpoint_id)

    async def asave_state(self, checkpoint_id: str, state: dict[str, Any]):
        """Save state to memory."""
        self.save_state(checkpoint_id, state)

    async def aload_state(self, checkpoint_id: str) -> dict[str, Any] | None:
        """Load state from memory."""
        return self.load_state(checkpoint_id)

    async def adelete_state(self, checkpoint_id: str):
        """Delete the specified checkpoint."""
        self.delete_state(checkpoint_id)


class FileCheckPointer(CheckpointStorage):
    """File-based Checkpoint storage."""

    def __init__(self, checkpoint_dir: str):
        """
        Initialize file storage.

        Args:
            checkpoint_dir: Checkpoint storage directory
        """
        self.checkpoint_dir = Path(checkpoint_dir)

        # Ensure directory exists
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def _get_checkpoint_file(self, checkpoint_id: str) -> Path:
        """Get checkpoint file path."""
        return self.checkpoint_dir / f"{checkpoint_id}.json"

    def save_state(self, checkpoint_id: str, state: dict[str, Any]):
        """Save state to file."""
        checkpoint_file = self._get_checkpoint_file(checkpoint_id)
        try:
            # Write to file
            with open(checkpoint_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)

            logger.debug("State saved to file: %s", checkpoint_file)

        except Exception as e:
            logger.error("Failed to save state: %s", str(e))
            raise

    def load_state(self, checkpoint_id: str) -> dict[str, Any] | None:
        """Load state from file."""
        checkpoint_file = self._get_checkpoint_file(checkpoint_id)
        if not checkpoint_file.exists():
            logger.debug("Checkpoint file not found: %s", checkpoint_file)
            return None

        try:
            with open(checkpoint_file, "r", encoding="utf-8") as f:
                state_dict = json.load(f)

            logger.debug("State loaded from file: %s", checkpoint_file)
            return state_dict

        except (OSError, json.JSONDecodeError, ValueError) as e:
            logger.error("Failed to load state: %s", str(e))
            return None

    def delete_state(self, checkpoint_id: str):
        """Delete checkpoint file."""
        checkpoint_file = self._get_checkpoint_file(checkpoint_id)
        if checkpoint_file.exists():
            os.remove(checkpoint_file)
            logger.debug("Deleted checkpoint file: %s", checkpoint_file)

    async def asave_state(self, checkpoint_id: str, state: dict[str, Any]):
        """Save state to file."""
        self.save_state(checkpoint_id, state)

    async def aload_state(self, checkpoint_id: str) -> dict[str, Any] | None:
        """Load state from file."""
        return self.load_state(checkpoint_id)

    async def adelete_state(self, checkpoint_id: str):
        """Delete checkpoint file."""
        self.delete_state(checkpoint_id)


class SqliteCheckPointer(CheckpointStorage):
    """SQLite-based Checkpoint storage."""

    def __init__(self, db_path: str):
        """
        Initialize SQLite storage.

        Args:
            db_path: SQLite database file path
        """
        import sqlite3

        self.db_path = db_path
        self.conn: sqlite3.Connection | None = None

        # Ensure database directory exists
        db_dir = Path(db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

        # Initialize database table
        self._init_db()

    def _init_db(self):
        """Initialize database table."""
        import sqlite3

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS checkpoints (
                checkpoint_id TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        conn.commit()
        conn.close()

    def __enter__(self):
        import sqlite3

        self.conn = sqlite3.connect(self.db_path)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.conn:
            self.conn.close()
            self.conn = None
        return False

    async def __aenter__(self):
        return self.__enter__()

    async def __aexit__(self, exc_type, exc_value, traceback):
        return self.__exit__(exc_type, exc_value, traceback)

    def save_state(self, checkpoint_id: str, state: dict[str, Any]):
        """Save state to SQLite."""
        import sqlite3

        conn = sqlite3.connect(self.db_path)
        try:
            # Convert to JSON string
            state_json = json.dumps(state, ensure_ascii=False)

            # Insert or update
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO checkpoints (checkpoint_id, state, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            """,
                (checkpoint_id, state_json),
            )

            conn.commit()
            logger.debug("State saved to SQLite: checkpoint_id=%s", checkpoint_id)

        except Exception as e:
            logger.error("Failed to save state: %s", str(e))
            raise
        finally:
            conn.close()

    def load_state(self, checkpoint_id: str) -> dict[str, Any] | None:
        """Load state from SQLite."""
        import sqlite3

        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT state FROM checkpoints WHERE checkpoint_id = ?",
                (checkpoint_id,),
            )

            row = cursor.fetchone()
            if not row:
                logger.debug("Checkpoint not found: checkpoint_id=%s", checkpoint_id)
                return None

            state_json = row[0]
            state_dict = json.loads(state_json)

            logger.debug("State loaded from SQLite: checkpoint_id=%s", checkpoint_id)
            return state_dict

        except (json.JSONDecodeError, ValueError) as e:
            logger.error("Failed to load state: %s", str(e))
            return None
        finally:
            conn.close()

    def delete_state(self, checkpoint_id: str):
        """Delete checkpoint."""
        import sqlite3

        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM checkpoints WHERE checkpoint_id = ?", (checkpoint_id,)
            )
            conn.commit()
            logger.debug("Deleted checkpoint: checkpoint_id=%s", checkpoint_id)
        finally:
            conn.close()

    async def asave_state(self, checkpoint_id: str, state: dict[str, Any]):
        """Save state to SQLite."""
        self.save_state(checkpoint_id, state)

    async def aload_state(self, checkpoint_id: str) -> dict[str, Any] | None:
        """Load state from SQLite."""
        return self.load_state(checkpoint_id)

    async def adelete_state(self, checkpoint_id: str):
        """Delete checkpoint."""
        self.delete_state(checkpoint_id)
