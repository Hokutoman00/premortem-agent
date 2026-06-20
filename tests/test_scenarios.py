"""End-to-end scenarios — the deterministic stories the demo and video replay. These pin
the externally-visible behaviour: the five built-in scenarios, the displayed-vs-acted
verdict consistency, and the day1->day2 learning loop."""
from __future__ import annotations

import pytest

from premortem.agent import PreMortemAgent
from premortem.memory.failure_memory import FailureMemory
from premortem.scenarios import SCENARIOS, scenario_plan
from premortem.types import PaymentPlan


@pytest.fixture
def fresh_agent():
    return PreMortemAgent(memory=FailureMemory(":memory:"))


EXPECTED = {
    "safe": ("PROCEED", True),
    "bank_swap": ("BLOCK", False),
    "tampered_img": ("BLOCK", False),
    "new_vendor": ("BLOCK", False),
    "doc_mismatch": ("BLOCK", False),
}


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_scenario_verdict_and_execution(fresh_agent, name):
    plan, image_ref = scenario_plan(name)
    out = fresh_agent.decide_and_explain(plan, image_ref)
    verdict, executed = EXPECTED[name]
    assert out["explain"]["verdict"] == verdict
    assert out["decision"]["executed"] is executed


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_displayed_verdict_matches_acted_verdict(fresh_agent, name):
    # decide_and_explain must show the same verdict it acts on — never re-derive a
    # different one on an un-grounded plan (the explain-vs-decision divergence bug).
    plan, image_ref = scenario_plan(name)
    out = fresh_agent.decide_and_explain(plan, image_ref)
    acted = out["decision"]["verdict"]["decision"]
    shown = out["explain"]["verdict"]
    proceeded = out["decision"]["executed"]
    # PROCEED -> executed; BLOCK/ESCALATE -> not executed; and the two views agree.
    assert shown == acted
    assert proceeded == (acted == "PROCEED")


def test_tampered_image_block_comes_from_vl_leg(fresh_agent):
    # The block must be driven by the vision cross-check the structured data alone misses.
    plan, image_ref = scenario_plan("tampered_img")
    out = fresh_agent.decide_and_explain(plan, image_ref)
    confirmed = {c["mode"] for c in out["decision"]["verdict"]["confirmed"]}
    assert "invoice_image_mismatch" in confirmed


def test_doc_mismatch_block_comes_from_document_field_probes(fresh_agent):
    # The structured payment is clean; the block must be driven by the document-field probes
    # (tax-id + PO total) that a check on the structured fields alone would never run.
    plan, image_ref = scenario_plan("doc_mismatch")
    out = fresh_agent.decide_and_explain(plan, image_ref)
    confirmed = {c["mode"] for c in out["decision"]["verdict"]["confirmed"]}
    assert "tax_id_mismatch" in confirmed
    assert "po_mismatch" in confirmed
    # and the bank/amount probes did clear (this is not a bank-swap or anomaly block)
    assert "bank_changed" not in confirmed


def test_flipping_the_invoice_fixture_flips_the_verdict(fresh_agent):
    # The mock vision reads a per-image fixture, so the DOCUMENT drives the decision — not a
    # code branch on the filename. Same payment plan: pointed at the tampered invoice it BLOCKs
    # (printed IBAN is a GB account); pointed at the clean counterpart it PROCEEDs. This is the
    # offline proxy for "qwen-vl-max read the pixels": flip what the image shows, flip the verdict.
    plan, tampered_ref = scenario_plan("tampered_img")
    blocked = fresh_agent.decide_and_explain(plan, tampered_ref)
    assert blocked["explain"]["verdict"] == "BLOCK"
    assert "invoice_image_mismatch" in {
        c["mode"] for c in blocked["decision"]["verdict"]["confirmed"]}

    clean = fresh_agent.decide_and_explain(plan, "invoice_INV-2026-0451_clean.png")
    assert clean["explain"]["verdict"] == "PROCEED"
    assert clean["decision"]["executed"] is True


def test_unknown_invoice_image_escalates_rather_than_clears(fresh_agent):
    # An image the mock has no fixture for is an empty read -> image_consistency is unfalsifiable
    # -> the engine escalates rather than silently clearing a payment it could not verify (I5).
    plan, _ = scenario_plan("tampered_img")
    out = fresh_agent.decide_and_explain(plan, "invoice_unknown_no_fixture.png")
    assert out["explain"]["verdict"] == "ESCALATE"
    assert out["decision"]["executed"] is False


def test_safe_clears_modes_and_carries_no_high_unverified_residual(fresh_agent):
    plan, image_ref = scenario_plan("safe")
    ex = fresh_agent.decide_and_explain(plan, image_ref)["explain"]
    assert ex["verdict"] == "PROCEED"
    assert len(ex["cleared"]) >= 8          # the catastrophic floor was actively ruled out
    # A clean payment whose document fields all AGREE with the records must not PROCEED while
    # leaving a high/catastrophic danger merely *unverified*: the doc-field probes (tax-id and
    # PO total) actually RUN and CLEAR rather than lingering as `unverified(high)`. Any residual
    # that remains is at most a lighter advisory — never a high danger we declined to check.
    assert not any(
        "unverified(high)" in r or "(catastrophic)" in r for r in ex["residual"]), ex["residual"]


def test_learning_loop_day1_pays_day2_escalates(fresh_agent):
    # Day 1: a clean, in-distribution payment to an approved vendor proceeds and pays.
    day1 = PaymentPlan(
        invoice_id="INV-D1", vendor_name="Acme Supplies Ltd", vendor_id="V-1007",
        amount=4750.0, currency="USD", bank={"iban": "DE89370400440532013000"},
        action="pay_invoice", source_image_facts={"iban_on_doc": "DE89370400440532013000"})
    d1 = fresh_agent.assess(day1)
    assert d1.executed is True

    # A human later discovers the goods never arrived -> teach the agent.
    fresh_agent.learn_from_human(day1, failure_mode="goods_not_received",
                                 evidence="支払済だが納品実績なし", label="human_override")

    # Day 2: the same fingerprint now carries an unprobeable remembered failure -> escalate.
    d2 = fresh_agent.assess(day1)
    assert d2.executed is False
    assert d2.verdict.decision.value == "ESCALATE"
