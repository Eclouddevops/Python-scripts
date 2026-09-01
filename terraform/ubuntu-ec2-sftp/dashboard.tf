###############################################################################
# Web Dashboard credentials (File Browser)
#
# Generates a strong admin password (unless one is supplied) and stores the
# dashboard login credentials + URL in AWS Secrets Manager.
###############################################################################

resource "random_password" "dashboard_admin" {
  count   = var.enable_web_dashboard && var.web_dashboard_admin_password == "" ? 1 : 0
  length  = 20
  special = true
  # Avoid characters that are awkward on shell/URL/JSON round-trips.
  override_special = "!@#%^*-_=+"
}

locals {
  dashboard_admin_password = var.enable_web_dashboard ? (
    var.web_dashboard_admin_password != "" ? var.web_dashboard_admin_password : random_password.dashboard_admin[0].result
  ) : ""
}

resource "aws_secretsmanager_secret" "dashboard" {
  count       = var.enable_web_dashboard ? 1 : 0
  name        = "${local.name_prefix}/dashboard/credentials"
  description = "Web dashboard (File Browser) login credentials for ${local.name_prefix}."

  recovery_window_in_days = 0

  tags = {
    Name = "${local.name_prefix}-dashboard-creds"
  }
}

resource "aws_secretsmanager_secret_version" "dashboard" {
  count     = var.enable_web_dashboard ? 1 : 0
  secret_id = aws_secretsmanager_secret.dashboard[0].id

  secret_string = jsonencode({
    username = var.web_dashboard_admin_user
    password = local.dashboard_admin_password
    port     = var.web_dashboard_port
    url      = "http://${aws_instance.this.public_ip}:${var.web_dashboard_port}"
  })
}
