[한국어](ko/02-tasks-and-images.md)

# 02. Task suite and multi-architecture images

In this step, you create 56 tasks (40 training + 16 held-out) that both sandboxes run identically, build one base image shared by all tasks for `linux/amd64` and `linux/arm64`, and push it to Amazon ECR. The step then explains how AgentCore Runtime (arm64 + shim) and E2B (amd64 templates) each use the same image.

Prerequisites: the tools from `00-prerequisites.md` (AWS CLI, Finch, `uv`) and the environment variable `HF_TOKEN`

Time required: a few minutes for task generation, up to tens of minutes for building and pushing the base image (depends on local network and CPU), a few minutes for prebuilding E2B templates

## 1. Why build a derived task suite

The starting point is the dataset used by the TRL Harbor example, `AdithyaSK/data_agent_rl_environment_train` (Kaggle data analysis question tasks). The upstream task environment cannot be used as is to compare the two sandboxes, so this guide selects a subset of tasks and rebuilds them as Harbor tasks in the same format.

| Upstream state | Problem | What this guide does |
|---|---|---|
| Task image `savatar101/env-data-agent-train:base` is amd64 only | AgentCore Runtime runs only arm64 images [documented] | Rebuild the same recipe (`python:3.12-slim` + data analysis packages) with pinned versions for multiple architectures |
| On sandbox start, the healthcheck downloads Kaggle data from a Hugging Face bucket | Requires internet, anonymous access hits rate limits, and network latency unrelated to the sandbox gets mixed into measurements | Include the selected tasks' data in the image ahead of time and run tasks with `no-network` |
| No oracle solution | No way to confirm that a task is valid (environment, data, verifier) in each sandbox | Add `solution/solve.sh` that writes the correct answer |
| LLM judge step in the verifier (`OPENAI_API_KEY`) | External API dependency, reward noise | Select only tasks with numeric answers and remove the judge step |

The repository contains only the selection and generation scripts and the generated task directories, not the Kaggle data (`tasks/image/data/` is in `.gitignore`). The upstream instructions and grader (`tests/grader.py`) are kept as is.

## 2. Task selection rules

[`tasks/select_tasks.py`](../tasks/select_tasks.py) combines the upstream `manifest.parquet` with the difficulty registry (`registry.json` from `AdithyaSK/data_agent_rl_environment_train_difficulty_ranked`, per-task rollout solve fraction) to produce `tasks/suite.json`. With the same seed and the same dataset revision, the result is the same. Both dataset revisions are pinned in the script (`TRAIN_REVISION` = `4073bb9b817aba164d8697cbe504a646522cd07a`, `RANKED_REVISION` = `5923562863a29724c026021a2d16cb8e44e376d9`) and recorded in `suite.json` (`source.train_revision`, `source.ranked_revision`); `build_suite.py` downloads the task files from the same train revision.

| Rule | Default | Reason |
|---|---|---|
| `verdict` | `verified` | Only tasks that passed upstream verification |
| Answer format | Numeric (`^[-+]?\d[\d,]*(\.\d+)?%?$`) | Reward is decided by the grader's exact match and numeric tolerance stages alone |
| `package_tier` | 1 | Needs only packages installed in the base image |
| Dataset size | 20 MB or less | All data fits in one shared image |
| solve fraction | 0.125 to 0.25 (`--solve-lo`, `--solve-hi`) | The difficulty must be such that the policy model gets only some right, so that rewards differ within a GRPO group and provide a learning signal |
| Tasks per dataset | Up to 3 (`--max-per-dataset`) | Prevents skew toward particular datasets |
| Held-out split | 35% of datasets are set aside for held-out first (`--heldout-dataset-frac`) | Held-out tasks do not share Kaggle datasets with training tasks |
| Seed | 42 | Deterministic selection |

The dataset order is shuffled with the seed, and tasks are then picked one per dataset in turn (round-robin).

Final suite (`tasks/suite.json`):

| Split | Tasks | Kaggle datasets | Mean difficulty registry solve fraction |
|---|---|---|---|
| train | 40 | 27 | 0.18 |
| heldout | 16 | 14 (no overlap with train) | 0.20 |

The data included in the image totals about 57 MB.

