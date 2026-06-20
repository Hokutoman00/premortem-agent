"""Core data types — the layer-boundary contracts from design.md §3.

These are intentionally plain dataclasses (not behaviour) so every layer hands the
next a typed, inspectable value. The example data in design.md §3 is reproduced in
tests/conftest.py as fixtures.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


class Reversibility(str, Enum):
    """How recoverable an action is. UNKNOWN is treated as IRREVERSIBLE (invariant I5)."""

    REVERSIBLE = "reversible"
    IRREVERSIBLE = "irreversible"
    UNKNOWN = "unknown"


class VerdictDecision(str, Enum):
    PROCEED = "PROCEED"   # tried to break the plan, could not -> safe to act
    BLOCK = "BLOCK"       # a failure mode was confirmed -> stop + escalate
    ESCALATE = "ESCALATE" # a failure mode could not be cheaply falsified -> human (I5)


class Severity(str, Enum):
    CATASTROPHIC = "catastrophic"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True)
class PaymentPlan:
    """Front stage -> middle stage. A structured intent to move money.

    `source_image_facts` carries values the vision model read *off the invoice image*
    so probes can cross-check the image against external records (design §2 "反証").
    """

    invoice_id: str
    vendor_name: str
    vendor_id: str
    amount: float
    currency: str
    bank: dict[str, str]
    action: str = "pay_invoice"
    source_image_facts: dict[str, str] = field(default_factory=dict)

    def fingerprint(self) -> str:
        """Stable key for failure-memory lookup (vendor + verb + rounded amount)."""
        return f"{self.vendor_id}:{self.action}:{int(round(self.amount))}"


@dataclass(frozen=True)
class FailureMode:
    """A concrete way the action could be wrong. Produced by enumerate_failure_modes."""

    id: str
    desc: str
    probe: str                       # name of the probe that would expose it, "" if none
    severity: Severity = Severity.HIGH
    seed_source: str = "llm"         # "memory" | "registry" | "llm"

    @property
    def falsifiable(self) -> bool:
        return bool(self.probe)


@dataclass(frozen=True)
class Probe:
    """A read-only test that makes a failure mode visible if it is real (invariant I2)."""

    name: str
    mode_id: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProbeResult:
    """Outcome of running one probe."""

    mode: str
    confirmed: bool          # True == the failure mode IS real -> dangerous
    evidence: str
    probe_ran: bool = True   # False == probe could not run (unfalsifiable)


@dataclass(frozen=True)
class Verdict:
    """Middle stage -> back stage. The falsification result for an action."""

    decision: VerdictDecision
    confirmed: list[ProbeResult] = field(default_factory=list)
    attempted: int = 0
    # mode ids whose unfalsifiability forced ESCALATE (catastrophic or memory-grounded)
    unfalsifiable: list[str] = field(default_factory=list)
    cleared: list[str] = field(default_factory=list)   # modes a probe actively ruled out
    residual: list[str] = field(default_factory=list)  # non-blocking risks surfaced to human
    notes: str = ""

    @property
    def safe(self) -> bool:
        return self.decision == VerdictDecision.PROCEED


@dataclass(frozen=True)
class Decision:
    """Final policy output for an action."""

    action: str
    executed: bool
    reversibility: Reversibility
    verdict: Verdict | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["reversibility"] = self.reversibility.value
        if self.verdict is not None:
            d["verdict"] = {
                "decision": self.verdict.decision.value,
                "attempted": self.verdict.attempted,
                "confirmed": [asdict(c) for c in self.verdict.confirmed],
                "unfalsifiable": self.verdict.unfalsifiable,
                "cleared": self.verdict.cleared,
                "residual": self.verdict.residual,
                "notes": self.verdict.notes,
            }
        return d


@dataclass(frozen=True)
class FailureOutcome:
    """Back stage -> failure-memory. Append-only learning record (invariant I4)."""

    action_fp: str
    failure_mode: str
    evidence: str
    label: str               # "confirmed_fraud" | "human_override" | "false_positive" | ...
    source: str = "engine"   # "engine" | "human_override" | "post_hoc"
