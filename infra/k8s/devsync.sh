#!/usr/bin/env bash
# Copy local code into the running dev pod (debug iterations without rebuilding the image).
set -euo pipefail
P="$(kubectl -n harbor-rl get pod -l job=dev -o name | head -1)"
cd "$(dirname "$0")/../.."
COPYFILE_DISABLE=1 tar --no-xattrs -czf - training bench agentcore/harbor_agentcore tasks/train tasks/heldout | kubectl -n harbor-rl exec -i "$P" -- bash -c "rm -rf /app/tasks && tar xzf - -C /app"
echo "$P"