```bash
export HF_TOKEN=...                     # environment variable only (anonymous access hits rate limits)
uv run --with pandas --with pyarrow --with "huggingface_hub>=1.33" --with tomli-w \
  python3 tasks/select_tasks.py     # -> tasks/suite.json
uv run --with pandas --with pyarrow --with "huggingface_hub>=1.33" --with tomli-w \
  python3 tasks/build_suite.py      # -> tasks/train/, tasks/heldout/, tasks/image/data/
```

The scripts declare no dependencies of their own, so `uv run --with` supplies them (`pandas`, `pyarrow`, `huggingface_hub>=1.33`, `tomli-w`).

`select_tasks.py` lists the bucket for each candidate dataset to compute its size, so it can take a few minutes to run.

## 3. Task structure

[`tasks/build_suite.py`](../tasks/build_suite.py) converts upstream tasks to the Harbor task format and downloads each task's Kaggle data to `tasks/image/data/<owner>__<dataset>/` (files are flattened, with no subfolders). Example: `tasks/train/0000_939_939639_qa_2/`

```
instruction.md           # upstream prompt (LLM-judge sentence removed)
task.toml                # config (below)
environment/Dockerfile   # ARG BASE_IMAGE=harbor-rl-tasks-base:latest; FROM ${BASE_IMAGE}; WORKDIR /workdir (identical for all 56 tasks)
tests/test.sh            # reads /workdir/answer.txt, writes /logs/verifier/reward.txt
tests/grader.py          # upstream grader: exact match, then numeric tolerance
solution/solve.sh        # oracle: printf '<gold>' > /workdir/answer.txt
```

What differs from upstream in `task.toml`:

| Key | Value | Notes |
|---|---|---|
| `task.name` | `harbor-rl-suite/<task_dir>` | |
| `environment.cpus`, `memory_mb` | `2`, `4096` | E2B template resources. AgentCore sessions are fixed at 2 vCPU / 8 GB, so memory differs (stated in `05-comparison.md`) |
| `environment.network_mode` | `"no-network"` | See 3.1 below |
| `environment.healthcheck.command` | `rm -rf /home/user/input && ln -s /data/<owner>__<dataset> /home/user/input && [ -n "$(ls /home/user/input/)" ]` | Symlinks the data included in the image instead of downloading it. Runs the same way in both sandboxes through Harbor `run_healthcheck()` |
| `environment.env` | `KAGGLE_DATASET_NAME` | |
| `verifier.env` | `EXPECTED_ANSWER`, `QUESTION`, `REWARD_MODE`, `ATOL`, `RTOL` (`OPENAI_API_KEY` removed) | No judge step, no `pip install openai` during verification |
| `metadata` | `suite_split`, `sweep_solve_frac`, `data_prefix` | For analysis |

The reward is 0.0 or 1.0. If the answer file is missing or empty, `test.sh` records 0.0.

### 3.1 `network_mode = "no-network"`

Every task's `task.toml` contains the following setting, written by `build_suite.py`.

```toml
[environment]
network_mode = "no-network"
```

- The data is in the image, so tasks do not need the network.
- Arbitrary code generated by the model runs inside the sandbox, so blocking outbound traffic (egress) is safer.
- Both sandboxes run under the same conditions (no internet), so the comparison is fair.

Harbor checks this policy when it creates the environment object (`BaseEnvironment._validate_network_policy_support`, Harbor 0.23.0). If the environment does not declare that it supports blocking internet access, Harbor rejects the task with the error `network_mode='no-network' is not supported by ...`; it does not silently allow internet access.

| Sandbox | How the policy is enforced |
|---|---|
| E2B | The Harbor E2B environment creates the sandbox with `allow_internet_access=False` |
| AgentCore | Network is configured per runtime, not per session. The runtime is deployed in VPC mode in subnets with no internet route (`03b-sandbox-agentcore.md`), and `AgentCoreEnvironment` declares support for blocking internet access only when the environment variable `AGENTCORE_NETWORK_ISOLATED=1` is set |

TRL's Harbor integration does not pass the network policy to Harbor, so the training harness interprets the task's policy itself and passes it along (`04-grpo-training.md` 6.1). We confirmed that `curl https://example.com` fails inside the sandbox (E2B: DNS resolution failure, AgentCore: connection timeout) and that the task data in `/home/user/input` is readable.

