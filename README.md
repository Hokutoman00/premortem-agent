# PreMortem — prove the plan wrong before it pays

> An accounts-payable autopilot that, before an **irreversible** action (paying an invoice),
> enumerates how its own plan could be wrong, runs **read-only** grounding probes to try to
> *confirm* those failures, and executes only when it **cannot break its own plan**. Every
> miss it learns about is remembered, so the next pre-mortem is sharper.

Built for the **Global AI Hackathon Series with Qwen Cloud — Track 4: Autopilot Agent**.
Reasoning runs on **`qwen-max`**, invoice perception on **`qwen-vl-max`** (DashScope
MultiModalConversation), both through **Qwen Cloud**.

---

## ⚡ Judge quickstart (60 seconds, no credentials)

```bash
pip install -e ".[dev,mcp]"
python scripts/run_demo.py        # 5 payments through the pre-mortem gate + the learning loop
```

Expected verdicts (deterministic on the offline mock — reproduces byte-for-byte):

| Scenario | A text-only agent | **PreMortem** | Why PreMortem differs |
|----------|-------------------|---------------|-----------------------|
| `safe` | PAYS | **PROCEED → PAID** | 11 catastrophes enumerated, all 11 ruled out |
| `bank_swap` | PAYS | **BLOCK** | payout IBAN swapped; structured probes confirm |
| **`tampered_img`** | **PAYS** ❗ | **BLOCK** | structured plan is clean — only `qwen-vl-max` reading the **invoice image** catches the swapped account |
| **`doc_mismatch`** | **PAYS** ❗ | **BLOCK** | bank/amount clear — only the document's **tax-id + PO total** betray it |
| `new_vendor` | PAYS | **BLOCK** | unapproved payee, no history; escalates rather than guess |

The two **❗** rows are the thesis: *a confirmation-seeking agent pays them; PreMortem proves
its own plan wrong first.* `tampered_img` is the check **a text-only model cannot build**.

Two more things you can run in a minute:

```bash
python -m pytest -q                  # 101 mock tests creds-free (+2 live qwen-vl-max = 103 with a key)
python scripts/mcp_client_demo.py    # a real MCP client calls the probe tools over stdio
```

The MCP run spawns the probe server and **invokes** `image_consistency` & friends over the
protocol — a saved round-trip is at [docs/mcp-client-transcript.txt](docs/mcp-client-transcript.txt)
(the probes aren't just *exposed* as MCP, they're *called*). Everything below is detail.

---

## The idea in one paragraph

