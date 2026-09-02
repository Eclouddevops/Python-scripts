###############################################################################
# Vendor admin user credentials (sudo / root privileges)
#
# Stores the sudo-privileged vendor account credentials in AWS Secrets Manager,
# consistent with the other accounts. This user has a real login shell and full
# sudo access, and can log in via SSH with either the password or the SSH key.
###############################################################################

# Auto-generate a strong password unless one is explicitly supplied. This keeps
# the plaintext password out of the code/Git — it only exists in Secrets Manager.
resource "random_password" "vendor" {
  count            = var.enable_vendor_user && var.vendor_password == "" ? 1 : 0
  length           = 20
  special          = true
  override_special = "!@#%^*-_=+"
}

locals {
  vendor_password = var.enable_vendor_user ? (
    var.vendor_password != "" ? var.vendor_password : random_password.vendor[0].result
  ) : ""
}

resource "aws_secretsmanager_secret" "vendor" {
  count       = var.enable_vendor_user ? 1 : 0
  name        = "${local.name_prefix}/admin/vendor-credentials"
  description = "Sudo-privileged vendor admin login for ${local.name_prefix}."

  recovery_window_in_days = 0

  tags = {
    Name = "${local.name_prefix}-vendor-creds"
  }
}

resource "aws_secretsmanager_secret_version" "vendor" {
  count     = var.enable_vendor_user ? 1 : 0
  secret_id = aws_secretsmanager_secret.vendor[0].id

  secret_string = jsonencode({
    username   = var.vendor_username
    password   = local.vendor_password
    host       = local.public_ip
    port       = 22
    privileges = "sudo (root)"
    shell      = "/bin/bash"
    note       = "Admin user with sudo. SSH: ssh ${var.vendor_username}@${local.public_ip} (password or key). Run 'sudo -i' for root."
  })
}
