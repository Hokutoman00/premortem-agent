"""Live vision smoke test against real Qwen Cloud (`qwen-vl-max`).

SKIPPED by default. The whole suite is creds-free on the mock provider; this single test
is the one place we exercise the real DashScope `MultiModalConversation` leg, and it only
runs when a key is present:

    PREMORTEM_LLM=dashscope DASHSCOPE_API_KEY=... python -m pytest tests/test_vision_live.py

It is the regression guard for the claim "the vision leg actually reads an invoice image
on Qwen Cloud" — the leg a text-only competitor cannot build (SUBMISSION-DRAFT)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

_HAS_KEY = bool(os.environ.get("DASHSCOPE_API_KEY"))

pytestmark = pytest.mark.skipif(
    not _HAS_KEY,
    reason="live vision test requires DASHSCOPE_API_KEY (creds-gated; mock suite covers logic)",
)


def _sample_invoice_ref() -> str:
    """The shipped invoice fixture to read. Skips (self-describing) if it is ever removed, so
    a maintainer knows exactly what to restore to run the live leg for real."""
    cand = Path(__file__).parent / "fixtures" / "invoice_sample.png"
    if cand.exists():
        return str(cand)
    pytest.skip("no invoice image fixture found (place one at tests/fixtures/invoice_sample.png)")


def test_real_vl_reads_iban_from_invoice_image():
    from premortem.config import Config
    from premortem.llm.dashscope_adapter import DashScopeAdapter
    from premortem.perception.vision import VisionPerceiver

    image_ref = _sample_invoice_ref()
    # Go through the production VisionPerceiver so the live leg validates the SAME prompt the
    # deployed engine uses (incl. the document fields the doc-field probes read), not a
    # test-local prompt that could drift from production.
    perceiver = VisionPerceiver(DashScopeAdapter(Config.from_env()))
    facts = perceiver.read_invoice(image_ref)
    # The real model returns prose-wrapped or fenced JSON sometimes, but the perceiver parses
    # it down to a dict; the irreducible claim is that it read the printed IBAN back.
    assert isinstance(facts, dict)
    assert facts.get("iban_on_doc"), f"no iban_on_doc parsed from live read: {facts!r}"


def test_real_vl_tampered_scenario_blocks_on_image_mismatch():
    """The money shot, proven live: run the *actual* `tampered_img` scenario end-to-end on the
    real DashScope adapter (qwen-vl-max reads the shipped PNG, not the mock sidecar) and assert
    the BLOCK is driven by `invoice_image_mismatch`. This converts the demo's strongest claim —
    "the check a text-only model cannot build" — from asserted to demonstrated against the live
    model on the same image the video shows."""
    from premortem.agent import PreMortemAgent
    from premortem.config import Config
    from premortem.llm.dashscope_adapter import DashScopeAdapter
    from premortem.memory.failure_memory import FailureMemory
    from premortem.scenarios import scenario_plan

    plan, image_ref = scenario_plan("tampered_img")
    # scenario_plan resolves tampered_img to the absolute path of the shipped PNG, so the real
    # adapter sends a readable file:// URI to qwen-vl-max (a bare name would 404 on the cloud host).
    assert image_ref and Path(image_ref).exists(), (
        f"tampered_img must resolve to a shipped PNG for the live read; got {image_ref!r}")

    agent = PreMortemAgent(
        llm=DashScopeAdapter(Config.from_env()), memory=FailureMemory(":memory:"))
    out = agent.decide_and_explain(plan, image_ref)

    assert out["explain"]["verdict"] == "BLOCK", out["explain"]
    confirmed = {c["mode"] for c in out["decision"]["verdict"]["confirmed"]}
    assert "invoice_image_mismatch" in confirmed, (
        f"live qwen-vl-max did not drive the image-mismatch BLOCK; confirmed={confirmed}, "
        f"facts must show the GB IBAN read off the tampered PNG. explain={out['explain']}")
    assert out["decision"]["executed"] is False
