#!/bin/bash
###############################################################################
# Cloud-init user_data: Configure Ubuntu + hardened SFTP + FTP data volume
#
# Layout goal: files live at a SHORT shared path -> $FTP_MOUNT/$SHARED_DIR
#   e.g. /srv/ftp/data/testwebsite
#
# - Formats & mounts the dedicated EBS data volume for FTP storage
# - All SFTP users are chrooted to $FTP_MOUNT and share ONE writable folder
# - Key-based user (sftpuser) + password user (vsftpuser) both see the same data
# - Vendor admin (sudo) + File Browser dashboard all point at the same folder
###############################################################################
set -euxo pipefail

SFTP_USER="${sftp_user}"
SFTP_GROUP="sftpusers"
PUBLIC_KEY="${public_key}"

# FTP data volume + external user settings
FTP_MOUNT="${ftp_data_mount_point}"
SHARED_DIR="${shared_dir}"                 # single shared folder name, e.g. "data"
VSFTP_USER="${vsftp_user}"
VSFTP_PASS='${vsftp_password}'

# Vendor admin user (sudo) settings
ENABLE_VENDOR="${enable_vendor_user}"
VENDOR_USER="${vendor_user}"
VENDOR_PASS='${vendor_password}'

export DEBIAN_FRONTEND=noninteractive

# ---------------------------------------------------------------------------
# 1. System update
# ---------------------------------------------------------------------------
apt-get update -y
apt-get upgrade -y
apt-get install -y openssh-server curl fail2ban ec2-instance-connect

# ---------------------------------------------------------------------------
# 2. Prepare & mount the dedicated EBS data volume for FTP storage
# ---------------------------------------------------------------------------
mkdir -p "$FTP_MOUNT"

# Wait for the extra EBS volume to attach (separate Terraform resource).
echo "Waiting for the FTP data volume to attach..."
for i in $(seq 1 30); do
  if lsblk -dpno NAME,FSTYPE,TYPE | awk '$3=="disk" && $2==""' | grep -q .; then
    break
  fi
  sleep 5
done

# Find a block device with NO filesystem and NO partitions (our data disk).
DATA_DEV=""
for dev in $(lsblk -dpno NAME,TYPE | awk '$2=="disk"{print $1}'); do
  if lsblk -no MOUNTPOINT "$dev" | grep -q "/$"; then
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
# 3. Chroot + shared folder layout
#
#    $FTP_MOUNT (/srv/ftp)            <- chroot root  : MUST be root:root 0755
#      └── $SHARED_DIR (data)         <- shared files : writable by sftp group
#
#    Every SFTP user is chrooted to $FTP_MOUNT, so after login they see the
#    "$SHARED_DIR" folder and files live at the short path:
#        $FTP_MOUNT/$SHARED_DIR/<foldername>   e.g. /srv/ftp/data/testwebsite
# ---------------------------------------------------------------------------
groupadd -f "$SFTP_GROUP"

# Chroot root: owned by root, not group/other writable (sshd requirement).
chown root:root "$FTP_MOUNT"
chmod 755 "$FTP_MOUNT"

# Single shared, group-writable data directory.
SHARED_PATH="$FTP_MOUNT/$SHARED_DIR"
mkdir -p "$SHARED_PATH"
chown root:"$SFTP_GROUP" "$SHARED_PATH"
chmod 2775 "$SHARED_PATH"      # setgid so new files inherit the group

# ---------------------------------------------------------------------------
# 3b. One-time migration of files from the OLD per-user layout into the new
#     shared folder. Runs once (guarded by a marker file). Any content under
#     the previous locations is moved into $SHARED_PATH so nothing is lost when
#     switching from the deep path to the short /srv/ftp/$SHARED_DIR path.
# ---------------------------------------------------------------------------
MIGRATION_MARKER="$FTP_MOUNT/.shared-folder-migrated"
if [ ! -f "$MIGRATION_MARKER" ]; then
  for OLD in "$FTP_MOUNT/$VSFTP_USER/files" "$FTP_MOUNT/$SFTP_USER/upload"; do
    if [ -d "$OLD" ] && [ -n "$(ls -A "$OLD" 2>/dev/null)" ]; then
      echo "Migrating existing files from $OLD -> $SHARED_PATH"
      # -n = don't overwrite files already present in the destination.
      cp -a -n "$OLD"/. "$SHARED_PATH"/ 2>/dev/null || true
    fi
  done
  # Normalise ownership/permissions on migrated content.
  chown -R root:"$SFTP_GROUP" "$SHARED_PATH"
  find "$SHARED_PATH" -type d -exec chmod 2775 {} \; 2>/dev/null || true
  find "$SHARED_PATH" -type f -exec chmod 664 {} \; 2>/dev/null || true
  touch "$MIGRATION_MARKER"
  echo "Migration to shared folder complete."
fi

# ---------------------------------------------------------------------------
# 4. Key-based SFTP user (sftpuser) — chrooted to $FTP_MOUNT
# ---------------------------------------------------------------------------
if ! id "$SFTP_USER" >/dev/null 2>&1; then
  useradd -g "$SFTP_GROUP" -s /usr/sbin/nologin -d "$FTP_MOUNT" -M "$SFTP_USER"
fi

# authorized_keys must live OUTSIDE the chroot for a nologin sftp user; we place
# it under /etc so sshd (running as root, before chroot) can read it.
mkdir -p /etc/ssh/authorized_keys
echo "$PUBLIC_KEY" > "/etc/ssh/authorized_keys/$SFTP_USER"
chmod 644 "/etc/ssh/authorized_keys/$SFTP_USER"

