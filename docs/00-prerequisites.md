[한국어](ko/00-prerequisites.md)

# 00. Prerequisites

This guide runs TRL GRPO + Harbor training on SageMaker HyperPod (EKS orchestration) and compares two rollout sandboxes connected to it: E2B sandbox (Method A) and Amazon Bedrock AgentCore Runtime (Method B). This document covers what to prepare before you start: region, quotas, local tools, credentials, domain, and estimated cost.

> Terminology note: "E2B" in the Gemma 4 model lineup (effective 2B, for example `google/gemma-4-E2B-it`) has nothing to do with the E2B sandbox. This guide always refers to the model by its full Hugging Face ID (`google/gemma-4-E4B-it`) and to the sandbox as "E2B sandbox".

Overall flow:

| Step | Document |
|---|---|
| Prerequisites | 00 (this document) |
| HyperPod EKS cluster and Pod permissions | [`01-hyperpod-eks.md`](01-hyperpod-eks.md) |
| Task suite and multi-architecture images | [`02-tasks-and-images.md`](02-tasks-and-images.md) |
| Method A: self-hosted E2B | [`03a-sandbox-e2b.md`](03a-sandbox-e2b.md) |
| Method B: AgentCore Runtime | [`03b-sandbox-agentcore.md`](03b-sandbox-agentcore.md) |
| GRPO training | [`04-grpo-training.md`](04-grpo-training.md) |
| Measured results and comparison | [`05-comparison.md`](05-comparison.md) |
| Cleanup | [`06-cleanup.md`](06-cleanup.md) |

## 1. Region

All resources are created in `us-west-2` (Oregon). Because `AWS_REGION` may not be set in your shell, every AWS CLI command in this guide includes `--region us-west-2`.

| Requirement | us-west-2 |
|---|---|
| HyperPod `ml.p4d.24xlarge` | Available |
| AgentCore Runtime (`platformVersion` V2, VPC mode) | Available. VPC mode can only use subnets in supported AZ IDs (`usw2-az1`, `usw2-az2`, `usw2-az3`) [documented] |
| AgentCore default active session quota | 5,000 (2,500 in regions other than us-east-1 and us-west-2) [documented] |
| Self-hosted E2B client node `c8i.metal-48xl` | Available |

Tag every resource with `Project=harbor-rl-sandbox`. The scripts in this repository add the tag automatically, and the cleanup step uses it to find remaining resources ([`06-cleanup.md`](06-cleanup.md)).

## 2. Service quotas

Request increases for any insufficient quotas in the Service Quotas console. Approval can take time, so check these first.

```bash
# HyperPod p4d instance quota (needs at least 1)
aws service-quotas list-service-quotas --service-code sagemaker --region us-west-2 \
  --query "Quotas[?contains(QuotaName, 'ml.p4d.24xlarge for cluster usage')].[QuotaName,Value]" --output table

# AgentCore Runtime quotas
aws service-quotas list-service-quotas --service-code bedrock-agentcore --region us-west-2 \
  --query "Quotas[].[QuotaName,QuotaCode,Value,Adjustable]" --output table

# EC2 On-Demand Standard vCPU quota (self-hosted E2B only)
aws service-quotas get-service-quota --service-code ec2 --quota-code L-1216C47A --region us-west-2 \
  --query 'Quota.Value'
```

| Quota | Required | Default | Adjustable |
|---|---|---|---|
| SageMaker `ml.p4d.24xlarge for cluster usage` | 1 | Varies by account (may be 0) | Yes |
| EC2 Running On-Demand Standard (A, C, D, H, I, M, R, T, Z) instances (`L-1216C47A`) | About 230 vCPUs (only when using self-hosted E2B) | Varies by account | Yes |
| VPC, Elastic IP | At least 1 of each available (2 of each if you also use self-hosted E2B) | 5 / 5 | Yes |
| AgentCore active sessions (`L-3E5722B2`) | 128 or more (maximum of the concurrency sweep) | 5,000 [documented] | Yes |
| AgentCore new session creation rate (`L-8EE2AEA2`) | | 25 TPS [documented] | Yes |
| AgentCore data plane API (`L-46ED137C`) | | 1,000 TPS [documented] | Yes |
| AgentCore resources per session | | 2 vCPU / 8 GB [documented] | No |
| AgentCore container image size (`L-0A9E32B3`) | | 2 GB [documented] | No |
| AgentCore maximum session lifetime / idle timeout | | 8 hours / 15 minutes [documented] | Yes |

