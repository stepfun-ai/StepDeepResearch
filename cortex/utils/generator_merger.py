"""Generator merger implementation using asyncio."""

import asyncio
from collections.abc import Generator
from typing import Any, AsyncGenerator, Awaitable, Callable, Optional


class GeneratorMerger:
    """A merger that combines multiple generator functions using asyncio for concurrent execution."""

    def __init__(
        self,
        on_generator_complete: Optional[
            Callable[[str, str, Optional[Exception]], Awaitable[None]]
        ] = None,
    ):
        """
        Initialize the merger.

        Args:
            on_generator_complete: Optional callback function called when a sub-generator completes.
                                   Parameters: (generator_id, generator_type, error)
                                   If not provided, completion events will be yielded.
        """
        self._generators: dict[str, Callable[[], Generator[Any, None, None]]] = {}
        self._async_generators: dict[str, Callable[[], AsyncGenerator[Any, None]]] = {}
        self._running_tasks: list[asyncio.Task] = []
        self._queue: asyncio.Queue = asyncio.Queue()
        self._active_count: int = 0
        self._lock: asyncio.Lock = asyncio.Lock()
        self._processed_generators: set[str] = set()  # Processed generator IDs
        self._on_generator_complete = on_generator_complete
        self._generator_id_counter: int = 0  # Counter for generating unique generator IDs

    def add_generator(
        self,
        generator_func: Callable[[], Generator[Any, None, None]],
        generator_id: Optional[str] = None,
    ):
        """
        Dynamically add a synchronous generator function.

        Note: This method is synchronous and does not use locks when adding.
        Lock protection is primarily used in the async merge() and delete operations.

        Args:
            generator_func: A function that returns a synchronous generator
            generator_id: Optional generator identifier used in completion events
        """
        if generator_id is None:
            generator_id = f"sync_gen_{len(self._generators)}"

        if generator_id in self._generators or generator_id in self._async_generators:
            raise ValueError(f"Generator {generator_id} already exists")

        self._generators[generator_id] = generator_func

    def add_async_generator(
        self,
        async_generator_func: Callable[[], AsyncGenerator[Any, None]],
        generator_id: Optional[str] = None,
    ):
        """
        Dynamically add an async generator function.

        Args:
            async_generator_func: A function that returns an async generator
            generator_id: Optional generator identifier used in completion events
        """
        if generator_id is None:
            generator_id = f"async_gen_{len(self._async_generators)}"

        # Check if generator_id already exists
        if generator_id in self._generators or generator_id in self._async_generators:
            raise ValueError(f"Generator {generator_id} already exists")

        self._async_generators[generator_id] = async_generator_func

    def _get_next_item(self, generator: Generator[Any, None, None]) -> tuple[bool, Any]:
        """
        Get the next value from a generator (runs in thread).

        Args:
            generator: generator object

        Returns:
            (has_more, item) tuple, where has_more indicates if there are more values
        """
        try:
            item = next(generator)
            return (True, item)
        except StopIteration:
            return (False, None)

    async def _run_generator_with_wrapper(
        self,
        generator_id: str,
        generator_type: str,
        generator_executor: Callable[[], AsyncGenerator[Any, None]],
    ):
        """
        Generic generator execution wrapper.

        Args:
            generator_id: generator identifier
            generator_type: generator type ("sync" or "async")
            generator_executor: async function that executes the generator and yields values
        """
        async with self._lock:
            self._active_count += 1

        error = None

        try:
            # Execute specific generator logic
            async for item in generator_executor():
                # Put generator-produced values into queue
                await self._queue.put(item)

        except Exception as e:
            error = e
            # If generator errors, also put into queue for processing
            await self._queue.put(("__error__", e))
        finally:
            async with self._lock:
                self._active_count -= 1

            # Notify generator completion
            await self._notify_generator_complete(generator_id, generator_type, error)

    async def _run_generator(
        self,
        generator_id: str,
        generator_func: Callable[[], Generator[Any, None, None]],
    ):
        """
        Run a synchronous generator in the event loop.

        Args:
            generator_id: generator identifier
            generator_func: function that returns a synchronous generator
        """

        async def sync_generator_executor():
            # Create generator (this step is fast, doesn't need to run in thread)
            generator = generator_func()
            loop = asyncio.get_event_loop()

            # Get values one by one, run in thread pool to avoid blocking event loop
            while True:
                has_more, item = await loop.run_in_executor(
                    None, self._get_next_item, generator
                )

                if not has_more:
                    break

                yield item

        await self._run_generator_with_wrapper(
            generator_id, "sync", sync_generator_executor
        )

    async def _run_async_generator(
        self,
        generator_id: str,
        async_generator_func: Callable[[], AsyncGenerator[Any, None]],
    ):
        """
        Run an async generator in the event loop.

        Args:
            generator_id: generator identifier
            async_generator_func: function that returns an async generator
        """

        async def async_generator_executor():
            # Create async generator
            async_generator = async_generator_func()

            # Get values directly from async generator
            async for item in async_generator:
                yield item

        await self._run_generator_with_wrapper(
            generator_id, "async", async_generator_executor
        )

    async def _notify_generator_complete(
        self, generator_id: str, generator_type: str, error: Optional[Exception]
    ):
        """
        Notify generator completion.

        Args:
            generator_id: Generator identifier
            generator_type: Generator type ("sync" or "async")
            error: Error object if any; otherwise None
        """
        # Use lock to protect dictionary modification
        async with self._lock:
            # Mark generator as completed
            self._processed_generators.add(generator_id)

            # Auto-delete completed generator
            if generator_type == "sync" and generator_id in self._generators:
                del self._generators[generator_id]
            elif generator_type == "async" and generator_id in self._async_generators:
                del self._async_generators[generator_id]

        event = {
            "type": "generator_complete",
            "generator_id": generator_id,
            "generator_type": generator_type,
            "status": "error" if error else "completed",
            "error": str(error) if error else None,
        }

        if self._on_generator_complete:
            # If there's a callback, call it
            if asyncio.iscoroutinefunction(self._on_generator_complete):
                await self._on_generator_complete(generator_id, generator_type, error)
            else:
                self._on_generator_complete(generator_id, generator_type, error)
        else:
            # If no callback, put event into queue, will be yielded
            await self._queue.put(("__event__", event))

    async def merge(self) -> AsyncGenerator[Any, None]:
        """
        Merge all added generators (sync and async), returning an async generator.
        Supports dynamically adding new generators during iteration.

        Yields:
            Values produced by the various generators
        """
        if not self._generators and not self._async_generators:
            return

        # Reset state
        self._queue = asyncio.Queue()
        self._active_count = 0
        self._running_tasks = []
        self._processed_generators = set()

        # Use lock to get initial generator snapshot
        async with self._lock:
            sync_generators_snapshot = list(self._generators.items())
            async_generators_snapshot = list(self._async_generators.items())

        # Create tasks for initial sync generators
        for generator_id, generator_func in sync_generators_snapshot:
            task = asyncio.create_task(
                self._run_generator(generator_id, generator_func),
                name=f"sync_{generator_id}",
            )
            self._running_tasks.append(task)

        # Create tasks for initial async generators
        for generator_id, async_generator_func in async_generators_snapshot:
            task = asyncio.create_task(
                self._run_async_generator(generator_id, async_generator_func),
                name=f"async_{generator_id}",
            )
            self._running_tasks.append(task)

        # Get values from queue and yield
        while True:
            # Use lock to get current generator snapshot
            async with self._lock:
                sync_generators_snapshot = list(self._generators.items())
                async_generators_snapshot = list(self._async_generators.items())
                processed_generators_snapshot = self._processed_generators.copy()

            # Check for newly added sync generators
            for generator_id, generator_func in sync_generators_snapshot:
                if generator_id not in processed_generators_snapshot:
                    # Check if a task is already running this generator
                    task_exists = any(
                        task.get_name() == f"sync_{generator_id}" and not task.done()
                        for task in self._running_tasks
                    )
                    if not task_exists:
                        task = asyncio.create_task(
                            self._run_generator(generator_id, generator_func),
                            name=f"sync_{generator_id}",
                        )
                        self._running_tasks.append(task)

            # Check for newly added async generators
            for generator_id, async_generator_func in async_generators_snapshot:
                if generator_id not in processed_generators_snapshot:
                    # Check if a task is already running this generator
                    task_exists = any(
                        task.get_name() == f"async_{generator_id}" and not task.done()
                        for task in self._running_tasks
                    )
                    if not task_exists:
                        task = asyncio.create_task(
                            self._run_async_generator(
                                generator_id, async_generator_func
                            ),
                            name=f"async_{generator_id}",
                        )
                        self._running_tasks.append(task)

            # Check if all generators have been processed and no active tasks
            async with self._lock:
                all_generators = set(self._generators.keys()) | set(
                    self._async_generators.keys()
                )
                all_done = self._active_count == 0 and all_generators.issubset(
                    self._processed_generators
                )

            if all_done:
                # Re-check for newly added generators (avoid race condition)
                await asyncio.sleep(0)  # Yield control to allow other tasks to run
                async with self._lock:
                    all_generators = set(self._generators.keys()) | set(
                        self._async_generators.keys()
                    )
                    if self._active_count == 0 and all_generators.issubset(
                        self._processed_generators
                    ):
                        break

            # Get value from queue (with timeout to avoid infinite wait while allowing new generator checks)
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=0.01)
            except asyncio.TimeoutError:
                # Continue checking for new generators after timeout
                continue

            # Check for special markers
            if isinstance(item, tuple):
                if item[0] == "__error__":
                    raise item[1]
                elif item[0] == "__event__":
                    # If it's an event, yield the event object
                    yield item[1]
                    continue

            yield item

        # Wait for all tasks to complete
        await asyncio.gather(*self._running_tasks, return_exceptions=True)

    async def __aiter__(self):
        """Allow the merger to be used as an async iterator."""
        async for item in self.merge():
            yield item


