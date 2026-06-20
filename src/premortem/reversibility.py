"""ReversibilityClassifier — the two-regime gate (design §2 "決める").

Rule-first, LLM-assist. Rules cover the actions we know; anything thin-evidence falls to
UNKNOWN, which the policy treats as IRREVERSIBLE (invariant I5 — do not guess on the
safe side of money movement). The LLM is consulted only to break genuine ambiguity and
its answer is clamped: it can never downgrade an action the rules call irreversible.
"""
from __future__ import annotations

from .llm.base import QwenClient
from .types import Reversibility

# Verbs whose effect cannot be cheaply undone once executed.
_IRREVERSIBLE_VERBS = ("pay", "wire", "send_money", "送金", "transfer_funds", "remit", "settle")
# Verbs that produce only drafts/reads — safe to run immediately under EV-max.
_REVERSIBLE_VERBS = ("draft", "preview", "read", "simulate", "validate", "lookup", "list")


class ReversibilityClassifier:
    def __init__(self, llm: QwenClient | None = None):
        self.llm = llm

    def classify(self, action: str) -> Reversibility:
        a = action.lower()
        if any(v in a for v in _IRREVERSIBLE_VERBS):
            return Reversibility.IRREVERSIBLE
        if any(v in a for v in _REVERSIBLE_VERBS):
            return Reversibility.REVERSIBLE
        # Ambiguous: ask the LLM, but never let it downgrade below UNKNOWN's safe default.
        if self.llm is not None:
            ans = self.llm.complete(
                f"CLASSIFY_REVERSIBILITY: is the action '{action}' reversible, "
                f"irreversible, or unknown? Answer one word.",
            ).strip().lower()
            if "irreversible" in ans:
                return Reversibility.IRREVERSIBLE
            if "reversible" in ans:
                return Reversibility.REVERSIBLE
        return Reversibility.UNKNOWN
