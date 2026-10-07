[한국어](ko/01-hyperpod-eks.md)

# 01. Create the HyperPod EKS cluster

In this step, you create a SageMaker HyperPod cluster with EKS orchestration and one GPU training node (`ml.p4d.24xlarge`, A100 40GB x 8), and then prepare the permissions and Secret that let training Pods use the sandboxes and S3. Before you start, check the quotas and tools in [`00-prerequisites.md`](00-prerequisites.md).

Time required: tens of minutes for CloudFormation stack creation (the script assumes a 40 to 60 minute wait) + GPU node provisioning (an additional few minutes to tens of minutes depending on capacity)

## 1. Creation method

You can create a HyperPod EKS cluster with the SageMaker console, the HyperPod CLI (`hyp`), or the AWS CLI, and all of them use the same official CloudFormation template (`main-stack-eks-based-template.yaml`). This guide uses **AWS CLI + official template + `params.json`**, because every value changed from the template defaults is visible in a single file and no extra tools are needed.

Template location (published by the `aws/sagemaker-hyperpod-cluster-setup` repository to per-region buckets):

```
https://aws-sagemaker-hyperpod-cluster-setup-us-west-2-prod.s3.us-west-2.amazonaws.com/templates/main-stack-eks-based-template.yaml
```

> The main template fetches its nested templates from the same bucket at deployment time. To pin the template version completely, copy the `templates/` prefix to your own bucket and set the `CustomBucketName` parameter.

## 2. Parameters

[`infra/hyperpod/params.json`](../infra/hyperpod/params.json) overrides the template defaults as follows.

| Parameter | Value | Reason |
|---|---|---|
| `ResourceNamePrefix` / `ResourceNameShortPrefix` | `harbor-rl-hp` / `harborrl` | Name prefix for resources the template creates |
| `HyperPodClusterName` | `harbor-rl-hp` | Cluster name used in all later commands |
| `EKSClusterName` | `harbor-rl-hp-eks` | The actual EKS name is prefixed with `ResourceNamePrefix` (section 5) |
| `KubernetesVersion` | `1.35` | The template default 1.34 is closer to the end of standard support (after which the control plane price goes from $0.10 to $0.60/hour) |
| `AvailabilityZoneIds` | `usw2-az1,usw2-az2,usw2-az3` | The template default is us-east-2 AZs. Creating private subnets in 3 AZs makes it easier to add an instance group in another AZ when capacity is short |
| `InstanceGroupSettings1` | Group `gpu`: `ml.p4d.24xlarge` x1, `usw2-az2`, `ThreadsPerCore=1`, EBS 500 GB | GPU training node |
| `CreateFsxStack` | `false` | This experiment does not need a shared file system. The model cache and results use the node's NVMe instance store |
| `FsxAvailabilityZoneId` | `usw2-az2` | FSx is not created, but the template default (a us-east-2 AZ) is aligned to this region |
| `EnableHPInferenceFeature` | `false` | Training only |
| `NodeRecovery` | `Automatic` | HyperPod replaces nodes automatically on failure |
| `Tags` | `[{"Key":"Project","Value":"harbor-rl-sandbox"}]` | Tags on the HyperPod cluster itself (separate from the stack tags) |

What the template creates: a VPC (public subnets, NAT gateway, Elastic IP), private subnets in a secondary CIDR, security groups, an S3 gateway endpoint, an EKS cluster (add-ons vpc-cni, kube-proxy, coredns, **eks-pod-identity-agent**), an S3 bucket for lifecycle scripts, the HyperPod execution role, the HyperPod cluster, and HyperPod Helm charts installed through Lambda (NVIDIA device plugin, EFA device plugin, Kubeflow training operator, health monitoring agent, and others).

The HyperPod VPC CIDR (`10.192.0.0/16`) and the Pod CIDR are used later for the self-hosted E2B VPC peering (section 3.4 of [`03a-sandbox-e2b.md`](03a-sandbox-e2b.md)) and the AgentCore dedicated subnets ([`03b-sandbox-agentcore.md`](03b-sandbox-agentcore.md)).

