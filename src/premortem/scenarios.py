"""Built-in demo scenarios — the deterministic stories the video and tests replay.

Each scenario is (PaymentPlan, image_ref|None). They exercise every verdict branch
against the default demo ledger (data/demo_data.py):
  - safe        : routine repeat payment to an approved vendor -> PROCEED -> pays.
  - bank_swap   : same vendor, IBAN silently changed -> bank_detail_diff CONFIRMS -> BLOCK.
  - tampered_img: structured request looks fine, but the invoice IMAGE shows a different
                  IBAN -> image_consistency (VL leg) CONFIRMS -> BLOCK. The leg a
                  text-only competitor cannot build.
  - new_vendor  : unapproved brand-new payee -> approval_list CONFIRMS -> BLOCK.
  - doc_mismatch: structured payment is clean (approved vendor, known IBAN, in-distribution
                  amount), but the invoice DOCUMENT prints a tax-id and a PO total that
                  disagree with the records -> tax_id_check + po_match CONFIRM -> BLOCK. The
                  document-field analogue of tampered_img: the structured fields alone look fine.
"""
from __future__ import annotations

from pathlib import Path

from .types import PaymentPlan

# Demo invoice images live next to the vision fixtures. The real DashScopeAdapter sends the
# file to qwen-vl-max via a file:// URL, so it must receive an ABSOLUTE on-disk path — a bare
# basename would become a broken relative file://invoice_....png and the live VL leg would fail
# (ESCALATE) instead of BLOCK. The mock keys off the basename, so it is unaffected either way.
_VISION_FIXTURE_DIR = Path(__file__).resolve().parent / "data" / "vision_fixtures"


def _demo_image_ref(name: str) -> str:
    """Absolute path to the shipped demo PNG if it exists, else the bare name unchanged."""
    png = _VISION_FIXTURE_DIR / name
    return str(png) if png.exists() else name

# A normal, in-distribution repeat payment to an approved vendor on the known account.
# The document fields all AGREE with the records (matching tax-id and PO total), so the
# document-field probes (tax_id_check, po_match) actually RUN and CLEAR — a clean payment
# leaves no high-severity unverified residual, only lighter advisory notes.
_SAFE = PaymentPlan(
    invoice_id="INV-2026-0413", vendor_name="Acme Supplies Ltd", vendor_id="V-1007",
    amount=5120.00, currency="USD",
    bank={"iban": "DE89370400440532013000", "name": "Acme Supplies Ltd"},
    action="pay_invoice",
    source_image_facts={
        "iban_on_doc": "DE89370400440532013000",   # matches -> image_consistency clears
        "amount_on_doc": "5,120.00",
        "tax_id_on_doc": "DE811234567",             # == V-1007's tax id -> tax_id_check clears
        "po_amount": "5120.00",                      # == amount paid -> po_match clears
    },
)

# Same vendor — but the payout IBAN has been swapped (classic vendor-impersonation fraud).
# The document's tax-id and PO total AGREE with the records, so those probes RUN and CLEAR;
# the only confirmed dangers are the bank ones (bank_detail_diff + bank_country_mismatch),
# keeping the residual free of "unverified(high)" tax/PO noise.
_BANK_SWAP = PaymentPlan(
    invoice_id="INV-2026-0440", vendor_name="Acme Supplies Ltd", vendor_id="V-1007",
    amount=4880.00, currency="USD",
    bank={"iban": "GB44BARC20038512345678", "name": "Acme Supplies Ltd"},
    action="pay_invoice",
    source_image_facts={
        "iban_on_doc": "GB44BARC20038512345678",    # != plan/known DE -> bank probes CONFIRM
        "amount_on_doc": "4,880.00",
        "tax_id_on_doc": "DE811234567",             # == V-1007's tax id -> tax_id_check clears
        "po_amount": "4880.00",                      # == amount paid -> po_match clears
    },
)

# Structured request matches records, but the IMAGE shows a mismatching IBAN.
_TAMPERED = PaymentPlan(
    invoice_id="INV-2026-0451", vendor_name="Acme Supplies Ltd", vendor_id="V-1007",
    amount=5300.00, currency="USD",
    bank={"iban": "DE89370400440532013000", "name": "Acme Supplies Ltd"},
    action="pay_invoice",
    # note: no source_image_facts here — they come from the VL read of the tampered image
)

# Brand-new, unapproved payee. The document's own tax-id and PO total agree with the V-9001
# record, so those probes clear — the BLOCK is driven purely by approval_list (unapproved_vendor)
# and the missing-history signals, not by tax/PO noise.
_NEW_VENDOR = PaymentPlan(
    invoice_id="INV-2026-0460", vendor_name="Bright Star Trading", vendor_id="V-9001",
    amount=9000.00, currency="USD",
    bank={"iban": "GB29NWBK60161331926819", "name": "Bright Star Trading"},
    action="pay_invoice",
    source_image_facts={
        "iban_on_doc": "GB29NWBK60161331926819",    # == plan iban -> image_consistency clears
        "amount_on_doc": "9,000.00",
        "tax_id_on_doc": "GB000000000",             # == V-9001's tax id -> tax_id_check clears
        "po_amount": "9000.00",                      # == amount paid -> po_match clears
    },
)

# Structured payment is clean — approved vendor, the known IBAN, an in-distribution,
# non-round, novel amount, so every bank/amount probe clears. But the invoice DOCUMENT
# prints a tax-id that is not V-1007's (DE811234567) and a PO total that disagrees with the
# amount being paid. Only the document-field probes (tax_id_check, po_match) catch it.
_DOC_MISMATCH = PaymentPlan(
    invoice_id="INV-2026-0473", vendor_name="Acme Supplies Ltd", vendor_id="V-1007",
    amount=5275.50, currency="USD",
    bank={"iban": "DE89370400440532013000", "name": "Acme Supplies Ltd"},
    action="pay_invoice",
    source_image_facts={
        "iban_on_doc": "DE89370400440532013000",   # matches -> image_consistency clears
        "amount_on_doc": "5,275.50",
        "tax_id_on_doc": "DE899999999",             # != DE811234567 -> tax_id_check CONFIRMS
        "po_amount": "4900.00",                      # != 5,275.50 -> po_match CONFIRMS
    },
)

SCENARIOS: dict[str, tuple[PaymentPlan, str | None]] = {
    "safe": (_SAFE, None),
    "bank_swap": (_BANK_SWAP, None),
    "tampered_img": (_TAMPERED, _demo_image_ref("invoice_INV-2026-0451_tampered.png")),
    "new_vendor": (_NEW_VENDOR, None),
    "doc_mismatch": (_DOC_MISMATCH, None),
}


def scenario_plan(name: str) -> tuple[PaymentPlan | None, str | None]:
    return SCENARIOS.get(name, (None, None))
