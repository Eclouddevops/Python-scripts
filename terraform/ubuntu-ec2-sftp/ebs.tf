###############################################################################
# Dedicated EBS Data Volume for FTP / SFTP storage
#
# A separate, encrypted 100 GiB volume (default) is attached to the instance
# and mounted at var.ftp_data_mount_point (default /srv/ftp) by cloud-init.
# Both the SFTP users and the web dashboard store files here, so FTP space is
# no longer limited by the small root volume.
#
# Keeping FTP data on its own volume means it survives instance replacement
# and can be resized independently.
###############################################################################

resource "aws_ebs_volume" "ftp_data" {
  availability_zone = aws_instance.this.availability_zone
  size              = var.ftp_data_volume_size
  type              = var.ftp_data_volume_type
  encrypted         = true

  tags = {
    Name    = "${local.name_prefix}-ftp-data"
    Purpose = "ftp-storage"
  }
}

resource "aws_volume_attachment" "ftp_data" {
  # Linux exposes this as a NVMe device on Nitro instances; cloud-init resolves
  # the actual device path by size/label, so the requested name is just a hint.
  device_name = "/dev/sdf"
  volume_id   = aws_ebs_volume.ftp_data.id
  instance_id = aws_instance.this.id

  # Safe detach on destroy.
  stop_instance_before_detaching = true
}