## 3. Create

```bash
export AWS_REGION=us-west-2
./infra/hyperpod/create-cluster.sh
```

[`infra/hyperpod/create-cluster.sh`](../infra/hyperpod/create-cluster.sh) validates the template, creates the stack, and waits for `CREATE_COMPLETE`. The key part:

```bash
aws cloudformation create-stack \
  --stack-name harbor-rl-hp \
  --template-url "$TEMPLATE_URL" \
  --parameters file://infra/hyperpod/params.json \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM CAPABILITY_AUTO_EXPAND \
  --tags Key=Project,Value=harbor-rl-sandbox \
  --region us-west-2
```

- `CAPABILITY_AUTO_EXPAND`: The HyperPod documentation lists only `CAPABILITY_IAM` and `CAPABILITY_NAMED_IAM`, but the template uses `Transform: AWS::LanguageExtensions`, so the third one is also required.
- To change the stack name, set `STACK_NAME=...`. Creation takes a long time, so run it in a separate terminal or in the background and check progress in the console or with `aws cloudformation describe-stack-events --stack-name harbor-rl-hp --region us-west-2`.
- While you wait, you can build the task image in [`02-tasks-and-images.md`](02-tasks-and-images.md) and deploy self-hosted E2B in [`03a-sandbox-e2b.md`](03a-sandbox-e2b.md) in parallel. The self-hosted E2B `deploy.sh` uploads its template to the results bucket, which [`training/build-image.sh`](../training/build-image.sh) creates, so run `build-image.sh` first (section 3.1 of [`04-grpo-training.md`](04-grpo-training.md)).

## 4. Verify the GPU node (do not stop at stack completion)

Even when the stack is `CREATE_COMPLETE` and the cluster is `InService`, the GPU instance may not exist yet. With the template default `NodeProvisioningMode=Continuous`, if p4d capacity is short, HyperPod keeps retrying provisioning in the background, and the cluster status is reported as `InService` in the meantime.

```bash
aws sagemaker describe-cluster --cluster-name harbor-rl-hp --region us-west-2 \
  --query 'InstanceGroups[].[InstanceGroupName,CurrentCount,TargetCount]' --output table
aws sagemaker list-cluster-events --cluster-name harbor-rl-hp --region us-west-2 --max-results 10 \
  --query 'Events[].[EventTime,Description]' --output text
```

Proceed to the next step when `CurrentCount` for group `gpu` equals `TargetCount` (1). If it stays at 0:

- Check the events for insufficient capacity (`insufficient capacity`) and wait until a retry succeeds.
- To use a different AZ, you cannot modify the existing group. The instance group's subnet (`OverrideVpcConfig`) cannot be changed with `update-cluster` after creation (`ValidationException`), so add a **new instance group** that specifies a private subnet in another AZ and scale the existing group's instance count down to 0. Private subnets already exist in the three AZs specified in section 2.
- If available in your account, reserve capacity with a HyperPod flexible training plan. This may require account-level allowlisting.

## 5. Connect kubectl

The template prefixes the EKS cluster name with `ResourceNamePrefix` (if `EKSClusterName=harbor-rl-hp-eks`, the actual name is `harbor-rl-hp-harbor-rl-hp-eks`). Look up the actual name from the HyperPod cluster. To avoid touching your existing kubeconfig, use a file dedicated to this guide.

```bash
EKS_CLUSTER=$(aws sagemaker describe-cluster --cluster-name harbor-rl-hp --region us-west-2 \
  --query Orchestrator.Eks.ClusterArn --output text | awk -F/ '{print $NF}')
export KUBECONFIG=$HOME/.kube/harbor-rl-hp     # dedicated kubeconfig file for this guide
aws eks update-kubeconfig --name "$EKS_CLUSTER" --region us-west-2 --alias harbor-rl-hp

kubectl get nodes -o custom-columns=NAME:.metadata.name,GPU:.status.allocatable.nvidia\\.com/gpu,EFA:.status.allocatable.vpc\\.amazonaws\\.com/efa
```