## 4. Shared multi-architecture base image

All 56 tasks share one image, `harbor-rl/tasks-base` ([`tasks/image/Dockerfile`](../tasks/image/Dockerfile)).

- Base: `python:3.12-slim-trixie@sha256:05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f` (pinned by digest) + `ca-certificates`, `curl`, `git`
- Packages: [`requirements.txt`](../tasks/image/requirements.txt) (pinned versions of pandas, numpy, scipy, scikit-learn, statsmodels, matplotlib, seaborn, plotly, tabulate from `requirements.in`)
- Data: `/data/<owner>__<dataset>/`
- Directories: `/home/user/input`, `/workdir`, `/logs/verifier`

This guide uses tag `v2`. The image size is far below the AgentCore container image limit (2 GB) [documented].

### 4.1 Build and push

[`tasks/image/build-push.sh`](../tasks/image/build-push.sh) requires `TAG` (no default). If the ECR repository `harbor-rl/tasks-base` does not exist, the script creates it with scan on push enabled and the `Project=harbor-rl-sandbox` tag, and then logs in, builds, and pushes with Finch.

```bash
export AWS_REGION=us-west-2
TAG=v2 ./tasks/image/build-push.sh
# -> <ACCOUNT_ID>.dkr.ecr.us-west-2.amazonaws.com/harbor-rl/tasks-base:v2
```

The commands the script runs, and their Docker equivalents:

```bash
REGISTRY=<ACCOUNT_ID>.dkr.ecr.us-west-2.amazonaws.com
IMAGE=$REGISTRY/harbor-rl/tasks-base:v2

# Finch: build both architectures, then push one OCI image index
aws ecr get-login-password --region us-west-2 | finch login --username AWS --password-stdin $REGISTRY
finch build --platform linux/amd64,linux/arm64 -t $IMAGE tasks/image
finch push --platform linux/amd64,linux/arm64 $IMAGE

# Docker equivalent (buildx builds and pushes in one step)
aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin $REGISTRY
docker buildx build --platform linux/amd64,linux/arm64 -t $IMAGE --push tasks/image
```

Verify: the image index must contain both architectures.

```bash
aws ecr describe-images --repository-name harbor-rl/tasks-base --region us-west-2 \
  --query 'imageDetails[].[imageTags[0],imageManifestMediaType,imageSizeInBytes]' --output table
```

The `v2` tag entry is `application/vnd.oci.image.index.v1+json`, and two untagged per-architecture manifests appear alongside it.

> On an Apple silicon Mac, the amd64 side is built under emulation. This image only installs wheels and copies data, so the default Finch VM settings are sufficient. The large Trainer image, in contrast, is built in AWS CodeBuild (amd64) (`04-grpo-training.md`).

## 5. How each sandbox uses the same image

```
harbor-rl/tasks-base:v2 (OCI image index)
 ├─ linux/arm64 ─► + shim layer + warmup.sh ─► harbor-rl/tasks-agentcore:v2 ─► one AgentCore Runtime (all 56 tasks)
 └─ linux/amd64 ─► E2B Template().from_image(...).set_start_cmd(warmup.sh) ─► 56 templates (alias = Harbor naming rule)
```

**Shared warm-up before the snapshot.** Both sandboxes start sessions from a snapshot (AgentCore V2 snapshots the initialized container, E2B snapshots the built template). [`tasks/image/warmup.sh`](../tasks/image/warmup.sh) runs once before that snapshot on both: it imports the task libraries (`pandas`, `numpy`, `scipy`, `sklearn`, `statsmodels`, `seaborn`, `plotly`, `tabulate`, `matplotlib.pyplot`) and reads every file under `/data`, so the snapshot already holds them in memory. This follows the AgentCore V2 optimization guidance to do expensive, reusable work such as importing dependencies at startup, before the snapshot [documented]. The script only reads files and creates no per-session state (no random values, time or credentials), so nothing that must differ between sessions is cloned. The script is not part of the base image; each sandbox adds it as described in 5.1 and 5.2.

