###############################################################################
# AWS Secrets Manager
#
# Stores the generated SSH private key (and useful connection metadata) in
# Secrets Manager so it can be retrieved securely without ever landing on
# local disk. Retrieve it later with:
#
#   aws secretsmanager get-secret-value \
#     --secret-id <name> --region ap-south-1 \
#     --query SecretString --output text | jq -r .private_key > key.pem
#   chmod 600 key.pem
###############################################################################

resource "aws_secretsmanager_secret" "ssh_key" {
  name        = "${local.name_prefix}/ec2/ssh-private-key"
  description = "SSH private key for the ${local.name_prefix} Ubuntu EC2 instance (SFTP enabled)."

  # Allow immediate re-creation with the same name during testing.
  recovery_window_in_days = 0

  tags = {
    Name = "${local.name_prefix}-ssh-key"
  }
}

resource "aws_secretsmanager_secret_version" "ssh_key" {
  secret_id = aws_secretsmanager_secret.ssh_key.id

  secret_string = jsonencode({
    private_key   = tls_private_key.ssh.private_key_pem
    public_key    = tls_private_key.ssh.public_key_openssh
    key_name      = aws_key_pair.this.key_name
    instance_user = "ubuntu"
    sftp_user     = var.sftp_username
    region        = var.aws_region
  })
}
