[English](../02-tasks-and-images.md)

# 02. 태스크 스위트와 멀티 아키텍처 이미지

이 단계에서는 두 샌드박스가 똑같이 실행할 태스크 56개(학습 40 + held-out 16)를 만들고, 모든 태스크가 공유하는 베이스 이미지 하나를 `linux/amd64`와 `linux/arm64`로 빌드해 Amazon ECR에 올립니다. 이어서 같은 이미지를 AgentCore Runtime(arm64 + shim)과 E2B(amd64 템플릿)가 각각 어떻게 사용하는지 설명합니다.

사전 조건: `00-prerequisites.md`의 도구(AWS CLI, Finch, `uv`)와 환경 변수 `HF_TOKEN`

소요 시간: 태스크 생성 수 분, 베이스 이미지 빌드와 푸시 수십 분 이내(로컬 네트워크와 CPU에 따라 다름), E2B 템플릿 사전 빌드 수 분

## 1. 왜 파생 태스크 스위트를 만드는가

출발점은 TRL Harbor 예제가 쓰는 데이터셋 `AdithyaSK/data_agent_rl_environment_train`(Kaggle 데이터 분석 질문 태스크)입니다. 업스트림 태스크 환경은 두 샌드박스 비교에 그대로 쓸 수 없으므로, 일부 태스크를 골라 같은 형식의 Harbor 태스크로 다시 만듭니다.

| 업스트림 상태 | 문제 | 이 가이드의 대응 |
|---|---|---|
| 태스크 이미지 `savatar101/env-data-agent-train:base`가 amd64 전용 | AgentCore Runtime은 arm64 이미지만 실행 [documented] | 같은 레시피(`python:3.12-slim` + 데이터 분석 패키지)를 버전 고정 후 멀티 아키텍처로 재빌드 |
| 샌드박스 시작 시 healthcheck가 Hugging Face 버킷에서 Kaggle 데이터를 내려받음 | 인터넷이 필요하고, 익명 접근은 rate limit에 걸리며, 샌드박스와 무관한 네트워크 지연이 측정에 섞임 | 선택한 태스크의 데이터를 이미지에 미리 포함하고 태스크를 `no-network`로 실행 |
| oracle 해답 없음 | 태스크가 각 샌드박스에서 유효한지(환경, 데이터, verifier) 확인할 수 없음 | `solution/solve.sh`가 정답을 기록하도록 추가 |
| verifier에 LLM judge 단계(`OPENAI_API_KEY`) | 외부 API 의존, 보상 잡음 | 정답이 숫자인 태스크만 선택하고 judge 단계 제거 |

저장소에는 선택과 생성 스크립트, 생성된 태스크 디렉터리만 있고 Kaggle 데이터는 없습니다(`tasks/image/data/`는 `.gitignore` 대상). 업스트림 instruction과 grader(`tests/grader.py`)는 그대로 유지합니다.

## 2. 태스크 선택 규칙

[`tasks/select_tasks.py`](../../tasks/select_tasks.py)가 업스트림 `manifest.parquet`과 난이도 레지스트리(`AdithyaSK/data_agent_rl_environment_train_difficulty_ranked`의 `registry.json`, 태스크별 롤아웃 solve fraction)를 합쳐 `tasks/suite.json`을 만듭니다. 두 데이터셋의 리비전은 코드에 고정되어 있습니다(`TRAIN_REVISION` `4073bb9b817aba164d8697cbe504a646522cd07a`, `RANKED_REVISION` `5923562863a29724c026021a2d16cb8e44e376d9`). 같은 시드와 같은 리비전이면 결과가 같으며, 사용한 리비전은 `suite.json`의 `source.train_revision`, `source.ranked_revision`에 기록됩니다. [`tasks/build_suite.py`](../../tasks/build_suite.py)도 `suite.json`에 기록된 `train_revision`으로 업스트림 태스크를 내려받습니다.

