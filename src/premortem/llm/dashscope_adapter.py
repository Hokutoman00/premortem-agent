"""DashScopeAdapter — the real Qwen Cloud client (qwen-max + qwen-vl-max).

Only imported when PREMORTEM_LLM=dashscope. Uses the OpenAI-
compatible endpoint for text and DashScope's MultiModalConversation for vision, both
per Qwen Cloud docs. Kept deliberately thin: same QwenClient surface as MockAdapter so
the engine code is identical in demo and production (design §4).

This file performs NO calls at import time; constructing it only validates that a key
is present. Network calls happen lazily inside the methods.
"""
from __future__ import annotations

import json

from ..config import Config
from .base import QwenClient, SampleSet


class DashScopeAdapter(QwenClient):
    def __init__(self, config: Config):
        if not config.dashscope_api_key:
            raise RuntimeError(
                "PREMORTEM_LLM=dashscope but DASHSCOPE_API_KEY is empty. "
                "Set it in .env (see ~/.credentials/ convention) or use mock mode."
            )
        self.config = config
        self._text_client = None  # lazy OpenAI-compatible client

    # --- lazy clients ---------------------------------------------------
    def _text(self):
        if self._text_client is None:
            from openai import OpenAI  # provided by the [dashscope] extra

            self._text_client = OpenAI(
                api_key=self.config.dashscope_api_key,
                base_url=self.config.dashscope_base_url,
            )
        return self._text_client

    # --- text reasoning -------------------------------------------------
    def complete(self, prompt: str, *, system: str | None = None,
                 temperature: float = 0.2) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = self._text().chat.completions.create(
            model=self.config.reasoning_model,
            messages=messages,
            temperature=temperature,
        )
        return (resp.choices[0].message.content or "").strip()

    def complete_samples(self, prompt: str, *, n: int = 5, system: str | None = None,
                         temperature: float = 0.7) -> SampleSet:
        # No logprobs on Qwen Cloud -> recover uncertainty by sampling N times.
        samples = [
            self.complete(prompt, system=system, temperature=temperature)
            for _ in range(max(1, n))
        ]
        return SampleSet(samples=samples)

    # --- vision ---------------------------------------------------------
    def vision(self, prompt: str, image_ref: str, *, temperature: float = 0.0) -> str:
        """Read an invoice via qwen-vl-max MultiModalConversation.

        image_ref may already be a URL/URI ("https://...", "file://...") or a local path. A
        bare or relative path is resolved to an absolute file:// URI via Path.as_uri(), which
        emits a well-formed URI on both POSIX (file:///app/...) and Windows (file:///C:/...) —
        string-concatenating "file://" + path would mangle a Windows drive path.
        """
        import dashscope
        from dashscope import MultiModalConversation
        from pathlib import Path

        dashscope.api_key = self.config.dashscope_api_key
        if "://" in image_ref:
            image_field = image_ref
        else:
            image_field = Path(image_ref).resolve().as_uri()
        messages = [{
            "role": "user",
            "content": [
                {"image": image_field},
                {"text": prompt},
            ],
        }]
        resp = MultiModalConversation.call(
            model=self.config.vision_model,
            messages=messages,
            # raise image token budget 1,280 -> 16,384 for dense invoices
            vl_high_resolution_images=True,
        )
        try:
            content = resp["output"]["choices"][0]["message"]["content"]
            if isinstance(content, list):
                texts = [c.get("text", "") for c in content if isinstance(c, dict)]
                return "\n".join(t for t in texts if t).strip()
            return str(content).strip()
        except (KeyError, IndexError, TypeError):
            return json.dumps({"error": "vision_parse_failed", "raw": str(resp)})
