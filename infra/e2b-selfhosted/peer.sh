#!/usr/bin/env bash
# Peer the self-hosted E2B VPC with the HyperPod VPC so trainer pods can reach the internal E2B load balancer,
# and restrict that load balancer to HTTPS from the two VPCs.
# Idempotent. Routes are added for every CIDR of each VPC (HyperPod has secondary pod CIDRs) in every route table.
#
#   ./infra/e2b-selfhosted/peer.sh
set -euo pipefail
export AWS_REGION="${AWS_REGION:-us-west-2}"
STACK="${STACK:-harbor-rl-e2b}"
HP_STACK="${HP_STACK:-harbor-rl-hp}"
NAME="${NAME:-harbor-rl-e2b-to-hp}"
TAGS="Key=Project,Value=harbor-rl-sandbox"

E2B_VPC="$(aws cloudformation describe-stack-resources --stack-name "$STACK" --region "$AWS_REGION" \
  --logical-resource-id VPC --query 'StackResources[0].PhysicalResourceId' --output text)"
HP_VPC="$(aws ec2 describe-vpcs --region "$AWS_REGION" --filters "Name=tag:Name,Values=${HP_STACK}-VPC" \
  --query 'Vpcs[0].VpcId' --output text)"
echo "E2B VPC $E2B_VPC <-> HyperPod VPC $HP_VPC"

PCX="$(aws ec2 describe-vpc-peering-connections --region "$AWS_REGION" \
  --filters "Name=requester-vpc-info.vpc-id,Values=${E2B_VPC}" "Name=accepter-vpc-info.vpc-id,Values=${HP_VPC}" \
            "Name=status-code,Values=active,pending-acceptance" \
  --query 'VpcPeeringConnections[0].VpcPeeringConnectionId' --output text)"
if [ "$PCX" = "None" ]; then
  PCX="$(aws ec2 create-vpc-peering-connection --region "$AWS_REGION" --vpc-id "$E2B_VPC" --peer-vpc-id "$HP_VPC" \
    --tag-specifications "ResourceType=vpc-peering-connection,Tags=[{$TAGS},{Key=Name,Value=$NAME}]" \
    --query VpcPeeringConnection.VpcPeeringConnectionId --output text)"
  aws ec2 wait vpc-peering-connection-exists --region "$AWS_REGION" --vpc-peering-connection-ids "$PCX"
  aws ec2 accept-vpc-peering-connection --region "$AWS_REGION" --vpc-peering-connection-id "$PCX" >/dev/null
fi
echo "peering $PCX"

cidrs() { aws ec2 describe-vpcs --region "$AWS_REGION" --vpc-ids "$1" \
  --query 'Vpcs[0].CidrBlockAssociationSet[?CidrBlockState.State==`associated`].CidrBlock' --output text; }
# Skips gateway route tables (the E2B VPC's regional NAT gateway has one; it rejects peering routes) and the
# isolated route table of the AgentCore session subnets (agentcore/network.sh), which must stay local-only.
route_tables() { aws ec2 describe-route-tables --region "$AWS_REGION" --filters "Name=vpc-id,Values=$1" \
  --query 'RouteTables[?!(Associations[?GatewayId]) && !(Tags[?Key==`Name` && Value==`harbor-rl-agentcore-isolated`])].RouteTableId' \
  --output text; }
