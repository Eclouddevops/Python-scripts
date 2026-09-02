###############################################################################
# Security Group
#
# SFTP runs over SSH, so only port 22 is required for file transfer + shell.
###############################################################################

resource "aws_security_group" "this" {
  name        = "${local.name_prefix}-sg"
  description = "Security group for ${local.name_prefix} Ubuntu EC2 (SSH/SFTP)."
  vpc_id      = local.vpc_id

  ingress {
    description = "SSH and SFTP access"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = var.allowed_ssh_cidrs
  }

  # Web dashboard (File Browser) — only added when enabled.
  dynamic "ingress" {
    for_each = var.enable_web_dashboard ? [1] : []
    content {
      description = "Web dashboard (File Browser) access"
      from_port   = var.web_dashboard_port
      to_port     = var.web_dashboard_port
      protocol    = "tcp"
      cidr_blocks = var.allowed_web_cidrs
    }
  }

  # Web hosting (nginx HTTP) — only added when enabled.
  dynamic "ingress" {
    for_each = var.enable_web_hosting ? [1] : []
    content {
      description = "HTTP website hosting (nginx)"
      from_port   = var.web_hosting_port
      to_port     = var.web_hosting_port
      protocol    = "tcp"
      cidr_blocks = var.allowed_web_cidrs
    }
  }

  egress {
    description = "Allow all outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${local.name_prefix}-sg"
  }
}
