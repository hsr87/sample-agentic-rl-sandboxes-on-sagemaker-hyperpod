[English](../06-cleanup.md)

# 06. 리소스 정리 (Cleanup)

이 문서는 가이드를 자신의 계정에서 따라 한 뒤 만든 리소스를 모두 지우는 절차입니다. 위에서 아래 순서대로 실행하면 의존성 오류 없이 정리됩니다. 리소스는 이름과 태그(`Project=harbor-rl-sandbox`)로 찾으므로, 가이드의 기본 이름을 바꾸지 않았다면 명령을 그대로 복사해 실행할 수 있습니다.

- 셀프호스팅 E2B를 배포하지 않았다면(E2B Cloud 사용) 2절 대신 2.7절만 실행합니다.
- 결과를 보관하려면 6절의 백업 명령을 먼저 실행합니다.
- 명령은 bash 기준입니다(변수의 단어 분리에 의존). zsh를 쓴다면 먼저 `bash`를 실행한 셸에서 진행합니다.
- 삭제는 되돌릴 수 없습니다. 각 단계의 조회 명령으로 대상이 맞는지 확인한 뒤 삭제 명령을 실행합니다.

## 계속 비용이 나가는 리소스 (먼저 확인)

| 리소스 | 비용 | 지우는 단계 |
|---|---|---|
| HyperPod `ml.p4d.24xlarge` 1대 | $25.91/h [documented] | 4 |
| 셀프호스팅 E2B 전체(클라이언트 노드 `c8i.metal-48xl`, Nomad 서버, API 노드, 빌드 노드, 배스천, Aurora, ElastiCache, NAT 게이트웨이, ALB) | 약 $11.11/h [estimated, 계산식은 `05-comparison.md`] | 2 |
| EKS 컨트롤 플레인 | $0.10/h [documented] | 4 |
| NAT 게이트웨이 (HyperPod VPC, E2B VPC 각 1개) | 각 $0.045/h + 처리 GB당 요금 [documented] | 2, 4 |
| AgentCore용 인터페이스 엔드포인트 4개(ecr.api, ecr.dkr, logs, bedrock-agentcore) x 서브넷 2개 | $0.08/h [estimated: 4 x 2 x $0.01/h] | 3 |
| AgentCore Runtime | 런타임 자체는 무과금. 활성 세션만 과금 | 1, 3 |
| Secrets Manager 비밀 | 비밀당 월 $0.40 [documented] | 2 |
| ECR 이미지, EBS 스냅샷(E2B AMI), S3 객체, CloudWatch 로그 | 저장 용량 과금 | 2, 3, 4, 5, 6 |

## 0. 변수

모든 단계에서 이 변수를 사용합니다. 4절에서 HyperPod 클러스터를 지우기 전에 한 번 실행해 두어야 `EKS_CLUSTER_NAME`과 `RUNTIME_ID`를 조회할 수 있습니다.

```bash
export AWS_REGION=us-west-2
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export CLUSTER_NAME=harbor-rl-hp            # HyperPod cluster name (params.json HyperPodClusterName)
export STACK_NAME=harbor-rl-hp              # HyperPod CloudFormation stack (create-cluster.sh)
export E2B_STACK=harbor-rl-e2b              # self-hosted E2B stack (deploy.sh STACK)
export RUNTIME_NAME=harbor_rl_tasks         # AgentCore runtime name (deploy_runtime.sh)
export BUCKET=harbor-rl-sandbox-$ACCOUNT_ID-$AWS_REGION
export KUBECONFIG=$HOME/.kube/harbor-rl-hp

export DOMAIN=example.com                   # the DOMAIN you passed to deploy.sh
export E2B_DOMAIN=e2b.$DOMAIN               # E2B_DOMAIN used by deploy.sh
export ZONE_ID=$(aws route53 list-hosted-zones-by-name --dns-name "$DOMAIN" \
  --query "HostedZones[?Name=='${DOMAIN}.'].Id | [0]" --output text | sed 's|/hostedzone/||')
# or set it directly: export ZONE_ID=<HOSTED_ZONE_ID>

# looked up by name (the template prefixes the EKS name with ResourceNamePrefix)
export EKS_CLUSTER_NAME=$(aws sagemaker describe-cluster --cluster-name $CLUSTER_NAME --region $AWS_REGION \
  --query Orchestrator.Eks.ClusterArn --output text | awk -F/ '{print $NF}')
export RUNTIME_ID=$(aws bedrock-agentcore-control list-agent-runtimes --region $AWS_REGION \
  --query "agentRuntimes[?agentRuntimeName=='${RUNTIME_NAME}'].agentRuntimeId | [0]" --output text)
# or set it directly: export RUNTIME_ID=<RUNTIME_ID>

echo "EKS=$EKS_CLUSTER_NAME RUNTIME=$RUNTIME_ID ZONE=$ZONE_ID"
```

## 1. 실행 중인 작업 멈추기 (1~2분)

학습 Job이 남아 있으면 AgentCore 세션과 E2B 샌드박스가 계속 과금됩니다. Job을 지우면(`kubectl delete`는 SIGTERM 뒤 SIGKILL을 보냄) 하네스의 종료 훅(인터프리터 종료 훅)이 실행된다는 보장이 없으므로, 열려 있던 샌드박스가 남을 수 있습니다.

