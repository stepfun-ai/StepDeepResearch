from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    import yaml
except Exception:  # noqa: BLE001
    yaml = None

_RUNTIME_CONFIG_CACHE: dict[str, Any] | None = None


def _repo_root() -> Path:
    # `cortex/` lives under the project root in this repo.
    return Path(__file__).resolve().parent.parent


def _pick_first_present(cfg: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in cfg:
            return cfg.get(key)
    return None


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(text)
        except Exception:  # noqa: BLE001
            return None
    return None


def load_runtime_config() -> dict[str, Any]:
    """Load runtime config from YAML, cached for process lifetime.

    Resolution order:
    1) `$STEP_DEEPRESEARCH_CONFIG` (if set)
    2) `<repo_root>/config.yaml` (if exists)
    """
    global _RUNTIME_CONFIG_CACHE  # noqa: PLW0603
    if _RUNTIME_CONFIG_CACHE is not None:
        return _RUNTIME_CONFIG_CACHE

    if yaml is None:
        _RUNTIME_CONFIG_CACHE = {}
        return _RUNTIME_CONFIG_CACHE

    env_path = (os.getenv("STEP_DEEPRESEARCH_CONFIG") or "").strip()
    candidates: list[Path] = []
    if env_path:
        candidates.append(Path(env_path))
    candidates.append(_repo_root() / "config.yaml")

    for path in candidates:
        try:
            if not path.exists() or not path.is_file():
                continue
            with path.open("r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f) or {}
            if isinstance(loaded, dict):
                _RUNTIME_CONFIG_CACHE = loaded
                return _RUNTIME_CONFIG_CACHE
        except Exception:  # noqa: BLE001
            continue

    _RUNTIME_CONFIG_CACHE = {}
    return _RUNTIME_CONFIG_CACHE


def get_context_limit_overrides() -> tuple[int | None, int | None]:
    """Return (upper, lower) context limit overrides from runtime config."""
    cfg = load_runtime_config()
    upper = _pick_first_present(
        cfg, ("context_upper_limit", "final_answer_context_upper_limit")
    )
    lower = _pick_first_present(
        cfg, ("context_lower_limit", "final_answer_context_lower_limit")
    )
    return _as_int(upper), _as_int(lower)

