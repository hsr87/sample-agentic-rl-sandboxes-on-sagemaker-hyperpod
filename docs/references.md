[한국어](ko/references.md)

# References

The evidence behind the claims and numbers in this guide. Section 1 lists sources and check dates, section 2 lists differences between the official documentation and actual behavior (the basis for the "Common pitfalls" in each chapter of the guide), and section 3 lists the verification results for the facts assumed when designing the guide. Official AWS documentation and repository source code are the primary evidence; blogs are used only as supporting evidence.

## 1. Sources (check date)

### 1.1 Amazon SageMaker HyperPod (EKS)

| Topic | Source | Check date |
|---|---|---|
| Official HyperPod EKS CloudFormation template (S3 Last-Modified 2026-09-29), template repository | https://aws-sagemaker-hyperpod-cluster-setup-us-west-2-prod.s3.us-west-2.amazonaws.com/templates/main-stack-eks-based-template.yaml , https://github.com/aws/sagemaker-hyperpod-cluster-setup | 2026-09-30 |
| HyperPod EKS prerequisites (Pod Identity support) | https://docs.aws.amazon.com/sagemaker/latest/dg/sagemaker-hyperpod-eks-prerequisites.html | 2026-09-30 |
| Creating a cluster with the console/CloudFormation | https://docs.aws.amazon.com/sagemaker/latest/dg/smcluster-getting-started-eks-console-create-cluster-cfn.html | 2026-09-30 |
| HyperPod Helm chart | https://docs.aws.amazon.com/sagemaker/latest/dg/sagemaker-hyperpod-eks-install-packages-using-helm-chart.html | 2026-09-30 |
| Lifecycle scripts (repository renamed: `awsome-distributed-ai`) | https://github.com/awslabs/awsome-distributed-ai/tree/main/1.architectures/7.sagemaker-hyperpod-eks/LifecycleScripts/base-config | 2026-09-30 |
| HyperPod CLI (`sagemaker-hyperpod` 3.11.0) | https://github.com/aws/sagemaker-hyperpod-cli | 2026-09-30 |

### 1.2 Amazon Bedrock AgentCore Runtime

| Topic | Source | Check date |
|---|---|---|
| `InvokeAgentRuntimeCommand` API (event stream, `command` 1 to 65,536 characters, `timeout` 1 to 3,600 seconds, default 300 seconds) | https://docs.aws.amazon.com/bedrock-agentcore/latest/APIReference/API_InvokeAgentRuntimeCommand.html | 2026-09-30 |
| Execute command guide (no shell state retained, "25 TPS" wording) | https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-execute-command.html | 2026-09-30 |
| `InvokeAgentRuntime` API (payload up to 100,000,000 bytes, `runtimeSessionId` 33 to 256 characters) | https://docs.aws.amazon.com/bedrock-agentcore/latest/APIReference/API_InvokeAgentRuntime.html | 2026-10-01 |
| Quotas (active sessions, session creation TPS, data plane TPS, image size, session lifetime) | https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html | 2026-09-30 |
| HTTP protocol contract (`/ping`, `/invocations`, port 8080) | https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-http-protocol-contract.html | 2026-09-30 |
| Platform versions (V1, V2), V2 GA announcement | https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-how-it-works.html#runtime-platform-versions , https://aws.amazon.com/about-aws/whats-new/2026/09/new-agentcore-runtime-generally-available/ | 2026-09-30 |
| V2 optimization guide ("Do expensive, reusable work as your process starts, before the snapshot. For example, import dependencies, load model weights, or read static configuration from your deployment bundle."; with its own HTTP server, report healthy from `/ping` only after initialization completes; complete initialization within 120 seconds; compute random values, time and credentials per request, not at startup) | https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-v2-optimize.html | 2026-09-30 (startup statement 2026-10-07) |
| Interface VPC endpoints (AWS PrivateLink): data plane endpoint `com.amazonaws.<region>.bedrock-agentcore` (Runtime data plane supported), control plane `bedrock-agentcore-control`, Gateway `bedrock-agentcore.gateway`; private DNS keeps the default Regional DNS name; endpoint policies can restrict SigV4 callers by IAM principal | https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/vpc-interface-endpoints.html | 2026-10-07 |
| VPC mode (supported AZ IDs, required endpoints for a VPC without internet, ENIs retained up to 8 hours, minimum S3 bucket permissions for container agents: the regional ECR layer bucket `prod-<region>-starport-layer-bucket`) | https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-vpc.html | 2026-09-30 (S3 bucket permissions 2026-10-07) |
| Sessions, stopping sessions, permissions | https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-sessions.html , https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-stop-session.html , https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-permissions.html | 2026-09-30 |
| Observability (runtime metrics) | https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-runtime-metrics.html | 2026-09-30 |
| Runtime Instances (x86, GPU) | https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-instances-how-it-works.html | 2026-09-30 |
| V2 introduction blog (supporting evidence) | https://aws.amazon.com/blogs/machine-learning/the-new-agentcore-runtime-elastic-optimized-and-consistently-fast-starts/ | 2026-09-30 |
| Harbor AgentCore provider code (Apache-2.0, `acr-kit-v1` branch, commit 4ee0cb25), AgentCore RL toolkit (Apache-2.0) | https://github.com/mightma/harbor/tree/acr-kit-v1 , https://github.com/awslabs/agentcore-rl-toolkit | 2026-09-30 |
| harbor-on-agentcore (reference only, no LICENSE) | https://github.com/mightma/harbor-on-agentcore | 2026-09-30 |
| Harbor issue #3446 requesting an official AgentCore provider | https://github.com/harbor-framework/harbor/issues/3446 | 2026-09-30 |

