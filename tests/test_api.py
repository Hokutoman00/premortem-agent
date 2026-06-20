"""FastAPI surface — the deployable contract. Runs against the in-process app with the
mock provider (conftest forces an in-memory DB), so no network and no creds. The app's
_agent is process-global, so assertions use relative counts rather than absolute state."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from premortem.api import app

client = TestClient(app)


def test_health_reports_mock_provider():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["provider"] == "mock"


def test_scenarios_lists_all_built_in():
    names = client.get("/demo/scenarios").json()["scenarios"]
    assert set(names) == {"safe", "bank_swap", "tampered_img", "new_vendor", "doc_mismatch"}


@pytest.mark.parametrize("name,verdict,executed", [
    ("safe", "PROCEED", True),
    ("bank_swap", "BLOCK", False),
    ("tampered_img", "BLOCK", False),
    ("new_vendor", "BLOCK", False),
    ("doc_mismatch", "BLOCK", False),
])
def test_demo_scenario_endpoint(name, verdict, executed):
    body = client.get(f"/demo/scenario/{name}").json()
    assert body["scenario"] == name
    assert body["explain"]["verdict"] == verdict
    assert body["decision"]["executed"] is executed
    assert body["decision"]["verdict"]["decision"] == body["explain"]["verdict"]


def test_unknown_scenario_returns_available_list():
    body = client.get("/demo/scenario/nope").json()
    assert "error" in body and "safe" in body["available"]


def test_assess_clean_payment_proceeds():
    # A genuinely clean invoice: every document field agrees with the records, so even modes
    # the global agent has learned for V-1007 (e.g. a past tax-id/PO mismatch from the
    # doc_mismatch demo) are *probed and cleared* rather than escalated. This pins that a
    # fully-consistent payment proceeds regardless of what the shared memory has seen before.
    r = client.post("/assess", json={
        "invoice_id": "INV-API-1", "vendor_name": "Acme Supplies Ltd",
        "vendor_id": "V-1007", "amount": 4750.0, "currency": "USD",
        "bank": {"iban": "DE89370400440532013000"},
        "source_image_facts": {
            "iban_on_doc": "DE89370400440532013000",
            "tax_id_on_doc": "DE811234567",   # V-1007's real tax id -> tax_id_check clears
            "po_amount": "4750.00",            # agrees with the amount -> po_match clears
        },
    })
    assert r.json()["explain"]["verdict"] == "PROCEED"


def test_assess_swapped_bank_blocks():
    r = client.post("/assess", json={
        "invoice_id": "INV-API-2", "vendor_name": "Acme Supplies Ltd",
        "vendor_id": "V-1007", "amount": 4880.0, "currency": "USD",
        "bank": {"iban": "GB44BARC20038512345678"},
        "source_image_facts": {"iban_on_doc": "GB44BARC20038512345678"},
    })
    out = r.json()
    assert out["explain"]["verdict"] == "BLOCK"
    assert out["decision"]["executed"] is False


def test_learn_increments_memory_and_is_inspectable():
    before = client.get("/memory").json()["count"]
    r = client.post("/learn", json={
        "invoice_id": "INV-API-3", "vendor_id": "V-1007", "amount": 4750.0,
        "failure_mode": "goods_not_received", "evidence": "納品なし",
    })
    assert r.json()["memory_size"] == before + 1
    rows = client.get("/memory").json()["rows"]
    assert any(row["failure_mode"] == "goods_not_received" for row in rows)
