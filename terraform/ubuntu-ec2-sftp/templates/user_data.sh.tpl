#!/bin/bash
###############################################################################
# Cloud-init user_data: Configure Ubuntu + hardened SFTP
#
# - Updates packages
# - Creates a dedicated, chroot-jailed SFTP user
# - Configures OpenSSH for an "sftp-only" group with a proper chroot
# - Installs the generated SSH public key for the SFTP user
# - Sets correct ownership/permissions so SFTP works AND stays secure
###############################################################################
set -euxo pipefail

SFTP_USER="${sftp_user}"
UPLOAD_DIR="${upload_dir}"
SFTP_GROUP="sftpusers"
PUBLIC_KEY="${public_key}"

export DEBIAN_FRONTEND=noninteractive

# ---------------------------------------------------------------------------
# 1. System update
# ---------------------------------------------------------------------------
apt-get update -y
apt-get upgrade -y
apt-get install -y openssh-server

# ---------------------------------------------------------------------------
# 2. Create SFTP group + user (no shell login, only SFTP)
# ---------------------------------------------------------------------------
groupadd -f "$SFTP_GROUP"

if ! id "$SFTP_USER" >/dev/null 2>&1; then
  useradd -m -g "$SFTP_GROUP" -s /usr/sbin/nologin "$SFTP_USER"
fi

# ---------------------------------------------------------------------------
# 3. Set up the chroot jail
#    The chroot root must be owned by root:root and NOT writable by the user.
#    A writable "upload" subdirectory is created for actual transfers.
# ---------------------------------------------------------------------------
SFTP_HOME="/home/$SFTP_USER"

chown root:root "$SFTP_HOME"
chmod 755 "$SFTP_HOME"

mkdir -p "$SFTP_HOME/$UPLOAD_DIR"
chown "$SFTP_USER":"$SFTP_GROUP" "$SFTP_HOME/$UPLOAD_DIR"
chmod 755 "$SFTP_HOME/$UPLOAD_DIR"

# ---------------------------------------------------------------------------
# 4. Install the SSH public key for key-based SFTP auth
# ---------------------------------------------------------------------------
mkdir -p "$SFTP_HOME/.ssh"
echo "$PUBLIC_KEY" > "$SFTP_HOME/.ssh/authorized_keys"
chown -R "$SFTP_USER":"$SFTP_GROUP" "$SFTP_HOME/.ssh"
chmod 700 "$SFTP_HOME/.ssh"
chmod 600 "$SFTP_HOME/.ssh/authorized_keys"

# Also give the default 'ubuntu' user the same key (for admin SSH access)
if [ -d /home/ubuntu/.ssh ]; then
  echo "$PUBLIC_KEY" >> /home/ubuntu/.ssh/authorized_keys
  sort -u /home/ubuntu/.ssh/authorized_keys -o /home/ubuntu/.ssh/authorized_keys
fi

# ---------------------------------------------------------------------------
# 5. Configure OpenSSH for the chrooted SFTP group
# ---------------------------------------------------------------------------
SSHD_CONFIG="/etc/ssh/sshd_config"

# Use the internal-sftp subsystem (built into sshd, no external binary needed).
if grep -qE "^Subsystem\s+sftp" "$SSHD_CONFIG"; then
  sed -i "s|^Subsystem\s\+sftp.*|Subsystem sftp internal-sftp|" "$SSHD_CONFIG"
else
  echo "Subsystem sftp internal-sftp" >> "$SSHD_CONFIG"
fi

# Append the Match block only once.
if ! grep -q "Match Group $SFTP_GROUP" "$SSHD_CONFIG"; then
cat >> "$SSHD_CONFIG" <<EOF

# ---- SFTP chroot configuration (managed by Terraform user_data) ----
Match Group $SFTP_GROUP
    ChrootDirectory %h
    ForceCommand internal-sftp
    AllowTcpForwarding no
    X11Forwarding no
    PasswordAuthentication no
EOF
fi

# ---------------------------------------------------------------------------
# 6. Restart SSH to apply the configuration
# ---------------------------------------------------------------------------
sshd -t
systemctl restart ssh || systemctl restart sshd

echo "SFTP setup complete for user '$SFTP_USER' (chroot: $SFTP_HOME, upload dir: $UPLOAD_DIR)"

# ---------------------------------------------------------------------------
# 7. (Optional) Web Dashboard — File Browser
#    Provides browser-based file access with a login page, pointed at the
#    SAME upload directory used by SFTP so files are shared between both.
# ---------------------------------------------------------------------------
if [ "${enable_web_dashboard}" = "true" ]; then
  echo "Installing File Browser web dashboard..."

  DASHBOARD_PORT="${web_dashboard_port}"
  DASHBOARD_USER="${web_dashboard_user}"
  DASHBOARD_PASS='${web_dashboard_password}'
  DATA_DIR="$SFTP_HOME/$UPLOAD_DIR"
  FB_CONFIG_DIR="/etc/filebrowser"
  FB_DB="$FB_CONFIG_DIR/filebrowser.db"

  # Install curl if missing, then install the File Browser binary.
  apt-get install -y curl
  curl -fsSL https://raw.githubusercontent.com/filebrowser/get/master/get.sh | bash

  mkdir -p "$FB_CONFIG_DIR"

  # Initialise the database, root directory, and listen settings.
  filebrowser -d "$FB_DB" config init
  filebrowser -d "$FB_DB" config set --address 0.0.0.0 --port "$DASHBOARD_PORT" --root "$DATA_DIR"

  # Create the admin user (idempotent: update password if it already exists).
  if ! filebrowser -d "$FB_DB" users add "$DASHBOARD_USER" "$DASHBOARD_PASS" --perm.admin 2>/dev/null; then
    filebrowser -d "$FB_DB" users update "$DASHBOARD_USER" --password "$DASHBOARD_PASS" --perm.admin
  fi

  # Ensure the data directory exists and is writable by the service (root here).
  mkdir -p "$DATA_DIR"

  # Create a systemd service so the dashboard starts on boot and restarts on failure.
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
