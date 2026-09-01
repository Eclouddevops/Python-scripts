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
