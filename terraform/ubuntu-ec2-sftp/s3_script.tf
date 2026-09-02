###############################################################################
# S3 bucket — stores the rendered cloud-init script
#
# user_data has a hard 16 KB AWS limit. We work around it by:
#   1. Rendering the full setup script as an S3 object.
#   2. Passing a tiny bootstrap (~400 bytes) as user_data that fetches the
#      full script from S3 via the instance's IAM profile and executes it.
###############################################################################

resource "aws_s3_bucket" "scripts" {
  bucket_prefix = "${local.name_prefix}-scripts-"
  force_destroy = true

  tags = {
    Name    = "${local.name_prefix}-scripts"
    Purpose = "cloud-init user_data"
  }
}

resource "aws_s3_bucket_versioning" "scripts" {
  bucket = aws_s3_bucket.scripts.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "scripts" {
  bucket                  = aws_s3_bucket.scripts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Render and upload the full setup script.
resource "aws_s3_object" "setup_script" {
  bucket = aws_s3_bucket.scripts.id
  key    = "setup.sh"
  content = templatefile("${path.module}/templates/user_data.sh.tpl", {
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

  etag = md5(templatefile("${path.module}/templates/user_data.sh.tpl", {
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
  }))

  tags = {
    Name = "${local.name_prefix}-setup-script"
  }
}