| 규칙 | 기본값 | 이유 |
|---|---|---|
| `verdict` | `verified` | 업스트림 검증을 통과한 태스크만 |
| 정답 형식 | 숫자(`^[-+]?\d[\d,]*(\.\d+)?%?$`) | grader의 exact match와 numeric tolerance 단계만으로 보상 결정 |
| `package_tier` | 1 | 베이스 이미지에 설치된 패키지만 필요 |
| 데이터셋 크기 | 20 MB 이하 | 모든 데이터를 하나의 공용 이미지에 포함 |
| solve fraction | 0.125 ~ 0.25 (`--solve-lo`, `--solve-hi`) | 정책 모델이 일부만 맞히는 난이도여야 GRPO 그룹 안에 보상 차이가 생겨 학습 신호가 됨 |
| 데이터셋당 태스크 | 최대 3개 (`--max-per-dataset`) | 특정 데이터셋 쏠림 방지 |
| held-out 분리 | 데이터셋의 35%를 먼저 held-out용으로 떼어 냄 (`--heldout-dataset-frac`) | held-out 태스크는 학습 태스크와 Kaggle 데이터셋이 겹치지 않음 |
| 시드 | 42 | 결정적 선택 |

데이터셋 순서를 시드로 섞은 뒤 데이터셋마다 한 개씩 돌아가며(round-robin) 태스크를 고릅니다.

최종 스위트(`tasks/suite.json`):

| 분할 | 태스크 | Kaggle 데이터셋 | 난이도 레지스트리 solve fraction 평균 |
|---|---|---|---|
| train | 40 | 27 | 0.18 |
| heldout | 16 | 14 (train과 겹치지 않음) | 0.20 |

이미지에 포함되는 데이터는 합계 약 57 MB입니다.

```bash
export HF_TOKEN=...                     # environment variable only (anonymous access hits rate limits)
uv run --with pandas --with pyarrow --with "huggingface_hub>=1.33" --with tomli-w \
  python3 tasks/select_tasks.py         # -> tasks/suite.json
uv run --with pandas --with pyarrow --with "huggingface_hub>=1.33" --with tomli-w \
  python3 tasks/build_suite.py          # -> tasks/train/, tasks/heldout/, tasks/image/data/
```

저장소에는 Python 프로젝트 파일이 없으므로 의존성(`pandas`, `pyarrow`, `huggingface_hub>=1.33`, `tomli-w`)을 `uv run --with`로 지정합니다.

`select_tasks.py`는 후보 데이터셋마다 버킷 목록을 조회해 크기를 계산하므로, 실행에 수 분이 걸릴 수 있습니다.

## 3. 태스크 구조

[`tasks/build_suite.py`](../../tasks/build_suite.py)가 업스트림 태스크를 Harbor 태스크 형식으로 변환하고, 각 태스크의 Kaggle 데이터를 `tasks/image/data/<owner>__<dataset>/`에 내려받습니다(파일은 하위 폴더 없이 평탄화). 예: `tasks/train/0000_939_939639_qa_2/`

```
instruction.md           # upstream prompt (LLM-judge sentence removed)
task.toml                # config (below)
environment/Dockerfile   # ARG BASE_IMAGE=harbor-rl-tasks-base:latest; FROM ${BASE_IMAGE}; WORKDIR /workdir (identical for all 56 tasks)
tests/test.sh            # reads /workdir/answer.txt, writes /logs/verifier/reward.txt
tests/grader.py          # upstream grader: exact match, then numeric tolerance
solution/solve.sh        # oracle: printf '<gold>' > /workdir/answer.txt
```

`task.toml`에서 업스트림과 달라지는 부분:

| 키 | 값 | 비고 |
|---|---|---|
| `task.name` | `harbor-rl-suite/<task_dir>` | |
| `environment.cpus`, `memory_mb` | `2`, `4096` | E2B 템플릿 리소스. AgentCore 세션은 2 vCPU / 8 GB로 고정이라 메모리가 다름(`05-comparison.md`에 명시) |
| `environment.network_mode` | `"no-network"` | 아래 3.1 |
| `environment.healthcheck.command` | `rm -rf /home/user/input && ln -s /data/<owner>__<dataset> /home/user/input && [ -n "$(ls /home/user/input/)" ]` | 다운로드 대신 이미지에 포함된 데이터를 심볼릭 링크. Harbor `run_healthcheck()`로 두 샌드박스에서 같은 방식으로 실행 |
| `environment.env` | `KAGGLE_DATASET_NAME` | |
| `verifier.env` | `EXPECTED_ANSWER`, `QUESTION`, `REWARD_MODE`, `ATOL`, `RTOL` (`OPENAI_API_KEY` 제거) | judge 단계 없음, 검증 시 `pip install openai` 없음 |
| `metadata` | `suite_split`, `sweep_solve_frac`, `data_prefix` | 분석용 |

보상은 0.0 또는 1.0입니다. 답 파일이 없거나 비어 있으면 `test.sh`가 0.0을 기록합니다.

### 3.1 `network_mode = "no-network"`

모든 태스크의 `task.toml`에는 `build_suite.py`가 쓴 아래 설정이 들어 있습니다.

```toml
[environment]
network_mode = "no-network"
```

- 데이터가 이미지에 들어 있으므로 태스크 수행에 네트워크가 필요하지 않습니다.
- 모델이 생성한 임의의 코드가 샌드박스 안에서 실행되므로, 외부로 나가는 트래픽(egress)을 막아 두는 것이 안전합니다.
- 두 샌드박스가 같은 조건(인터넷 없음)에서 실행되므로 비교가 공정합니다.

Harbor는 환경 객체를 만들 때 이 정책을 검사합니다(`BaseEnvironment._validate_network_policy_support`, Harbor 0.23.0). 환경이 인터넷 차단을 지원한다고 선언하지 않으면 `network_mode='no-network' is not supported by ...` 오류로 태스크를 거부하며, 조용히 인터넷을 허용하지 않습니다.

| 샌드박스 | 정책 적용 방식 |
|---|---|
| E2B | Harbor E2B 환경이 샌드박스를 `allow_internet_access=False`로 생성 |
| AgentCore | 네트워크는 세션이 아니라 런타임 단위 설정입니다. 런타임을 인터넷 경로가 없는 서브넷의 VPC 모드로 배포하고(`03b-sandbox-agentcore.md`), 환경 변수 `AGENTCORE_NETWORK_ISOLATED=1`일 때만 `AgentCoreEnvironment`가 인터넷 차단 지원을 선언 |

TRL의 Harbor 통합은 네트워크 정책을 Harbor에 넘기지 않으므로, 학습 하네스가 태스크의 정책을 직접 해석해 전달합니다(`04-grpo-training.md` 6.1). 샌드박스 안에서 `curl https://example.com`은 실패하고(E2B: DNS 해석 실패, AgentCore: 연결 타임아웃) `/home/user/input`의 태스크 데이터는 읽을 수 있음을 확인했습니다.

## 4. 공용 멀티 아키텍처 베이스 이미지

56개 태스크가 이미지 하나 `harbor-rl/tasks-base`를 공유합니다([`tasks/image/Dockerfile`](../../tasks/image/Dockerfile)).

- 베이스: `python:3.12-slim-trixie@sha256:05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f`(다이제스트 고정, 멀티 아키텍처 인덱스) + `ca-certificates`, `curl`, `git`
- 패키지: [`requirements.txt`](../../tasks/image/requirements.txt)(`requirements.in`의 pandas, numpy, scipy, scikit-learn, statsmodels, matplotlib, seaborn, plotly, tabulate를 버전 고정)
- 데이터: `/data/<owner>__<dataset>/`
- 디렉터리: `/home/user/input`, `/workdir`, `/logs/verifier`

이 가이드는 태그 `v2`를 사용합니다. 이미지 크기는 AgentCore 컨테이너 이미지 한도(2 GB) [documented]보다 훨씬 작습니다.

### 4.1 빌드와 푸시

[`tasks/image/build-push.sh`](../../tasks/image/build-push.sh)는 `TAG`가 필수입니다(기본값 없음). ECR 리포지토리 `harbor-rl/tasks-base`가 없으면 push 시 스캔을 켜고 `Project=harbor-rl-sandbox` 태그를 붙여 만든 뒤, Finch로 로그인, 빌드, 푸시합니다.

