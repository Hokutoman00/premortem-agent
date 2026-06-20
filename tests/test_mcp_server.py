"""MCP surface (design §6). The probe bank is exposed as MCP tools so any Qwen-Agent can
ground its reasoning on the read-only checks. These tests pin the contract WITHOUT needing
the optional `mcp` extra installed: they call the plain tool functions directly and assert
the full canonical probe set is surfaced and read-only-shaped."""
from __future__ import annotations

import asyncio

import pytest

from premortem import mcp_server
from premortem.probes.registry import (
    bank_country_mismatch, bank_detail_diff, amount_anomaly, approval_list,
    currency_check, duplicate_check, image_consistency, po_match, round_number,
    tax_id_check, vendor_age,
)

# The eleven canonical probe functions defined in the registry module.
_CANONICAL = {
    "bank_detail_diff", "vendor_age", "duplicate_check", "amount_anomaly",
    "approval_list", "bank_country_mismatch", "round_number", "image_consistency",
    "currency_check", "tax_id_check", "po_match",
}


def test_all_canonical_probes_are_exposed():
    assert set(mcp_server.TOOLS) == _CANONICAL


def test_every_tool_returns_the_readonly_result_shape():
    # Smoke-call each tool with minimal valid args; each must return the {confirmed,
    # evidence, probe_ran} shape and never raise (invariant I2: read-only, total).
    calls = {
        "bank_detail_diff": dict(vendor_id="V-1007", iban="DE89370400440532013000"),
        "vendor_age": dict(vendor_id="V-1007"),
        "duplicate_check": dict(vendor_id="V-1007", amount=4750.0, invoice_id="INV-X"),
        "amount_anomaly": dict(vendor_id="V-1007", amount=4750.0),
        "approval_list": dict(vendor_id="V-1007"),
        "bank_country_mismatch": dict(vendor_id="V-1007", iban="DE89370400440532013000"),
        "round_number": dict(vendor_id="V-1007", amount=5000.0),
        "image_consistency": dict(vendor_id="V-1007", iban="DE89370400440532013000",
                                  iban_on_doc="GB44BARC20038512345678"),
        "currency_check": dict(vendor_id="V-1007", currency="USD"),
        "tax_id_check": dict(vendor_id="V-1007", tax_id_on_doc="DE811234567"),
        "po_match": dict(vendor_id="V-1007", amount=4750.0, po_amount=4750.0),
    }
    assert set(calls) == _CANONICAL  # the test itself covers every tool
    for name, kwargs in calls.items():
        out = mcp_server.TOOLS[name](**kwargs)
        assert set(out) == {"confirmed", "evidence", "probe_ran"}, name
        assert isinstance(out["confirmed"], bool), name


def test_image_consistency_tool_catches_doc_mismatch():
    # The Qwen-irreplaceable leg, surfaced over MCP: doc IBAN != plan IBAN -> confirmed.
    out = mcp_server.TOOLS["image_consistency"](
        vendor_id="V-1007", iban="DE89370400440532013000",
        iban_on_doc="GB44BARC20038512345678")
    assert out["confirmed"] is True


def test_round_number_tool_confirms_round_amount():
    assert mcp_server.TOOLS["round_number"](vendor_id="V-1007", amount=5000.0)["confirmed"]
    assert not mcp_server.TOOLS["round_number"](vendor_id="V-1007", amount=4750.0)["confirmed"]


def test_tax_id_and_po_tools_confirm_mismatch():
    # The two new three-way-match legs, surfaced over MCP.
    assert mcp_server.TOOLS["tax_id_check"](
        vendor_id="V-1007", tax_id_on_doc="DE999999999")["confirmed"] is True
    assert mcp_server.TOOLS["po_match"](
        vendor_id="V-1007", amount=4750.0, po_amount=4000.0)["confirmed"] is True
    # Agreeing values clear.
    assert mcp_server.TOOLS["po_match"](
        vendor_id="V-1007", amount=4750.0, po_amount=4750.0)["confirmed"] is False


def test_exposed_tools_cover_the_registry_callables():
    # Guard against drift: the tool set names the same probes the registry implements.
    registry_fns = {
        bank_detail_diff, vendor_age, duplicate_check, amount_anomaly, approval_list,
        bank_country_mismatch, round_number, image_consistency, currency_check,
        tax_id_check, po_match,
    }
    assert len(registry_fns) == len(_CANONICAL) == len(mcp_server.TOOLS)


def test_build_server_registers_every_tool():
    # Gap #3: build_server() is the real MCP wiring (normally `# pragma: no cover`).
    # When the `mcp` extra is installed, prove it registers exactly the canonical set —
    # otherwise the @server.tool() wrappers could drift from TOOLS unnoticed.
    pytest.importorskip("mcp")
    server = mcp_server.build_server()
    registered = {t.name for t in asyncio.run(server.list_tools())}
    assert registered == _CANONICAL


def test_mcp_client_round_trip_over_stdio():
    """The other half of the MCP claim: a real client spawns the server over stdio and
    *calls* a tool through the protocol (not a Python function call). Proves the
    `scripts/mcp_client_demo.py` evidence is a genuine JSON-RPC round-trip. Gated on the
    `mcp` extra; spawns a subprocess so it is the one slow MCP test."""
    pytest.importorskip("mcp")
    import json
    import sys
    from pathlib import Path

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    src = str(Path(__file__).resolve().parents[1] / "src")

    async def _go():
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "premortem.mcp_server"],
            env={"PYTHONPATH": src, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                res = await session.call_tool(
                    "image_consistency",
                    dict(vendor_id="V-1007", iban="DE89370400440532013000",
                         iban_on_doc="GB44BARC20038512345678"))
                return {t.name for t in listed.tools}, res

        # unreachable
    names, res = asyncio.run(_go())
    assert names == _CANONICAL
    # the dict comes back as JSON in a text content block (or structured content)
    payload = getattr(res, "structuredContent", None)
    if isinstance(payload, dict):
        payload = payload.get("result", payload)
    else:
        payload = json.loads(res.content[0].text)
    assert payload["confirmed"] is True and payload["probe_ran"] is True
