"""Check that a sandbox enforces the tasks' network_mode = "no-network": outbound connections fail while the task
data is readable. Uses training.harness.TimedBashEnv, so the sandbox is created exactly as in training.

    python3 bench/egress_check.py --sandbox e2b
    python3 bench/egress_check.py --sandbox agentcore
"""

import argparse
import asyncio
import glob

from training.harness import TimedBashEnv

SANDBOXES = {"e2b": "e2b", "agentcore": "harbor_agentcore.environment:AgentCoreEnvironment"}
CHECKS = [
    ("https", "curl -sS -m 8 -o /dev/null -w '%{http_code}' https://example.com; echo \" rc=$?\""),
    ("pypi", "python3 -c \"import urllib.request as u; print(u.urlopen('https://pypi.org', timeout=8).status)\" "
             "2>&1 | tail -1"),
    # A public object in another account's bucket: reachable through an S3 gateway endpoint with a permissive policy,
    # blocked by the restricted endpoint policy on the AgentCore isolated subnets (expect 403 or a failure).
    ("s3", "curl -sS -m 8 -o /dev/null -w '%{http_code}' -r 0-10 "
           "https://s3.us-west-2.amazonaws.com/aws-codedeploy-us-west-2/latest/install; echo \" rc=$?\""),
    ("data", "ls /home/user/input | head -2"),
]


async def main(sandbox: str) -> int:
    env = TimedBashEnv(environment_type=SANDBOXES[sandbox])
    await env._start(sorted(glob.glob("tasks/train/*"))[0])
    try:
        print("network policy:", env._env.network_policy.network_mode.value)
        out = {}
        for name, cmd in CHECKS:
            r = await env._env.exec(cmd, timeout_sec=30)
            out[name] = ((r.stdout or "") + (r.stderr or "")).strip()
            print(f"{name:6s} -> {out[name][:160]}")
    finally:
        await env._stop()
    s3_open = out["s3"].startswith(("200", "206"))
    blocked = " rc=0" not in out["https"] and not out["pypi"].strip().isdigit() and not s3_open
    print("egress blocked:", blocked, "| data readable:", bool(out["data"]))
    return 0 if blocked and out["data"] else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sandbox", choices=sorted(SANDBOXES), required=True)
    raise SystemExit(asyncio.run(main(ap.parse_args().sandbox)))
