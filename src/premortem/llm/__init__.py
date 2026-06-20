"""LLM provider abstraction. Pick an adapter by env (design §4)."""
from __future__ import annotations

from ..config import Config, CONFIG
from .base import QwenClient
from .mock_adapter import MockAdapter


def build_client(config: Config = CONFIG) -> QwenClient:
    """Return the configured QwenClient. Defaults to the creds-free mock."""
    if config.provider == "dashscope":
        # Imported lazily so the package works with zero extra deps in mock mode.
        from .dashscope_adapter import DashScopeAdapter

        return DashScopeAdapter(config)
    return MockAdapter(config)


__all__ = ["QwenClient", "MockAdapter", "build_client"]
