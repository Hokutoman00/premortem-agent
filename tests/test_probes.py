"""Probes — the non-LLM checks that anchor every verdict (invariant I6). Each probe must
confirm a real danger, clear a safe payment, and honestly report probe_ran=False when it
lacks the data to judge (so the engine escalates instead of guessing)."""
from __future__ import annotations

from premortem.probes.registry import (
    amount_anomaly,
    approval_list,
    bank_country_mismatch,
    bank_detail_diff,
    currency_check,
    default_registry,
    duplicate_check,
    image_consistency,
    po_match,
    round_number,
    tax_id_check,
    vendor_age,
)
from premortem.types import PaymentPlan


def _plan(**kw):
    base = dict(
        invoice_id="INV-X", vendor_name="Acme Supplies Ltd", vendor_id="V-1007",
        amount=5000.0, currency="USD",
        bank={"iban": "DE89370400440532013000"}, action="pay_invoice",
    )
    base.update(kw)
    return PaymentPlan(**base)


def test_bank_detail_diff_confirms_swapped_iban(store):
    r = bank_detail_diff(_plan(bank={"iban": "GB44BARC20038512345678"}), store)
    assert r.confirmed and r.probe_ran


def test_bank_detail_diff_clears_matching_iban(store):
    r = bank_detail_diff(_plan(), store)
    assert not r.confirmed and r.probe_ran


def test_bank_detail_diff_unrunnable_without_history(store):
    r = bank_detail_diff(_plan(vendor_id="V-9001", bank={"iban": "GB29NWBK60161331926819"}), store)
    assert not r.confirmed and not r.probe_ran  # no prior payment -> cannot judge


def test_vendor_age_confirms_first_payment(store):
    assert vendor_age(_plan(vendor_id="V-9001"), store).confirmed  # brand-new payee


def test_vendor_age_clears_established_vendor(store):
    assert not vendor_age(_plan(vendor_id="V-1007"), store).confirmed


def test_approval_list_confirms_unapproved(store):
    assert approval_list(_plan(vendor_id="V-9001"), store).confirmed


def test_approval_list_clears_approved(store):
    assert not approval_list(_plan(vendor_id="V-1007"), store).confirmed


def test_bank_country_mismatch_confirms_gb_account_for_de_vendor(store):
    r = bank_country_mismatch(_plan(bank={"iban": "GB44BARC20038512345678"}), store)
    assert r.confirmed


def test_bank_country_mismatch_clears_matching_country(store):
    assert not bank_country_mismatch(_plan(), store).confirmed


def test_duplicate_check_confirms_repeated_amount(store):
    # 4120.00 is an exact past payment for V-1007.
    assert duplicate_check(_plan(amount=4120.00), store).confirmed


def test_duplicate_check_clears_novel_amount(store):
    assert not duplicate_check(_plan(amount=5123.45), store).confirmed


def test_amount_anomaly_unrunnable_without_history(store):
    r = amount_anomaly(_plan(vendor_id="V-9001"), store)
    assert not r.probe_ran


def test_amount_anomaly_clears_in_distribution(store):
    assert not amount_anomaly(_plan(amount=5000.0), store).confirmed


def test_round_number_confirms_round_amount(store):
    assert round_number(_plan(amount=9000.0), store).confirmed


def test_round_number_clears_non_round(store):
    assert not round_number(_plan(amount=5123.45), store).confirmed


def test_image_consistency_confirms_doc_vs_plan_mismatch(store):
    p = _plan(source_image_facts={"iban_on_doc": "GB44BARC20038512345678"})
    assert image_consistency(p, store).confirmed  # the VL leg a text-only model can't build


def test_image_consistency_clears_matching_doc(store):
    p = _plan(source_image_facts={"iban_on_doc": "DE89370400440532013000"})
    assert not image_consistency(p, store).confirmed


def test_image_consistency_unrunnable_without_facts(store):
    assert not image_consistency(_plan(source_image_facts={}), store).probe_ran


def test_currency_check_confirms_unknown_currency(store):
    assert currency_check(_plan(currency="JPY"), store).confirmed


def test_currency_check_clears_known_currency(store):
    assert not currency_check(_plan(currency="USD"), store).confirmed


def test_tax_id_check_confirms_mismatch(store):
    # The tax id printed on the invoice disagrees with the vendor record -> impersonation tell.
    p = _plan(source_image_facts={"iban_on_doc": "DE89370400440532013000",
                                  "tax_id_on_doc": "DE999999999"})
    r = tax_id_check(p, store)
    assert r.confirmed and r.probe_ran


def test_tax_id_check_clears_matching_id(store):
    p = _plan(source_image_facts={"tax_id_on_doc": "DE811234567"})  # V-1007's real id
    r = tax_id_check(p, store)
    assert not r.confirmed and r.probe_ran


def test_tax_id_check_unrunnable_without_doc_id(store):
    assert not tax_id_check(_plan(source_image_facts={}), store).probe_ran


def test_po_match_confirms_amount_disagreement(store):
    p = _plan(amount=5000.0, source_image_facts={"po_amount": "4000.0"})
    r = po_match(p, store)
    assert r.confirmed and r.probe_ran


def test_po_match_clears_agreeing_amount(store):
    p = _plan(amount=5000.0, source_image_facts={"po_amount": "5000.0"})
    r = po_match(p, store)
    assert not r.confirmed and r.probe_ran


def test_po_match_unrunnable_without_po_reference(store):
    assert not po_match(_plan(source_image_facts={}), store).probe_ran


def test_registry_unwired_probe_reports_cannot_run(store):
    reg = default_registry()
    assert not reg.has("goods_not_received")  # a memory-only mode with no implemented probe
    r = reg.get("goods_not_received")(_plan(), store)  # honest "cannot falsify"
    assert not r.confirmed and not r.probe_ran
