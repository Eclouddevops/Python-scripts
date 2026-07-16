# =============================================================================
# AWS EC2 Instance - Terraform Configuration
# Instance: 8 vCPU, 16GB RAM, 80GB Storage, Ubuntu
# Key Pair: Auto-created and stored in AWS Secrets Manager
# =============================================================================

terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }
}

# =============================================================================
# VARIABLES
# =============================================================================

variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
  default     = "us-east-1"
}

variable "instance_name" {
  description = "Name tag for the EC2 instance"
  type        = string
  default     = "ubuntu-server"
}

variable "instance_type" {
  description = "EC2 instance type (8 vCPU, 16GB RAM)"
  type        = string
  default     = "m5.2xlarge"
}

variable "root_volume_size" {
  description = "Root EBS volume size in GB"
  type        = number
  default     = 80
}

variable "key_pair_name" {
  description = "Name of the SSH key pair to create"
  type        = string
  default     = "ec2-ubuntu-key"
}

variable "allowed_ssh_cidr" {
  description = "CIDR block allowed to SSH into the instance"
  type        = string
  default     = "0.0.0.0/0"
}

variable "environment" {
  description = "Environment tag (e.g., dev, staging, production)"
  type        = string
  default     = "dev"
}

variable "vpc_id" {
  description = "VPC ID to launch the instance in (leave empty for default VPC)"
  type        = string
  default     = ""
}

variable "subnet_id" {
  description = "Subnet ID to launch the instance in (leave empty for default)"
  type        = string
  default     = ""
}

# =============================================================================
# PROVIDER
# =============================================================================

provider "aws" {
  region = var.aws_region
}

# =============================================================================
# DATA SOURCES
# =============================================================================

# Get latest Ubuntu 22.04 LTS AMI
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
}

# Get default VPC if no VPC ID provided
data "aws_vpc" "default" {
  default = true
}

# =============================================================================
# TLS PRIVATE KEY & AWS KEY PAIR
# Auto-generates an SSH key pair and registers it with AWS
# =============================================================================

resource "tls_private_key" "ec2_key" {
  algorithm = "RSA"
  rsa_bits  = 4096
}

resource "aws_key_pair" "ec2_key_pair" {
  key_name   = var.key_pair_name
  public_key = tls_private_key.ec2_key.public_key_openssh

  tags = {
    Name        = var.key_pair_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# =============================================================================
# AWS SECRETS MANAGER - Store SSH Private Key
# =============================================================================

resource "aws_secretsmanager_secret" "ec2_ssh_key" {
  name        = "ec2/${var.instance_name}/ssh-private-key"
  description = "SSH private key for EC2 instance: ${var.instance_name} (Key Pair: ${var.key_pair_name})"

  tags = {
    Name        = "${var.instance_name}-ssh-key"
    Environment = var.environment
    KeyPairName = var.key_pair_name
    ManagedBy   = "terraform"
  }
}

resource "aws_secretsmanager_secret_version" "ec2_ssh_key_value" {
  secret_id = aws_secretsmanager_secret.ec2_ssh_key.id

  secret_string = jsonencode({
    private_key      = tls_private_key.ec2_key.private_key_pem
    public_key       = tls_private_key.ec2_key.public_key_openssh
    key_pair_name    = aws_key_pair.ec2_key_pair.key_name
    instance_name    = var.instance_name
    ssh_user         = "ubuntu"
    created_by       = "terraform"
  })
}

# =============================================================================
# SECURITY GROUP
# =============================================================================

resource "aws_security_group" "ec2_sg" {
  name        = "${var.instance_name}-sg"
  description = "Security group for ${var.instance_name} EC2 instance"
  vpc_id      = var.vpc_id != "" ? var.vpc_id : data.aws_vpc.default.id

  # SSH access
  ingress {
    description = "SSH access"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ssh_cidr]
  }

  # HTTP access
  ingress {
    description = "HTTP access"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # HTTPS access
  ingress {
    description = "HTTPS access"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # All outbound traffic
  egress {
    description = "All outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "${var.instance_name}-sg"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# =============================================================================
# EC2 INSTANCE
# =============================================================================

resource "aws_instance" "ec2" {
  ami                         = data.aws_ami.ubuntu.id
  instance_type               = var.instance_type
  key_name                    = aws_key_pair.ec2_key_pair.key_name
  vpc_security_group_ids      = [aws_security_group.ec2_sg.id]
  subnet_id                   = var.subnet_id != "" ? var.subnet_id : null
  associate_public_ip_address = true

  root_block_device {
    volume_size           = var.root_volume_size
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = true
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  tags = {
    Name        = var.instance_name
    Environment = var.environment
    OS          = "Ubuntu 22.04 LTS"
    ManagedBy   = "terraform"
  }

  depends_on = [aws_key_pair.ec2_key_pair]
}

# =============================================================================
# ELASTIC IP (Static Public IP)
# =============================================================================

resource "aws_eip" "ec2_eip" {
  instance = aws_instance.ec2.id
  domain   = "vpc"

  tags = {
    Name        = "${var.instance_name}-eip"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# =============================================================================
# OUTPUTS
# =============================================================================

output "instance_id" {
  description = "EC2 instance ID"
  value       = aws_instance.ec2.id
}

output "instance_public_ip" {
  description = "Elastic IP address of the instance"
  value       = aws_eip.ec2_eip.public_ip
}

output "instance_private_ip" {
  description = "Private IP address of the instance"
  value       = aws_instance.ec2.private_ip
}

output "instance_type" {
  description = "Instance type"
  value       = aws_instance.ec2.instance_type
}

output "ami_id" {
  description = "AMI ID used"
  value       = data.aws_ami.ubuntu.id
}

output "security_group_id" {
  description = "Security group ID"
  value       = aws_security_group.ec2_sg.id
}

output "key_pair_name" {
  description = "AWS Key Pair name assigned to the instance"
  value       = aws_key_pair.ec2_key_pair.key_name
}

output "secrets_manager_secret_name" {
  description = "Secrets Manager secret name containing the SSH private key"
  value       = aws_secretsmanager_secret.ec2_ssh_key.name
}

output "secrets_manager_secret_arn" {
  description = "Secrets Manager secret ARN"
  value       = aws_secretsmanager_secret.ec2_ssh_key.arn
}

output "ssh_retrieve_key_command" {
  description = "AWS CLI command to retrieve SSH private key from Secrets Manager"
  value       = "aws secretsmanager get-secret-value --secret-id ec2/${var.instance_name}/ssh-private-key --query SecretString --output text | jq -r '.private_key' > ${var.key_pair_name}.pem && chmod 600 ${var.key_pair_name}.pem"
}

output "ssh_command" {
  description = "SSH command to connect (after retrieving key from Secrets Manager)"
  value       = "ssh -i ${var.key_pair_name}.pem ubuntu@${aws_eip.ec2_eip.public_ip}"
}