### 1.3 E2B

| Topic | Source | Check date |
|---|---|---|
| E2B pricing | https://e2b.dev/pricing | 2026-09-30 |
| Billing documentation | https://docs.e2b.dev/billing.md | 2026-09-30 |
| Increasing concurrency | https://docs.e2b.dev/faq/increase-concurrency.md | 2026-09-30 |
| Maximum sandbox lifetime | https://docs.e2b.dev/faq/sandbox-lifetime.md | 2026-09-30 |
| Template V2 (remote builds), V1 build deprecation (2026-08-01) | https://docs.e2b.dev/migration/template-v2.md , https://docs.e2b.dev/migration/v1-build-deprecation.md | 2026-09-30 |
| Persistence (pause/resume, snapshot) | https://docs.e2b.dev/sandbox/persistence.md | 2026-09-30 |
| E2B SDK source (sandbox creation path, egress control `allow_internet_access`, network deny_out/allowlist) | https://github.com/e2b-dev/E2B | 2026-10-01 |
| Self-hosted sample `aws-samples/sample-e2b-on-aws` (commit 830b516: CloudFormation + Terraform + Nomad, cleanup procedure in the README, `infra-iac/destroy.sh`, `destroy-cnf.sh`) | https://github.com/aws-samples/sample-e2b-on-aws | 2026-10-01 (cleanup scripts 2026-10-06) |

### 1.4 Harbor, TRL, model, dataset

