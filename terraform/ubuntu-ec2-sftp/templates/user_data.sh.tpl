#!/bin/bash
###############################################################################
# Cloud-init user_data: Configure Ubuntu + hardened SFTP + FTP data volume
#
# - Updates packages
# - Formats & mounts the dedicated EBS data volume for FTP storage
# - Creates a key-based chroot SFTP user (sftpuser)
# - Creates a PASSWORD-based chroot SFTP user (vsftpuser) with upload/download,
#   for external users (credentials come from Secrets Manager)
# - Installs the File Browser web dashboard pointed at the FTP data volume
###############################################################################
set -euxo pipefail

SFTP_USER="${sftp_user}"
UPLOAD_DIR="${upload_dir}"
SFTP_GROUP="sftpusers"
PUBLIC_KEY="${public_key}"

# FTP data volume + external user settings
FTP_MOUNT="${ftp_data_mount_point}"
VSFTP_USER="${vsftp_user}"
VSFTP_PASS='${vsftp_password}'
VSFTP_UPLOAD_DIR="${vsftp_upload_dir}"

export DEBIAN_FRONTEND=noninteractive

# ---------------------------------------------------------------------------
# 1. System update
# ---------------------------------------------------------------------------
apt-get update -y
apt-get upgrade -y
apt-get install -y openssh-server curl

# ---------------------------------------------------------------------------
# 2. Prepare & mount the dedicated EBS data volume for FTP storage
#    On Nitro instances the extra volume shows up as an unpartitioned NVMe
#    device with no filesystem. We locate the first such disk, format it once
#    (only if empty), and mount it persistently via /etc/fstab (by UUID).
# ---------------------------------------------------------------------------
mkdir -p "$FTP_MOUNT"

# Find a block device that has NO filesystem and NO partitions (our data disk).
DATA_DEV=""
for dev in $(lsblk -dpno NAME,TYPE | awk '$2=="disk"{print $1}'); do
  # Skip the root disk (the one that has a mounted partition).
  if lsblk -no MOUNTPOINT "$dev" | grep -q "/$"; then
    continue
  fi
  # Skip disks that already have any child partition mounted at /
  ROOTCHILD=$(lsblk -no MOUNTPOINT "$dev" | grep -c "^/$" || true)
  if [ "$ROOTCHILD" -gt 0 ]; then
    continue
  fi
  FSTYPE=$(lsblk -no FSTYPE "$dev" | tr -d '[:space:]')
  HASPART=$(lsblk -no NAME "$dev" | wc -l)
  if [ -z "$FSTYPE" ] && [ "$HASPART" -eq 1 ]; then
    DATA_DEV="$dev"
    break
  fi
done

if [ -n "$DATA_DEV" ]; then
  # Format only if there is no filesystem yet (preserves data on re-runs).
  if ! blkid "$DATA_DEV" >/dev/null 2>&1; then
    mkfs.ext4 -L ftpdata "$DATA_DEV"
  fi
  UUID=$(blkid -s UUID -o value "$DATA_DEV")
  if ! grep -q "$UUID" /etc/fstab; then
    echo "UUID=$UUID $FTP_MOUNT ext4 defaults,nofail 0 2" >> /etc/fstab
  fi
  mount -a
  echo "FTP data volume ($DATA_DEV) mounted at $FTP_MOUNT"
else
  echo "WARNING: no separate data volume found; using root disk for $FTP_MOUNT"
fi

# ---------------------------------------------------------------------------
# 3. Create SFTP group
# ---------------------------------------------------------------------------
groupadd -f "$SFTP_GROUP"

# ---------------------------------------------------------------------------
# 4. Key-based SFTP user (sftpuser) — chroot to its home on the data volume
# ---------------------------------------------------------------------------
SFTP_HOME="$FTP_MOUNT/$SFTP_USER"

if ! id "$SFTP_USER" >/dev/null 2>&1; then
  useradd -g "$SFTP_GROUP" -s /usr/sbin/nologin -d "$SFTP_HOME" -M "$SFTP_USER"
fi

# Chroot root must be root-owned and not group/other-writable.
mkdir -p "$SFTP_HOME"
chown root:root "$SFTP_HOME"
chmod 755 "$SFTP_HOME"

mkdir -p "$SFTP_HOME/$UPLOAD_DIR"
chown "$SFTP_USER":"$SFTP_GROUP" "$SFTP_HOME/$UPLOAD_DIR"
chmod 755 "$SFTP_HOME/$UPLOAD_DIR"

mkdir -p "$SFTP_HOME/.ssh"
echo "$PUBLIC_KEY" > "$SFTP_HOME/.ssh/authorized_keys"
chown -R "$SFTP_USER":"$SFTP_GROUP" "$SFTP_HOME/.ssh"
chmod 700 "$SFTP_HOME/.ssh"
chmod 600 "$SFTP_HOME/.ssh/authorized_keys"

