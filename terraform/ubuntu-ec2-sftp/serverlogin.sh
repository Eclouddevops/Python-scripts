export AWS_PROFILE=CoreProdWorkloadAccount

# 1. Fetch the SSH key from Secrets Manager
aws secretsmanager get-secret-value \
  --secret-id ubuntu-sftp-prod/ec2/ssh-private-key \
  --region ap-south-1 \
  --query "SecretString" --output text \
  | python -c "import sys, json; print(json.load(sys.stdin)['private_key'])" > key.pem

# 2. Lock down permissions
chmod 600 key.pem

# 3. Verify (should print: -----BEGIN RSA PRIVATE KEY-----)
head -1 key.pem

# 4. SSH in as ubuntu
ssh -i key.pem ubuntu@43.204.195.124
