# context.py

import logging
import os
from datetime import datetime
from pathlib import Path

from pythonjsonlogger import jsonlogger

from cortex.server.log.trace import TraceIdFilter


def setup_logging(log_dir: str = "./logs", log_level: int = logging.WARNING):
    """
    Configure logging system to output to both console and file.

    Args:
        log_dir: Log file directory, defaults to ./logs
        log_level: Log level, defaults to INFO
    """
    # Use rename_fields parameter to alias field names
    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(levelname)s %(trace_id)s %(name)s %(message)s",
        rename_fields={
            "asctime": "time",  # Timestamp
            "levelname": "level",  # Log level
            "trace_id": "traceid",  # Trace ID (camelCase)
            "name": "name",  # Logger name
            "message": "msg",  # Log message
        },
    )

    # Set StreamHandler encoding to UTF-8 for proper Unicode handling
    import sys

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    stream_handler.addFilter(TraceIdFilter())

    handlers = [stream_handler]

    # Add file Handler
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    log_file = log_path / f"server_{datetime.now().strftime('%Y%m%d')}.log"

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.addFilter(TraceIdFilter())
    handlers.append(file_handler)

    # Ensure basicConfig uses UTF-8 encoding
    logging.basicConfig(
        level=log_level,
        handlers=handlers,
        encoding="utf-8",  # Add UTF-8 encoding support
    )
