#!/usr/bin/env bash
# Runs inside the trainer pod (8x A100): vLLM server on GPUs 0-1, GRPO training on GPUs 2-7.
# Usage: training/run.sh e2b|agentcore [extra train_grpo.py args]
set -euo pipefail
SANDBOX="$1"; shift
MODEL="${MODEL:-google/gemma-4-E4B-it}"
RUN_ID="${RUN_ID:-grpo-${SANDBOX}-$(date +%Y%m%d-%H%M%S)}"
OUT="/results/${RUN_ID}"
# Results live on the node's hostPath, so a reused RUN_ID would mix logs of an earlier (possibly failed) run.
if [ -n "$(ls -A "$OUT" 2>/dev/null)" ]; then
  echo "$OUT is not empty; choose a new RUN_ID or move the old run away"; exit 1
fi
mkdir -p "$OUT"
cd /app

if curl -sf http://localhost:8000/health >/dev/null; then
  echo "a vLLM server is already listening on :8000; stop it first"; exit 1
fi

# --host 127.0.0.1: the dev-mode server exposes weight-update and RPC routes without auth; only the trainer
# processes in this pod (localhost) need it.
# setsid: vLLM spawns EngineCore/worker processes; killing the whole process group on exit frees GPUs 0-1.
CUDA_VISIBLE_DEVICES=0,1 VLLM_SERVER_DEV_MODE=1 setsid vllm serve "$MODEL" \
  --tensor-parallel-size 2 --host 127.0.0.1 --port 8000 \
  --weight-transfer-config '{"backend": "nccl"}' \
  --logprobs-mode processed_logprobs --max-logprobs -1 \
  --limit-mm-per-prompt '{"image": 0, "audio": 0}' \
  --max-model-len 32768 --gpu-memory-utilization 0.6 \
  > "$OUT/vllm.log" 2>&1 &
VLLM_PID=$!
trap 'kill -- -$VLLM_PID 2>/dev/null || true' EXIT

echo "waiting for vLLM server..."
until curl -sf http://localhost:8000/health >/dev/null; do
  kill -0 $VLLM_PID 2>/dev/null || { echo "vLLM exited"; tail -50 "$OUT/vllm.log"; exit 1; }
  sleep 5
done

PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True CUDA_VISIBLE_DEVICES=2,3,4,5,6,7 accelerate launch --config_file training/zero3.yaml --num_processes 6 \
  training/train_grpo.py --sandbox "$SANDBOX" --model "$MODEL" --output-dir "$OUT" "$@" 2>&1 | tee "$OUT/train.log"

if [ -n "${RESULTS_S3_URI:-}" ]; then
  python3 -m bench.s3sync "$OUT"
fi
