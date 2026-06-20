"""PreMortem — an AP autopilot that tries to prove its own plan wrong before it pays.

Public surface kept small on purpose; import submodules directly for internals.
"""
from .types import (
    PaymentPlan,
    FailureMode,
    Probe,
    ProbeResult,
    Verdict,
    Decision,
    FailureOutcome,
    Reversibility,
    VerdictDecision,
)

__all__ = [
    "PaymentPlan",
    "FailureMode",
    "Probe",
    "ProbeResult",
    "Verdict",
    "Decision",
    "FailureOutcome",
    "Reversibility",
    "VerdictDecision",
]

__version__ = "0.1.0"
