[English](../05-comparison.md)

# 05. 측정 기반 비교: E2B sandbox vs AgentCore Runtime

이 문서의 모든 숫자에는 출처 태그가 붙어 있습니다.

- **[measured]**: 이 가이드의 실험에서 측정한 값. 원본은 `results/`에 있습니다.
- **[documented]**: 공식 문서나 가격표의 값. 출처와 확인 날짜는 [`references.md`](references.md)에 있습니다.
- **[estimated]**: 측정값과 문서값으로 계산한 값. 공식은 표 옆이나 `results/summary/cost.csv`의 `formula` 열에 있습니다.

표와 차트는 `bench/analyze.py`와 `bench/cost_model.py`로 `results/`에서 다시 만들 수 있습니다. 측정일은 2026-10-07입니다.

## 0. 비교 조건

두 샌드박스 모두 같은 조건에서 측정했습니다.

- 같은 HyperPod 노드(`ml.p4d.24xlarge` 1대)의 같은 Trainer 이미지(태그 `v12`)에서 실행
- 같은 태스크 56개(학습 40, held-out 16), 같은 모델(`google/gemma-4-E4B-it`), 같은 학습 설정(`04-grpo-training.md`)
- 같은 네트워크 정책: 모든 태스크가 `network_mode = "no-network"`. 샌드박스 안의 코드는 인터넷에 나갈 수 없습니다(`02-tasks-and-images.md` 3.1).
- 같은 샌드박스 워밍업: [`tasks/image/warmup.sh`](../../tasks/image/warmup.sh)(태스크 라이브러리 import와 `/data` 읽기)가 두 샌드박스 모두에서 스냅샷 전에 한 번 실행됩니다. AgentCore는 shim이 컨테이너 시작 시, E2B는 템플릿 start command로 실행합니다(`02-tasks-and-images.md` 4.2).
- 학습 Pod에서 샌드박스 API까지 둘 다 사설 경로: E2B는 VPC 피어링 + 내부 ALB, AgentCore는 데이터 플레인 인터페이스 VPC 엔드포인트(PrivateLink, `com.amazonaws.us-west-2.bedrock-agentcore`)

| 항목 | E2B sandbox (방법 A) | AgentCore Runtime (방법 B) |
|---|---|---|
| 배포 형태 | 같은 계정, 같은 리전에 배포한 셀프호스팅 E2B(`aws-samples/sample-e2b-on-aws`). E2B Cloud는 측정하지 않고 문서값으로만 비교 | 관리형 서비스, Runtime V2 |
| 네트워크 | 내부 ALB + VPC 피어링(사설 경로). 샌드박스 이그레스는 E2B가 차단 | 데이터 플레인 PrivateLink(프라이빗 DNS, 사설 경로). 세션은 VPC 모드, 인터넷 경로가 없는 격리 서브넷 |
| 샌드박스 하드웨어 | 전용 `c8i.metal-48xl` 1대(측정 기간 동안 이 실험만 사용) | 다중 테넌트 관리형 microVM |
| 세션 크기 | 2 vCPU / 4 GiB (태스크 설정) | 2 vCPU / 8 GB (고정) |
| 이미지 | 같은 이미지의 amd64 변형 | 같은 이미지의 arm64 변형 + shim 레이어 |
| 워밍업 시점 | 템플릿 빌드 때 start command로 실행, 끝난 뒤 템플릿 스냅샷 | 컨테이너 시작 때 shim이 실행(최대 90초), 끝난 뒤 8080을 열고 첫 healthy `/ping` 뒤 V2 스냅샷 |
| Harbor 환경 | Harbor 내장 `e2b` 환경 그대로 | 이 가이드의 `AgentCoreEnvironment` |

**한쪽에만 적용한 설정** (공정성을 위해 모두 밝힘):

- **E2B만**
  - `e2b==2.50.0` 고정: 2.51.0은 이 셀프호스팅 서버 버전이 제공하지 않는 API로 샌드박스를 만듭니다.
  - 팀 티어 상향(세션 24시간, 동시 1,000): Harbor가 24시간 타임아웃으로 샌드박스를 만들고 벤치마크가 128개를 동시에 띄우기 때문입니다. 샘플 기본값은 1시간 / 20입니다.
- **AgentCore만**
  - 명령 앞에 `exec </dev/null;`: AgentCore는 stdin에 닫히지 않는 파이프를 넘기므로, 이것이 없으면 stdin을 읽는 명령이 멈춥니다(Docker/E2B와 동작을 맞춤).
  - 디렉터리 전송을 tar.gz 한 번으로 처리: Harbor의 E2B 환경은 업로드를 배치로, 다운로드를 파일 하나씩 합니다. 각 구현을 있는 그대로 측정했습니다.

**결과를 읽을 때 기억할 점**

