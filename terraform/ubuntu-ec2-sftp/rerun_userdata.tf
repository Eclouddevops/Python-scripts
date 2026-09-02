###############################################################################
# Re-run user_data IN PLACE (no instance replacement)
#
# Because user_data_replace_on_change = false, changing the cloud-init script
# does NOT recreate the instance — but cloud-init also won't re-run it on its
# own. This null_resource re-applies the script over SSH whenever the rendered
# user_data changes, so configuration updates land on the SAME running instance.
#
# Requires the private key (from Secrets Manager) to reach the instance over SSH
# as the 'ubuntu' user. Controlled by var.rerun_user_data_on_change.
###############################################################################

resource "null_resource" "rerun_user_data" {
  count = var.rerun_user_data_on_change ? 1 : 0

  # Re-trigger whenever the S3 setup script content changes (etag changes).
  triggers = {
    script_etag = aws_s3_object.setup_script.etag
  }

  connection {
    type        = "ssh"
    host        = local.public_ip
    user        = "ubuntu"
    private_key = tls_private_key.ssh.private_key_pem
    timeout     = "5m"
  }

  # Fetch the latest setup script from S3 and re-run it in place.
  provisioner "remote-exec" {
    inline = [
      "echo 'Re-applying setup script from S3 on the existing instance...'",
      "aws s3 cp s3://${aws_s3_bucket.scripts.id}/${aws_s3_object.setup_script.key} /tmp/setup.sh --region ${var.aws_region}",
      "chmod +x /tmp/setup.sh",
      "sudo bash /tmp/setup.sh 2>&1 | sudo tee /var/log/user-data-setup.log",
      "echo 'Setup script re-applied successfully.'",
    ]
  }

  depends_on = [aws_instance.this, aws_eip.this, aws_s3_object.setup_script]
}
