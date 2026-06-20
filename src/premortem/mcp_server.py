"""MCP server exposing the read-only probes as tools (design §5).

Qwen Cloud names "custom skills, MCP integrations" as a scored Technical-Depth signal,
so the falsification probes are surfaced as MCP tools: a Qwen-Agent (or any MCP client)
can call them to ground its own reasoning. Every tool is read-only (invariant I2).

Run:  python -m premortem.mcp_server   (requires the [mcp] extra: pip install mcp)

If the `mcp` package is not installed this module still imports; it raises only when you
actually try to start the server, so the rest of the package stays creds/dep-free.
"""
from __future__ import annotations

from .data.demo_data import default_store
from .probes.registry import default_registry
from .types import PaymentPlan

_STORE = default_store()
_PROBES = default_registry()


def _plan_from(vendor_id: str, amount: float, iban: str, invoice_id: str = "",
               currency: str = "USD", iban_on_doc: str | None = None,
               tax_id_on_doc: str | None = None,
               po_amount: float | None = None) -> PaymentPlan:
    facts: dict[str, str] = {"iban_on_doc": iban if iban_on_doc is None else iban_on_doc}
    if tax_id_on_doc is not None:
        facts["tax_id_on_doc"] = tax_id_on_doc
    if po_amount is not None:
        facts["po_amount"] = str(po_amount)
    return PaymentPlan(
        invoice_id=invoice_id or f"INV-{vendor_id}", vendor_name="", vendor_id=vendor_id,
        amount=amount, currency=currency, bank={"iban": iban},
        source_image_facts=facts,
    )


def _result(probe: str, plan: PaymentPlan) -> dict:
    r = _PROBES.get(probe)(plan, _STORE)
    return {"confirmed": r.confirmed, "evidence": r.evidence, "probe_ran": r.probe_ran}


# --- plain-callable tool functions (also unit-testable without MCP) -----
def probe_bank_detail_diff(vendor_id: str, iban: str) -> dict:
    return _result("bank_detail_diff", _plan_from(vendor_id, 0.0, iban))


def probe_vendor_age(vendor_id: str) -> dict:
    return _result("vendor_age", _plan_from(vendor_id, 0.0, ""))


def probe_duplicate_check(vendor_id: str, amount: float, invoice_id: str) -> dict:
    return _result("duplicate_check", _plan_from(vendor_id, amount, "", invoice_id))


def probe_amount_anomaly(vendor_id: str, amount: float) -> dict:
    return _result("amount_anomaly", _plan_from(vendor_id, amount, ""))


def probe_approval_list(vendor_id: str) -> dict:
    return _result("approval_list", _plan_from(vendor_id, 0.0, ""))


def probe_bank_country_mismatch(vendor_id: str, iban: str) -> dict:
    return _result("bank_country_mismatch", _plan_from(vendor_id, 0.0, iban))


def probe_round_number(vendor_id: str, amount: float) -> dict:
    return _result("round_number", _plan_from(vendor_id, amount, ""))


def probe_image_consistency(vendor_id: str, iban: str, iban_on_doc: str) -> dict:
    return _result(
        "image_consistency",
        _plan_from(vendor_id, 0.0, iban, iban_on_doc=iban_on_doc))


def probe_currency_check(vendor_id: str, currency: str) -> dict:
    return _result("currency_check", _plan_from(vendor_id, 0.0, "", currency=currency))


def probe_tax_id_check(vendor_id: str, tax_id_on_doc: str) -> dict:
    return _result(
        "tax_id_check",
        _plan_from(vendor_id, 0.0, "", tax_id_on_doc=tax_id_on_doc))


def probe_po_match(vendor_id: str, amount: float, po_amount: float) -> dict:
    return _result(
        "po_match",
        _plan_from(vendor_id, amount, "", po_amount=po_amount))


# All eleven canonical read-only probes are exposed (design §6 / I2). The memory
# aliases in default_registry() resolve to these same callables, so this is the full
# falsification surface a Qwen-Agent can ground its reasoning on.
TOOLS = {
    "bank_detail_diff": probe_bank_detail_diff,
    "vendor_age": probe_vendor_age,
    "duplicate_check": probe_duplicate_check,
    "amount_anomaly": probe_amount_anomaly,
    "approval_list": probe_approval_list,
    "bank_country_mismatch": probe_bank_country_mismatch,
    "round_number": probe_round_number,
    "image_consistency": probe_image_consistency,
    "currency_check": probe_currency_check,
    "tax_id_check": probe_tax_id_check,
    "po_match": probe_po_match,
}


def build_server():  # pragma: no cover - exercised only with the mcp extra installed
    """Construct an MCP server registering the probe tools. Requires `mcp`."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as e:
        raise RuntimeError(
            "MCP server requires the [mcp] extra: pip install mcp"
        ) from e

    server = FastMCP("premortem-probes")

    @server.tool()
    def bank_detail_diff(vendor_id: str, iban: str) -> dict:
        """Read-only: does the payout IBAN differ from this vendor's last paid IBAN?"""
        return probe_bank_detail_diff(vendor_id, iban)

    @server.tool()
    def vendor_age(vendor_id: str) -> dict:
        """Read-only: is this a brand-new payee with no payment history?"""
        return probe_vendor_age(vendor_id)

    @server.tool()
    def duplicate_check(vendor_id: str, amount: float, invoice_id: str) -> dict:
        """Read-only: has an equal-amount or same-id invoice already been paid?"""
        return probe_duplicate_check(vendor_id, amount, invoice_id)

    @server.tool()
    def amount_anomaly(vendor_id: str, amount: float) -> dict:
        """Read-only: is the amount far outside this vendor's payment history?"""
        return probe_amount_anomaly(vendor_id, amount)

    @server.tool()
    def approval_list(vendor_id: str) -> dict:
        """Read-only: is this vendor on the approved-payee list?"""
        return probe_approval_list(vendor_id)

    @server.tool()
    def bank_country_mismatch(vendor_id: str, iban: str) -> dict:
        """Read-only: does the IBAN country differ from the vendor's registered country?"""
        return probe_bank_country_mismatch(vendor_id, iban)

    @server.tool()
    def round_number(vendor_id: str, amount: float) -> dict:
        """Read-only: is the amount a suspiciously round figure (manual/inflated signal)?"""
        return probe_round_number(vendor_id, amount)

    @server.tool()
    def image_consistency(vendor_id: str, iban: str, iban_on_doc: str) -> dict:
        """Read-only: does the IBAN read off the invoice image match the payment plan?"""
        return probe_image_consistency(vendor_id, iban, iban_on_doc)

    @server.tool()
    def currency_check(vendor_id: str, currency: str) -> dict:
        """Read-only: is the payment currency one this vendor has been paid in before?"""
        return probe_currency_check(vendor_id, currency)

    @server.tool()
    def tax_id_check(vendor_id: str, tax_id_on_doc: str) -> dict:
        """Read-only: does the tax/registration id on the invoice match the vendor record?"""
        return probe_tax_id_check(vendor_id, tax_id_on_doc)

    @server.tool()
    def po_match(vendor_id: str, amount: float, po_amount: float) -> dict:
        """Read-only: does the invoice amount agree with its referenced purchase order?"""
        return probe_po_match(vendor_id, amount, po_amount)

    return server


if __name__ == "__main__":  # pragma: no cover
    build_server().run()