```bash
export AWS_REGION=us-west-2
TAG=v2 ./tasks/image/build-push.sh
# -> <ACCOUNT_ID>.dkr.ecr.us-west-2.amazonaws.com/harbor-rl/tasks-base:v2
```

스크립트가 실행하는 명령과 Docker 대응 명령:

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

확인: 이미지 인덱스 안에 두 아키텍처가 있어야 합니다.

```bash
aws ecr describe-images --repository-name harbor-rl/tasks-base --region us-west-2 \
  --query 'imageDetails[].[imageTags[0],imageManifestMediaType,imageSizeInBytes]' --output table
```

태그 `v2` 항목은 `application/vnd.oci.image.index.v1+json`이고, 태그 없는 아키텍처별 manifest 2개가 함께 보입니다.

> Apple silicon Mac에서는 amd64 쪽이 에뮬레이션으로 빌드됩니다. 이 이미지는 wheel 설치와 데이터 복사뿐이라 Finch 기본 VM 설정으로 충분합니다. 반면 크기가 큰 Trainer 이미지는 AWS CodeBuild(amd64)에서 빌드합니다(`04-grpo-training.md`).

### 4.2 샌드박스 워밍업 (`tasks/image/warmup.sh`)

두 샌드박스 모두 세션을 스냅샷에서 복원합니다(AgentCore V2 세션, E2B 템플릿). [`tasks/image/warmup.sh`](../../tasks/image/warmup.sh)는 스냅샷을 찍기 전에 한 번 실행되어, Python과 태스크 라이브러리(pandas, numpy, scipy, sklearn, statsmodels, seaborn, plotly, tabulate, matplotlib)를 import하고 `/data` 아래 파일을 모두 읽습니다. 이렇게 읽은 내용이 스냅샷에 페이지 캐시로 담깁니다. AgentCore V2 최적화 가이드의 권고(의존성 import처럼 비싸고 재사용 가능한 작업은 스냅샷 전 시작 단계에서 수행)를 따른 것입니다 [documented].

| 샌드박스 | 실행 시점 | 코드 |
|---|---|---|
| AgentCore | shim이 컨테이너 시작 시 8080을 열기 전에 실행(최대 90초, 실패해도 속도만 손해). V2는 첫 healthy `/ping` 뒤에 스냅샷을 찍음 | [`agentcore/shim/main.go`](../../agentcore/shim/main.go) 138~172행(`main()`, `warmup()`), 이미지의 `/usr/local/share/harbor/warmup.sh`([`agentcore/image/Dockerfile`](../../agentcore/image/Dockerfile) 12행) |
| E2B | 템플릿 start command로 실행하고, 준비 확인 `test -f /tmp/.harbor-warmup-done`이 통과하면 E2B가 템플릿 스냅샷을 찍음 | [`bench/prebuild_e2b_templates.py`](../../bench/prebuild_e2b_templates.py) 48~52행, 67~68행(`set_start_cmd`) |

- 스크립트는 파일을 읽기만 하고 세션별 상태(난수, 시각, 자격 증명)를 만들지 않으므로, 스냅샷에서 복원된 세션끼리 공유해도 안전합니다.
- 두 샌드박스가 같은 스크립트를 쓰므로 비교 조건이 같습니다. 효과는 `05-comparison.md` 2절의 첫 Python import 지연(`py_import_first`, `py_import_again`)으로 확인합니다.

## 5. 각 샌드박스가 같은 이미지를 쓰는 방식

```
harbor-rl/tasks-base:v2 (OCI image index)
 ├─ linux/arm64 ─► + shim layer + warmup.sh ─► harbor-rl/tasks-agentcore:v2 ─► one AgentCore Runtime (all 56 tasks)
 └─ linux/amd64 ─► E2B Template().from_image(...).set_start_cmd(warmup) ─► 56 templates (alias = Harbor naming rule)
```

### 5.1 AgentCore: arm64 + shim, 런타임 하나

