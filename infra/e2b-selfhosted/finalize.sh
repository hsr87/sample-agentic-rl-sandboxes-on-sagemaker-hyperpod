#!/usr/bin/env bash
# Post-deploy settings for self-hosted E2B, run on the bastion through SSM (deploy.sh calls it; safe to re-run).
#
#   ./infra/e2b-selfhosted/finalize.sh            # keep the current team API key
#   ROTATE=1 ./infra/e2b-selfhosted/finalize.sh   # issue a new team API key first (re-seeds the team:
#                                                 # its templates are deleted, so rebuild them afterwards)
#
# 1. Team tier: Harbor creates E2B sandboxes with a 24 h timeout and the benchmark runs up to 128 at once, but the
#    sample seeds tier base_v1 with max_length_hours=1 and concurrent_instances=20.
# 2. Team API key: stored in Secrets Manager (harbor-rl-e2b/team-api-key) on the bastion itself. It is never
#    printed, so it does not land in the SSM command history; set-secret.sh reads it from Secrets Manager.
# 3. The sample's deploy log prints the key; it is redacted, and the local config file is made root-only.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/bastion.sh"
SECRET_ID="${SECRET_ID:-harbor-rl-e2b/team-api-key}"
MAX_HOURS="${MAX_HOURS:-24}"
MAX_SANDBOXES="${MAX_SANDBOXES:-1000}"

bastion_run "$(cat <<EOF
set -euo pipefail
export HOME=/root AWS_REGION=$AWS_REGION
cd /opt/infra/sample-e2b-on-aws
if [ "${ROTATE:-}" = 1 ]; then
  bash infra-iac/db/init-db.sh >/dev/null 2>&1   # re-seed: new team id and API key (output holds the key)
  echo "team API key rotated"
fi
chmod 600 /opt/config.properties /opt/infra/sample-e2b-on-aws/infra-iac/db/config.json 2>/dev/null || true

S=\$(grep '^CFNDBCredentialSecretName=' /opt/config.properties | cut -d= -f2)
J=\$(aws secretsmanager get-secret-value --secret-id "\$S" --query SecretString --output text)
PGPASSWORD=\$(echo "\$J" | jq -r .password) psql -h \$(echo "\$J" | jq -r .host) -p \$(echo "\$J" | jq -r .port) \
  -U \$(echo "\$J" | jq -r .username) -d \$(echo "\$J" | jq -r .dbname) -v ON_ERROR_STOP=1 -tAc \
  "update tiers set max_length_hours = $MAX_HOURS, concurrent_instances = $MAX_SANDBOXES where id = 'base_v1' returning id, max_length_hours, concurrent_instances"

umask 077
F=\$(mktemp)
grep -m1 '^teamApiKey=' /opt/config.properties | cut -d= -f2- | tr -d '\n' > "\$F"
[ -s "\$F" ] || { echo "teamApiKey not found (deploy chain not finished?)"; rm -f "\$F"; exit 1; }
if aws secretsmanager describe-secret --secret-id "$SECRET_ID" >/dev/null 2>&1; then
  aws secretsmanager put-secret-value --secret-id "$SECRET_ID" --secret-string "file://\$F" >/dev/null
else
  aws secretsmanager create-secret --name "$SECRET_ID" --secret-string "file://\$F" \
    --description "Self-hosted E2B team API key (harbor-rl)" --tags Key=Project,Value=harbor-rl-sandbox >/dev/null
fi
rm -f "\$F"
echo "team API key stored in Secrets Manager: $SECRET_ID"

sed -i -E 's/(Team API Key:|E2B_API_KEY=)[[:space:]]*[^[:space:]]+/\1 <redacted>/g' /tmp/e2b.log 2>/dev/null || true
echo "deploy log redacted"
EOF
)"
