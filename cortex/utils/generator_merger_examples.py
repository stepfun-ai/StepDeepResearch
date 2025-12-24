"""GeneratorMerger usage examples collection."""

import asyncio
import time

from .generator_merger import GeneratorMerger


async def example_1_basic_usage():
    """Example 1: Basic usage - merging multiple simple generators."""
    print("=" * 60)
    print("Example 1: Basic Usage")
    print("=" * 60)

    merger = GeneratorMerger()

    def number_generator(start: int, end: int, prefix: str):
        """Generator that produces number sequences."""
        for i in range(start, end):
            yield f"{prefix}-{i}"

    # Add multiple generators
    merger.add_generator(lambda: number_generator(1, 4, "A"))
    merger.add_generator(lambda: number_generator(10, 13, "B"))
    merger.add_generator(lambda: number_generator(20, 23, "C"))

    print("Merged output (order may vary due to concurrent execution):")
    async for item in merger:
        print(f"  Received: {item}")

    print()


async def example_2_dynamic_addition():
    """Example 2: Dynamic generator addition - adding new generators during iteration."""
    print("=" * 60)
    print("Example 2: Dynamic Generator Addition")
    print("=" * 60)

    merger = GeneratorMerger()

    def slow_generator(name: str, count: int, delay: float):
        """Generator with delay, simulating slow data source."""
        for i in range(count):
            time.sleep(delay)  # Simulate I/O operation
            yield f"{name}-{i}"

    # Initially add two generators
    merger.add_generator(lambda: slow_generator("Fast", 3, 0.1))
    merger.add_generator(lambda: slow_generator("Medium", 3, 0.15))

    print("Starting iteration, will dynamically add new generator later...")
    count = 0
    async for item in merger:
        print(f"  Received: {item}")
        count += 1

        # Dynamically add new generator during iteration
        if count == 3:
            print("  Dynamically adding new generator...")
            merger.add_generator(lambda: slow_generator("Slow", 3, 0.2))

    print()


async def example_3_different_data_types():
    """Example 3: Handling different data types."""
    print("=" * 60)
    print("Example 3: Handling Different Data Types")
    print("=" * 60)

    merger = GeneratorMerger()

    def string_generator():
        """Generate strings."""
        for s in ["hello", "world", "python"]:
            yield s

    def number_generator():
        """Generate numbers."""
        for n in [1, 2, 3, 4, 5]:
            yield n

    def dict_generator():
        """Generate dictionaries."""
        for i in range(3):
            yield {"id": i, "name": f"item_{i}", "value": i * 10}

    merger.add_generator(string_generator)
    merger.add_generator(number_generator)
    merger.add_generator(dict_generator)

    print("Merging different data types:")
    async for item in merger:
        print(f"  Type: {type(item).__name__}, Value: {item}")

    print()


async def example_4_data_streams():
    """Example 4: Simulating multiple data stream scenarios."""
    print("=" * 60)
    print("Example 4: Simulating Multiple Data Stream Scenarios")
    print("=" * 60)

    merger = GeneratorMerger()

    def log_stream(source: str):
        """Simulate log stream."""
        for i in range(5):
            time.sleep(0.05)
            yield {"source": source, "level": "INFO", "message": f"Log entry {i}"}

    def metric_stream(metric_name: str):
        """Simulate metric stream."""
        for i in range(4):
            time.sleep(0.08)
            yield {"metric": metric_name, "value": i * 10, "timestamp": time.time()}

    def event_stream(event_type: str):
        """Simulate event stream."""
        for i in range(3):
            time.sleep(0.06)
            yield {"event": event_type, "id": i, "data": f"event_data_{i}"}

    # Add multiple data streams
    merger.add_generator(lambda: log_stream("server1"))
    merger.add_generator(lambda: log_stream("server2"))
    merger.add_generator(lambda: metric_stream("cpu_usage"))
    merger.add_generator(lambda: metric_stream("memory_usage"))
    merger.add_generator(lambda: event_stream("user_action"))

    print("Merging multiple data streams (real-time output):")
    async for item in merger:
        if "source" in item:
            print(f"  [LOG] {item['source']}: {item['message']}")
        elif "metric" in item:
            print(f"  [METRIC] {item['metric']}: {item['value']}")
        elif "event" in item:
            print(f"  [EVENT] {item['event']}: {item['data']}")

    print()