AgentCore Runtime은 HTTP 서비스 계약(포트 8080, `GET /ping`, `POST /invocations`)을 요구하므로 베이스 이미지 위에 작은 Go shim([`agentcore/shim/main.go`](../../agentcore/shim/main.go))을 얹습니다([`agentcore/image/Dockerfile`](../../agentcore/image/Dockerfile)). shim은 다이제스트로 고정한 `golang:1.25-bookworm` 단계(`@sha256:3b4a1151...`, 전체 다이제스트는 Dockerfile에 있음)에서 `linux/arm64`로 정적 빌드되어 `/usr/local/bin/agentcore-shim`에 들어가고 `ENTRYPOINT`가 됩니다. 같은 이미지에 워밍업 스크립트가 `/usr/local/share/harbor/warmup.sh`로 들어갑니다(4.2절). 태스크 명령 자체는 `InvokeAgentRuntimeCommand`로 실행됩니다.

[`agentcore/deploy_runtime.sh`](../../agentcore/deploy_runtime.sh)가 이미지 빌드, 실행 역할, 런타임 생성을 한 번에 처리합니다. `TAG`는 필수이며 `tasks-base`의 태그를 그대로 씁니다. `SKIP_BUILD=1`이면 이미 푸시된 `tasks-agentcore:$TAG`를 재사용합니다. 빌드 컨텍스트는 `shim/main.go`와 `tasks/image/warmup.sh`만 담은 임시 디렉터리입니다([`agentcore/deploy_runtime.sh`](../../agentcore/deploy_runtime.sh) 31~35행). 자세한 절차는 `03b-sandbox-agentcore.md`에 있습니다.

```bash
# Build context: the shim source plus the shared warm-up script
CTX=$(mktemp -d); mkdir -p $CTX/shim
cp agentcore/shim/main.go $CTX/shim/ && cp tasks/image/warmup.sh $CTX/

# Finch (what deploy_runtime.sh runs)
finch build --platform linux/arm64 --build-arg BASE_IMAGE=$REGISTRY/harbor-rl/tasks-base:v2 \
  -f agentcore/image/Dockerfile -t $REGISTRY/harbor-rl/tasks-agentcore:v2 $CTX
finch push --platform linux/arm64 $REGISTRY/harbor-rl/tasks-agentcore:v2

# Docker equivalent
docker buildx build --platform linux/arm64 --build-arg BASE_IMAGE=$REGISTRY/harbor-rl/tasks-base:v2 \
  -f agentcore/image/Dockerfile -t $REGISTRY/harbor-rl/tasks-agentcore:v2 --push $CTX
```

**런타임 하나로 스위트 전체를 처리합니다.** AgentCore 런타임은 이미지 하나에 묶이고, 런타임을 만들거나 이미지를 바꿀 때마다 생성/업데이트가 끝나기를 기다려야 합니다. 이 스위트는 56개 태스크의 `environment/`가 모두 같아 이미지가 하나이므로 런타임도 하나(`harbor_rl_tasks`)입니다. 태스크별 차이(데이터 경로)는 세션 시작 후 healthcheck가 심볼릭 링크로 맞춥니다.

**태스크가 많아질 때(내용 해시 기반 중복 제거).** 태스크마다 런타임을 만들면 런타임 수와 생성 대기 시간이 태스크 수에 비례해 늘어납니다. 대신 태스크 환경을 내용 해시로 묶어 같은 이미지를 쓰는 태스크는 런타임 하나를 공유하게 합니다. Harbor도 환경 디렉터리의 SHA-256 해시(`environment_content_hash`)를 계산하므로 이 값을 그룹 키로 쓸 수 있습니다. 오픈소스 프로젝트 `harbor-on-agentcore`는 이 방식으로 대규모 태스크 세트를 훨씬 적은 수의 런타임에 수용했다고 보고합니다 [documented]. 이 가이드의 스위트에서는 그룹이 하나뿐이므로 별도 구현은 넣지 않았습니다.

### 5.2 E2B: amd64 + 사전 빌드한 템플릿

