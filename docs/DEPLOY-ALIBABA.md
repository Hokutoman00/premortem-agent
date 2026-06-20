# Deploying PreMortem on Alibaba Cloud

The hackathon requires the backend to **run on Alibaba Cloud against Qwen Cloud**, shown in a
short screen recording. This is the turn-key runbook. Two supported targets: **ECS** (a normal
VM, simplest to record) and **Function Compute** (serverless). Both serve the same
`premortem.api:app` FastAPI surface.

> **Credentials gate.** Everything below requires a Qwen Cloud / Alibaba Cloud account and a
> DashScope API key. The code, tests, and demo are 100% reproducible **without** them on the
> mock provider; only this live-deploy step is credential-gated.

---

## 0. Get the key (one time)

1. Sign in to the Alibaba Cloud / Qwen Cloud (Model Studio / DashScope) console.
2. Create a **DashScope API key**. Note the **international** base URL:
   `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`.
3. Confirm access to **`qwen-max`** (reasoning) and **`qwen-vl-max`** (vision).
4. Store the key the way `.env` expects — **never commit it** (see `.env.example`).

Quick local smoke test against the real provider before deploying:

```bash
export PREMORTEM_LLM=dashscope
export DASHSCOPE_API_KEY=<your key>
python scripts/run_demo.py     # same five scenarios, now hitting Qwen Cloud
```

---

## Option A — ECS (Elastic Compute Service), simplest to record

A small instance (e.g. `ecs.t6` / 1 vCPU 2 GiB, Ubuntu 22.04) is plenty; the agent is I/O-bound
on the model API.

```bash
# on the ECS instance
sudo apt update && sudo apt install -y python3-pip git
git clone <your public repo> premortem && cd premortem
pip install -e ".[dashscope]"

# configure
cp .env.example .env
#  edit .env:  PREMORTEM_LLM=dashscope  + DASHSCOPE_API_KEY=...

# run (bind to all interfaces so the security group can reach it)
uvicorn premortem.api:app --host 0.0.0.0 --port 8000
```

Open port **8000** in the instance **Security Group** (inbound, your IP). Then from your laptop:

```bash
curl http://<ECS_PUBLIC_IP>:8000/health
# {"status":"ok","provider":"dashscope","memory_size":0}
```

**The `/health` response showing `"provider":"dashscope"` is your proof shot** — it is the
on-Alibaba-Cloud, on-Qwen-Cloud evidence the rules ask for. Record:

1. `curl .../health` → `provider: dashscope`.
2. `curl .../demo/scenario/tampered_img` → `BLOCK` driven by `invoice_image_mismatch` (the
   `qwen-vl-max` leg running on Alibaba Cloud).
3. The Alibaba Cloud ECS console tab showing the instance is yours and running.

For a persistent service, wrap it in systemd or `tmux`; for the recording, a foreground
`uvicorn` is fine.

---

## Option B — Function Compute (serverless)

FastAPI runs under an ASGI adapter. Use a **Custom Runtime (Python)** HTTP function:

1. Package the repo + `pip install -t . -e ".[dashscope]"` (vendored deps).
2. Entry command: `uvicorn premortem.api:app --host 0.0.0.0 --port 9000`
   (Function Compute custom runtime listens on `$FC_SERVER_PORT`, commonly 9000 — bind to it).
3. Set the env vars `PREMORTEM_LLM=dashscope` and `DASHSCOPE_API_KEY` in the function config
   (use a secret, not plaintext in the repo).
4. **Memory note:** Function Compute instances are ephemeral, so point
   `PREMORTEM_MEMORY_DB` at a mounted **NAS** path (or swap in an RDS-backed store) if you want
   the learning loop to persist across cold starts. For the demo, the in-instance SQLite file is
   sufficient to show the day1→day2 loop within one warm instance.

The HTTP trigger URL replaces `<ECS_PUBLIC_IP>:8000` in the curls above.

---

## Pointing the web UI at the deployment

`web/index.html` calls the API at `location.origin` when served over HTTP with a port, else
falls back to `http://127.0.0.1:8000`. To demo the hosted backend, either:

- serve `web/index.html` as a static file from the same origin (e.g. behind the same
  ECS/nginx), or
- edit the `API` constant at the top of the `<script>` to your public URL.

---

## Cost & teardown

- `qwen-max` + `qwen-vl-max` calls are small per assessment; the five demo scenarios are a
  handful of calls total. Self-consistency N is configurable via
  `PREMORTEM_SELF_CONSISTENCY_N` (default 5) — lower it to cut cost during testing.
- **Stop the ECS instance** (or delete the function) after recording to stop billing.
- The DashScope key is the only secret; rotate it if it was ever exposed.

## Verification checklist (before recording)

- [ ] `/health` returns `provider: dashscope`.
- [ ] `tampered_img` returns `BLOCK` with `invoice_image_mismatch` confirmed (VL leg live).
- [ ] `safe` returns `PROCEED` / PAID.
- [ ] `bank_swap` and `new_vendor` return `BLOCK`.
- [ ] `/learn` then re-run `safe` → `ESCALATE` (learning loop live on the host).
- [ ] Alibaba Cloud console visible in-frame proving the host is yours.
