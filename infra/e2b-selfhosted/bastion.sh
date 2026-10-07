#!/usr/bin/env bash
# Shared helper (sourced): run a shell script on the self-hosted E2B bastion through SSM Run Command and print its
# output. The script travels base64-encoded inside the command, so callers must never put secrets in it; scripts
# read secrets on the bastion itself and must not print them (SSM keeps command output in its history).
export AWS_REGION="${AWS_REGION:-us-west-2}"
STACK="${STACK:-harbor-rl-e2b}"

bastion_id() {
  aws cloudformation describe-stack-resources --stack-name "$STACK" --region "$AWS_REGION" \
    --logical-resource-id BastionInstance --query 'StackResources[0].PhysicalResourceId' --output text
}

bastion_run() {  # script text; optional timeout seconds (default 600)
  local iid script_b64 params cmd_id st
  iid="$(bastion_id)"
  script_b64="$(printf '%s' "$1" | base64 | tr -d '\n')"
  params="$(python3 -c 'import json,sys; print(json.dumps({"commands": ["echo " + sys.argv[1] + " | base64 -d | bash"], "executionTimeout": [sys.argv[2]]}))' "$script_b64" "${2:-600}")"
  cmd_id="$(aws ssm send-command --instance-ids "$iid" --region "$AWS_REGION" --document-name AWS-RunShellScript \
    --parameters "$params" --query Command.CommandId --output text)"
  while :; do
    st="$(aws ssm get-command-invocation --command-id "$cmd_id" --instance-id "$iid" --region "$AWS_REGION" \
      --query Status --output text 2>/dev/null || echo Pending)"
    case "$st" in Pending|InProgress|Delayed) sleep 3 ;; *) break ;; esac
  done
  aws ssm get-command-invocation --command-id "$cmd_id" --instance-id "$iid" --region "$AWS_REGION" \
    --query '[StandardOutputContent,StandardErrorContent]' --output text
  [ "$st" = "Success" ]
}
