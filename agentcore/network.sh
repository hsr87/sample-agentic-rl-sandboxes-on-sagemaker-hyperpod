#!/usr/bin/env bash
# Isolated network for AgentCore Runtime sessions (VPC mode without internet), in the HyperPod VPC.
#
#   ./agentcore/network.sh            # idempotent; prints SUBNETS=... and SESSION_SG=... for deploy_runtime.sh
#
# Creates (all tagged Project=harbor-rl-sandbox):
#   * two private subnets in AgentCore-supported AZs, with a route table that has only the local route
#     (no NAT, no internet gateway), so code running in a session cannot reach the internet
#   * a session security group: no inbound; outbound HTTPS only to the endpoints (interface SG, S3 prefix list)
#   * an endpoint security group: inbound HTTPS from the session security group and the VPC CIDRs
#   * interface endpoints for ECR (api, dkr), CloudWatch Logs and the AgentCore data plane (bedrock-agentcore), and the S3 gateway endpoint on the new route
#     table, which AgentCore requires in VPC mode without internet access (AgentCore devguide, "VPC endpoint
#     configuration"), each with a restrictive endpoint policy (see "Endpoints" below)
set -euo pipefail
export AWS_REGION="${AWS_REGION:-us-west-2}"
HP_STACK="${HP_STACK:-harbor-rl-hp}"
AZ_IDS="${AZ_IDS:-usw2-az1 usw2-az2}"            # must be AgentCore VPC-supported AZ ids for the region
CIDRS="${CIDRS:-10.192.96.0/24 10.192.112.0/24}"  # free ranges inside the HyperPod VPC primary CIDR
NAME=harbor-rl-agentcore
TAG_SPEC() { echo "ResourceType=$1,Tags=[{Key=Project,Value=harbor-rl-sandbox},{Key=Name,Value=$2}]"; }
ec2() { aws ec2 "$@" --region "$AWS_REGION"; }

VPC="$(ec2 describe-vpcs --filters "Name=tag:Name,Values=${HP_STACK}-VPC" --query 'Vpcs[0].VpcId' --output text)"
[ "$VPC" != "None" ] || { echo "HyperPod VPC ${HP_STACK}-VPC not found"; exit 1; }

# Route table with only the local route.
RTB="$(ec2 describe-route-tables --filters "Name=vpc-id,Values=$VPC" "Name=tag:Name,Values=${NAME}-isolated" \
  --query 'RouteTables[0].RouteTableId' --output text)"
if [ "$RTB" = "None" ]; then
  RTB="$(ec2 create-route-table --vpc-id "$VPC" --tag-specifications "$(TAG_SPEC route-table "${NAME}-isolated")" \
    --query RouteTable.RouteTableId --output text)"
fi

# Subnets.
SUBNETS=()
set -- $CIDRS
for az in $AZ_IDS; do
  cidr="$1"; shift
  sn="$(ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC" "Name=cidr-block,Values=$cidr" \
    --query 'Subnets[0].SubnetId' --output text)"
  if [ "$sn" = "None" ]; then
    sn="$(ec2 create-subnet --vpc-id "$VPC" --cidr-block "$cidr" --availability-zone-id "$az" \
      --tag-specifications "$(TAG_SPEC subnet "${NAME}-${az}")" --query Subnet.SubnetId --output text)"
  fi
  ec2 associate-route-table --route-table-id "$RTB" --subnet-id "$sn" >/dev/null 2>&1 || true
  SUBNETS+=("$sn")
done

# Security groups.
sg() {  # name description
  local id
  id="$(ec2 describe-security-groups --filters "Name=vpc-id,Values=$VPC" "Name=group-name,Values=$1" \
    --query 'SecurityGroups[0].GroupId' --output text)"
  if [ "$id" = "None" ]; then
    id="$(ec2 create-security-group --vpc-id "$VPC" --group-name "$1" --description "$2" \
      --tag-specifications "$(TAG_SPEC security-group "$1")" --query GroupId --output text)"
  fi
  echo "$id"
}
SESSION_SG="$(sg "${NAME}-sessions" "AgentCore sessions: no inbound, HTTPS to VPC endpoints only")"
ENDPOINT_SG="$(sg "${NAME}-endpoints" "VPC endpoints for AgentCore sessions: HTTPS from sessions only")"
# Replace the default allow-all egress of the session group with HTTPS to the endpoints only.
ec2 revoke-security-group-egress --group-id "$SESSION_SG" --protocol -1 --cidr 0.0.0.0/0 >/dev/null 2>&1 || true
ec2 authorize-security-group-egress --group-id "$SESSION_SG" --protocol tcp --port 443 \
  --source-group "$ENDPOINT_SG" >/dev/null 2>&1 || true
# ECR image layers come from S3 through the gateway endpoint, which is addressed by the S3 prefix list.
S3_PL="$(ec2 describe-managed-prefix-lists --filters "Name=prefix-list-name,Values=com.amazonaws.${AWS_REGION}.s3" \
  --query 'PrefixLists[0].PrefixListId' --output text)"
ec2 authorize-security-group-egress --group-id "$SESSION_SG" \
  --ip-permissions "IpProtocol=tcp,FromPort=443,ToPort=443,PrefixListIds=[{PrefixListId=$S3_PL}]" >/dev/null 2>&1 || true
