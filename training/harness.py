"""Shared TRL harness for both sandboxes: TRL's single-`bash`-tool harness plus

1. a pluggable sandbox: `environment_type` may be a Harbor built-in name ("e2b") or an import path
   ("harbor_agentcore.environment:AgentCoreEnvironment"). TRL's HarborEnv only passes `type=` to Harbor,
   which rejects import paths, so `_start` is overridden to pass `import_path=` instead.
2. per-call timing of every sandbox operation, written as JSON lines (one file per process) to
   $SANDBOX_TIMING_DIR, independent of TRL's own logging.
3. failure capture: if the sandbox cannot be started, the rollout continues with a tool that reports the
   error and a reward of 0.0, and the cause is logged, instead of crashing the training step.
4. clean exit: TRL's HarborEnv.__del__ blocks forever at interpreter shutdown (it waits on an event loop
   whose thread is already gone), and sandboxes still open at exit keep billing (Harbor creates E2B
   sandboxes with a 24 h timeout). An atexit hook stops every live sandbox first, and __del__ never blocks.

Select it with HarborSpec(agent="training.harness:TimedBashEnv", environment_type=...).
"""

import asyncio
import json
import os
import socket
import sys
import tempfile
import threading
import time
import traceback
import uuid
import weakref
from contextlib import asynccontextmanager
from pathlib import Path

from trl.experimental.harbor import HarborBashEnv

_LOG_LOCK = threading.Lock()
# TRL's bash harness keeps 8000 characters of tool output. With max_completion_length=4096 tokens a couple of
# large outputs (for example `cat` of a CSV) exhausted the budget in 46% of rollouts, so this harness keeps less.
TOOL_OUTPUT_MAX_CHARS = int(os.environ.get("TOOL_OUTPUT_MAX_CHARS", "2000"))
_LIVE_ENVS: "weakref.WeakSet[TimedBashEnv]" = weakref.WeakSet()


def _log_path() -> Path | None:
    root = os.environ.get("SANDBOX_TIMING_DIR")
    if not root:
        return None
    rank = os.environ.get("RANK", "0")
    Path(root).mkdir(parents=True, exist_ok=True)
    return Path(root) / f"sandbox_{socket.gethostname()}_rank{rank}_{os.getpid()}.jsonl"


def log_event(**fields) -> None:
    path = _log_path()
    if path is None:
        return
    fields.setdefault("ts", time.time())
    fields.setdefault("step", os.environ.get("TRAIN_STEP"))
    with _LOG_LOCK, open(path, "a") as f:
        f.write(json.dumps(fields) + "\n")


