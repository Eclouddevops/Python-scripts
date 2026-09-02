# Access & Login Guide

How to connect to the Ubuntu EC2 server created by this Terraform module.

---

## Which login should I use?

Pick the row that matches who you are:

| I want to… | Use | Auth | Section |
|------------|-----|------|---------|
| Give an **external user** file access | `vsftpuser` | **Password** | [→ External user](#a-external-user-vsftpuser--start-here) |
| Manage the server (shell, `sudo`) | `ubuntu` | SSH key | [→ Admin SSH](#b-admin-ssh-login) |
| **Vendor admin** (sudo + password) | `sftpvendor` | Password or key | [→ Vendor admin](#f-vendor-admin-sftpvendor--sudo) |
| Transfer files internally / scripted | `sftpuser` | SSH key | [→ Key SFTP](#c-internal-sftp-sftpuser) |
| Use a desktop app (WinSCP/FileZilla) | either | key **or** password | [→ GUI client](#d-gui-client-winscp--filezilla) |
| Use a **web browser** (no client) | `admin` or `vsftpuser` | Password | [→ Web dashboard](#e-web-dashboard-browser) |

### Good to know

- **Fixed IP** — the server has a static **Elastic IP**, so the address never changes across restarts. Get it with `terraform output elastic_ip`.
- **Storage** — all files live on a dedicated **100 GiB encrypted EBS volume** at `/srv/ftp`, separate from the OS disk.
- **Credentials** — everything is stored in **AWS Secrets Manager**; nothing is committed to Git or written to disk by Terraform.
- **Ports** — SFTP/SSH on **22**, web dashboard on **8080**.

---

## Prerequisites (do this once)

**1. Authenticate to AWS** (account `986788162487`, region `ap-south-1`):

```bash
export AWS_PROFILE=CoreProdWorkloadAccount        # Bash / Git Bash / Linux / macOS
# PowerShell:  $env:AWS_PROFILE = "CoreProdWorkloadAccount"
# CMD:         set AWS_PROFILE=CoreProdWorkloadAccount

aws sts get-caller-identity                       # should show Account: 986788162487
```

**2. Get your connection details** (run from `terraform/ubuntu-ec2-sftp/`):

```bash
terraform output
```

| Output | Example | What it is |
|--------|---------|------------|
| `instance_public_ip` / `elastic_ip` | `13.127.46.86` | The address you connect to |
| `ssh_key_secret_name` | `ubuntu-sftp-prod/ec2/ssh-private-key` | Secret with the SSH key |
| `vsftp_secret_name` | `ubuntu-sftp-prod/ftp/vsftpuser-credentials` | Secret with external user login |
| `web_dashboard_secret_name` | `ubuntu-sftp-prod/dashboard/credentials` | Secret with admin dashboard login |

> ⚠️ **Secret names depend on your deployment.** The prefix is
> `<project_name>-<environment>` (e.g. `ubuntu-sftp-prod`). Always copy the exact
> names from `terraform output` — don't guess. Using the wrong name is the most
> common cause of `ResourceNotFoundException`.

In the examples below, replace `<IP>` with your `elastic_ip`.

---

## A. External user (`vsftpuser`) — START HERE

This is the account you hand out to **external users**. It logs in with a
**username + password** (no SSH key) and can **upload and download** inside its
`files/` folder. The **same** credentials work for both **SFTP** and the
**web browser**.

### Step 1 — Get the credentials

```bash
aws secretsmanager get-secret-value \
  --secret-id ubuntu-sftp-prod/ftp/vsftpuser-credentials \
  --region ap-south-1 \
  --query SecretString --output text
```

Returns:
```json
{
  "username": "vsftpuser",
  "password": "••••••••••••••••••••••••",
  "host": "13.127.46.86",
  "port": 22,
  "protocol": "SFTP",
  "upload_dir": "files",
  "dashboard_url": "http://13.127.46.86:8080"
}
```

> 💡 **This whole JSON is what you give an external user** — it has everything
> they need for both SFTP and the browser.

### Step 2 — Connect via SFTP (command line)

```bash
sftp vsftpuser@<IP>
# enter the password when prompted
sftp> cd files            # the writable folder
sftp> put report.pdf      # upload
sftp> get data.csv        # download
sftp> bye
```

### Step 2 (alternative) — Connect via the browser

Open the `dashboard_url` (e.g. `http://<IP>:8080`) and log in as `vsftpuser`
with the same password. You'll see only your own `files/` folder.

> ⚠️ Give external parties **only** the `vsftpuser` credentials — never the SSH
> key or the `ubuntu` admin login.

---

## B. Admin SSH login

Full shell access with `sudo`, as the **`ubuntu`** user (SSH key required).

### Step 1 — Fetch the SSH private key (once)

**Linux / macOS (with `jq`):**
```bash
aws secretsmanager get-secret-value \
  --secret-id ubuntu-sftp-prod/ec2/ssh-private-key \
  --region ap-south-1 --query SecretString --output text \
  | jq -r .private_key > key.pem
chmod 600 key.pem
```

**Windows / Git Bash (no `jq` — uses Python):**
```bash
aws secretsmanager get-secret-value \
  --secret-id ubuntu-sftp-prod/ec2/ssh-private-key \
  --region ap-south-1 --query "SecretString" --output text \
  | python -c "import sys, json; print(json.load(sys.stdin)['private_key'])" > key.pem
chmod 600 key.pem
```

Check it worked:
```bash
head -1 key.pem      # should print: -----BEGIN RSA PRIVATE KEY-----
```

### Step 2 — Log in

```bash
ssh -i key.pem ubuntu@<IP>
```

---

## C. Internal SFTP (`sftpuser`)

A **key-based** SFTP account for internal or automated transfers. No shell,
chroot-jailed to its `upload/` folder. Uses the **same `key.pem`** from
section B.

```bash
sftp -i key.pem sftpuser@<IP>
sftp> cd upload           # the writable folder
sftp> put localfile.txt   # upload
sftp> get remotefile.txt  # download
sftp> bye
```

> **Note:** you can only write inside `upload/`. The top level is read-only (a
> security requirement of the chroot) — always `cd upload` first.

---

## D. GUI client (WinSCP / FileZilla)

Great for drag-and-drop. Works for both users — pick the auth that matches.

### WinSCP (Windows)

1. **New Session** → File protocol **SFTP**, Host `<IP>`, Port `22`.
2. Enter the **User name**:
   - `vsftpuser` (external) → just type the **password** on the login screen.
   - `sftpuser` (key) → **Advanced → SSH → Authentication → Private key file** →
     select `key.pem` (WinSCP offers to convert to `.ppk` — click **Yes**).
3. **Login**, then open your folder (`files/` for vsftpuser, `upload/` for sftpuser).

### FileZilla (cross-platform)

- Protocol: **SFTP - SSH File Transfer Protocol**, Host `<IP>`, Port `22`.
- **`vsftpuser` (external):** Logon Type **Normal** → User `vsftpuser` + password.
- **`sftpuser` (key):** Logon Type **Key file** → User `sftpuser` + `key.pem`.

> External users only need FileZilla/WinSCP with **User = `vsftpuser`** and the
> **password** — no key file.

---

## E. Web dashboard (browser)

[File Browser](https://filebrowser.org/) is a web file manager with a login page —
no SSH client needed. It's rooted at the FTP storage volume (`/srv/ftp`).

### Get the admin URL + login

```bash
terraform output web_dashboard_url            # e.g. http://13.127.46.86:8080

aws secretsmanager get-secret-value \
  --secret-id ubuntu-sftp-prod/dashboard/credentials \
  --region ap-south-1 --query SecretString --output text
```

### Two logins available

| Login | Password from | Sees |
|-------|---------------|------|
| `admin` | `.../dashboard/credentials` secret | **All** files on the volume |
| `vsftpuser` | `.../ftp/vsftpuser-credentials` secret | **Only** its own `files/` folder |

1. Open the URL in your browser.
2. Log in as `admin` (full access) or `vsftpuser` (external, scoped).
3. Upload / download / preview files.

> The dashboard may take **1–2 minutes** after `terraform apply` to come online
> while cloud-init installs it.

---

## F. Vendor admin (`sftpvendor`) — sudo

A vendor account with **full sudo (root) privileges** and a real login shell.
It can log in via SSH with **either its password or the SSH key**, and run
`sudo` for root access. (Unlike the SFTP users, it is *not* chroot-jailed.)

### Get the credentials

```bash
aws secretsmanager get-secret-value \
  --secret-id ubuntu-sftp-prod/admin/vendor-credentials \
  --region ap-south-1 --query SecretString --output text
```

Returns:
```json
{
  "username": "sftpvendor",
  "password": "••••••••••••",
  "host": "13.127.46.86",
  "port": 22,
  "privileges": "sudo (root)",
  "shell": "/bin/bash"
}
```

### Log in and become root

```bash
ssh sftpvendor@<IP>        # enter the password (or use -i key.pem)
sudo -i                    # become root
```

> ⚠️ This account has full control of the server. Share it only with trusted
> vendors, and consider rotating the password after use.

---

## Access summary

| Method | Login | Auth | Port | Scope |
|--------|-------|------|------|-------|
| Admin SSH | `ubuntu` | key | 22 | full shell + `sudo` |
| **Vendor admin** | **`sftpvendor`** | **password** or key | 22 | **full shell + `sudo` (root)** |
| Internal SFTP | `sftpuser` | key | 22 | `upload/` folder |
| **External SFTP** | **`vsftpuser`** | **password** | 22 | `files/` folder |
| Web dashboard (admin) | `admin` | password | 8080 | all files |
| Web dashboard (external) | `vsftpuser` | password | 8080 | `files/` folder |

All files are stored on the dedicated **100 GiB** volume at `/srv/ftp`.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `ResourceNotFoundException` | Wrong secret name, or not deployed yet | Copy the exact name from `terraform output`; run `terraform apply` |
| `Wrong credentials` on dashboard | Using `vsftpuser` before re-deploy, or wrong password | Ensure you re-applied after enabling the vsftpuser dashboard login; copy password from the secret |
| `Permission denied (publickey)` | Setup still running / wrong user / key perms | Wait ~1–2 min after apply; use `ubuntu` (SSH) or `sftpuser` (SFTP); `chmod 600 key.pem` |
| Password login rejected for `vsftpuser` | SSH still initialising, or wrong password | Wait a minute after apply; re-copy the password (watch for trailing spaces) |
| `Connection timed out` (port 22) | Your IP not allowed | Add your IP/CIDR to `allowed_ssh_cidrs` and re-apply |
| Dashboard won't load (port 8080) | Still starting, or IP blocked | Wait 1–2 min; add your IP to `allowed_web_cidrs` |
| Can't upload via SFTP | Writing to the read-only chroot root | `cd files` (or `cd upload`) first |
| `jq: command not found` | jq not installed | Use the Python one-liner in section B |

---

## Security reminders

- **Restrict access:** set `allowed_ssh_cidrs` and `allowed_web_cidrs` to your
  specific IP/CIDR in production (defaults are `0.0.0.0/0`, i.e. open to the world).
- **HTTPS:** the dashboard uses plain **HTTP** — for production, put it behind
  HTTPS (reverse proxy or an ALB with an ACM certificate).
- **Key hygiene:** delete local `key.pem` when done — you can always re-fetch it
  from Secrets Manager.
