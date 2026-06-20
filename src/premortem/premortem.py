"""PreMortemEngine — enumerate failure modes, try to confirm them, return a Verdict.

This is the middle stage from design.md §2. The whole product thesis lives here:
instead of acting when the model is confident, the engine actively tries to *prove its
own plan wrong* and acts only when it cannot. The failure-mode list is seeded from
exogenous experience (memory) and a fixed catastrophe registry first, with the LLM only
*adding* to that floor — so the model's blind spots cannot shrink the safety surface
(invariant I6).
"""
from __future__ import annotations

import json
from dataclasses import replace

from .catastrophe_registry import CatastropheRegistry
from .data.demo_data import DemoDataStore
from .llm.base import QwenClient
from .memory.failure_memory import FailureMemory
from .probes.registry import ProbeRegistry
from .types import (
    FailureMode,
    PaymentPlan,
    ProbeResult,
    Severity,
    Verdict,
    VerdictDecision,
)

_SEVERITY_ORDER = {
    Severity.CATASTROPHIC: 0, Severity.HIGH: 1, Severity.MEDIUM: 2, Severity.LOW: 3,
}


class PreMortemEngine:
    def __init__(
        self,
        llm: QwenClient,
        store: DemoDataStore,
        probes: ProbeRegistry,
        memory: FailureMemory,
        registry: CatastropheRegistry | None = None,
        block_threshold: Severity = Severity.HIGH,
        self_consistency_n: int = 5,
        escalate_agreement: float = 0.6,
    ):
        self.llm = llm
        self.store = store
        self.probes = probes
        self.memory = memory
        self.registry = registry or CatastropheRegistry()
        # A CONFIRMED mode at this severity or worse blocks; lighter confirms are residual.
        self.block_threshold = block_threshold
        # Self-consistency as a logprob substitute (design §4): the LLM enumeration leg is
        # sampled N times. If the reasoning model cannot agree with itself about an
        # irreversible payment's risk landscape (modal agreement below this floor), that
        # disagreement IS the uncertainty signal — we refuse a clean verdict and escalate.
        self.self_consistency_n = max(1, self_consistency_n)
        self.escalate_agreement = escalate_agreement

    # --- enumerate (design §2 "列挙する") ------------------------------
    def enumerate_failure_modes(self, plan: PaymentPlan) -> list[FailureMode]:
        seed: list[FailureMode] = []
        # (a) exogenous experience — modes that actually bit us before (primary)
        seed += self.memory.seed_modes_for(plan.fingerprint(), plan.vendor_id)
        # (b) fixed cold-start floor — known AP catastrophes (always present)
        seed += self.registry.modes()
        # (c) LLM augmentation — model ADDS to the floor, never replaces it
        seed += self._llm_extra_modes(plan)
        return self._wire_memory_probes(self._dedup(seed))

    def _wire_memory_probes(self, modes: list[FailureMode]) -> list[FailureMode]:
        """A memory-seeded mode stores its own id as the probe name, but the registry
        keys some probes differently (e.g. mode `new_payee_first_payment` -> probe
        `vendor_age`). Backfill the canonical probe so a remembered mode that IS probeable
        still gets falsified rather than auto-escalating. A remembered mode with no probe
        anywhere (e.g. `goods_not_received`) stays unwired -> escalate (the learning loop)."""
        reg_probe = {m.id: m.probe for m in self.registry.modes()}
        out: list[FailureMode] = []
        for m in modes:
            if (m.seed_source == "memory" and not self.probes.has(m.probe)
                    and self.probes.has(reg_probe.get(m.id, ""))):
                m = replace(m, probe=reg_probe[m.id])
            out.append(m)
        return out

    def _llm_extra_modes(self, plan: PaymentPlan) -> list[FailureMode]:
        stats = self.store.amount_stats(plan.vendor_id)
        hint = "large_amount" if (stats and plan.amount > stats[0] * 3) else ""
        prompt = (
            "ADDITIONAL_FAILURE_MODES: given this payment plan, list any further ways it "
            "could be wrong that are NOT already covered. Return a JSON array of objects "
            "with keys id, desc, probe, severity. "
            f"plan={{vendor:{plan.vendor_id}, amount:{plan.amount}, "
            f"currency:{plan.currency}}} {hint}"
        )
        # Self-consistency stands in for the logprobs Qwen Cloud does not expose (design §4):
        # sample the enumeration leg N times and read the agreement BEFORE trusting any one
        # answer. We anchor on the modal sample for the *content*, but the agreement fraction
        # is itself a safety signal.
        samples = self.llm.complete_samples(prompt, n=self.self_consistency_n)
        out: list[FailureMode] = []

        # Low self-agreement on an irreversible payment's risk landscape is an unfalsifiable
        # danger in its own right: the model cannot even stabilise *what could go wrong*, so a
        # clean PROCEED would be unearned. Inject a catastrophic, unprobeable mode -> the
        # existing falsify rule (catastrophic + unfalsifiable) escalates to a human (I5).
        if self.self_consistency_n > 1 and samples.agreement() < self.escalate_agreement:
            out.append(FailureMode(
                id="llm_enumeration_unstable",
                desc=(f"qwen-max disagreed with itself across {samples.n} samples "
                      f"(agreement {samples.agreement():.2f} < {self.escalate_agreement}); "
                      f"risk enumeration is not self-consistent"),
                probe="",  # unfalsifiable by construction -> escalates, never auto-clears
                severity=Severity.CATASTROPHIC,
                seed_source="llm",
            ))

        try:
            data = json.loads(samples.modal())
        except Exception:
            return out
        if isinstance(data, list):
            for m in data:
                if not isinstance(m, dict) or "id" not in m:
                    continue
                sev = m.get("severity", "medium")
                out.append(FailureMode(
                    id=str(m["id"]),
                    desc=str(m.get("desc", "")),
                    probe=str(m.get("probe", "")),
                    severity=_coerce_sev(sev),
                    seed_source="llm",
                ))
        return out

    @staticmethod
    def _dedup(modes: list[FailureMode]) -> list[FailureMode]:
        # Keep the highest-priority seed_source per id: memory > registry > llm, then
        # order by severity so the most dangerous modes are probed first.
        priority = {"memory": 0, "registry": 1, "llm": 2}
        best: dict[str, FailureMode] = {}
        for m in modes:
            cur = best.get(m.id)
            if cur is None or priority[m.seed_source] < priority[cur.seed_source]:
                best[m.id] = m
        return sorted(
            best.values(),
            key=lambda m: (_SEVERITY_ORDER[m.severity], priority[m.seed_source], m.id),
        )

    # --- falsify (design §2 "反証する") --------------------------------
    def falsify(self, plan: PaymentPlan, modes: list[FailureMode]) -> Verdict:
        """Severity-graded falsification.

        The verdict is anchored on what the probes could and could not rule out:
          - a CONFIRMED mode at/above block_threshold (default HIGH) -> BLOCK;
          - a mode we could not falsify that is *catastrophic* OR *memory-grounded*
            (it actually bit us before) -> ESCALATE: we refuse to clear a possible
            catastrophe or a known-recurring failure on a guess (invariants I3/I5);
          - everything else a probe ruled out is `cleared`; lower-severity risks we
            could not check are `residual` — surfaced to the human, never blocking a
            routine payment (otherwise the autopilot could never act). design §6.
        """
        confirmed: list[ProbeResult] = []
        cleared: list[str] = []
        unfalsifiable: list[str] = []   # drove ESCALATE
        residual: list[str] = []        # non-blocking, surfaced to human
        attempted = 0
        block_rank = _SEVERITY_ORDER[self.block_threshold]

        for mode in modes:
            result: ProbeResult | None = None
            if mode.falsifiable and self.probes.has(mode.probe):
                result = self.probes.get(mode.probe)(plan, self.store)
                if result.probe_ran:
                    attempted += 1

            ran = result is not None and result.probe_ran
            if ran and result.confirmed:
                if _SEVERITY_ORDER[mode.severity] <= block_rank:
                    confirmed.append(result)
                else:
                    residual.append(f"{mode.id}:confirmed({mode.severity.value})")
            elif ran:
                cleared.append(mode.id)
            else:
                # could not falsify this mode
                if mode.severity == Severity.CATASTROPHIC or mode.seed_source == "memory":
                    unfalsifiable.append(mode.id)
                else:
                    residual.append(f"{mode.id}:unverified({mode.severity.value})")

        if confirmed:
            decision = VerdictDecision.BLOCK
            notes = f"{len(confirmed)} 件の failure mode が反証で CONFIRMED → 実行停止"
        elif unfalsifiable:
            decision = VerdictDecision.ESCALATE
            notes = (f"{len(unfalsifiable)} 件の致命/既知再発モードを反証できず → 人へ "
                     f"escalate（invariant I5）")
        else:
            decision = VerdictDecision.PROCEED
            notes = (f"致命的モードを {attempted} 件すべて反証試行し壊せず → 実行可"
                     f"（残存 advisory {len(residual)} 件は記録）")
        return Verdict(
            decision=decision,
            confirmed=confirmed,
            attempted=attempted,
            unfalsifiable=unfalsifiable,
            cleared=cleared,
            residual=residual,
            notes=notes,
        )

    def run(self, plan: PaymentPlan) -> Verdict:
        return self.falsify(plan, self.enumerate_failure_modes(plan))


def _coerce_sev(value: str) -> Severity:
    try:
        return Severity(value)
    except ValueError:
        return Severity.MEDIUM
