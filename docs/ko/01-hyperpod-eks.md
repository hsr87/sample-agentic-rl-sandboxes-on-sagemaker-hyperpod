[English](../01-hyperpod-eks.md)

# 01. HyperPod EKS 클러스터 만들기

이 단계에서는 GPU 학습 노드 1대(`ml.p4d.24xlarge`, A100 40GB x 8)를 가진 SageMaker HyperPod 클러스터를 EKS 오케스트레이션으로 만들고, 학습 Pod가 샌드박스와 S3를 쓸 수 있도록 권한과 Secret을 준비합니다. 시작 전에 [`00-prerequisites.md`](00-prerequisites.md)의 쿼터와 도구를 확인하세요.

소요 시간: CloudFormation 스택 생성 수십 분(스크립트는 40~60분 대기를 가정) + GPU 노드 프로비저닝(용량 상황에 따라 추가로 수 분에서 수십 분)

## 1. 생성 방식

HyperPod EKS 클러스터는 SageMaker 콘솔, HyperPod CLI(`hyp`), AWS CLI로 만들 수 있으며 모두 같은 공식 CloudFormation 템플릿(`main-stack-eks-based-template.yaml`)을 씁니다. 이 가이드는 **AWS CLI + 공식 템플릿 + `params.json`** 방식을 씁니다. 템플릿 기본값에서 바꾼 값이 모두 파일 하나에 드러나고, 추가 도구가 필요 없기 때문입니다.

템플릿 위치(`aws/sagemaker-hyperpod-cluster-setup` 저장소가 리전별 버킷에 게시):

```
https://aws-sagemaker-hyperpod-cluster-setup-us-west-2-prod.s3.us-west-2.amazonaws.com/templates/main-stack-eks-based-template.yaml
```

> 메인 템플릿은 중첩 템플릿을 배포 시점에 같은 버킷에서 가져옵니다. 템플릿 버전을 완전히 고정하려면 `templates/` 접두사를 자체 버킷에 복사하고 `CustomBucketName` 파라미터를 지정하세요.

## 2. 파라미터

[`infra/hyperpod/params.json`](../../infra/hyperpod/params.json)은 템플릿 기본값을 다음처럼 덮어씁니다.

| 파라미터 | 값 | 이유 |
|---|---|---|
| `ResourceNamePrefix` / `ResourceNameShortPrefix` | `harbor-rl-hp` / `harborrl` | 템플릿이 만드는 리소스 이름 접두사 |
| `HyperPodClusterName` | `harbor-rl-hp` | 이후 모든 명령에서 쓰는 클러스터 이름 |
| `EKSClusterName` | `harbor-rl-hp-eks` | 실제 EKS 이름에는 `ResourceNamePrefix`가 앞에 붙음(5절) |
| `KubernetesVersion` | `1.35` | 템플릿 기본값 1.34는 표준 지원 종료가 더 가까움(종료 후 컨트롤 플레인 요금 $0.10에서 $0.60/시간) |
| `AvailabilityZoneIds` | `usw2-az1,usw2-az2,usw2-az3` | 템플릿 기본값은 us-east-2의 AZ. 3개 AZ에 프라이빗 서브넷을 만들어 두면 용량이 부족할 때 다른 AZ에 인스턴스 그룹을 추가하기 쉬움 |
| `InstanceGroupSettings1` | 그룹 `gpu`: `ml.p4d.24xlarge` x1, `usw2-az2`, `ThreadsPerCore=1`, EBS 500 GB | GPU 학습 노드 |
| `CreateFsxStack` | `false` | 이 실험은 공유 파일 시스템이 필요 없음. 모델 캐시와 결과는 노드의 NVMe 인스턴스 스토어 사용 |
| `FsxAvailabilityZoneId` | `usw2-az2` | FSx를 만들지 않지만 템플릿 기본값(us-east-2 AZ)을 이 리전 값으로 맞춤 |
| `EnableHPInferenceFeature` | `false` | 학습 전용 |
| `NodeRecovery` | `Automatic` | 노드 장애 시 HyperPod가 자동 교체 |
| `Tags` | `[{"Key":"Project","Value":"harbor-rl-sandbox"}]` | HyperPod 클러스터 자체의 태그(스택 태그와 별도) |

