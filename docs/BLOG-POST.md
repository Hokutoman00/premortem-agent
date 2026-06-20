# Why confidence is not enough: falsification before an autopilot acts

*Draft companion post for PreMortem (Qwen Cloud Track 4). Ready to publish; not yet posted.*

---

Ask a large language model "is this payment safe to send?" and a fluent model will usually
tell you yes. It is the wrong question. It is a *confirmation-seeking* question, and a model
trained to be helpful is very good at confirming. For a chatbot that costs you nothing. For an
**autopilot about to wire money**, that reflex is the whole problem.

PreMortem is an accounts-payable agent built on the opposite reflex. Before it pays an invoice
— an action it **cannot undo** — it does not ask whether the plan is good. It tries to **prove
the plan wrong**, and pays only when it has attacked its own plan and failed.

## The move: ask the disconfirming question

The shift is small to describe and changes everything downstream. Instead of *"is this plan
good?"* (confirmation), the agent asks *"here are eleven ways this exact payment could be a
catastrophe — can I confirm any of them with a cheap, read-only check?"* (falsification).

So a payment runs a gauntlet:

1. **Two regimes.** Reversible actions — draft, preview, simulate — skip the ritual and run
   immediately. The pre-mortem compute is spent *only* where a mistake is expensive and
   irreversible. Paranoia you can't afford everywhere, aimed where it pays for itself.
2. **Enumerate the failures.** Modes come from three places: a fixed registry of known AP
   catastrophes, an append-only **memory of past real misses**, and extra modes proposed by
   `qwen-max`. The model widens the search; it does not get the final say.
3. **Try to confirm each one.** Every mode has a **read-only probe** — payment history, vendor
   registration, account diffs, and a `qwen-vl-max` read of the invoice *image* checked against
   the structured payment instruction.
4. **Decide by what survived.** Confirm a danger at or above the block threshold → **stop and
   escalate**. A danger you *cannot* check that is catastrophic or remembered from a real past
   failure → **escalate rather than guess**. Only a plan that survived every attack gets paid.

## The check a text-only agent cannot build

The scenario that makes the case is `tampered_img`. The structured payment record is *clean* —
right vendor, right amount, a plausible account. A text-only agent reading the fields pays it.

But the **invoice image** shows a *different* bank account than the one in the payment
instruction. `qwen-vl-max` reads the document, and an image-consistency probe catches the
mismatch the structured data hides:

```
→ call_tool image_consistency
    ← confirmed=True  evidence='請求書画像の口座 GB44BARC20038512345678 != 支払指示 DE89370400440532013000'
```

That is not a prompt trick. It requires real multimodal perception — the Qwen leg of the
architecture — and it is the difference between an agent that *talks* about safety and one that
*has* a check a single-modality model structurally cannot.

## No logprobs? Then confidence has to come from evidence

Qwen Cloud doesn't expose token logprobs, which kills the naive "ask the model how sure it is"
path. Good — that constraint *is* the design. PreMortem recovers uncertainty at the application
layer: it samples the enumeration leg N=5 times and measures **modal agreement**. And it does
not merely *report* the number — it **wires it into the verdict**. If the model cannot agree
with itself (agreement < 0.6) about an irreversible payment's risks, the engine injects a
catastrophic, unprobeable `llm_enumeration_unstable` mode that escalates to a human through the
same rule as any danger it cannot check. An unstable risk-read can never be silently cleared
into a payment.

There's a subtler trap here too: the text and vision legs **share weights**, so two confident
LLM legs can be confidently wrong *together*. PreMortem treats the deterministic probes as the
anchor and demotes the correlated LLM legs to a pre-filter. The money decision rests on evidence
that doesn't come from the model.

## The probes are *called*, not just exposed

All eleven read-only checks are surfaced as **MCP tools**, so any MCP-speaking agent can ground
its reasoning on them. "Exposed" is cheap to claim, so PreMortem ships the other half: a real MCP
client that spawns the server over stdio and **invokes** the tools over the protocol —

```
→ initialize     ← server: premortem-probes (MCP 2025-11-25)
→ list_tools     ← 11 read-only probe tools
→ call_tool image_consistency  ← confirmed=True   [the vision leg, over the wire]
→ call_tool approval_list      ← confirmed=False  [a clean clear, over the wire]
```

— a genuine JSON-RPC round-trip, regression-tested, with a saved transcript in the repo.

## It learns from the miss no probe can see

The most honest scenario is the one where every cheap check **passes** and the agent **should**
pay — and the payment is still a mistake. A clean payment to an approved vendor clears every
pre-payment probe, so it pays. Then a human discovers the goods were never delivered — a failure
no *pre*-payment check can see.

The human teaches the agent once. That failure is appended to memory. The **next** payment that
fingerprints to the same vendor now re-enumerates `goods_not_received` as a seeded mode — and
since there's still no cheap probe for it, the agent **escalates instead of paying again**.
*Day 1 paid, Day 2 stopped.* The enumeration isn't purely model-imagined; it's grounded in what
actually went wrong before, and it compounds.

## Why this shape matters beyond invoices

Accounts payable is a clean place to show it, but the structure is general: *gate every
irreversible action behind a falsification step, anchor the verdict on evidence the model didn't
produce, and remember every real miss so the next pre-mortem is sharper.* Confidence is what a
fluent model offers for free. For an autopilot, the thing worth building is the **disconfirming
question** — and the discipline to pay only when you tried to prove yourself wrong and couldn't.

---

*PreMortem is open source (MIT). Reasoning on `qwen-max`, invoice perception on `qwen-vl-max`,
both through Qwen Cloud; backend on Alibaba Cloud. Every decision path reproduces offline on a
deterministic mock — `python scripts/run_demo.py`.*
