"""VisionPerceiver — reads the invoice image with qwen-vl-max and returns grounded facts.

The point (design §1, AMPLIFY Qwen-irreplaceability): the vision model is not used to
"OCR for convenience" but to produce a *judgment basis* — the IBAN / amount / vendor as
they literally appear on the document image — which `image_consistency` then cross-checks
against the structured payment request. A text-only competitor cannot build this leg.
"""
from __future__ import annotations

import json

from ..llm.base import QwenClient

_VISION_PROMPT = (
    "You are auditing an invoice image before a payment is made. "
    "Extract ONLY what is printed on the document. Return strict JSON with keys: "
    "iban_on_doc, amount_on_doc, vendor_on_doc, tax_id_on_doc, po_number_on_doc, "
    "po_amount. iban_on_doc/amount_on_doc/vendor_on_doc are the remit-to IBAN, the total "
    "due, and the vendor name; tax_id_on_doc is the vendor's printed tax/registration "
    "number; po_number_on_doc and po_amount are the purchase-order reference and its total "
    "if the invoice prints them. If a field is not legible or not present, use an empty "
    "string. Do not infer values that are not visibly printed."
)


class VisionPerceiver:
    def __init__(self, llm: QwenClient):
        self.llm = llm

    def read_invoice(self, image_ref: str) -> dict[str, str]:
        raw = self.llm.vision(_VISION_PROMPT, image_ref)
        return self._parse(raw)

    @staticmethod
    def _parse(raw: str) -> dict[str, str]:
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            # Be defensive: a non-JSON answer yields no grounded facts, which makes
            # image_consistency unfalsifiable -> escalate, never a silent pass.
            return {}
        if not isinstance(data, dict):
            return {}
        return {k: str(v) for k, v in data.items() if v is not None}
