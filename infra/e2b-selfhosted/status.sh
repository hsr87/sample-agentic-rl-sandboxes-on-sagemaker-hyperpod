#!/usr/bin/env bash
# Show the self-hosted E2B deploy chain progress on the bastion (via SSM, no SSH needed).
# Lines that could carry credentials are filtered out on the bastion before they reach SSM output.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/bastion.sh"
bastion_run 'ls /opt/.e2b-step-*.done 2>/dev/null | sed s,/opt/.e2b-step-,, ; echo ---
tail -n 15 /tmp/e2b.log 2>/dev/null | grep -viE "api.?key|token|password|secret" | cut -c1-200'
