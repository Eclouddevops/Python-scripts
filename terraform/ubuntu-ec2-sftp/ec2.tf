###############################################################################
# EC2 Instance (Ubuntu 22.04 LTS) with SFTP configured via cloud-init
###############################################################################

resource "aws_instance" "this" {
  ami                         = data.aws_ami.ubuntu.id
  instance_type               = var.instance_type
  key_name                    = aws_key_pair.this.key_name
  subnet_id                   = local.subnet_id
  vpc_security_group_ids      = [aws_security_group.this.id]
  associate_public_ip_address = var.associate_public_ip

  user_data = templatefile("${path.module}/templates/user_data.sh.tpl", {
    sftp_user              = var.sftp_username
    upload_dir             = var.sftp_upload_dir
    public_key             = trimspace(tls_private_key.ssh.public_key_openssh)
    ftp_data_mount_point   = var.ftp_data_mount_point
    vsftp_user             = var.vsftp_username
    vsftp_password         = local.vsftp_password
    vsftp_upload_dir       = var.vsftp_upload_dir
    enable_web_dashboard   = var.enable_web_dashboard ? "true" : "false"
    web_dashboard_port     = var.web_dashboard_port
    web_dashboard_user     = var.web_dashboard_admin_user
    web_dashboard_password = local.dashboard_admin_password
  })

  # Re-run user_data if the SFTP configuration changes.
  user_data_replace_on_change = true

  root_block_device {
    volume_size           = var.root_volume_size
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = true
  }

  metadata_options {
    http_tokens   = "required" # Enforce IMDSv2
    http_endpoint = "enabled"
  }

  tags = {
    Name = "${local.name_prefix}-ec2"
    OS   = "Ubuntu-22.04-LTS"
    SFTP = "enabled"
  }
}