ec2 authorize-security-group-ingress --group-id "$ENDPOINT_SG" --protocol tcp --port 443 \
  --source-group "$SESSION_SG" >/dev/null 2>&1 || true
# Private DNS of the interface endpoints applies to the whole VPC, so the HyperPod nodes and pods (ECR image
# pulls, logs) also resolve to these endpoints and must be allowed in.
for cidr in $(ec2 describe-vpcs --vpc-ids "$VPC" \
    --query 'Vpcs[0].CidrBlockAssociationSet[?CidrBlockState.State==`associated`].CidrBlock' --output text); do
  ec2 authorize-security-group-ingress --group-id "$ENDPOINT_SG" --protocol tcp --port 443 \
    --cidr "$cidr" >/dev/null 2>&1 || true
done

# Endpoints. Code running in a session can reach these endpoints, so their policies limit what it can do there:
#   * S3: a gateway endpoint of its own on the isolated route table, allowing only the regional ECR layer bucket
#     (AgentCore devguide, "Minimum S3 bucket permissions for container agents"). The VPC's other S3 endpoint stays
#     on the other route tables.
#   * ECR and Logs: only principals of this account (blocks pushing data out with someone else's credentials).
#     Their private DNS covers the whole VPC, so nodes and pods use them too; they use this account's roles.
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
S3_POLICY="{\"Statement\":[{\"Sid\":\"EcrLayersOnly\",\"Effect\":\"Allow\",\"Principal\":\"*\",\"Action\":\"s3:GetObject\",\"Resource\":\"arn:aws:s3:::prod-${AWS_REGION}-starport-layer-bucket/*\"}]}"
OWN_ACCOUNT_POLICY="{\"Statement\":[{\"Sid\":\"OwnAccountOnly\",\"Effect\":\"Allow\",\"Principal\":\"*\",\"Action\":\"*\",\"Resource\":\"*\",\"Condition\":{\"StringEquals\":{\"aws:PrincipalAccount\":\"${ACCOUNT_ID}\"}}}]}"

# S3: detach the isolated route table from any other S3 gateway endpoint, then attach the restricted one.
S3_SVC="com.amazonaws.${AWS_REGION}.s3"
S3_EP="$(ec2 describe-vpc-endpoints --filters "Name=vpc-id,Values=$VPC" "Name=service-name,Values=$S3_SVC" \
  "Name=tag:Name,Values=${NAME}-s3" --query 'VpcEndpoints[0].VpcEndpointId' --output text)"
for other in $(ec2 describe-vpc-endpoints --filters "Name=vpc-id,Values=$VPC" "Name=service-name,Values=$S3_SVC" \
    --query 'VpcEndpoints[].VpcEndpointId' --output text); do
  [ "$other" = "$S3_EP" ] && continue
  ec2 modify-vpc-endpoint --vpc-endpoint-id "$other" --remove-route-table-ids "$RTB" >/dev/null 2>&1 || true
done
if [ "$S3_EP" = "None" ]; then
  ec2 create-vpc-endpoint --vpc-id "$VPC" --vpc-endpoint-type Gateway --service-name "$S3_SVC" \
    --route-table-ids "$RTB" --policy-document "$S3_POLICY" \
    --tag-specifications "$(TAG_SPEC vpc-endpoint "${NAME}-s3")" >/dev/null
else
  ec2 modify-vpc-endpoint --vpc-endpoint-id "$S3_EP" --policy-document "$S3_POLICY" >/dev/null
fi

interface_endpoint() {  # service
  local svc="com.amazonaws.${AWS_REGION}.$1" id
  id="$(ec2 describe-vpc-endpoints --filters "Name=vpc-id,Values=$VPC" "Name=service-name,Values=$svc" \
    --query 'VpcEndpoints[0].VpcEndpointId' --output text)"
  if [ "$id" = "None" ]; then
    ec2 create-vpc-endpoint --vpc-id "$VPC" --vpc-endpoint-type Interface --service-name "$svc" \
      --subnet-ids "${SUBNETS[@]}" --security-group-ids "$ENDPOINT_SG" --private-dns-enabled \
      --policy-document "$OWN_ACCOUNT_POLICY" --tag-specifications "$(TAG_SPEC vpc-endpoint "${NAME}-$1")" >/dev/null
  else
    ec2 modify-vpc-endpoint --vpc-endpoint-id "$id" --policy-document "$OWN_ACCOUNT_POLICY" >/dev/null
  fi
}
interface_endpoint ecr.api
interface_endpoint ecr.dkr
interface_endpoint logs
# AgentCore data plane (InvokeAgentRuntime, InvokeAgentRuntimeCommand, StopRuntimeSession): with private DNS, the
# trainer pods reach AgentCore over PrivateLink instead of the public endpoint, like they reach the internal E2B ALB.
interface_endpoint bedrock-agentcore

# Residual path: the VPC resolver still answers public DNS names from these subnets (DNS tunneling). Close it with
# Route 53 Resolver DNS Firewall on the VPC if the tasks handle sensitive data (see docs/03b-sandbox-agentcore.md).

echo "SUBNETS=$(IFS=,; echo "${SUBNETS[*]}")"
echo "SESSION_SG=$SESSION_SG"
