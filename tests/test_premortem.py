"""PreMortemEngine — enumerate -> falsify -> Verdict. The product thesis: act only when
the engine cannot prove its own plan wrong; severity grades whether a confirmed/unprobeable
mode blocks, escalates, or is merely advisory."""
from __future__ import annotations

from dataclasses import replace

from premortem.catastrophe_registry import CatastropheRegistry
from premortem.memory.failure_memory import FailureMemory
from premortem.premortem import PreMortemEngine
from premortem.types import (
    FailureMode,
    FailureOutcome,
    PaymentPlan,
    Severity,
    VerdictDecision,
)


def _plan(**kw):
    base = dict(
        invoice_id="INV-X", vendor_name="Acme Supplies Ltd", vendor_id="V-1007",
        amount=5000.0, currency="USD",
        bank={"iban": "DE89370400440532013000"}, action="pay_invoice",
        source_image_facts={"iban_on_doc": "DE89370400440532013000"},
    )
    base.update(kw)
    return PaymentPlan(**base)


# --- enumerate ---------------------------------------------------------------
def test_enumerate_always_includes_registry_floor(engine):
    modes = engine.enumerate_failure_modes(_plan())
    ids = {m.id for m in modes}
    # The catastrophe registry floor is present regardless of the LLM (invariant I6).
    for required in ("bank_changed", "unapproved_vendor", "invoice_image_mismatch"):
        assert required in ids


def test_enumerate_is_severity_ordered(engine):
    modes = engine.enumerate_failure_modes(_plan())
    order = {Severity.CATASTROPHIC: 0, Severity.HIGH: 1, Severity.MEDIUM: 2, Severity.LOW: 3}
    ranks = [order[m.severity] for m in modes]
    assert ranks == sorted(ranks)  # most dangerous probed first


def test_memory_seed_outranks_registry(engine, memory):
    memory.append(FailureOutcome(
        action_fp="V-1007:pay_invoice:5000", failure_mode="bank_changed",
        evidence="過去に口座差替", label="confirmed_fraud", source="engine"))
    modes = engine.enumerate_failure_modes(_plan())
    bank = next(m for m in modes if m.id == "bank_changed")
    assert bank.seed_source == "memory"  # memory > registry in dedup


# --- falsify: the three verdict branches ------------------------------------
def test_clean_payment_proceeds(engine):
    v = engine.run(_plan())
    assert v.decision == VerdictDecision.PROCEED
    assert v.confirmed == []


def test_swapped_bank_blocks(engine):
    v = engine.run(_plan(bank={"iban": "GB44BARC20038512345678"},
                         source_image_facts={"iban_on_doc": "GB44BARC20038512345678"}))
    assert v.decision == VerdictDecision.BLOCK
    assert any(r.mode == "bank_changed" for r in v.confirmed)


def test_unapproved_new_vendor_blocks(engine):
    v = engine.run(_plan(vendor_id="V-9001", amount=9000.0,
                         bank={"iban": "GB29NWBK60161331926819"},
                         source_image_facts={"iban_on_doc": "GB29NWBK60161331926819"}))
    assert v.decision == VerdictDecision.BLOCK
    confirmed = {r.mode for r in v.confirmed}
    assert "unapproved_vendor" in confirmed
    assert "new_payee_first_payment" in confirmed


# --- severity grading --------------------------------------------------------
def test_confirmed_below_threshold_is_residual_not_block(engine):
    # round_number_anomaly is MEDIUM: confirmed but must NOT block on its own.
    v = engine.run(_plan(amount=9000.0))
    assert v.decision == VerdictDecision.PROCEED
    assert any(r.startswith("round_number_anomaly:confirmed") for r in v.residual)


def test_unprobeable_catastrophic_escalates():
    # A lone catastrophic mode with no probe must escalate, never silently pass (I5).
    store_modes = [FailureMode(id="meteor", desc="x", probe="", severity=Severity.CATASTROPHIC,
                              seed_source="registry")]
    eng = PreMortemEngine(
        llm=_NullLLM(), store=_DummyStore(), probes=_EmptyProbes(),
        memory=FailureMemory(":memory:"), registry=CatastropheRegistry(store_modes))
    v = eng.falsify(_plan(), eng.registry.modes())
    assert v.decision == VerdictDecision.ESCALATE
    assert "meteor" in v.unfalsifiable


def test_unprobeable_registry_mode_is_residual_not_escalate(engine):
    v = engine.run(_plan())
    # po_mismatch / tax_id_mismatch are HIGH but, on a routine plan with no PO/tax-id facts
    # on the document, their probes honestly cannot run. A non-catastrophic, registry-sourced
    # mode that cannot be checked is advisory *residual*, not an escalation driver — so a clean
    # payment still proceeds (only catastrophic/memory-sourced unprobeables escalate, I5).
    assert v.decision == VerdictDecision.PROCEED
    assert any(r.startswith("po_mismatch") for r in v.residual)


# --- memory-probe backfill (the wiring-bug regression) ----------------------
def test_memory_mode_backfills_canonical_probe(engine, memory):
    # A remembered mode stores its own id as probe name; new_payee_first_payment's real
    # probe is `vendor_age`. The backfill must rewire it so a probeable remembered mode
    # confirms instead of auto-escalating.
    memory.append(FailureOutcome(
        action_fp="V-9001:pay_invoice:9000", failure_mode="new_payee_first_payment",
        evidence="初回支払", label="confirmed_by_probe", source="engine"))
    modes = engine.enumerate_failure_modes(
        _plan(vendor_id="V-9001", amount=9000.0))
    npf = next(m for m in modes if m.id == "new_payee_first_payment")
    assert npf.seed_source == "memory"
    assert npf.probe == "vendor_age"  # backfilled from the registry mode->probe map


def test_unprobeable_memory_mode_stays_unwired_and_escalates(engine, memory):
    # goods_not_received has no probe anywhere -> stays unwired -> escalate (the loop).
    memory.append(FailureOutcome(
        action_fp="V-1007:pay_invoice:5000", failure_mode="goods_not_received",
        evidence="納品なし", label="human_override", source="human_override"))
    v = engine.run(_plan())
    assert v.decision == VerdictDecision.ESCALATE
    assert "goods_not_received" in v.unfalsifiable


# --- minimal stand-ins for the isolated-escalation test ----------------------
class _NullLLM:
    def complete(self, *a, **k): return "[]"
    def complete_samples(self, *a, **k): raise NotImplementedError
    def vision(self, *a, **k): return "{}"


class _DummyStore:
    def amount_stats(self, vendor_id): return None


class _EmptyProbes:
    def has(self, name): return False
    def get(self, name): raise KeyError(name)