alb_route_tables() {  # route tables of the internal load balancer's subnets (the only E2B side that needs a path back)
  local lb subnets
  lb="$(aws cloudformation describe-stack-resources --stack-name "$STACK" --region "$AWS_REGION" \
    --logical-resource-id ApplicationLoadBalancer --query 'StackResources[0].PhysicalResourceId' --output text)"
  subnets="$(aws elbv2 describe-load-balancers --region "$AWS_REGION" --load-balancer-arns "$lb" \
    --query 'LoadBalancers[0].AvailabilityZones[].SubnetId' --output text | tr '\t' ',')"
  aws ec2 describe-route-tables --region "$AWS_REGION" --filters "Name=association.subnet-id,Values=$subnets" \
    --query 'RouteTables[].RouteTableId' --output text | tr '\t' '\n' | sort -u
}
add_routes() {  # dest-vpc route-table...
  local dest="$1"; shift
  for rtb in "$@"; do
    for cidr in $(cidrs "$dest"); do
      aws ec2 create-route --region "$AWS_REGION" --route-table-id "$rtb" --destination-cidr-block "$cidr" \
        --vpc-peering-connection-id "$PCX" >/dev/null 2>&1 \
        || aws ec2 replace-route --region "$AWS_REGION" --route-table-id "$rtb" --destination-cidr-block "$cidr" \
             --vpc-peering-connection-id "$PCX" >/dev/null
      echo "  $rtb: $cidr -> $PCX"
    done
  done
}
# E2B side: only the load balancer subnets route back to HyperPod (sandbox and server nodes get no route; the
# HyperPod security groups also admit only their own members). HyperPod side: pods and nodes reach the ALB.
ALB_RTBS="$(alb_route_tables)"
add_routes "$HP_VPC" $ALB_RTBS
for rtb in $(route_tables "$E2B_VPC"); do  # remove peering routes from any other E2B route table
  echo "$ALB_RTBS" | grep -qx "$rtb" && continue
  for cidr in $(cidrs "$HP_VPC"); do
    aws ec2 delete-route --region "$AWS_REGION" --route-table-id "$rtb" --destination-cidr-block "$cidr" \
      >/dev/null 2>&1 && echo "  $rtb: removed $cidr" || true
  done
done
add_routes "$E2B_VPC" $(route_tables "$HP_VPC")

# Restrict the internal load balancer to HTTPS from the two VPCs. The sample opens 80 and 443 to 0.0.0.0/0
# (there is no listener on 80); sandbox subdomains are served without authentication to anyone who can reach the
# load balancer, so only the E2B VPC itself and the HyperPod VPC (trainer pods) are allowed.
ALB_SG="$(aws cloudformation describe-stack-resources --stack-name "$STACK" --region "$AWS_REGION" \
  --logical-resource-id ALBSecurityGroup --query 'StackResources[0].PhysicalResourceId' --output text)"
for port in 80 443; do
  for any in "IpRanges=[{CidrIp=0.0.0.0/0}]" "Ipv6Ranges=[{CidrIpv6=::/0}]"; do
    aws ec2 revoke-security-group-ingress --region "$AWS_REGION" --group-id "$ALB_SG" \
      --ip-permissions "IpProtocol=tcp,FromPort=$port,ToPort=$port,$any" >/dev/null 2>&1 || true  # absent is fine
  done
done
for cidr in $(cidrs "$E2B_VPC") $(cidrs "$HP_VPC"); do
  aws ec2 authorize-security-group-ingress --region "$AWS_REGION" --group-id "$ALB_SG" \
    --ip-permissions "IpProtocol=tcp,FromPort=443,ToPort=443,IpRanges=[{CidrIp=$cidr,Description=harbor-rl}]" \
    >/dev/null 2>&1 || true  # already present is fine
done
# Verify the result instead of trusting the calls above.
OPEN="$(aws ec2 describe-security-groups --region "$AWS_REGION" --group-ids "$ALB_SG" --query \
  'SecurityGroups[0].IpPermissions[?contains(IpRanges[].CidrIp, `0.0.0.0/0`) || contains(Ipv6Ranges[].CidrIpv6, `::/0`)]' \
  --output text)"
[ -z "$OPEN" ] || { echo "ALB security group $ALB_SG is still open to the internet"; exit 1; }
aws ec2 describe-security-groups --region "$AWS_REGION" --group-ids "$ALB_SG" \
  --query 'SecurityGroups[0].IpPermissions[].[FromPort,IpRanges[].CidrIp]' --output text
