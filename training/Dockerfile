# Trainer image: vLLM (rollout generation) + TRL GRPO + Harbor with both sandbox backends.
# Build context: repository root.
FROM vllm/vllm-openai:v0.30.0@sha256:8a69ffad015f138d7170c4ddc429e230a3bc1c1719f67e14324749df200a4b90

# e2b is pinned to 2.50.0: 2.51.0 creates sandboxes with POST /v2/sandboxes, which self-hosted E2B
# (sample-e2b-on-aws 830b516, e2b-dev/infra 225f963) does not serve; 2.50.0 uses POST /sandboxes.
RUN pip install --no-cache-dir \
      "trl[harbor]==1.14.1" \
      "harbor[e2b]==0.23.0" \
      "e2b==2.50.0" \
      "transformers==5.17.0" \
      "deepspeed==0.19.7" \
      "boto3==1.43.99" \
      "pandas==3.0.6" "matplotlib==3.11.2"

WORKDIR /app
COPY training/ /app/training/
COPY agentcore/harbor_agentcore/ /app/agentcore/harbor_agentcore/
COPY bench/ /app/bench/
COPY tasks/train/ /app/tasks/train/
COPY tasks/heldout/ /app/tasks/heldout/
COPY tasks/image/warmup.sh /app/tasks/image/warmup.sh

ENV PYTHONPATH=/app:/app/agentcore \
    TRL_EXPERIMENTAL_SILENCE=1 \
    PYTHONUNBUFFERED=1
ENTRYPOINT []
CMD ["bash"]
