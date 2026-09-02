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
    public_key             = trimspace(tls_private_key.ssh.public_key_openssh)
    host_key_private       = tls_private_key.host.private_key_openssh
    host_key_public        = trimspace(tls_private_key.host.public_key_openssh)
    ftp_data_mount_point   = var.ftp_data_mount_point
    shared_dir             = var.ftp_shared_dir
    vsftp_user             = var.vsftp_username
    vsftp_password         = local.vsftp_password
    enable_vendor_user     = var.enable_vendor_user ? "true" : "false"
    vendor_user            = var.vendor_username
    vendor_password        = local.vendor_password
    enable_web_dashboard   = var.enable_web_dashboard ? "true" : "false"
    web_dashboard_port     = var.web_dashboard_port
    web_dashboard_user     = var.web_dashboard_admin_user
    web_dashboard_password = local.dashboard_admin_password
    enable_web_hosting     = var.enable_web_hosting ? "true" : "false"
    web_hosting_subdir     = var.web_hosting_subdir
    web_hosting_port       = var.web_hosting_port
    use_cloudflare         = var.use_cloudflare ? "true" : "false"
    cloudflare_ipv4_cidrs  = join(" ", var.cloudflare_ipv4_cidrs)
  })

  # IN-PLACE UPDATES:
  # Keep this FALSE so changing user_data does NOT destroy/recreate the running
  # instance. The updated user_data is written to the instance, but cloud-init
  # only runs user_data automatically on the FIRST boot. To (re)apply the new
  # script on the existing instance, reboot it or run it once (see the
  # user_data_rerun note in README).
  user_data_replace_on_change = false

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

  lifecycle {
    # Do NOT replace the instance just because Canonical published a newer AMI.
    ignore_changes = [ami]
  }
}
