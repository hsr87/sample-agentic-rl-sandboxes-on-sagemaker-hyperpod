"""Pre-build the E2B sandbox templates that Harbor's E2B environment looks up, from the shared ECR image.

Harbor names one template per task: `{task short name}__{12-char hash of environment/}`. It builds a missing
template with `Template().from_image(image)` (no registry credentials) or `from_dockerfile`, which cannot pull
our private ECR image. This script creates exactly those aliases from the linux/amd64 variant of the ECR image,
passing a short-lived ECR token (valid 12 h, used only during the build), so no long-lived AWS keys are shared
with E2B. At training time Harbor finds the alias and runs its unmodified E2B environment.

Run it as a Kubernetes Job (the trainer pod role can only pull harbor-rl/tasks-base, so the token handed to the
E2B template builder is pull-only for that one repository; do not run it with broader local credentials):

    TAG=<trainer tag> ./infra/k8s/submit.sh e2b-prebuild 0 \
      python3 bench/prebuild_e2b_templates.py --image <account>.dkr.ecr.<region>.amazonaws.com/harbor-rl/tasks-base:v2
"""

import argparse
import asyncio
import base64
import os
import tempfile
import time
import uuid
from pathlib import Path

import boto3
from e2b import AsyncTemplate, Template


def harbor_alias(task_dir: Path) -> tuple[str, int, int]:
    """Template alias, cpus and memory exactly as Harbor's E2BEnvironment computes them."""
    from harbor.environments.factory import EnvironmentFactory
    from harbor.models.task.task import Task
    from harbor.models.trial.config import EnvironmentConfig as TrialEnvironmentConfig
    from harbor.models.trial.paths import TrialPaths

    task = Task(task_dir=task_dir)
    env = EnvironmentFactory.create_environment_from_config(
        config=TrialEnvironmentConfig(type="e2b"),
        environment_dir=task.paths.environment_dir,
        environment_name=task.short_name,
        session_id=uuid.uuid4().hex,
        trial_paths=TrialPaths(trial_dir=Path(tempfile.mkdtemp(prefix="prebuild_"))),
        task_env_config=task.config.environment,
    )
    return env._template_name, env._effective_cpus, env._effective_memory_mb


WARMUP_SCRIPT = Path(__file__).resolve().parent.parent / "tasks" / "image" / "warmup.sh"
WARMUP_DONE = "/tmp/.harbor-warmup-done"
WARMUP_START_CMD = (
    f"echo {base64.b64encode(WARMUP_SCRIPT.read_bytes()).decode()} | base64 -d | sh; touch {WARMUP_DONE}"
)


def ecr_password(region: str) -> str:
    token = boto3.client("ecr", region_name=region).get_authorization_token()["authorizationData"][0]
    return base64.b64decode(token["authorizationToken"]).decode().split(":", 1)[1]


async def build_one(sem, alias, cpus, mem, image, password, force):
    async with sem:
        if not force and await AsyncTemplate.alias_exists(alias):
            return alias, "exists", 0.0
        t0 = time.perf_counter()
        # The shared sandbox warm-up runs as the template's start command; E2B snapshots the template once it is done,
        # the same point at which AgentCore V2 snapshots its sessions (see tasks/image/warmup.sh).
        template = Template().from_image(image, username="AWS", password=password).set_start_cmd(
            WARMUP_START_CMD, f"test -f {WARMUP_DONE}")
        await AsyncTemplate.build(template=template, alias=alias, cpu_count=cpus, memory_mb=mem)
        return alias, "built", time.perf_counter() - t0


async def main_async(args):
    task_dirs = [p.parent for root in args.tasks for p in sorted(Path(root).glob("*/task.toml"))]
    targets = [harbor_alias(d) for d in task_dirs]
    password = ecr_password(args.region)
    sem = asyncio.Semaphore(args.parallel)
    results = await asyncio.gather(
        *(build_one(sem, a, c, m, args.image, password, args.force) for a, c, m in targets), return_exceptions=True
    )
    for r in results:
        print(r)
    failed = [r for r in results if isinstance(r, Exception)]
    print(f"templates: {len(results) - len(failed)} ok, {len(failed)} failed")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True, help="ECR image (index with linux/amd64)")
    ap.add_argument("--tasks", nargs="*", default=["tasks/train", "tasks/heldout"])
    ap.add_argument("--region", default=os.environ.get("AWS_REGION", "us-west-2"))
    ap.add_argument("--parallel", type=int, default=8)
    ap.add_argument("--force", action="store_true")
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