class TimedBashEnv(HarborBashEnv):
    """HarborBashEnv + import-path sandboxes + timing + failure capture."""

    def __init__(self, environment_type: str = "docker"):
        super().__init__(environment_type=environment_type)
        self._rollout_id = None
        self._broken: str | None = None
        _LIVE_ENVS.add(self)

    def _close(self, timeout: float = 60.0) -> None:
        """Stop the current sandbox (bounded wait) and the env's event loop."""
        try:
            if self._env is not None and self._loop_thread.is_alive():
                asyncio.run_coroutine_threadsafe(self._stop(), self._loop).result(timeout=timeout)
        except Exception:  # noqa: BLE001
            pass
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)

    def __del__(self):
        if sys.is_finalizing():
            return
        self._close(timeout=30.0)

    @asynccontextmanager
    async def _timed(self, op: str, **extra):
        t0 = time.perf_counter()
        ok, err = True, None
        try:
            yield
        except BaseException as e:
            ok, err = False, f"{type(e).__name__}: {e}"[:500]
            raise
        finally:
            log_event(sandbox=self._environment_type, rollout=self._rollout_id,
                      task=getattr(self._task, "short_name", None), op=op,
                      dur=time.perf_counter() - t0, ok=ok, err=err, **extra)

    async def _start(self, task_dir: str) -> str:
        from harbor.environments.factory import EnvironmentFactory
        from harbor.models.task.task import Task
        from harbor.models.trial.config import EnvironmentConfig as TrialEnvironmentConfig
        from harbor.models.trial.paths import TrialPaths
        from harbor.trial.network_policy import resolve_agent_env_baseline

        await self._stop()
        self._rollout_id = uuid.uuid4().hex[:12]
        self._broken = None
        self._task = Task(task_dir=Path(task_dir))
        self._paths = TrialPaths(trial_dir=Path(tempfile.mkdtemp(prefix="harbor_trl_")))
        et = self._environment_type
        config = TrialEnvironmentConfig(import_path=et) if ":" in et else TrialEnvironmentConfig(type=et)
        # TRL's Harbor env does not pass a network policy, so every sandbox would default to public internet.
        # Resolve the task's [environment] policy the way a Harbor trial does; providers that cannot enforce
        # it reject the task instead of silently allowing egress.
        network_policy = resolve_agent_env_baseline(self._task.config, config)
        try:
            async with self._timed("provision"):
                async with self._timed("create"):
                    self._env = EnvironmentFactory.create_environment_from_config(
                        config=config,
                        environment_dir=self._task.paths.environment_dir,
                        environment_name=self._task.short_name,
                        session_id=uuid.uuid4().hex,
                        trial_paths=self._paths,
                        task_env_config=self._task.config.environment,
                        network_policy=network_policy,
                    )
                async with self._timed("start"):
                    await self._env.start(force_build=False)
                async with self._timed("upload_build_files"):
                    await self._upload_build_files()
                async with self._timed("healthcheck"):
                    await self._env.run_healthcheck()
                async with self._timed("prepare"):
                    await self._env.exec("mkdir -p /workdir /home/user/input")
                    await self._setup()
        except Exception as e:  # noqa: BLE001
            self._broken = f"{type(e).__name__}: {e}"[:500]
            log_event(sandbox=et, rollout=self._rollout_id, task=self._task.short_name, op="rollout_failed",
                      cause="provision", err=self._broken, tb=traceback.format_exc()[-2000:])
            try:
                await self._stop()
            except Exception:  # noqa: BLE001
                pass
        return self._task.instruction

    def _exec(self, command: str, timeout: int = 180) -> str:
        if self._broken:
            return f"sandbox error: {self._broken}"
        t0 = time.perf_counter()
        ok, err, rc = True, None, None
        try:
            result = self._run(self._env.exec(command, timeout_sec=timeout))
            rc = result.return_code
        except Exception as e:  # noqa: BLE001
            ok, err = False, f"{type(e).__name__}: {e}"[:500]
            return f"sandbox error: {err}"
        finally:
            log_event(sandbox=self._environment_type, rollout=self._rollout_id, task=self._task.short_name,
                      op="exec", dur=time.perf_counter() - t0, ok=ok, err=err, rc=rc, cmd=command[:300])
        out = (result.stdout or "") + (result.stderr or "")
        if len(out) > TOOL_OUTPUT_MAX_CHARS:
            out = out[:TOOL_OUTPUT_MAX_CHARS] + "\n... [truncated]"
        return out or f"(empty output, rc={result.return_code})"

    async def _verify(self) -> float:
        if self._broken:
            return 0.0
        try:
            async with self._timed("verify"):
                reward = await super()._verify()
        except Exception as e:  # noqa: BLE001
            log_event(sandbox=self._environment_type, rollout=self._rollout_id, task=self._task.short_name,
                      op="rollout_failed", cause="verify", err=f"{type(e).__name__}: {e}"[:500])
            return 0.0
        log_event(sandbox=self._environment_type, rollout=self._rollout_id, task=self._task.short_name,
                  op="reward", reward=reward)
        return reward

    async def _stop(self) -> None:
        if self._env is None:
            return
        async with self._timed("stop"):
            await super()._stop()


def _stop_live_sandboxes() -> None:
    for env in list(_LIVE_ENVS):
        env._close(timeout=60.0)


# threading's exit hooks run last-registered-first, and concurrent.futures shuts its thread pools down in
# one of them. The AgentCore environment still needs its pool for StopRuntimeSession, so import that module
# first (it registers lazily otherwise) and register after it. Plain atexit would run too late.
import concurrent.futures.thread  # noqa: E402,F401

threading._register_atexit(_stop_live_sandboxes)