- E2B: 남은 샌드박스는 24시간 타임아웃이 지나거나 kill될 때까지 유지됩니다. 아래처럼 목록을 조회해 kill합니다(E2B Cloud는 대시보드에서도 확인 가능). 셀프호스팅 E2B는 2절에서 스택과 함께 사라집니다.
- AgentCore: 세션은 유휴 타임아웃 15분 뒤 끝납니다.

```bash
kubectl -n harbor-rl delete jobs --all
kubectl -n harbor-rl get pods        # expect: No resources found

# E2B: list and kill open sandboxes (in the cluster, with the Secret sandbox-secrets)
TAG=v12 ./infra/k8s/submit.sh e2b-kill 0 python3 -c '
from e2b import Sandbox
p = Sandbox.list()
while p.has_next:
    for s in p.next_items():
        print(s.sandbox_id, Sandbox.kill(s.sandbox_id))'
kubectl -n harbor-rl logs -f job/e2b-kill
kubectl -n harbor-rl delete job e2b-kill
```

## 2. 셀프호스팅 E2B (40~70분)

순서가 중요합니다.

- **Terraform 리소스를 먼저 지웁니다.** 샘플의 Terraform 상태는 E2B 스택의 S3 버킷(`terraform-state/`)에 있습니다. 버킷을 먼저 비우면 Terraform이 만든 Auto Scaling 그룹, 인스턴스, 보안 그룹, 비밀이 상태 없이 남아 손으로 지워야 합니다. Terraform 리소스는 CloudFormation 스택의 멤버가 아니므로 스택을 지워도 함께 지워지지 않습니다.
- **VPC 피어링**이 남아 있으면 E2B VPC 삭제가 실패합니다.
- **RDS 삭제 보호**가 켜져 있으면 스택 삭제가 실패합니다.

### 2.1 VPC 피어링 삭제 (1분)

```bash
PCX=$(aws ec2 describe-vpc-peering-connections --region $AWS_REGION \
  --filters Name=tag:Name,Values=harbor-rl-e2b-to-hp Name=status-code,Values=active,pending-acceptance \
  --query 'VpcPeeringConnections[].VpcPeeringConnectionId' --output text)
echo "$PCX"
for p in $PCX; do aws ec2 delete-vpc-peering-connection --vpc-peering-connection-id $p --region $AWS_REGION; done
```

`peer.sh`가 넣은 피어링 경로(HyperPod VPC의 라우팅 테이블, E2B VPC에서는 내부 ALB 서브넷의 라우팅 테이블)는 blackhole 상태로 남고, 각 VPC와 함께 삭제됩니다. ALB 보안 그룹 규칙은 E2B 스택과 함께 삭제됩니다.

### 2.2 Terraform 리소스와 배포 체인 산출물 삭제 (15~30분, 배스천에서)

샘플(`aws-samples/sample-e2b-on-aws`, 커밋 `830b516a47b5ecbe86bb981d4816927145280e22`)에 들어 있는 `infra-iac/destroy.sh`를 배스천에서 실행합니다. 이 스크립트는 Nomad Job 중지, 템플릿별 ECR 리포지토리(`e2bdev/base/<template_id>`, DB의 템플릿 ID 기준)와 `e2bdev/base`, `e2b-core/*` 리포지토리 삭제, `terraform destroy`, Terraform이 만든 Secrets Manager 비밀의 즉시 삭제를 순서대로 처리합니다. 배스천은 SSH가 막혀 있으므로 SSM 세션으로 접속합니다(로컬에 Session Manager 플러그인 필요).

```bash
BASTION=$(aws cloudformation describe-stack-resources --stack-name $E2B_STACK --region $AWS_REGION \
  --logical-resource-id BastionInstance --query 'StackResources[0].PhysicalResourceId' --output text)
aws ssm start-session --target $BASTION --region $AWS_REGION
```

배스천 셸에서:

```bash
sudo -i                                   # root, HOME=/root (the deploy chain ran as root)
cd /opt/infra/sample-e2b-on-aws
bash infra-iac/destroy.sh --dry-run       # review what will be deleted
bash infra-iac/destroy.sh                 # type the stack name (harbor-rl-e2b) to confirm
exit; exit
```

`destroy.sh`가 실패 단계를 보고하면 원인을 고친 뒤 다시 실행합니다(각 단계는 재실행해도 안전). 마지막에 출력되는 "summary"에 실패가 없어야 다음 단계로 넘어갑니다.

### 2.3 Packer AMI와 스냅샷 삭제 (1분)

`destroy.sh`는 오케스트레이터 AMI(`<스택 이름>-orch-*`)를 재배포용으로 일부러 남깁니다. 재배포하지 않는다면 AMI와 스냅샷을 지웁니다.

```bash
for ami in $(aws ec2 describe-images --owners self --region $AWS_REGION \
    --filters "Name=name,Values=${E2B_STACK}-orch-*" --query 'Images[].ImageId' --output text); do
  SNAPS=$(aws ec2 describe-images --image-ids $ami --region $AWS_REGION \
    --query 'Images[].BlockDeviceMappings[].Ebs.SnapshotId' --output text)
  aws ec2 deregister-image --image-id $ami --region $AWS_REGION
  for s in $SNAPS; do aws ec2 delete-snapshot --snapshot-id $s --region $AWS_REGION; done
done
```

