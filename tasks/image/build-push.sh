#!/usr/bin/env bash
# Build the shared task base image for linux/amd64 + linux/arm64 with Finch and push the image index to ECR.
# Docker equivalent: docker buildx build --platform linux/amd64,linux/arm64 -t "$IMAGE" --push tasks/image
set -euo pipefail
REGION="${AWS_REGION:-us-west-2}"
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
REGISTRY="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
TAG="${TAG:?set TAG (image tag to build, e.g. v2)}"
IMAGE="${REGISTRY}/harbor-rl/tasks-base:${TAG}"
HERE="$(cd "$(dirname "$0")" && pwd)"

aws ecr describe-repositories --repository-names harbor-rl/tasks-base --region "$REGION" >/dev/null 2>&1 || \
  aws ecr create-repository --repository-name harbor-rl/tasks-base --region "$REGION" \
    --image-scanning-configuration scanOnPush=true --tags Key=Project,Value=harbor-rl-sandbox >/dev/null
aws ecr get-login-password --region "$REGION" | finch login --username AWS --password-stdin "$REGISTRY"
finch build --platform linux/amd64,linux/arm64 -t "$IMAGE" "$HERE"
finch push --platform linux/amd64,linux/arm64 "$IMAGE"
echo "$IMAGE"