템플릿이 만드는 것: VPC(퍼블릭 서브넷, NAT 게이트웨이, Elastic IP), 보조 CIDR의 프라이빗 서브넷, 보안 그룹, S3 게이트웨이 엔드포인트, EKS 클러스터(애드온 vpc-cni, kube-proxy, coredns, **eks-pod-identity-agent**), lifecycle 스크립트용 S3 버킷, HyperPod 실행 역할, HyperPod 클러스터, 그리고 Lambda로 설치되는 HyperPod Helm 차트(NVIDIA device plugin, EFA device plugin, Kubeflow training operator, health monitoring agent 등).

HyperPod VPC의 CIDR(`10.192.0.0/16`)과 Pod CIDR은 이후 셀프호스팅 E2B VPC 피어링([`03a-sandbox-e2b.md`](03a-sandbox-e2b.md) 3.4절)과 AgentCore 전용 서브넷([`03b-sandbox-agentcore.md`](03b-sandbox-agentcore.md))에서 사용합니다.

## 3. 생성

```bash
export AWS_REGION=us-west-2
./infra/hyperpod/create-cluster.sh
```

[`infra/hyperpod/create-cluster.sh`](../../infra/hyperpod/create-cluster.sh)는 템플릿을 검증한 뒤 스택을 만들고 `CREATE_COMPLETE`까지 기다립니다. 핵심 부분:

```bash
aws cloudformation create-stack \
  --stack-name harbor-rl-hp \
  --template-url "$TEMPLATE_URL" \
  --parameters file://infra/hyperpod/params.json \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM CAPABILITY_AUTO_EXPAND \
  --tags Key=Project,Value=harbor-rl-sandbox \
  --region us-west-2
```

- `CAPABILITY_AUTO_EXPAND`: HyperPod 문서에는 `CAPABILITY_IAM`, `CAPABILITY_NAMED_IAM`만 나오지만, 템플릿이 `Transform: AWS::LanguageExtensions`를 쓰므로 세 번째도 필요합니다.
- 스택 이름을 바꾸려면 `STACK_NAME=...`을 지정합니다. 오래 걸리므로 별도 터미널이나 백그라운드에서 실행하고 진행 상황은 콘솔 또는 `aws cloudformation describe-stack-events --stack-name harbor-rl-hp --region us-west-2`로 확인합니다.
- 기다리는 동안 [`02-tasks-and-images.md`](02-tasks-and-images.md)의 태스크 이미지 빌드와 [`03a-sandbox-e2b.md`](03a-sandbox-e2b.md)의 셀프호스팅 E2B 배포를 병행할 수 있습니다. E2B 배포 스크립트(`deploy.sh`)는 결과 버킷이 필요하므로, 버킷을 만드는 `training/build-image.sh`([`04-grpo-training.md`](04-grpo-training.md) 3절)를 먼저 실행합니다.

## 4. GPU 노드 확인 (스택 완료만 보고 끝내지 마세요)

스택이 `CREATE_COMPLETE`이고 클러스터가 `InService`여도 GPU 인스턴스가 아직 없을 수 있습니다. 템플릿 기본값 `NodeProvisioningMode=Continuous`에서는 p4d 용량이 부족하면 HyperPod가 백그라운드에서 프로비저닝을 계속 재시도하고, 그동안에도 클러스터 상태는 `InService`로 보고됩니다.

```bash
aws sagemaker describe-cluster --cluster-name harbor-rl-hp --region us-west-2 \
  --query 'InstanceGroups[].[InstanceGroupName,CurrentCount,TargetCount]' --output table
aws sagemaker list-cluster-events --cluster-name harbor-rl-hp --region us-west-2 --max-results 10 \
  --query 'Events[].[EventTime,Description]' --output text
```

그룹 `gpu`의 `CurrentCount`가 `TargetCount`(1)와 같아지면 다음 단계로 갑니다. 계속 0이면:

- 이벤트에서 용량 부족(`insufficient capacity`) 여부를 확인하고, 재시도가 성공할 때까지 기다립니다.
- 다른 AZ를 쓰려면 기존 그룹을 고칠 수 없습니다. 인스턴스 그룹의 서브넷(`OverrideVpcConfig`)은 생성 후 `update-cluster`로 바꿀 수 없으므로(`ValidationException`), 다른 AZ의 프라이빗 서브넷을 지정한 **새 인스턴스 그룹**을 추가하고 기존 그룹의 인스턴스 수를 0으로 줄입니다. 프라이빗 서브넷은 2절에서 지정한 세 AZ에 이미 만들어져 있습니다.
- 계정에서 사용할 수 있다면 HyperPod flexible training plan으로 용량을 예약합니다. 계정 단위 허용(allowlist)이 필요할 수 있습니다.

## 5. kubectl 연결

템플릿은 EKS 클러스터 이름 앞에 `ResourceNamePrefix`를 붙입니다(`EKSClusterName=harbor-rl-hp-eks`이면 실제 이름은 `harbor-rl-hp-harbor-rl-hp-eks`). 실제 이름은 HyperPod 클러스터에서 조회합니다. 기존 kubeconfig를 건드리지 않도록 이 가이드 전용 파일을 씁니다.

```bash
EKS_CLUSTER=$(aws sagemaker describe-cluster --cluster-name harbor-rl-hp --region us-west-2 \
  --query Orchestrator.Eks.ClusterArn --output text | awk -F/ '{print $NF}')
export KUBECONFIG=$HOME/.kube/harbor-rl-hp     # dedicated kubeconfig file for this guide
aws eks update-kubeconfig --name "$EKS_CLUSTER" --region us-west-2 --alias harbor-rl-hp

kubectl get nodes -o custom-columns=NAME:.metadata.name,GPU:.status.allocatable.nvidia\\.com/gpu,EFA:.status.allocatable.vpc\\.amazonaws\\.com/efa
```

기대 결과: 노드 1개, GPU 8, EFA 4. 이후 모든 `kubectl` 명령은 같은 `KUBECONFIG`를 쓰는 셸에서 실행합니다(새 터미널을 열면 다시 `export`). kubeconfig에는 자격 증명 값이 들어가지 않고, `aws eks get-token`을 호출하는 설정만 들어갑니다.

노드의 NVMe 인스턴스 스토어는 `/opt/dlami/nvme`에 마운트되어 있습니다. 학습 Job은 이 아래의 `harbor-rl/cache`(모델 캐시)와 `harbor-rl/results`(결과)를 hostPath로 씁니다.

## 6. Pod 권한과 Secret

학습 Pod는 **EKS Pod Identity**로 AWS 권한을 받습니다. 액세스 키를 클러스터에 복사하지 않습니다. HyperPod EKS 템플릿이 Pod Identity Agent 애드온을 이미 설치하며, HyperPod 노드의 Pod는 `hostNetwork`가 아니면 IMDS에 접근할 수 없으므로 Pod Identity(또는 IRSA)가 필요합니다.

[`infra/k8s/setup-access.sh`](../../infra/k8s/setup-access.sh)는 클러스터가 준비되면 바로 실행합니다. `RUNTIME_ID`(AgentCore 런타임 ID)는 선택입니다. 지정하지 않으면 스크립트는 역할 정책에서 AgentCore 문(statement)을 빼고 안내 메시지를 출력하며, 나머지(네임스페이스, ServiceAccount, 역할, Pod Identity 연결, Secret)는 그대로 만듭니다. [`03b-sandbox-agentcore.md`](03b-sandbox-agentcore.md)에서 런타임을 배포한 뒤 `RUNTIME_ID`를 지정해 스크립트를 다시 실행합니다.

```bash
export KUBECONFIG=$HOME/.kube/harbor-rl-hp
export RUNTIME_ID=<RUNTIME_ID>                  # optional: AgentCore runtime id (not the ARN), after 03b
export HF_TOKEN=<your-hugging-face-token>       # from your environment, never written to a file
export E2B_API_KEY=<your-e2b-api-key>           # E2B Cloud only; leave unset for self-hosted E2B
./infra/k8s/setup-access.sh
```

스크립트가 하는 일(다시 실행해도 안전함):

