###############################################################################
# EC2 Instance (Ubuntu 22.04 LTS) with SFTP configured via cloud-init
###############################################################################

resource "aws_instance" "this" {
  ami                         = data.aws_ami.ubuntu.id
  instance_type               = var.instance_type
  key_name                    = aws_key_pair.this.key_name
  subnet_id                   = local.subnet_id
  vpc_security_group_ids      = [aws_security_group.this.id]
  associate_public_ip_address = var.associate_public_ip
  iam_instance_profile        = aws_iam_instance_profile.instance.name

  # TINY bootstrap (~400 bytes — well within the 16 KB AWS limit).
  # The full setup script lives in S3 (see s3_script.tf); this fetches
  # and runs it using the instance's IAM profile credentials.
  # Changing s3_object.setup_script triggers the null_resource rerun
  # (see rerun_userdata.tf) so the new script is re-applied in place.
  user_data = <<-BOOTSTRAP
    #!/bin/bash
    set -euo pipefail
    aws s3 cp s3://${aws_s3_bucket.scripts.id}/${aws_s3_object.setup_script.key} /tmp/setup.sh \
      --region ${var.aws_region}
    chmod +x /tmp/setup.sh
    bash /tmp/setup.sh 2>&1 | tee /var/log/user-data-setup.log
  BOOTSTRAP

  # IN-PLACE UPDATES:
  # Keep this FALSE so changing user_data does NOT destroy/recreate the running
  # instance. The updated user_data is written to the instance, but cloud-init
  # only runs user_data automatically on the FIRST boot. To (re)apply the new
  # script on the existing instance, reboot it or run it once (see the
  # user_data_rerun note in README).
  user_data_replace_on_change = false

  root_block_device {
    volume_size           = var.root_volume_size
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = true
  }

  metadata_options {
    http_tokens   = "required" # Enforce IMDSv2
    http_endpoint = "enabled"
  }

  tags = {
    Name = "${local.name_prefix}-ec2"
    OS   = "Ubuntu-22.04-LTS"
    SFTP = "enabled"
  }

  lifecycle {
    # Do NOT replace the instance just because Canonical published a newer AMI.
    ignore_changes = [ami]
  }
}