async def example_5_file_processing():
    """Example 5: Simulating file processing scenario - merging content from multiple files."""
    print("=" * 60)
    print("Example 5: Simulating File Processing Scenario")
    print("=" * 60)

    merger = GeneratorMerger()

    def file_reader(filename: str, lines: list[str]):
        """Simulate file reader."""
        for line_num, line in enumerate(lines, 1):
            time.sleep(0.02)  # Simulate read delay
            yield {"file": filename, "line": line_num, "content": line}

    # Simulate content of three files
    file1_content = ["Line 1", "Line 2", "Line 3"]
    file2_content = ["A", "B", "C", "D"]
    file3_content = ["Data 1", "Data 2"]

    merger.add_generator(lambda: file_reader("file1.txt", file1_content))
    merger.add_generator(lambda: file_reader("file2.txt", file2_content))
    merger.add_generator(lambda: file_reader("file3.txt", file3_content))

    print("Merging and processing multiple files:")
    async for item in merger:
        print(f"  [{item['file']}] Line {item['line']}: {item['content']}")

    print()


async def example_6_batch_processing():
    """Example 6: Batch processing scenario - merging results from multiple tasks."""
    print("=" * 60)
    print("Example 6: Batch Processing Scenario")
    print("=" * 60)

    merger = GeneratorMerger()

    def task_processor(task_id: int, items: list[str]):
        """Simulate task processor."""
        for item in items:
            time.sleep(0.03)  # Simulate processing time
            yield {
                "task_id": task_id,
                "item": item,
                "status": "processed",
                "result": f"result_{item}",
            }

    # Add multiple tasks
    merger.add_generator(lambda: task_processor(1, ["item1", "item2", "item3"]))
    merger.add_generator(lambda: task_processor(2, ["itemA", "itemB"]))
    merger.add_generator(
        lambda: task_processor(3, ["data1", "data2", "data3", "data4"])
    )

    print("Concurrently processing multiple tasks:")
    results = []
    async for item in merger:
        results.append(item)
        print(f"  Task {item['task_id']} completed: {item['item']} -> {item['result']}")

    print(f"\nTotal processed: {len(results)} items")
    print()


async def example_7_error_handling():
    """Example 7: Error handling - demonstrating behavior when generator errors occur."""
    print("=" * 60)
    print("Example 7: Error Handling")
    print("=" * 60)

    merger = GeneratorMerger()

    def normal_generator():
        """Normal generator."""
        for i in range(3):
            yield f"normal-{i}"

    def error_generator():
        """Generator that will error."""
        yield "error-1"
        yield "error-2"
        raise ValueError("Simulated error")

    def another_normal_generator():
        """Another normal generator."""
        for i in range(2):
            yield f"another-{i}"

    merger.add_generator(normal_generator)
    merger.add_generator(error_generator)
    merger.add_generator(another_normal_generator)

    print("Processing generators with errors:")
    try:
        async for item in merger:
            print(f"  Received: {item}")
    except ValueError as e:
        print(f"  Caught error: {e}")

    print()