Most "agents" decide by asking a model *"is this plan good?"* — a confirmation-seeking
question a fluent model happily answers *yes*. PreMortem inverts it. For any action that
**cannot be undone**, it first writes down the ways the plan could be a catastrophe, then
spends its compute trying to **falsify the plan** — to *prove* one of those failures is real
using cheap, read-only checks. If it confirms a danger at or above the block threshold, it
**stops and escalates**. If a danger is real but it has *no way to check* (e.g. "the goods
were never delivered"), it refuses to guess and **escalates**. It pays only when it
attacked its own plan and could not break it. This is a pre-mortem, not a post-mortem: the
autopsy happens *before* the money moves.

A reversible action (draft, preview, read, simulate) skips the whole ritual and executes
immediately — pre-mortem compute is spent only where a mistake is expensive (two-regime policy).

---

## Why this needs Qwen specifically

The hardest fraud to catch is a **tampered invoice image** whose printed bank account differs
from the structured payment instruction. PreMortem reads the invoice with **`qwen-vl-max`**
and the `image_consistency` probe cross-checks the IBAN the model *saw on the document* against
the IBAN in the payment plan. That falsification leg is **a check a text-only competitor cannot
build** — it requires real multimodal perception, which is the Qwen leg of the architecture.

Qwen Cloud exposes **no logprobs**, so PreMortem recovers uncertainty at the application layer
via **self-consistency** (sample the enumeration leg N=5 times, measure modal agreement) plus the
grounding probes — the confidence comes from *evidence*, not from a token probability the API
doesn't return. And it is **wired into the verdict**, not just measured: if the model cannot agree
with itself (agreement < 0.6) about an irreversible payment's risks, the engine injects a
catastrophic, unprobeable `llm_enumeration_unstable` mode that escalates to a human through the
same falsification rule as any other danger it cannot check (`tests/test_self_consistency.py`).

---

## Run it in 30 seconds (no credentials)

The default provider is a deterministic **mock** adapter — every decision path runs offline
with no DashScope key, so you (and a judge) can reproduce every verdict.

```bash
pip install -e .            # or: pip install -r requirements.txt
python scripts/run_demo.py  # walks all 5 scenarios + the day1→day2 learning loop
```

Run the test suite — 101 tests run creds-free on the mock provider (in-memory SQLite), plus 2
live `qwen-vl-max` tests that un-skip with a `DASHSCOPE_API_KEY` (**103 total**):

```bash
pip install -e ".[dev]"
python -m pytest -q
```

Serve the API + web UI:

```bash
uvicorn premortem.api:app --reload      # http://127.0.0.1:8000
# then open web/index.html (it calls the API at 127.0.0.1:8000)
```

To run against **real Qwen Cloud**, set `PREMORTEM_LLM=dashscope` and `DASHSCOPE_API_KEY`
in `.env` (see [.env.example](.env.example)). The engine code is byte-for-byte identical in
mock and real mode — only the adapter changes.

---

## The five demo scenarios

| Scenario | What it is | Verdict | Acted |
|----------|-----------|---------|-------|
| `safe` | Approved vendor V-1007, known account, in-distribution amount | **PROCEED** | PAID |
| `bank_swap` | Same vendor, but the payment IBAN was swapped to a new GB account | **BLOCK** | STOPPED |
| `tampered_img` | Plan IBAN looks clean, but the **invoice image** shows a different account | **BLOCK** | STOPPED |
| `new_vendor` | Brand-new, unapproved vendor V-9001, no history, GB account | **BLOCK** | STOPPED |
| `doc_mismatch` | Structured plan is clean, but the **document's tax-id and PO total** disagree with the records | **BLOCK** | STOPPED |

`bank_swap` is caught by structured probes. `tampered_img` is caught **only** by the
`qwen-vl-max` vision leg — the structured plan alone looks fine. `doc_mismatch` is the
document-field analogue: bank and amount probes all clear, and only the tax-id and
PO-total probes fire — so a check on the structured fields alone would have paid it. Those
contrasts are the demo's spine.

> **Honest note on the offline mock.** In `tampered_img` the *real* `qwen-vl-max` reads the
> shipped invoice image and extracts the mismatching IBAN. The default **mock** adapter does
> **not** decode the PNG — it returns the ground-truth read keyed off the `_tampered` image ref,
> so the *engine logic* (vision read → image-consistency probe → BLOCK) is byte-identical and
> fully reproducible offline, while the actual pixel decoding is what the credentialed live run
> (and `tests/test_vision_live.py`) exercises. The mock makes the **decision path** reproducible,
> not the image OCR.

---

## The learning loop (the v8 displacement)

A clean payment to an approved vendor **passes** every cheap pre-payment probe and gets paid —
because the real failure (*goods never delivered*) is invisible to any check you can run before
the money moves. When a human later discovers the miss, they teach the agent:

```
POST /learn  { vendor_id: "V-1007", failure_mode: "goods_not_received", evidence: "..." }
```

That failure is appended to an **append-only failure memory** (SQLite). The *next* payment that
fingerprints to the same vendor now re-enumerates `goods_not_received` as a seeded failure mode.
It still has no cheap probe — so instead of paying again, the agent **escalates to a human**.
**Day 1 PAID, Day 2 STOPPED — the pre-mortem improved itself.** Enumeration is therefore not
purely model-imagined; it is grounded in *what actually went wrong before*.

---

## Architecture (one breath)

```
PaymentPlan ─▶ ReversibilityClassifier ─▶ reversible? ──yes──▶ execute now (no pre-mortem)
                                              │ no / unknown
                                              ▼
              enumerate failure modes  =  memory seed  +  catastrophe-registry floor  +  LLM extra
                                              │
                                              ▼
              falsify(): for each mode run its read-only probe (some via qwen-vl-max)
                                              │
              ┌───────────────────────────────┼───────────────────────────────┐
        confirmed ≥ threshold            confirmed < threshold            unfalsifiable
              ▼                                 ▼                               ▼
            BLOCK + remember               residual (advisory)         ESCALATE + remember
```

Full diagram and invariants: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

The probes are exposed as **MCP tools** (`src/premortem/mcp_server.py`) so the falsification
bank is reusable by any MCP-speaking agent — the "MCP integrations" the Qwen Cloud rubric names
under Technical Depth. And they are **called over the protocol**, not merely exposed:
`scripts/mcp_client_demo.py` is a real MCP client that spawns the server over stdio and invokes
the tools (saved transcript: [docs/mcp-client-transcript.txt](docs/mcp-client-transcript.txt);
round-trip regression-tested in `tests/test_mcp_server.py`).

---

## Safety invariants (enforced, tested)

| # | Invariant |
|---|-----------|
| I1 | An irreversible/unknown action **never executes** without a `PROCEED` verdict. |
| I2 | Every probe is **read-only** — falsification cannot itself move money or mutate state. |
| I3 | A confirmed failure **at or above the block threshold** → `BLOCK` + escalate. |
| I4 | Every block / human override / post-hoc miss is **appended to failure memory**. |
| I5 | A **catastrophic or memory-seeded** danger that cannot be falsified → `ESCALATE`; a lighter unprobeable danger is **surfaced as advisory residual**, never silently cleared into a payment. |
| I6 | LLM legs are correlated; the verdict **anchors on the non-LLM probe leg** where one exists. |

Each invariant has corresponding tests in [tests/](tests/) (`test_policy.py`,
`test_premortem.py`, `test_scenarios.py`).

---

## Layout

```
src/premortem/
  reversibility.py     two-regime gate (rules first, LLM only to break ties)
  premortem.py         enumerate + severity-graded falsify()
  policy.py            execute / block / escalate + write-back to memory
  agent.py             orchestrator (perception → engine → policy)
  probes/registry.py   read-only falsification probes (incl. image_consistency)
  perception/vision.py qwen-vl-max invoice reader
  memory/failure_memory.py   append-only SQLite learning store
  llm/                 QwenClient ABC · mock_adapter (default) · dashscope_adapter
  api.py               FastAPI surface (deployable on Alibaba Cloud)
  data/catastrophe_registry.json   11 catastrophe modes + severities
web/index.html         single-file demo UI
scripts/run_demo.py    offline, creds-free end-to-end demo
tests/                 103 tests (101 mock, creds-free · 2 live qwen-vl-max)
```

Deploy guide: [docs/DEPLOY-ALIBABA.md](docs/DEPLOY-ALIBABA.md) ·
Demo storyboard: [docs/DEMO-SCRIPT.md](docs/DEMO-SCRIPT.md) ·
Companion write-up: [docs/BLOG-POST.md](docs/BLOG-POST.md).

## License

MIT — see [LICENSE](LICENSE).
