###############################################################################
# Input Variables
###############################################################################

variable "aws_region" {
  description = "AWS region to deploy resources into (Mumbai)."
  type        = string
  default     = "ap-south-1"
}

variable "enable_assume_role" {
  description = <<-EOT
    Whether Terraform should assume `assume_role_arn`.
    Keep this FALSE (default) when your AWS profile already resolves to the
    target account (e.g. AWS_PROFILE=CoreProdWorkloadAccount) — otherwise the
    role would try to re-assume itself and fail with an AccessDenied error.
    Set to TRUE only when running from a different base account that is allowed
    to assume the Organization access role.
  EOT
  type        = bool
  default     = false
}

variable "assume_role_arn" {
  description = "IAM role ARN to assume in the target AWS account. Only used when enable_assume_role = true."
  type        = string
  default     = "arn:aws:iam::986788162487:role/OrganizationAccountAccessRole"
}

variable "project_name" {
  description = "Short name used to prefix and tag all resources."
  type        = string
  default     = "ubuntu-base"
}

variable "environment" {
  description = "Deployment environment (e.g. prod, dev, staging)."
  type        = string
  default     = "prod"
}

variable "instance_type" {
  description = "EC2 instance type."
  type        = string
  default     = "t3.micro"
}

variable "root_volume_size" {
  description = "Size of the root EBS volume in GiB."
  type        = number
  default     = 20
}

variable "vpc_id" {
  description = "VPC ID to launch the instance in. Leave empty to use the default VPC."
  type        = string
  default     = ""
}

variable "subnet_id" {
  description = "Subnet ID to launch the instance in. Leave empty to auto-select a default subnet."
  type        = string
  default     = ""
}

variable "associate_public_ip" {
  description = "Whether to associate a public IP address with the instance."
  type        = bool
  default     = true
}

variable "allowed_ssh_cidrs" {
  description = "List of CIDR blocks allowed to connect via SSH/SFTP (port 22). Restrict this in production."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "sftp_username" {
  description = "Dedicated SFTP user to create on the instance."
  type        = string
  default     = "sftpuser"
}

variable "sftp_upload_dir" {
  description = "Name of the writable upload directory inside the SFTP user's chroot home."
  type        = string
  default     = "upload"
}

variable "common_tags" {
  description = "Common tags applied to all resources."
  type        = map(string)
  default = {
    Project     = "ubuntu-base"
    ManagedBy   = "Terraform"
    Environment = "prod"
  }
}
