###############################################################################
# Outputs
###############################################################################

output "instance_id" {
  description = "ID of the Ubuntu EC2 instance."
  value       = aws_instance.this.id
}

output "instance_public_ip" {
  description = "Public IP address clients should use (Elastic IP when enabled, else the dynamic public IP)."
  value       = local.public_ip
}

output "elastic_ip" {
  description = "The Elastic IP address (or 'disabled' when not enabled)."
  value       = var.enable_elastic_ip ? aws_eip.this[0].public_ip : "disabled"
}

output "ssh_host_public_key" {
  description = "The stable SSH host public key the server presents (ED25519). Stays constant across rebuilds."
  value       = trimspace(tls_private_key.host.public_key_openssh)
}

output "known_hosts_line" {
  description = "Ready-to-use ~/.ssh/known_hosts entry so clients trust the server without prompts."
  value       = "${local.public_ip} ${trimspace(tls_private_key.host.public_key_openssh)}"
}

output "instance_private_ip" {
  description = "Private IP address of the instance."
  value       = aws_instance.this.private_ip
}

output "ami_id" {
  description = "AMI ID used for the instance."
  value       = data.aws_ami.ubuntu.id
}

output "ssh_key_secret_name" {
  description = "Secrets Manager secret name holding the SSH private key."
  value       = aws_secretsmanager_secret.ssh_key.name
}

output "ssh_key_secret_arn" {
  description = "Secrets Manager secret ARN holding the SSH private key."
  value       = aws_secretsmanager_secret.ssh_key.arn
}

output "retrieve_key_command" {
  description = "Command to fetch the private key from Secrets Manager to a local file."
  value       = "aws secretsmanager get-secret-value --secret-id ${aws_secretsmanager_secret.ssh_key.name} --region ${var.aws_region} --query SecretString --output text | jq -r .private_key > ${local.name_prefix}-key.pem && chmod 600 ${local.name_prefix}-key.pem"
}

output "admin_ssh_command" {
  description = "SSH command for admin access as the 'ubuntu' user."
  value       = "ssh -i ${local.name_prefix}-key.pem ubuntu@${local.public_ip}"
}

output "sftp_connect_command" {
  description = "SFTP command to connect as the dedicated SFTP user."
  value       = "sftp -i ${local.name_prefix}-key.pem ${var.sftp_username}@${local.public_ip}"
}

###############################################################################
# Web Dashboard outputs (only meaningful when enable_web_dashboard = true)
###############################################################################

output "web_dashboard_url" {
  description = "URL to open the browser-based file dashboard (login required)."
  value       = var.enable_web_dashboard ? "http://${local.public_ip}:${var.web_dashboard_port}" : "disabled"
}

output "web_dashboard_username" {
  description = "Admin username for the web dashboard login."
  value       = var.enable_web_dashboard ? var.web_dashboard_admin_user : "disabled"
}

output "web_dashboard_secret_name" {
  description = "Secrets Manager secret holding the dashboard login credentials."
  value       = var.enable_web_dashboard ? aws_secretsmanager_secret.dashboard[0].name : "disabled"
}

output "retrieve_dashboard_credentials_command" {
  description = "Command to fetch the dashboard username/password from Secrets Manager."
  value       = var.enable_web_dashboard ? "aws secretsmanager get-secret-value --secret-id ${aws_secretsmanager_secret.dashboard[0].name} --region ${var.aws_region} --query SecretString --output text" : "disabled"
}

###############################################################################
# FTP data volume outputs
###############################################################################

output "ftp_data_volume_id" {
  description = "ID of the dedicated EBS volume used for FTP storage."
  value       = aws_ebs_volume.ftp_data.id
}

output "ftp_data_volume_size_gb" {
  description = "Size of the dedicated FTP data volume (GiB)."
  value       = aws_ebs_volume.ftp_data.size
}

output "ftp_data_mount_point" {
  description = "Where the FTP data volume is mounted on the instance."
  value       = var.ftp_data_mount_point
}

output "ftp_shared_path" {
  description = "The short shared folder path on the server where all files land."
  value       = "${var.ftp_data_mount_point}/${var.ftp_shared_dir}"
}

output "website_url" {
  description = "URL of the hosted website (nginx) when web hosting is enabled."
  value = var.enable_web_hosting ? (
    var.web_hosting_port == 80 ? "http://${local.public_ip}" : "http://${local.public_ip}:${var.web_hosting_port}"
  ) : "disabled"
}

output "website_root_path" {
  description = "Server directory served by nginx (upload files here to publish them)."
  value       = var.enable_web_hosting ? "${var.ftp_data_mount_point}/${var.ftp_shared_dir}${var.web_hosting_subdir != "" ? "/${var.web_hosting_subdir}" : ""}" : "disabled"
}

###############################################################################
# External FTP user (vsftpuser) outputs
###############################################################################

output "vsftp_username" {
  description = "Username of the external, password-authenticated FTP user."
  value       = var.vsftp_username
}

output "vsftp_secret_name" {
  description = "Secrets Manager secret holding the external FTP user's credentials."
  value       = aws_secretsmanager_secret.vsftp.name
}

output "vsftp_connect_command" {
  description = "SFTP command for the external user (password auth — no key needed)."
  value       = "sftp ${var.vsftp_username}@${local.public_ip}"
}

output "retrieve_vsftp_credentials_command" {
  description = "Command to fetch the external FTP user's username/password from Secrets Manager."
  value       = "aws secretsmanager get-secret-value --secret-id ${aws_secretsmanager_secret.vsftp.name} --region ${var.aws_region} --query SecretString --output text"
}

###############################################################################
# Vendor admin user (sudo) outputs
###############################################################################

output "vendor_username" {
  description = "Username of the sudo-privileged vendor admin account."
  value       = var.enable_vendor_user ? var.vendor_username : "disabled"
}

output "vendor_ssh_command" {
  description = "SSH command for the vendor admin user (password or key)."
  value       = var.enable_vendor_user ? "ssh ${var.vendor_username}@${local.public_ip}" : "disabled"
}

output "vendor_secret_name" {
  description = "Secrets Manager secret holding the vendor admin credentials."
  value       = var.enable_vendor_user ? aws_secretsmanager_secret.vendor[0].name : "disabled"
}

output "retrieve_vendor_credentials_command" {
  description = "Command to fetch the vendor admin username/password from Secrets Manager."
  value       = var.enable_vendor_user ? "aws secretsmanager get-secret-value --secret-id ${aws_secretsmanager_secret.vendor[0].name} --region ${var.aws_region} --query SecretString --output text" : "disabled"
}
