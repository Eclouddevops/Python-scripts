###############################################################################
# Data Sources
###############################################################################

# Latest Ubuntu 22.04 LTS (Jammy) AMI published by Canonical (owner 099720109477).
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

# Fall back to the default VPC when no vpc_id is provided.
data "aws_vpc" "default" {
  count   = var.vpc_id == "" ? 1 : 0
  default = true
}

# Fall back to a default subnet when no subnet_id is provided.
data "aws_subnets" "default" {
  count = var.subnet_id == "" ? 1 : 0

  filter {
    name   = "vpc-id"
    values = [local.vpc_id]
  }
}

locals {
  name_prefix = "${var.project_name}-${var.environment}"

  vpc_id = var.vpc_id != "" ? var.vpc_id : data.aws_vpc.default[0].id

  subnet_id = var.subnet_id != "" ? var.subnet_id : data.aws_subnets.default[0].ids[0]
}
