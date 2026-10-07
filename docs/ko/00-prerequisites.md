[English](../00-prerequisites.md)

# 00. 사전 준비

이 가이드는 SageMaker HyperPod(EKS 오케스트레이션) 위에서 TRL GRPO + Harbor 학습을 실행하고, 롤아웃 샌드박스로 E2B sandbox(방법 A)와 Amazon Bedrock AgentCore Runtime(방법 B)을 각각 연결해 비교합니다. 이 문서는 시작 전에 준비할 리전, 쿼터, 로컬 도구, 자격 증명, 도메인, 예상 비용을 정리합니다.

> 용어 주의: Gemma 4 모델 라인업의 "E2B"(effective 2B, 예: `google/gemma-4-E2B-it`)는 E2B 샌드박스와 무관합니다. 이 가이드에서는 모델을 항상 전체 Hugging Face ID(`google/gemma-4-E4B-it`)로, 샌드박스는 "E2B sandbox"로 표기합니다.

전체 흐름:

| 단계 | 문서 |
|---|---|
| 사전 준비 | 00 (이 문서) |
| HyperPod EKS 클러스터와 Pod 권한 | [`01-hyperpod-eks.md`](01-hyperpod-eks.md) |
| 태스크 스위트와 멀티 아키텍처 이미지 | [`02-tasks-and-images.md`](02-tasks-and-images.md) |
| 방법 A: 셀프호스팅 E2B | [`03a-sandbox-e2b.md`](03a-sandbox-e2b.md) |
| 방법 B: AgentCore Runtime | [`03b-sandbox-agentcore.md`](03b-sandbox-agentcore.md) |
| GRPO 학습 | [`04-grpo-training.md`](04-grpo-training.md) |
| 측정 결과와 비교 | [`05-comparison.md`](05-comparison.md) |
| 정리 | [`06-cleanup.md`](06-cleanup.md) |

## 1. 리전

모든 리소스는 `us-west-2`(오레곤)에 만듭니다. 셸에 `AWS_REGION`이 설정되어 있지 않을 수 있으므로 이 가이드의 AWS CLI 명령은 항상 `--region us-west-2`를 붙입니다.

| 요구 사항 | us-west-2 |
|---|---|
| HyperPod `ml.p4d.24xlarge` | 제공 |
| AgentCore Runtime (`platformVersion` V2, VPC 모드) | 제공. VPC 모드는 지원 AZ ID(`usw2-az1`, `usw2-az2`, `usw2-az3`)의 서브넷만 사용 가능 [documented] |
| AgentCore 활성 세션 기본 쿼터 | 5,000 (us-east-1, us-west-2 외 리전은 2,500) [documented] |
| 셀프호스팅 E2B 클라이언트 노드 `c8i.metal-48xl` | 제공 |

모든 리소스에는 태그 `Project=harbor-rl-sandbox`를 붙입니다. 이 저장소의 스크립트는 자동으로 붙이며, 정리할 때 이 태그로 남은 리소스를 찾습니다([`06-cleanup.md`](06-cleanup.md)).

## 2. 서비스 쿼터

부족한 쿼터는 Service Quotas 콘솔에서 증가를 요청합니다. 승인까지 시간이 걸릴 수 있으므로 가장 먼저 확인하세요.

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

| 쿼터 | 필요량 | 기본값 | 조정 가능 |
|---|---|---|---|
| SageMaker `ml.p4d.24xlarge for cluster usage` | 1 | 계정마다 다름 (0일 수 있음) | 예 |
| EC2 Running On-Demand Standard (A, C, D, H, I, M, R, T, Z) instances (`L-1216C47A`) | 약 230 vCPU (셀프호스팅 E2B를 쓸 때만) | 계정마다 다름 | 예 |
| VPC, Elastic IP | 각 1개 이상 여유 (셀프호스팅 E2B까지 쓰면 각 2개) | 5 / 5 | 예 |
| AgentCore 활성 세션 (`L-3E5722B2`) | 128 이상 (동시성 스윕 최대값) | 5,000 [documented] | 예 |
| AgentCore 새 세션 생성 속도 (`L-8EE2AEA2`) | | 25 TPS [documented] | 예 |
| AgentCore 데이터 플레인 API (`L-46ED137C`) | | 1,000 TPS [documented] | 예 |
| AgentCore 세션당 리소스 | | 2 vCPU / 8 GB [documented] | 아니오 |
| AgentCore 컨테이너 이미지 크기 (`L-0A9E32B3`) | | 2 GB [documented] | 아니오 |
| AgentCore 최대 세션 수명 / 유휴 타임아웃 | | 8시간 / 15분 [documented] | 예 |