### 2.4 스택 버킷 비우기, RDS 삭제 보호 확인, 스택 삭제 (15~30분)

```bash
# the four stack buckets (build cache, e2b, loki, templates); versioning is off in this template
for b in $(aws cloudformation describe-stack-resources --stack-name $E2B_STACK --region $AWS_REGION \
    --query "StackResources[?ResourceType=='AWS::S3::Bucket'].PhysicalResourceId" --output text); do
  aws s3 rm s3://$b --recursive --only-show-errors
done

# RDS deletion protection: disable only if it prints True (the sample README asks to check)
DB=$(aws cloudformation describe-stack-resources --stack-name $E2B_STACK --region $AWS_REGION \
  --logical-resource-id AuroraCluster --query 'StackResources[0].PhysicalResourceId' --output text)
aws rds describe-db-clusters --db-cluster-identifier $DB --region $AWS_REGION \
  --query 'DBClusters[0].DeletionProtection' --output text
# aws rds modify-db-cluster --db-cluster-identifier $DB --no-deletion-protection --apply-immediately --region $AWS_REGION

# stack: VPC, NAT, internal ALB, ACM certificate, Aurora, ElastiCache, bastion, buckets, DB credential secret
aws cloudformation delete-stack --stack-name $E2B_STACK --region $AWS_REGION
aws cloudformation wait stack-delete-complete --stack-name $E2B_STACK --region $AWS_REGION
```

Aurora와 ElastiCache 삭제가 가장 오래 걸립니다. 스택이 `DELETE_FAILED`가 되면 이벤트에서 남은 리소스를 확인합니다. 흔한 원인은 비운 뒤에 객체가 다시 들어온 버킷, 남아 있는 ENI나 보안 그룹, 콘솔에서만 지워지는 ALB(샘플 README에 명시)입니다.

```bash
aws cloudformation describe-stack-events --stack-name $E2B_STACK --region $AWS_REGION \
  --query "StackEvents[?ResourceStatus=='DELETE_FAILED'].[LogicalResourceId,ResourceStatusReason]" --output text
```

### 2.5 스택 밖에 남는 리소스 (2분)

```bash
# ECR repositories of the deploy chain (destroy.sh normally removes them; this loop is a no-op then)
for r in e2b-core/api e2b-core/client-proxy e2b-core/db-migrator e2bdev/base; do
  aws ecr delete-repository --repository-name $r --force --region $AWS_REGION 2>/dev/null && echo "deleted $r"
done
# per-template repositories e2bdev/base/<template_id>: list them, and delete only the ones of this deployment
# (do not wildcard if another E2B deployment shares the account)
aws ecr describe-repositories --region $AWS_REGION \
  --query "repositories[?starts_with(repositoryName,'e2bdev/')].repositoryName" --output text

# Nomad/cluster log group
aws logs delete-log-group --log-group-name harbor-rl-e2b-cluster-logs --region $AWS_REGION

# bastion key pair (deploy.sh discards the private key, so there is no local key file to remove)
aws ec2 delete-key-pair --key-name harbor-rl-e2b-bastion --region $AWS_REGION

# team API key written by finalize.sh
aws secretsmanager delete-secret --secret-id harbor-rl-e2b/team-api-key \
  --force-delete-without-recovery --region $AWS_REGION
```

`--force-delete-without-recovery`를 빼면 기본 30일(최소 7일, `--recovery-window-in-days 7`) 복구 기간 동안 비밀이 "삭제 예정" 상태로 남습니다. 그동안은 계속 과금되지는 않지만 같은 이름으로 다시 만들 수 없어 재배포 시 `finalize.sh`가 실패합니다.

### 2.6 E2B 쪽 데이터

템플릿, 팀, API 키, 샌드박스 메타데이터는 모두 E2B 스택의 Aurora와 S3에 있으므로 2.2~2.4에서 함께 지워집니다. 팀 티어 변경(`finalize.sh`의 `base_v1` 24시간 / 1,000)도 DB 안의 설정이라 별도 정리가 필요 없습니다.

### 2.7 E2B Cloud를 사용한 경우

셀프호스팅 대신 E2B Cloud를 썼다면 2.1~2.6 대신 대시보드나 E2B CLI로 다음을 지웁니다.

- 실행 중인 샌드박스: `e2b sandbox list`, `e2b sandbox kill <sandbox_id>`
- 템플릿: `e2b template list`, `e2b template delete <template>`
- 이 가이드용으로 발급한 API 키: 대시보드에서 폐기

## 3. AgentCore (런타임 수 분, 네트워크 최대 8시간 대기 가능)

AgentCore가 VPC 모드 세션용으로 만든 ENI는 런타임을 지운 뒤에도 **최대 8시간** 남을 수 있습니다 [documented]. 이 ENI가 남아 있는 동안은 `network.sh`의 서브넷과 보안 그룹을 지울 수 없고, 같은 VPC를 쓰는 HyperPod 스택(4절)도 지울 수 없습니다. 그래서 1절 직후 런타임부터 지워 대기 시간을 앞당기는 것을 권장합니다.

