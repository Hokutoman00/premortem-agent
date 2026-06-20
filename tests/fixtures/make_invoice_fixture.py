"""Generate the synthetic invoice image used by the live vision smoke test.

Deterministic and dependency-light (Pillow only). Re-run to regenerate:

    python tests/fixtures/make_invoice_fixture.py

The image deliberately prints an IBAN, an amount, and a vendor name so the
`qwen-vl-max` leg has a real document to read in test_vision_live.py. No real
PII — all values are demo constants matching the demo data store (V-1007).
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).parent / "invoice_sample.png"

# Demo-data-consistent values (vendor V-1007). iban_on_doc here MATCHES the clean
# plan IBAN; the tampered-image scenario is exercised in the mock suite, not here.
LINES = [
    ("INVOICE", 0),
    ("", 1),
    ("Vendor:  Acme Supplies Ltd  (V-1007)", 0),
    ("Tax ID:  DE811234567", 0),
    ("Invoice #: INV-1007-0412", 0),
    ("PO #:    PO-1007-0412", 0),
    ("", 1),
    ("Description                         Amount", 0),
    ("Freight services, March            USD 4,750.00", 0),
    ("", 1),
    ("Total due:                         USD 4,750.00", 0),
    ("", 1),
    ("Remit to (bank):", 0),
    ("IBAN: DE89 3704 0044 0532 0130 00", 0),
    ("BIC:  COBADEFFXXX", 0),
]


def main() -> None:
    img = Image.new("RGB", (900, 560), "white")
    d = ImageDraw.Draw(img)
    y = 30
    for text, _ in LINES:
        # Use the default bitmap font scaled up via spacing so the test stays font-agnostic.
        d.text((40, y), text, fill="black")
        y += 32
    d.rectangle([20, 20, 880, 540], outline="black", width=2)
    img.save(OUT)
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
