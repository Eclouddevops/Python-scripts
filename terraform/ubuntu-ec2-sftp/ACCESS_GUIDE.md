# Access & Login Guide

This guide explains **every way to access** the Ubuntu EC2 instance provisioned
by this Terraform module:

1. [Admin SSH login](#1-admin-ssh-login-shell-access) — full shell
2. [SFTP — command line](#2-sftp--command-line) — secure file transfer
3. [SFTP — GUI client](#3-sftp--gui-client-winscp--filezilla) — WinSCP / FileZilla
4. [Web dashboard](#4-web-dashboard--browser-login) — browser login, no client needed

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
| `instance_public_ip` | `13.127.46.86` | The server IP |
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
- Logon Type: **Key file**
- User: `sftpuser`
- Key file: `key.pem`

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

1. Open the `url` in your browser (e.g. `http://13.127.46.86:8080`).
2. Enter the `username` and `password` from the secret.
3. Upload / download / preview files via the web UI.

> The dashboard may take **1–2 minutes** after `terraform apply` to come online
> while cloud-init installs and starts the service.

---

## Access summary

| Method | User / Login | Port | Best for |
|--------|--------------|------|----------|
| SSH | `ubuntu` + key | 22 | Server admin (full shell, `sudo`) |
| SFTP (CLI) | `sftpuser` + key | 22 | Scripted / quick file transfer |
| SFTP (GUI) | `sftpuser` + key | 22 | Drag-and-drop file transfer |
| Web dashboard | `admin` + password | 8080 | Browser access, no client install |

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
