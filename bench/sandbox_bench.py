"""Sandbox micro-benchmark, identical for both sandboxes (run from the trainer pod).

Uses the same Harbor environment classes that training uses (EnvironmentFactory with a task from the suite).

  latency:      N sequential sessions; per session: start, 20x exec `true`, 1 MB and 8 MB upload + download, stop
  concurrency:  for each level C in --levels, C sessions at once, each: start, 10x exec, stop
                -> throughput (sessions/s, execs/s), error and throttle rates

    python bench/sandbox_bench.py --sandbox agentcore --out /results/bench
"""

import argparse
import asyncio
import csv
import os
import random
import tempfile
import time
import uuid
from pathlib import Path

SANDBOXES = {"e2b": "e2b", "agentcore": "harbor_agentcore.environment:AgentCoreEnvironment"}
THROTTLE_MARKERS = ("throttl", "rate exceeded", "too many requests", "429", "quota", "concurren", "rate limit")


def make_env(env_type: str, task_dir: Path):
    from harbor.environments.factory import EnvironmentFactory
    from harbor.models.task.task import Task
    from harbor.models.trial.config import EnvironmentConfig as TrialEnvironmentConfig
    from harbor.models.trial.paths import TrialPaths
    from harbor.trial.network_policy import resolve_agent_env_baseline

    task = Task(task_dir=task_dir)
    config = TrialEnvironmentConfig(import_path=env_type) if ":" in env_type else TrialEnvironmentConfig(type=env_type)
    return EnvironmentFactory.create_environment_from_config(
        network_policy=resolve_agent_env_baseline(task.config, config),  # same policy as training
        config=config,
        environment_dir=task.paths.environment_dir,
        environment_name=task.short_name,
        session_id=uuid.uuid4().hex,
        trial_paths=TrialPaths(trial_dir=Path(tempfile.mkdtemp(prefix="bench_"))),
        task_env_config=task.config.environment,
    )


class Recorder:
    def __init__(self, path: Path, sandbox: str):
        self.path, self.sandbox = path, sandbox
        self.f = open(path, "w", newline="")
        self.w = csv.writer(self.f)
        self.w.writerow(["sandbox", "test", "concurrency", "session", "op", "t_start", "dur_sec", "ok", "throttled", "err"])

    async def timed(self, test, conc, session, op, coro):
        t0, ts = time.perf_counter(), time.time()
        try:
            res = await coro
            self.w.writerow([self.sandbox, test, conc, session, op, ts, time.perf_counter() - t0, 1, 0, ""])
            return res
        except Exception as e:  # noqa: BLE001
            msg = f"{type(e).__name__}: {e}".replace("\n", " ")[:300]
            thr = int(any(m in msg.lower() for m in THROTTLE_MARKERS))
            self.w.writerow([self.sandbox, test, conc, session, op, ts, time.perf_counter() - t0, 0, thr, msg])
            raise


async def latency_session(rec, env_type, task_dir, i, blobs, tmp: Path):
    env = make_env(env_type, task_dir)
    try:
        await rec.timed("latency", 1, i, "start", env.start(force_build=False))
        # First and second import of the task libraries in a fresh session: the first one pays for reading the
        # libraries from disk unless the sandbox snapshot already holds them (tasks/image/warmup.sh).
        imp = "python3 -c 'import pandas, numpy, sklearn'"
        await rec.timed("latency", 1, i, "py_import_first", env.exec(imp))
        await rec.timed("latency", 1, i, "py_import_again", env.exec(imp))
        for _ in range(20):
            await rec.timed("latency", 1, i, "exec_true", env.exec("true"))
        for name, path in blobs.items():
            remote = f"/tmp/bench_{name}.bin"
            await rec.timed("latency", 1, i, f"upload_{name}", env.upload_file(path, remote))
            await rec.timed("latency", 1, i, f"download_{name}", env.download_file(remote, tmp / f"dl_{name}_{i}.bin"))
    finally:
        await rec.timed("latency", 1, i, "stop", env.stop(delete=True))


async def concurrent_session(rec, env_type, task_dir, conc, i, counters):
    env = make_env(env_type, task_dir)
    started = False
    try:
        await rec.timed("concurrency", conc, i, "start", env.start(force_build=False))
        started = True
        for _ in range(10):
            await rec.timed("concurrency", conc, i, "exec_true", env.exec("true"))
            counters["execs"] += 1
        counters["ok"] += 1
    except Exception:  # noqa: BLE001  (recorded by Recorder)
        counters["failed"] += 1
    finally:
        if started:
            try:
                await rec.timed("concurrency", conc, i, "stop", env.stop(delete=True))
            except Exception:  # noqa: BLE001
                pass


async def main_async(args):
    env_type = SANDBOXES[args.sandbox]
    task_dir = sorted(p.parent for p in Path(args.tasks).glob("*/task.toml"))[0]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    rec = Recorder(out / f"bench_{args.sandbox}_{stamp}.csv", args.sandbox)
    summary = open(out / f"bench_{args.sandbox}_{stamp}_throughput.csv", "w", newline="")
    sw = csv.writer(summary)
    sw.writerow(["sandbox", "concurrency", "sessions_ok", "sessions_failed", "execs", "wall_sec",
                 "sessions_per_sec", "execs_per_sec"])

    tmp = Path(tempfile.mkdtemp(prefix="bench_blobs_"))
    blobs = {}
    for name, size in (("1MB", 1 << 20), ("8MB", 8 << 20)):
        p = tmp / f"{name}.bin"
        p.write_bytes(random.randbytes(size))
        blobs[name] = p

    if args.latency_sessions:
        for i in range(args.latency_sessions):
            try:
                await latency_session(rec, env_type, task_dir, i, blobs, tmp)
            except Exception as e:  # noqa: BLE001
                print(f"latency session {i} failed: {e}")
            rec.f.flush()

    for conc in args.levels:
        counters = {"ok": 0, "failed": 0, "execs": 0}
        t0 = time.perf_counter()
        await asyncio.gather(*(concurrent_session(rec, env_type, task_dir, conc, i, counters) for i in range(conc)))
        wall = time.perf_counter() - t0
        sw.writerow([args.sandbox, conc, counters["ok"], counters["failed"], counters["execs"], round(wall, 3),
                     round(counters["ok"] / wall, 3), round(counters["execs"] / wall, 3)])
        summary.flush()
        rec.f.flush()
        print(f"[{args.sandbox}] concurrency={conc} ok={counters['ok']} failed={counters['failed']} wall={wall:.1f}s")
        await asyncio.sleep(args.cooldown)
    rec.f.close()
    summary.close()
    print(f"wrote {rec.path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sandbox", choices=sorted(SANDBOXES), required=True)
    ap.add_argument("--tasks", default="tasks/train")
    ap.add_argument("--out", default="/results/bench")
    ap.add_argument("--latency-sessions", type=int, default=30)
    ap.add_argument("--levels", type=int, nargs="*", default=[8, 32, 128])
    ap.add_argument("--cooldown", type=float, default=30.0)
    args = ap.parse_args()
    os.environ.setdefault("AGENTCORE_MAX_THREADS", "1024")
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