- vCPU breakdown for self-hosted E2B: client `c8i.metal-48xl` 192 + build node `m8i.4xlarge` 16 + five `t3.xlarge` (3 Nomad servers, 2 API) 20 + bastion `c7i.xlarge` 4 = 232. E2B uses Firecracker microVMs, so the client node must be bare metal.
- p4d On-Demand capacity is not guaranteed. If the GPU node takes a long time to come up, see section 4 of [`01-hyperpod-eks.md`](01-hyperpod-eks.md). If available in your account, you can also reserve capacity with a HyperPod flexible training plan (this may require account-level allowlisting).
- How AgentCore quotas show up in actual behavior is covered in section 7 of [`03b-sandbox-agentcore.md`](03b-sandbox-agentcore.md) and in [`05-comparison.md`](05-comparison.md).

## 3. Local tools

| Tool | Verified version | Purpose | Install (macOS) |
|---|---|---|---|
| AWS CLI v2 | 2.37.6 (2.36.46 or later required) | All AWS operations, AgentCore `--platform-version` | `brew install awscli` |
| kubectl | 1.34 | EKS operations | `brew install kubectl` |
| Finch | 1.17.0 | Container build and push | `brew install --cask finch` |
| Python 3 + uv | Python 3.14, uv 0.8 | Local scripts (task generation, benchmark analysis, command serialization in `submit.sh`) | `brew install uv` |
| jq | 1.7 | JSON processing | `brew install jq` |
| envsubst (gettext) | 1.0 | Rendering IAM policies and Job manifests (`setup-access.sh`, `submit.sh`) | `brew install gettext` |
| helm | 3.19 (optional) | Checking charts during cleanup | `brew install helm` |

- Dependencies of local Python scripts are given with `uv run --with`. Task generation (`tasks/select_tasks.py`, `tasks/build_suite.py`) needs `pandas`, `pyarrow`, `huggingface_hub>=1.33` and `tomli-w`; analysis (`bench/analyze.py`, `bench/cost_model.py`) needs `pandas` and `matplotlib` ([`02-tasks-and-images.md`](02-tasks-and-images.md), [`04-grpo-training.md`](04-grpo-training.md)).
- You do not need eksctl or the HyperPod CLI (`hyp`). The cluster is created with the official CloudFormation template ([`01-hyperpod-eks.md`](01-hyperpod-eks.md)).
- With an AWS CLI older than 2.36.46, the `--platform-version` option is not recognized when creating an AgentCore runtime.
- Container work uses Finch by default, with the Docker equivalent shown next to each command. If you use Docker, replace `finch` with `docker`, and use `docker buildx build --platform ... --push` for multi-architecture builds.
- The large amd64 Trainer image is built in CodeBuild, so local Finch is used mainly for the task image and the AgentCore image ([`02-tasks-and-images.md`](02-tasks-and-images.md), section 3 of [`04-grpo-training.md`](04-grpo-training.md)).

```bash
# Start the Finch VM (macOS)
finch vm init    # first time only
finch vm start

# Docker equivalent: start Docker Desktop or the Docker daemon
```

## 4. Credentials (environment variables)

Pass all credentials only through environment variables. Do not store their values in files, scripts, kubeconfig, container images, logs, or git. The values below are placeholders.

```bash
export AWS_REGION=us-west-2
export AWS_ACCESS_KEY_ID=<your-access-key-id>
export AWS_SECRET_ACCESS_KEY=<your-secret-access-key>
export AWS_SESSION_TOKEN=<your-session-token>    # temporary credentials (recommended)
export HF_TOKEN=<your-hugging-face-token>
export E2B_API_KEY=<your-e2b-api-key>            # E2B Cloud only (not needed for self-hosted E2B)

aws sts get-caller-identity --region us-west-2
```