- 지연 차이에는 샌드박스 기술의 차이와 배포 형태의 차이(전용 bare metal 대 다중 테넌트 관리형 서비스)가 함께 들어 있습니다. 네트워크 경로는 둘 다 사설입니다.
- E2B Cloud(인터넷 경유)의 지연은 측정하지 않았으므로, 셀프호스팅 결과를 E2B Cloud에 그대로 옮기면 안 됩니다.

## 1. 태스크 유효성 (arm64 포팅 비용)

| 샌드박스 | 오라클 통과 | 태스크당 중앙 소요 | 출처 |
|---|---|---|---|
| E2B (amd64) | 56/56 [measured] | 3.00초 [measured] | `results/oracle/oracle_e2b_20261007-083831.csv` |
| AgentCore (arm64) | 56/56 [measured] | 4.16초 [measured] | `results/oracle/oracle_agentcore_20261007-084123.csv` |

- 이 스위트에서 arm64 때문에 잃은 태스크는 없습니다.
- 포팅 비용은 준비 단계에 있습니다. 원본 데이터셋 이미지가 amd64 전용이라 이미지 레시피를 다시 만들어 amd64 + arm64로 빌드했고, AgentCore용 shim 레이어를 더했습니다(`02-tasks-and-images.md`). 원본 이미지를 그대로 쓰는 공개 데이터셋이라면 이 재빌드 비용이 이미지 수만큼 커집니다.

## 2. 샌드박스 마이크로벤치마크

같은 스크립트(`bench/sandbox_bench.py`)와 같은 파라미터로, 노드에 다른 작업이 없을 때 하나씩 실행했습니다.

**단일 세션 지연 (30 세션, exec는 600회)** [measured], `results/summary/bench_latency.csv`, `results/charts/bench_latency.png`

| 작업 | E2B p50 / p95 | AgentCore p50 / p95 | 배수 (p50) |
|---|---|---|---|
| 세션 시작 | 87 / 194 ms | 1,820 / 2,283 ms | 21x |
| 첫 Python import (`python3 -c 'import pandas, numpy, sklearn'`, 새 세션의 첫 명령) | 862 / 927 ms | 2,610 / 46,619 ms | 3.0x |
| 같은 import 두 번째 | 737 / 781 ms | 1,201 / 1,577 ms | 1.6x |
| exec 왕복 (`true`) | 8.6 / 9.7 ms | 140 / 191 ms | 16x |
| 1 MB 업로드 | 8.6 / 11.2 ms | 143 / 184 ms | 17x |
| 1 MB 다운로드 | 25.0 / 28.2 ms | 361 / 375 ms | 14x |
| 8 MB 업로드 | 33.1 / 37.9 ms | 5,702 / 5,763 ms | 172x |
| 8 MB 다운로드 | 160 / 189 ms | 5,539 / 5,604 ms | 35x |
| 세션 종료 | 28.3 / 54.3 ms | 188 / 263 ms | 6.6x |

**동시성 스윕 (각 세션 시작 + exec 10회)** [measured], `results/summary/bench_concurrency.csv`, `results/charts/bench_concurrency.png`

| 동시 세션 | E2B 시작 p50 / p95 | AgentCore 시작 p50 / p95 | E2B exec/s | AgentCore exec/s | 오류, 스로틀 |
|---|---|---|---|---|---|
| 8 | 167 / 227 ms | 2,082 / 2,422 ms | 212 | 16 | 둘 다 0 |
| 32 | 440 / 815 ms | 2,413 / 2,857 ms | 315 | 60 | 둘 다 0 |
| 128 | 1,935 / 3,344 ms | 4,472 / 5,084 ms | 341 | 161 | 둘 다 0 |

해석:

- **E2B:** 단건 지연이 모든 항목에서 빠릅니다. 대부분 한 자릿수에서 두 자릿수 배이고, CPU가 일하는 Python import에서는 차이가 1.6~3.0배로 줄어듭니다.
- **첫 Python import의 분포.** E2B는 30세션 중 29세션이 0.84~0.93초, 한 세션만 3.2초였습니다. AgentCore는 19세션이 1.7~2.7초였지만 나머지는 3.5초에서 약 57초까지 긴 꼬리가 있어 p95가 46.6초입니다 [measured]. 같은 세션의 두 번째 import는 AgentCore도 p95 1.6초로 안정적이므로, 꼬리는 세션의 첫 import에만 나타납니다. 원인은 이 측정만으로는 가릴 수 없습니다.
- **AgentCore 동시성:** 128 동시에서도 오류와 스로틀이 없었습니다. 세션 시작 p50은 8 동시 2.1초에서 128 동시 4.5초로 늘어납니다. 신규 세션 생성 쿼터 25 TPS [documented]의 영향으로 보입니다.
- **AgentCore 파일 전송:** 8 MB 전송이 5.5~5.7초로, 크기에 비례하지 않게 느립니다. 큰 파일은 S3를 경유하는 것이 좋습니다.
- **E2B 128 동시:** 4 GiB × 128 = 512 GiB로 노드 물리 메모리(384 GiB, 192 vCPU [documented])보다 크지만 실패 없이 떴습니다. Firecracker는 메모리를 실제 사용분만큼만 잡기 때문으로 보입니다.
- **"25 TPS" 문구:** 실행 명령 문서의 "25 TPS"는 `InvokeAgentRuntimeCommand`에 적용되지 않았습니다. 128 동시에서 초당 161 명령, 학습 전체에서 명령 31,672건(분당 최대 380건) 동안 스로틀 0이었습니다 [measured]. 명령에는 데이터 플레인 1,000 TPS 쿼터 [documented]가 맞습니다.

