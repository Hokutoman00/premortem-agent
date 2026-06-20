"""PreMortemAgent — top-level orchestrator wiring perception -> engine -> policy.

This is the object the API and demo construct. It owns the dependency graph and exposes
two entry points:
  - assess(plan)            : decide on an already-structured PaymentPlan.
  - assess_with_image(...)  : read an invoice image first (qwen-vl-max), attach the
                              grounded facts, then decide. This is the path that uses the
                              vision leg as a judgment basis.
  - learn_from_human(...)   : record a human override / post-hoc miss so the next
                              pre-mortem is seeded by it (the v8 learning loop).
"""
from __future__ import annotations

from dataclasses import replace

from .catastrophe_registry import CatastropheRegistry
from .config import Config, CONFIG
from .data.demo_data import DemoDataStore, default_store
from .llm import build_client
from .llm.base import QwenClient
from .memory.failure_memory import FailureMemory
from .perception.vision import VisionPerceiver
from .policy import Policy
from .premortem import PreMortemEngine
from .probes.registry import default_registry
from .reversibility import ReversibilityClassifier
from .types import Decision, FailureOutcome, PaymentPlan


class PreMortemAgent:
    def __init__(
        self,
        llm: QwenClient | None = None,
        store: DemoDataStore | None = None,
        memory: FailureMemory | None = None,
        config: Config = CONFIG,
    ):
        self.config = config
        self.llm = llm or build_client(config)
        self.store = store or default_store()
        self.memory = memory or FailureMemory(":memory:")
        self.probes = default_registry()
        self.registry = CatastropheRegistry()
        self.vision = VisionPerceiver(self.llm)
        self.engine = PreMortemEngine(
            self.llm, self.store, self.probes, self.memory, self.registry,
            self_consistency_n=config.self_consistency_n,
        )
        self.classifier = ReversibilityClassifier(self.llm)
        self.policy = Policy(self.engine, self.classifier, self.memory)

    # --- decision entry points -----------------------------------------
    def assess(self, plan: PaymentPlan, executor=None) -> Decision:
        return self.policy.decide(plan, executor=executor)

    def ground(self, plan: PaymentPlan, image_ref: str) -> PaymentPlan:
        """Read the invoice image (qwen-vl-max) and attach the facts the model SAW.

        Exposed so the demo/UI can run `assess` and `explain` on the SAME grounded plan
        the decision used — otherwise the displayed verdict would re-derive on a plan
        missing the VL leg and could disagree with the actual decision."""
        facts = self.vision.read_invoice(image_ref)
        return replace(plan, source_image_facts={**plan.source_image_facts, **facts})

    def assess_with_image(self, plan: PaymentPlan, image_ref: str,
                          executor=None) -> Decision:
        return self.policy.decide(self.ground(plan, image_ref), executor=executor)

    def decide_and_explain(self, plan: PaymentPlan, image_ref: str | None = None) -> dict:
        """Decision + its explanation on ONE plan, from ONE engine run.

        Grounds on the image first (if any) so the VL leg is reflected, then decides via
        `decide_with_trace`, which runs enumerate+falsify exactly once and hands back the
        very (modes, verdict) it acted on. The explanation is rendered from that same
        verdict — so under a real sampling backend the verdict shown can never disagree
        with the verdict acted on (it is the *same object*, not a re-derivation)."""
        grounded = self.ground(plan, image_ref) if image_ref else plan
        decision, modes, verdict = self.policy.decide_with_trace(grounded)
        # Reversible plans skip the pre-mortem (verdict is None); explain them on their own
        # engine pass since there is no acted-on verdict to mirror. Irreversible plans —
        # every demo scenario — mirror the exact verdict the decision used.
        explanation = (self._explanation(grounded, modes, verdict) if verdict is not None
                       else self.explain(grounded))
        return {"decision": decision.to_dict(), "explain": explanation}

    # --- learning loop (v8) --------------------------------------------
    def learn_from_human(self, plan: PaymentPlan, failure_mode: str, evidence: str,
                         label: str = "human_override") -> int:
        """Record a human correction so future pre-mortems seed on it (invariant I4)."""
        return self.memory.append(FailureOutcome(
            action_fp=plan.fingerprint(), failure_mode=failure_mode,
            evidence=evidence, label=label, source="human_override",
        ))

    # --- introspection for demo/UI -------------------------------------
    def explain(self, plan: PaymentPlan) -> dict:
        """Stand-alone introspection: run the engine and format the result. Used where no
        decision has been committed (e.g. a reversible plan, or a pure what-would-happen
        query). The decision path uses `_explanation` on its already-computed verdict."""
        modes = self.engine.enumerate_failure_modes(plan)
        verdict = self.engine.falsify(plan, modes)
        return self._explanation(plan, modes, verdict)

    def _explanation(self, plan: PaymentPlan, modes, verdict) -> dict:
        return {
            "fingerprint": plan.fingerprint(),
            "enumerated": [
                {"id": m.id, "severity": m.severity.value, "source": m.seed_source,
                 "probe": m.probe} for m in modes
            ],
            "verdict": verdict.decision.value,
            "confirmed": [{"mode": r.mode, "evidence": r.evidence} for r in verdict.confirmed],
            "unfalsifiable": verdict.unfalsifiable,
            "cleared": verdict.cleared,
            "residual": verdict.residual,
            "attempted": verdict.attempted,
            "notes": verdict.notes,
            "memory_size": self.memory.count(),
        }
