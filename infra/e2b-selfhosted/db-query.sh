#!/usr/bin/env bash
# Run one SQL statement against the self-hosted E2B database from the bastion (via SSM). The DB credentials are
# read on the bastion from Secrets Manager and never leave it. Do not select credential columns.
#
#   ./infra/e2b-selfhosted/db-query.sh "select id, max_length_hours, concurrent_instances from tiers"
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/bastion.sh"
SQL_B64="$(printf '%s' "${1:?SQL statement}" | base64 | tr -d '\n')"
bastion_run "set -euo pipefail
S=\$(grep '^CFNDBCredentialSecretName=' /opt/config.properties | cut -d= -f2)
J=\$(aws secretsmanager get-secret-value --region $AWS_REGION --secret-id \"\$S\" --query SecretString --output text)
export PGPASSWORD=\$(echo \"\$J\" | jq -r .password)
echo $SQL_B64 | base64 -d | psql -h \$(echo \"\$J\" | jq -r .host) -p \$(echo \"\$J\" | jq -r .port) \\
  -U \$(echo \"\$J\" | jq -r .username) -d \$(echo \"\$J\" | jq -r .dbname) -v ON_ERROR_STOP=1 -P pager=off"
