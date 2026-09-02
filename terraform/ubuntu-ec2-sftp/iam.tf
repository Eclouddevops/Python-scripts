###############################################################################
# IAM role + instance profile
#
# Grants the EC2 instance permission to:
#   - Read the setup script from the S3 scripts bucket
#   - Use ec2-instance-connect (already handled by the package install, but
#     this ensures the SSM/Connect IAM path also works)
###############################################################################

resource "aws_iam_role" "instance" {
  name = "${local.name_prefix}-ec2-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })

  tags = {
    Name = "${local.name_prefix}-ec2-role"
  }
}

resource "aws_iam_role_policy" "read_scripts_bucket" {
  name = "${local.name_prefix}-read-scripts"
  role = aws_iam_role.instance.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["s3:GetObject", "s3:ListBucket"]
      Resource = [
        aws_s3_bucket.scripts.arn,
        "${aws_s3_bucket.scripts.arn}/*",
      ]
    }]
  })
}

resource "aws_iam_instance_profile" "instance" {
  name = "${local.name_prefix}-ec2-profile"
  role = aws_iam_role.instance.name
}
