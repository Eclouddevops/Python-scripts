#!/bin/bash
###############################################################################
# serverlogin.sh — fetch the SSH key from Secrets Manager and log in as 'ubuntu'
#
# - Auto-discovers the server IP from `terraform output` (falls back to a
#   hardcoded IP if terraform isn't available in the current directory)
# - Fetches the private key from Secrets Manager into key.pem
# - Clears any stale known_hosts entry (safe: the server uses a STABLE host key)
# - Connects as the 'ubuntu' admin user
#
# Usage:  ./serverlogin.sh
# Prereqs: awscli, python, terraform (optional), and the AWS profile below.
###############################################################################
set -euo pipefail

# ---- Config ----
export AWS_PROFILE="${AWS_PROFILE:-CoreProdWorkloadAccount}"
REGION="ap-south-1"
SECRET_ID="ubuntu-sftp-prod/ec2/ssh-private-key"
FALLBACK_IP="43.204.195.124"     # used only if terraform output is unavailable
KEY_FILE="key.pem"
SSH_USER="ubuntu"

# ---- 1. Resolve the server IP ----
# Prefer the live value from terraform; fall back to the hardcoded IP.
if command -v terraform >/dev/null 2>&1 && terraform output -raw instance_public_ip >/dev/null 2>&1; then
  SERVER_IP="$(terraform output -raw instance_public_ip)"
  echo "==> Using IP from terraform output: $SERVER_IP"
else
  SERVER_IP="$FALLBACK_IP"
  echo "==> Using fallback IP: $SERVER_IP"
fi

# ---- 2. Fetch the SSH key from Secrets Manager ----
echo "==> Fetching SSH key from Secrets Manager ($SECRET_ID)..."
aws secretsmanager get-secret-value \
  --secret-id "$SECRET_ID" \
  --region "$REGION" \
  --query "SecretString" --output text \
  | python -c "import sys, json; print(json.load(sys.stdin)['private_key'])" > "$KEY_FILE"

# Fail early if the key wasn't retrieved correctly.
if ! head -1 "$KEY_FILE" | grep -q "BEGIN .*PRIVATE KEY"; then
  echo "ERROR: Could not retrieve a valid private key."
  echo "       Check AWS_PROFILE ('$AWS_PROFILE'), your credentials, and the secret name."
  exit 1
fi
echo "==> Key retrieved OK."

# ---- 3. Lock down key permissions ----
chmod 600 "$KEY_FILE"

# ---- 4. Clear any stale host key (server may have been rebuilt) ----
# The module injects a STABLE host key, so accepting the new one is safe.
ssh-keygen -R "$SERVER_IP" >/dev/null 2>&1 || true

# ---- 5. Connect ----
echo "==> Connecting to $SSH_USER@$SERVER_IP ..."
exec ssh -i "$KEY_FILE" \
  -o StrictHostKeyChecking=accept-new \
  "$SSH_USER@$SERVER_IP"
