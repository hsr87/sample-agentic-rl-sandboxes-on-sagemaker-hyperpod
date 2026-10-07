# Shared base image for every task in the suite (linux/amd64 and linux/arm64).
# Recipe follows savatar101/env-data-agent-train:base (amd64 only) with pinned packages,
# plus the Kaggle data for all selected tasks baked in under /data/<owner>__<dataset>/.
# E2B sandbox uses the amd64 variant as-is; AgentCore adds a contract shim layer (agentcore/image/).
FROM python:3.12-slim-trixie@sha256:05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl git \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

# Staged by tasks/build_suite.py (not in git).
COPY data/ /data/

RUN mkdir -p /home/user/input /workdir /logs/verifier
WORKDIR /workdir
CMD ["python3"]
