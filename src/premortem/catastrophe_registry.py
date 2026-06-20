"""CatastropheRegistry — static cold-start seed of known AP failure archetypes.

Why it exists (design §6 cold-start, AMPLIFY red-team v8): on day 1 the failure-memory
is empty, so the engine cannot learn its way to safety. The registry guarantees a floor
of catastrophic modes that are *always* enumerated, independent of the LLM's imagination
(invariant I6 — do not let the model's blind spots define the safety surface).
"""
from __future__ import annotations

import json
from importlib import resources

from .types import FailureMode, Severity

_SEVERITY = {s.value: s for s in Severity}


def _load() -> list[FailureMode]:
    raw = json.loads(
        resources.files("premortem.data").joinpath("catastrophe_registry.json").read_text("utf-8")
    )
    modes = []
    for m in raw["modes"]:
        modes.append(FailureMode(
            id=m["id"],
            desc=m["desc"],
            probe=m.get("probe", ""),
            severity=_SEVERITY.get(m.get("severity", "high"), Severity.HIGH),
            seed_source="registry",
        ))
    return modes


class CatastropheRegistry:
    def __init__(self, modes: list[FailureMode] | None = None):
        self._modes = modes if modes is not None else _load()

    def modes(self) -> list[FailureMode]:
        return list(self._modes)

    def __len__(self) -> int:
        return len(self._modes)
