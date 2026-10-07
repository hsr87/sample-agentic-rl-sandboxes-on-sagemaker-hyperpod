"""Harbor environment backed by Amazon Bedrock AgentCore Runtime sessions.

One Harbor sandbox = one AgentCore Runtime session (a microVM running the task image) on a
runtime that was deployed ahead of time from the shared task image (agentcore/deploy_runtime.sh).

  start()    -> first InvokeAgentRuntime call with a new session id creates the microVM
  exec()     -> InvokeAgentRuntimeCommand (streamed stdout/stderr/exit code)
  upload_*   -> InvokeAgentRuntime to the shim's /invocations (base64, up to ~96 MB per call);
                directories travel as one tar.gz
  download_* -> the same in reverse
  stop()     -> StopRuntimeSession, always (sessions otherwise bill until the idle timeout)

Configuration (environment variables):
  AGENTCORE_RUNTIME_ARN  required, runtime deployed from the task image
  AGENTCORE_QUALIFIER    endpoint qualifier, default "DEFAULT"
  AWS_REGION             region of the runtime

Command wrapping rules and the streaming pattern are adapted from github.com/mightma/harbor
(branch acr-kit-v1, commit 4ee0cb25, Apache-2.0), which ported them from
github.com/awslabs/agentcore-rl-toolkit (Apache-2.0).

Usage with Harbor's CLI:  -e harbor_agentcore.environment:AgentCoreEnvironment
Usage with TRL:           environment_type="harbor_agentcore.environment:AgentCoreEnvironment"
                          through training/harness.py (HarborSpec only accepts built-in names).
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import random
import re
import shlex
import tarfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from harbor.environments.base import BaseEnvironment, ExecResult
from harbor.environments.capabilities import EnvironmentCapabilities
from harbor.environments.definition import effective_exec_cwd, parse_dockerfile_workdir

COMMAND_MAX_LEN = 65536
COMMAND_MAX_TIMEOUT_SEC = 3600
SESSION_ID_MIN_LEN = 33
RETRYABLE_CODES = {"ThrottlingException", "ServiceQuotaExceededException", "RetryableConflictException",
                   "ServiceUnavailableException", "InternalServerException"}
_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_CLIENT = None
# boto3 calls block, so they run on a dedicated pool. asyncio's default executor caps at ~32 threads,
# which would serialize high-concurrency rollouts on the client side.
_EXECUTOR = ThreadPoolExecutor(max_workers=int(os.environ.get("AGENTCORE_MAX_THREADS", "512")))


async def _in_thread(fn, *args, **kwargs):
    return await asyncio.get_running_loop().run_in_executor(_EXECUTOR, lambda: fn(*args, **kwargs))


def _client():
    """One thread-safe data plane client per process, sized for many concurrent sessions."""
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = boto3.client(
            "bedrock-agentcore",
            region_name=os.environ.get("AWS_REGION", "us-west-2"),
            config=Config(max_pool_connections=512, read_timeout=COMMAND_MAX_TIMEOUT_SEC + 120,
                          connect_timeout=10, retries={"mode": "standard", "max_attempts": 3}),
        )
    return _CLIENT


def wrap_in_shell(command: str) -> str:
    """InvokeAgentRuntimeCommand splits the command argv-style, so pipes and $VAR need an explicit shell.

    Single-quoted form when possible; otherwise double quotes with only backslash and double quote
    escaped, which leaves $ and backticks for the inner shell.
    """
    if "'" not in command:
        return f"/bin/bash -c '{command}'"
    escaped = command.replace("\\", "\\\\").replace('"', '\\"')
    return f'/bin/bash -c "{escaped}"'


def compose_command(command: str, cwd: str | None, env: dict[str, str] | None, user: str | int | None) -> str:
    """Fold cwd, env and user into the command (the API has no fields for them).

    stdin is redirected from /dev/null: InvokeAgentRuntimeCommand hands the command an open pipe that never
    reaches EOF, so anything reading stdin (`cat`, a bare `python3`) would hang until the timeout. Docker exec
    without -i and E2B give the command no stdin, so this keeps the semantics identical.
    """
    prefix = "exec </dev/null; "
    prefix += f"cd {shlex.quote(cwd)} && " if cwd else ""
    if env:
        bad = [k for k in env if not _ENV_KEY_RE.match(k)]
        if bad:
            raise ValueError(f"invalid environment variable names: {bad}")
        prefix += "export " + " ".join(f"{k}={shlex.quote(str(v))}" for k, v in env.items()) + " && "
    composed = prefix + command
    if user is None or str(user) in ("root", "0"):
        return composed
    return f"su -s /bin/bash {shlex.quote(str(user))} -c {shlex.quote(composed)}"


def _call_with_retry(fn, *, attempts: int = 8, **kwargs):
    """Retry throttling and transient errors with jittered exponential backoff."""
    for i in range(attempts):
        try:
            return fn(**kwargs)
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code not in RETRYABLE_CODES or i == attempts - 1:
                raise
            time.sleep(min(20.0, 0.5 * 2**i) * (0.5 + random.random()))



# Limits for directories copied out of a session (verifier logs and artifacts are small).
MAX_DOWNLOAD_BYTES = 1 << 30
MAX_DOWNLOAD_MEMBERS = 100_000

class AgentCoreEnvironment(BaseEnvironment):
    def __init__(self, *args, **kwargs):
        self._runtime_arn = os.environ.get("AGENTCORE_RUNTIME_ARN", "")
        self._qualifier = os.environ.get("AGENTCORE_QUALIFIER", "DEFAULT")
        # Network access is a property of the runtime, not of a session. The operator declares that the runtime
        # runs in VPC mode on subnets without an internet route (agentcore/network.sh), which lets tasks that
        # request network_mode="no-network" run here. Without it such tasks are rejected by Harbor.
        self._network_isolated = os.environ.get("AGENTCORE_NETWORK_ISOLATED", "") == "1"
        self._session_id: str | None = None
        super().__init__(*args, **kwargs)
        dockerfile = self.environment_dir / "Dockerfile"
        self._workdir = parse_dockerfile_workdir(dockerfile) if dockerfile.exists() else None

    @staticmethod
    def type() -> str:
        return "agentcore"

    @property
    def capabilities(self) -> EnvironmentCapabilities:
        # Network mode (PUBLIC or VPC) is fixed per runtime, so there is no per-session toggle: the runtime either
        # blocks all egress (isolated VPC subnets) or allows it.
        return EnvironmentCapabilities(disable_internet=self._network_isolated)

    def _validate_definition(self):
        if not self._runtime_arn:
            raise ValueError("AGENTCORE_RUNTIME_ARN is not set")

    # -- session lifecycle -------------------------------------------------------------

    def _invoke_shim(self, payload: dict) -> dict:
        resp = _call_with_retry(
            _client().invoke_agent_runtime,
            agentRuntimeArn=self._runtime_arn,
            runtimeSessionId=self._session_id,
            qualifier=self._qualifier,
            contentType="application/json",
            accept="application/json",
            payload=json.dumps(payload).encode(),
        )
        body = json.loads(resp["response"].read())
        if body.get("status") != "ok":
            raise RuntimeError(f"shim action {payload.get('action')!r} failed: {body}")
        return body

    async def start(self, force_build: bool) -> None:
        # The first call that names a new session id provisions the microVM.
        stem = re.sub(r"[^a-zA-Z0-9_-]+", "-", self.environment_name)[:120]
        self._session_id = f"{stem}-{uuid.uuid4().hex}".ljust(SESSION_ID_MIN_LEN, "0")
        await _in_thread(self._invoke_shim, {"action": "ping"})
        await self._upload_environment_dir_after_start()

    async def stop(self, delete: bool) -> None:
        # Always stop the session: an idle session keeps billing memory until the idle timeout.
        if not self._session_id:
            return
        session_id, self._session_id = self._session_id, None
        try:
            await _in_thread(
                _call_with_retry, _client().stop_runtime_session,
                agentRuntimeArn=self._runtime_arn, runtimeSessionId=session_id, qualifier=self._qualifier,
            )
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") != "ResourceNotFoundException":
                self.logger.warning(f"StopRuntimeSession failed for {session_id}: {e}")

    # -- commands ----------------------------------------------------------------------

    def _exec_sync(self, command: str, timeout_sec: int) -> ExecResult:
        wrapped = wrap_in_shell(command)
        if len(wrapped) > COMMAND_MAX_LEN:
            raise ValueError(f"command is {len(wrapped)} chars; AgentCore caps a command at {COMMAND_MAX_LEN}")
        resp = _call_with_retry(
            _client().invoke_agent_runtime_command,
            agentRuntimeArn=self._runtime_arn,
            runtimeSessionId=self._session_id,
            qualifier=self._qualifier,
            contentType="application/json",
            accept="application/vnd.amazon.eventstream",
            body={"command": wrapped, "timeout": timeout_sec},
        )
        stdout, stderr, exit_code, status = [], [], None, None
        for event in resp["stream"]:
            chunk = event.get("chunk")
            if chunk is None:
                # Throttling and other errors can arrive as stream members, not as exceptions.
                raise RuntimeError(f"error event in command stream: {event}")
            if "contentDelta" in chunk:
                stdout.append(chunk["contentDelta"].get("stdout") or "")
                stderr.append(chunk["contentDelta"].get("stderr") or "")
            elif "contentStop" in chunk:
                exit_code = chunk["contentStop"].get("exitCode")
                status = chunk["contentStop"].get("status")
        if exit_code is None:
            raise RuntimeError("command stream ended without contentStop")
        if status == "TIMED_OUT" and exit_code == 0:
            exit_code = 124
        return ExecResult(stdout="".join(stdout), stderr="".join(stderr), return_code=exit_code)

    async def exec(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_sec: int | None = None,
        user: str | int | None = None,
    ) -> ExecResult:
        if not self._session_id:
            raise RuntimeError("sandbox not started")
        cwd = effective_exec_cwd(cwd, self.task_env_config.workdir, self._workdir)
        composed = compose_command(command, cwd, self._merge_env(env), self._resolve_user(user))
        timeout = min(int(timeout_sec), COMMAND_MAX_TIMEOUT_SEC) if timeout_sec else COMMAND_MAX_TIMEOUT_SEC
        return await _in_thread(self._exec_sync, composed, max(1, timeout))

    # -- files -------------------------------------------------------------------------

    async def _write(self, path: str, data: bytes, mode: int = 0o644) -> None:
        payload = {"action": "upload", "path": path, "data": base64.b64encode(data).decode(), "mode": mode}
        await _in_thread(self._invoke_shim, payload)

    async def _read(self, path: str) -> bytes:
        body = await _in_thread(self._invoke_shim, {"action": "download", "path": path})
        return base64.b64decode(body["data"])

    async def upload_file(self, source_path: Path | str, target_path: str) -> None:
        src = Path(source_path)
        await self._write(target_path, src.read_bytes(), src.stat().st_mode & 0o777)

    async def upload_dir(self, source_dir: Path | str, target_dir: str) -> None:
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            tar.add(str(source_dir), arcname=".")
        archive = f"/tmp/.upload-{uuid.uuid4().hex}.tgz"
        await self._write(archive, buf.getvalue())
        target = shlex.quote(str(PurePosixPath(target_dir)))
        r = await self.exec(f"mkdir -p {target} && tar -xzf {archive} -C {target} && rm -f {archive}", user="root")
        if r.return_code != 0:
            raise RuntimeError(f"upload_dir extract failed: {r.stderr}")

    async def download_file(self, source_path: str, target_path: Path | str) -> None:
        Path(target_path).parent.mkdir(parents=True, exist_ok=True)
        Path(target_path).write_bytes(await self._read(source_path))

    async def download_dir(self, source_dir: str, target_dir: Path | str) -> None:
        archive = f"/tmp/.download-{uuid.uuid4().hex}.tgz"
        r = await self.exec(f"tar -czf {archive} -C {shlex.quote(source_dir)} .", user="root")
        if r.return_code != 0:
            raise RuntimeError(f"download_dir archive failed: {r.stderr}")
        data = await self._read(archive)
        await self.exec(f"rm -f {archive}", user="root")
        Path(target_dir).mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            # The archive is produced by code running in the sandbox: bound its expanded size before extracting
            # (filter="data" already rejects absolute paths, traversal and links).
            members = tar.getmembers()
            total = sum(m.size for m in members)
            if len(members) > MAX_DOWNLOAD_MEMBERS or total > MAX_DOWNLOAD_BYTES:
                raise RuntimeError(f"download_dir {source_dir}: {len(members)} entries, {total} bytes exceeds limits")
            tar.extractall(str(target_dir), members=members, filter="data")