### 3.1 런타임, 로그 그룹, 실행 역할

```bash
aws bedrock-agentcore-control delete-agent-runtime --agent-runtime-id $RUNTIME_ID --region $AWS_REGION
while aws bedrock-agentcore-control get-agent-runtime --agent-runtime-id $RUNTIME_ID --region $AWS_REGION \
      >/dev/null 2>&1; do sleep 15; done; echo "runtime deleted"

for g in $(aws logs describe-log-groups --region $AWS_REGION \
    --log-group-name-prefix /aws/bedrock-agentcore/runtimes/${RUNTIME_NAME}- \
    --query 'logGroups[].logGroupName' --output text); do
  aws logs delete-log-group --log-group-name $g --region $AWS_REGION
done

aws iam delete-role-policy --role-name harbor-rl-agentcore-exec --policy-name agentcore-exec
aws iam delete-role --role-name harbor-rl-agentcore-exec
```

### 3.2 격리 네트워크 (`agentcore/network.sh`가 만든 리소스)

`network.sh`는 HyperPod VPC 안에 서브넷 2개, 로컬 경로만 있는 라우팅 테이블, 보안 그룹 2개, 인터페이스 엔드포인트 4개(ecr.api, ecr.dkr, logs, 그리고 학습 Pod가 AgentCore 데이터 플레인을 PrivateLink로 호출하는 bedrock-agentcore. 모두 프라이빗 DNS, 정책: 이 계정 주체만)와 격리 라우팅 테이블 전용 S3 게이트웨이 엔드포인트 `harbor-rl-agentcore-s3`(정책: ECR 레이어 버킷의 `s3:GetObject`만)를 만듭니다. `bedrock-agentcore` 엔드포인트를 지우면 VPC 안의 AgentCore 호출은 다시 퍼블릭 엔드포인트로 가므로, 1절에서 AgentCore Job을 모두 멈춘 뒤에 지웁니다. HyperPod 스택의 S3 게이트웨이 엔드포인트는 HyperPod 스택 소유이며 격리 라우팅 테이블이 연결되지 않으므로 그대로 둡니다. 인터페이스 엔드포인트가 `network.sh` 실행 전부터 VPC에 있었다면 `network.sh`가 그 정책을 이 계정 전용으로 바꿉니다. 그런 엔드포인트는 삭제 대상(이름 태그 `harbor-rl-agentcore-*`)이 아니므로, 원래 정책으로 되돌리려면 `aws ec2 modify-vpc-endpoint --vpc-endpoint-id <id> --reset-policy --region $AWS_REGION`을 실행합니다.

```bash
NAME=harbor-rl-agentcore
VPC=$(aws ec2 describe-vpcs --region $AWS_REGION --filters "Name=tag:Name,Values=${STACK_NAME}-VPC" \
  --query 'Vpcs[0].VpcId' --output text)

# 1) interface endpoints (ecr.api, ecr.dkr, logs, bedrock-agentcore data plane PrivateLink)
EPS=$(aws ec2 describe-vpc-endpoints --region $AWS_REGION --filters Name=vpc-id,Values=$VPC \
  "Name=tag:Name,Values=$NAME-ecr.api,$NAME-ecr.dkr,$NAME-logs,$NAME-bedrock-agentcore" \
  --query 'VpcEndpoints[].VpcEndpointId' --output text)
[ -n "$EPS" ] && aws ec2 delete-vpc-endpoints --vpc-endpoint-ids $EPS --region $AWS_REGION
# wait until their network interfaces are gone (usually 1 to 3 minutes)
while [ -n "$(aws ec2 describe-vpc-endpoints --region $AWS_REGION --filters Name=vpc-id,Values=$VPC \
    "Name=tag:Name,Values=$NAME-ecr.api,$NAME-ecr.dkr,$NAME-logs,$NAME-bedrock-agentcore" \
    --query "VpcEndpoints[?State!='deleted'].VpcEndpointId" --output text)" ]; do sleep 15; done

# 2) S3 gateway endpoints: detach the isolated route table from any gateway endpoint (normally a no-op)
RTB=$(aws ec2 describe-route-tables --region $AWS_REGION --filters Name=vpc-id,Values=$VPC \
  "Name=tag:Name,Values=$NAME-isolated" --query 'RouteTables[0].RouteTableId' --output text)
for ep in $(aws ec2 describe-vpc-endpoints --region $AWS_REGION --filters Name=vpc-id,Values=$VPC \
    Name=vpc-endpoint-type,Values=Gateway --query "VpcEndpoints[?contains(RouteTableIds, '$RTB')].VpcEndpointId" \
    --output text); do
  aws ec2 modify-vpc-endpoint --vpc-endpoint-id $ep --remove-route-table-ids $RTB --region $AWS_REGION
done
# then delete network.sh's own S3 gateway endpoint (harbor-rl-agentcore-s3, isolated route table only)
OWN_S3=$(aws ec2 describe-vpc-endpoints --region $AWS_REGION --filters Name=vpc-id,Values=$VPC \
  "Name=tag:Name,Values=$NAME-s3" --query 'VpcEndpoints[].VpcEndpointId' --output text)
[ -n "$OWN_S3" ] && aws ec2 delete-vpc-endpoints --vpc-endpoint-ids $OWN_S3 --region $AWS_REGION

# 3) remaining network interfaces in the two subnets (AgentCore ENIs can persist up to 8 h)
SUBNETS=$(aws ec2 describe-subnets --region $AWS_REGION --filters Name=vpc-id,Values=$VPC \
  "Name=tag:Name,Values=$NAME-*" --query 'Subnets[].SubnetId' --output text)
aws ec2 describe-network-interfaces --region $AWS_REGION --filters "Name=subnet-id,Values=$(printf '%s' "$SUBNETS" | tr '\t' ',')" \
  --query 'NetworkInterfaces[].[NetworkInterfaceId,InterfaceType,Status,Description]' --output text
```