## 3. GRPO 학습 (같은 설정, 40 스텝)

설정: seed 42, 스텝당 48 롤아웃(6 프롬프트 × 8 생성), `max_completion_length` 8192, `max_tool_calling_iterations` 20, temperature 1.0, lr 2e-6. 학습 전후에 held-out 16 태스크 × 6 샘플을 평가합니다.

출처: `results/summary/training_runs.csv`, `training_steps.csv`, `training_sandbox_ops.csv`, `training_sandbox_sessions.csv`, `results/charts/training.png`

| 지표 | E2B | AgentCore |
|---|---|---|
| 40 스텝 학습 시간 | 8,660초 (2.41 h) [measured] | 16,524초 (4.59 h) [measured] |
| 평가 포함 전체 실행 시간 | 2.65 h [measured] | 5.05 h [measured] |
| 평균 스텝 시간 | 216초 [measured] | 413초 [measured] |
| ├ 생성(vLLM 대기) | 88초 [measured] | 98초 [measured] |
| ├ 샌드박스 대기 합계 | 35.5초 [measured] | 112.3초 [measured] |
| │ ├ 그중 프로비저닝 | 19.4초 [measured] | 18.1초 [measured] |
| │ ├ 그중 exec(도구 호출) | 15.1초 [measured] | 83.0초 [measured] |
| │ └ 그중 verifier | 0.7초 [measured] | 9.8초 [measured] |
| └ 학습(backward 등)과 다른 랭크 대기 | 93초 [measured] | 203초 [measured] |
| 스텝 시간 중 샌드박스 대기 비중 | 17.0% [measured] | 27.5% [measured] |
| 스텝당 exec 호출 수(6 랭크 합계) | 263 [measured] | 339 [measured] |
| 롤아웃 / 실패 롤아웃 | 1,920 / 0 [measured] | 1,920 / 0 [measured] |
| 롤아웃당 도구 호출(exec) 수, 학습 전 평가 → 마지막 10 스텝 | 6.19 → 5.28 [measured] | 6.21 → 6.90 [measured] |
| 학습 보상, 처음 5 스텝 → 마지막 5 스텝 | 0.375 → 0.417 [measured] | 0.321 → 0.404 [measured] |
| held-out 해결률, 학습 전 → 후 | 33.3% → 33.3% [measured] | 34.4% → 38.5% [measured] |

**학습 안의 샌드박스 호출 지연 (p50)** [measured], `training_sandbox_ops.csv`

| 호출 | E2B | AgentCore |
|---|---|---|
| 프로비저닝 전체(생성, 시작, 헬스체크, 준비) | 2,221 ms | 2,202 ms |
| exec (모델의 도구 호출) | 14 ms | 200 ms |
| verifier | 84 ms | 1,149 ms |
| stop | 29 ms | 170 ms |

해석:

