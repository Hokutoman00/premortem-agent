"""QwenClient — the interface every layer talks to instead of a vendor SDK.

Why an interface (design §4, invariant I6): the two LLM legs (text + vision) share
weights and therefore fail in correlated ways. Pinning them behind one small contract
lets the engine (a) run creds-free on a deterministic MockAdapter for tests/demo and
(b) anchor its final verdict on the *non-LLM* probe leg, treating these calls as a
prior, not an oracle.

Note on uncertainty: DashScope/Qwen does NOT expose logprobs. So `complete_samples`
exists to recover a cheap uncertainty signal at the application layer via
self-consistency (sample N, measure agreement) rather than token probabilities.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class SampleSet:
    """Result of self-consistency sampling."""

    samples: list[str]

    @property
    def n(self) -> int:
        return len(self.samples)

    def agreement(self) -> float:
        """Fraction of samples equal to the modal sample. 1.0 == unanimous."""
        if not self.samples:
            return 0.0
        norm = [s.strip().lower() for s in self.samples]
        modal = max(set(norm), key=norm.count)
        return norm.count(modal) / len(norm)

    def modal(self) -> str:
        if not self.samples:
            return ""
        norm = [s.strip() for s in self.samples]
        return max(set(norm), key=norm.count)


class QwenClient(ABC):
    """Minimal surface over Qwen Cloud (DashScope)."""

    @abstractmethod
    def complete(self, prompt: str, *, system: str | None = None,
                 temperature: float = 0.2) -> str:
        """Single text completion (qwen-max reasoning)."""

    @abstractmethod
    def complete_samples(self, prompt: str, *, n: int = 5, system: str | None = None,
                         temperature: float = 0.7) -> SampleSet:
        """N text completions for self-consistency (logprob substitute)."""

    @abstractmethod
    def vision(self, prompt: str, image_ref: str, *,
               temperature: float = 0.0) -> str:
        """Read an invoice image (qwen-vl-max / MultiModalConversation).

        `image_ref` is a path or URL. Returns the model's reading as text/JSON.
        """
