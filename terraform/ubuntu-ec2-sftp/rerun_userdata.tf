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

  # Re-trigger whenever the rendered user_data content changes.
  triggers = {
    user_data = aws_instance.this.user_data
  }

  connection {
    type        = "ssh"
    host        = local.public_ip
    user        = "ubuntu"
    private_key = tls_private_key.ssh.private_key_pem
    timeout     = "5m"
  }

  # Fetch the current user_data from the instance metadata and execute it as
  # root. This applies the latest configuration without replacing the instance.
  provisioner "remote-exec" {
    inline = [
      "echo 'Re-applying user_data on the existing instance...'",
      "TOKEN=$(curl -sS -X PUT 'http://169.254.169.254/latest/api/token' -H 'X-aws-ec2-metadata-token-ttl-seconds: 300')",
      "curl -sS -H \"X-aws-ec2-metadata-token: $TOKEN\" http://169.254.169.254/latest/user-data -o /tmp/user_data.sh",
      "sudo bash /tmp/user_data.sh",
      "echo 'user_data re-applied successfully.'",
    ]
  }

  depends_on = [aws_instance.this, aws_eip.this]
}
