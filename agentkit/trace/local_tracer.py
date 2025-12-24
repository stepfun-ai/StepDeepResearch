import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from .span import Event, Span
from .tracer import Tracer


class LocalStorageTracer(Tracer):
    def __init__(self, storage_dir: str = "./traces"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.spans_dir = self.storage_dir / "spans"
        self.events_dir = self.storage_dir / "events"
        self.spans_dir.mkdir(exist_ok=True)
        self.events_dir.mkdir(exist_ok=True)

    def _get_trace_spans_file(self, trace_id: str) -> Path:
        return self.spans_dir / f"{trace_id}.jsonl"

    def _get_trace_events_file(self, trace_id: str) -> Path:
        return self.events_dir / f"{trace_id}.jsonl"

    def record_span(self, span: Span) -> None:
        spans_file = self._get_trace_spans_file(span.trace_id)
        with open(spans_file, "a", encoding="utf-8") as f:
            span_data = span.model_dump_json(exclude_none=True, ensure_ascii=False)
            f.write(span_data + "\n")

    def record_event(self, event: Event) -> None:
        events_file = self._get_trace_events_file(event.trace_id)
        with open(events_file, "a", encoding="utf-8") as f:
            event_data = event.model_dump_json(exclude_none=True, ensure_ascii=False)
            f.write(event_data + "\n")

    def get_spans(self, trace_id: str) -> list[Span]:
        spans_file = self._get_trace_spans_file(trace_id)
        if not spans_file.exists():
            return []

        spans = []
        with open(spans_file, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                if line.strip():
                    try:
                        span_data = json.loads(line)
                        spans.append(Span(**span_data))
                    except Exception as e:
                        # Log error but continue processing other lines
                        print(
                            f"Warning: Failed to parse span at line {line_num} in {spans_file}: {e}"
                        )
                        continue
        return spans

    def get_events(self, trace_id: str) -> list[Event]:
        events_file = self._get_trace_events_file(trace_id)
        if not events_file.exists():
            return []

        events = []
        with open(events_file, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                if line.strip():
                    try:
                        event_data = json.loads(line)
                        events.append(Event(**event_data))
                    except Exception as e:
                        # Log error but continue processing other lines
                        print(
                            f"Warning: Failed to parse event at line {line_num} in {events_file}: {e}"
                        )
                        continue
        return events

    def get_trace(self, trace_id: str) -> Optional[dict]:
        spans = self.get_spans(trace_id)
        events = self.get_events(trace_id)

        if not spans and not events:
            return None

        return {
            "trace_id": trace_id,
            "spans": [span.model_dump(mode="json") for span in spans],
            "events": [event.model_dump(mode="json") for event in events],
            "span_count": len(spans),
            "event_count": len(events),
        }

    def get_trace_raw(self, trace_id: str) -> Optional[dict]:
        """
        Get raw trace data (without Pydantic model validation).
        Used for frontend display to avoid serialization/deserialization issues.
        """
        spans_file = self._get_trace_spans_file(trace_id)
        events_file = self._get_trace_events_file(trace_id)

        if not spans_file.exists() and not events_file.exists():
            return None

        spans = []
        events = []

        # Read spans (raw JSON)
        if spans_file.exists():
            with open(spans_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            span_data = json.loads(line)
                            spans.append(span_data)
                        except json.JSONDecodeError as e:
                            # Skip invalid line
                            print(f"Warning: Failed to parse span line: {e}")
                            continue

        # Read events (raw JSON)
        if events_file.exists():
            with open(events_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            event_data = json.loads(line)
                            events.append(event_data)
                        except json.JSONDecodeError as e:
                            # Skip invalid line
                            print(f"Warning: Failed to parse event line: {e}")
                            continue

        return {
            "trace_id": trace_id,
            "spans": spans,
            "events": events,
            "span_count": len(spans),
            "event_count": len(events),
        }

    def list_traces(self, limit: int = 100, offset: int = 0) -> list[dict]:
        trace_files = {}

        for spans_file in self.spans_dir.glob("*.jsonl"):
            trace_id = spans_file.stem
            trace_files[trace_id] = {
                "trace_id": trace_id,
                "spans_file": spans_file,
                "mtime": spans_file.stat().st_mtime,
            }

        for events_file in self.events_dir.glob("*.jsonl"):
            trace_id = events_file.stem
            if trace_id not in trace_files:
                trace_files[trace_id] = {
                    "trace_id": trace_id,
                    "events_file": events_file,
                    "mtime": events_file.stat().st_mtime,
                }
            else:
                trace_files[trace_id]["events_file"] = events_file
                trace_files[trace_id]["mtime"] = max(
                    trace_files[trace_id]["mtime"], events_file.stat().st_mtime
                )

        sorted_traces = sorted(
            trace_files.values(), key=lambda x: x["mtime"], reverse=True
        )

        traces = []
        for trace_info in sorted_traces[offset : offset + limit]:
            trace_id = trace_info["trace_id"]
            spans = self.get_spans(trace_id)
            events = self.get_events(trace_id)

            traces.append(
                {
                    "trace_id": trace_id,
                    "span_count": len(spans),
                    "event_count": len(events),
                    "last_modified": datetime.fromtimestamp(trace_info["mtime"]),
                }
            )

        return traces
