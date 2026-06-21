# Deploy the PreMortem backend on Alibaba Cloud Function Compute

This hosts the FastAPI surface (`premortem.api:app`) as an Alibaba Cloud **Function
Compute 3.0** custom-container web function in **Singapore (`ap-southeast-1`)**, so the
backend itself runs on Alibaba Cloud (not only the Qwen Cloud model calls).

## Account requirements (Singapore region)

- **Credit card / payment method only.** Identity (passport) verification is **not**
  required for Function Compute in Singapore. On the Alibaba Cloud *International* site,
  identity verification is forced only for: purchasing **Chinese-mainland** region
  services, signing online contracts, applying for a credit limit, joining ACPN, or
  changing the mobile number across countries — none of which apply here.
- Card must be enabled for **online + international** transactions and **3D Secure**, with
  at least **USD 1.00** available (a USD 1.00 pre-authorization validates the card).
- Visa / Mastercard / PayPal accepted.

## Deploy

From the **repo root** (build context must be the repo root so `pip install .` works):

```bash
# 1. Build the image
docker build -f deploy/alibaba-fc/Dockerfile -t premortem-api:latest .

# 2. Tag + push to your ACR namespace (registry-intl.ap-southeast-1.aliyuncs.com/<ns>/...)
docker tag premortem-api:latest registry-intl.ap-southeast-1.aliyuncs.com/<ns>/premortem-api:latest
docker push registry-intl.ap-southeast-1.aliyuncs.com/<ns>/premortem-api:latest

# 3. Edit s.yaml: replace REPLACE_NAMESPACE with <ns>, then deploy
npm i -g @serverless-devs/s
s config add          # provide the AccessKey (AK/SK); store secrets only in ~/.credentials
s deploy
```

`s deploy` prints the HTTP trigger URL. Smoke-test it:

```bash
curl https://<trigger-host>/health           # -> {"status":"ok"} or similar liveness
curl https://<trigger-host>/demo/scenarios    # -> the five built-in demo payments
```

## Running live Qwen Cloud on the host (optional)

The committed `s.yaml` defaults to the **creds-free mock provider**, so the hosted backend
runs with no secret and judges can poke it freely. To make the *hosted* backend call Qwen
Cloud live, set these as FC environment variables at deploy time (console or `s` env) —
**never commit the key**:

- `PREMORTEM_LLM=dashscope`
- `DASHSCOPE_API_KEY=<from ~/.credentials/qwen-cloud.env>`
- `DASHSCOPE_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1`

The deploy-proof the hackathon rules require is already satisfied by the code-file link to
[`src/premortem/llm/dashscope_adapter.py`](../../src/premortem/llm/dashscope_adapter.py);
this Function Compute deployment is an **additional** strengthening of the
"backend runs on Alibaba Cloud" reading.