- **샌드박스 지연이 학습 시간을 바꿉니다.** E2B 쪽 스텝이 평균 197초 짧았습니다(48%). 그중 77초는 각 랭크의 샌드박스 대기 차이, 110초는 "학습과 다른 랭크 대기" 차이, 10초는 생성 시간 차이입니다 [measured]. 랭크들은 동기화 지점에서 가장 느린 랭크를 기다리므로, 한 랭크의 샌드박스 지연이 다른 랭크의 대기 시간으로도 나타납니다.
- **프로비저닝은 비슷합니다.** 마이크로벤치에서는 E2B 세션 시작이 87 ms였지만, Harbor의 E2B 환경을 거치면 p50 2.2초가 됩니다(Harbor `start()`의 템플릿 확인 등 추가 API 호출로 보임). 학습에서 세션은 랭크마다 순차로 만들어지므로 스텝당 약 18~19초가 두 샌드박스 모두에 듭니다.
- **순차 프로비저닝의 비용.** 프로비저닝은 스텝 시간의 9.0%(E2B), 4.4%(AgentCore)입니다 [measured]. 랭크마다 8개 세션을 하나씩 만들기 때문입니다. 8개를 동시에 만들면 랭크당 대기가 세션 1개 수준(p95 E2B 4.2초, AgentCore 2.9초)으로 줄어 스텝당 약 15초를 아낄 수 있습니다 [estimated: 19.4 - 4.2, 18.1 - 2.9]. 두 샌드박스 모두에 비슷하게 작은 영향입니다.
- **워밍업 뒤의 첫 Python 명령.** 롤아웃에서 처음 실행한 Python 명령의 소요는 p50 E2B 0.32초, AgentCore 1.19초, 평균 0.43초, 4.48초였습니다 [measured]. 평균이 p50보다 훨씬 큰 것은 2절의 첫 import 꼬리와 같은 모양입니다.
- **도구 호출 수는 학습 중에 갈라졌습니다.** 학습 전 평가에서는 롤아웃당 exec 수가 같았습니다(6.19 대 6.21). 학습이 진행되면서 AgentCore 실행의 정책이 더 많이 호출했습니다(처음 10 스텝 6.69 대 5.85, 마지막 10 스텝 6.90 대 5.28, 학습 후 평가 6.64 대 5.27) [measured]. 학습 전체 exec 호출은 AgentCore 14,776건, E2B 11,609건입니다. 따라서 AgentCore 쪽 샌드박스 대기에는 호출당 지연과 호출 수 차이가 함께 들어 있습니다. 실행이 각 1회이고 샘플링이 확률적이므로, 이 행동 차이가 샌드박스 때문인지는 이 실험으로 판단할 수 없습니다.
- **오래 걸린 exec (60초 이상).** 모델이 `pip install`을 시도하면 E2B에서는 DNS 해석이 실패해 약 148초 뒤에 끝나고, AgentCore 격리 VPC에서는 DNS는 되지만 연결이 시간 초과되어 도구 타임아웃 180초까지 기다립니다. AgentCore에서는 9건 모두 `pip install`이 180초 타임아웃에 걸렸습니다. E2B에서는 6건으로, 5건은 `pip install`(약 148초에 종료), 1건은 `head ... && tail -f ...` 명령이 180초 타임아웃에 걸렸습니다 [measured]. 이 1건이 두 실행을 통틀어 유일하게 실패한 exec 호출이며, 롤아웃은 실패하지 않았습니다.
- **학습 효과는 결론 보류입니다.** held-out 변화는 E2B +0.0%p, AgentCore +4.2%p입니다. 96 샘플 평균의 표준오차는 약 4.8%p입니다 [estimated: √(0.35 × 0.65 / 96)]. 실행이 각 1회뿐이고 학습 전 값도 다르므로, 이 차이를 샌드박스의 영향으로 해석할 수 없습니다. 이 실험이 보여 주는 것은 두 샌드박스 모두에서 같은 학습이 실패 없이 끝났다는 점입니다.

## 4. 비용

가격은 us-west-2 온디맨드 정가입니다 [documented]. 계산은 `bench/cost_model.py`, 결과는 `results/summary/cost.csv`에 있습니다.

### 4.1 샌드박스 비용 (학습 1회, 평가 포함 2,112 세션)

| 항목 | AgentCore | 셀프호스팅 E2B (전용) | E2B Cloud (가정) |
|---|---|---|---|
| 과금 기준 | 사용한 vCPU-h, 사용한 GB-h, VPC 엔드포인트 | 인스턴스 시간(사용 여부 무관) | 할당 vCPU, GiB × 실행 시간 |
| 1회 비용 | **$6.09** [estimated] | $29.43 [estimated] | $20.25 [estimated] |
| 1,000 롤아웃당 | **$2.89** [estimated] | $13.94 [estimated] | $9.59 [estimated] |

각 금액의 계산식:

- **AgentCore:** CloudWatch 사용량 × 단가 + VPC 엔드포인트. 5.66 vCPU-h × $0.1276 + 294.0 GB-h × $0.0169 + $0.08/h × 5.05 h = $6.09. 사용량과 세션 수(2,112), 명령 수(31,672), 스로틀(0)은 [measured]이고 출처는 `results/usage/agentcore_grpo_window.json`, 단가는 [documented]입니다. VPC 엔드포인트 항목은 인터페이스 엔드포인트 4개 × 2 AZ × $0.01/h입니다: VPC 모드 세션에 필요한 3개(ECR api, ECR dkr, Logs)와 학습 Pod의 사설 경로인 데이터 플레인 PrivateLink 엔드포인트(`bedrock-agentcore`)입니다(E2B 쪽의 해당 경로인 내부 ALB는 고정비에 포함).
- **셀프호스팅 E2B:** 시간당 고정비 × 실행 시간. $11.11/h × 2.65 h = $29.43. 고정비 내역:
  - `c8i.metal-48xl` $9.00
  - t3.xlarge 5대(Nomad 서버 3, API 2) $0.83
  - `m8i.4xlarge`(템플릿 빌드) $0.85
  - 배스천 $0.18
  - NAT, ALB, Aurora, ElastiCache 최소 요금
- **E2B Cloud:** 실제로 돌리지 않았습니다. 측정한 E2B 세션 시간 122.3 h [measured]에 E2B Cloud 단가를 곱했습니다. 122.3 h × (2 × $0.000014 + 4 × $0.0000045) × 3600 = $20.25.

