[English](../references.md)

# 참고 자료

이 가이드의 주장과 수치의 근거입니다. 1절은 출처와 확인 날짜, 2절은 공식 문서와 실제 동작이 다른 점(가이드 각 장의 "Common pitfalls"의 근거), 3절은 가이드를 설계할 때 전제한 사실의 검증 결과입니다. 공식 AWS 문서와 저장소 소스 코드를 1차 근거로, 블로그는 보조 근거로만 사용했습니다.

## 1. 출처 (확인 날짜)

### 1.1 Amazon SageMaker HyperPod (EKS)

| 주제 | 출처 | 확인 날짜 |
|---|---|---|
| HyperPod EKS 공식 CloudFormation 템플릿(S3 Last-Modified 2026-09-29), 템플릿 저장소 | https://aws-sagemaker-hyperpod-cluster-setup-us-west-2-prod.s3.us-west-2.amazonaws.com/templates/main-stack-eks-based-template.yaml , https://github.com/aws/sagemaker-hyperpod-cluster-setup | 2026-09-30 |
| HyperPod EKS 사전 요구 사항(Pod Identity 지원) | https://docs.aws.amazon.com/sagemaker/latest/dg/sagemaker-hyperpod-eks-prerequisites.html | 2026-09-30 |
| 콘솔/CloudFormation으로 클러스터 생성 | https://docs.aws.amazon.com/sagemaker/latest/dg/smcluster-getting-started-eks-console-create-cluster-cfn.html | 2026-09-30 |
| HyperPod Helm 차트 | https://docs.aws.amazon.com/sagemaker/latest/dg/sagemaker-hyperpod-eks-install-packages-using-helm-chart.html | 2026-09-30 |
| Lifecycle 스크립트(저장소 이름 변경: `awsome-distributed-ai`) | https://github.com/awslabs/awsome-distributed-ai/tree/main/1.architectures/7.sagemaker-hyperpod-eks/LifecycleScripts/base-config | 2026-09-30 |
| HyperPod CLI(`sagemaker-hyperpod` 3.11.0) | https://github.com/aws/sagemaker-hyperpod-cli | 2026-09-30 |

### 1.2 Amazon Bedrock AgentCore Runtime

| 주제 | 출처 | 확인 날짜 |
|---|---|---|
| `InvokeAgentRuntimeCommand` API(이벤트 스트림, `command` 1~65,536자, `timeout` 1~3,600초, 기본 300초) | https://docs.aws.amazon.com/bedrock-agentcore/latest/APIReference/API_InvokeAgentRuntimeCommand.html | 2026-09-30 |
| 명령 실행 가이드(셸 상태 비유지, "25 TPS" 문구) | https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-execute-command.html | 2026-09-30 |
| `InvokeAgentRuntime` API(payload 최대 100,000,000 바이트, `runtimeSessionId` 33~256자) | https://docs.aws.amazon.com/bedrock-agentcore/latest/APIReference/API_InvokeAgentRuntime.html | 2026-10-01 |
| 쿼터(활성 세션, 세션 생성 TPS, 데이터 플레인 TPS, 이미지 크기, 세션 수명) | https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html | 2026-09-30 |
| HTTP 프로토콜 계약(`/ping`, `/invocations`, 포트 8080) | https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-http-protocol-contract.html | 2026-09-30 |
| 플랫폼 버전(V1, V2), V2 GA 발표 | https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-how-it-works.html#runtime-platform-versions , https://aws.amazon.com/about-aws/whats-new/2026/09/new-agentcore-runtime-generally-available/ | 2026-09-30 |
| V2 최적화 가이드("Do expensive, reusable work as your process starts, before the snapshot. For example, import dependencies, load model weights, or read static configuration from your deployment bundle." 자체 HTTP 서버를 쓰면 초기화가 끝난 뒤에만 `/ping`에서 healthy 보고, 초기화는 120초 안에 완료, 난수, 시각, 자격 증명은 시작 시점이 아니라 요청마다 계산) | https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-v2-optimize.html | 2026-09-30 (시작 단계 문구 2026-10-07) |
| 인터페이스 VPC 엔드포인트(AWS PrivateLink): 데이터 플레인 엔드포인트 `com.amazonaws.<region>.bedrock-agentcore`(Runtime 데이터 플레인 지원), 제어 플레인 `bedrock-agentcore-control`, Gateway `bedrock-agentcore.gateway`. 프라이빗 DNS는 기본 리전 DNS 이름을 그대로 사용. 엔드포인트 정책으로 SigV4 호출자를 IAM 주체 기준으로 제한 가능 | https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/vpc-interface-endpoints.html | 2026-10-07 |
| VPC 모드(지원 AZ ID, 인터넷 없는 VPC의 필수 엔드포인트, ENI 최대 8시간 유지, 컨테이너 에이전트의 최소 S3 버킷 권한: 리전별 ECR 레이어 버킷 `prod-<region>-starport-layer-bucket`) | https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-vpc.html | 2026-09-30 (S3 버킷 권한 2026-10-07) |
| 세션, 세션 중지, 권한 | https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-sessions.html , https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-stop-session.html , https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-permissions.html | 2026-09-30 |
| 관측성(런타임 지표) | https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-runtime-metrics.html | 2026-09-30 |
| Runtime Instances(x86, GPU) | https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-instances-how-it-works.html | 2026-09-30 |
| V2 소개 블로그(보조 근거) | https://aws.amazon.com/blogs/machine-learning/the-new-agentcore-runtime-elastic-optimized-and-consistently-fast-starts/ | 2026-09-30 |
| Harbor AgentCore provider 코드(Apache-2.0, `acr-kit-v1` 브랜치, 커밋 4ee0cb25), AgentCore RL 툴킷(Apache-2.0) | https://github.com/mightma/harbor/tree/acr-kit-v1 , https://github.com/awslabs/agentcore-rl-toolkit | 2026-09-30 |
| harbor-on-agentcore(참고만, LICENSE 없음) | https://github.com/mightma/harbor-on-agentcore | 2026-09-30 |
| Harbor 공식 AgentCore provider 요청 이슈 #3446 | https://github.com/harbor-framework/harbor/issues/3446 | 2026-09-30 |