### 5.1 AgentCore: arm64 + shim, one runtime

AgentCore Runtime requires an HTTP service contract (port 8080, `GET /ping`, `POST /invocations`), so a small Go shim ([`agentcore/shim/main.go`](../agentcore/shim/main.go)) is layered on top of the base image ([`agentcore/image/Dockerfile`](../agentcore/image/Dockerfile)). The shim is statically built for `linux/arm64` in a `golang:1.25-bookworm` stage pinned by digest (`@sha256:3b4a1151...`), placed at `/usr/local/bin/agentcore-shim`, and set as the `ENTRYPOINT`. The Dockerfile also copies `warmup.sh` to `/usr/local/share/harbor/warmup.sh`, and the shim runs it at container start before it listens on 8080 (at most 90 seconds, below the 120-second V2 initialization limit), so the V2 snapshot taken after the first healthy `/ping` includes the warm-up. The task commands themselves run through `InvokeAgentRuntimeCommand`.

[`agentcore/deploy_runtime.sh`](../agentcore/deploy_runtime.sh) handles the image build, execution role, and runtime creation in one go. `TAG` is required and uses the same tag as `tasks-base`. With `SKIP_BUILD=1`, it reuses the already pushed `tasks-agentcore:$TAG`. The detailed procedure is in `03b-sandbox-agentcore.md`.

The build context is a temporary directory that holds only `shim/main.go` and `warmup.sh` (copied from `tasks/image/warmup.sh`), because the Dockerfile needs files from both `agentcore/` and `tasks/`.

```bash
# Build context (what deploy_runtime.sh prepares)
CTX=$(mktemp -d) && mkdir -p $CTX/shim
cp agentcore/shim/main.go $CTX/shim/ && cp tasks/image/warmup.sh $CTX/

# Finch (what deploy_runtime.sh runs)
finch build --platform linux/arm64 --build-arg BASE_IMAGE=$REGISTRY/harbor-rl/tasks-base:v2 \
  -f agentcore/image/Dockerfile -t $REGISTRY/harbor-rl/tasks-agentcore:v2 $CTX
finch push --platform linux/arm64 $REGISTRY/harbor-rl/tasks-agentcore:v2

# Docker equivalent
docker buildx build --platform linux/arm64 --build-arg BASE_IMAGE=$REGISTRY/harbor-rl/tasks-base:v2 \
  -f agentcore/image/Dockerfile -t $REGISTRY/harbor-rl/tasks-agentcore:v2 --push $CTX
```

**One runtime handles the whole suite.** An AgentCore runtime is bound to one image, and every time you create a runtime or change its image, you have to wait for the create/update to finish. In this suite, all 56 tasks have the same `environment/`, so there is one image and therefore one runtime (`harbor_rl_tasks`). Per-task differences (the data path) are handled by the healthcheck with a symlink after the session starts.

**When the number of tasks grows (content-hash deduplication).** Creating one runtime per task makes the number of runtimes and the creation wait time grow in proportion to the number of tasks. Instead, group task environments by content hash so that tasks using the same image share one runtime. Harbor also computes a SHA-256 hash of the environment directory (`environment_content_hash`), so you can use that value as the group key. The open source project `harbor-on-agentcore` reports that it fit a large task set onto far fewer runtimes this way [documented]. This guide's suite has only one group, so no separate implementation is included.

### 5.2 E2B: amd64 + prebuilt templates

Harbor's E2B environment (`harbor/environments/e2b.py`, Harbor 0.23.0) computes a template alias `{task short name}__{first 12 characters of the environment/ directory hash}` for each task. If the alias does not exist, it builds the template itself with `Template().from_image(image)` (no registry credentials) or `from_dockerfile`, but the task Dockerfile is `FROM ${BASE_IMAGE}` (private ECR), so this path cannot pull the image.

Therefore, [`bench/prebuild_e2b_templates.py`](../bench/prebuild_e2b_templates.py) actually instantiates Harbor's E2B environment object to obtain the alias, CPU, and memory with the same code Harbor uses, and then prebuilds the templates from the amd64 variant of the ECR image index.

