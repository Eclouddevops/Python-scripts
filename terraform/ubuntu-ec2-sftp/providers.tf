###############################################################################
# AWS Provider
#
# Authentication is flexible and controlled by the `enable_assume_role` variable:
#
#   * DEFAULT (enable_assume_role = false):
#       Uses your current credentials directly. This is the correct setting when
#       your AWS profile ALREADY resolves to the target account, e.g.:
#         export AWS_PROFILE=CoreProdWorkloadAccount
#       (The CoreProdWorkloadAccount profile already assumes the
#        OrganizationAccountAccessRole, so Terraform must NOT assume it again —
#        a role cannot re-assume itself.)
#
#   * enable_assume_role = true:
#       Terraform assumes `assume_role_arn` from a DIFFERENT set of base
#       credentials (e.g. running from a management/tooling account that has
#       permission to assume the Organization access role).
###############################################################################

provider "aws" {
  region = var.aws_region

  dynamic "assume_role" {
    for_each = var.enable_assume_role ? [1] : []
    content {
      role_arn     = var.assume_role_arn
      session_name = "terraform-ubuntu-ec2-sftp"
    }
  }

  default_tags {
    tags = var.common_tags
  }
}