| 리소스 | 내용 |
|---|---|
| 네임스페이스, ServiceAccount | `harbor-rl`, `trainer` |
| IAM 역할 `harbor-rl-trainer-pod` | 신뢰 주체 `pods.eks.amazonaws.com`(`sts:AssumeRole`, `sts:TagSession`). 조건: `aws:SourceAccount`가 이 계정이고, Pod Identity 세션 태그 `eks-cluster-name`(이 클러스터), `kubernetes-namespace=harbor-rl`, `kubernetes-service-account=trainer`가 일치할 때만. [`infra/iam/trainer-pod-trust.json`](../../infra/iam/trainer-pod-trust.json)을 `envsubst`로 렌더링하며, 스크립트를 실행할 때마다 `update-assume-role-policy`로 다시 적용 |
| 인라인 정책 `trainer-pod` | [`infra/iam/trainer-pod-policy.json`](../../infra/iam/trainer-pod-policy.json)을 `envsubst`로 렌더링. **해당 런타임 하나**(`runtime/<RUNTIME_ID>`와 그 `runtime-endpoint/*`. 이 문은 `RUNTIME_ID`를 지정했을 때만 포함)에 대한 `bedrock-agentcore:InvokeAgentRuntimeCommand`, `InvokeAgentRuntime`, `StopRuntimeSession`, 결과 버킷의 `results/*`에 대한 `s3:PutObject`, `s3:GetObject`, E2B 템플릿 빌드용 `ecr:GetAuthorizationToken`과 `harbor-rl/tasks-base` 리포지토리 pull |
| Pod Identity 연결 | `harbor-rl/trainer` ServiceAccount와 위 역할 |
| Secret `sandbox-secrets` | 환경 변수의 `HF_TOKEN`, `E2B_API_KEY`(설정된 것만)를 `kubectl`에 직접 전달해 생성. 값은 디스크에 쓰지 않음. Secret에 이미 있는 키(예: `E2B_DOMAIN`)는 유지. server-side apply(`--server-side --force-conflicts --field-manager=harbor-rl`)로 쓰므로 `last-applied-configuration` 어노테이션에 값의 사본이 남지 않음 |

셀프호스팅 E2B를 쓰는 경우 `E2B_API_KEY`는 비워 두고 [`infra/e2b-selfhosted/set-secret.sh`](../../infra/e2b-selfhosted/set-secret.sh)를 실행합니다([`03a-sandbox-e2b.md`](03a-sandbox-e2b.md) 3.5절). 이 스크립트는 같은 Secret을 Secrets Manager의 팀 API 키, `E2B_DOMAIN`, `HF_TOKEN`(환경 변수에서 가져오고, 설정되지 않았으면 기존 Secret의 값을 유지)으로 다시 씁니다. server-side apply 플래그도 같습니다(`--server-side --force-conflicts --field-manager=harbor-rl`). 기존 키에 병합하는 것은 `setup-access.sh`뿐이므로, `setup-access.sh`를 먼저 실행하고(네임스페이스를 만듦) `set-secret.sh`를 그 다음에 실행합니다.

신뢰 정책의 세션 태그 조건 때문에, 같은 계정의 다른 클러스터나 다른 네임스페이스, 다른 ServiceAccount에 Pod Identity 연결을 만들어도 이 역할을 맡을 수 없습니다. Secret은 server-side apply로 쓰므로, client-side `kubectl apply`처럼 `kubectl.kubernetes.io/last-applied-configuration` 어노테이션에 값이 한 번 더 복사되지 않습니다(어노테이션은 메타데이터를 보여 주는 도구나 출력에 그대로 드러남). Secret을 손으로 고칠 때도 `kubectl apply --server-side`를 쓰세요.

결과 버킷 `harbor-rl-sandbox-<ACCOUNT_ID>-us-west-2`는 Trainer 이미지 빌드 스크립트가 처음 실행될 때 만듭니다([`04-grpo-training.md`](04-grpo-training.md) 3.1절).

## 7. 작업 실행 방식

모든 실험(oracle 검증, 벤치마크, 학습)은 같은 Trainer 이미지로 만든 Kubernetes Job으로 실행합니다. 두 샌드박스가 같은 노드, 같은 이미지, 같은 네트워크 경로를 쓰게 하기 위해서입니다. 이미지는 [`04-grpo-training.md`](04-grpo-training.md) 3절에서 빌드하며, 이 가이드는 두 샌드박스에 같은 태그(`v12`)를 씁니다.

