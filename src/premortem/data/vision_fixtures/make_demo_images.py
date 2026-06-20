"""Generate the real demo invoice PNGs that the live qwen-vl-max leg reads.

Deterministic, Pillow-only. Re-run to regenerate both shipped fixtures:

    python src/premortem/data/vision_fixtures/make_demo_images.py

Why these files exist
---------------------
The offline **mock** adapter reads the `*.png.json` sidecar next to each image (it never
decodes pixels), so the demo is reproducible without a key. But the **real** DashScopeAdapter
sends the actual file to `qwen-vl-max`. If only the sidecar shipped, the live VL leg would be
handed a non-existent `file://invoice_...png` and the `tampered_img` money-shot would fail/
ESCALATE instead of BLOCK. So we ship a real PNG whose **printed fields equal the sidecar's
ground truth** — the mock and the live model then read the same document and reach the same
verdict. Text is rendered with a TrueType face at a legible size so the model can read a full
IBAN off the image.

No real PII — every value is a demo constant consistent with the demo ledger (V-1007).
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent


def _font(size: int) -> ImageFont.ImageFont:
    # Pillow bundles DejaVuSans; fall back to the bitmap default if it is unavailable.
    for name in ("DejaVuSans.ttf", "DejaVuSansMono.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


# Each variant prints the fields the VL prompt extracts (iban/amount/vendor/tax_id/po).
# Only the remit-to IBAN differs between clean and tampered — that single difference is what
# the image_consistency probe catches, so the DOCUMENT (not a filename branch) drives the verdict.
_COMMON = {
    "vendor": "Acme Supplies Ltd  (V-1007)",
    "tax_id": "DE811234567",
    "invoice_no": "INV-2026-0451",
    "po_no": "PO-2026-0451",
    "amount": "USD 5,300.00",
    "po_total": "USD 5,300.00",
    "bic": "COBADEFFXXX",
}

VARIANTS = {
    # The untampered invoice: the remit-to IBAN MATCHES vendor V-1007's known DE account.
    "invoice_INV-2026-0451_clean.png": {
        "iban": "DE89 3704 0044 0532 0130 00",
        "iban_flat": "DE89370400440532013000",
    },
    # The tampered invoice: the printed remit-to IBAN is a GB account that does NOT match the
    # payment plan's DE account — image_consistency CONFIRMS the mismatch and the engine BLOCKs.
    "invoice_INV-2026-0451_tampered.png": {
        "iban": "GB44 BARC 2003 8512 345678",
        "iban_flat": "GB44BARC20038512345678",
    },
}


def _render(iban_printed: str) -> Image.Image:
    img = Image.new("RGB", (1000, 640), "white")
    d = ImageDraw.Draw(img)
    title = _font(34)
    body = _font(24)
    d.rectangle([20, 20, 980, 620], outline="black", width=2)
    d.text((44, 36), "INVOICE", fill="black", font=title)
    lines = [
        f"Vendor:    {_COMMON['vendor']}",
        f"Tax ID:    {_COMMON['tax_id']}",
        f"Invoice #: {_COMMON['invoice_no']}",
        f"PO #:      {_COMMON['po_no']}",
        "",
        "Description                       Amount",
        f"Freight services, June            {_COMMON['amount']}",
        "",
        f"Total due:                        {_COMMON['amount']}",
        f"PO total:                         {_COMMON['po_total']}",
        "",
        "Remit to (bank):",
        f"IBAN: {iban_printed}",
        f"BIC:  {_COMMON['bic']}",
    ]
    y = 96
    for text in lines:
        d.text((44, y), text, fill="black", font=body)
        y += 36
    return img


def _sidecar(name: str, iban_flat: str) -> dict:
    """The ground truth the VL model would extract from this PNG — the mock reads this so the
    offline verdict equals the live verdict. Kept in lockstep with what _render prints."""
    return {
        "_what_this_is": (
            "Ground-truth the VL model extracts from the shipped PNG of the same name. The mock "
            "READS this sidecar instead of decoding the PNG, so the engine's vision->"
            "image_consistency path is reproducible offline AND identical to the live qwen-vl-max "
            "read of the real image. Regenerate both with make_demo_images.py."
        ),
        "iban_on_doc": iban_flat,
        "amount_on_doc": "5,300.00",
        "vendor_on_doc": "Acme Supplies Ltd",
        "tax_id_on_doc": _COMMON["tax_id"],          # == V-1007 record -> tax_id_check clears
        "po_number_on_doc": _COMMON["po_no"],
        "po_amount": "5300.00",                       # == amount paid -> po_match clears
    }


def main() -> None:
    for name, v in VARIANTS.items():
        img = _render(v["iban"])
        png = HERE / name
        img.save(png)
        sidecar = HERE / f"{name}.json"
        sidecar.write_text(json.dumps(_sidecar(name, v["iban_flat"]), ensure_ascii=False, indent=2)
                           + "\n", encoding="utf-8")
        print(f"wrote {png.name} ({png.stat().st_size} bytes) + {sidecar.name}")


if __name__ == "__main__":
    main()
