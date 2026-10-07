[한국어](ko/06-cleanup.md)

# 06. Resource cleanup

This document is the procedure for deleting all resources you created after following the guide in your own account. Running the steps from top to bottom cleans up without dependency errors. Resources are found by name and tag (`Project=harbor-rl-sandbox`), so if you did not change the guide's default names, you can copy and run the commands as is.

- If you did not deploy self-hosted E2B (used E2B Cloud), run only section 2.7 instead of section 2.
- To keep results, run the backup command in section 6 first.
- The commands assume bash (they rely on word splitting of variables). If you use zsh, first start a `bash` shell and work in it.
- Deletion cannot be undone. Use the lookup commands in each step to confirm the targets before running the delete commands.

## Resources that keep incurring cost (check first)

| Resource | Cost | Deleted in step |
|---|---|---|
| HyperPod `ml.p4d.24xlarge` x1 | $25.91/h [documented] | 4 |
| Entire self-hosted E2B (client node `c8i.metal-48xl`, Nomad servers, API nodes, build node, bastion, Aurora, ElastiCache, NAT gateway, ALB) | About $11.11/h [estimated, formula in `05-comparison.md`] | 2 |
| EKS control plane | $0.10/h [documented] | 4 |
| NAT gateways (one each in the HyperPod VPC and the E2B VPC) | $0.045/h each + per-GB processing charge [documented] | 2, 4 |
| 4 interface endpoints x 2 subnets for AgentCore (`ecr.api`, `ecr.dkr`, `logs`, data-plane `bedrock-agentcore`) | $0.08/h [estimated: 4 x 2 x $0.01/h] | 3 |
| AgentCore Runtime | The runtime itself is free. Only active sessions are billed | 1, 3 |
| Secrets Manager secrets | $0.40 per secret per month [documented] | 2 |
| ECR images, EBS snapshots (E2B AMI), S3 objects, CloudWatch logs | Billed by storage size | 2, 3, 4, 5, 6 |

## 0. Variables

All steps use these variables. Run this once before deleting the HyperPod cluster in section 4 so that `EKS_CLUSTER_NAME` and `RUNTIME_ID` can be looked up.

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

## 1. Stop running work (1 to 2 minutes)

If training Jobs remain, AgentCore sessions and E2B sandboxes keep incurring charges. Deleting a Job sends SIGTERM and then SIGKILL to its Pod, and the harness exit hook runs only at a normal interpreter exit, so do not count on it here. Sandboxes that were open stay as follows.

- AgentCore: sessions end at the 15 minute idle timeout.
- E2B (self-hosted and E2B Cloud): sandboxes stay until their 24 hour timeout or until killed. List and kill them with the Job below (it reads `E2B_API_KEY` and `E2B_DOMAIN` from the Secret); on E2B Cloud the dashboard also works. Self-hosted sandboxes also disappear with the stack in section 2.

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
kubectl -n harbor-rl logs -f job/e2b-kill      # one line per killed sandbox: <id> True
kubectl -n harbor-rl delete job e2b-kill
```

## 2. Self-hosted E2B (40 to 70 minutes)

Order matters.

- **Delete the Terraform resources first.** The sample's Terraform state is in the E2B stack's S3 bucket (`terraform-state/`). If you empty the bucket first, the Auto Scaling groups, instances, security groups, and secrets created by Terraform are left without state and must be deleted by hand. Terraform resources are not members of the CloudFormation stack, so deleting the stack does not delete them.
- If the **VPC peering** remains, deleting the E2B VPC fails.
- If **RDS deletion protection** is on, stack deletion fails.

### 2.1 Delete VPC peering (1 minute)

```bash
PCX=$(aws ec2 describe-vpc-peering-connections --region $AWS_REGION \
  --filters Name=tag:Name,Values=harbor-rl-e2b-to-hp Name=status-code,Values=active,pending-acceptance \
  --query 'VpcPeeringConnections[].VpcPeeringConnectionId' --output text)