```bash
export KUBECONFIG=$HOME/.kube/harbor-rl-hp
export AGENTCORE_RUNTIME_ARN=arn:aws:bedrock-agentcore:us-west-2:<ACCOUNT_ID>:runtime/<RUNTIME_ID>   # AgentCore jobs only

# infra/k8s/submit.sh <job name> <gpus> <command...>
TAG=v12 ./infra/k8s/submit.sh oracle-agentcore 0 python3 bench/oracle_check.py --sandbox agentcore
kubectl -n harbor-rl logs -f job/oracle-agentcore
```

[`infra/k8s/submit.sh`](../../infra/k8s/submit.sh)의 동작:

- `TAG`가 필수입니다. 기본값이 없으므로 빠뜨리면 즉시 중단합니다. 이미지는 `<ACCOUNT_ID>.dkr.ecr.us-west-2.amazonaws.com/harbor-rl/trainer:<TAG>`이며, 다른 이미지를 쓰려면 `IMAGE`로 전체 URI를 지정합니다.
- [`infra/k8s/job.yaml`](../../infra/k8s/job.yaml)을 `envsubst`로 렌더링해 `kubectl apply`합니다. Job은 ServiceAccount `trainer`(Pod Identity)로 실행되고, `backoffLimit: 0`이라 실패해도 재시도하지 않으며, 완료 24시간 뒤 자동 삭제됩니다.
- `AGENTCORE_RUNTIME_ARN`은 AgentCore를 쓰는 Job에만 필요합니다. `AGENTCORE_NETWORK_ISOLATED`는 기본값 `1`입니다(런타임이 인터넷 없는 VPC 모드로 배포되므로).
- `E2B_API_KEY`, `E2B_DOMAIN`, `HF_TOKEN`은 Secret `sandbox-secrets`에서 주입됩니다(모두 optional). `E2B_DOMAIN`이 없으면 E2B SDK는 E2B Cloud에 연결합니다.
- 결과는 노드의 `/opt/dlami/nvme/harbor-rl/results/<RUN_ID>`와 S3 `s3://harbor-rl-sandbox-<ACCOUNT_ID>-us-west-2/results/`에 저장됩니다. `RESULTS_S3_URI`로 바꿀 수 있습니다.

학습 Job은 GPU 8개를 모두 쓰므로 한 번에 하나만 실행합니다. 학습 명령과 `RUN_ID` 지정 방법은 [`04-grpo-training.md`](04-grpo-training.md) 4.2절에 있습니다. `training/run.sh`는 `/results/<RUN_ID>`가 비어 있지 않으면 시작을 거부합니다. 결과가 노드 디스크(hostPath)에 남으므로, 같은 `RUN_ID`를 다시 쓰면 이전 실행의 로그와 섞이기 때문입니다. 새 `RUN_ID`를 쓰거나 이전 디렉터리를 옮긴 뒤 다시 제출하세요.

## 8. 자주 겪는 문제 (Common pitfalls)

