#!/bin/sh
# Sandbox warm-up, run once before the sandbox snapshot is taken (identical for both sandboxes):
#   * AgentCore Runtime V2: the shim runs it at container startup, before it listens on 8080 (the snapshot is taken
#     after the first healthy /ping).
#   * E2B: the template's start command runs it, and the template snapshot is taken when it has finished.
# It only reads files (Python and the task libraries, the baked-in task data), so the snapshot carries them in the
# page cache. It creates no per-session state (no random values, time, credentials).
python3 -c "import pandas, numpy, scipy, sklearn, statsmodels, seaborn, plotly, tabulate, matplotlib.pyplot" \
  >/dev/null 2>&1 || true
find /data -type f -exec cat {} + >/dev/null 2>&1 || true
