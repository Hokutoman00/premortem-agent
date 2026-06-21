# Demo video storyboard (~3:00)

Target: the Qwen Cloud rubric's **Presentation & Documentation (15%)** — "clear demo, key logic
visualized" — while reinforcing **Technical Depth** and **Innovation** by *showing the
falsification happen*, not just narrating it. Format: screen recording, voice-over, ~3 minutes.
Capture at the resolution `video-pipeline.md` specifies; assemble with `video-build.mjs`.

**Architecture honesty ($0 path, 2026-06-21).** The engine runs locally (`premortem.api:app`);
the **model inference runs on Qwen Cloud (Alibaba Cloud)** — `qwen-max` reasoning and `qwen-vl-max`
perception, called from [`dashscope_adapter.py`](../src/premortem/llm/dashscope_adapter.py). So the
narration says "reasoning and invoice-reading run on Qwen Cloud," **not** "this backend is deployed
on Alibaba Cloud." The binding deploy-proof is a **code-file link**, not a recording (see
DEPLOY-ALIBABA.md banner) — so there is **no separate Alibaba-console clip** to record; the old
§"Separate Alibaba Cloud proof recording" is struck below.

The structural verdicts (safe=PROCEED, the four BLOCKs, the day1→day2 learning loop) are shown from
the **deterministic engine** (reproducible on the mock — the engine code is identical in both modes,
so the decision shown is the decision production runs). The **Qwen-irreplaceable perception leg** is
shown **genuinely live**: the `qwen-vl-max` read of the tampered invoice in beat 5 is backed by the
committed live transcript [`docs/live-vl-evidence.md`](live-vl-evidence.md). Do **not** narrate mock
output as if it were a live model call.

---

## Beat sheet

| # | Time | On screen | Voice-over (script) |
|---|------|-----------|--------------------|
| 1 | 0:00–0:16 | Title card → the web UI header | "Most AI agents decide by asking the model *'is this plan good?'* — and a fluent model says yes. PreMortem does the opposite. Before it pays an invoice it tries to **prove its own plan wrong**." |
| 2 | 0:16–0:32 | `curl /health` → `provider: dashscope` | "It reasons on `qwen-max` and reads invoices with `qwen-vl-max` — on Qwen Cloud, Alibaba Cloud's model platform. The decisions you'll see are the engine's; the invoice-reading you'll see is a live `qwen-vl-max` call." |
| 3 | 0:32–0:52 | Click **`safe`** → PROCEED / PAID, **11 cleared** | "A clean payment. The agent enumerates **eleven** ways this could be a catastrophe, runs read-only probes, rules **all eleven** out, finds no confirmable danger — and only **then** pays." |
| 4 | 0:52–1:15 | Click **`bank_swap`** → BLOCK / STOPPED; point at the two confirmed rows | "Same vendor — but the payout account was swapped. The pre-mortem **confirms** it: the IBAN differs from the last paid account, and the country doesn't match the vendor's registration. It stops and escalates. No money moves." |
| 5 | 1:15–1:45 | Click **`tampered_img`** → BLOCK; highlight `invoice_image_mismatch` | "Now the hard one. The structured payment looks **clean** — a text-only agent pays this. But the invoice **image** shows a different bank account. `qwen-vl-max` reads the document, and the image-consistency probe catches the mismatch the structured data hides. **This is the check a text-only model cannot build.**" |
| 6 | 1:45–2:05 | Click **`doc_mismatch`** → BLOCK; highlight `tax_id_mismatch` + `po_mismatch` | "Its document-field sibling. Bank and amount probes all **clear** — only the document betrays it: the printed tax-id isn't the vendor's, and the PO total doesn't match the amount. A check on the structured fields alone would have paid it." |
| 7 | 2:05–2:18 | Click **`new_vendor`** → BLOCK; show confirmed + escalate rows | "A brand-new, unapproved vendor with no history: confirmed unapproved and first-ever payment, plus a danger it *can't* check — so it escalates rather than guesses." |
| 8 | 2:18–2:48 | Click **Teach override**, then re-run `safe` → now **ESCALATE** | "Here's the part that compounds. This clean payment passed every probe and got paid — but the goods never arrived, a failure no pre-payment check can see. A human teaches the agent once. Now the **same** payment escalates instead of paying. The pre-mortem learned from a real miss — Day 1 paid, Day 2 stopped." |
| 9 | 2:48–3:00 | Architecture diagram (ARCHITECTURE.md mermaid) + repo URL | "Read-only probes, a severity-graded falsification engine, an append-only failure memory, and the probes exposed as MCP tools. Open source. It pays only when it cannot break its own plan." |

---

## Pre-flight (record these exact states)

Run the deployment, then in order:

```bash
curl http://<HOST>:8000/health                          # beat 2
curl http://<HOST>:8000/demo/scenario/safe              # beat 3
curl http://<HOST>:8000/demo/scenario/bank_swap         # beat 4
curl http://<HOST>:8000/demo/scenario/tampered_img      # beat 5
curl http://<HOST>:8000/demo/scenario/doc_mismatch      # beat 6
curl http://<HOST>:8000/demo/scenario/new_vendor        # beat 7
curl -X POST http://<HOST>:8000/learn -H 'Content-Type: application/json' \
  -d '{"invoice_id":"INV-2026-0501","vendor_id":"V-1007","amount":5120.0,
       "failure_mode":"goods_not_received","evidence":"支払済だが納品実績なし","label":"human_override"}'
curl http://<HOST>:8000/demo/scenario/safe              # beat 8 — now ESCALATE
```

The web UI (`web/index.html`) drives all of this with clicks, which records better than curl —
use the UI for the on-screen action and keep a terminal in frame only for beat 2 (`/health`).

## Capture notes

- **Beat 5 is the money shot** — linger on the `invoice_image_mismatch` confirmed row and say
  the words "the check a text-only model cannot build." That single contrast is the
  differentiation thesis and the Qwen-irreplaceability argument in one frame.
- Beats 5 and 6 are a **pair** (image leg + document-field leg) — keep them back-to-back so the
  "structured data looks clean, the document doesn't" theme lands twice.
- Keep the **failure-memory panel** visible during beat 8 so the new `goods_not_received` row
  appears as you teach it — the learning is *shown*, not claimed.
- Show the GitHub repo once (beat 9). No Alibaba Cloud console shot is needed — the deploy-proof is
  a code-file link, not an on-screen instance.
- Total spoken words ~340–370 at a calm pace ≈ 3:00.

---

## ~~Separate Alibaba Cloud proof recording~~ — STRUCK ($0 path, 2026-06-21)

**Not required.** The official rules satisfy "Proof of Alibaba Cloud Deployment" with **a link to a
code file in the repo that uses Alibaba Cloud services/APIs** —
[`src/premortem/llm/dashscope_adapter.py`](../src/premortem/llm/dashscope_adapter.py), backed by the
live transcript [`docs/live-vl-evidence.md`](live-vl-evidence.md). There is **no live ECS instance**
to film and **no separate clip** to record. The single 3-minute demo above is the only video
artifact. (Verified against the official rules page; see DEPLOY-ALIBABA.md banner.)