마지막 명령의 출력이 비어 있을 때 다음을 실행합니다. AgentCore가 관리하는 ENI는 직접 지우지 말고 서비스가 해제할 때까지 기다립니다.

```bash
# 4) subnets, then the route table
for s in $SUBNETS; do aws ec2 delete-subnet --subnet-id $s --region $AWS_REGION; done
aws ec2 delete-route-table --route-table-id $RTB --region $AWS_REGION

# 5) security groups: they reference each other, so remove the cross rules first
SESSION_SG=$(aws ec2 describe-security-groups --region $AWS_REGION --filters Name=vpc-id,Values=$VPC \
  Name=group-name,Values=$NAME-sessions --query 'SecurityGroups[0].GroupId' --output text)
ENDPOINT_SG=$(aws ec2 describe-security-groups --region $AWS_REGION --filters Name=vpc-id,Values=$VPC \
  Name=group-name,Values=$NAME-endpoints --query 'SecurityGroups[0].GroupId' --output text)
aws ec2 revoke-security-group-egress --group-id $SESSION_SG --protocol tcp --port 443 \
  --source-group $ENDPOINT_SG --region $AWS_REGION
aws ec2 revoke-security-group-ingress --group-id $ENDPOINT_SG --protocol tcp --port 443 \
  --source-group $SESSION_SG --region $AWS_REGION
aws ec2 delete-security-group --group-id $SESSION_SG --region $AWS_REGION
aws ec2 delete-security-group --group-id $ENDPOINT_SG --region $AWS_REGION
```

`DependencyViolation`이 나면 아직 ENI가 남아 있는 것입니다. 3)의 조회 명령으로 확인하고 시간을 두고 다시 실행합니다.

## 4. HyperPod EKS 클러스터 (30~40분)

HyperPod 스택 하나가 VPC, NAT 게이트웨이, EIP, S3 게이트웨이 엔드포인트, EKS, HyperPod 클러스터, lifecycle 스크립트 버킷, IAM 역할, Helm 의존성을 모두 지웁니다. 3.2절이 끝난 뒤(VPC 안에 `network.sh` 리소스가 없어야 함)에 실행합니다. 노드 로컬 디스크(`/opt/dlami/nvme/harbor-rl`, 캐시와 결과)는 인스턴스와 함께 사라지므로, 필요한 결과는 먼저 S3 버킷 `results/`에 있는지 확인합니다.

```bash
# Pod Identity association, namespace (ServiceAccount, Secret sandbox-secrets, Jobs)
for a in $(aws eks list-pod-identity-associations --cluster-name $EKS_CLUSTER_NAME --region $AWS_REGION \
    --namespace harbor-rl --service-account trainer --query 'associations[].associationId' --output text); do
  aws eks delete-pod-identity-association --cluster-name $EKS_CLUSTER_NAME --association-id $a --region $AWS_REGION
done
kubectl delete namespace harbor-rl

# empty the stack buckets first (stack deletion fails on non-empty buckets); review the list before removing
aws s3api list-buckets --query "Buckets[?starts_with(Name, '${STACK_NAME}-')].Name" --output text
for b in $(aws s3api list-buckets --query "Buckets[?starts_with(Name, '${STACK_NAME}-')].Name" --output text); do
  aws s3 rm s3://$b --recursive --only-show-errors
done

aws cloudformation delete-stack --stack-name $STACK_NAME --region $AWS_REGION
aws cloudformation wait stack-delete-complete --stack-name $STACK_NAME --region $AWS_REGION

# log groups created by the services (the stack does not remove them)
aws logs delete-log-group --log-group-name /aws/eks/$EKS_CLUSTER_NAME/cluster --region $AWS_REGION
for prefix in /aws/lambda/$STACK_NAME /aws/sagemaker/Clusters/$CLUSTER_NAME/; do
  for g in $(aws logs describe-log-groups --log-group-name-prefix $prefix --region $AWS_REGION \
      --query 'logGroups[].logGroupName' --output text); do
    aws logs delete-log-group --log-group-name $g --region $AWS_REGION
  done
done

# trainer pod role (setup-access.sh) and the local kubeconfig
aws iam delete-role-policy --role-name harbor-rl-trainer-pod --policy-name trainer-pod
aws iam delete-role --role-name harbor-rl-trainer-pod
rm -f ~/.kube/harbor-rl-hp
```