Expected result: 1 node, 8 GPUs, 4 EFA. Run all later `kubectl` commands in a shell that uses the same `KUBECONFIG` (`export` it again when you open a new terminal). The kubeconfig contains no credential values, only the configuration that calls `aws eks get-token`.

The node's NVMe instance store is mounted at `/opt/dlami/nvme`. Training Jobs use `harbor-rl/cache` (model cache) and `harbor-rl/results` (results) under it as hostPath volumes.

## 6. Pod permissions and Secret

Training Pods get AWS permissions through **EKS Pod Identity**. Access keys are not copied to the cluster. The HyperPod EKS template already installs the Pod Identity Agent add-on, and Pods on HyperPod nodes cannot reach IMDS unless they use `hostNetwork`, so Pod Identity (or IRSA) is required.

Run [`infra/k8s/setup-access.sh`](../infra/k8s/setup-access.sh) right after the cluster is ready. `RUNTIME_ID` (the AgentCore runtime ID) is optional: without it, the script leaves the AgentCore statement out of the role policy, prints a note, and still creates everything else (namespace, ServiceAccount, role, Pod Identity association, Secret). After you deploy the runtime in [`03b-sandbox-agentcore.md`](03b-sandbox-agentcore.md), run the script again with `RUNTIME_ID` set. The script rewrites the role policy on every run, so keep `RUNTIME_ID` set on later reruns.

```bash
export KUBECONFIG=$HOME/.kube/harbor-rl-hp
# export RUNTIME_ID=<RUNTIME_ID>                # after 03b only: AgentCore runtime id (not the ARN)
export HF_TOKEN=<your-hugging-face-token>       # from your environment, never written to a file
export E2B_API_KEY=<your-e2b-api-key>           # E2B Cloud only; leave unset for self-hosted E2B
./infra/k8s/setup-access.sh
```

What the script does (safe to rerun):

| Resource | Details |
|---|---|
| Namespace, ServiceAccount | `harbor-rl`, `trainer` |
| IAM role `harbor-rl-trainer-pod` | Trusted principal `pods.eks.amazonaws.com` (`sts:AssumeRole`, `sts:TagSession`), [`infra/iam/trainer-pod-trust.json`](../infra/iam/trainer-pod-trust.json) rendered with `envsubst`. The trust policy requires `aws:SourceAccount` = this account and the Pod Identity session tags `eks-cluster-name` = this cluster, `kubernetes-namespace` = `harbor-rl`, `kubernetes-service-account` = `trainer`, so pods of other clusters, namespaces or ServiceAccounts cannot assume the role. The script re-applies the trust policy on every run (`update-assume-role-policy`) |
| Inline policy `trainer-pod` | [`infra/iam/trainer-pod-policy.json`](../infra/iam/trainer-pod-policy.json) rendered with `envsubst`. `bedrock-agentcore:InvokeAgentRuntimeCommand`, `InvokeAgentRuntime`, `StopRuntimeSession` on **that one runtime** (`runtime/<RUNTIME_ID>` and its `runtime-endpoint/*`; this statement is included only when `RUNTIME_ID` is set), `s3:PutObject`, `s3:GetObject` on `results/*` in the results bucket, and `ecr:GetAuthorizationToken` plus pull on the `harbor-rl/tasks-base` repository for E2B template builds |
| Pod Identity association | The `harbor-rl/trainer` ServiceAccount and the role above |
| Secret `sandbox-secrets` | Created by passing `HF_TOKEN` and `E2B_API_KEY` (only those that are set) from environment variables directly to `kubectl`. Values are not written to disk. Keys already in the Secret (for example `E2B_DOMAIN`) are kept. The Secret is written with server-side apply (`--server-side --force-conflicts --field-manager=harbor-rl`), so no `last-applied-configuration` annotation keeps a second copy of the values |

