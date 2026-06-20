"""Policy — the two-regime rule. Reversible actions execute immediately with no pre-mortem
(EV-max); irreversible/unknown actions require a PROCEED verdict, and any BLOCK/ESCALATE is
written to failure-memory so the next pre-mortem is sharper (invariants I1 + I4)."""
from __future__ import annotations

from dataclasses import replace

from premortem.types import PaymentPlan, Reversibility


def _pay(**kw):
    base = dict(
        invoice_id="INV-X", vendor_name="Acme Supplies Ltd", vendor_id="V-1007",
        amount=4750.0, currency="USD",
        bank={"iban": "DE89370400440532013000"}, action="pay_invoice",
        source_image_facts={"iban_on_doc": "DE89370400440532013000"},
    )
    base.update(kw)
    return PaymentPlan(**base)


def test_reversible_action_skips_premortem_and_executes(agent):
    ran = []
    d = agent.assess(_pay(action="draft_invoice"), executor=ran.append)
    assert d.reversibility == Reversibility.REVERSIBLE
    assert d.executed is True
    assert d.verdict is None          # no pre-mortem spent on a cheap-to-undo action
    assert len(ran) == 1


def test_irreversible_clean_payment_executes(agent):
    ran = []
    d = agent.assess(_pay(), executor=ran.append)
    assert d.reversibility == Reversibility.IRREVERSIBLE
    assert d.executed is True
    assert d.verdict.decision.value == "PROCEED"
    assert len(ran) == 1


def test_blocked_payment_never_executes(agent):
    ran = []
    d = agent.assess(_pay(bank={"iban": "GB44BARC20038512345678"},
                          source_image_facts={"iban_on_doc": "GB44BARC20038512345678"}),
                     executor=ran.append)
    assert d.executed is False        # invariant I1: irreversible never acts without PROCEED
    assert d.verdict.decision.value == "BLOCK"
    assert ran == []                  # the executor was never called


def test_block_is_written_to_memory(agent):
    before = agent.memory.count()
    agent.assess(_pay(bank={"iban": "GB44BARC20038512345678"},
                      source_image_facts={"iban_on_doc": "GB44BARC20038512345678"}))
    rows = list(agent.memory.all())
    assert agent.memory.count() > before
    # the confirmed danger is the thing remembered (invariant I4)
    assert any(r["failure_mode"] == "bank_changed" for r in rows)
    assert all(r["label"] == "confirmed_by_probe" for r in rows)


def test_escalation_records_only_unfalsifiable_drivers(agent):
    # Seed an unprobeable remembered failure so the next identical payment escalates.
    agent.learn_from_human(_pay(), failure_mode="goods_not_received",
                           evidence="納品なし", label="human_override")
    before = agent.memory.count()
    d = agent.assess(_pay())
    assert d.executed is False
    assert d.verdict.decision.value == "ESCALATE"
    new_rows = list(agent.memory.all())[before:]
    assert new_rows and all(r["label"] == "unfalsifiable_catastrophic" for r in new_rows)
    assert any(r["failure_mode"] == "goods_not_received" for r in new_rows)
