"""MockAdapter — deterministic, creds-free QwenClient for tests and the offline demo.

It does NOT call any network. It produces stable, scenario-shaped responses so the
full pre-mortem loop (enumerate -> falsify -> decide -> learn) runs and can be unit
tested without a DashScope key. Determinism is keyed off the prompt text, so the same
input always yields the same output (important for replayable demos and CI).

Design intent (design §4): real and mock adapters are interchangeable behind
QwenClient; only `build_client` chooses between them via PREMORTEM_LLM.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ..config import Config
from .base import QwenClient, SampleSet

# What each demo invoice image "shows", as a sidecar next to the (binary) PNG it stands for.
# The mock reads THIS rather than decoding pixels, so flipping a fixture flips the verdict —
# the document drives the decision, not a branch on the filename. The real DashScopeAdapter
# decodes the actual image; the engine logic in between is byte-identical (design §4).
_VISION_FIXTURE_DIR = Path(__file__).resolve().parents[1] / "data" / "vision_fixtures"


def _seed(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16)


def _load_vision_fixture(image_ref: str) -> dict | None:
    """The mock's 'read' of an invoice image: load the sidecar that records what the VL model
    would extract from `image_ref`. Returns None when no fixture exists for this image — the
    caller then reports an empty read, which makes image_consistency unfalsifiable -> escalate
    (never a silent clean pass). Keyed off the image basename so refs and paths both resolve."""
    name = Path(image_ref).name
    path = _VISION_FIXTURE_DIR / f"{name}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


class MockAdapter(QwenClient):
    def __init__(self, config: Config | None = None):
        self.config = config
        self.calls: list[tuple[str, str]] = []  # (kind, prompt) for test introspection

    # --- text reasoning -------------------------------------------------
    def complete(self, prompt: str, *, system: str | None = None,
                 temperature: float = 0.2) -> str:
        self.calls.append(("complete", prompt))
        # The enumerate prompt asks for ADDITIONAL failure modes as a JSON array.
        if "ADDITIONAL_FAILURE_MODES" in prompt:
            return self._enumerate_extra(prompt)
        # The reversibility helper asks for one token.
        if "CLASSIFY_REVERSIBILITY" in prompt:
            return self._classify_reversibility(prompt)
        return "ok"

    def complete_samples(self, prompt: str, *, n: int = 5, system: str | None = None,
                         temperature: float = 0.7) -> SampleSet:
        self.calls.append(("complete_samples", prompt))
        base = self.complete(prompt, system=system, temperature=0.0)
        # Self-agreement shaped by a REAL under-determination signal, not a magic word: the
        # engine tags the enumeration prompt with `large_amount` when the payment is far outside
        # the vendor's historical distribution (premortem.py `_llm_extra_modes`). An out-of-
        # distribution payment is exactly where a reasoning model's risk enumeration gets shaky,
        # so the mock emits mostly *distinct* dissents -> modal agreement 0.4 < the 0.6 escalate
        # floor at n=5, exercising the "enumeration unstable -> ESCALATE" path. The modal sample
        # stays `base` (JSON-parseable) so content extraction still works. In-distribution
        # payments converge -> unanimous. (Tests can still force dissent plan-independently by
        # subclassing, see tests/test_self_consistency.py `_DissentAdapter`.)
        if "large_amount" in prompt:
            samples = [base, base] + [f"dissent-{i}" for i in range(n - 2)]
        else:
            samples = [base] * n
        return SampleSet(samples=samples[:n])

    # --- vision ---------------------------------------------------------
    def vision(self, prompt: str, image_ref: str, *, temperature: float = 0.0) -> str:
        self.calls.append(("vision", image_ref))
        # The mock "reads" the invoice by loading the sidecar fixture that records what the VL
        # model would extract from THIS image (not a branch on the filename). Flip the fixture's
        # iban_on_doc and the same engine flips PROCEED<->BLOCK — the document drives the verdict.
        facts = _load_vision_fixture(image_ref)
        if facts is None:
            # No fixture for this image -> the mock saw nothing legible. An empty read leaves
            # image_consistency unfalsifiable, so the engine escalates rather than clearing it
            # on a guess (invariant I5) — never a silent clean pass.
            return json.dumps({})
        return json.dumps(facts, ensure_ascii=False)

    # --- canned reasoning bodies ---------------------------------------
    def _enumerate_extra(self, prompt: str) -> str:
        """Return 1-2 plausible extra modes, deterministically, as a JSON array.

        Mirrors what qwen-max would add on top of the memory+registry seed. Kept small
        and stable; the registry/memory seed carries the catastrophic modes so the demo
        does not depend on the LLM leg for safety (invariant I6)."""
        extra = [{
            "id": "currency_mismatch",
            "desc": "請求書通貨と支払指示通貨が一致しない",
            "probe": "",  # no cheap probe wired -> becomes unfalsifiable -> escalate (I5)
            "severity": "medium",
        }]
        # Add a second, falsifiable mode when the amount string is large.
        if "large_amount" in prompt:
            extra.append({
                "id": "amount_anomaly",
                "desc": "金額が当該ベンダーの履歴平均から大きく乖離",
                "probe": "amount_anomaly",
                "severity": "high",
            })
        return json.dumps(extra, ensure_ascii=False)

    def _classify_reversibility(self, prompt: str) -> str:
        p = prompt.lower()
        if "pay" in p or "wire" in p or "send money" in p or "送金" in prompt:
            return "irreversible"
        if "draft" in p or "preview" in p or "read" in p:
            return "reversible"
        return "unknown"