If you use self-hosted E2B, leave `E2B_API_KEY` empty and run [`infra/e2b-selfhosted/set-secret.sh`](../infra/e2b-selfhosted/set-secret.sh) (section 3.5 of [`03a-sandbox-e2b.md`](03a-sandbox-e2b.md)). This script rewrites the same Secret with the team API key from Secrets Manager, `E2B_DOMAIN`, and `HF_TOKEN` (taken from the environment, or kept from the existing Secret when it is not set). It uses the same server-side apply flags (`--server-side --force-conflicts --field-manager=harbor-rl`). Only `setup-access.sh` merges into the existing keys, so run `setup-access.sh` first (it creates the namespace) and `set-secret.sh` after it.

Because of the session tag conditions in the trust policy, a Pod Identity association created in another cluster, another namespace, or for another ServiceAccount in the same account cannot assume this role. The Secret is written with server-side apply, so unlike client-side `kubectl apply`, the values are not copied again into the `kubectl.kubernetes.io/last-applied-configuration` annotation (annotations show up as-is in tools and output that display metadata). When you edit the Secret by hand, use `kubectl apply --server-side` as well.

The results bucket `harbor-rl-sandbox-<ACCOUNT_ID>-us-west-2` is created the first time the Trainer image build script runs (section 3.1 of [`04-grpo-training.md`](04-grpo-training.md)).

## 7. How jobs run

All experiments (oracle validation, benchmarks, training) run as Kubernetes Jobs built from the same Trainer image. This ensures both sandboxes use the same node, the same image, and the same network path. The image is built in section 3 of [`04-grpo-training.md`](04-grpo-training.md), and this guide uses the same tag (`v12`) for both sandboxes.

```bash
export KUBECONFIG=$HOME/.kube/harbor-rl-hp
export AGENTCORE_RUNTIME_ARN=arn:aws:bedrock-agentcore:us-west-2:<ACCOUNT_ID>:runtime/<RUNTIME_ID>   # AgentCore jobs only

# infra/k8s/submit.sh <job name> <gpus> <command...>
TAG=v12 ./infra/k8s/submit.sh oracle-agentcore 0 python3 bench/oracle_check.py --sandbox agentcore
kubectl -n harbor-rl logs -f job/oracle-agentcore
```

How [`infra/k8s/submit.sh`](../infra/k8s/submit.sh) behaves:

- `TAG` is required. There is no default, so the script stops immediately if you omit it. The image is `<ACCOUNT_ID>.dkr.ecr.us-west-2.amazonaws.com/harbor-rl/trainer:<TAG>`; to use a different image, set the full URI in `IMAGE`.
- It renders [`infra/k8s/job.yaml`](../infra/k8s/job.yaml) with `envsubst` and runs `kubectl apply`. The Job runs as ServiceAccount `trainer` (Pod Identity), has `backoffLimit: 0` so it is not retried on failure, and is deleted automatically 24 hours after completion.
- `AGENTCORE_RUNTIME_ARN` is needed only for Jobs that use AgentCore. `AGENTCORE_NETWORK_ISOLATED` defaults to `1` (because the runtime is deployed in VPC mode with no internet access).
- `E2B_API_KEY`, `E2B_DOMAIN`, and `HF_TOKEN` are injected from the Secret `sandbox-secrets` (all optional). Without `E2B_DOMAIN`, the E2B SDK connects to E2B Cloud.
- Results are stored in `/opt/dlami/nvme/harbor-rl/results/<RUN_ID>` on the node and in S3 at `s3://harbor-rl-sandbox-<ACCOUNT_ID>-us-west-2/results/`. You can change this with `RESULTS_S3_URI`.

A training Job uses all 8 GPUs, so run only one at a time. The training command and how to set `RUN_ID` are in section 4.2 of [`04-grpo-training.md`](04-grpo-training.md). `training/run.sh` refuses to start if `/results/<RUN_ID>` is not empty. Results remain on the node disk (hostPath), so reusing the same `RUN_ID` would mix in logs from the previous run. Use a new `RUN_ID`, or move the previous directory, and then resubmit.