### 4.2 사용률이 비용을 가른다

| 지표 | 값 |
|---|---|
| AgentCore 세션 CPU 사용률 | 1.20% [measured]: 5.66 사용 vCPU-h / (235.4 세션-h × 2 vCPU) |
| AgentCore 세션당 평균 메모리 사용량 | 1.25 GB [measured]: 294.0 GB-h / 235.4 세션-h |
| E2B 클라이언트 노드 CPU 사용률 | 0.70% [measured]: CloudWatch, 학습 구간 5분 평균(`results/usage/e2b_client_cpu.json`, `bench/e2b_client_cpu.py`로 생성) |
| 학습 중 평균 동시 세션 | 46 [measured]: 122.3 세션-h / 2.65 h (6 랭크 × 8 생성) |
| 셀프호스팅 E2B의 샌드박스 비용이 AgentCore와 같아지는 평균 동시 세션 | 약 430 [estimated]: $11.11/h ÷ ($6.09 / 235.4 세션-h) |

데이터 분석 태스크는 대부분의 시간을 모델 생성 대기로 보내므로 샌드박스 CPU는 거의 놉니다.

- **AgentCore:** 쓴 CPU와 메모리만 과금되므로 이 패턴에서 샌드박스 비용이 가장 낮습니다.
- **셀프호스팅 E2B:** 노드를 계속 채울 수 있는 규모(이 구성에서 평균 약 430 동시 세션 이상)가 아니면 샌드박스 비용만으로는 비쌉니다.

### 4.3 손익분기 CPU 사용률 (AgentCore vs E2B Cloud)

![break-even](../../results/charts/break_even.png)

샌드박스 1시간당 비용 [estimated]:

- **AgentCore:** `2 vCPU × u × $0.1276 + 메모리 사용량(GB) × $0.0169`. 메모리는 고정 할당 8 GB가 아니라 사용량으로 과금되는 것으로 계산했습니다(CloudWatch `MemoryUsed-GBHours`). VPC 엔드포인트 고정비는 세션 수에 따라 나뉘므로 이 차트에는 넣지 않았습니다.
- **E2B Cloud:** 할당량 기준이라 사용률과 무관하게 $0.1656입니다.

| AgentCore 세션 메모리 사용량 | 손익분기 CPU 사용률 u |
|---|---|
| 1.25 GB (이 실험 측정) | 57% [estimated] = (0.1656 - 1.25 × 0.0169) / 0.2552 |
| 4.29 GB (E2B 할당 4 GiB와 같게 쓸 때) | 36% [estimated] |
| 8 GB (고정 할당을 다 쓸 때) | 12% [estimated] |

이 실험의 측정 사용률은 1.20%로, 어느 경우에도 손익분기보다 한참 아래입니다.

### 4.4 전체 학습 비용에서 샌드박스 비중

| 항목 | AgentCore | 셀프호스팅 E2B (전용) |
|---|---|---|
| GPU (HyperPod `ml.p4d.24xlarge` $25.91/h [documented] × 실행 시간) | $130.89 [estimated] (5.05 h) | $68.67 [estimated] (2.65 h) |
| 샌드박스 | $6.09 [estimated] | $29.43 [estimated] |
| 합계 | $136.98 [estimated] | **$98.10** [estimated] |
| 샌드박스 비중 | 4.4% [estimated] | 30.0% [estimated] |

GPU 비용이 훨씬 크기 때문에, 이 실험에서 실제로 비용을 가른 것은 샌드박스 요금이 아니라 **샌드박스 지연이 늘린 GPU 시간**이었습니다.

- **AgentCore:** 샌드박스 요금은 $23.34 쌌지만, 실행이 2.40 h 길어져 GPU 비용이 $62.22 더 들었습니다. 합계는 셀프호스팅 E2B가 28% 낮습니다 [estimated: 1 - 98.10 / 136.98].
- **셀프호스팅 E2B 노드를 공유할 때:** 노드를 다른 실험과 나눠 쓰면 E2B 쪽 샌드박스 비용은 더 내려갑니다.
- **E2B Cloud:** 지연(인터넷 경유)을 측정하지 않았으므로 전체 비용 비교에 넣지 않았습니다.

판단 기준:

- **GPU 시간 단가 × 샌드박스 대기 비중**이 크면 지연이 짧은 쪽이 유리합니다.
- **샌드박스 수 × 유휴 시간**이 크면 사용량 과금이 유리합니다.

## 5. 구축 노력