async def example_usage():
    """Example usage - demonstrates generator completion events and deletion functionality."""
    print("=" * 60)
    print("Example 1: Using callback")
    print("=" * 60)

    # Define callback
    async def on_complete(
        generator_id: str, generator_type: str, error: Optional[Exception]
    ):
        if error:
            print(
                f"  [CALLBACK] Generator {generator_id} ({generator_type}) completed with error: {error}"
            )
        else:
            print(f"  [CALLBACK] Generator {generator_id} ({generator_type}) completed")

    # Create merger with callback
    merger = GeneratorMerger(on_generator_complete=on_complete)

    def generator1():
        for i in range(1, 5):
            yield f"sync-gen1-{i}"

    async def async_generator1():
        for i in range(20, 25):
            await asyncio.sleep(0.01)
            yield f"async-gen1-{i}"

    def generator2():
        for i in range(1, 5):
            yield f"sync-gen2-{i}"

    async def async_generator2():
        for i in range(40, 45):
            await asyncio.sleep(0.01)
            yield f"async-gen2-{i}"

    # Add generators
    merger.add_generator(generator1, generator_id="gen1")
    merger.add_async_generator(async_generator1, generator_id="async_gen1")
    merger.add_generator(generator2, generator_id="gen2")
    merger.add_async_generator(async_generator2, generator_id="async_gen2")

    print("Merged generator output:")
    async for item in merger:
        if isinstance(item, dict) and item.get("type") == "generator_complete":
            # If callback exists, events won't be yielded, so this won't execute
            print(f"  Event: {item}")
        else:
            print(f"  Data: {item}")

    print("\n" + "=" * 60)
    print("Example 2: Dynamic addition and deletion of generators")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(example_usage())
