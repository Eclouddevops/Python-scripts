###############################################################################
# AWS Provider
#
# Authenticates against the CoreProdWorkloadAccount by assuming the
# OrganizationAccountAccessRole. You can either:
#   1. Use an AWS profile (recommended):  export AWS_PROFILE=CoreProdWorkloadAccount
#      and remove the assume_role block below, OR
#   2. Let Terraform assume the role directly (default below).
###############################################################################

provider "aws" {
  region = var.aws_region

  # Assume the Organization access role in the target account.
  # Comment this block out if you are already using an AWS_PROFILE that
  # resolves to the correct account.
  assume_role {
    role_arn     = var.assume_role_arn
    session_name = "terraform-ubuntu-ec2-sftp"
  }

  default_tags {
    tags = var.common_tags
  }
}
