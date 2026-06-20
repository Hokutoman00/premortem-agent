"""FastAPI surface — deployable on Alibaba Cloud (ECS / Function Compute).

Endpoints:
  GET  /health                 liveness
  GET  /demo/scenarios         the five built-in demo payments
  GET  /demo/scenario/{name}   decide one built-in scenario (decision + explanation)
  POST /assess                 decide on a PaymentPlan (optional image_ref)
  POST /learn                  record a human override into failure-memory
  GET  /memory                 inspect what the agent has learned

Stateless except for the in-process FailureMemory, which persists to the configured
SQLite path so learning survives restarts (set PREMORTEM_MEMORY_DB).
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from .agent import PreMortemAgent
from .config import CONFIG
from .memory.failure_memory import FailureMemory
from .scenarios import SCENARIOS, scenario_plan
from .types import PaymentPlan

app = FastAPI(title="PreMortem", version="0.1.0",
              description="AP autopilot that tries to prove its own plan wrong before it pays.")

# One agent per process; memory persists to the configured DB path.
_agent = PreMortemAgent(memory=FailureMemory(CONFIG.memory_db))


class AssessRequest(BaseModel):
    invoice_id: str
    vendor_name: str
    vendor_id: str
    amount: float
    currency: str = "USD"
    bank: dict[str, str] = Field(default_factory=dict)
    action: str = "pay_invoice"
    source_image_facts: dict[str, str] = Field(default_factory=dict)
    image_ref: str | None = None


class LearnRequest(BaseModel):
    invoice_id: str
    vendor_id: str
    amount: float
    failure_mode: str
    evidence: str
    label: str = "human_override"


def _plan(req: AssessRequest) -> PaymentPlan:
    return PaymentPlan(
        invoice_id=req.invoice_id, vendor_name=req.vendor_name, vendor_id=req.vendor_id,
        amount=req.amount, currency=req.currency, bank=req.bank, action=req.action,
        source_image_facts=req.source_image_facts,
    )


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "provider": CONFIG.provider,
            "memory_size": _agent.memory.count()}


@app.get("/demo/scenarios")
def demo_scenarios() -> dict[str, Any]:
    return {"scenarios": list(SCENARIOS.keys())}


@app.post("/assess")
def assess(req: AssessRequest) -> dict[str, Any]:
    return _agent.decide_and_explain(_plan(req), req.image_ref)


@app.post("/learn")
def learn(req: LearnRequest) -> dict[str, Any]:
    plan = PaymentPlan(invoice_id=req.invoice_id, vendor_name="", vendor_id=req.vendor_id,
                       amount=req.amount, currency="USD", bank={})
    rid = _agent.learn_from_human(plan, req.failure_mode, req.evidence, req.label)
    return {"recorded_id": rid, "memory_size": _agent.memory.count()}


@app.get("/memory")
def memory() -> dict[str, Any]:
    rows = [dict(r) for r in _agent.memory.all()]
    return {"count": len(rows), "rows": rows}


@app.get("/demo/scenario/{name}")
def demo_scenario(name: str) -> dict[str, Any]:
    plan, image_ref = scenario_plan(name)
    if plan is None:
        return {"error": f"unknown scenario '{name}'",
                "available": list(SCENARIOS.keys())}
    return {"scenario": name, **_agent.decide_and_explain(plan, image_ref)}