```python
# ecr_password(): password part of the base64-decoded ECR authorization token (valid 12 h)
# WARMUP_START_CMD runs tasks/image/warmup.sh, then touches /tmp/.harbor-warmup-done
template = Template().from_image(image, username="AWS", password=password).set_start_cmd(
    WARMUP_START_CMD, f"test -f {WARMUP_DONE}")
await AsyncTemplate.build(template=template, alias=alias, cpu_count=cpus, memory_mb=mem)
```

- The shared warm-up is the template start command; the ready check waits for `/tmp/.harbor-warmup-done`, and E2B snapshots the template after the start command has finished, so every sandbox created from it starts with the warm-up done. The script is read from `tasks/image/warmup.sh` in the Trainer image.

- No long-lived access keys are passed to E2B. The only credential used for the build is an ECR authorization token valid for 12 hours (user name `AWS`).
- During training, the alias already exists, so Harbor creates sandboxes with the unmodified E2B environment.
- All 56 tasks have the same `environment/`, so the 12-character hash is the same for all of them, and the aliases differ only by task name (56 templates with identical content).
- The default parallelism is 8 (`--parallel`), and existing aliases are skipped. After changing the image, rebuild with `--force`.
- The principal that runs the script (the Trainer Pod) needs `ecr:GetAuthorizationToken` and pull permission on the `harbor-rl/tasks-base` repository ([`infra/iam/trainer-pod-policy.json`](../infra/iam/trainer-pod-policy.json)).

Self-hosted E2B sits behind an internal ALB and is reachable only from the HyperPod VPC (through peering), so the prebuild runs as a Job inside the cluster. The Trainer image contains `bench/` and `tasks/` (`TAG` is the Trainer image tag, `04-grpo-training.md` section 3).

The commands in sections 5.2 and 5.3 are shown here for reference and are run later, in [`03a-sandbox-e2b.md`](03a-sandbox-e2b.md) and [`03b-sandbox-agentcore.md`](03b-sandbox-agentcore.md). They need the Trainer image (section 3 of [`04-grpo-training.md`](04-grpo-training.md)), the namespace, ServiceAccount and Secret (section 6 of [`01-hyperpod-eks.md`](01-hyperpod-eks.md)), and the deployed sandboxes.

```bash
export REGISTRY=<ACCOUNT_ID>.dkr.ecr.us-west-2.amazonaws.com
TAG=v12 ./infra/k8s/submit.sh e2b-prebuild 0 \
  python3 bench/prebuild_e2b_templates.py --image $REGISTRY/harbor-rl/tasks-base:v2
kubectl -n harbor-rl logs -f job/e2b-prebuild     # last line: "templates: 56 ok, 0 failed"
```

Run the prebuild only as this Job, also with E2B Cloud. The ECR token is handed to the E2B template builder, and a token obtained with the Trainer Pod role can pull only the `harbor-rl/tasks-base` repository. Running the script locally with broader credentials would hand over a token that can pull every repository those credentials can read.

### 5.3 Task validation (oracle)

Run every task's oracle (`solution/solve.sh`) in both sandboxes with the same harness used for training, to confirm that the environment, data, and verifier work on each architecture ([`bench/oracle_check.py`](../bench/oracle_check.py)).

```bash
TAG=v12 ./infra/k8s/submit.sh oracle-e2b 0 python3 bench/oracle_check.py --sandbox e2b --out /results/oracle
TAG=v12 AGENTCORE_RUNTIME_ARN=arn:aws:bedrock-agentcore:us-west-2:<ACCOUNT_ID>:runtime/<RUNTIME_ID> \
  ./infra/k8s/submit.sh oracle-agentcore 0 python3 bench/oracle_check.py --sandbox agentcore --out /results/oracle
```

The pass counts and time per task (the cost of porting to arm64) are in section 1 of `05-comparison.md`.

## 6. arm64 considerations