Harbor의 E2B 환경(`harbor/environments/e2b.py`, Harbor 0.23.0)은 태스크마다 템플릿 alias `{태스크 short name}__{environment/ 디렉터리 해시 앞 12자}`를 계산합니다. alias가 없으면 `Template().from_image(image)`(레지스트리 자격 증명 없음) 또는 `from_dockerfile`로 직접 빌드하는데, 태스크 Dockerfile이 `FROM ${BASE_IMAGE}`(프라이빗 ECR)라 이 경로로는 이미지를 받을 수 없습니다.

그래서 [`bench/prebuild_e2b_templates.py`](../../bench/prebuild_e2b_templates.py)가 Harbor의 E2B 환경 객체를 실제로 만들어 Harbor와 같은 코드로 alias, CPU, 메모리를 얻은 뒤, ECR 이미지 인덱스의 amd64 variant로 템플릿을 미리 빌드합니다. 템플릿 start command는 워밍업 스크립트(4.2절)이고, 끝나면 만드는 표시 파일로 준비를 확인합니다.

```python
# bench/prebuild_e2b_templates.py:48-52, 67-68
WARMUP_START_CMD = (
    f"echo {base64.b64encode(WARMUP_SCRIPT.read_bytes()).decode()} | base64 -d | sh; touch {WARMUP_DONE}"
)
# ecr_password(): password part of the base64-decoded ECR authorization token (valid 12 h)
template = Template().from_image(image, username="AWS", password=password).set_start_cmd(
    WARMUP_START_CMD, f"test -f {WARMUP_DONE}")
await AsyncTemplate.build(template=template, alias=alias, cpu_count=cpus, memory_mb=mem)
```

- E2B에는 장기 액세스 키를 넘기지 않습니다. 빌드에 쓰이는 자격 증명은 12시간 유효한 ECR 인증 토큰(사용자 이름 `AWS`)뿐입니다. 이 토큰은 실행 주체의 ECR 권한을 그대로 가지므로, 스크립트는 `harbor-rl/tasks-base` 하나만 pull할 수 있는 Trainer Pod 역할(Kubernetes Job)로 실행합니다.
- 학습 시 Harbor는 alias가 이미 있으므로 수정되지 않은 E2B 환경 그대로 샌드박스를 만듭니다.
- 56개 태스크의 `environment/`가 같으므로 해시 12자는 모두 같고, alias는 태스크 이름으로만 구분됩니다(내용이 같은 템플릿 56개).
- 기본 병렬도는 8(`--parallel`)이고, 이미 있는 alias는 건너뜁니다. 이미지를 바꾼 뒤에는 `--force`로 다시 빌드합니다.
- 스크립트를 실행하는 주체(Trainer Pod)에는 `ecr:GetAuthorizationToken`과 `harbor-rl/tasks-base` 리포지토리 pull 권한이 필요합니다([`infra/iam/trainer-pod-policy.json`](../../infra/iam/trainer-pod-policy.json)).

셀프호스팅 E2B는 내부 ALB 뒤에 있어 HyperPod VPC(피어링)에서만 접근할 수 있으므로, 사전 빌드는 클러스터 안의 Job으로 실행합니다. Trainer 이미지에 `bench/`와 `tasks/`가 들어 있습니다(`TAG`는 Trainer 이미지 태그, `04-grpo-training.md` 3절).

> 이 절과 5.3절의 Job 명령은 여기서 바로 실행하지 않습니다. Trainer 이미지([`04-grpo-training.md`](04-grpo-training.md) 3절), 학습 Pod 권한과 Secret([`01-hyperpod-eks.md`](01-hyperpod-eks.md) 6절), 배포된 샌드박스([`03a-sandbox-e2b.md`](03a-sandbox-e2b.md), [`03b-sandbox-agentcore.md`](03b-sandbox-agentcore.md))가 필요하므로, 실제 실행은 03a, 03b의 해당 단계에서 합니다.

