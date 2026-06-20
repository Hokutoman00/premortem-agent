"""Self-consistency as the logprob substitute (design §4, ARCHITECTURE §5).

Qwen Cloud exposes no logprobs, so confidence on the LLM enumeration leg is recovered by
sampling it N times. These tests prove the mechanism is *wired into the verdict path*, not
just documented: when the model cannot agree with itself about an irreversible payment's
risk landscape, the engine refuses a clean PROCEED and escalates (invariant I5)."""
from __future__ import annotations

from premortem.catastrophe_registry import CatastropheRegistry
from premortem.llm.base import SampleSet
from premortem.llm.mock_adapter import MockAdapter
from premortem.memory.failure_memory import FailureMemory
from premortem.premortem import PreMortemEngine
from premortem.probes.registry import default_registry
from premortem.types import PaymentPlan, Severity, VerdictDecision


class _DissentAdapter(MockAdapter):
    """Always low self-agreement on the enumeration leg, regardless of plan fields.

    Lets us isolate the consistency gate at the verdict level on an otherwise-clean
    payment (approved vendor, matching bank) — so the ONLY thing that can move the
    verdict off PROCEED is the unstable-enumeration escalation."""

    def complete_samples(self, prompt, *, n=5, system=None, temperature=0.7):
        base = self.complete(prompt, system=system)
        return SampleSet(samples=([base, base] + [f"d-{i}" for i in range(n - 2)])[:n])


def _plan(vendor_id: str, amount: float = 5000.0) -> PaymentPlan:
    return PaymentPlan(
        invoice_id="INV-SC", vendor_name="Acme Supplies Ltd", vendor_id=vendor_id,
        amount=amount, currency="USD",
        bank={"iban": "DE89370400440532013000"}, action="pay_invoice",
        source_image_facts={"iban_on_doc": "DE89370400440532013000"},
    )


# A payment far outside V-1007's history (mean ~4830) — the engine tags its enumeration
# prompt `large_amount`, which is the genuine under-determination signal the mock dissents on.
_OOD_AMOUNT = 250000.0


def _engine(**kw) -> PreMortemEngine:
    return PreMortemEngine(
        MockAdapter(), default_store_for_test(), default_registry(),
        FailureMemory(":memory:"), CatastropheRegistry(), **kw)


def default_store_for_test():
    from premortem.data.demo_data import default_store
    return default_store()


def test_low_self_agreement_injects_unstable_mode():
    # A genuinely out-of-distribution payment makes the model's risk enumeration unstable: the
    # engine tags the prompt `large_amount`, the mock emits mostly-distinct dissents, so modal
    # agreement is 0.4 < the 0.6 floor and the catastrophic unprobeable mode is injected.
    eng = _engine()
    modes = eng.enumerate_failure_modes(_plan("V-1007", amount=_OOD_AMOUNT))
    unstable = [m for m in modes if m.id == "llm_enumeration_unstable"]
    assert len(unstable) == 1
    assert unstable[0].severity == Severity.CATASTROPHIC
    assert unstable[0].probe == ""  # unfalsifiable by construction


def test_low_self_agreement_escalates_the_verdict():
    # Otherwise-clean payment (approved vendor V-1007, matching bank) that would PROCEED;
    # unstable enumeration is the only mover, so the verdict must flip to ESCALATE.
    eng = PreMortemEngine(
        _DissentAdapter(), default_store_for_test(), default_registry(),
        FailureMemory(":memory:"), CatastropheRegistry())
    v = eng.run(_plan("V-1007"))
    assert v.decision == VerdictDecision.ESCALATE
    assert "llm_enumeration_unstable" in v.unfalsifiable


def test_self_consistent_enumeration_does_not_inject_unstable_mode():
    # A normal vendor id -> unanimous samples -> agreement 1.0 -> no injected mode,
    # so a clean payment still proceeds (the mechanism does not fire spuriously).
    eng = _engine()
    modes = eng.enumerate_failure_modes(_plan("V-1007"))
    assert not any(m.id == "llm_enumeration_unstable" for m in modes)
    assert eng.run(_plan("V-1007")).decision == VerdictDecision.PROCEED


def test_single_sample_disables_the_consistency_gate():
    # With N=1 there is nothing to disagree with; the gate must not fire even on an
    # out-of-distribution payment (agreement of a singleton is 1.0 and the n>1 guard is false).
    eng = _engine(self_consistency_n=1)
    modes = eng.enumerate_failure_modes(_plan("V-1007", amount=_OOD_AMOUNT))
    assert not any(m.id == "llm_enumeration_unstable" for m in modes)


def test_agreement_floor_is_configurable():
    # Raising the floor above the mock's self-consistent agreement (1.0 is unreachable)
    # is a no-op for clean prompts; lowering it below 0.4 silences the out-of-distribution case.
    eng = _engine(escalate_agreement=0.3)
    modes = eng.enumerate_failure_modes(_plan("V-1007", amount=_OOD_AMOUNT))
    # 0.4 agreement is NOT below a 0.3 floor -> no injection.
    assert not any(m.id == "llm_enumeration_unstable" for m in modes)
