#!/usr/bin/env python3
"""Offline, creds-free demo of the full pre-mortem loop.

Run:  python scripts/run_demo.py      (uses MockAdapter; no DashScope key needed)

It walks the five built-in scenarios, then stages the learning drama (day1 miss ->
human override -> failure-memory -> day2 catch) that the 3-minute video dramatizes.
"""
from __future__ import annotations

import sys
from pathlib import Path

# The demo prints em-dashes and Japanese notes; force UTF-8 so it does not crash on a
# legacy Windows console (cp932) where the default codec cannot encode them.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from premortem.agent import PreMortemAgent          # noqa: E402
from premortem.scenarios import SCENARIOS, scenario_plan  # noqa: E402
from premortem.types import PaymentPlan             # noqa: E402


def _line(title: str) -> None:
    print("\n" + "=" * 68)
    print(title)
    print("=" * 68)


def _show(agent: PreMortemAgent, name: str) -> None:
    plan, image_ref = scenario_plan(name)
    if image_ref:  # ground on the VL read so explain() and the decision use one plan
        plan = agent.ground(plan, image_ref)
    decision = agent.assess(plan)
    ex = agent.explain(plan)
    verb = "PAID" if decision.executed else "STOPPED"
    print(f"\n[{name}]  action={plan.action}  amount={plan.amount} {plan.currency}")
    print(f"  reversibility : {decision.reversibility.value}")
    print(f"  enumerated    : {len(ex['enumerated'])} modes "
          f"(memory/registry/llm seed)")
    print(f"  verdict       : {ex['verdict']}  -> {verb}")
    print(f"  cleared       : {len(ex['cleared'])} probes ruled out")
    if ex["confirmed"]:
        for c in ex["confirmed"]:
            print(f"    CONFIRMED   : {c['mode']} — {c['evidence']}")
    if ex["unfalsifiable"]:
        print(f"    unfalsifiable: {ex['unfalsifiable']}")
    if ex["residual"]:
        print(f"    residual     : {ex['residual']}")
    print(f"  reason        : {decision.reason}")


def main() -> None:
    agent = PreMortemAgent()  # mock provider, in-memory ledger + memory

    _line("PART 1 — five payments through the pre-mortem gate")
    for name in SCENARIOS:
        _show(agent, name)

    _line("PART 2 — the learning loop (v8): day1 miss -> override -> day2 catch")
    # Day 1: a clean payment to an approved vendor, known account, in-distribution amount.
    # Every document field agrees with the records (incl. tax-id and PO — so even the modes
    # PART 1's doc_mismatch taught the shared agent for V-1007 are probed and cleared). The
    # engine PROCEEDs and PAYS. It is a real miss: the failure (goods never delivered) is
    # invisible to any cheap pre-payment probe.
    day1_plan = PaymentPlan(
        invoice_id="INV-2026-0501", vendor_name="Acme Supplies Ltd",
        vendor_id="V-1007", amount=4750.00, currency="USD",
        bank={"iban": "DE89370400440532013000", "name": "Acme Supplies Ltd"},
        action="pay_invoice",
        source_image_facts={"iban_on_doc": "DE89370400440532013000",
                            "tax_id_on_doc": "DE811234567", "po_amount": "4750.00"},
    )
    ex1 = agent.explain(day1_plan)
    d1 = agent.assess(day1_plan)
    print(f"\n[day1]  verdict={ex1['verdict']}  executed={d1.executed}  "
          f"(cleared={len(ex1['cleared'])}, memory_size={agent.memory.count()})")
    print("        -> PAID. A human later finds the goods were never delivered — a "
          "failure no pre-payment probe could see.")

    # Human override teaches the agent the new failure mode (invariant I4).
    agent.learn_from_human(
        day1_plan, failure_mode="goods_not_received",
        evidence="支払済だが納品実績なし（受領照合の欠落・人間が事後発見）",
        label="human_override",
    )
    print(f"[learn] recorded human override -> memory_size={agent.memory.count()}")

    # Day 2: the same vendor + amount fingerprints to the remembered failure. It is now
    # seeded back in, has no cheap probe, and is memory-grounded -> the engine ESCALATES
    # to a human instead of paying again (invariant I5). The pre-mortem improved itself.
    day2 = PaymentPlan(
        invoice_id="INV-2026-0588", vendor_name="Acme Supplies Ltd",
        vendor_id="V-1007", amount=4750.00, currency="USD",
        bank={"iban": "DE89370400440532013000", "name": "Acme Supplies Ltd"},
        action="pay_invoice",
        # Same clean document fields as day1 — every probeable mode (incl. the tax-id/PO ones
        # PART 1 taught) clears, leaving the learned goods_not_received as the *only*
        # unprobeable, memory-grounded danger that drives the escalation.
        source_image_facts={"iban_on_doc": "DE89370400440532013000",
                            "tax_id_on_doc": "DE811234567", "po_amount": "4750.00"},
    )
    ex2 = agent.explain(day2)
    d2 = agent.assess(day2)
    seeded = [m for m in ex2["enumerated"] if m["source"] == "memory"]
    print(f"\n[day2]  memory-seeded modes now enumerated: {[m['id'] for m in seeded]}")
    print(f"        verdict={ex2['verdict']}  executed={d2.executed}  "
          f"(escalated on: {ex2['unfalsifiable']})")
    print("        -> the SAME failure is caught before payment. "
          "Day1 PAID, day2 STOPPED — the gate learned.")

    _line("DONE — every branch ran on the mock provider, no credentials used.")


if __name__ == "__main__":
    main()
