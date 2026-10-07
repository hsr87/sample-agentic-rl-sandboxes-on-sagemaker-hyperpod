#!/usr/bin/env bash
# Deploy self-hosted E2B (aws-samples/sample-e2b-on-aws) in this account and region, with DNS in Route 53.
#
#   DOMAIN=example.com ./infra/e2b-selfhosted/deploy.sh     # E2B_DOMAIN defaults to e2b.example.com
#
# Access model: PublicAccess=Private, so the load balancer is internal. The public DNS records resolve only to
# private addresses; trainer pods reach them through VPC peering (peer.sh). Nothing under the domain is reachable
# from the internet, and the bastion has no SSH ingress (it is managed through SSM).
#
# What it does (about 1 to 1.5 hours, idempotent; re-run after a failure):
#   0. anti-spoofing DNS records (null MX, SPF -all, DMARC reject) for a domain that never sends mail
#   1. CloudFormation template at a pinned commit, uploaded to the project bucket
#   2. EC2 key pair for the bastion (required by the template; the private key is discarded, access is via SSM)
#   3. the stack (Environment=dev, Architecture=x86_64, AutoDeploy=false); the generated DB password goes through
#      a temporary 0600 parameters file, not the command line (the stack keeps it in Secrets Manager)
#   4. the ACM DNS validation record, then *.<E2B_DOMAIN> -> internal load balancer
#   5. the sample's deploy chain on the bastion through SSM (packer, terraform, init-db, build, prepare, deploy,
#      create-template), at the pinned commit, with two fixes the unattended path of the sample lacks:
#      HOME=/root (Go needs a cache directory in init-db) and git safe.directory (the repository is owned by
#      ubuntu while the chain runs as root; otherwise image tags get an empty commit hash)
#   6. finalize.sh: team tier limits, team API key into Secrets Manager, key redacted from the deploy log
set -euo pipefail
export AWS_REGION="${AWS_REGION:-us-west-2}"
DOMAIN="${DOMAIN:?set DOMAIN (a domain with a public Route 53 hosted zone in this account)}"
E2B_DOMAIN="${E2B_DOMAIN:-e2b.${DOMAIN}}"
export STACK="${STACK:-harbor-rl-e2b}"
SAMPLE_COMMIT="${SAMPLE_COMMIT:-830b516a47b5ecbe86bb981d4816927145280e22}"
CLIENT_INSTANCE_TYPE="${CLIENT_INSTANCE_TYPE:-c8i.metal-48xl}"
KEY_NAME="${KEY_NAME:-harbor-rl-e2b-bastion}"
HERE="$(cd "$(dirname "$0")" && pwd)"
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
BUCKET="harbor-rl-sandbox-${ACCOUNT_ID}-${AWS_REGION}"
ZONE_ID="$(aws route53 list-hosted-zones-by-name --dns-name "$DOMAIN" \
  --query "HostedZones[?Name=='${DOMAIN}.'].Id | [0]" --output text | sed 's|/hostedzone/||')"
[ -n "$ZONE_ID" ] && [ "$ZONE_ID" != "None" ] || { echo "no hosted zone for $DOMAIN"; exit 1; }
source "$HERE/bastion.sh"

upsert() {  # name type value
  aws route53 change-resource-record-sets --hosted-zone-id "$ZONE_ID" --change-batch \
    "{\"Changes\":[{\"Action\":\"UPSERT\",\"ResourceRecordSet\":{\"Name\":\"$1\",\"Type\":\"$2\",\"TTL\":300,\"ResourceRecords\":[{\"Value\":\"$3\"}]}}]}" >/dev/null
}
txt() {  # name value (TXT values need inner quotes)
  aws route53 change-resource-record-sets --hosted-zone-id "$ZONE_ID" --change-batch \
    "{\"Changes\":[{\"Action\":\"UPSERT\",\"ResourceRecordSet\":{\"Name\":\"$1\",\"Type\":\"TXT\",\"TTL\":3600,\"ResourceRecords\":[{\"Value\":\"\\\"$2\\\"\"}]}}]}" >/dev/null
}

# 0. Anti-spoofing records.
upsert "$DOMAIN" MX "0 ."
txt "$DOMAIN" "v=spf1 -all"
txt "_dmarc.$DOMAIN" "v=DMARC1; p=reject; sp=reject; adkim=s; aspf=s"
upsert "$E2B_DOMAIN" MX "0 ."
txt "$E2B_DOMAIN" "v=spf1 -all"

# 1. Template at a pinned commit.
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
curl -sfL "https://raw.githubusercontent.com/aws-samples/sample-e2b-on-aws/${SAMPLE_COMMIT}/e2b-setup-env.yml" -o "$TMP/e2b-setup-env.yml"
# predictable bucket name: verify ownership before CloudFormation reads the template from it
aws s3api put-object --bucket "$BUCKET" --key "e2b/e2b-setup-env-${SAMPLE_COMMIT}.yml" --body "$TMP/e2b-setup-env.yml" \
  --expected-bucket-owner "$ACCOUNT_ID" >/dev/null
TEMPLATE_URL="https://${BUCKET}.s3.${AWS_REGION}.amazonaws.com/e2b/e2b-setup-env-${SAMPLE_COMMIT}.yml"

# 2. Bastion key pair: the template requires a key name, but the bastion is reached only through SSM (no SSH
#    ingress), so the private key is discarded instead of being stored as a long-lived credential.
if ! aws ec2 describe-key-pairs --key-names "$KEY_NAME" --region "$AWS_REGION" >/dev/null 2>&1; then
  aws ec2 create-key-pair --key-name "$KEY_NAME" --region "$AWS_REGION" \
    --tag-specifications "ResourceType=key-pair,Tags=[{Key=Project,Value=harbor-rl-sandbox}]" \
    --query KeyFingerprint --output text >/dev/null