```bash
export REGISTRY=<ACCOUNT_ID>.dkr.ecr.us-west-2.amazonaws.com
TAG=v12 ./infra/k8s/submit.sh e2b-prebuild 0 \
  python3 bench/prebuild_e2b_templates.py --image $REGISTRY/harbor-rl/tasks-base:v2
kubectl -n harbor-rl logs -f job/e2b-prebuild     # last line: "templates: 56 ok, 0 failed"
```

E2B Cloud를 쓰는 경우에도 같은 Job으로 실행합니다. 더 넓은 ECR 권한을 가진 로컬 자격 증명으로 실행하면 그 권한의 토큰이 E2B 템플릿 빌더로 넘어가므로 그렇게 하지 마세요.

### 5.3 태스크 유효성 확인 (oracle)

두 샌드박스에서 모든 태스크의 oracle(`solution/solve.sh`)을 학습과 같은 하네스로 실행해, 환경, 데이터, verifier가 각 아키텍처에서 동작하는지 확인합니다([`bench/oracle_check.py`](../../bench/oracle_check.py)).

```bash
TAG=v12 ./infra/k8s/submit.sh oracle-e2b 0 python3 bench/oracle_check.py --sandbox e2b --out /results/oracle
TAG=v12 AGENTCORE_RUNTIME_ARN=arn:aws:bedrock-agentcore:us-west-2:<ACCOUNT_ID>:runtime/<RUNTIME_ID> \
  ./infra/k8s/submit.sh oracle-agentcore 0 python3 bench/oracle_check.py --sandbox agentcore --out /results/oracle
```

통과 수와 태스크당 소요 시간(arm64 이식 비용)은 `05-comparison.md` 1절에 있습니다.

## 6. arm64 주의 사항

- **패키지 wheel:** 다른 태스크 스위트로 확장할 때는 aarch64 wheel이 없어 소스 빌드가 필요한 패키지가 있는지 먼저 확인하세요. 이 스위트는 같은 `requirements.txt`로 두 아키텍처 빌드가 모두 성공합니다.
- **numpy와 OpenBLAS:** `harbor-on-agentcore`는 arm64에서 `import numpy`가 SIGILL로 종료되어 `OPENBLAS_CORETYPE`을 설정했다고 보고합니다. 이 이미지의 고정 버전에서는 설정 없이 동작하므로 아무것도 추가하지 않았습니다. 버전을 바꾸면 arm64에서 `python3 -c "import numpy"`를 먼저 확인하세요.
- **V2 스냅샷 기동:** AgentCore V2 세션은 초기화 시점의 스냅샷에서 시작하므로 그 시점의 난수 시드, uuid, 시간 관련 상태가 세션 사이에 복제됩니다. 이 태스크들은 데이터를 결정적으로 읽기만 하므로 영향이 없지만, 시드에 의존하는 태스크는 세션 시작 후 시드를 다시 잡아야 합니다.
- **첫 import 지연:** 워밍업(4.2절)으로 라이브러리를 스냅샷에 담아도, 새 세션에서 pandas 같은 무거운 패키지를 처음 import하는 명령은 같은 세션의 두 번째보다 느립니다. AgentCore에서는 일부 세션에 수십 초의 꼬리가 있었습니다. 측정값은 `05-comparison.md` 2절에 있습니다.
- **메모리 조건:** `memory_mb=4096`은 E2B 템플릿에만 적용되고 AgentCore 세션은 8 GB 고정입니다. 데이터셋이 20 MB 이하라 영향은 작지만 비교 조건 차이로 `05-comparison.md`에 명시합니다.

## 7. 자주 겪는 문제 (Common pitfalls)

