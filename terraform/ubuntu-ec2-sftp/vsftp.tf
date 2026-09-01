###############################################################################
# External FTP user "vsftpuser" credentials
#
# Generates a strong password (unless one is supplied) for the external,
# password-authenticated SFTP account and stores it in AWS Secrets Manager.
# External users are given ONLY these "vsftpuser" credentials.
###############################################################################

resource "random_password" "vsftp" {
  count            = var.vsftp_password == "" ? 1 : 0
  length           = 24
  special          = true
  override_special = "!@#%^*-_=+"
}

locals {
  vsftp_password = var.vsftp_password != "" ? var.vsftp_password : random_password.vsftp[0].result
}

resource "aws_secretsmanager_secret" "vsftp" {
  name        = "${local.name_prefix}/ftp/vsftpuser-credentials"
  description = "External FTP (vsftpuser) login credentials for ${local.name_prefix}. Give these to external users."

  recovery_window_in_days = 0

  tags = {
    Name = "${local.name_prefix}-vsftpuser-creds"
  }
}

resource "aws_secretsmanager_secret_version" "vsftp" {
  secret_id = aws_secretsmanager_secret.vsftp.id

  secret_string = jsonencode({
    username   = var.vsftp_username
    password   = local.vsftp_password
    host       = local.public_ip
    port       = 22
    protocol   = "SFTP"
    upload_dir = var.vsftp_upload_dir
    note       = "Connect with: sftp ${var.vsftp_username}@${local.public_ip} (password auth). Files live under '${var.vsftp_upload_dir}'."
  })
}