- 셀프호스팅 E2B의 vCPU 내역: 클라이언트 `c8i.metal-48xl` 192 + 빌드 노드 `m8i.4xlarge` 16 + `t3.xlarge` 5대(Nomad 서버 3, API 2) 20 + 배스천 `c7i.xlarge` 4 = 232. E2B는 Firecracker microVM을 쓰므로 클라이언트 노드는 bare metal이어야 합니다.
- p4d 온디맨드 용량은 보장되지 않습니다. GPU 노드가 오래 뜨지 않을 때의 대처는 [`01-hyperpod-eks.md`](01-hyperpod-eks.md) 4절을 참고합니다. 계정에서 사용할 수 있다면 HyperPod flexible training plan으로 용량을 예약할 수도 있습니다(계정 단위 허용이 필요할 수 있음).
- AgentCore 쿼터가 실제 동작에 어떻게 나타나는지는 [`03b-sandbox-agentcore.md`](03b-sandbox-agentcore.md) 7절과 [`05-comparison.md`](05-comparison.md)에 있습니다.

## 3. 로컬 도구

| 도구 | 검증한 버전 | 용도 | 설치 (macOS) |
|---|---|---|---|
| AWS CLI v2 | 2.37.6 (2.36.46 이상 필요) | 모든 AWS 작업, AgentCore `--platform-version` | `brew install awscli` |
| kubectl | 1.34 | EKS 작업 | `brew install kubectl` |
| Finch | 1.17.0 | 컨테이너 빌드와 푸시 | `brew install --cask finch` |
| Python 3 + uv | Python 3.14, uv 0.8 | 로컬 스크립트(태스크 생성, 벤치마크 분석, `submit.sh`의 명령 직렬화) | `brew install uv` |
| jq | 1.7 | JSON 처리 | `brew install jq` |
| envsubst (gettext) | 1.0 | IAM 정책과 Job 매니페스트 렌더링(`setup-access.sh`, `submit.sh`) | `brew install gettext` |
| helm | 3.19 (선택) | 정리 단계에서 차트 확인 | `brew install helm` |

- 로컬 Python 스크립트의 의존성은 `uv run --with`로 지정합니다. 태스크 생성(`tasks/select_tasks.py`, `tasks/build_suite.py`)은 `pandas`, `pyarrow`, `huggingface_hub>=1.33`, `tomli-w`, 분석(`bench/analyze.py`, `bench/cost_model.py`)은 `pandas`, `matplotlib`이 필요합니다([`02-tasks-and-images.md`](02-tasks-and-images.md), [`04-grpo-training.md`](04-grpo-training.md)).
- eksctl과 HyperPod CLI(`hyp`)는 필요하지 않습니다. 클러스터는 공식 CloudFormation 템플릿으로 만듭니다([`01-hyperpod-eks.md`](01-hyperpod-eks.md)).
- AWS CLI가 2.36.46보다 낮으면 AgentCore 런타임 생성 시 `--platform-version` 옵션을 인식하지 못합니다.
- 컨테이너 작업은 Finch를 기본으로 하고, 각 명령 옆에 Docker 대응 명령을 적습니다. Docker를 쓰는 경우 `finch`를 `docker`로, 멀티 아키텍처 빌드는 `docker buildx build --platform ... --push`로 바꾸면 됩니다.
- 용량이 큰 amd64 Trainer 이미지는 CodeBuild에서 빌드하므로 로컬 Finch는 주로 태스크 이미지와 AgentCore 이미지에 씁니다([`02-tasks-and-images.md`](02-tasks-and-images.md), [`04-grpo-training.md`](04-grpo-training.md) 3절).