fi

# 3. Stack.
if ! aws cloudformation describe-stacks --stack-name "$STACK" --region "$AWS_REGION" >/dev/null 2>&1; then
  (umask 077; python3 - "$TMP/params.json" <<PY
import json, secrets, string, sys
a = string.ascii_letters + string.digits
p = {
    "Environment": "dev", "Architecture": "x86_64", "ClientInstanceType": "$CLIENT_INSTANCE_TYPE",
    "BaseDomain": "$E2B_DOMAIN", "VpcBlock": "10.50.0.0/16",
    "PublicSubnet1Block": "10.50.0.0/20", "PublicSubnet2Block": "10.50.16.0/20", "PublicSubnet3Block": "10.50.64.0/20",
    "PrivateSubnet1Block": "10.50.32.0/20", "PrivateSubnet2Block": "10.50.48.0/20", "PrivateSubnet3Block": "10.50.80.0/20",
    "AvailabilityZone1": "${AWS_REGION}a", "AvailabilityZone2": "${AWS_REGION}b", "AvailabilityZone3": "${AWS_REGION}c",
    "PublicAccess": "Private",
    "AllowRemoteSSHIPs": "127.0.0.1/32",  # no SSH from anywhere; the bastion is reached through SSM
    "KeyName": "$KEY_NAME", "DBUsername": "e2badmin",
    "DBPassword": "p1" + "".join(secrets.choice(a) for _ in range(24)),
    "AutoDeploy": "false",
}
json.dump([{"ParameterKey": k, "ParameterValue": v} for k, v in p.items()], open(sys.argv[1], "w"))
PY
  )
  aws cloudformation create-stack --stack-name "$STACK" --region "$AWS_REGION" \
    --template-url "$TEMPLATE_URL" --parameters "file://$TMP/params.json" \
    --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM CAPABILITY_AUTO_EXPAND \
    --tags Key=Project,Value=harbor-rl-sandbox >/dev/null
  rm -f "$TMP/params.json"
fi

# 4. ACM validation record (the stack waits on the certificate until this resolves), then the wildcard record.
echo "waiting for the certificate validation record..."
for _ in $(seq 1 60); do
  CERT_ARN="$(aws cloudformation describe-stack-resources --stack-name "$STACK" --region "$AWS_REGION" \
    --logical-resource-id WildcardCertificate --query 'StackResources[0].PhysicalResourceId' --output text 2>/dev/null || true)"
  if [[ "$CERT_ARN" == arn:* ]]; then
    REC="$(aws acm describe-certificate --certificate-arn "$CERT_ARN" --region "$AWS_REGION" \
      --query 'Certificate.DomainValidationOptions[0].ResourceRecord.[Name,Value]' --output text 2>/dev/null || true)"
    if [ -n "$REC" ] && [ "$REC" != "None	None" ] && [ "$REC" != "None" ]; then
      upsert "$(echo "$REC" | cut -f1)" CNAME "$(echo "$REC" | cut -f2)"
      break
    fi
  fi
  sleep 20
done
echo "waiting for stack $STACK..."
aws cloudformation wait stack-create-complete --stack-name "$STACK" --region "$AWS_REGION"
ALB_DNS="$(aws cloudformation describe-stacks --stack-name "$STACK" --region "$AWS_REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='CFNALBDNS'].OutputValue" --output text)"
upsert "*.${E2B_DOMAIN}" CNAME "$ALB_DNS"
echo "*.${E2B_DOMAIN} -> ${ALB_DNS} (internal)"

# 5. Deploy chain on the bastion (runs in the background there; poll its checkpoints).
echo "waiting for the bastion to register with SSM..."
until [ "$(aws ssm describe-instance-information --region "$AWS_REGION" \
  --filters "Key=InstanceIds,Values=$(bastion_id)" --query 'length(InstanceInformationList)' --output text)" = 1 ]; do
  sleep 15
done
bastion_run "set -e
export HOME=/root
git config --global --add safe.directory /opt/infra/sample-e2b-on-aws
cd /opt/infra/sample-e2b-on-aws
git fetch -q origin && git checkout -q $SAMPLE_COMMIT
ls /opt/.e2b-step-create-template.done >/dev/null 2>&1 && { echo 'deploy chain already complete'; exit 0; }
pgrep -f deploy-all.sh >/dev/null && { echo 'deploy chain already running'; exit 0; }
umask 077; touch /tmp/e2b.log; chmod 600 /tmp/e2b.log   # the chain prints the team API key until finalize.sh
nohup bash deploy-all.sh >> /tmp/e2b.log 2>&1 &
echo 'deploy chain started'"
echo "deploy chain running (about 45 to 60 minutes); progress: infra/e2b-selfhosted/status.sh"
while :; do
  OUT="$(bastion_run 'ls /opt/.e2b-step-*.done 2>/dev/null | sed s,/opt/.e2b-step-,, | tr "\n" " "; tail -n 3 /tmp/e2b.log | grep -c "FAILED, aborting" || true')"
  echo "  done: $(echo "$OUT" | head -1)"
  echo "$OUT" | grep -q "create-template.done" && break
  if [ "$(echo "$OUT" | sed -n 2p | tr -d '[:space:]')" != "0" ]; then
    echo "deploy chain failed; see infra/e2b-selfhosted/status.sh, fix, and re-run this script (it resumes)"; exit 1
  fi
  sleep 120
done

# 6. Tier limits, API key into Secrets Manager, log redaction.
"$HERE/finalize.sh"
echo "Next: infra/e2b-selfhosted/peer.sh, then E2B_DOMAIN=${E2B_DOMAIN} infra/e2b-selfhosted/set-secret.sh"
