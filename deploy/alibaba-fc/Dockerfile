# PreMortem backend — Alibaba Cloud Function Compute (FC 3.0) custom-container web function.
# Build context is the repo root so `pip install .` sees pyproject + src:
#   docker build -f deploy/alibaba-fc/Dockerfile -t premortem-api:latest .
FROM python:3.11-slim

WORKDIR /app
COPY . /app

# Engine + ASGI server. The DashScope adapter (optional extra) is installed so the
# hosted backend can call Qwen Cloud when PREMORTEM_LLM=dashscope; with the default
# mock provider it runs creds-free.
RUN pip install --no-cache-dir ".[dashscope]" "uvicorn[standard]>=0.29"

# FC custom-container web functions forward HTTP to the port the container listens on
# (caServerPort, default 9000). uvicorn binds it directly.
ENV PREMORTEM_MEMORY_DB=/tmp/premortem_memory.sqlite3
EXPOSE 9000
CMD ["uvicorn", "premortem.api:app", "--host", "0.0.0.0", "--port", "9000"]