| Topic | Source | Check date |
|---|---|---|
| Harbor `BaseEnvironment` | https://github.com/harbor-framework/harbor/blob/9b168361ebe973113640b9183b03cbd7884d720e/src/harbor/environments/base.py | 2026-09-30 |
| Harbor `EnvironmentFactory` (`import_path`) | https://github.com/harbor-framework/harbor/blob/9b168361ebe973113640b9183b03cbd7884d720e/src/harbor/environments/factory.py | 2026-09-30 |
| Harbor E2B environment | https://github.com/harbor-framework/harbor/blob/9b168361ebe973113640b9183b03cbd7884d720e/src/harbor/environments/e2b.py | 2026-09-30 |
| TRL Harbor documentation | https://huggingface.co/docs/trl/main/en/harbor | 2026-09-30 |
| TRL `HarborSpec`, `HarborEnv`, `GRPOTrainer` source | https://github.com/huggingface/trl/blob/4c623f3d154548209963842c6717e99f51b5a5b2/trl/experimental/harbor/_spec.py , https://github.com/huggingface/trl/blob/4c623f3d154548209963842c6717e99f51b5a5b2/trl/experimental/harbor/_env.py , https://github.com/huggingface/trl/blob/4c623f3d154548209963842c6717e99f51b5a5b2/trl/trainer/grpo_trainer.py | 2026-09-30 |
| TRL releases (PyPI) | https://pypi.org/pypi/trl/json | 2026-09-30 |
| TRL Harbor example | https://github.com/huggingface/trl/blob/main/examples/grpo_harbor/grpo_harbor.py | 2026-09-30 |
| Related TRL issues and PRs | [#6776](https://github.com/huggingface/trl/issues/6776), [#7428](https://github.com/huggingface/trl/issues/7428), [#7449](https://github.com/huggingface/trl/issues/7449), [PR #6948 (proposal to remove the Harbor integration)](https://github.com/huggingface/trl/pull/6948) | 2026-09-30 |
| Gemma 4 E4B model configuration | https://huggingface.co/google/gemma-4-E4B-it/blob/main/config.json | 2026-09-30 |
| vLLM Gemma 4 recipe, mixed head size issue | https://docs.vllm.ai/projects/recipes/en/stable/Google/Gemma4.html , https://github.com/vllm-project/vllm/issues/38887 | 2026-09-30 |
| Original task dataset, original image tags | https://huggingface.co/datasets/AdithyaSK/data_agent_rl_environment_train , https://hub.docker.com/v2/repositories/savatar101/env-data-agent-train/tags | 2026-09-30 |
| Difficulty-ranked dataset | https://huggingface.co/datasets/AdithyaSK/data_agent_rl_environment_train_difficulty_ranked | 2026-09-30 |

### 1.5 Pricing and instance specifications (us-west-2, on-demand)

| Item | Value | Source | Check date |
|---|---|---|---|
| HyperPod `ml.p4d.24xlarge` cluster | $25.91001756/h (usage type `USW2-Cluster:ml.p4d.24xlarge`, AWS Pricing API) | https://aws.amazon.com/sagemaker/ai/pricing/ | 2026-10-01 |
| AgentCore Runtime V2 | $0.1276 per vCPU-hour, $0.0169 per GB-hour, per-second billing (minimum 1 second, minimum 128 MB memory). V1 is $0.0895 / $0.00945 | https://aws.amazon.com/bedrock/agentcore/pricing/ | 2026-09-30 |
| E2B Cloud | $0.000014/vCPU-second, $0.0000045/GiB-second | https://e2b.dev/pricing | 2026-09-30 |
| Self-hosted E2B nodes | `c8i.metal-48xl` $8.99616/h, `t3.xlarge` $0.1664/h, `m8i.4xlarge` $0.84672/h, `c7i.xlarge` $0.1785/h (AWS Pricing API) | https://aws.amazon.com/ec2/pricing/on-demand/ | 2026-10-01 |
| `c8i.metal-48xl` specifications | 192 vCPU, 384 GiB (`aws ec2 describe-instance-types`) | https://aws.amazon.com/ec2/instance-types/c8i/ | 2026-10-01 |
| NAT gateway, ALB, Aurora Serverless v2, ElastiCache Serverless (Redis) | $0.045/h, $0.0225/h, $0.12/ACU-h, storage $0.125/GB-h (minimum 1 GB) | https://aws.amazon.com/vpc/pricing/ , https://aws.amazon.com/elasticloadbalancing/pricing/ , https://aws.amazon.com/rds/aurora/pricing/ , https://aws.amazon.com/elasticache/pricing/ | 2026-10-01 |
| EKS cluster | Standard support $0.10/h, extended support $0.60/h | https://aws.amazon.com/eks/pricing/ | 2026-10-06 |
| VPC interface endpoint | $0.01/h per endpoint-AZ (usage type `USW2-VpcEndpoint-Hours`, AWS Pricing API), $0.01 per GB processed | https://aws.amazon.com/privatelink/pricing/ | 2026-10-06 |
| Secrets Manager | $0.40 per secret per month, $0.05 per 10,000 API calls | https://aws.amazon.com/secrets-manager/pricing/ | 2026-10-06 |

## 2. Differences between documentation and actual behavior (check date)

Each item is behavior confirmed in this guide's configuration (the versions in sections 1.4 and 1.5). "Handling" describes how the scripts and code in this repository deal with it. Measured values are in [`05-comparison.md`](05-comparison.md).

### 2.1 HyperPod EKS

| Check date | Difference | Handling |
|---|---|---|
| 2026-09-30 | The template uses `Transform: AWS::LanguageExtensions`, so `CAPABILITY_AUTO_EXPAND` is required, but the documentation mentions only `CAPABILITY_IAM` and `CAPABILITY_NAMED_IAM` | `create-cluster.sh` specifies all three capabilities |
| 2026-09-30 | The template's default AZs are in us-east-2 (`use2-az1,use2-az2`) and the default Kubernetes is 1.34 (standard support ends 2026-12). The `hyp` CLI default of 1.31 is already in extended support ($0.60/h) | AZs and version (1.35) are set explicitly in `params.json` |
| 2026-09-30 | Even when p4d capacity is insufficient, the CloudFormation stack reports `CREATE_COMPLETE` and the cluster reports `InService`. The template default `NodeProvisioningMode=Continuous` retries in the background | Do not rely only on stack completion; check the node count with `CurrentCount` from `aws sagemaker describe-cluster` and with `list-cluster-events` |
| 2026-09-30 | An instance group's `OverrideVpcConfig` cannot be changed with `update-cluster` (ValidationException) | If a different AZ is needed, add a new instance group |
| 2026-09-30 | The template prefixes the EKS cluster name with `ResourceNamePrefix` (`EKSClusterName=harbor-rl-hp-eks` → `harbor-rl-hp-harbor-rl-hp-eks`) | Look up the actual name with `describe-cluster --query Orchestrator.Eks.ClusterArn` and use it |
| 2026-09-30 | Querying flexible training plans can fail with an error saying an account allowlist is required | This guide is based on on-demand capacity. Contact your AWS account team if needed |
| 2026-09-30 | The lifecycle script repository was renamed from `awsome-distributed-training` to `awsome-distributed-ai` (the old URL in the template works via redirect) | The guide shows the new URL |

### 2.2 TRL, vLLM

| Check date | Difference | Handling |
|---|---|---|
| 2026-09-30 | `HarborSpec(environment_type=...)` does not accept an import path (`EnvironmentType` enum validation). The error only appears at the first `reset()` | `agent=` accepts `"pkg.mod:Class"`, so a harness subclass is passed through this path, and inside it the custom environment is selected with Harbor's `import_path` |
| 2026-09-30 | TRL ignores the timeouts in `task.toml` (tool calls default to 180 seconds, the verifier has no timeout) | The same values apply to both sandboxes, so the comparison is not affected |
| 2026-09-30 | TRL's Harbor environment does not pass the task's network policy to the environment | `training/harness.py` and `bench/sandbox_bench.py` obtain the policy with Harbor's `resolve_agent_env_baseline` and pass it as `network_policy=`. If a provider cannot enforce the policy, Harbor rejects the task |
| 2026-09-30 | TRL 1.14.1 `HarborEnv.__del__` hangs forever at interpreter shutdown waiting on an event loop that has already stopped. Sandboxes open at shutdown are also not cleaned up (Harbor creates E2B sandboxes with a 24-hour timeout) | The harness makes `__del__` non-blocking and stops all live sandboxes in a shutdown hook that runs before the thread pool closes |
| 2026-09-30 | TRL 1.14.1 (same on main 7379929): with vLLM server mode + tool calls + 2 or more training processes, `IndexError` in `_tool_call_loop`. Server-mode generation assumes every rank has the same number of requests, but in the tool loop it differs per rank. Mismatched collectives can deadlock | `training/trl_patches.py`: computes offsets from per-rank counts, and ranks that finish first join the collectives with empty requests. Applied equally to both sandboxes |
| 2026-09-30 | TRL exposes every public method of the environment class as a tool. Leaving a helper method public causes `DocstringParsingException` during tool schema generation | Non-tool methods use a `_` prefix |
| 2026-10-01 | In server mode, the multi-turn context limit check is based on `max_position_embeddings` from the model configuration (131k for Gemma 4 E4B) and does not know the vLLM server's `--max-model-len`. vLLM rejects requests longer than the server limit with 400, which terminates the entire training run | `training/run.sh` runs with `--max-model-len 32768` (fits multi-turn prompts + 8,192 output tokens) |
| 2026-09-30 | Launching the vLLM server with `--gpu-memory-utilization 0.85` causes OOM at the first weight sync (it allocates a new buffer to receive Gemma 4 E4B's per-layer embedding tensors). The end of the log shows only "start_weight_update must be called before update_weights" instead of the cause | `--gpu-memory-utilization 0.6`. Check the first ERROR in the log |
| 2026-10-01 | `completions/clipped_ratio` reads higher than actual on Gemma 4. vLLM stops at the end tokens in `generation_config.json` (`<eos>`, `<turn\|>`, `<\|tool_response>`), but TRL counts a completion as properly terminated only when the last token is the tokenizer's `eos_token_id` or pad | With `mask_truncated_completions=False` (the default), training is not affected. This metric is not used in the comparison |
| 2026-10-01 | During training, the warning `CUDACachingAllocator ... expandable_segments: memory mapping failed with OOM` repeats, but training continues | Non-fatal warning (Gemma 4's 262k-vocabulary logits are large on A100 40GB). Common to both sandboxes |
| 2026-09-30 | The official vLLM image (`vllm/vllm-openai`) has no `python` command, only `python3` | Scripts use `python3` |
| 2026-09-30 | TRL PR #6948 proposes removing `trl.experimental.harbor` | Pinned `trl==1.14.1` |

### 2.3 AgentCore Runtime

| Check date | Difference | Handling |
|---|---|---|
| 2026-09-30 | `InvokeAgentRuntimeCommand` passes an open pipe that never sends EOF as stdin. Commands that read stdin (`cat`, `python3` with no arguments) hang until the timeout. The policy model actually generates such commands. Docker (`exec` without `-i`) and E2B do not provide stdin. Undocumented behavior | `exec </dev/null;` is prepended to every command to match Docker/E2B semantics |
| 2026-09-30 | The command request has only `command` and `timeout`, with no cwd or env fields. Unless the command is wrapped in a shell, pipes and `$VAR` are not interpreted | Every command is wrapped in `/bin/bash -c`, with `cd` and `export` included in the command string |
| 2026-09-30 | V2 starts from a snapshot, so the random seed, uuid, time, hostname, and PID state at initialization are replicated into every session | Do not create seed-dependent state during image initialization. Be careful when writing RL tasks |
| 2026-09-30 | The reference implementation's shim reports HealthyBusy on `stop(delete=False)` or abnormal client termination, so a session can be billed for up to 8 hours | This repository's shim never reports HealthyBusy, and `stop()` always calls `StopRuntimeSession` |
| 2026-10-01 | The "25 TPS" limit in the execute-command documentation does not apply to `InvokeAgentRuntimeCommand`. Commands follow the data plane quota (1,000 TPS); 25 TPS is the session creation quota, consistent with the quotas page. Under high concurrency the session creation quota shows up as increased session start latency rather than throttling errors | Measured values in `05-comparison.md` |
| 2026-10-01 | Runtime invocation metrics can be queried only when all 4 dimensions are specified: `Resource` (runtime ARN), `Operation`, `ComputeType=MicroVM`, `Name=<runtime>::DEFAULT`. `CPUUsed-vCPUHours` and `MemoryUsed-GBHours` use `Resource`, `Service=AgentCore.Runtime`, `Name`. `StopRuntimeSession` metrics use the session ID as `Resource`, so a separate series is created per session | `bench/agentcore_metrics.py` |
| 2026-09-30 | Right after snapshot restore, the first command in a session that imports a heavy package (pandas, etc.) is much slower than later commands (presumably the cost of the first file reads after restore) | Both sandboxes run the shared read-only warm-up `tasks/image/warmup.sh` before the snapshot, as the V2 optimization guide recommends (AgentCore: in the shim before listening on 8080; E2B: as the template start command) |
| 2026-10-07 | With the warm-up in the snapshot, the first import of the task libraries in a fresh AgentCore session still has a long tail: most of 30 sessions take 1.7 to 2.7 s, but some take up to about 57 s (p95 46.6 s); the second import in the same session is p95 1.6 s. E2B with the same warm-up takes 0.84 to 0.93 s (one outlier at 3.2 s) | Cause not determined. Reported in `05-comparison.md` section 2; account for it in tool timeouts |
| 2026-10-07 | Without a data-plane interface endpoint, the trainer Pods reach `InvokeAgentRuntime`/`InvokeAgentRuntimeCommand`/`StopRuntimeSession` through the public Regional endpoint, while E2B is reached through VPC peering and an internal ALB | `network.sh` adds an interface endpoint for `com.amazonaws.<region>.bedrock-agentcore` with private DNS and the own-account endpoint policy, so both sandboxes are reached over private paths |
| 2026-10-01 | File transfers through the shim become disproportionately slow from a few MB upward | Routing large files through S3 is recommended. In training, only verifier results (a few KB) are transferred |
| 2026-09-30 | On the arm64 image, `import numpy` works without `OPENBLAS_CORETYPE` (numpy 2.5.3). The SIGILL reported by harbor-on-agentcore does not reproduce on this image | No extra configuration |
| 2026-10-06 | In VPC mode (no internet), if the session security group's egress is restricted to the endpoints only, HTTPS to the S3 managed prefix list must also be allowed (ECR image layers come through the S3 gateway endpoint). Without it, runtime updates fail with `UPDATE_FAILED` ("internal error") and no cause is shown | `network.sh` adds egress 443 to the S3 prefix list on the session security group |
| 2026-10-06 | Private DNS for interface endpoints applies to the whole VPC, so ECR and CloudWatch Logs calls from HyperPod nodes and pods in the same VPC also go through these endpoints | The endpoint security group allows HTTPS from the session security group and the entire VPC CIDR |
| 2026-10-06 | Network settings are per runtime, not per session. Even after the runtime is deleted, VPC mode ENIs remain for up to 8 hours and block deletion of the subnets and security groups [documented] | During cleanup, delete the runtime first and wait for the ENIs to be released (`06-cleanup.md` section 3) |
| 2026-10-06 | CloudTrail event history (`lookup-events`) records control plane calls (`CreateAgentRuntime`, `UpdateAgentRuntime`) by default, but not data plane calls (`InvokeAgentRuntime`, `InvokeAgentRuntimeCommand`, `StopRuntimeSession`) | If per-command auditing is needed, configure CloudTrail data events (trail, advanced event selectors) separately. Data event support was not verified in this guide |
| 2026-10-07 | In AgentCore isolated VPC mode, an S3 gateway endpoint without a policy lets session code reach any S3 bucket that credentials allow, and the VPC resolver still answers public DNS names from the isolated subnets. With the endpoint policy restricted to `s3:GetObject` on the ECR layer bucket, reading an object from another bucket inside a session fails with HTTP 403, while image pulls and the oracle (56/56) still work | `network.sh` gives the isolated route table its own S3 gateway endpoint with that policy and restricts the ECR and Logs interface endpoints to this account's principals. DNS tunneling remains possible; Route 53 Resolver DNS Firewall (VPC-wide, needs an allow list) closes it and is not configured in this guide |
| 2026-09-30 | Code running inside a session can read the credentials of the runtime execution role | The execution role is limited to ECR pull for this runtime's image and runtime logs |

### 2.4 E2B (self-hosted sample, SDK, Harbor E2B environment)

| Check date | Difference | Handling |
|---|---|---|
| 2026-10-01 | E2B Python SDK 2.51.0 uses `POST /v2/sandboxes` to create sandboxes, but the API of the self-hosted sample (830b516, e2b-dev/infra 225f963) provides only `GET` on `/v2/sandboxes`. Every creation fails with `404: validation error: method not allowed`. Up to 2.50.0, `POST /sandboxes` is used (confirmed in the wheel source). The template build API is not affected | Pin `e2b==2.50.0` in the Trainer image. With self-hosted E2B, the SDK version must be pinned to match the server version |
| 2026-10-01 | Harbor's E2B environment creates sandboxes with a 24-hour timeout, but the default team tier `base_v1` created by the self-hosted sample has `max_length_hours=1` and `concurrent_instances=20` (the same values as E2B Cloud Hobby). Every creation fails with `400: Timeout cannot be greater than 1 hours`, and the limit of 20 concurrent also blocks high-concurrency benchmarks | `finalize.sh` changes `base_v1` in the DB's `tiers` to 24 hours / 1,000 (24 hours is the documented E2B Cloud Pro value; 1,000 is large enough that node capacity becomes the real limit) |
| 2026-10-01 | The sample's (830b516) unattended deployment chain fails at the `init-db` step: the cloud-init path has no `HOME`, and `deploy-all.sh` passes `HOME=/root` only to some steps (Go: `GOCACHE is not defined ...`) | `deploy.sh` runs the chain on the bastion with `HOME=/root` |
| 2026-10-01 | The `build` step of the same chain: the repository owner is `ubuntu` while the chain runs as root, so git refuses with `dubious ownership`, and the commit hash in the image tag becomes empty (`e2b-core/client-proxy:` invalid reference) | `deploy.sh` sets `git config --global --add safe.directory` first |
| 2026-10-01 | The sample's `PublicAccess` parameter changes only the ALB scheme (internet-facing/internal), and the ALB security group allows 80 and 443 from 0.0.0.0/0 in both modes. Sandbox subdomains (`<port>-<sandbox_id>.<E2B_DOMAIN>`) respond without authentication to anyone who can reach the ALB | Deploy with `PublicAccess=Private`, and `peer.sh` restricts the ALB security group to 443 from the two VPC CIDRs. The public DNS records resolve only to private IPs |
| 2026-10-01 | The sample's default client node type is x86 `c5.metal` (when `ClientInstanceType` is empty) | `deploy.sh` specifies `c8i.metal-48xl` explicitly |
| 2026-10-01 | The sample deployment log (`/tmp/e2b.log`) prints the team API key in plain text | `finalize.sh` moves the key to Secrets Manager and masks it in the log; the configuration file is root-only (600) |
| 2026-10-06 | The regional NAT gateway route table in the E2B VPC rejects peering routes | `peer.sh` skips the gateway route table and adds the route to all other route tables |
| 2026-10-06 | The sample's `infra-iac/destroy.sh` deletes the Terraform resources but keeps the orchestrator AMI for redeployment. The Terraform state is in the E2B bucket, so emptying the bucket first orphans the Terraform resources. Secrets created by Terraform have a default 30-day recovery window, so the script deletes them immediately. The sample README notes that the ALB may need to be deleted from the console | The order in `06-cleanup.md` section 2 (destroy.sh, AMI, buckets, stack) |
| 2026-09-30 | E2B documents disagree on the default sandbox memory (pricing page 4 GiB, billing documentation 512 MiB, build example 2,048 MB) | 2 vCPU / 4 GiB is set explicitly in the template |

### 2.5 Network blocking and other

| Check date | Difference | Handling |
|---|---|---|
| 2026-10-06 | With every task set to `network_mode = "no-network"`, `curl https://example.com` from the sandbox fails on both sandboxes, but the failure mode differs: DNS resolution failure on E2B, connection timeout on AgentCore (isolated VPC mode). Task data (`/home/user/input`) is readable on both | The error messages the policy model sees can differ. Keep this in mind when interpreting the comparison |
| 2026-09-30 | The original dataset image (`savatar101/env-data-agent-train:base`) is amd64 only and downloads Kaggle data from the internet at task start (up to 1.9 GB). No oracle solutions | Use a multi-architecture derived subset (56 tasks) with the data baked into the image |
| 2026-09-30 | Uploading to a newly created S3 bucket with a boto3 S3 client that has no Region specified fails with `TemporaryRedirect` | Specify `region_name` explicitly |

## 3. Verification of prior assumptions

Status: confirmed, refuted, changed, inconsistent. All check dates are 2026-09-30 unless otherwise noted.

### 3.1 Harbor and TRL

| Assumption | Status | Findings | Source |
|---|---|---|---|
| `trl.experimental.harbor.HarborSpec(dataset, agent="bash", environment_type="e2b", num_tasks=...)` is provided | Confirmed | Signature: `HarborSpec(dataset, *, agent="bash", environment_type="docker", num_tasks=None, indices=None, include_metadata=True)`. Included in releases since TRL v1.8.0; latest on PyPI is 1.14.1 | [_spec.py@4c623f3d](https://github.com/huggingface/trl/blob/4c623f3d154548209963842c6717e99f51b5a5b2/trl/experimental/harbor/_spec.py), [PyPI](https://pypi.org/pypi/trl/json) |
| Installation: `trl[harbor]`, `harbor[e2b]`, `vllm>=0.22.0`, `transformers>=5.2.0` | Confirmed (partially) | Stated in the documentation. Only the transformers version is enforced by code. `trl[harbor]` requires `harbor>=0.13.0` and Python 3.12 or later. Latest Harbor is 0.23.0 | [TRL Harbor documentation](https://huggingface.co/docs/trl/main/en/harbor) |
| Experimental feature that supports only external agents | Confirmed | | Same as above |
| Sandbox provisioning within a generation batch is sequential | Confirmed | `GRPOTrainer._generate_and_score_completions` calls `environment.reset()` in a plain for loop. Bash tool calls and the verifier are also sequential within a process. Parallelism equals the number of accelerate processes | [grpo_trainer.py@4c623f3d](https://github.com/huggingface/trl/blob/4c623f3d154548209963842c6717e99f51b5a5b2/trl/trainer/grpo_trainer.py), [_env.py](https://github.com/huggingface/trl/blob/4c623f3d154548209963842c6717e99f51b5a5b2/trl/experimental/harbor/_env.py) |
| List of `BaseEnvironment` abstract methods | Confirmed | `type()`, `_validate_definition()`, `start(force_build)`, `stop(delete)`, `upload_file`, `upload_dir`, `download_file`, `download_dir`, `exec(command, cwd, env, timeout_sec, user) -> ExecResult`. `capabilities` and `preflight` are optional overrides | [base.py@9b168361](https://github.com/harbor-framework/harbor/blob/9b168361ebe973113640b9183b03cbd7884d720e/src/harbor/environments/base.py) |
| The Harbor CLI selects a custom environment with `-e module:Class` | Confirmed | `EnvironmentFactory` loads the class with `config.import_path` | [factory.py@9b168361](https://github.com/harbor-framework/harbor/blob/9b168361ebe973113640b9183b03cbd7884d720e/src/harbor/environments/factory.py) |
| `HarborSpec(environment_type=...)` accepts an import path | Refuted | It is passed only to `TrialEnvironmentConfig(type=...)` and fails `EnvironmentType` enum validation. `agent=` accepts `"pkg.mod:Class"`, so a harness subclass is passed through this path and uses `import_path` inside it (section 2.2) | [_env.py](https://github.com/huggingface/trl/blob/4c623f3d154548209963842c6717e99f51b5a5b2/trl/experimental/harbor/_env.py) |
| No official Harbor AgentCore provider (issue #3446) | Confirmed | The issue is open. No provider PR (only adapter PRs #3448 and #3449 exist) | [#3446](https://github.com/harbor-framework/harbor/issues/3446) |
| Reuse code from `mightma/harbor-on-agentcore` | Changed | This repository has no LICENSE, so its code cannot be copied. This guide's AgentCore environment and shim are taken, with attribution, from the Apache-2.0 `mightma/harbor@acr-kit-v1` (commit 4ee0cb25) and `awslabs/agentcore-rl-toolkit` | [harbor-on-agentcore](https://github.com/mightma/harbor-on-agentcore), [fork](https://github.com/mightma/harbor/tree/acr-kit-v1) |

### 3.2 AgentCore Runtime

| Assumption | Status | Findings | Source |
|---|---|---|---|
| Commands run with `InvokeAgentRuntimeCommand`, streaming stdout/stderr/exitCode | Confirmed | Events: `contentStart`, `contentDelta{stdout,stderr}`, `contentStop{exitCode,status}` | [API reference](https://docs.aws.amazon.com/bedrock-agentcore/latest/APIReference/API_InvokeAgentRuntimeCommand.html) |
| Command timeout 1 to 3,600 seconds, command size up to 64 KB | Confirmed | `command` 1 to 65,536 characters, `timeout` default 300 seconds | Same as above |
| No shell state between commands | Confirmed (with addition) | Shell state is not retained, but files and background processes persist within the session | [runtime-execute-command](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-execute-command.html) |
| cwd and env can be specified for commands | Refuted | The request body has only `command` and `timeout`. `cd` and `export` must be included in the command string | API reference |
| Quotas (5,000 active sessions, 1,000 TPS data plane, 25 TPS session creation, fixed 2 vCPU/8 GB, 2 GB image, up to 8 hours, 15 min idle, 1,000 runtimes) | Confirmed | Default values. Check the values applied to your account in Service Quotas. Quota codes: L-3E5722B2 (sessions), L-8EE2AEA2 (session creation), L-46ED137C (data plane), L-F4575653 (number of runtimes), L-0A9E32B3 (image) | [Quotas](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html) |
| The "25 TPS" in the execute-command documentation applies to command invocations | Refuted (2026-10-01) | Original text: "ThrottlingException: Occurs when you exceed the request rate limit of 25 TPS." Command invocations follow the 1,000 TPS data plane quota, and 25 TPS is the session creation quota (section 2.3, measurements in `05-comparison.md`) | [runtime-execute-command](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-execute-command.html), [Quotas](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html) |
| Only arm64 images are supported | Confirmed | x86 in microVM mode is "coming soon". x86/GPU only with Runtime Instances (EC2 pricing + 12% management fee, 7.8% for G series) | [V2 blog](https://aws.amazon.com/blogs/machine-learning/the-new-agentcore-runtime-elastic-optimized-and-consistently-fast-starts/), [Runtime Instances](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-instances-how-it-works.html) |
| Service contract (`/ping`, `/invocations`, port 8080) required | Confirmed | No exception for command-only use. In V2, creation fails if `/ping` is not healthy within 120 seconds. A minimal shim is required | [HTTP protocol contract](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-http-protocol-contract.html) |
| `platformVersion: V2` (GA 2026-09) | Confirmed | GA on 2026-09-18, available in us-west-2. Default is V1. Requires boto3 1.43.95 or later or AWS CLI 2.36.46 or later. Snapshot-based startup | [What's New](https://aws.amazon.com/about-aws/whats-new/2026/09/new-agentcore-runtime-generally-available/), [platform versions](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-how-it-works.html#runtime-platform-versions) |
| V2 pricing: $0.1276 per vCPU-hour, $0.0169 per GB-hour, per-second billing, no CPU charge during I/O wait | Confirmed | Minimum 1 second, minimum 128 MB memory. V1 is $0.0895 / $0.00945. Billed until the session ends | [Pricing](https://aws.amazon.com/bedrock/agentcore/pricing/) |
| Default network is PUBLIC, VPC mode is per runtime | Confirmed | VPC mode subnets in usw2-az1/2/3. A VPC without internet requires ecr.dkr, ecr.api, S3 gateway, and logs endpoints | [VPC](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-vpc.html) |
| Callers in a VPC can reach the Runtime data plane privately | Confirmed (2026-10-07) | Interface endpoint `com.amazonaws.<region>.bedrock-agentcore` (PrivateLink), Runtime data plane supported | [VPC interface endpoints](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/vpc-interface-endpoints.html) |

### 3.3 E2B

| Assumption | Status | Findings | Source |
|---|---|---|---|
| $0.000014/vCPU-second, $0.0000045/GiB-second | Confirmed | | [Pricing](https://e2b.dev/pricing) |
| Default 2 vCPU / 4 GiB | Inconsistent | Pricing page says 4 GiB, billing documentation says 512 MiB, build example says 2,048 MB. Must be specified explicitly when building templates | [Pricing](https://e2b.dev/pricing), [Billing](https://docs.e2b.dev/billing.md) |
| Concurrency Hobby 20, Pro 100 (1,100 with add-ons) | Confirmed | +500 per add-on, $500 per month. Session creation rate Hobby 1/second, Pro 5/second | [Increase concurrency](https://docs.e2b.dev/faq/increase-concurrency.md) |
| Maximum session Hobby 1 hour, Pro 24 hours | Confirmed | Based on continuous runtime; resets on pause/resume | [Sandbox lifetime](https://docs.e2b.dev/faq/sandbox-lifetime.md) |
| Self-hosted: switch with `E2B_DOMAIN` and `E2B_API_KEY` | Confirmed | `aws-samples/sample-e2b-on-aws` (CloudFormation + Terraform + Nomad) | [sample-e2b-on-aws](https://github.com/aws-samples/sample-e2b-on-aws) |

### 3.4 Model and task dataset

| Assumption | Status | Findings | Source |
|---|---|---|---|
| Gemma 4 (E2B, E4B, 12B, 26B A4B, 31B), Apache 2.0, native function calling | Confirmed | `google/gemma-4-E4B-it` is not gated. Actual parameters 8.0B (text decoder 4.0B + per-layer embedding 2.8B + audio/vision) | [config.json](https://huggingface.co/google/gemma-4-E4B-it/blob/main/config.json) |
| Trainable with TRL GRPO + vLLM | Confirmed | Tool call parsing confirmed with TRL 1.14.1 + transformers 5.17. vLLM supports Gemma 4 and the `gemma4` tool parser since 0.19.0. TRITON_ATTN is used due to mixed head sizes (vLLM #38887) | [vLLM Gemma4 recipe](https://docs.vllm.ai/projects/recipes/en/stable/Google/Gemma4.html), [vLLM #38887](https://github.com/vllm-project/vllm/issues/38887) |
| Use `AdithyaSK/data_agent_rl_environment_train` as is on arm64 | Changed | 2,238 tasks and a single image (`savatar101/env-data-agent-train:base`), but amd64 only. Downloads Kaggle data from HF at start (internet required, up to 1.9 GB). No oracle solutions. This guide restores the recipe, rebuilds it for multiple architectures, and uses a derived subset with the data baked into the image (56 tasks, 40 training / 16 evaluation, each from a different Kaggle dataset) | [dataset](https://huggingface.co/datasets/AdithyaSK/data_agent_rl_environment_train), [Docker Hub tags](https://hub.docker.com/v2/repositories/savatar101/env-data-agent-train/tags) |