## 8. Common pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| `create-stack` fails with `Requires capabilities : [CAPABILITY_AUTO_EXPAND]` | The template uses the `AWS::LanguageExtensions` transform. The HyperPod documentation lists only `CAPABILITY_IAM` and `CAPABILITY_NAMED_IAM` | Specify all three capabilities (`infra/hyperpod/create-cluster.sh`) |
| Created with defaults, the subnets point to AZs in another region or the Kubernetes version is old | Template defaults are us-east-2 AZs and Kubernetes 1.34 | Set `AvailabilityZoneIds`, `FsxAvailabilityZoneId`, and `KubernetesVersion` explicitly in `params.json` |
| The stack is `CREATE_COMPLETE` and the cluster is `InService`, but there is no GPU node | Insufficient p4d capacity. `NodeProvisioningMode=Continuous` reports `InService` while it retries in the background | Check `CurrentCount` in `describe-cluster` and `list-cluster-events`. Wait, or add a new instance group in another AZ |
| `update-cluster` to change an instance group's AZ fails with `ValidationException` | `OverrideVpcConfig` cannot be changed after creation | Add a new instance group with a private subnet in another AZ and scale the existing group to 0 |
| Listing or creating a flexible training plan fails with an allowlist error | Account-level allowlisting may be required | Use On-Demand capacity, or request account allowlisting through AWS support channels |
| `aws eks update-kubeconfig` cannot find the cluster | The template prefixes the EKS name with `ResourceNamePrefix` (`harbor-rl-hp-harbor-rl-hp-eks`) | Get the actual name with `describe-cluster --query Orchestrator.Eks.ClusterArn` (section 5) |
| `kubectl` sees another cluster or has no connection information | `KUBECONFIG` is not set in a new shell | `export KUBECONFIG=$HOME/.kube/harbor-rl-hp` |
| AgentCore calls from training Pods fail with `AccessDenied` | `setup-access.sh` was run without `RUNTIME_ID`, so the AgentCore statement (scoped to a single runtime) is not in the Pod role policy | After deploying the runtime in [`03b-sandbox-agentcore.md`](03b-sandbox-agentcore.md), run `setup-access.sh` again with `RUNTIME_ID` (the runtime ID, not the ARN) |
| `submit.sh` stops with `set TAG (trainer image tag)` | The image tag has no default | Specify the tag you built (for example `TAG=v12`). The scripts that build or deploy images (`tasks/image/build-push.sh`, `agentcore/deploy_runtime.sh`, `training/build-image.sh`) all require `TAG` as well |
| A training Job exits immediately with `... is not empty; choose a new RUN_ID` | Results for the same `RUN_ID` remain on the node hostPath | Use a new `RUN_ID` or move the previous results directory |
| Training Pods get no AWS credentials, or get `AccessDenied` | The trust policy allows only Pods of this cluster, namespace `harbor-rl`, and ServiceAccount `trainer`. The Job ran in another namespace or ServiceAccount, or the cluster name differs | Submit with `infra/k8s/submit.sh` (uses `harbor-rl/trainer`). If you created a new cluster, run `setup-access.sh` again to update the trust policy |
| Resubmitting with the same name gives a `field is immutable` error or ends with `unchanged` and no new Job starts | Completed Jobs remain for 24 hours, and a Job's Pod template is immutable | Run `kubectl -n harbor-rl delete job <job name>` and resubmit, or use a different name |

Evidence and check dates for differences between the documentation and actual behavior are in section 2 of [`references.md`](references.md). The cluster deletion procedure is in section 4 of [`06-cleanup.md`](06-cleanup.md).

## Next steps

- Task suite and images: [`02-tasks-and-images.md`](02-tasks-and-images.md)
- Sandbox setup: [`03a-sandbox-e2b.md`](03a-sandbox-e2b.md) (Method A), [`03b-sandbox-agentcore.md`](03b-sandbox-agentcore.md) (Method B)
- Training: [`04-grpo-training.md`](04-grpo-training.md)