# Give the default 'ubuntu' admin user the same key.
if [ -d /home/ubuntu/.ssh ]; then
  echo "$PUBLIC_KEY" >> /home/ubuntu/.ssh/authorized_keys
  sort -u /home/ubuntu/.ssh/authorized_keys -o /home/ubuntu/.ssh/authorized_keys
fi

# ---------------------------------------------------------------------------
# 5. Password-based external SFTP user (vsftpuser) — chroot on data volume
#    Has full upload + download inside its writable directory.
# ---------------------------------------------------------------------------
VSFTP_HOME="$FTP_MOUNT/$VSFTP_USER"

if ! id "$VSFTP_USER" >/dev/null 2>&1; then
  useradd -g "$SFTP_GROUP" -s /usr/sbin/nologin -d "$VSFTP_HOME" -M "$VSFTP_USER"
fi

# Set / update the password (from Secrets Manager value).
echo "$VSFTP_USER:$VSFTP_PASS" | chpasswd

# Chroot root: root-owned, not writable by the user.
mkdir -p "$VSFTP_HOME"
chown root:root "$VSFTP_HOME"
chmod 755 "$VSFTP_HOME"

# Writable upload/download directory owned by the user.
mkdir -p "$VSFTP_HOME/$VSFTP_UPLOAD_DIR"
chown "$VSFTP_USER":"$SFTP_GROUP" "$VSFTP_HOME/$VSFTP_UPLOAD_DIR"
chmod 755 "$VSFTP_HOME/$VSFTP_UPLOAD_DIR"

# ---------------------------------------------------------------------------
# 6. Configure OpenSSH: internal-sftp + chroot for the group, and allow
#    password auth ONLY for the SFTP group (admin SSH stays key-only).
# ---------------------------------------------------------------------------
SSHD_CONFIG="/etc/ssh/sshd_config"

if grep -qE "^Subsystem\s+sftp" "$SSHD_CONFIG"; then
  sed -i "s|^Subsystem\s\+sftp.*|Subsystem sftp internal-sftp|" "$SSHD_CONFIG"
else
  echo "Subsystem sftp internal-sftp" >> "$SSHD_CONFIG"
fi

if ! grep -q "Match Group $SFTP_GROUP" "$SSHD_CONFIG"; then
cat >> "$SSHD_CONFIG" <<EOF

# ---- SFTP chroot configuration (managed by Terraform user_data) ----
Match Group $SFTP_GROUP
    ChrootDirectory %h
    ForceCommand internal-sftp
    AllowTcpForwarding no
    X11Forwarding no
    PasswordAuthentication yes
EOF
fi

# ---------------------------------------------------------------------------
# 7. Restart SSH to apply
# ---------------------------------------------------------------------------
sshd -t
systemctl restart ssh || systemctl restart sshd

echo "SFTP configured: key user '$SFTP_USER' + password user '$VSFTP_USER' (data volume: $FTP_MOUNT)"

# ---------------------------------------------------------------------------
# 8. (Optional) Web Dashboard — File Browser, rooted at the FTP data volume
#    so admins can see BOTH users' files from the browser.
# ---------------------------------------------------------------------------
if [ "${enable_web_dashboard}" = "true" ]; then
  echo "Installing File Browser web dashboard..."

  DASHBOARD_PORT="${web_dashboard_port}"
  DASHBOARD_USER="${web_dashboard_user}"
  DASHBOARD_PASS='${web_dashboard_password}'
  DATA_DIR="$FTP_MOUNT"
  FB_CONFIG_DIR="/etc/filebrowser"
  FB_DB="$FB_CONFIG_DIR/filebrowser.db"

  curl -fsSL https://raw.githubusercontent.com/filebrowser/get/master/get.sh | bash

  mkdir -p "$FB_CONFIG_DIR"

  filebrowser -d "$FB_DB" config init
  filebrowser -d "$FB_DB" config set --address 0.0.0.0 --port "$DASHBOARD_PORT" --root "$DATA_DIR"

  if ! filebrowser -d "$FB_DB" users add "$DASHBOARD_USER" "$DASHBOARD_PASS" --perm.admin 2>/dev/null; then
    filebrowser -d "$FB_DB" users update "$DASHBOARD_USER" --password "$DASHBOARD_PASS" --perm.admin
  fi

  cat > /etc/systemd/system/filebrowser.service <<EOF
[Unit]
Description=File Browser Web Dashboard
After=network.target

[Service]
ExecStart=/usr/local/bin/filebrowser -d $FB_DB
Restart=on-failure
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable filebrowser
  systemctl restart filebrowser

  echo "File Browser dashboard running on port $DASHBOARD_PORT (root: $DATA_DIR)"
fi

echo "All setup complete."