```bash
# Start the Finch VM (macOS)
finch vm init    # first time only
finch vm start

# Docker equivalent: start Docker Desktop or the Docker daemon
```

## 4. 자격 증명 (환경 변수)

모든 자격 증명은 환경 변수로만 전달합니다. 값을 파일, 스크립트, kubeconfig, 컨테이너 이미지, 로그, git에 저장하지 마세요. 아래 값은 자리표시자입니다.

```bash
export AWS_REGION=us-west-2
export AWS_ACCESS_KEY_ID=<your-access-key-id>
export AWS_SECRET_ACCESS_KEY=<your-secret-access-key>
export AWS_SESSION_TOKEN=<your-session-token>    # temporary credentials (recommended)
export HF_TOKEN=<your-hugging-face-token>
export E2B_API_KEY=<your-e2b-api-key>            # E2B Cloud only (not needed for self-hosted E2B)

aws sts get-caller-identity --region us-west-2
```

| 변수 | 필요한 경우 | 클러스터로 전달되는 방식 |
|---|---|---|
| `AWS_*` | 항상 (로컬 CLI와 스크립트) | 전달하지 않음. Pod는 EKS Pod Identity로 IAM 역할 권한을 받음 |
| `HF_TOKEN` | 권장 | `infra/k8s/setup-access.sh`가 Kubernetes Secret `sandbox-secrets`에 저장 |
| `E2B_API_KEY` | E2B Cloud를 쓸 때만 | `infra/k8s/setup-access.sh`가 같은 Secret에 저장 |

- **`HF_TOKEN`:** 정책 모델 `google/gemma-4-E4B-it`과 데이터셋을 Hugging Face Hub에서 받을 때 씁니다. 이 모델은 gated 모델이 아니므로 토큰 없이도 받을 수 있지만, 익명 다운로드는 rate limit에 걸리기 쉬우므로 읽기 전용(read) 토큰을 권장합니다. https://huggingface.co/settings/tokens 에서 만듭니다.
- **셀프호스팅 E2B의 API 키:** 로컬 환경 변수로 다루지 않습니다. 배포 마지막 단계(`finalize.sh`)가 팀 API 키를 만들어 AWS Secrets Manager(`harbor-rl-e2b/team-api-key`)에 저장하고, `infra/e2b-selfhosted/set-secret.sh`가 이를 읽어 화면에 출력하지 않고 Kubernetes Secret으로 옮깁니다([`03a-sandbox-e2b.md`](03a-sandbox-e2b.md) 3.5절).
- IAM 사용자나 장기 액세스 키는 만들지 않습니다. IAM Identity Center 등에서 받은 임시 자격 증명을 쓰세요.
- 필요한 IAM 권한: CloudFormation, IAM 역할과 정책 생성, EC2/VPC, EKS, SageMaker, S3, ECR, CodeBuild, CloudWatch Logs, Secrets Manager, SSM, Route 53, ACM, Bedrock AgentCore(control plane, data plane), Service Quotas. 이 가이드는 관리자 권한 역할로 검증했습니다.

## 5. 도메인 (셀프호스팅 E2B만)

셀프호스팅 E2B(`aws-samples/sample-e2b-on-aws`)는 API와 각 샌드박스를 `api.e2b.<도메인>`, `<port>-<sandbox id>.e2b.<도메인>` 같은 호스트 이름으로 구분합니다. 따라서 다음이 필요합니다.

- 고객이 소유한 도메인과 그 도메인의 **공개(public) Route 53 호스팅 영역**. 이 가이드에서는 `E2B_DOMAIN=e2b.example.com`처럼 하위 도메인을 씁니다.
- 와일드카드 ACM 인증서의 DNS 검증 레코드, `*.e2b.<도메인>` CNAME 레코드, 메일 위장 방지 레코드(null MX, SPF `-all`, DMARC `reject`)를 배포 스크립트가 이 호스팅 영역에 만듭니다.