| 증상 | 원인 | 대응 |
|---|---|---|
| 데이터셋, 버킷 조회가 rate limit으로 실패 | 익명 Hugging Face 접근 rate limit | `HF_TOKEN`을 환경 변수로 설정하고 실행 |
| `build-push.sh`가 `set TAG`로 즉시 종료 | 이미지 스크립트는 `TAG` 기본값이 없음 | `TAG=v2 ./tasks/image/build-push.sh` |
| amd64 이미지로 AgentCore 런타임을 만들려 함 | AgentCore Runtime은 arm64만 지원 [documented] | 인덱스의 arm64 variant 사용, AgentCore 이미지는 `--platform linux/arm64`로 빌드 |
| AgentCore 런타임 생성 후 세션이 시작되지 않음 | 베이스 이미지만으로는 `/ping`, `/invocations` 계약을 만족하지 않음 | shim 레이어를 추가한 `tasks-agentcore` 이미지 사용(`ENTRYPOINT agentcore-shim`) |
| 모든 롤아웃이 `network_mode='no-network' is not supported by ...`로 실패 | 환경이 인터넷 차단 지원을 선언하지 않아 Harbor가 태스크를 거부 | AgentCore: 런타임을 격리 VPC 모드로 배포하고 `AGENTCORE_NETWORK_ISOLATED=1`(`submit.sh` 기본값). 다른 provider: 인터넷 차단을 지원하는지 확인 |
| Harbor가 E2B 템플릿을 직접 빌드하다 `FROM ${BASE_IMAGE}`에서 실패 | Harbor E2B 환경은 프라이빗 레지스트리 자격 증명을 넘기지 않음 | 학습 전에 `prebuild_e2b_templates.py`로 같은 alias를 미리 생성 |
| 사전 빌드했는데 학습 시 템플릿을 또 빌드하려 함 | alias에 `environment/` 내용 해시가 들어가므로 태스크 Dockerfile을 바꾸면 alias가 바뀜 | `environment/`를 바꾼 뒤에는 사전 빌드를 다시 실행 |
| 다이제스트로 고정한 베이스 이미지가 레지스트리에서 사라졌거나 보안 패치가 필요함 | 다이제스트 고정은 태그가 다른 이미지를 가리키게 되어도 같은 이미지를 받음 | 새 다이제스트를 확인(`finch image inspect` 또는 `docker buildx imagetools inspect`)해 `tasks/image/Dockerfile`의 `FROM`을 바꾸고 새 태그로 빌드 |
| 업스트림 데이터셋을 갱신했는데 선택 결과가 그대로 | 데이터셋 리비전이 `select_tasks.py`와 `suite.json`에 고정됨 | 의도적으로 갱신할 때만 `TRAIN_REVISION`, `RANKED_REVISION`을 바꾸고 스위트를 다시 생성 |
| 이미지를 다시 푸시했는데 E2B 샌드박스가 예전 내용 | 이미 있는 alias는 건너뜀 | `--force`로 다시 빌드 |
| 셀프호스팅 E2B에서 샌드박스 생성이 `404: method not allowed` | E2B SDK 2.51.0은 `POST /v2/sandboxes`를 쓰지만 이 가이드의 셀프호스팅 E2B API는 지원하지 않음(템플릿 빌드 API는 영향 없음) | Trainer 이미지에서 `e2b==2.50.0` 고정 |
| 셀프호스팅 E2B에서 `400: Timeout cannot be greater than 1 hours` | 기본 팀 티어가 1시간 / 동시 20개. Harbor는 24시간 타임아웃으로 생성 | 팀 티어 조정(`03a-sandbox-e2b.md`의 `finalize.sh`) |
| 노트북에서 셀프호스팅 E2B에 접근할 수 없음 | 내부 ALB, 이름이 사설 IP로만 해석됨 | 사전 빌드와 oracle 확인은 클러스터 Job으로 실행 |
| AgentCore에서 `cat`, 인자 없는 `python3`이 타임아웃까지 멈춤 | `InvokeAgentRuntimeCommand`가 EOF가 오지 않는 stdin 파이프를 넘김 | AgentCore 환경이 모든 명령 앞에 `exec </dev/null;`을 붙이고 `/bin/bash -c`로 감쌈 |
| `task.toml`의 `ATOL`/`RTOL`을 바꿔도 채점이 그대로 | 업스트림 `grader.py`는 이 값을 읽지 않고 고정 허용 오차를 사용 | 허용 오차를 바꾸려면 grader를 수정 |

근거 URL과 확인 날짜는 `references.md`에 있습니다.

다음 단계: `03a-sandbox-e2b.md`, `03b-sandbox-agentcore.md`