- **Package wheels:** When extending to another task suite, first check whether any package lacks an aarch64 wheel and needs a source build. For this suite, builds for both architectures succeed with the same `requirements.txt`.
- **numpy and OpenBLAS:** `harbor-on-agentcore` reports that `import numpy` terminated with SIGILL on arm64 and that it set `OPENBLAS_CORETYPE`. With the pinned versions in this image it works without that setting, so nothing was added. If you change versions, check `python3 -c "import numpy"` on arm64 first.
- **V2 snapshot startup:** AgentCore V2 sessions start from a snapshot taken at initialization, so the random seed, uuid, and time-related state at that point are replicated across sessions. These tasks only read data deterministically and are not affected, but tasks that depend on a seed must reseed after the session starts.
- **First import latency:** Right after snapshot restore, the first command that imports a heavy package such as pandas can still be slower than later commands, even with the shared warm-up. The measured distribution for both sandboxes is in section 2 of `05-comparison.md`.
- **Memory conditions:** `memory_mb=4096` applies only to E2B templates; AgentCore sessions are fixed at 8 GB. The datasets are 20 MB or less, so the impact is small, but `05-comparison.md` states it as a difference in comparison conditions.

## 7. Common pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| Dataset and bucket listings fail with rate limits | Rate limits on anonymous Hugging Face access | Set `HF_TOKEN` as an environment variable and run again |
| `build-push.sh` exits immediately with `set TAG` | Image scripts have no default for `TAG` | `TAG=v2 ./tasks/image/build-push.sh` |
| Trying to create an AgentCore runtime with an amd64 image | AgentCore Runtime supports only arm64 [documented] | Use the arm64 variant of the index, and build the AgentCore image with `--platform linux/arm64` |
| Sessions do not start after creating the AgentCore runtime | The base image alone does not satisfy the `/ping`, `/invocations` contract | Use the `tasks-agentcore` image with the shim layer added (`ENTRYPOINT agentcore-shim`) |
| All rollouts fail with `network_mode='no-network' is not supported by ...` | The environment does not declare support for blocking internet access, so Harbor rejects the task | AgentCore: deploy the runtime in isolated VPC mode and set `AGENTCORE_NETWORK_ISOLATED=1` (the `submit.sh` default). Other providers: check whether they support blocking internet access |
| Harbor builds the E2B template itself and fails at `FROM ${BASE_IMAGE}` | The Harbor E2B environment does not pass private registry credentials | Create the same aliases ahead of time with `prebuild_e2b_templates.py` before training |
| Templates were prebuilt, but training tries to build them again | The alias includes the `environment/` content hash, so changing the task Dockerfile changes the alias | Rerun the prebuild after changing `environment/` |
| The digest-pinned base image was removed from the registry, or needs a security patch | A digest pin pulls the same image even after the tag moves to a different image | Look up the new digest (`finch image inspect`, or `docker buildx imagetools inspect`), update `FROM` in `tasks/image/Dockerfile`, and build with a new tag |
| The upstream dataset was updated, but the selection result is unchanged | The dataset revisions are pinned in `select_tasks.py` and `suite.json` | Change `TRAIN_REVISION` and `RANKED_REVISION` only when you update on purpose, and regenerate the suite |
| The image was pushed again, but E2B sandboxes have the old content | Existing aliases are skipped | Rebuild with `--force` |
| Sandbox creation on self-hosted E2B fails with `404: method not allowed` | E2B SDK 2.51.0 uses `POST /v2/sandboxes`, which this guide's self-hosted E2B API does not support (the template build API is not affected) | Pin `e2b==2.50.0` in the Trainer image |
| `400: Timeout cannot be greater than 1 hours` on self-hosted E2B | The default team tier is 1 hour / 20 concurrent. Harbor creates sandboxes with a 24-hour timeout | Adjust the team tier (`finalize.sh` in `03a-sandbox-e2b.md`) |
| Self-hosted E2B is not reachable from a laptop | Internal ALB, names resolve only to private IPs | Run the prebuild and oracle checks as cluster Jobs |
| On AgentCore, `cat` or `python3` with no arguments hangs until the timeout | `InvokeAgentRuntimeCommand` passes a stdin pipe that never sends EOF | The AgentCore environment prefixes every command with `exec </dev/null;` and wraps it in `/bin/bash -c` |
| Changing `ATOL`/`RTOL` in `task.toml` does not change grading | The upstream `grader.py` does not read these values and uses fixed tolerances | Modify the grader to change tolerances |

Source URLs and check dates are in `references.md`.

Next steps: `03a-sandbox-e2b.md`, `03b-sandbox-agentcore.md`