| Variable | When needed | How it reaches the cluster |
|---|---|---|
| `AWS_*` | Always (local CLI and scripts) | Not passed. Pods get IAM role permissions through EKS Pod Identity |
| `HF_TOKEN` | Recommended | `infra/k8s/setup-access.sh` stores it in the Kubernetes Secret `sandbox-secrets` |
| `E2B_API_KEY` | Only when using E2B Cloud | `infra/k8s/setup-access.sh` stores it in the same Secret |

- **`HF_TOKEN`:** Used to download the policy model `google/gemma-4-E4B-it` and datasets from the Hugging Face Hub. The model is not gated, so you can download it without a token, but anonymous downloads easily hit rate limits, so a read-only (read) token is recommended. Create one at https://huggingface.co/settings/tokens.
- **API key for self-hosted E2B:** Not handled as a local environment variable. The final deployment step (`finalize.sh`) creates a team API key and stores it in AWS Secrets Manager (`harbor-rl-e2b/team-api-key`), and `infra/e2b-selfhosted/set-secret.sh` reads it and moves it into a Kubernetes Secret without printing it (section 3.5 of [`03a-sandbox-e2b.md`](03a-sandbox-e2b.md)).
- Do not create IAM users or long-lived access keys. Use temporary credentials obtained from IAM Identity Center or a similar source.
- Required IAM permissions: CloudFormation, IAM role and policy creation, EC2/VPC, EKS, SageMaker, S3, ECR, CodeBuild, CloudWatch Logs, Secrets Manager, SSM, Route 53, ACM, Bedrock AgentCore (control plane, data plane), Service Quotas. This guide was verified with an administrator role.

## 5. Domain (self-hosted E2B only)

Self-hosted E2B (`aws-samples/sample-e2b-on-aws`) distinguishes the API and each sandbox by host names such as `api.e2b.<domain>` and `<port>-<sandbox id>.e2b.<domain>`. You therefore need the following:

- A domain you own and a **public Route 53 hosted zone** for it. This guide uses a subdomain such as `E2B_DOMAIN=e2b.example.com`.
- The deployment script creates the DNS validation records for a wildcard ACM certificate, a `*.e2b.<domain>` CNAME record, and anti-spoofing mail records (null MX, SPF `-all`, DMARC `reject`) in this hosted zone.

If you use a company domain, check your domain policy first. Many organizations prohibit unauthenticated public endpoints under the company domain. E2B sandbox hosts are open without authentication to anyone who can reach the ALB, so this guide uses an **internal ALB** (`PublicAccess=Private`) connected to the HyperPod VPC through VPC peering. Public DNS exposes only private IPs, and the ALB security group allows only HTTPS 443 from the two VPCs. See sections 1 to 3 of [`03a-sandbox-e2b.md`](03a-sandbox-e2b.md) for the full configuration.

