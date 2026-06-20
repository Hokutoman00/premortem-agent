# Demo video storyboard (~3:00)

Target: the Qwen Cloud rubric's **Presentation & Documentation (15%)** — "clear demo, key logic
visualized" — while reinforcing **Technical Depth** and **Innovation** by *showing the
falsification happen*, not just narrating it. Format: screen recording, voice-over, ~3 minutes.
Capture at the resolution `video-pipeline.md` specifies; assemble with `video-build.mjs`.

The whole video runs on the **live Alibaba Cloud deployment** (`provider: dashscope`). Note
this 3-minute demo is **not** the cloud-deployment proof: the official rules ask for that as a
**separate short recording** — see [§"Separate Alibaba Cloud proof recording"](#separate-alibaba-cloud-proof-recording-20-30s--distinct-required-artifact) below. Record both.

---

## Beat sheet

| # | Time | On screen | Voice-over (script) |
|---|------|-----------|--------------------|
| 1 | 0:00–0:16 | Title card → the web UI header | "Most AI agents decide by asking the model *'is this plan good?'* — and a fluent model says yes. PreMortem does the opposite. Before it pays an invoice it tries to **prove its own plan wrong**." |
| 2 | 0:16–0:32 | `curl /health` → `provider: dashscope`, Alibaba console tab visible | "This is running on Alibaba Cloud, reasoning on `qwen-max`, reading invoices with `qwen-vl-max`. Everything you'll see is live." |
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
- Show the Alibaba Cloud console briefly (beat 2) and the GitHub repo once (beat 9). The console
  shot here is for *context*; the **standalone deployment proof is recorded separately** (next
  section) — do not rely on this 3-min demo to satisfy that artifact.
- Total spoken words ~340–370 at a calm pace ≈ 3:00.

---

## Separate Alibaba Cloud proof recording (20–30s) — distinct required artifact

The official rules count "the backend running on Alibaba Cloud" as a **separate** required
artifact, not a beat of the demo. Record a short, unedited clip — the point is *unfaked liveness*,
so keep it raw:

1. The Alibaba Cloud **ECS/Function Compute console** in frame, showing the running instance
   (region + public IP visible).
2. From your laptop, `curl http://<PUBLIC_IP>:8000/health` → `{"status":"ok","provider":"dashscope",...}`
   — proves the public endpoint is the deployed backend, not localhost.
3. One live falsification call against the cloud host:
   `curl http://<PUBLIC_IP>:8000/demo/scenario/tampered_img` → `verdict: BLOCK` with
   `invoice_image_mismatch` — proves `qwen-vl-max` is actually wired on the deployed instance.

Upload this as its own link (or as a clearly separate segment) alongside the 3-minute demo. It is
the artifact that converts "deployed on Alibaba Cloud" from claimed to shown; do not skip it.
