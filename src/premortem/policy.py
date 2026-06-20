"""Policy — the two-regime decision rule that turns a Verdict into action.

Regime split (design §2 "決める", AMPLIFY v6/v7):
  - reversible action  -> act immediately, EV-max. No pre-mortem needed; mistakes are
    cheap to undo, so spending probe budget would be uneconomic.
  - irreversible/unknown action -> require a PROCEED verdict from the pre-mortem engine.
    Anything else (BLOCK / ESCALATE) stops and routes to a human, and is written to
    failure-memory so the next pre-mortem is sharper (invariant I4).

This concentrates the defense ONLY on irreversible actions — the economic displacement
from the field's "approve everything at the end" or "automate everything" baseline.
"""
from __future__ import annotations

from .memory.failure_memory import FailureMemory
from .premortem import PreMortemEngine
from .reversibility import ReversibilityClassifier
from .types import (
    Decision,
    FailureOutcome,
    PaymentPlan,
    Reversibility,
    Verdict,
    VerdictDecision,
)


class Policy:
    def __init__(
        self,
        engine: PreMortemEngine,
        classifier: ReversibilityClassifier,
        memory: FailureMemory,
    ):
        self.engine = engine
        self.classifier = classifier
        self.memory = memory

    def decide(self, plan: PaymentPlan, executor=None) -> Decision:
        decision, _modes, _verdict = self.decide_with_trace(plan, executor=executor)
        return decision

    def decide_with_trace(self, plan: PaymentPlan, executor=None):
        """Decide AND return the exact (modes, verdict) the decision was computed from.

        The engine is run **once** here. Callers that also need to *explain* the decision
        (the API / demo UI) build their explanation from this same verdict instead of
        re-running enumerate+falsify — under a real sampling backend (qwen-max) a second
        run could enumerate different LLM-extra modes or a different self-consistency
        reading, so the displayed reasoning could disagree with the verdict acted on.
        Returns (Decision, modes|[], Verdict|None); verdict is None only for the
        reversible regime, which skips the pre-mortem entirely."""
        rev = self.classifier.classify(plan.action)

        # Reversible regime: act now, no pre-mortem (EV-max).
        if rev == Reversibility.REVERSIBLE:
            executed = self._execute(plan, executor)
            return (
                Decision(
                    action=plan.action, executed=executed, reversibility=rev,
                    verdict=None, reason="可逆行動につき pre-mortem 不要・即実行（EV最大）",
                ),
                [],
                None,
            )

        # Irreversible / unknown regime: pre-mortem must clear it. One run, one verdict.
        modes = self.engine.enumerate_failure_modes(plan)
        verdict = self.engine.falsify(plan, modes)
        if verdict.decision == VerdictDecision.PROCEED:
            executed = self._execute(plan, executor)
            return (
                Decision(
                    action=plan.action, executed=executed, reversibility=rev,
                    verdict=verdict, reason="不可逆行動・反証で壊せず → 実行",
                ),
                modes,
                verdict,
            )

        # BLOCK or ESCALATE: never execute; learn from it (invariant I1 + I4).
        self._remember(plan, verdict)
        return (
            Decision(
                action=plan.action, executed=False, reversibility=rev, verdict=verdict,
                reason=("不可逆行動・反証で危険を検出 → 停止して人へ escalate"
                        if verdict.decision == VerdictDecision.BLOCK
                        else "不可逆行動・反証不能の経路が残存 → 保守側で人へ escalate"),
            ),
            modes,
            verdict,
        )

    # --- helpers --------------------------------------------------------
    @staticmethod
    def _execute(plan: PaymentPlan, executor) -> bool:
        if executor is None:
            return True  # demo/no-op executor: report intent to act
        executor(plan)
        return True

    def _remember(self, plan: PaymentPlan, verdict: Verdict) -> None:
        fp = plan.fingerprint()
        if verdict.decision == VerdictDecision.BLOCK:
            for r in verdict.confirmed:
                self.memory.append(FailureOutcome(
                    action_fp=fp, failure_mode=r.mode, evidence=r.evidence,
                    label="confirmed_by_probe", source="engine",
                ))
        else:  # ESCALATE — record only the catastrophic/known-recurring drivers, not noise
            for mode_id in verdict.unfalsifiable:
                self.memory.append(FailureOutcome(
                    action_fp=fp, failure_mode=mode_id,
                    evidence="致命/既知再発モードを反証できず保守 escalate",
                    label="unfalsifiable_catastrophic", source="engine",
                ))