스택이 `DELETE_FAILED`면 2.4절의 이벤트 조회 명령에서 스택 이름만 `$STACK_NAME`으로 바꿔 원인을 확인합니다. 가장 흔한 원인은 VPC 안에 남은 ENI(3.2절)나 비어 있지 않은 버킷입니다.

## 5. 이미지와 빌드 (수 분)

```bash
for r in harbor-rl/tasks-base harbor-rl/tasks-agentcore harbor-rl/trainer; do
  aws ecr delete-repository --repository-name $r --force --region $AWS_REGION
done
aws codebuild delete-project --name harbor-rl-trainer-build --region $AWS_REGION
aws logs delete-log-group --log-group-name /aws/codebuild/harbor-rl-trainer-build --region $AWS_REGION
aws iam delete-role-policy --role-name harbor-rl-codebuild --policy-name codebuild
aws iam delete-role --role-name harbor-rl-codebuild
```

로컬 Finch 이미지와 빌드 캐시도 지우려면 `finch image prune -a`, `finch builder prune -a`(Docker: `docker image prune -a`, `docker builder prune -a`)를 실행합니다.

## 6. S3 버킷 (수 분)

이 버킷에는 학습 결과(`results/`), CodeBuild 소스(`codebuild/`), E2B CloudFormation 템플릿 사본(`e2b/`)이 있습니다. 결과를 보관하려면 먼저 내려받습니다. 버전 관리가 꺼져 있으므로 `--force`로 비우고 지울 수 있습니다.

```bash
aws s3 sync s3://$BUCKET/results ./results-backup     # optional backup
aws s3 rb s3://$BUCKET --force
```

## 7. DNS 레코드 (수 분)

호스팅 영역 자체는 고객 소유이므로 지우지 않습니다. `deploy.sh`가 만든 레코드만 지웁니다.

| 레코드 | 이름 | 유형 | 권장 |
|---|---|---|---|
| 와일드카드 | `*.<E2B_DOMAIN>` | CNAME (내부 ALB) | 삭제 |
| ACM 검증 | `_<hash>.<E2B_DOMAIN>` | CNAME (`*.acm-validations.aws`) | 삭제 |
| 메일 사칭 방지 (E2B 하위 도메인) | `<E2B_DOMAIN>` | MX `0 .`, TXT `v=spf1 -all` | 삭제 |
| 메일 사칭 방지 (상위 도메인) | `<DOMAIN>`, `_dmarc.<DOMAIN>` | MX `0 .`, TXT SPF, TXT DMARC | 메일을 보내지 않는 도메인이면 유지 권장 |

상위 도메인의 사칭 방지 레코드는 메일을 보내지 않는 도메인을 보호하므로, 도메인을 계속 보유한다면 남겨 두는 편이 안전합니다. 원래 이 도메인에 메일 레코드가 있었다면 `deploy.sh`가 같은 이름의 MX와 TXT를 덮어썼으므로, 지운 뒤 기존 값을 직접 복원합니다.

```bash
# delete one record set by exact name (with trailing dot) and type
del_rr() {
  RRS=$(aws route53 list-resource-record-sets --hosted-zone-id "$ZONE_ID" \
    --query "ResourceRecordSets[?Name=='$1' && Type=='$2'] | [0]" --output json)
  if [ "$RRS" = "null" ]; then echo "not found: $1 $2"; return; fi
  aws route53 change-resource-record-sets --hosted-zone-id "$ZONE_ID" \
    --change-batch "{\"Changes\":[{\"Action\":\"DELETE\",\"ResourceRecordSet\":$RRS}]}" >/dev/null \
    && echo "deleted: $1 $2"
}

# review first: all records under E2B_DOMAIN
aws route53 list-resource-record-sets --hosted-zone-id "$ZONE_ID" \
  --query "ResourceRecordSets[?ends_with(Name, '${E2B_DOMAIN}.')].[Name,Type]" --output text

del_rr "\\052.${E2B_DOMAIN}." CNAME            # Route 53 stores '*' as \052
for n in $(aws route53 list-resource-record-sets --hosted-zone-id "$ZONE_ID" \
    --query "ResourceRecordSets[?Type=='CNAME' && ends_with(Name, '.${E2B_DOMAIN}.') && contains(ResourceRecords[0].Value, 'acm-validations.aws')].Name" \
    --output text); do
  del_rr "$n" CNAME                             # ACM validation record
done
del_rr "${E2B_DOMAIN}." MX
del_rr "${E2B_DOMAIN}." TXT

# only if you do not want to keep them (see above)
# del_rr "${DOMAIN}." MX
# del_rr "${DOMAIN}." TXT
# del_rr "_dmarc.${DOMAIN}." TXT
```

## 8. 콘솔에서 확인할 것

- **CloudFormation:** 두 스택(`harbor-rl-hp`, `harbor-rl-e2b`)과 중첩 스택이 모두 사라졌는지, `DELETE_FAILED` 스택이 없는지 확인합니다.
- **EC2 > 로드 밸런서:** 샘플 README에 따르면 E2B ALB가 남는 경우가 있어 콘솔에서 지워야 할 수 있습니다.
- **EC2 > 네트워크 인터페이스:** HyperPod VPC에 AgentCore ENI가 남아 있으면 해제될 때까지 기다립니다(최대 8시간).
- **Service Quotas:** 이 가이드를 위해 올린 쿼터(EC2 vCPU, `ml.p4d.24xlarge` 클러스터 사용량)는 과금되지 않으므로 그대로 두어도 됩니다.
- **외부 자격 증명:** 이 가이드 전용으로 만든 Hugging Face 토큰이나 E2B Cloud API 키는 각 서비스에서 폐기합니다.
- **Billing > Cost Explorer:** 하루 뒤 `Project=harbor-rl-sandbox` 비용 할당 태그(활성화한 경우)와 서비스별 비용이 0으로 떨어졌는지 확인합니다.