With E2B Cloud, you do not need a domain, EC2 quotas, or a deployment: you need only an E2B account and API key (https://e2b.dev). However, task data and command output leave your account, and this guide did not take measurements on E2B Cloud. Plan limits are Hobby: 20 concurrent / maximum 1 hour per session, and Pro: 100 concurrent / 24 hours [documented]. Harbor's E2B environment creates sandboxes with a 24-hour timeout and the concurrency sweep goes up to 128, so reproducing with E2B Cloud requires Pro or higher (section 6 of [`03a-sandbox-e2b.md`](03a-sandbox-e2b.md)).

## 6. Estimated cost

All unit prices are us-west-2 On-Demand list prices [documented], and the reproduction costs are [estimated] values based on the assumptions below. Costs calculated from usage measured in the actual runs are in section 4 of [`05-comparison.md`](05-comparison.md).

### 6.1 Unit prices [documented]

| Item | Unit price |
|---|---|
| HyperPod `ml.p4d.24xlarge` | $25.91/hour |
| EKS control plane | $0.10/hour ($0.60/hour for versions past standard support) |
| NAT gateway | $0.045/hour + $0.045/GB data processed |
| Public IPv4 address | $0.005/hour |
| VPC interface endpoints (`ecr.api`, `ecr.dkr`, `logs` and the data-plane `bedrock-agentcore` for AgentCore) | $0.01/hour (per endpoint x AZ) + $0.01/GB data processed |
| AgentCore Runtime | vCPU $0.1276/hour, memory $0.0169/GB-hour. Billed per second, no CPU charge while waiting on I/O |
| E2B Cloud | vCPU $0.000014/second ($0.0504/hour), memory $0.0000045/GiB-second ($0.0162/GiB-hour). Billed on allocation while running |
| E2B Cloud Pro plan | $150/month |

### 6.2 Self-hosted E2B fixed cost [estimated]

Self-hosted E2B costs money for as long as it is running, regardless of the number of sandboxes. The value is the sum of the [documented] hourly price of each component (`SELF_HOSTED` in `bench/cost_model.py`).

| Component | Per hour |
|---|---|
| Client `c8i.metal-48xl` x1 | $8.996 |
| Nomad server `t3.xlarge` x3 + API `t3.xlarge` x2 | 5 x $0.1664 = $0.832 |
| Build node `m8i.4xlarge` x1 | $0.847 |
| Bastion `c7i.xlarge` x1 | $0.179 |
| NAT gateway, ALB hourly charges | $0.045 + $0.0225 |
| Aurora Serverless v2 (minimum 0.5 ACU), ElastiCache Serverless Redis (minimum 1 GB) | 0.5 x $0.12 + $0.125 |
| **Total** | **About $11.11/hour (about $267/day)** |

### 6.3 Estimated cost for one reproduction [estimated]

Assumptions:
- HyperPod cluster running for 12 hours: creation, image preparation and validation, benchmarks, two GRPO training runs (one per sandbox, including pre- and post-training evaluation).
- Sandbox sessions: 2,112 per training run (40 steps x 48 rollouts per step = 1,920, plus pre- and post-training evaluation 2 x 16 tasks x 6 = 192). Adding benchmarks and oracle validation gives about 3,000 sessions per method.
- Average session lifetime 3 minutes (0.05 hours), sandbox size AgentCore 2 vCPU / 8 GB (fixed), E2B 2 vCPU / 4 GiB.
- Self-hosted E2B running for 12 hours from deployment to cleanup.

| Item | Formula | Estimated amount |
|---|---|---|
| HyperPod p4d | 12 hours x $25.91 | About $311 |
| EKS + NAT + public IPv4 | 12 hours x ($0.10 + $0.045 + $0.005) | About $2 |
| Interface endpoints for AgentCore | 4 x 2 AZs x $0.01 x 12 hours | About $1 |
| AgentCore Runtime (upper bound: assumes 100% CPU usage) | 3,000 x 0.05 hours x (2 x $0.1276 + 8 x $0.0169) | About $59 |
| ECR, S3, CodeBuild, CloudWatch Logs | Small | Under $5 |
| **Common + AgentCore subtotal** | | **About $378** |
| Method A with self-hosted E2B (this guide's approach) | 12 hours x $11.11 | About $133 |
| Method A with E2B Cloud (alternative) | 3,000 x 180 seconds x (2 x $0.000014 + 4 x $0.0000045) | About $25 (+ Pro $150/month) |
| **Total** | | **Self-hosted E2B: about $510. E2B Cloud: about $400 (about $550 including Pro)** |

- Most of the cost is the GPU instance. Section 4 of [`05-comparison.md`](05-comparison.md) recalculates, from measured values, how sandbox latency affects training time (and therefore GPU cost) and what share of the cost the sandbox accounts for.
- AgentCore does not charge for CPU while the CPU is waiting on I/O, so the AgentCore amount above is an upper bound. Self-hosted E2B, in contrast, is a fixed cost independent of utilization.
- If you leave the cluster running after you finish, the GPU alone costs about $622 per day (24 x $25.91), and about $890 per day if self-hosted E2B is also left running. Clean up immediately when you are done by following [`06-cleanup.md`](06-cleanup.md).

## Next steps

Create the HyperPod EKS cluster in [`01-hyperpod-eks.md`](01-hyperpod-eks.md). While cluster creation and GPU provisioning are in progress, you can build the task image in [`02-tasks-and-images.md`](02-tasks-and-images.md) and deploy self-hosted E2B in [`03a-sandbox-e2b.md`](03a-sandbox-e2b.md) (1 to 1.5 hours) in parallel. The self-hosted E2B `deploy.sh` needs the results bucket, which `training/build-image.sh` creates (section 3.1 of [`04-grpo-training.md`](04-grpo-training.md)), so run `build-image.sh` first.