| 항목 | E2B (셀프호스팅) | AgentCore |
|---|---|---|
| 새로 쓴 코드 | 배포와 운영 스크립트(`infra/e2b-selfhosted/`), 템플릿 사전 빌드(`bench/prebuild_e2b_templates.py`, 워밍업 start command 포함) | 환경 클래스(`agentcore/harbor_agentcore/environment.py`), shim(`agentcore/shim/main.go`, 워밍업 포함), 이미지와 네트워크/배포 스크립트 |
| Harbor 연동 | 내장 `e2b` 환경 그대로 | `BaseEnvironment` 직접 구현. 공식 provider 없음(Harbor 이슈 #3446) |
| 인프라 | VPC, Nomad 서버 3, API 2, bare metal 클라이언트, 빌드 노드, Aurora, Redis, ALB, ACM, 도메인, VPC 피어링 | 런타임 1개, 실행 역할 1개, 격리 서브넷 2개와 VPC 엔드포인트 5개(인터페이스 4: ECR api, ECR dkr, Logs, bedrock-agentcore. S3 게이트웨이 1) |
| 셋업 시간 | 스택 + 배포 체인 약 1~1.5 h [estimated] | 이미지 빌드 후 런타임 생성 수 분 [estimated] |
| 운영 부담 | 노드 패치, 용량 계획, DB, 인증서, 업그레이드(SDK와 서버 버전 맞추기), 팀 키 관리 | 서비스 쿼터 관리 |
| 주의할 점 | 샘플 무인 배포 경로의 환경 문제(`deploy.sh`가 처리), 티어 기본값, SDK 버전 | stdin 파이프, `bash -c` 래핑, shim 계약(`/ping`), V2 스냅샷 상태 복제(워밍업은 파일 읽기만), VPC 모드의 S3 prefix list 이그레스 |

E2B Cloud를 쓰면 인프라 행이 "API 키 하나"로 줄어드는 대신, 데이터가 계정 밖으로 나가고 티어 한도가 적용됩니다.

## 6. 제약

| 항목 | E2B | AgentCore |
|---|---|---|
| 아키텍처 | x86_64 (셀프호스팅은 arm64 배포도 가능) | arm64만 [documented] |
| 세션 크기 | 템플릿별로 지정(이 가이드 2 vCPU / 4 GiB) | 2 vCPU / 8 GB 고정, 조정 불가 [documented]. 더 크게 하려면 Runtime Instances(EC2 기반: 세션당 인스턴스, EC2 과금, I/O 대기 무료 없음, 같은 인스턴스의 trial 간 격리 없음) |
| 이미지 크기 | 템플릿 디스크 한도 | 2 GB, 조정 불가 [documented] |
| 동시성 | Cloud: Hobby 20, Pro 100(애드온으로 1,100) [documented]. 셀프호스팅: 노드 용량과 티어 설정 | 활성 세션 5,000(us-west-2, 조정 가능) [documented] |
| 세션 수명 | Cloud: Hobby 1 h, Pro 24 h [documented]. 셀프호스팅: 티어 설정 | 최대 8 h, 유휴 15분(조정 가능) [documented] |
| 포크/스냅샷 | 일시 중지/재개, 스냅샷 [documented] | 세션 포크 없음 |
| 이그레스 제어 | 샌드박스 단위(`allow_internet_access`, 네트워크 allowlist) | 런타임 단위(VPC 모드와 서브넷 라우팅). 세션 단위 불가 |
| 관측성 | 셀프호스팅: EC2/Nomad 지표와 로그(직접 운영) | CloudWatch 제공 지표(호출, 스로틀, vCPU-h, GB-h). 4개 차원을 모두 지정해야 조회됨 |

## 7. 보안과 거버넌스

| 항목 | 셀프호스팅 E2B (이 가이드 구성) | E2B Cloud | AgentCore (이 가이드 구성) |
|---|---|---|---|
| 데이터 위치 | 내 계정 | E2B 인프라(계정 밖) | 내 계정 |
| 인증 | 팀 API 키. Secrets Manager에 보관, Kubernetes Secret으로 전달 | 팀 API 키 | IAM SigV4. Pod Identity 역할을 런타임 1개로 범위 제한 |
| 비밀 | 팀 API 키는 Secrets Manager. Kubernetes Secret은 server-side apply로 써서 `last-applied` 사본 없음. 템플릿 사전 빌드는 저장소 하나만 pull할 수 있는 12시간 ECR 토큰만 E2B에 전달 | 팀 API 키 | 샌드박스용 비밀 없음. Kubernetes Secret에는 `HF_TOKEN`만(server-side apply) |
| 네트워크 노출 | 내부 ALB, 두 VPC의 HTTPS만 허용(`peer.sh`가 0.0.0.0/0, `::/0` 규칙이 남지 않았는지 검증). 배스천 SSH 없음(SSM, 개인 키는 생성 직후 폐기) | 인터넷 | 학습 Pod는 HyperPod VPC 안의 `bedrock-agentcore` 인터페이스 엔드포인트(PrivateLink, 프라이빗 DNS)로 호출, IAM 인증 |
| 샌드박스 이그레스 | 차단(태스크 정책, E2B가 강제) | 샌드박스 단위 설정 | 차단(인터넷 경로 없는 격리 서브넷, VPC 엔드포인트만) |
| VPC 엔드포인트 정책 | 해당 없음 | 해당 없음 | 격리 라우트 테이블 전용 S3 게이트웨이 엔드포인트는 ECR 레이어 버킷(`prod-<region>-starport-layer-bucket`)의 `s3:GetObject`만 허용. ECR(api, dkr), Logs, `bedrock-agentcore` 인터페이스 엔드포인트는 이 계정 주체(`aws:PrincipalAccount`)만 허용해, 다른 계정 자격 증명으로 데이터를 내보내는 경로를 막음([`03b-sandbox-agentcore.md`](03b-sandbox-agentcore.md) 3.1절에서 검증) |
| 남은 이그레스 경로 | 샌드박스에서 외부 DNS 해석도 실패(`03a-sandbox-e2b.md` 3.7절) | 확인 안 함 | VPC 리졸버가 격리 서브넷에서도 공개 DNS 이름에 응답하므로 DNS 터널링은 가능. 민감 데이터라면 Route 53 Resolver DNS Firewall 필요(VPC 전체에 적용되므로 클러스터가 쓰는 이름의 허용 목록 필요). 이 가이드에서는 구성하지 않음 |
| 학습 쪽으로 돌아오는 경로 | E2B 쪽은 ALB 서브넷만 HyperPod VPC 경로를 가지며, HyperPod 노드 보안 그룹이 자기 구성원만 받으므로 E2B 호스트에서 HyperPod 노드나 Pod로 연결 불가 | 해당 없음 | 격리 라우트 테이블에는 피어링 경로가 없음 |
| 격리 | Firecracker microVM | Firecracker microVM | 세션별 microVM |
| 감사 로그 | 직접 구성: API 서버와 Nomad 로그. AWS API 호출이 아니므로 CloudTrail에 남지 않음 | E2B 제공 범위(이 가이드에서 확인 안 함) | 제어 플레인(`CreateAgentRuntime`, `UpdateAgentRuntime`)은 CloudTrail 이벤트 기록에 기본으로 남음. 데이터 플레인(`InvokeAgentRuntime`, `InvokeAgentRuntimeCommand`, `StopRuntimeSession`)은 기본 이벤트 기록에 없음 [measured]. 명령 단위 감사는 데이터 이벤트 구성을 별도로 검토 |
| 주의 | DB와 노드 운영, 키 교체가 내 책임. API 키는 IAM처럼 세분화되지 않음 | 데이터 반출 검토 필요 | 세션 안의 코드가 실행 역할 자격 증명을 읽을 수 있으므로 실행 역할은 최소 권한(이 가이드: 이미지 리포지토리 1개 pull과 이 런타임의 로그 그룹만) |

**위협 모델 참고** (두 샌드박스에 공통)

- 보상 무결성: 에이전트 명령은 root로 실행되고, verifier는 나중에 같은 샌드박스에서 실행됩니다. 따라서 정책이 원리적으로 verifier가 쓰는 파일이나 도구를 바꿔 자신의 보상을 올릴 수 있습니다. 이는 Harbor 설계의 성질이며 어느 샌드박스의 문제도 아닙니다. 신뢰할 수 없는 정책의 보상은 이 점을 감안해 해석하세요.
- 샌드박스 워밍업은 파일만 읽고 세션별 상태(난수, 시각, 자격 증명)를 만들지 않으므로, 스냅샷에서 복원된 세션끼리 공유해도 되는 내용만 스냅샷에 들어갑니다.
- 학습 Pod는 root로 실행되고 GPU 노드의 hostPath 볼륨(모델 캐시, 결과)을 씁니다. 이 워크로드 전용인 단일 테넌트 HyperPod 노드를 전제로 한 구성입니다. 노드를 다른 워크로드와 공유한다면 그대로 쓰지 마세요.
- 학습 Pod 안의 vLLM 서버는 `127.0.0.1`에만 바인드됩니다. dev 모드 서버가 가중치 업데이트와 RPC 경로를 인증 없이 열기 때문입니다.
- 입력은 고정되어 있습니다. 베이스 이미지는 다이제스트로, Trainer Python 패키지는 정확한 버전으로, Hugging Face 데이터셋은 리비전으로, 셀프호스팅 E2B 샘플은 전체 커밋 SHA로 고정합니다([`02-tasks-and-images.md`](02-tasks-and-images.md), [`04-grpo-training.md`](04-grpo-training.md)).

## 8. 가설 판정

| 가설 | 판정 | 근거 |
|---|---|---|
| AgentCore는 셀프호스팅 대비 운영할 인프라가 없음 | 확인 | 5절: 런타임 1개와 격리 네트워크 대 10여 종의 인프라 |
| E2B Cloud 대비 데이터가 계정 안에 있고 IAM, CloudTrail로 통제 | 부분 확인 | 데이터 위치와 IAM은 확인. CloudTrail은 제어 플레인만 기본 기록되고, 명령 실행은 기본 이벤트 기록에 없음 [measured]. 셀프호스팅 E2B도 계정 안에 있음 |
| 엔터프라이즈 계약 없이 높은 동시성 | 확인(128까지 측정) | 128 동시, 학습 2,112 세션과 명령 31,672건(분당 최대 380건)에서 스로틀 0 [measured]. 쿼터 5,000 [documented] |
| CPU 사용률이 낮으면(대략 40~50% 미만) 더 저렴 | 확인, 단 메모리 사용량에 따라 기준이 달라짐 | 손익분기 57%(메모리 1.25 GB), 36%(4.29 GB), 12%(8 GB) [estimated]. 측정 사용률 1.20% |
| 공개 amd64 데이터셋의 arm64 포팅 비용 | 부분 확인 | 재빌드한 스위트에서는 손실 0 [measured]. 원본 이미지가 amd64 전용이라 재빌드 자체가 비용 |
| 2 vCPU / 8 GB, 2 GB 이미지 고정 한도 | 확인(이 실험에서는 제약이 되지 않음) | [documented]. 측정 CPU 사용률 1.20%, 메모리 사용 1.25 GB |
| 실행 중간 상태에서 포크 불가 | 확인 | [documented] |
| 공식 Harbor provider 없음 | 확인 | Harbor 이슈 #3446 미해결. 직접 구현 필요 |
| 표준 GRPO에서 포크 없음은 약점이 아님 | 확인 | 같은 이미지에서 G개 세션으로 1,920 롤아웃 실패 0 [measured] |
| logprob 수집은 하네스 문제이지 샌드박스 문제가 아님 | 확인 | 두 샌드박스 모두 TRL이 Trainer 쪽에서 수집 |
| 이그레스 제어는 VPC 모드로 대부분 해결 | 확인, 단 런타임 단위 | 격리 VPC에서 외부 연결 실패, 데이터 접근 정상 [measured]. 세션 단위 제어는 불가 |
| 콜드 스타트가 AgentCore에 유리하다고 볼 근거 없음 | 확인 | 단건 시작 87 ms 대 1,820 ms [measured]. Harbor 경로의 프로비저닝은 2.2초 대 2.2초로 같은 수준 [measured]. 워밍업 뒤에도 새 세션의 첫 Python import는 p50 0.86초 대 2.61초, AgentCore p95 46.6초 [measured] |

## 9. 고객 의사결정 표

| 고객 상황 | 추천 | 이유 |
|---|---|---|
| 샌드박스 운영 인력이 없고 빨리 시작해야 함 | AgentCore | 런타임 1개, 쓴 만큼 과금, 실패와 스로틀 0 [measured] |
| 데이터 반출 불가, IAM으로 통제 | AgentCore 또는 셀프호스팅 E2B | 둘 다 계정 안, 둘 다 사설 경로. AgentCore는 IAM 네이티브 |
| GPU가 비싸고 롤아웃당 샌드박스 호출이 많음 | 셀프호스팅 E2B | 학습 시간 48% 단축 [measured], 전체 비용 28% 낮음 [estimated] |
| 샌드박스 사용이 들쭉날쭉하거나 실험이 간헐적 | AgentCore | 셀프호스팅은 유휴 시간에도 시간당 $11.11 [estimated] |
| 노드를 계속 채울 대규모 상시 학습 | 셀프호스팅 E2B | 평균 동시 세션 약 430 이상이면 샌드박스 비용도 역전 [estimated] |
| 2 vCPU / 8 GB를 넘는 샌드박스, x86 전용 바이너리 | E2B | AgentCore 세션 크기 고정, arm64만 |
| 큰 파일(수 MB 이상)을 자주 주고받음 | E2B, 또는 AgentCore + S3 경유 | AgentCore 8 MB 전송 5.5~5.7초 [measured] |
| 롤아웃 중간 상태 저장/포크(트리 탐색 등) | E2B | AgentCore 포크 없음 |
| 명령 단위 감사가 필수 | 어느 쪽이든 추가 구성 필요 | AgentCore 데이터 플레인은 CloudTrail 기본 기록에 없음, 셀프호스팅 E2B는 자체 로그 |

## 10. 한계

- 각 샌드박스로 학습을 1회씩만 실행했습니다. 스텝 시간 차이는 분명하지만, 학습 품질 차이와 롤아웃당 도구 호출 수 차이의 원인은 결론을 낼 수 없습니다.
- 셀프호스팅 E2B는 전용 bare metal 노드라는 유리한 조건이었습니다. 네트워크 경로는 둘 다 사설입니다. E2B Cloud의 지연은 측정하지 않았습니다.
- 비용은 정가 기준입니다. 할인, Savings Plans, 데이터 전송, CloudWatch 요금은 넣지 않았습니다.
- AgentCore 메모리 과금은 CloudWatch `MemoryUsed-GBHours` 기준으로 계산했고, 청구서와 대조하지는 않았습니다.