### 1.3 E2B

| 주제 | 출처 | 확인 날짜 |
|---|---|---|
| E2B 요금 | https://e2b.dev/pricing | 2026-09-30 |
| 과금(billing) 문서 | https://docs.e2b.dev/billing.md | 2026-09-30 |
| 동시성 증설 | https://docs.e2b.dev/faq/increase-concurrency.md | 2026-09-30 |
| 샌드박스 최대 수명 | https://docs.e2b.dev/faq/sandbox-lifetime.md | 2026-09-30 |
| 템플릿 V2(원격 빌드), V1 빌드 중단(2026-08-01) | https://docs.e2b.dev/migration/template-v2.md , https://docs.e2b.dev/migration/v1-build-deprecation.md | 2026-09-30 |
| Persistence(pause/resume, snapshot) | https://docs.e2b.dev/sandbox/persistence.md | 2026-09-30 |
| E2B SDK 소스(샌드박스 생성 경로, egress 제어 `allow_internet_access`, network deny_out/allowlist) | https://github.com/e2b-dev/E2B | 2026-10-01 |
| 셀프호스팅 샘플 `aws-samples/sample-e2b-on-aws`(커밋 830b516: CloudFormation + Terraform + Nomad, README의 정리 절차, `infra-iac/destroy.sh`, `destroy-cnf.sh`) | https://github.com/aws-samples/sample-e2b-on-aws | 2026-10-01 (정리 스크립트 2026-10-06) |

### 1.4 Harbor, TRL, 모델, 데이터셋

