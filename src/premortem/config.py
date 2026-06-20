"""Runtime configuration. Reads .env once; safe defaults make mock mode zero-config."""
from __future__ import annotations

import os
from dataclasses import dataclass

try:  # optional dependency; mock mode does not need it
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv is convenience only
    pass


@dataclass(frozen=True)
class Config:
    provider: str
    dashscope_api_key: str
    dashscope_base_url: str
    reasoning_model: str
    vision_model: str
    self_consistency_n: int
    memory_db: str

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            provider=os.getenv("PREMORTEM_LLM", "mock").strip().lower(),
            dashscope_api_key=os.getenv("DASHSCOPE_API_KEY", ""),
            dashscope_base_url=os.getenv(
                "DASHSCOPE_BASE_URL",
                "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            ),
            reasoning_model=os.getenv("PREMORTEM_REASONING_MODEL", "qwen-max"),
            vision_model=os.getenv("PREMORTEM_VISION_MODEL", "qwen-vl-max"),
            self_consistency_n=int(os.getenv("PREMORTEM_SELF_CONSISTENCY_N", "5")),
            memory_db=os.getenv("PREMORTEM_MEMORY_DB", "premortem_memory.sqlite3"),
        )


CONFIG = Config.from_env()
