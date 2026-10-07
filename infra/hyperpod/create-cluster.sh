#!/usr/bin/env bash
# Create the HyperPod EKS cluster (VPC, NAT, EKS, S3 lifecycle bucket, IAM, HyperPod, Helm deps)
# from the official SageMaker HyperPod cluster-setup CloudFormation template.
set -euo pipefail

REGION="${AWS_REGION:-us-west-2}"
STACK_NAME="${STACK_NAME:-harbor-rl-hp}"
TEMPLATE_URL="https://aws-sagemaker-hyperpod-cluster-setup-${REGION}-prod.s3.${REGION}.amazonaws.com/templates/main-stack-eks-based-template.yaml"
HERE="$(cd "$(dirname "$0")" && pwd)"

aws cloudformation validate-template --template-url "$TEMPLATE_URL" --region "$REGION" >/dev/null

# CAPABILITY_AUTO_EXPAND is required because the template uses Transform: AWS::LanguageExtensions
# (the HyperPod docs only list CAPABILITY_IAM and CAPABILITY_NAMED_IAM).
aws cloudformation create-stack \
  --stack-name "$STACK_NAME" \
  --template-url "$TEMPLATE_URL" \
  --parameters "file://${HERE}/params.json" \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM CAPABILITY_AUTO_EXPAND \
  --tags Key=Project,Value=harbor-rl-sandbox \
  --region "$REGION"

echo "Waiting for stack ${STACK_NAME} (typically 40 to 60 minutes)..."
aws cloudformation wait stack-create-complete --stack-name "$STACK_NAME" --region "$REGION"
aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" \
  --query 'Stacks[0].StackStatus' --output text