| 증상 | 원인 | 해결 |
|---|---|---|
| `create-stack`이 `Requires capabilities : [CAPABILITY_AUTO_EXPAND]`로 실패 | 템플릿이 `AWS::LanguageExtensions` 변환을 씀. HyperPod 문서에는 `CAPABILITY_IAM`, `CAPABILITY_NAMED_IAM`만 나옴 | 세 capability를 모두 지정(`infra/hyperpod/create-cluster.sh`) |
| 기본값으로 만들었더니 서브넷이 다른 리전 AZ를 가리키거나 Kubernetes 버전이 오래됨 | 템플릿 기본값이 us-east-2 AZ, Kubernetes 1.34 | `params.json`에서 `AvailabilityZoneIds`, `FsxAvailabilityZoneId`, `KubernetesVersion`을 명시 |
| 스택은 `CREATE_COMPLETE`, 클러스터는 `InService`인데 GPU 노드가 없음 | p4d 용량 부족. `NodeProvisioningMode=Continuous`가 백그라운드에서 재시도하는 동안에도 `InService`로 보고됨 | `describe-cluster`의 `CurrentCount`와 `list-cluster-events` 확인. 기다리거나 다른 AZ에 새 인스턴스 그룹 추가 |
| 인스턴스 그룹의 AZ를 바꾸려는 `update-cluster`가 `ValidationException` | `OverrideVpcConfig`는 생성 후 변경 불가 | 다른 AZ의 프라이빗 서브넷으로 새 인스턴스 그룹을 추가하고 기존 그룹을 0으로 축소 |
| flexible training plan 조회나 생성이 허용 목록(allowlist) 오류로 실패 | 계정 단위 허용이 필요할 수 있음 | 온디맨드 용량을 쓰거나 AWS 지원 채널로 계정 허용 요청 |
| `aws eks update-kubeconfig`가 클러스터를 찾지 못함 | 템플릿이 EKS 이름 앞에 `ResourceNamePrefix`를 붙임(`harbor-rl-hp-harbor-rl-hp-eks`) | `describe-cluster --query Orchestrator.Eks.ClusterArn`으로 실제 이름 확인(5절) |
| `kubectl`이 다른 클러스터를 보거나 연결 정보가 없음 | 새 셸에서 `KUBECONFIG`가 설정되지 않음 | `export KUBECONFIG=$HOME/.kube/harbor-rl-hp` |
| 학습 Pod의 AgentCore 호출이 `AccessDenied`로 실패 | `setup-access.sh`를 `RUNTIME_ID` 없이 실행해서, 런타임 하나로 범위가 제한된 AgentCore 문이 Pod 역할 정책에 없음 | [`03b-sandbox-agentcore.md`](03b-sandbox-agentcore.md)에서 런타임을 배포한 뒤 `RUNTIME_ID`(ARN이 아닌 런타임 ID)를 지정해 `setup-access.sh`를 다시 실행 |
| `submit.sh`가 `set TAG (trainer image tag)`로 중단 | 이미지 태그에 기본값이 없음 | 빌드한 태그를 지정(예: `TAG=v12`). 이미지를 빌드하거나 배포하는 스크립트(`tasks/image/build-push.sh`, `agentcore/deploy_runtime.sh`, `training/build-image.sh`)도 모두 `TAG`가 필수 |
| 학습 Job이 `... is not empty; choose a new RUN_ID`로 바로 종료 | 같은 `RUN_ID`의 결과가 노드 hostPath에 남아 있음 | 새 `RUN_ID`를 쓰거나 이전 결과 디렉터리를 옮김 |
| 학습 Pod가 AWS 자격 증명을 받지 못하거나 `AccessDenied` | 신뢰 정책이 이 클러스터, 네임스페이스 `harbor-rl`, ServiceAccount `trainer`의 Pod만 허용. 다른 네임스페이스나 ServiceAccount에서 실행했거나 클러스터 이름이 다름 | `infra/k8s/submit.sh`로 제출(`harbor-rl/trainer` 사용). 클러스터를 새로 만들었다면 `setup-access.sh`를 다시 실행해 신뢰 정책을 갱신 |
| 같은 이름으로 다시 제출하면 `field is immutable` 오류가 나거나 `unchanged`로 끝나고 새 Job이 뜨지 않음 | 완료된 Job은 24시간 동안 남고, Job의 Pod 템플릿은 변경 불가 | `kubectl -n harbor-rl delete job <job 이름>` 후 다시 제출하거나 다른 이름 사용 |

문서와 실제 동작의 차이에 대한 근거와 확인 날짜는 [`references.md`](references.md) 2절에 있습니다. 클러스터 삭제 절차는 [`06-cleanup.md`](06-cleanup.md) 4절에 있습니다.

## 다음 단계

- 태스크 스위트와 이미지: [`02-tasks-and-images.md`](02-tasks-and-images.md)
- 샌드박스 준비: [`03a-sandbox-e2b.md`](03a-sandbox-e2b.md)(방법 A), [`03b-sandbox-agentcore.md`](03b-sandbox-agentcore.md)(방법 B)
- 학습: [`04-grpo-training.md`](04-grpo-training.md)
