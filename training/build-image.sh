#!/usr/bin/env bash
# Build the trainer image (linux/amd64, ~9 GB base) on AWS CodeBuild and push it to ECR.
# Local alternative (slow on Apple silicon, emulated amd64 plus a large upload):
#   finch build --platform linux/amd64 -f training/Dockerfile -t "$IMAGE" . && finch push "$IMAGE"
#   docker buildx build --platform linux/amd64 -f training/Dockerfile -t "$IMAGE" --push .
set -euo pipefail
export AWS_REGION="${AWS_REGION:-us-west-2}"
export ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
[ -n "$ACCOUNT_ID" ] || { echo "could not resolve AWS account id"; exit 1; }
export BUCKET="harbor-rl-sandbox-${ACCOUNT_ID}-${AWS_REGION}"
REGISTRY="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
TAG="${TAG:?set TAG (trainer image tag, e.g. v10)}"
IMAGE="${REGISTRY}/harbor-rl/trainer:${TAG}"
PROJECT=harbor-rl-trainer-build
ROLE=harbor-rl-codebuild
TAGS='Key=Project,Value=harbor-rl-sandbox'
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# One-time setup: bucket, ECR repo, CodeBuild role and project.
# The bucket name is predictable, so every access checks that this account owns it (bucket squatting).
if ! aws s3api head-bucket --bucket "$BUCKET" --expected-bucket-owner "$ACCOUNT_ID" 2>/dev/null; then
  aws s3api create-bucket --bucket "$BUCKET" --region "$AWS_REGION" \
    --create-bucket-configuration LocationConstraint="$AWS_REGION" >/dev/null
  aws s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
  aws s3api put-bucket-tagging --bucket "$BUCKET" --tagging 'TagSet=[{Key=Project,Value=harbor-rl-sandbox}]'
fi
aws ecr describe-repositories --repository-names harbor-rl/trainer --region "$AWS_REGION" >/dev/null 2>&1 || \
  aws ecr create-repository --repository-name harbor-rl/trainer --region "$AWS_REGION" --tags "$TAGS" \
    --image-scanning-configuration scanOnPush=true >/dev/null
if ! aws iam get-role --role-name "$ROLE" >/dev/null 2>&1; then
  aws iam create-role --role-name "$ROLE" --tags "$TAGS" \
    --assume-role-policy-document "$(envsubst < "${ROOT}/infra/codebuild/codebuild-trust.json")" >/dev/null
  aws iam put-role-policy --role-name "$ROLE" --policy-name codebuild \
    --policy-document "$(envsubst < "${ROOT}/infra/codebuild/codebuild-policy.json")"
  sleep 10
fi
# Trust is (re)applied on every run: only this account's harbor-rl-trainer-build project can assume the role.
aws iam update-assume-role-policy --role-name "$ROLE" \
  --policy-document "$(envsubst < "${ROOT}/infra/codebuild/codebuild-trust.json")"
if ! aws codebuild batch-get-projects --names "$PROJECT" --region "$AWS_REGION" --query 'projects[0].name' --output text | grep -q "$PROJECT"; then
  aws codebuild create-project --region "$AWS_REGION" --name "$PROJECT" \
    --source "type=S3,location=${BUCKET}/codebuild/trainer-src.zip,buildspec=infra/codebuild/buildspec.yml" \
    --artifacts type=NO_ARTIFACTS \
    --environment "type=LINUX_CONTAINER,image=aws/codebuild/amazonlinux-x86_64-standard:5.0,computeType=BUILD_GENERAL1_LARGE,privilegedMode=true" \
    --service-role "$(aws iam get-role --role-name "$ROLE" --query Role.Arn --output text)" \
    --timeout-in-minutes 90 --tags key=Project,value=harbor-rl-sandbox >/dev/null
fi

# Upload the build context and build.
TMP="$(mktemp -d)"
(cd "$ROOT" && zip -qr "$TMP/src.zip" training agentcore/harbor_agentcore bench tasks/train tasks/heldout tasks/image/warmup.sh infra/codebuild/buildspec.yml -x '*/__pycache__/*')
aws s3api put-object --bucket "$BUCKET" --key codebuild/trainer-src.zip --body "$TMP/src.zip" \
  --expected-bucket-owner "$ACCOUNT_ID" >/dev/null
BUILD_ID="$(aws codebuild start-build --region "$AWS_REGION" --project-name "$PROJECT" \
  --environment-variables-override name=REGISTRY,value="$REGISTRY" name=IMAGE,value="$IMAGE" \
  --query build.id --output text)"
echo "CodeBuild ${BUILD_ID}"
while true; do
  STATUS="$(aws codebuild batch-get-builds --ids "$BUILD_ID" --region "$AWS_REGION" --query 'builds[0].buildStatus' --output text)"
  [ "$STATUS" != "IN_PROGRESS" ] && break
  sleep 20
done
echo "status: $STATUS"; [ "$STATUS" = "SUCCEEDED" ] && echo "$IMAGE"
