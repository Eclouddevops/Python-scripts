###############################################################################
# Elastic IP
#
# Allocates a static public IP and associates it with the instance so the
# server keeps the SAME public address across stop/start and instance
# replacement. Created only when var.enable_elastic_ip = true.
###############################################################################

resource "aws_eip" "this" {
  count    = var.enable_elastic_ip ? 1 : 0
  domain   = "vpc"
  instance = aws_instance.this.id

  tags = {
    Name = "${local.name_prefix}-eip"
  }

  # Ensure the instance (and its default route) exists before associating.
  depends_on = [aws_instance.this]
}

locals {
  # The address clients should use: the Elastic IP when enabled, otherwise the
  # instance's dynamic public IP.
  public_ip = var.enable_elastic_ip ? aws_eip.this[0].public_ip : aws_instance.this.public_ip
}