## 9. 검증

```bash
# anything still tagged Project=harbor-rl-sandbox (some resources are tagged only through their stack,
# so the by-name checks below are needed as well)
aws resourcegroupstaggingapi get-resources --region $AWS_REGION \
  --tag-filters Key=Project,Values=harbor-rl-sandbox --query 'ResourceTagMappingList[].ResourceARN' --output text

# stacks, clusters, runtimes
aws cloudformation list-stacks --region $AWS_REGION \
  --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE ROLLBACK_COMPLETE DELETE_FAILED DELETE_IN_PROGRESS \
  --query "StackSummaries[?starts_with(StackName,'harbor-rl')].[StackName,StackStatus]" --output text
aws sagemaker list-clusters --region $AWS_REGION --name-contains harbor-rl --query 'ClusterSummaries[].ClusterName' --output text
aws bedrock-agentcore-control list-agent-runtimes --region $AWS_REGION \
  --query "agentRuntimes[?starts_with(agentRuntimeName,'harbor_rl')].agentRuntimeId" --output text

# compute and network
aws ec2 describe-instances --region $AWS_REGION --filters 'Name=tag:Name,Values=harbor-rl-*' \
  Name=instance-state-name,Values=pending,running,stopping,stopped --query 'Reservations[].Instances[].InstanceId' --output text
aws ec2 describe-vpcs --region $AWS_REGION --filters 'Name=tag:Name,Values=harbor-rl-*' --query 'Vpcs[].VpcId' --output text
aws ec2 describe-vpc-endpoints --region $AWS_REGION --filters 'Name=tag:Name,Values=harbor-rl-*' \
  --query "VpcEndpoints[?State!='deleted'].[VpcEndpointId,ServiceName]" --output text
aws ec2 describe-subnets --region $AWS_REGION --filters 'Name=tag:Name,Values=harbor-rl-agentcore-*' \
  --query 'Subnets[].SubnetId' --output text
aws ec2 describe-security-groups --region $AWS_REGION --filters 'Name=group-name,Values=harbor-rl-agentcore-*' \
  --query 'SecurityGroups[].GroupId' --output text
aws ec2 describe-vpc-peering-connections --region $AWS_REGION --filters Name=tag:Name,Values=harbor-rl-e2b-to-hp \
  Name=status-code,Values=active,pending-acceptance --query 'VpcPeeringConnections[].VpcPeeringConnectionId' --output text
aws ec2 describe-nat-gateways --region $AWS_REGION --filter Name=state,Values=available \
  --query 'NatGateways[].[NatGatewayId,VpcId]' --output text
aws ec2 describe-addresses --region $AWS_REGION --query 'Addresses[?AssociationId==null].PublicIp' --output text
aws ec2 describe-key-pairs --region $AWS_REGION --filters 'Name=key-name,Values=harbor-rl-*' \
  --query 'KeyPairs[].KeyName' --output text
aws ec2 describe-images --owners self --region $AWS_REGION --filters "Name=name,Values=${E2B_STACK}-*" \
  --query 'Images[].ImageId' --output text

# storage, images, logs
aws ecr describe-repositories --region $AWS_REGION --query "repositories[?starts_with(repositoryName,'harbor-rl/') \
  || starts_with(repositoryName,'e2b-core/') || starts_with(repositoryName,'e2bdev/')].repositoryName" --output text
aws s3api list-buckets --query "Buckets[?starts_with(Name,'harbor-rl')].Name" --output text
aws logs describe-log-groups --region $AWS_REGION \
  --query "logGroups[?contains(logGroupName,'harbor-rl') || contains(logGroupName,'harbor_rl')].logGroupName" --output text
aws codebuild list-projects --region $AWS_REGION --query "projects[?starts_with(@,'harbor-rl')]" --output text

# identity and secrets (include secrets scheduled for deletion, which still hold their names)
aws iam list-roles --query "Roles[?starts_with(RoleName,'harbor-rl')].RoleName" --output text
aws secretsmanager list-secrets --region $AWS_REGION --include-planned-deletion \
  --query "SecretList[?contains(Name,'harbor-rl')].[Name,DeletedDate]" --output text

# DNS (only the records you chose to keep should remain)
aws route53 list-resource-record-sets --hosted-zone-id "$ZONE_ID" \
  --query "ResourceRecordSets[?ends_with(Name, '${E2B_DOMAIN}.')].[Name,Type]" --output text
```

모든 출력이 비어 있으면 정리가 끝난 것입니다. 예외는 다음과 같습니다.

