###############################################################################
# Outputs
###############################################################################

output "instance_id" {
  description = "ID of the Ubuntu EC2 instance."
  value       = aws_instance.this.id
}

output "instance_public_ip" {
  description = "Public IP address of the instance."
  value       = aws_instance.this.public_ip
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
  value       = "ssh -i ${local.name_prefix}-key.pem ubuntu@${aws_instance.this.public_ip}"
}

output "sftp_connect_command" {
  description = "SFTP command to connect as the dedicated SFTP user."
  value       = "sftp -i ${local.name_prefix}-key.pem ${var.sftp_username}@${aws_instance.this.public_ip}"
}

###############################################################################
# Web Dashboard outputs (only meaningful when enable_web_dashboard = true)
###############################################################################

output "web_dashboard_url" {
  description = "URL to open the browser-based file dashboard (login required)."
  value       = var.enable_web_dashboard ? "http://${aws_instance.this.public_ip}:${var.web_dashboard_port}" : "disabled"
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
  value       = "sftp ${var.vsftp_username}@${aws_instance.this.public_ip}"
}

output "retrieve_vsftp_credentials_command" {
  description = "Command to fetch the external FTP user's username/password from Secrets Manager."
  value       = "aws secretsmanager get-secret-value --secret-id ${aws_secretsmanager_secret.vsftp.name} --region ${var.aws_region} --query SecretString --output text"
}
