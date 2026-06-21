# Proof of Alibaba Cloud services/API usage

This one-pager is the single place a judge can verify how PreMortem uses Alibaba Cloud,
exactly as the hackathon rules ask for it.

## What the rules require

> "Proof of Alibaba Cloud Deployment — a link to a code file in their code repo that
> demonstrates use of Alibaba Cloud services and APIs."

So the required artifact is **a link to a code file** that calls Alibaba Cloud
services/APIs — not a live ECS/Function-Compute instance and not a screen recording of a
running host. *(Rules text confirmed live on the official Devpost rules page,
2026-06-21.)*

We therefore make a precise claim: **PreMortem's model reasoning and invoice perception
run on Qwen Cloud / DashScope, which is an Alibaba Cloud service.** We do **not** claim the
application backend is hosted on Alibaba Cloud — the FastAPI surface is portable and runs
locally for reproduction.

## The proof (code file)

[`src/premortem/llm/dashscope_adapter.py`](../src/premortem/llm/dashscope_adapter.py) is the
code path that calls the Alibaba Cloud APIs:

- **`qwen-max`** — failure-mode reasoning, via the DashScope OpenAI-compatible endpoint.
- **`qwen-vl-max`** — invoice-image perception, via DashScope `MultiModalConversation`.

Region endpoint: `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`.

## Live evidence

A captured real run of the vision leg is in
[`docs/live-vl-evidence.md`](live-vl-evidence.md):

- captured (UTC): **2026-06-20T11:03:40Z**
- vision model: `qwen-vl-max` · reasoning model: `qwen-max`
- `qwen-vl-max` read the bank account printed on the tampered invoice PNG, the engine
  cross-checked it against the structured payment plan, and the verdict was **BLOCK**
  (`invoice_image_mismatch`) — the falsification leg a text-only agent cannot build.

## Reproduce it yourself

```bash
PREMORTEM_LLM=dashscope DASHSCOPE_API_KEY=<your key> \
  python -m pytest tests/test_vision_live.py -v
```

Both live `qwen-vl-max` tests pass against real Qwen Cloud (101 mock tests run creds-free;
**103 total** with a key). The engine code is byte-for-byte identical in mock and real
mode — only the adapter changes — so every tested verdict is the verdict production runs.

## Secret-redaction policy

No API key is ever committed. The DashScope key is provided only via environment variable
(`DASHSCOPE_API_KEY`) at runtime; the repo carries only [`.env.example`](../.env.example)
with a placeholder, and the live-evidence doc shows the key redacted as `...`.