# Give the default 'ubuntu' admin user the same key.
if [ -d /home/ubuntu/.ssh ]; then
  echo "$PUBLIC_KEY" >> /home/ubuntu/.ssh/authorized_keys
  sort -u /home/ubuntu/.ssh/authorized_keys -o /home/ubuntu/.ssh/authorized_keys
fi

# ---------------------------------------------------------------------------
# 5. Password-based external SFTP user (vsftpuser) — chrooted to $FTP_MOUNT
#    Shares the SAME $SHARED_DIR folder as sftpuser.
# ---------------------------------------------------------------------------
if ! id "$VSFTP_USER" >/dev/null 2>&1; then
  useradd -g "$SFTP_GROUP" -s /usr/sbin/nologin -d "$FTP_MOUNT" -M "$VSFTP_USER"
fi
echo "$VSFTP_USER:$VSFTP_PASS" | chpasswd

# ---------------------------------------------------------------------------
# 5b. Vendor admin user (sudo / root privileges) — real shell + password login
# ---------------------------------------------------------------------------
if [ "$ENABLE_VENDOR" = "true" ]; then
  if ! id "$VENDOR_USER" >/dev/null 2>&1; then
    useradd -m -s /bin/bash "$VENDOR_USER"
  fi
  echo "$VENDOR_USER:$VENDOR_PASS" | chpasswd
  usermod -aG sudo "$VENDOR_USER"
  # Also add to the sftp group so it can read/write the shared folder directly.
  usermod -aG "$SFTP_GROUP" "$VENDOR_USER"

  VENDOR_HOME="/home/$VENDOR_USER"
  mkdir -p "$VENDOR_HOME/.ssh"
  echo "$PUBLIC_KEY" > "$VENDOR_HOME/.ssh/authorized_keys"
  chown -R "$VENDOR_USER":"$VENDOR_USER" "$VENDOR_HOME/.ssh"
  chmod 700 "$VENDOR_HOME/.ssh"
  chmod 600 "$VENDOR_HOME/.ssh/authorized_keys"

  # Convenient symlink so the vendor reaches the shared folder quickly.
  ln -sfn "$SHARED_PATH" "$VENDOR_HOME/ftp-data"

  echo "Vendor admin user '$VENDOR_USER' created with sudo privileges."
fi

# ---------------------------------------------------------------------------
# 6. Configure OpenSSH: internal-sftp + chroot for the SFTP group.
#    authorized_keys is read from /etc/ssh/authorized_keys/<user> (outside the
#    chroot) so key-based login works for the nologin sftp users.
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
    ChrootDirectory $FTP_MOUNT
    ForceCommand internal-sftp -d /$SHARED_DIR
    AuthorizedKeysFile /etc/ssh/authorized_keys/%u
    AllowTcpForwarding no
    X11Forwarding no
    PasswordAuthentication yes
    KbdInteractiveAuthentication yes
EOF
fi

# Password login for the vendor admin user (full shell, sudo).
if [ "$ENABLE_VENDOR" = "true" ] && ! grep -q "Match User $VENDOR_USER" "$SSHD_CONFIG"; then
cat >> "$SSHD_CONFIG" <<EOF

# ---- Vendor admin password login (managed by Terraform user_data) ----
Match User $VENDOR_USER
    PasswordAuthentication yes
    KbdInteractiveAuthentication yes
EOF
fi

# ---------------------------------------------------------------------------
# 7. Restart SSH to apply
# ---------------------------------------------------------------------------
sshd -t
systemctl restart ssh || systemctl restart sshd

echo "SFTP configured. Shared folder: $SHARED_PATH (users land in /$SHARED_DIR)"

# ---------------------------------------------------------------------------
# 8. (Optional) Web Dashboard — File Browser, rooted at the SHARED folder so
#    the browser and SFTP show exactly the same short paths.
# ---------------------------------------------------------------------------
if [ "${enable_web_dashboard}" = "true" ]; then
  echo "Installing File Browser web dashboard..."

  DASHBOARD_PORT="${web_dashboard_port}"
  DASHBOARD_USER="${web_dashboard_user}"
  DASHBOARD_PASS='${web_dashboard_password}'
  DATA_DIR="$SHARED_PATH"
  FB_CONFIG_DIR="/etc/filebrowser"
  FB_DB="$FB_CONFIG_DIR/filebrowser.db"

  curl -fsSL https://raw.githubusercontent.com/filebrowser/get/master/get.sh | bash

  mkdir -p "$FB_CONFIG_DIR"

  filebrowser -d "$FB_DB" config init
  filebrowser -d "$FB_DB" config set --address 0.0.0.0 --port "$DASHBOARD_PORT" --root "$DATA_DIR"

  # Admin: full access to the shared folder.
  if ! filebrowser -d "$FB_DB" users add "$DASHBOARD_USER" "$DASHBOARD_PASS" --perm.admin 2>/dev/null; then
    filebrowser -d "$FB_DB" users update "$DASHBOARD_USER" --password "$DASHBOARD_PASS" --perm.admin
  fi

  # External user: same shared folder (single shared space, matching SFTP).
  if ! filebrowser -d "$FB_DB" users add "$VSFTP_USER" "$VSFTP_PASS" --scope "$DATA_DIR" --perm.admin=false 2>/dev/null; then
    filebrowser -d "$FB_DB" users update "$VSFTP_USER" --password "$VSFTP_PASS" --scope "$DATA_DIR" --perm.admin=false
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