| 주제 | 출처 | 확인 날짜 |
|---|---|---|
| Harbor `BaseEnvironment` | https://github.com/harbor-framework/harbor/blob/9b168361ebe973113640b9183b03cbd7884d720e/src/harbor/environments/base.py | 2026-09-30 |
| Harbor `EnvironmentFactory`(`import_path`) | https://github.com/harbor-framework/harbor/blob/9b168361ebe973113640b9183b03cbd7884d720e/src/harbor/environments/factory.py | 2026-09-30 |
| Harbor E2B 환경 | https://github.com/harbor-framework/harbor/blob/9b168361ebe973113640b9183b03cbd7884d720e/src/harbor/environments/e2b.py | 2026-09-30 |
| TRL Harbor 문서 | https://huggingface.co/docs/trl/main/en/harbor | 2026-09-30 |
| TRL `HarborSpec`, `HarborEnv`, `GRPOTrainer` 소스 | https://github.com/huggingface/trl/blob/4c623f3d154548209963842c6717e99f51b5a5b2/trl/experimental/harbor/_spec.py , https://github.com/huggingface/trl/blob/4c623f3d154548209963842c6717e99f51b5a5b2/trl/experimental/harbor/_env.py , https://github.com/huggingface/trl/blob/4c623f3d154548209963842c6717e99f51b5a5b2/trl/trainer/grpo_trainer.py | 2026-09-30 |
| TRL 릴리스(PyPI) | https://pypi.org/pypi/trl/json | 2026-09-30 |
| TRL Harbor 예제 | https://github.com/huggingface/trl/blob/main/examples/grpo_harbor/grpo_harbor.py | 2026-09-30 |
| TRL 관련 이슈와 PR | [#6776](https://github.com/huggingface/trl/issues/6776), [#7428](https://github.com/huggingface/trl/issues/7428), [#7449](https://github.com/huggingface/trl/issues/7449), [PR #6948(Harbor 통합 제거 제안)](https://github.com/huggingface/trl/pull/6948) | 2026-09-30 |
| Gemma 4 E4B 모델 설정 | https://huggingface.co/google/gemma-4-E4B-it/blob/main/config.json | 2026-09-30 |
| vLLM Gemma 4 레시피, 혼합 head size 이슈 | https://docs.vllm.ai/projects/recipes/en/stable/Google/Gemma4.html , https://github.com/vllm-project/vllm/issues/38887 | 2026-09-30 |
| 원본 태스크 데이터셋, 원본 이미지 태그 | https://huggingface.co/datasets/AdithyaSK/data_agent_rl_environment_train , https://hub.docker.com/v2/repositories/savatar101/env-data-agent-train/tags | 2026-09-30 |
| 난이도 순위 데이터셋 | https://huggingface.co/datasets/AdithyaSK/data_agent_rl_environment_train_difficulty_ranked | 2026-09-30 |

### 1.5 요금과 인스턴스 사양 (us-west-2, 온디맨드)

| 항목 | 값 | 출처 | 확인 날짜 |
|---|---|---|---|
| HyperPod `ml.p4d.24xlarge` 클러스터 | $25.91001756/h (usage type `USW2-Cluster:ml.p4d.24xlarge`, AWS Pricing API) | https://aws.amazon.com/sagemaker/ai/pricing/ | 2026-10-01 |
| AgentCore Runtime V2 | vCPU-시간 $0.1276, GB-시간 $0.0169, 초 단위(최소 1초, 메모리 최소 128 MB). V1은 $0.0895 / $0.00945 | https://aws.amazon.com/bedrock/agentcore/pricing/ | 2026-09-30 |
| E2B Cloud | $0.000014/vCPU-초, $0.0000045/GiB-초 | https://e2b.dev/pricing | 2026-09-30 |
| 셀프호스팅 E2B 노드 | `c8i.metal-48xl` $8.99616/h, `t3.xlarge` $0.1664/h, `m8i.4xlarge` $0.84672/h, `c7i.xlarge` $0.1785/h (AWS Pricing API) | https://aws.amazon.com/ec2/pricing/on-demand/ | 2026-10-01 |
| `c8i.metal-48xl` 사양 | 192 vCPU, 384 GiB (`aws ec2 describe-instance-types`) | https://aws.amazon.com/ec2/instance-types/c8i/ | 2026-10-01 |
| NAT 게이트웨이, ALB, Aurora Serverless v2, ElastiCache Serverless(Redis) | $0.045/h, $0.0225/h, $0.12/ACU-h, 저장 $0.125/GB-h(최소 1 GB) | https://aws.amazon.com/vpc/pricing/ , https://aws.amazon.com/elasticloadbalancing/pricing/ , https://aws.amazon.com/rds/aurora/pricing/ , https://aws.amazon.com/elasticache/pricing/ | 2026-10-01 |
| EKS 클러스터 | 표준 지원 $0.10/h, 연장 지원 $0.60/h | https://aws.amazon.com/eks/pricing/ | 2026-10-06 |
| VPC 인터페이스 엔드포인트 | 엔드포인트-AZ당 $0.01/h (usage type `USW2-VpcEndpoint-Hours`, AWS Pricing API), 처리 GB당 $0.01 | https://aws.amazon.com/privatelink/pricing/ | 2026-10-06 |
| Secrets Manager | 비밀당 월 $0.40, API 호출 1만 건당 $0.05 | https://aws.amazon.com/secrets-manager/pricing/ | 2026-10-06 |

## 2. 문서와 실제 동작의 차이 (확인 날짜)

각 항목은 이 가이드의 구성(1.4~1.5절의 버전)에서 확인한 동작입니다. "대응"은 이 저장소의 스크립트와 코드가 처리하는 방식입니다. 측정값은 [`05-comparison.md`](05-comparison.md)에 있습니다.

### 2.1 HyperPod EKS

| 확인 날짜 | 차이 | 대응 |
|---|---|---|
| 2026-09-30 | 템플릿이 `Transform: AWS::LanguageExtensions`를 쓰므로 `CAPABILITY_AUTO_EXPAND`가 필요하지만, 문서에는 `CAPABILITY_IAM`, `CAPABILITY_NAMED_IAM`만 나옴 | `create-cluster.sh`가 세 capability를 모두 지정 |
| 2026-09-30 | 템플릿 기본 AZ가 us-east-2(`use2-az1,use2-az2`)이고 기본 Kubernetes는 1.34(2026-12 표준 지원 종료). `hyp` CLI 기본값 1.31은 이미 연장 지원($0.60/h) | `params.json`에서 AZ와 버전(1.35)을 명시 |
| 2026-09-30 | p4d 용량이 부족해도 CloudFormation 스택은 `CREATE_COMPLETE`, 클러스터는 `InService`로 보고됨. 템플릿 기본값 `NodeProvisioningMode=Continuous`가 백그라운드에서 재시도 | 스택 완료만 보지 말고 `aws sagemaker describe-cluster`의 `CurrentCount`와 `list-cluster-events`로 노드 수를 확인 |
| 2026-09-30 | 인스턴스 그룹의 `OverrideVpcConfig`는 `update-cluster`로 바꿀 수 없음(ValidationException) | 다른 AZ가 필요하면 새 인스턴스 그룹을 추가 |
| 2026-09-30 | 템플릿이 EKS 클러스터 이름 앞에 `ResourceNamePrefix`를 붙임(`EKSClusterName=harbor-rl-hp-eks` → `harbor-rl-hp-harbor-rl-hp-eks`) | `describe-cluster --query Orchestrator.Eks.ClusterArn`으로 실제 이름을 조회해 사용 |
| 2026-09-30 | Flexible training plan 조회가 계정 allowlist가 필요하다는 오류로 실패할 수 있음 | 이 가이드는 온디맨드 용량 기준. 필요하면 AWS 담당자에게 문의 |
| 2026-09-30 | Lifecycle 스크립트 저장소가 `awsome-distributed-training`에서 `awsome-distributed-ai`로 이름 변경(템플릿의 기존 URL은 리다이렉트로 동작) | 가이드에는 새 URL 표기 |

### 2.2 TRL, vLLM

| 확인 날짜 | 차이 | 대응 |
|---|---|---|
| 2026-09-30 | `HarborSpec(environment_type=...)`는 import path를 받지 않음(`EnvironmentType` enum 검증). 오류는 첫 `reset()`에서야 발생 | `agent=`가 `"pkg.mod:Class"`를 받으므로 하네스 서브클래스를 이 경로로 넣고, 그 안에서 Harbor의 `import_path`로 커스텀 환경을 선택 |
| 2026-09-30 | TRL은 `task.toml`의 타임아웃을 무시함(도구 호출 기본 180초, verifier는 타임아웃 없음) | 두 샌드박스에 같은 값이 적용되므로 비교에는 영향 없음 |
| 2026-09-30 | TRL의 Harbor 환경은 태스크의 네트워크 정책을 환경에 전달하지 않음 | `training/harness.py`와 `bench/sandbox_bench.py`가 Harbor의 `resolve_agent_env_baseline`으로 정책을 구해 `network_policy=`로 전달. 정책을 강제할 수 없는 provider면 Harbor가 태스크를 거부 |
| 2026-09-30 | TRL 1.14.1 `HarborEnv.__del__`가 인터프리터 종료 시 이미 멈춘 이벤트 루프를 기다리며 무한 대기. 종료 시점에 열린 샌드박스도 정리되지 않음(Harbor는 E2B 샌드박스를 24시간 타임아웃으로 생성) | 하네스가 `__del__`을 비차단으로 바꾸고, 스레드 풀이 닫히기 전에 실행되는 종료 훅에서 살아 있는 샌드박스를 모두 중지 |
| 2026-09-30 | TRL 1.14.1(main 7379929에서도 동일): vLLM 서버 모드 + 도구 호출 + 학습 프로세스 2개 이상이면 `_tool_call_loop`에서 `IndexError`. 서버 모드 생성은 모든 rank의 요청 수가 같다고 가정하지만 도구 루프에서는 rank마다 다름. 집합 통신 불일치로 교착 가능 | `training/trl_patches.py`: rank별 개수로 오프셋 계산, 먼저 끝난 rank는 빈 요청으로 집합 통신에 참여. 두 샌드박스에 동일 적용 |
| 2026-09-30 | TRL은 환경 클래스의 모든 public 메서드를 도구로 노출. 도우미 메서드를 public으로 두면 도구 스키마 생성에서 `DocstringParsingException` | 도구가 아닌 메서드는 `_` 접두사 |
| 2026-10-01 | 서버 모드의 다중 턴 컨텍스트 상한 검사는 모델 설정의 `max_position_embeddings`(Gemma 4 E4B 131k) 기준이고 vLLM 서버의 `--max-model-len`은 모름. 서버 한도보다 긴 요청은 vLLM이 400으로 거부해 학습 전체가 종료됨 | `training/run.sh`가 `--max-model-len 32768`로 실행(다중 턴 프롬프트 + 출력 8,192 토큰 수용) |
| 2026-09-30 | vLLM 서버를 `--gpu-memory-utilization 0.85`로 띄우면 첫 가중치 동기화에서 OOM(Gemma 4 E4B의 per-layer embedding 텐서를 받을 버퍼를 새로 할당). 로그 끝에는 원인 대신 "start_weight_update must be called before update_weights"만 남음 | `--gpu-memory-utilization 0.6`. 로그에서는 첫 번째 ERROR를 확인 |
| 2026-10-01 | `completions/clipped_ratio`가 Gemma 4에서 실제보다 높게 나옴. vLLM은 `generation_config.json`의 종료 토큰(`<eos>`, `<turn\|>`, `<\|tool_response>`)에서 멈추지만 TRL은 마지막 토큰이 tokenizer의 `eos_token_id`나 pad일 때만 정상 종료로 셈 | `mask_truncated_completions=False`(기본값)라 학습에는 영향 없음. 이 지표는 비교에 쓰지 않음 |
| 2026-10-01 | 학습 중 `CUDACachingAllocator ... expandable_segments: memory mapping failed with OOM` 경고가 반복되지만 학습은 계속됨 | 비치명적 경고(A100 40GB에서 Gemma 4 262k 어휘 logits가 큼). 두 샌드박스 공통 |
| 2026-09-30 | vLLM 공식 이미지(`vllm/vllm-openai`)에는 `python` 명령이 없고 `python3`만 있음 | 스크립트에서 `python3` 사용 |
| 2026-09-30 | TRL PR #6948이 `trl.experimental.harbor` 제거를 제안 | `trl==1.14.1` 고정 |

### 2.3 AgentCore Runtime

| 확인 날짜 | 차이 | 대응 |
|---|---|---|
| 2026-09-30 | `InvokeAgentRuntimeCommand`는 EOF가 오지 않는 열린 파이프를 stdin으로 넘김. stdin을 읽는 명령(`cat`, 인자 없는 `python3`)은 타임아웃까지 멈춤. 정책 모델이 실제로 이런 명령을 생성함. Docker(`-i` 없는 `exec`)와 E2B는 stdin을 주지 않음. 문서에 없는 동작 | 모든 명령 앞에 `exec </dev/null;`을 붙여 Docker/E2B와 의미를 맞춤 |
| 2026-09-30 | 명령 요청에는 `command`, `timeout`만 있고 cwd, env 필드가 없음. 명령을 셸로 감싸지 않으면 파이프와 `$VAR`가 해석되지 않음 | 모든 명령을 `/bin/bash -c`로 감싸고 `cd`, `export`를 명령 문자열에 포함 |
| 2026-09-30 | V2는 스냅샷에서 기동하므로 초기화 시점의 난수 시드, uuid, 시간, 호스트명, PID 상태가 모든 세션에 복제됨 | 이미지 초기화 단계에서 시드에 의존하는 상태를 만들지 않음. RL 태스크 작성 시 주의 |
| 2026-09-30 | 참고 구현의 shim은 `stop(delete=False)`나 클라이언트 비정상 종료 시 HealthyBusy를 보고해 세션이 최대 8시간까지 과금될 수 있음 | 이 저장소의 shim은 HealthyBusy를 보고하지 않고, `stop()`은 항상 `StopRuntimeSession` 호출 |
| 2026-10-01 | 명령 실행 문서의 "25 TPS" 제한은 `InvokeAgentRuntimeCommand`에 적용되지 않음. 명령은 데이터 플레인 쿼터(1,000 TPS), 25 TPS는 세션 생성 쿼터로 쿼터 페이지와 일치. 세션 생성 쿼터는 높은 동시성에서 스로틀 오류가 아니라 세션 시작 지연 증가로 나타남 | 측정값은 `05-comparison.md` |
| 2026-10-01 | 런타임 호출 지표는 `Resource`(런타임 ARN), `Operation`, `ComputeType=MicroVM`, `Name=<런타임>::DEFAULT` 4개 차원을 모두 지정해야 조회됨. `CPUUsed-vCPUHours`, `MemoryUsed-GBHours`는 `Resource`, `Service=AgentCore.Runtime`, `Name`. `StopRuntimeSession` 지표는 세션 ID를 `Resource`로 써서 세션마다 따로 생김 | `bench/agentcore_metrics.py` |
| 2026-09-30 | 스냅샷 복원 직후 세션에서 무거운 패키지(pandas 등)를 처음 import하는 명령이 이후 명령보다 훨씬 느림(복원 후 첫 파일 읽기 비용으로 추정) | V2 최적화 가이드의 권고대로 두 샌드박스 모두 스냅샷 전에 읽기 전용 공용 워밍업 `tasks/image/warmup.sh`를 실행(AgentCore: shim이 8080을 열기 전, E2B: 템플릿 start command) |
| 2026-10-07 | 워밍업을 스냅샷에 담아도 AgentCore 새 세션의 첫 태스크 라이브러리 import에는 긴 꼬리가 있음: 30세션 중 대부분은 1.7~2.7초지만 일부는 약 57초까지(p95 46.6초). 같은 세션의 두 번째 import는 p95 1.6초. 같은 워밍업의 E2B는 0.84~0.93초(이상값 1건 3.2초) | 원인은 확인하지 못함. `05-comparison.md` 2절에 보고. 도구 타임아웃을 정할 때 감안 |
| 2026-10-07 | 데이터 플레인 인터페이스 엔드포인트가 없으면 학습 Pod는 `InvokeAgentRuntime`/`InvokeAgentRuntimeCommand`/`StopRuntimeSession`을 퍼블릭 리전 엔드포인트로 호출함. 반면 E2B는 VPC 피어링과 내부 ALB로 호출 | `network.sh`가 `com.amazonaws.<region>.bedrock-agentcore` 인터페이스 엔드포인트(프라이빗 DNS, 이 계정 전용 정책)를 추가해 두 샌드박스 모두 사설 경로로 호출 |
| 2026-10-01 | shim을 거친 파일 전송은 수 MB 단위부터 크기에 비례하지 않게 느려짐 | 큰 파일은 S3 경유를 권장. 학습에서는 verifier 결과(수 KB)만 오감 |
| 2026-09-30 | arm64 이미지에서 `import numpy`가 `OPENBLAS_CORETYPE` 없이 정상 동작(numpy 2.5.3). harbor-on-agentcore가 보고한 SIGILL은 이 이미지에서 재현되지 않음 | 설정 추가 없음 |
| 2026-10-06 | VPC 모드(인터넷 없음)에서 세션 보안 그룹의 egress를 엔드포인트로만 제한하면, S3 관리형 prefix list로의 HTTPS도 허용해야 함(ECR 이미지 레이어가 S3 게이트웨이 엔드포인트로 옴). 없으면 런타임 업데이트가 `UPDATE_FAILED`("internal error")로 실패하고 원인이 표시되지 않음 | `network.sh`가 세션 보안 그룹에 S3 prefix list egress 443을 추가 |
| 2026-10-06 | 인터페이스 엔드포인트의 private DNS는 VPC 전체에 적용되므로, 같은 VPC의 HyperPod 노드와 파드의 ECR, CloudWatch Logs 호출도 이 엔드포인트로 감 | 엔드포인트 보안 그룹이 세션 보안 그룹과 VPC CIDR 전체에서 HTTPS를 허용 |
| 2026-10-06 | 네트워크 설정은 세션이 아니라 런타임 단위. 런타임을 지워도 VPC 모드 ENI가 최대 8시간 남아 서브넷과 보안 그룹 삭제를 막음 [documented] | 정리 시 런타임을 먼저 지우고 ENI 해제를 기다림(`06-cleanup.md` 3절) |
| 2026-10-06 | CloudTrail 이벤트 기록(`lookup-events`)에는 제어 플레인 호출(`CreateAgentRuntime`, `UpdateAgentRuntime`)이 기본으로 남지만, 데이터 플레인 호출(`InvokeAgentRuntime`, `InvokeAgentRuntimeCommand`, `StopRuntimeSession`)은 남지 않음 | 명령 단위 감사가 필요하면 CloudTrail 데이터 이벤트(트레일, 고급 이벤트 선택기)를 별도로 구성. 데이터 이벤트 지원 여부는 이 가이드에서 검증하지 않음 |
| 2026-10-07 | AgentCore 격리 VPC 모드에서 정책 없는 S3 게이트웨이 엔드포인트는 세션 코드가 자격 증명이 허용하는 모든 S3 버킷에 닿게 하고, VPC 리졸버는 격리 서브넷에서도 공개 DNS 이름에 응답함. 엔드포인트 정책을 ECR 레이어 버킷의 `s3:GetObject`로 제한하면 세션에서 다른 버킷의 객체 읽기는 HTTP 403으로 실패하고, 이미지 pull과 oracle(56/56)은 그대로 동작 | `network.sh`가 격리 라우팅 테이블에 이 정책의 전용 S3 게이트웨이 엔드포인트를 두고, ECR과 Logs 인터페이스 엔드포인트를 이 계정 주체로 제한. DNS 터널링은 남음. Route 53 Resolver DNS Firewall(VPC 전체 적용, 허용 목록 필요)로 막을 수 있으며 이 가이드에서는 구성하지 않음 |
| 2026-09-30 | 세션 안에서 실행되는 코드는 런타임 실행 역할의 자격 증명을 읽을 수 있음 | 실행 역할을 이 런타임 이미지의 ECR pull과 런타임 로그로만 제한 |

### 2.4 E2B (셀프호스팅 샘플, SDK, Harbor E2B 환경)

| 확인 날짜 | 차이 | 대응 |
|---|---|---|
| 2026-10-01 | E2B Python SDK 2.51.0은 샌드박스 생성에 `POST /v2/sandboxes`를 쓰지만, 셀프호스팅 샘플(830b516, e2b-dev/infra 225f963)의 API는 `/v2/sandboxes`에 `GET`만 제공. 모든 생성이 `404: validation error: method not allowed`로 실패. 2.50.0까지는 `POST /sandboxes` 사용(휠 소스 확인). 템플릿 빌드 API는 영향 없음 | Trainer 이미지에서 `e2b==2.50.0` 고정. 셀프호스팅 E2B에서는 SDK 버전을 서버 버전에 맞춰 고정해야 함 |
| 2026-10-01 | Harbor E2B 환경은 샌드박스를 24시간 타임아웃으로 생성하지만, 셀프호스팅 샘플이 만드는 기본 팀 티어 `base_v1`은 `max_length_hours=1`, `concurrent_instances=20`(E2B Cloud Hobby와 같은 값). 모든 생성이 `400: Timeout cannot be greater than 1 hours`로 실패하고, 동시 20 제한은 높은 동시성의 벤치마크도 막음 | `finalize.sh`가 DB의 `tiers`에서 `base_v1`을 24시간 / 1,000으로 변경(24시간은 E2B Cloud Pro 문서값, 1,000은 노드 용량이 실제 한도가 되도록 충분히 큰 값) |
| 2026-10-01 | 샘플(830b516)의 무인 배포 체인이 `init-db` 단계에서 실패: cloud-init 경로에는 `HOME`이 없고 `deploy-all.sh`는 일부 단계에만 `HOME=/root`를 넘김(Go: `GOCACHE is not defined ...`) | `deploy.sh`가 배스천에서 `HOME=/root`로 체인을 실행 |
| 2026-10-01 | 같은 체인의 `build` 단계: 저장소 소유자는 `ubuntu`, 체인은 root로 실행되어 git이 `dubious ownership`으로 거부하고, 이미지 태그의 커밋 해시가 빈 값이 됨(`e2b-core/client-proxy:` invalid reference) | `deploy.sh`가 `git config --global --add safe.directory`를 먼저 설정 |
| 2026-10-01 | 샘플의 `PublicAccess` 파라미터는 ALB scheme(internet-facing/internal)만 바꾸고, ALB 보안 그룹은 두 모드 모두 0.0.0.0/0에서 80, 443을 허용. 샌드박스 하위 도메인(`<port>-<sandbox_id>.<E2B_DOMAIN>`)은 ALB에 닿는 누구에게나 인증 없이 응답 | `PublicAccess=Private`로 배포하고 `peer.sh`가 ALB 보안 그룹을 두 VPC CIDR의 443으로 제한. 공개 DNS 레코드는 사설 IP로만 해석됨 |
| 2026-10-01 | 샘플의 클라이언트 노드 기본 타입은 x86 `c5.metal`(`ClientInstanceType`이 빈 값일 때) | `deploy.sh`가 `c8i.metal-48xl`을 명시 |
| 2026-10-01 | 샘플 배포 로그(`/tmp/e2b.log`)에 팀 API 키가 평문으로 출력됨 | `finalize.sh`가 키를 Secrets Manager로 옮기고 로그에서 가림, 설정 파일은 root 전용(600) |
| 2026-10-06 | E2B VPC의 regional NAT 게이트웨이 라우팅 테이블은 피어링 경로를 거부함 | `peer.sh`가 게이트웨이 라우팅 테이블을 건너뛰고 나머지 모든 라우팅 테이블에 경로를 추가 |
| 2026-10-06 | 샘플의 `infra-iac/destroy.sh`는 Terraform 리소스를 지우지만 오케스트레이터 AMI는 재배포용으로 남김. Terraform 상태가 E2B 버킷에 있어 버킷을 먼저 비우면 Terraform 리소스가 고아가 됨. Terraform이 만든 비밀은 기본 30일 복구 기간이 있어 스크립트가 즉시 삭제함. 샘플 README는 ALB를 콘솔에서 지워야 할 수 있다고 안내 | `06-cleanup.md` 2절의 순서(destroy.sh, AMI, 버킷, 스택) |
| 2026-09-30 | E2B 문서끼리 기본 샌드박스 메모리가 다름(요금 페이지 4 GiB, billing 문서 512 MiB, 빌드 예제 2,048 MB) | 템플릿에 2 vCPU / 4 GiB를 명시 |

### 2.5 네트워크 차단과 기타

| 확인 날짜 | 차이 | 대응 |
|---|---|---|
| 2026-10-06 | 모든 태스크가 `network_mode = "no-network"`일 때 샌드박스에서 `curl https://example.com`은 두 샌드박스 모두 실패하지만 실패 형태가 다름: E2B는 DNS 해석 실패, AgentCore(격리 VPC 모드)는 연결 타임아웃. 태스크 데이터(`/home/user/input`)는 둘 다 읽힘 | 정책 모델이 보는 오류 메시지가 다를 수 있음. 비교 해석 시 참고 |
| 2026-09-30 | 원본 데이터셋 이미지(`savatar101/env-data-agent-train:base`)는 amd64 전용이고, 태스크 시작 시 인터넷에서 Kaggle 데이터를 내려받음(최대 1.9 GB). oracle 해답 없음 | 데이터를 이미지에 넣은 멀티 아키텍처 파생 서브셋(56개 태스크) 사용 |
| 2026-09-30 | 새로 만든 S3 버킷에 리전을 지정하지 않은 boto3 S3 클라이언트로 업로드하면 `TemporaryRedirect`로 실패 | `region_name`을 명시 |

## 3. 사전 가정 검증표

상태: 확인(confirmed), 반박(refuted), 변경(changed), 불일치(inconsistent). 확인 날짜는 모두 2026-09-30입니다(별도 표기 제외).

### 3.1 Harbor와 TRL

| 가정 | 상태 | 확인 내용 | 출처 |
|---|---|---|---|
| `trl.experimental.harbor.HarborSpec(dataset, agent="bash", environment_type="e2b", num_tasks=...)` 제공 | 확인 | 시그니처: `HarborSpec(dataset, *, agent="bash", environment_type="docker", num_tasks=None, indices=None, include_metadata=True)`. TRL v1.8.0부터 릴리스에 포함, 최신 PyPI 1.14.1 | [_spec.py@4c623f3d](https://github.com/huggingface/trl/blob/4c623f3d154548209963842c6717e99f51b5a5b2/trl/experimental/harbor/_spec.py), [PyPI](https://pypi.org/pypi/trl/json) |
| 설치: `trl[harbor]`, `harbor[e2b]`, `vllm>=0.22.0`, `transformers>=5.2.0` | 확인(부분) | 문서에 명시. 코드가 강제하는 것은 transformers 버전뿐. `trl[harbor]`는 `harbor>=0.13.0`, Python 3.12 이상 필요. Harbor 최신 0.23.0 | [TRL Harbor 문서](https://huggingface.co/docs/trl/main/en/harbor) |
| 실험적 기능이며 external agent만 지원 | 확인 | | 위와 동일 |
| 생성 배치 안의 샌드박스 프로비저닝은 순차 | 확인 | `GRPOTrainer._generate_and_score_completions`가 `environment.reset()`을 일반 for 루프로 호출. bash 도구 호출과 verifier도 프로세스 안에서 순차. 병렬성은 accelerate 프로세스 수만큼 | [grpo_trainer.py@4c623f3d](https://github.com/huggingface/trl/blob/4c623f3d154548209963842c6717e99f51b5a5b2/trl/trainer/grpo_trainer.py), [_env.py](https://github.com/huggingface/trl/blob/4c623f3d154548209963842c6717e99f51b5a5b2/trl/experimental/harbor/_env.py) |
| `BaseEnvironment` 추상 메서드 목록 | 확인 | `type()`, `_validate_definition()`, `start(force_build)`, `stop(delete)`, `upload_file`, `upload_dir`, `download_file`, `download_dir`, `exec(command, cwd, env, timeout_sec, user) -> ExecResult`. `capabilities`, `preflight`는 선택적 오버라이드 | [base.py@9b168361](https://github.com/harbor-framework/harbor/blob/9b168361ebe973113640b9183b03cbd7884d720e/src/harbor/environments/base.py) |
| Harbor CLI는 `-e module:Class`로 커스텀 환경 선택 | 확인 | `EnvironmentFactory`가 `config.import_path`로 클래스 로드 | [factory.py@9b168361](https://github.com/harbor-framework/harbor/blob/9b168361ebe973113640b9183b03cbd7884d720e/src/harbor/environments/factory.py) |
| `HarborSpec(environment_type=...)`가 import path를 받음 | 반박 | `TrialEnvironmentConfig(type=...)`에만 전달되어 `EnvironmentType` enum 검증에서 실패. `agent=`는 `"pkg.mod:Class"`를 받으므로 이 경로로 하네스 서브클래스를 넣고 그 안에서 `import_path` 사용(2.2절) | [_env.py](https://github.com/huggingface/trl/blob/4c623f3d154548209963842c6717e99f51b5a5b2/trl/experimental/harbor/_env.py) |
| 공식 Harbor AgentCore provider 없음(이슈 #3446) | 확인 | 이슈는 열려 있음. provider PR 없음(어댑터 PR #3448, #3449만 존재) | [#3446](https://github.com/harbor-framework/harbor/issues/3446) |
| `mightma/harbor-on-agentcore` 코드 재사용 | 변경 | 이 저장소에는 LICENSE가 없어 코드를 복사할 수 없음. 이 가이드의 AgentCore 환경과 shim은 Apache-2.0인 `mightma/harbor@acr-kit-v1`(커밋 4ee0cb25)과 `awslabs/agentcore-rl-toolkit`에서 출처를 표기하고 가져옴 | [harbor-on-agentcore](https://github.com/mightma/harbor-on-agentcore), [fork](https://github.com/mightma/harbor/tree/acr-kit-v1) |

### 3.2 AgentCore Runtime

| 가정 | 상태 | 확인 내용 | 출처 |
|---|---|---|---|
| `InvokeAgentRuntimeCommand`로 명령 실행, stdout/stderr/exitCode 스트리밍 | 확인 | 이벤트: `contentStart`, `contentDelta{stdout,stderr}`, `contentStop{exitCode,status}` | [API 레퍼런스](https://docs.aws.amazon.com/bedrock-agentcore/latest/APIReference/API_InvokeAgentRuntimeCommand.html) |
| 명령 타임아웃 1~3,600초, 명령 크기 최대 64 KB | 확인 | `command` 1~65,536자, `timeout` 기본 300초 | 위와 동일 |
| 명령 간 셸 상태 없음 | 확인(보완) | 셸 상태는 유지되지 않지만 파일과 백그라운드 프로세스는 세션 안에서 유지 | [runtime-execute-command](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-execute-command.html) |
| 명령에 cwd, env 지정 가능 | 반박 | 요청 본문에 `command`, `timeout`만 존재. 명령 문자열에 `cd`, `export` 포함 필요 | API 레퍼런스 |
| 쿼터(활성 세션 5,000, 데이터 플레인 1,000 TPS, 세션 생성 25 TPS, 2 vCPU/8 GB 고정, 이미지 2 GB, 최대 8시간, 유휴 15분, 런타임 1,000개) | 확인 | 기본값 기준. 자신의 계정 적용값은 Service Quotas에서 확인. 쿼터 코드: L-3E5722B2(세션), L-8EE2AEA2(세션 생성), L-46ED137C(데이터 플레인), L-F4575653(런타임 수), L-0A9E32B3(이미지) | [Quotas](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html) |
| execute-command 문서의 "25 TPS"가 명령 호출에 적용됨 | 반박(2026-10-01) | 원문: "ThrottlingException: Occurs when you exceed the request rate limit of 25 TPS." 명령 호출은 1,000 TPS 데이터 플레인 쿼터를 따르고 25 TPS는 세션 생성 쿼터(2.3절, 측정은 `05-comparison.md`) | [runtime-execute-command](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-execute-command.html), [Quotas](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html) |
| arm64 이미지만 지원 | 확인 | microVM 모드에서 x86은 "coming soon". x86/GPU는 Runtime Instances(EC2 요금 + 관리 수수료 12%, G 시리즈 7.8%)에서만 | [V2 블로그](https://aws.amazon.com/blogs/machine-learning/the-new-agentcore-runtime-elastic-optimized-and-consistently-fast-starts/), [Runtime Instances](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-instances-how-it-works.html) |
| 서비스 계약(`/ping`, `/invocations`, 포트 8080) 필요 | 확인 | 명령만 쓰는 경우의 예외 규정 없음. V2는 120초 안에 `/ping`이 healthy가 아니면 생성 실패. 최소 shim 필요 | [HTTP protocol contract](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-http-protocol-contract.html) |
| `platformVersion: V2`(2026-09 GA) | 확인 | 2026-09-18 GA, us-west-2 제공. 기본값은 V1. boto3 1.43.95 이상 또는 AWS CLI 2.36.46 이상 필요. 스냅샷 기반 기동 | [What's New](https://aws.amazon.com/about-aws/whats-new/2026/09/new-agentcore-runtime-generally-available/), [platform versions](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-how-it-works.html#runtime-platform-versions) |
| V2 요금: vCPU-시간 $0.1276, GB-시간 $0.0169, 초 단위, I/O 대기 중 CPU 과금 0 | 확인 | 최소 1초, 메모리 최소 128 MB. V1은 $0.0895 / $0.00945. 세션 종료 시까지 과금 | [Pricing](https://aws.amazon.com/bedrock/agentcore/pricing/) |
| 기본 네트워크 PUBLIC, VPC 모드는 런타임 단위 | 확인 | VPC 모드 서브넷은 usw2-az1/2/3. 인터넷 없는 VPC에서는 ecr.dkr, ecr.api, S3 게이트웨이, logs 엔드포인트 필요 | [VPC](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-vpc.html) |
| VPC 안의 호출자가 Runtime 데이터 플레인에 사설 경로로 접근 가능 | 확인(2026-10-07) | 인터페이스 엔드포인트 `com.amazonaws.<region>.bedrock-agentcore`(PrivateLink), Runtime 데이터 플레인 지원 | [VPC interface endpoints](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/vpc-interface-endpoints.html) |

### 3.3 E2B

| 가정 | 상태 | 확인 내용 | 출처 |
|---|---|---|---|
| $0.000014/vCPU-초, $0.0000045/GiB-초 | 확인 | | [Pricing](https://e2b.dev/pricing) |
| 기본 2 vCPU / 4 GiB | 불일치 | 요금 페이지는 4 GiB, billing 문서는 512 MiB, 빌드 예제는 2,048 MB. 템플릿 빌드 시 명시 필요 | [Pricing](https://e2b.dev/pricing), [Billing](https://docs.e2b.dev/billing.md) |
| 동시성 Hobby 20, Pro 100(애드온으로 1,100) | 확인 | 애드온 1개당 +500, 월 $500. 세션 생성 속도 Hobby 1/초, Pro 5/초 | [Increase concurrency](https://docs.e2b.dev/faq/increase-concurrency.md) |
| 최대 세션 Hobby 1시간, Pro 24시간 | 확인 | 연속 실행 기준, pause/resume 시 리셋 | [Sandbox lifetime](https://docs.e2b.dev/faq/sandbox-lifetime.md) |
| 셀프호스팅: `E2B_DOMAIN`, `E2B_API_KEY`로 전환 | 확인 | `aws-samples/sample-e2b-on-aws`(CloudFormation + Terraform + Nomad) | [sample-e2b-on-aws](https://github.com/aws-samples/sample-e2b-on-aws) |

### 3.4 모델과 태스크 데이터셋

| 가정 | 상태 | 확인 내용 | 출처 |
|---|---|---|---|
| Gemma 4(E2B, E4B, 12B, 26B A4B, 31B), Apache 2.0, 네이티브 function calling | 확인 | `google/gemma-4-E4B-it`는 gated 아님. 실제 파라미터 8.0B(텍스트 디코더 4.0B + per-layer embedding 2.8B + 오디오/비전) | [config.json](https://huggingface.co/google/gemma-4-E4B-it/blob/main/config.json) |
| TRL GRPO + vLLM으로 학습 가능 | 확인 | TRL 1.14.1 + transformers 5.17로 도구 호출 파싱 확인. vLLM은 0.19.0부터 Gemma 4와 `gemma4` tool parser 지원. 혼합 head size로 TRITON_ATTN 사용(vLLM #38887) | [vLLM Gemma4 recipe](https://docs.vllm.ai/projects/recipes/en/stable/Google/Gemma4.html), [vLLM #38887](https://github.com/vllm-project/vllm/issues/38887) |
| `AdithyaSK/data_agent_rl_environment_train`을 그대로 arm64에서 사용 | 변경 | 태스크 2,238개, 이미지 하나(`savatar101/env-data-agent-train:base`)지만 amd64 전용. 시작 시 HF에서 Kaggle 데이터를 내려받음(인터넷 필요, 최대 1.9 GB). oracle 해답 없음. 이 가이드는 레시피를 복원해 멀티 아키텍처로 재빌드하고 데이터를 이미지에 넣은 파생 서브셋(56개, 학습 40 / 평가 16, 서로 다른 Kaggle 데이터셋)을 사용 | [dataset](https://huggingface.co/datasets/AdithyaSK/data_agent_rl_environment_train), [Docker Hub tags](https://hub.docker.com/v2/repositories/savatar101/env-data-agent-train/tags) |
