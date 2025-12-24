"""
Utility functions for demo tools.
"""

import json
from typing import Any

from pydantic import BaseModel


def json_dumps(data: Any, indent: int = 2, ensure_ascii: bool = False) -> str:
    """
    Serialize data to JSON string with Pydantic model support.
    
    This is a thin wrapper around json.dumps that adds automatic serialization
    for Pydantic BaseModel instances. When encountering a Pydantic model, it
    calls model_dump() to convert it to a dict before JSON serialization.
    
    Args:
        data: The data to serialize. Can be any JSON-serializable type,
              including Pydantic models.
        indent: Number of spaces for indentation (default: 2).
        ensure_ascii: If False, allow non-ASCII characters in output (default: False).
    
    Returns:
        JSON string representation of the data.
    
    Raises:
        TypeError: If the data contains types that cannot be serialized.
    
    Example:
        >>> from pydantic import BaseModel
        >>> class User(BaseModel):
        ...     name: str
        ...     age: int
        >>> json_dumps({"user": User(name="Alice", age=30)})
        '{\\n  "user": {\\n    "name": "Alice",\\n    "age": 30\\n  }\\n}'
    """
    def default(obj: Any) -> Any:
        if isinstance(obj, BaseModel):
            return obj.model_dump()
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
    
    return json.dumps(data, indent=indent, ensure_ascii=ensure_ascii, default=default)
