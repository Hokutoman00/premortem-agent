"""DemoDataStore — an in-memory stand-in for an ERP / AP ledger.

Probes read from this store. In production, swap this class for an adapter over the real
ledger (the probe API is the seam). The data is hand-built to make the demo scenarios
deterministic and to give every catastrophe-registry probe something real to check.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class Vendor:
    vendor_id: str
    name: str
    approved: bool
    registered_country: str
    tax_id: str
    onboarded: date
    last_paid_iban: str | None = None


@dataclass
class Payment:
    invoice_id: str
    vendor_id: str
    amount: float
    currency: str
    iban: str
    paid_on: date


@dataclass
class DemoDataStore:
    vendors: dict[str, Vendor] = field(default_factory=dict)
    history: list[Payment] = field(default_factory=list)

    # --- read-only query surface used by probes ------------------------
    def vendor(self, vendor_id: str) -> Vendor | None:
        return self.vendors.get(vendor_id)

    def payments_for(self, vendor_id: str) -> list[Payment]:
        return [p for p in self.history if p.vendor_id == vendor_id]

    def last_iban(self, vendor_id: str) -> str | None:
        pays = sorted(self.payments_for(vendor_id), key=lambda p: p.paid_on)
        if pays:
            return pays[-1].iban
        v = self.vendor(vendor_id)
        return v.last_paid_iban if v else None

    def amount_stats(self, vendor_id: str) -> tuple[float, float] | None:
        amounts = [p.amount for p in self.payments_for(vendor_id)]
        if not amounts:
            return None
        mean = sum(amounts) / len(amounts)
        mx = max(amounts)
        return mean, mx


def default_store() -> DemoDataStore:
    """The canonical demo ledger used by tests, the offline demo, and the web UI."""
    store = DemoDataStore()
    store.vendors = {
        "V-1007": Vendor(
            vendor_id="V-1007", name="Acme Supplies Ltd", approved=True,
            registered_country="DE", tax_id="DE811234567",
            onboarded=date(2023, 4, 1),
            last_paid_iban="DE89370400440532013000",
        ),
        "V-2210": Vendor(
            vendor_id="V-2210", name="Globex Components GmbH", approved=True,
            registered_country="DE", tax_id="DE998877665",
            onboarded=date(2022, 11, 12),
            last_paid_iban="DE21500105170123456789",
        ),
        "V-9001": Vendor(  # unapproved, brand-new — used by the fraud scenario
            vendor_id="V-9001", name="Bright Star Trading", approved=False,
            registered_country="GB", tax_id="GB000000000",
            onboarded=date(2026, 6, 14),
            last_paid_iban=None,
        ),
    }
    store.history = [
        Payment("INV-2025-9912", "V-1007", 4120.00, "USD", "DE89370400440532013000", date(2026, 3, 14)),
        Payment("INV-2026-0118", "V-1007", 5380.50, "USD", "DE89370400440532013000", date(2026, 4, 19)),
        Payment("INV-2026-0290", "V-1007", 4990.00, "USD", "DE89370400440532013000", date(2026, 5, 21)),
        Payment("INV-2026-0041", "V-2210", 12750.00, "EUR", "DE21500105170123456789", date(2026, 4, 2)),
    ]
    return store
