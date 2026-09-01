# Access & Login Guide

This guide explains **every way to access** the Ubuntu EC2 instance provisioned
by this Terraform module:

1. [Admin SSH login](#1-admin-ssh-login-shell-access) — full shell (key)
2. [SFTP — key user (`sftpuser`)](#2-sftp--command-line) — secure file transfer with a key
3. [External FTP user (`vsftpuser`)](#external-ftp-user-vsftpuser--password-login) — **password login, for external users**
4. [SFTP — GUI client](#3-sftp--gui-client-winscp--filezilla) — WinSCP / FileZilla
5. [Web dashboard](#4-web-dashboard--browser-login) — browser login, no client needed

> **Storage:** all FTP/SFTP files live on a dedicated **100 GiB encrypted EBS
> volume** mounted at `/srv/ftp` — separate from the OS disk.
>
> **Fixed IP:** the server has a static **Elastic IP** — the public address
> stays the same across restarts and instance replacement, so you never have to
> update the host you connect to. Get it with `terraform output elastic_ip`.

> All credentials are stored in **AWS Secrets Manager**. Nothing is committed to
> the repo or written to disk by Terraform.

---

## Before you start

Make sure you are authenticated to the correct AWS account and region.

```bash
# Windows CMD
set AWS_PROFILE=CoreProdWorkloadAccount
# PowerShell
$env:AWS_PROFILE = "CoreProdWorkloadAccount"
# Bash / Git Bash / Linux / macOS
export AWS_PROFILE=CoreProdWorkloadAccount

# Verify — should show Account: 986788162487
aws sts get-caller-identity
```

Get the connection details Terraform produced (run from `terraform/ubuntu-ec2-sftp/`):

```bash
terraform output
```

Key outputs you'll use:

| Output | Example | What it is |
|--------|---------|------------|
| `instance_public_ip` | `13.127.46.86` | The server IP (the Elastic IP when enabled) |
| `elastic_ip` | `13.127.46.86` | The fixed Elastic IP address |
| `ssh_key_secret_name` | `ubuntu-sftp-prod/ec2/ssh-private-key` | Secret holding the SSH key |
| `web_dashboard_url` | `http://13.127.46.86:8080` | Browser dashboard URL |
| `web_dashboard_secret_name` | `ubuntu-sftp-prod/dashboard/credentials` | Secret holding dashboard login |

> **Note on names:** the secret prefix comes from `project_name`-`environment`.
> If you deployed with `project_name = "ubuntu-sftp"`, the prefix is
> `ubuntu-sftp-prod`. Always use the value from `terraform output` rather than
> guessing.

---

## Step 0: Fetch the SSH private key (once)

The private key lives in Secrets Manager. Save it to a local `.pem` file.

**With `jq` (Linux/macOS):**
```bash
aws secretsmanager get-secret-value \
  --secret-id ubuntu-sftp-prod/ec2/ssh-private-key \
  --region ap-south-1 \
  --query SecretString --output text | jq -r .private_key > key.pem
chmod 600 key.pem
```

**Without `jq` (Windows / Git Bash — uses Python instead):**
```bash
aws secretsmanager get-secret-value \
  --secret-id ubuntu-sftp-prod/ec2/ssh-private-key \
  --region ap-south-1 \
  --query "SecretString" --output text \
  | python -c "import sys, json; print(json.load(sys.stdin)['private_key'])" > key.pem
chmod 600 key.pem
```

Verify it looks right:
```bash
head -1 key.pem     # should print: -----BEGIN RSA PRIVATE KEY-----
```

---

## 1. Admin SSH login (shell access)

Use the **`ubuntu`** user for a full shell with `sudo`.

```bash
ssh -i key.pem ubuntu@<PUBLIC_IP>
```

Example:
```bash
ssh -i key.pem ubuntu@13.127.46.86
```

---

## 2. SFTP — command line

Use the **`sftpuser`** account. It is chroot-jailed with no shell — file transfer only.

```bash
sftp -i key.pem sftpuser@<PUBLIC_IP>
```

Once at the `sftp>` prompt:

```text
sftp> ls                 # you'll see the 'upload' folder
sftp> cd upload          # the writable directory
sftp> put localfile.txt  # UPLOAD from your PC
sftp> get remotefile.txt # DOWNLOAD to your PC
sftp> mkdir newfolder     # create a folder inside upload/
sftp> lls                # list files on your LOCAL machine
sftp> bye                # disconnect
```

> **Important:** You can only write inside `upload/`. The chroot root is
> intentionally read-only — always `cd upload` before uploading.

---

## External FTP user (`vsftpuser`) — password login

This is the account to give **external users**. It authenticates with a
**username + password** (no SSH key), and has full **upload and download**
access inside its `files/` directory. All data is stored on the 100 GiB FTP
volume (`/srv/ftp/vsftpuser/files`).

### Get the credentials from Secrets Manager

```bash
aws secretsmanager get-secret-value \
  --secret-id ubuntu-sftp-prod/ftp/vsftpuser-credentials \
  --region ap-south-1 \
  --query SecretString --output text
```

Returns JSON like:
```json
{
  "username": "vsftpuser",
  "password": "••••••••••••••••••••••••",
  "host": "13.127.46.86",
  "port": 22,
  "protocol": "SFTP",
  "upload_dir": "files"
}
```

### Connect (what the external user runs)

```bash
sftp vsftpuser@<PUBLIC_IP>
# ...enter the password when prompted...
sftp> cd files
sftp> put myfile.txt      # upload
sftp> get result.csv      # download
sftp> bye
```

> Give external parties **only** the `vsftpuser` credentials from the secret —
> never the SSH key or the `ubuntu` admin access.

### Same credentials in the browser dashboard

The **same** `vsftpuser` username + password also log into the [web dashboard](#4-web-dashboard--browser-login).
In the browser the user is **scoped to only their own `files/` folder** (they
can't see other users' data). So external users get **one** login that works for
both SFTP and the browser:

- **SFTP:** `sftp vsftpuser@<PUBLIC_IP>` → `cd files`
- **Browser:** open the dashboard URL → log in as `vsftpuser`

> `admin` still logs into the dashboard with full access to all files; the
> `admin` password is in the separate `.../dashboard/credentials` secret.

---

## 3. SFTP — GUI client (WinSCP / FileZilla)

### WinSCP (Windows)

1. **New Session**
   - File protocol: **SFTP**
   - Host name: `<PUBLIC_IP>`
   - Port: `22`
   - User name: `sftpuser`
2. **Advanced → SSH → Authentication → Private key file** → select `key.pem`
   (WinSCP will offer to convert to `.ppk` — click **Yes**).
3. **Login**, then open the `upload` folder and drag-and-drop files.

### FileZilla (cross-platform)

- Protocol: **SFTP - SSH File Transfer Protocol**
- Host: `<PUBLIC_IP>`, Port: `22`
- **For `sftpuser` (key):** Logon Type **Key file** → select `key.pem`
- **For `vsftpuser` (external):** Logon Type **Normal**, User `vsftpuser`, Password from the secret

> External users can simply use FileZilla/WinSCP with **User = `vsftpuser`** and
> the **password** from Secrets Manager — no key file needed.

---

## 4. Web dashboard — browser login

The [File Browser](https://filebrowser.org/) dashboard gives you a login page and
a full file manager in your browser. No SSH client needed. It manages the **same
`upload/` directory** as SFTP, so uploads appear in both.

### Get the URL and login credentials

```bash
# URL
terraform output web_dashboard_url          # e.g. http://13.127.46.86:8080

# Username + password (JSON) from Secrets Manager
aws secretsmanager get-secret-value \
  --secret-id ubuntu-sftp-prod/dashboard/credentials \
  --region ap-south-1 \
  --query SecretString --output text
```

The secret returns JSON like:
```json
{
  "username": "admin",
  "password": "••••••••••••••••••",
  "port": 8080,
  "url": "http://13.127.46.86:8080"
}
```

### Log in

Two logins are available on the dashboard:

| Login | Sees | Password source |
|-------|------|-----------------|
| `admin` | **All** files on the volume | `.../dashboard/credentials` secret |
| `vsftpuser` | **Only** its own `files/` folder | `.../ftp/vsftpuser-credentials` secret |

1. Open the `url` in your browser (e.g. `http://13.127.46.86:8080`).
2. Log in as **`admin`** (full access) or **`vsftpuser`** (external user, scoped).
3. Upload / download / preview files via the web UI.

> The dashboard may take **1–2 minutes** after `terraform apply` to come online
> while cloud-init installs and starts the service.

---

## Access summary

| Method | User / Login | Port | Best for |
|--------|--------------|------|----------|
| SSH | `ubuntu` + key | 22 | Server admin (full shell, `sudo`) |
| SFTP (key) | `sftpuser` + key | 22 | Internal / automated transfer |
| **External FTP** | **`vsftpuser` + password** | 22 | **External users (give them this only)** |
| SFTP (GUI) | `sftpuser` key **or** `vsftpuser` password | 22 | Drag-and-drop file transfer |
| Web dashboard (admin) | `admin` + password | 8080 | Browser access to all files |
| Web dashboard (external) | `vsftpuser` + password | 8080 | Browser access scoped to `files/` |

All file storage lives on the dedicated **100 GiB** volume at `/srv/ftp`.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ResourceNotFoundException` | Wrong secret name, or not deployed | Use exact name from `terraform output`; run `terraform apply` |
| `Permission denied (publickey)` | Setup still running / wrong user / bad key perms | Wait ~1 min after apply; use `sftpuser` for SFTP; `chmod 600 key.pem` |
| `Connection timed out` (SSH/SFTP) | Your IP not in `allowed_ssh_cidrs` | Add your IP/CIDR to `allowed_ssh_cidrs` and re-apply |
| Dashboard won't load | Still starting, or IP blocked | Wait 1–2 min; ensure your IP is in `allowed_web_cidrs` |
| Can't upload via SFTP | Writing to read-only chroot root | `cd upload` first |
| `jq: command not found` | jq not installed | Use the Python one-liner in Step 0 |

---

## Security reminders

- Restrict `allowed_ssh_cidrs` and `allowed_web_cidrs` to your specific IP/CIDR in production (defaults are `0.0.0.0/0`).
- The web dashboard uses plain **HTTP** — for production, front it with HTTPS (reverse proxy or ALB + ACM certificate).
- Delete any local `key.pem` when you no longer need it; you can always re-fetch it from Secrets Manager.