async def example_8_callback_usage():
    """Example 8: Using callback to monitor generator completion events."""
    print("=" * 60)
    print("Example 8: Using Callback to Monitor Generator Completion Events")
    print("=" * 60)

    # Track completed generators
    completed_generators = []

    # Define callback function
    async def on_generator_complete(
        generator_id: str, generator_type: str, error: Exception | None
    ):
        """Called when generator completes."""
        status = "Success" if error is None else f"Failed: {error}"
        completed_generators.append(
            {"id": generator_id, "type": generator_type, "status": status}
        )
        print(
            f"  [CALLBACK] Generator '{generator_id}' ({generator_type}) completed: {status}"
        )

    # Create merger with callback
    merger = GeneratorMerger(on_generator_complete=on_generator_complete)

    def fast_generator():
        """Fast completing generator."""
        for i in range(1, 4):
            yield f"fast-{i}"

    def slow_generator():
        """Slow completing generator."""
        for i in range(10, 13):
            time.sleep(0.05)  # Simulate slow operation
            yield f"slow-{i}"

    async def async_generator():
        """Async generator."""
        for i in range(20, 23):
            await asyncio.sleep(0.03)
            yield f"async-{i}"

    def error_generator():
        """Generator that will error."""
        yield "error-1"
        yield "error-2"
        raise ValueError("Test error")

    # Add generators with generator_id specified
    merger.add_generator(fast_generator, generator_id="fast_gen")
    merger.add_generator(slow_generator, generator_id="slow_gen")
    merger.add_async_generator(async_generator, generator_id="async_gen")
    merger.add_generator(error_generator, generator_id="error_gen")

    print("Starting generator processing (callback will be called on completion):")
    print()

    try:
        async for item in merger:
            # Note: If there's a callback, completion events won't be yielded, only callback is called
            print(f"  [DATA] Received data: {item}")
    except ValueError as e:
        print(f"  [ERROR] Caught error: {e}")

    print()
    print("Completed generators statistics:")
    for gen_info in completed_generators:
        print(f"  - {gen_info['id']} ({gen_info['type']}): {gen_info['status']}")

    print()


async def example_9_callback_vs_event():
    """Example 9: Comparing callback vs event yield differences."""
    print("=" * 60)
    print("Example 9: Comparing Callback vs Event Yield Differences")
    print("=" * 60)

    def simple_generator(name: str):
        """Simple generator."""
        for i in range(1, 3):
            yield f"{name}-{i}"

    print("Method 1: Using callback (events won't appear in iteration)")
    print("-" * 60)

    async def callback(
        generator_id: str, _generator_type: str, _error: Exception | None
    ):
        print(f"    [CALLBACK] {generator_id} completed")

    merger1 = GeneratorMerger(on_generator_complete=callback)
    merger1.add_generator(lambda: simple_generator("A"), generator_id="gen_A")
    merger1.add_generator(lambda: simple_generator("B"), generator_id="gen_B")

    print("    Iteration output:")
    async for item in merger1:
        print(f"      {item}")

    print()
    print("Method 2: Without callback (events will be yielded)")
    print("-" * 60)

    merger2 = GeneratorMerger()
    merger2.add_generator(lambda: simple_generator("X"), generator_id="gen_X")
    merger2.add_generator(lambda: simple_generator("Y"), generator_id="gen_Y")

    print("    Iteration output (includes completion events):")
    async for item in merger2:
        if isinstance(item, dict) and item.get("type") == "generator_complete":
            print(
                f"      [EVENT] {item['generator_id']} ({item['generator_type']}) "
                f"Status: {item['status']}"
            )
        else:
            print(f"      [DATA] {item}")

    print()


async def run_all_examples():
    """Run all examples."""
    examples = [
        example_1_basic_usage,
        example_2_dynamic_addition,
        example_3_different_data_types,
        example_4_data_streams,
        example_5_file_processing,
        example_6_batch_processing,
        example_7_error_handling,
        example_8_callback_usage,
        example_9_callback_vs_event,
    ]

    for example in examples:
        try:
            await example()
            await asyncio.sleep(0.5)  # Interval between examples
        except Exception as e:
            print(f"Example execution error: {e}\n")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("GeneratorMerger Usage Examples")
    print("=" * 60 + "\n")

    # Run all examples
    asyncio.run(run_all_examples())

    print("=" * 60)
    print("All examples completed!")
    print("=" * 60)
