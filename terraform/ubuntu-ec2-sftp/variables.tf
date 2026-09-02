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

variable "enable_elastic_ip" {
  description = <<-EOT
    Whether to allocate an Elastic IP and associate it with the instance so the
    server keeps a FIXED public IP across stop/start and instance replacement.
    Recommended for SFTP/FTP so external users don't have to update the host.
  EOT
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

variable "ftp_shared_dir" {
  description = <<-EOT
    Name of the single SHARED folder under the FTP mount that all SFTP users and
    the web dashboard read/write. Files land at a short path:
    <ftp_data_mount_point>/<ftp_shared_dir>/<yourfolder>  e.g. /srv/ftp/data/testwebsite
  EOT
  type        = string
  default     = "data"
}

###############################################################################
# FTP Data Volume (dedicated EBS volume for FTP/SFTP storage)
###############################################################################

variable "ftp_data_volume_size" {
  description = "Size (GiB) of the dedicated EBS data volume used for FTP/SFTP storage."
  type        = number
  default     = 100
}

variable "ftp_data_volume_type" {
  description = "EBS volume type for the FTP data volume."
  type        = string
  default     = "gp3"
}

variable "ftp_data_mount_point" {
  description = "Filesystem path where the FTP data volume is mounted on the instance."
  type        = string
  default     = "/srv/ftp"
}

###############################################################################
# External FTP user (password-authenticated) — "vsftpuser"
###############################################################################

variable "vsftp_username" {
  description = "Username for the external, password-authenticated FTP/SFTP account with upload + download access."
  type        = string
  default     = "vsftpuser"
}

variable "vsftp_password" {
  description = <<-EOT
    Password for the external FTP user. Leave empty to auto-generate a strong
    random password (recommended) — it is stored in AWS Secrets Manager so
    external users can be given the "vsftpuser" credentials only.
  EOT
  type        = string
  default     = ""
  sensitive   = true
}

###############################################################################
# Vendor admin user (sudo/root privileges, password + SSH login)
###############################################################################

variable "enable_vendor_user" {
  description = "Whether to create a sudo-privileged vendor user with password login."
  type        = bool
  default     = true
}

variable "vendor_username" {
  description = "Username for the sudo-privileged vendor account (full shell + sudo)."
  type        = string
  default     = "sftpvendor"
}

variable "vendor_password" {
  description = <<-EOT
    Password for the vendor admin user (sudo/root). Leave EMPTY (default) to
    auto-generate a strong random password that is stored in AWS Secrets Manager
    and retrieved from there — no plaintext password is kept in the code/Git.
    Set a value only if you must use a specific password.
  EOT
  type        = string
  default     = ""
  sensitive   = true
}

###############################################################################
# Web Dashboard (browser-based SFTP access via File Browser)
###############################################################################

variable "enable_web_dashboard" {
  description = "Whether to install the File Browser web dashboard for browser-based file access."
  type        = bool
  default     = true
}

variable "web_dashboard_port" {
  description = "TCP port the web dashboard listens on."
  type        = number
  default     = 8080
}

variable "web_dashboard_admin_user" {
  description = "Admin username for the web dashboard login."
  type        = string
  default     = "admin"
}

variable "web_dashboard_admin_password" {
  description = <<-EOT
    Admin password for the web dashboard login. Leave empty to auto-generate a
    strong random password (recommended) — it will be stored in Secrets Manager.
  EOT
  type        = string
  default     = ""
  sensitive   = true
}

variable "allowed_web_cidrs" {
  description = "List of CIDR blocks allowed to reach the web dashboard port. Restrict this in production."
  type        = list(string)
  default     = ["0.0.0.0/0"]
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
