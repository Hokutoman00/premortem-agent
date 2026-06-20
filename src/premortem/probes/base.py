"""Probe protocol. A probe is a pure, read-only function that tries to CONFIRM a
failure mode against ground truth (invariant I2: no side effects).

confirmed == True means "the failure mode is real" -> dangerous -> the engine BLOCKs.
A probe that cannot run for an input returns probe_ran=False -> the mode is treated as
unfalsifiable -> escalate (invariant I5).
"""
from __future__ import annotations

from typing import Callable

from ..data.demo_data import DemoDataStore
from ..types import PaymentPlan, ProbeResult

# A probe: (plan, store) -> ProbeResult
ProbeFn = Callable[[PaymentPlan, DemoDataStore], ProbeResult]