- **NAT 게이트웨이, 미연결 EIP 목록:** 계정의 다른 VPC 리소스도 함께 나오므로, 출력된 VPC ID가 이 가이드의 VPC(이미 삭제됨)인지 확인합니다.
- **Secrets Manager의 `DeletedDate`가 있는 항목:** 복구 기간을 둔 삭제 예정 비밀입니다. 과금되지 않지만 같은 이름으로 재배포하려면 `aws secretsmanager delete-secret --secret-id <name> --force-delete-without-recovery --region $AWS_REGION`으로 즉시 지웁니다.
- **유지하기로 한 DNS 레코드:** 7절에서 상위 도메인의 사칭 방지 레코드를 남겼다면 마지막 명령에는 나오지 않습니다(`E2B_DOMAIN` 아래만 조회).

## 부록: 이 가이드가 만드는 리소스

| 리소스 | 이름 / 찾는 방법 | 만드는 곳 | 지우는 단계 |
|---|---|---|---|
| CloudFormation 스택(HyperPod EKS: VPC, NAT, EIP, S3 게이트웨이 엔드포인트, EKS, HyperPod, lifecycle 버킷, IAM 역할, Helm 의존성) | `harbor-rl-hp`와 중첩 스택 | `infra/hyperpod/create-cluster.sh` | 4 |
| 서비스가 만든 로그 그룹 | `/aws/eks/<EKS 이름>/cluster`, `/aws/lambda/harbor-rl-hp*`, `/aws/sagemaker/Clusters/harbor-rl-hp/*` | EKS, Lambda, HyperPod | 4 |
| IAM 역할(Trainer Pod), Pod Identity 연결, 네임스페이스(ServiceAccount, Secret `sandbox-secrets`) | `harbor-rl-trainer-pod`, `harbor-rl/trainer`, `harbor-rl` | `infra/k8s/setup-access.sh`, `infra/e2b-selfhosted/set-secret.sh` | 4 |
| 로컬 kubeconfig | `~/.kube/harbor-rl-hp` | `01-hyperpod-eks.md` | 4 |
| ECR 리포지토리 | `harbor-rl/tasks-base`, `harbor-rl/tasks-agentcore`, `harbor-rl/trainer` | `tasks/image/build-push.sh`, `agentcore/deploy_runtime.sh`, `training/build-image.sh` | 5 |
| CodeBuild 프로젝트, 로그 그룹, IAM 역할 | `harbor-rl-trainer-build`, `/aws/codebuild/harbor-rl-trainer-build`, `harbor-rl-codebuild` | `training/build-image.sh` | 5 |
| S3 버킷(결과, CodeBuild 소스, E2B 템플릿 사본) | `harbor-rl-sandbox-<ACCOUNT_ID>-us-west-2` | `training/build-image.sh` | 6 |
| AgentCore Runtime(V2, VPC 모드), 로그 그룹, 실행 역할 | `harbor_rl_tasks`, `/aws/bedrock-agentcore/runtimes/harbor_rl_tasks-*`, `harbor-rl-agentcore-exec` | `agentcore/deploy_runtime.sh` | 3.1 |
| AgentCore 격리 네트워크(서브넷 2, 라우팅 테이블, 보안 그룹 2, 인터페이스 엔드포인트 4: ecr.api, ecr.dkr, logs, bedrock-agentcore, 전용 S3 게이트웨이 엔드포인트 1) | 태그 `Name=harbor-rl-agentcore-*`(데이터 플레인 PrivateLink 엔드포인트는 `harbor-rl-agentcore-bedrock-agentcore`, S3 엔드포인트는 `harbor-rl-agentcore-s3`) | `agentcore/network.sh` | 3.2 |
| CloudFormation 스택(셀프호스팅 E2B: VPC, NAT, 내부 ALB, ACM, Aurora, ElastiCache, 배스천, S3 버킷 4, DB 비밀) | `harbor-rl-e2b` | `infra/e2b-selfhosted/deploy.sh` | 2.4 |
| Terraform 리소스(Nomad 서버, API, 클라이언트 `c8i.metal-48xl`, 빌드 노드, Auto Scaling 그룹, 보안 그룹, 비밀, IAM) | 상태: E2B 버킷 `terraform-state/` | 샘플 배포 체인 | 2.2 |
| 배포 체인 산출물(ECR, AMI, 로그 그룹) | `e2b-core/*`, `e2bdev/base`, `e2bdev/base/<template_id>`, `harbor-rl-e2b-orch-*`, `harbor-rl-e2b-cluster-logs` | 샘플 배포 체인 | 2.2, 2.3, 2.5 |
| EC2 키 페어(배스천, 개인 키는 저장하지 않음) | `harbor-rl-e2b-bastion` | `deploy.sh` | 2.5 |
| Secrets Manager 비밀(팀 API 키) | `harbor-rl-e2b/team-api-key` | `infra/e2b-selfhosted/finalize.sh` | 2.5 |
| VPC 피어링, 라우팅 경로(HyperPod 라우팅 테이블, E2B ALB 서브넷 라우팅 테이블), ALB 보안 그룹 규칙 | 태그 `Name=harbor-rl-e2b-to-hp` | `infra/e2b-selfhosted/peer.sh` | 2.1 (경로와 규칙은 VPC, 스택과 함께) |
| Route 53 레코드 | 7절 표 | `deploy.sh` | 7 |