회사 도메인을 쓴다면 먼저 도메인 정책을 확인하세요. 많은 조직이 회사 도메인 아래에 인증 없는 공개 엔드포인트를 두는 것을 금지합니다. E2B 샌드박스 호스트는 ALB에 도달할 수 있는 누구에게나 인증 없이 열리므로, 이 가이드는 **내부(internal) ALB**(`PublicAccess=Private`)를 쓰고 HyperPod VPC와 VPC 피어링으로 연결합니다. 공개 DNS에는 사설 IP만 노출되고, ALB 보안 그룹은 두 VPC에서 오는 HTTPS 443만 허용합니다. 자세한 구성은 [`03a-sandbox-e2b.md`](03a-sandbox-e2b.md) 1~3절에 있습니다.

E2B Cloud를 쓰면 도메인, EC2 쿼터, 배포가 필요 없고 E2B 계정과 API 키(https://e2b.dev)만 있으면 됩니다. 단, 태스크 데이터와 명령 출력이 계정 밖으로 나가며, 이 가이드는 E2B Cloud에서 측정하지 않았습니다. 요금제별 한도는 Hobby 동시 20개 / 세션 최대 1시간, Pro 동시 100개 / 24시간입니다 [documented]. Harbor의 E2B 환경은 24시간 타임아웃으로 샌드박스를 만들고 동시성 스윕은 128까지 가므로, E2B Cloud로 재현하려면 Pro 이상이 필요합니다([`03a-sandbox-e2b.md`](03a-sandbox-e2b.md) 6절).

## 6. 예상 비용

모든 단가는 us-west-2 온디맨드 정가 [documented]이고, 재현 비용은 아래 가정에 따른 [estimated] 값입니다. 실제 실행에서 측정한 사용량으로 계산한 비용은 [`05-comparison.md`](05-comparison.md) 4절에 있습니다.

### 6.1 단가 [documented]

| 항목 | 단가 |
|---|---|
| HyperPod `ml.p4d.24xlarge` | $25.91/시간 |
| EKS 컨트롤 플레인 | $0.10/시간 (표준 지원이 끝난 버전은 $0.60/시간) |
| NAT 게이트웨이 | $0.045/시간 + 처리 데이터 $0.045/GB |
| 퍼블릭 IPv4 주소 | $0.005/시간 |
| VPC 인터페이스 엔드포인트 (AgentCore용 `ecr.api`, `ecr.dkr`, `logs`, `bedrock-agentcore`) | $0.01/시간 (엔드포인트 x AZ 당) + 처리 데이터 $0.01/GB |
| AgentCore Runtime | vCPU $0.1276/시간, 메모리 $0.0169/GB-시간. 초 단위 과금, I/O 대기 중에는 CPU 요금 없음 |
| E2B Cloud | vCPU $0.000014/초 ($0.0504/시간), 메모리 $0.0000045/GiB-초 ($0.0162/GiB-시간). 실행 중 할당량 기준 과금 |
| E2B Cloud Pro 요금제 | $150/월 |

### 6.2 셀프호스팅 E2B 고정 비용 [estimated]

셀프호스팅 E2B는 샌드박스 수와 무관하게 켜 두는 동안 비용이 나갑니다. 각 구성 요소의 [documented] 시간당 단가를 더한 값입니다(`bench/cost_model.py`의 `SELF_HOSTED`).

| 구성 요소 | 시간당 |
|---|---|
| 클라이언트 `c8i.metal-48xl` x1 | $8.996 |
| Nomad 서버 `t3.xlarge` x3 + API `t3.xlarge` x2 | 5 x $0.1664 = $0.832 |
| 빌드 노드 `m8i.4xlarge` x1 | $0.847 |
| 배스천 `c7i.xlarge` x1 | $0.179 |
| NAT 게이트웨이, ALB 시간 요금 | $0.045 + $0.0225 |
| Aurora Serverless v2 (최소 0.5 ACU), ElastiCache Serverless Redis (최소 1 GB) | 0.5 x $0.12 + $0.125 |
| **합계** | **약 $11.11/시간 (하루 약 $267)** |

### 6.3 재현 1회 예상 비용 [estimated]

가정:
- HyperPod 클러스터 가동 12시간: 생성, 이미지 준비와 검증, 벤치마크, GRPO 학습 2회(샌드박스별 1회, 학습 전후 평가 포함).
- 샌드박스 세션: 학습 1회당 2,112개(40 스텝 x 스텝당 48 롤아웃 = 1,920, 학습 전후 평가 2 x 16 태스크 x 6 = 192). 여기에 벤치마크와 oracle 검증을 더해 방법별 약 3,000 세션.
- 세션 평균 수명 3분(0.05시간), 샌드박스 크기 AgentCore 2 vCPU / 8 GB(고정), E2B 2 vCPU / 4 GiB.
- 셀프호스팅 E2B는 배포부터 정리까지 12시간 가동.

| 항목 | 계산식 | 예상 금액 |
|---|---|---|
| HyperPod p4d | 12시간 x $25.91 | 약 $311 |
| EKS + NAT + 퍼블릭 IPv4 | 12시간 x ($0.10 + $0.045 + $0.005) | 약 $2 |
| AgentCore용 인터페이스 엔드포인트 | 4개 x 2 AZ x $0.01 x 12시간 | 약 $1 |
| AgentCore Runtime (상한: CPU 100% 사용 가정) | 3,000 x 0.05시간 x (2 x $0.1276 + 8 x $0.0169) | 약 $59 |
| ECR, S3, CodeBuild, CloudWatch Logs | 소량 | $5 미만 |
| **공통 + AgentCore 소계** | | **약 $378** |
| 방법 A를 셀프호스팅 E2B로 (이 가이드의 방식) | 12시간 x $11.11 | 약 $133 |
| 방법 A를 E2B Cloud로 (대안) | 3,000 x 180초 x (2 x $0.000014 + 4 x $0.0000045) | 약 $25 (+ Pro $150/월) |
| **합계** | | **셀프호스팅 E2B: 약 $510. E2B Cloud: 약 $400 (Pro 포함 약 $550)** |

- 비용의 대부분은 GPU 인스턴스입니다. 샌드박스 지연이 학습 시간(따라서 GPU 비용)에 미치는 영향과 샌드박스 비용의 비중은 [`05-comparison.md`](05-comparison.md) 4절에서 측정값으로 다시 계산합니다.
- AgentCore는 CPU가 I/O를 기다리는 동안 CPU 요금이 부과되지 않으므로 위 AgentCore 금액은 상한입니다. 셀프호스팅 E2B는 반대로 사용률과 무관한 고정 비용입니다.
- 작업을 마친 뒤 클러스터를 그대로 두면 GPU만으로 하루 약 $622(24 x $25.91), 셀프호스팅 E2B까지 켜 두면 하루 약 $890이 추가로 나갑니다. 끝나면 바로 [`06-cleanup.md`](06-cleanup.md)를 따라 정리하세요.

## 다음 단계

[`01-hyperpod-eks.md`](01-hyperpod-eks.md)에서 HyperPod EKS 클러스터를 만듭니다. 클러스터 생성과 GPU 프로비저닝이 진행되는 동안 [`02-tasks-and-images.md`](02-tasks-and-images.md)의 태스크 이미지 빌드와 [`03a-sandbox-e2b.md`](03a-sandbox-e2b.md)의 셀프호스팅 E2B 배포(1~1.5시간)를 병행할 수 있습니다. 단, E2B 배포 스크립트(`deploy.sh`)는 결과 버킷에 CloudFormation 템플릿을 올리므로, 버킷을 만드는 `training/build-image.sh`([`04-grpo-training.md`](04-grpo-training.md) 3절)를 먼저 실행해야 합니다.
