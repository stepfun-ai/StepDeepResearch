from dataclasses import dataclass

from .local_tracer import LocalStorageTracer
from .tracer import Tracer


@dataclass
class DefaultSettings:
    app_name: str = "default"
    tracer: Tracer = LocalStorageTracer(storage_dir="./traces")


_settings = DefaultSettings()


def set_default(**kwargs):
    for key, value in kwargs.items():
        if hasattr(_settings, key):
            setattr(_settings, key, value)
        else:
            raise ValueError(f"Unknown setting: {key}")


def get_default_settings() -> DefaultSettings:
    return _settings


def get_default(key: str):
    """Get a single default value."""
    return getattr(_settings, key)
