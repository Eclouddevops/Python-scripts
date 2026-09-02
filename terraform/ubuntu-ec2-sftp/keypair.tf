###############################################################################
# SSH Key Pair
#
# Generates a fresh RSA 4096-bit key pair with the TLS provider. The public
# key is registered as an EC2 key pair, and the private key is stored securely
# in AWS Secrets Manager (see secrets.tf). The private key is never written
# to disk by Terraform.
###############################################################################

resource "tls_private_key" "ssh" {
  algorithm = "RSA"
  rsa_bits  = 4096
}

resource "aws_key_pair" "this" {
  key_name   = "${local.name_prefix}-keypair"
  public_key = tls_private_key.ssh.public_key_openssh

  tags = {
    Name = "${local.name_prefix}-keypair"
  }
}

###############################################################################
# Stable SSH HOST key
#
# Generated once by Terraform and injected into the instance via user_data, so
# the server presents the SAME host key even after a rebuild/resize. This stops
# the "REMOTE HOST IDENTIFICATION HAS CHANGED" warning from appearing when the
# instance is recreated. Kept in Terraform state (and can be stored in Secrets
# Manager if desired). ED25519 is used (modern, matches OpenSSH defaults).
###############################################################################

resource "tls_private_key" "host" {
  algorithm = "ED25519"
}
