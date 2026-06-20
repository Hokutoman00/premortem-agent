# Live Qwen Cloud evidence — `tampered_img` on `qwen-vl-max`

Captured run of the real DashScope vision leg against the shipped tampered invoice
PNG. Reproduce with: `PREMORTEM_LLM=dashscope DASHSCOPE_API_KEY=... python -m pytest
tests/test_vision_live.py -v` (both tests pass live).

- captured (UTC): 2026-06-20T11:03:40Z
- region endpoint: https://dashscope-intl.aliyuncs.com/compatible-mode/v1
- vision model: qwen-vl-max   reasoning model: qwen-max
- image read: invoice_INV-2026-0451_tampered.png

## What qwen-vl-max read off the invoice image
```json
{
  "iban_on_doc": "GB44 BARC 2003 8512 345678",
  "amount_on_doc": "USD5,300.00",
  "vendor_on_doc": "Acme Supplies Ltd (V-1007)",
  "tax_id_on_doc": "DE811234567",
  "po_number_on_doc": "PO-2026-0451",
  "po_amount": "USD5,300.00"
}
```

## Engine verdict (live)
- verdict: **BLOCK**
- executed: False
- confirmed failure modes: ['invoice_image_mismatch']

The BLOCK is driven by `invoice_image_mismatch`: the IBAN printed on the invoice
image differs from the IBAN in the structured payment plan — the falsification leg
a text-only agent cannot build. The structured bank/amount probes all clear; only the
vision cross-check catches it.
