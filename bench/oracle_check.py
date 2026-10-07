"""Task validity: run the oracle (solution/solve.sh) on every task through the training harness.

Uses training.harness.TimedBashEnv exactly as training does (same start, healthcheck, verifier), so a task
that passes here is a task whose environment, data and verifier work in that sandbox.

    python bench/oracle_check.py --sandbox agentcore --out /results/oracle
"""

import argparse
import csv
import os
import time
from pathlib import Path

from training.harness import TimedBashEnv

SANDBOXES = {"e2b": "e2b", "agentcore": "harbor_agentcore.environment:AgentCoreEnvironment"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sandbox", choices=sorted(SANDBOXES), required=True)
    ap.add_argument("--tasks", nargs="*", default=["tasks/train", "tasks/heldout"])
    ap.add_argument("--out", default="/results/oracle")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("SANDBOX_TIMING_DIR", str(out / f"sandbox_{args.sandbox}"))
    path = out / f"oracle_{args.sandbox}_{time.strftime('%Y%m%d-%H%M%S')}.csv"
    task_dirs = [p.parent for root in args.tasks for p in sorted(Path(root).glob("*/task.toml"))]

    env = TimedBashEnv(environment_type=SANDBOXES[args.sandbox])
    passed = 0
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["sandbox", "split", "task", "reward", "passed", "error", "wall_sec"])
        for task_dir in task_dirs:
            t0 = time.perf_counter()
            reward, err = 0.0, ""
            try:
                env.reset(task_dir=str(task_dir))
                if env._broken:
                    err = env._broken
                else:
                    env._run(env._env.upload_dir(task_dir / "solution", "/solution"))
                    env._exec("bash /solution/solve.sh")
                    reward = env.reward
            except Exception as e:  # noqa: BLE001
                err = f"{type(e).__name__}: {e}"[:300]
            ok = reward >= 1.0
            passed += ok
            w.writerow([args.sandbox, task_dir.parent.name, task_dir.name, reward, int(ok), err,
                        round(time.perf_counter() - t0, 3)])
            f.flush()
            print(f"[{args.sandbox}] {task_dir.name}: reward={reward} {err}")
    env._run(env._stop())
    print(f"[{args.sandbox}] oracle passed {passed}/{len(task_dirs)} -> {path}")


if __name__ == "__main__":
    main()