echo "$PCX"
for p in $PCX; do aws ec2 delete-vpc-peering-connection --vpc-peering-connection-id $p --region $AWS_REGION; done
```

The peering routes that `peer.sh` added (HyperPod route tables, and on the E2B side only the route tables of the internal ALB's subnets) remain in blackhole state and are deleted with each VPC. The ALB security group rules go with the E2B stack.

### 2.2 Delete Terraform resources and deployment chain artifacts (15 to 30 minutes, from the bastion)

Run `infra-iac/destroy.sh`, included in the sample (`aws-samples/sample-e2b-on-aws`, commit `830b516a47b5ecbe86bb981d4816927145280e22`), on the bastion. This script, in order, stops the Nomad Jobs, deletes the per-template ECR repositories (`e2bdev/base/<template_id>`, based on the template IDs in the DB) and the `e2bdev/base` and `e2b-core/*` repositories, runs `terraform destroy`, and immediately deletes the Secrets Manager secrets created by Terraform. SSH to the bastion is blocked, so connect with an SSM session (requires the Session Manager plugin locally).

```bash
BASTION=$(aws cloudformation describe-stack-resources --stack-name $E2B_STACK --region $AWS_REGION \
  --logical-resource-id BastionInstance --query 'StackResources[0].PhysicalResourceId' --output text)
aws ssm start-session --target $BASTION --region $AWS_REGION
```

In the bastion shell:

```bash
sudo -i                                   # root, HOME=/root (the deploy chain ran as root)
cd /opt/infra/sample-e2b-on-aws
bash infra-iac/destroy.sh --dry-run       # review what will be deleted
bash infra-iac/destroy.sh                 # type the stack name (harbor-rl-e2b) to confirm
exit; exit
```

If `destroy.sh` reports a failed step, fix the cause and run it again (each step is safe to rerun). Move on to the next step only when the "summary" printed at the end shows no failures.

### 2.3 Delete the Packer AMI and snapshots (1 minute)

`destroy.sh` intentionally keeps the orchestrator AMI (`<stack name>-orch-*`) for redeployment. If you will not redeploy, delete the AMI and snapshots.

```bash
for ami in $(aws ec2 describe-images --owners self --region $AWS_REGION \
    --filters "Name=name,Values=${E2B_STACK}-orch-*" --query 'Images[].ImageId' --output text); do
  SNAPS=$(aws ec2 describe-images --image-ids $ami --region $AWS_REGION \
    --query 'Images[].BlockDeviceMappings[].Ebs.SnapshotId' --output text)
  aws ec2 deregister-image --image-id $ami --region $AWS_REGION
  for s in $SNAPS; do aws ec2 delete-snapshot --snapshot-id $s --region $AWS_REGION; done
done
```

### 2.4 Empty the stack buckets, check RDS deletion protection, delete the stack (15 to 30 minutes)

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

Deleting Aurora and ElastiCache takes the longest. If the stack goes to `DELETE_FAILED`, check the events for the remaining resources. Common causes are a bucket that received objects again after being emptied, leftover ENIs or security groups, and an ALB that can only be deleted from the console (stated in the sample README).

```bash
aws cloudformation describe-stack-events --stack-name $E2B_STACK --region $AWS_REGION \
  --query "StackEvents[?ResourceStatus=='DELETE_FAILED'].[LogicalResourceId,ResourceStatusReason]" --output text
```

### 2.5 Resources left outside the stack (2 minutes)

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

# bastion key pair (deploy.sh discards the private key, so there is no local file to remove)
aws ec2 delete-key-pair --key-name harbor-rl-e2b-bastion --region $AWS_REGION

# team API key written by finalize.sh
aws secretsmanager delete-secret --secret-id harbor-rl-e2b/team-api-key \
  --force-delete-without-recovery --region $AWS_REGION
```

Without `--force-delete-without-recovery`, the secret stays in a "scheduled for deletion" state for the recovery window (30 days by default, minimum 7 days with `--recovery-window-in-days 7`). During that time it is not billed, but you cannot recreate a secret with the same name, so `finalize.sh` fails on redeployment.

### 2.6 Data on the E2B side

Templates, teams, API keys, and sandbox metadata all live in the E2B stack's Aurora and S3, so they are deleted along with steps 2.2 to 2.4. The team tier change (`base_v1` 24 hours / 1,000 in `finalize.sh`) is also a setting inside the DB, so it needs no separate cleanup.

### 2.7 If you used E2B Cloud

If you used E2B Cloud instead of self-hosting, delete the following with the dashboard or the E2B CLI instead of steps 2.1 to 2.6.

- Running sandboxes: `e2b sandbox list`, `e2b sandbox kill <sandbox_id>`
- Templates: `e2b template list`, `e2b template delete <template>`
- API keys issued for this guide: revoke them in the dashboard

## 3. AgentCore (runtime in a few minutes, network may wait up to 8 hours)

ENIs that AgentCore created for VPC mode sessions can remain for **up to 8 hours** after the runtime is deleted [documented]. While these ENIs remain, the subnets and security groups from `network.sh` cannot be deleted, and neither can the HyperPod stack that uses the same VPC (section 4). We therefore recommend deleting the runtime right after section 1 to start that wait earlier.

### 3.1 Runtime, log groups, execution role

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

### 3.2 Isolated network (resources created by `agentcore/network.sh`)

`network.sh` creates, inside the HyperPod VPC, 2 subnets, a route table with only the local route, 2 security groups, 4 interface endpoints (ecr.api, ecr.dkr, logs, and the AgentCore data-plane endpoint bedrock-agentcore that the trainer Pods use over PrivateLink; endpoint policy: this account's principals only), and an S3 gateway endpoint of its own (`harbor-rl-agentcore-s3`, associated only with the isolated route table; endpoint policy: the ECR layer bucket only). The HyperPod stack's S3 gateway endpoint stays on the other route tables and is deleted with that stack. Endpoint policies are attributes of the endpoints and go with them. If an interface endpoint for one of these services already existed in the VPC before `network.sh` ran, `network.sh` changed its policy to this account only. Such an endpoint is not a deletion target here (the Name tags `harbor-rl-agentcore-*` select only the endpoints `network.sh` created), so to restore its original policy run `aws ec2 modify-vpc-endpoint --vpc-endpoint-id <id> --reset-policy --region $AWS_REGION`.

```bash
NAME=harbor-rl-agentcore
VPC=$(aws ec2 describe-vpcs --region $AWS_REGION --filters "Name=tag:Name,Values=${STACK_NAME}-VPC" \
  --query 'Vpcs[0].VpcId' --output text)

# 1) interface endpoints (ecr.api, ecr.dkr, logs, bedrock-agentcore)
EPS=$(aws ec2 describe-vpc-endpoints --region $AWS_REGION --filters Name=vpc-id,Values=$VPC \
  "Name=tag:Name,Values=$NAME-ecr.api,$NAME-ecr.dkr,$NAME-logs,$NAME-bedrock-agentcore" \
  --query 'VpcEndpoints[].VpcEndpointId' --output text)
[ -n "$EPS" ] && aws ec2 delete-vpc-endpoints --vpc-endpoint-ids $EPS --region $AWS_REGION
# wait until their network interfaces are gone (usually 1 to 3 minutes)
while [ -n "$(aws ec2 describe-vpc-endpoints --region $AWS_REGION --filters Name=vpc-id,Values=$VPC \
    "Name=tag:Name,Values=$NAME-ecr.api,$NAME-ecr.dkr,$NAME-logs,$NAME-bedrock-agentcore" \
    --query "VpcEndpoints[?State!='deleted'].VpcEndpointId" --output text)" ]; do sleep 15; done

# 2) S3 gateway endpoints: detach the isolated route table from any gateway endpoint, then delete network.sh's own one
RTB=$(aws ec2 describe-route-tables --region $AWS_REGION --filters Name=vpc-id,Values=$VPC \
  "Name=tag:Name,Values=$NAME-isolated" --query 'RouteTables[0].RouteTableId' --output text)
for ep in $(aws ec2 describe-vpc-endpoints --region $AWS_REGION --filters Name=vpc-id,Values=$VPC \
    Name=vpc-endpoint-type,Values=Gateway --query "VpcEndpoints[?contains(RouteTableIds, '$RTB')].VpcEndpointId" \
    --output text); do
  aws ec2 modify-vpc-endpoint --vpc-endpoint-id $ep --remove-route-table-ids $RTB --region $AWS_REGION
done
OWN_S3=$(aws ec2 describe-vpc-endpoints --region $AWS_REGION --filters Name=vpc-id,Values=$VPC \
  "Name=tag:Name,Values=$NAME-s3" --query 'VpcEndpoints[].VpcEndpointId' --output text)
[ -n "$OWN_S3" ] && aws ec2 delete-vpc-endpoints --vpc-endpoint-ids $OWN_S3 --region $AWS_REGION

# 3) remaining network interfaces in the two subnets (AgentCore ENIs can persist up to 8 h)
SUBNETS=$(aws ec2 describe-subnets --region $AWS_REGION --filters Name=vpc-id,Values=$VPC \
  "Name=tag:Name,Values=$NAME-*" --query 'Subnets[].SubnetId' --output text)
aws ec2 describe-network-interfaces --region $AWS_REGION \
  --filters "Name=subnet-id,Values=$(echo "$SUBNETS" | tr '\t' ',')" \
  --query 'NetworkInterfaces[].[NetworkInterfaceId,InterfaceType,Status,Description]' --output text
```

Run the following once the output of the last command is empty. Do not delete ENIs managed by AgentCore yourself; wait until the service releases them.

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

A `DependencyViolation` means ENIs still remain. Check with the lookup command in 3) and try again later.

## 4. HyperPod EKS cluster (30 to 40 minutes)

The single HyperPod stack deletes the VPC, NAT gateway, EIP, S3 gateway endpoint, EKS, HyperPod cluster, lifecycle script bucket, IAM roles, and Helm dependencies. Run this after section 3.2 is done (no `network.sh` resources may remain in the VPC). The node-local disk (`/opt/dlami/nvme/harbor-rl`, cache and results) disappears with the instance, so first check that the results you need are in the S3 bucket under `results/`.

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

If the stack is `DELETE_FAILED`, check the cause with the event lookup command from section 2.4, changing only the stack name to `$STACK_NAME`. The most common causes are ENIs left in the VPC (section 3.2) or a non-empty bucket.

## 5. Images and builds (a few minutes)

```bash
for r in harbor-rl/tasks-base harbor-rl/tasks-agentcore harbor-rl/trainer; do
  aws ecr delete-repository --repository-name $r --force --region $AWS_REGION
done
aws codebuild delete-project --name harbor-rl-trainer-build --region $AWS_REGION
aws logs delete-log-group --log-group-name /aws/codebuild/harbor-rl-trainer-build --region $AWS_REGION
aws iam delete-role-policy --role-name harbor-rl-codebuild --policy-name codebuild
aws iam delete-role --role-name harbor-rl-codebuild
```

To also delete local Finch images and build cache, run `finch image prune -a` and `finch builder prune -a` (Docker: `docker image prune -a`, `docker builder prune -a`).

## 6. S3 bucket (a few minutes)

This bucket holds the training results (`results/`), the CodeBuild source (`codebuild/`), and a copy of the E2B CloudFormation template (`e2b/`). To keep the results, download them first. Versioning is off, so you can empty and delete it with `--force`.

```bash
aws s3 sync s3://$BUCKET/results ./results-backup     # optional backup
aws s3 rb s3://$BUCKET --force
```

## 7. DNS records (a few minutes)

The hosted zone itself is owned by the customer, so do not delete it. Delete only the records that `deploy.sh` created.

| Record | Name | Type | Recommendation |
|---|---|---|---|
| Wildcard | `*.<E2B_DOMAIN>` | CNAME (internal ALB) | Delete |
| ACM validation | `_<hash>.<E2B_DOMAIN>` | CNAME (`*.acm-validations.aws`) | Delete |
| Anti-spoofing for mail (E2B subdomain) | `<E2B_DOMAIN>` | MX `0 .`, TXT `v=spf1 -all` | Delete |
| Anti-spoofing for mail (parent domain) | `<DOMAIN>`, `_dmarc.<DOMAIN>` | MX `0 .`, TXT SPF, TXT DMARC | Keep recommended if the domain does not send mail |

The parent domain's anti-spoofing records protect a domain that does not send mail, so if you keep the domain, it is safer to leave them in place. If the domain originally had mail records, `deploy.sh` overwrote the MX and TXT records with the same names, so restore the previous values yourself after deleting.

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

## 8. What to check in the console

- **CloudFormation:** Confirm that both stacks (`harbor-rl-hp`, `harbor-rl-e2b`) and their nested stacks are gone and that no stack is in `DELETE_FAILED`.
- **EC2 > Load Balancers:** According to the sample README, the E2B ALB sometimes remains and may need to be deleted from the console.
- **EC2 > Network Interfaces:** If AgentCore ENIs remain in the HyperPod VPC, wait until they are released (up to 8 hours).
- **Service Quotas:** Quotas raised for this guide (EC2 vCPU, `ml.p4d.24xlarge` cluster usage) are not billed, so you can leave them as they are.
- **External credentials:** Revoke any Hugging Face token or E2B Cloud API key created only for this guide in the respective service.
- **Billing > Cost Explorer:** After one day, confirm that the `Project=harbor-rl-sandbox` cost allocation tag (if activated) and the per-service costs have dropped to 0.

## 9. Verification

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

If every output is empty, cleanup is complete. The exceptions are:

- **NAT gateway and unassociated EIP lists:** These also show resources from other VPCs in the account, so check whether the printed VPC IDs belong to this guide's VPCs (already deleted).
- **Secrets Manager entries with a `DeletedDate`:** These are secrets scheduled for deletion with a recovery window. They are not billed, but to redeploy with the same name, delete them immediately with `aws secretsmanager delete-secret --secret-id <name> --force-delete-without-recovery --region $AWS_REGION`.
- **DNS records you chose to keep:** If you kept the parent domain's anti-spoofing records in section 7, they do not appear in the last command (it only queries under `E2B_DOMAIN`).

## Appendix: Resources this guide creates

| Resource | Name / how to find | Created by | Deleted in step |
|---|---|---|---|
| CloudFormation stack (HyperPod EKS: VPC, NAT, EIP, S3 gateway endpoint, EKS, HyperPod, lifecycle bucket, IAM roles, Helm dependencies) | `harbor-rl-hp` and nested stacks | `infra/hyperpod/create-cluster.sh` | 4 |
| Log groups created by services | `/aws/eks/<EKS name>/cluster`, `/aws/lambda/harbor-rl-hp*`, `/aws/sagemaker/Clusters/harbor-rl-hp/*` | EKS, Lambda, HyperPod | 4 |
| IAM role (Trainer Pod), Pod Identity association, namespace (ServiceAccount, Secret `sandbox-secrets`) | `harbor-rl-trainer-pod`, `harbor-rl/trainer`, `harbor-rl` | `infra/k8s/setup-access.sh`, `infra/e2b-selfhosted/set-secret.sh` | 4 |
| Local kubeconfig | `~/.kube/harbor-rl-hp` | `01-hyperpod-eks.md` | 4 |
| ECR repositories | `harbor-rl/tasks-base`, `harbor-rl/tasks-agentcore`, `harbor-rl/trainer` | `tasks/image/build-push.sh`, `agentcore/deploy_runtime.sh`, `training/build-image.sh` | 5 |
| CodeBuild project, log group, IAM role | `harbor-rl-trainer-build`, `/aws/codebuild/harbor-rl-trainer-build`, `harbor-rl-codebuild` | `training/build-image.sh` | 5 |
| S3 bucket (results, CodeBuild source, E2B template copy) | `harbor-rl-sandbox-<ACCOUNT_ID>-us-west-2` | `training/build-image.sh` | 6 |
| AgentCore Runtime (V2, VPC mode), log groups, execution role | `harbor_rl_tasks`, `/aws/bedrock-agentcore/runtimes/harbor_rl_tasks-*`, `harbor-rl-agentcore-exec` | `agentcore/deploy_runtime.sh` | 3.1 |
| AgentCore isolated network (2 subnets, route table, 2 security groups, 4 interface endpoints including the data-plane endpoint `harbor-rl-agentcore-bedrock-agentcore`, S3 gateway endpoint `harbor-rl-agentcore-s3`, all with endpoint policies) | Tag `Name=harbor-rl-agentcore-*` | `agentcore/network.sh` | 3.2 |
| CloudFormation stack (self-hosted E2B: VPC, NAT, internal ALB, ACM, Aurora, ElastiCache, bastion, 4 S3 buckets, DB secret) | `harbor-rl-e2b` | `infra/e2b-selfhosted/deploy.sh` | 2.4 |
| Terraform resources (Nomad servers, API, client `c8i.metal-48xl`, build node, Auto Scaling groups, security groups, secrets, IAM) | State: E2B bucket `terraform-state/` | Sample deployment chain | 2.2 |
| Deployment chain artifacts (ECR, AMI, log group) | `e2b-core/*`, `e2bdev/base`, `e2bdev/base/<template_id>`, `harbor-rl-e2b-orch-*`, `harbor-rl-e2b-cluster-logs` | Sample deployment chain | 2.2, 2.3, 2.5 |
| EC2 key pair (bastion; private key discarded at creation) | `harbor-rl-e2b-bastion` | `deploy.sh` | 2.5 |
| Secrets Manager secret (team API key) | `harbor-rl-e2b/team-api-key` | `infra/e2b-selfhosted/finalize.sh` | 2.5 |
| VPC peering, routes (HyperPod route tables; E2B ALB subnet route tables), ALB security group rules | Tag `Name=harbor-rl-e2b-to-hp` | `infra/e2b-selfhosted/peer.sh` | 2.1 (routes and rules go with the VPCs and stacks) |
| Route 53 records | Table in section 7 | `deploy.sh` | 7 |
