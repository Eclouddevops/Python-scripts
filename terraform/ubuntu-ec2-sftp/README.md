# Ubuntu EC2 Instance with SFTP (Terraform)

Terraform configuration that provisions a hardened **Ubuntu 22.04 LTS** EC2
instance in the **CoreProdWorkloadAccount** (`986788162487`) in the
**Mumbai (`ap-south-1`)** region, with a **chroot-jailed SFTP** service, a
**browser-based file dashboard** ([File Browser](https://filebrowser.org/)) with
a login page, and the SSH private key stored securely in **AWS Secrets Manager**.

## What it creates

| Resource | Purpose |
|----------|---------|
| `tls_private_key` | Generates a fresh RSA 4096-bit SSH key pair |
| `aws_key_pair` | Registers the public key with EC2 |
| `aws_secretsmanager_secret` (+ version) | Stores the SSH private key + connection metadata securely |
| `aws_secretsmanager_secret` (dashboard) | Stores the web dashboard login (auto-generated password) |
| `aws_secretsmanager_secret` (vsftpuser) | Stores the **external FTP user** credentials (username + password) |
| `random_password` | Generates strong passwords (dashboard + vsftpuser) |
| `aws_ebs_volume` (100 GiB) + attachment | **Dedicated encrypted FTP storage volume**, mounted at `/srv/ftp` |
| `aws_eip` + association | **Elastic IP** — a fixed public IP that survives stop/start & replacement |
| `aws_security_group` | Allows SSH/SFTP on port 22 (+ dashboard port when enabled) |
| `aws_instance` | Ubuntu 22.04 LTS instance (IMDSv2, encrypted gp3 root volume) |
| cloud-init `user_data` | Mounts the FTP volume, creates the SFTP users, installs the dashboard |

## Key design points

- **Static Elastic IP** — the server is assigned a fixed public IP that stays the same across stop/start and instance replacement, so external users never have to change the host they connect to. Enabled by default (`enable_elastic_ip = true`).
- **Dedicated 100 GiB FTP storage** — a separate encrypted EBS volume is mounted at `/srv/ftp`. All FTP/SFTP users and the dashboard store files here, so FTP space is not limited by the small root disk. The volume survives instance replacement and can be resized independently.
- **Two SFTP users:**
  - `sftpuser` — **key-based** (uses the generated SSH key), for internal/automated use.
  - `vsftpuser` — **password-based**, for **external users**. Give them only these credentials (from Secrets Manager). Full upload + download inside their `files/` directory.
- **Secure SFTP** — both users are chroot-jailed on the data volume, have no shell (`/usr/sbin/nologin`), using the standard OpenSSH `ChrootDirectory` + `internal-sftp` pattern. Password auth is enabled **only** for the SFTP group; admin SSH stays key-only.
- **No key on disk** — the SSH private key is generated in-memory and written only to Secrets Manager.
- **Browser dashboard** — [File Browser](https://filebrowser.org/) runs as a systemd service on port `8080` (configurable), rooted at `/srv/ftp` so admins see every user's files. Requires a login.
- **IMDSv2 enforced** and **all volumes encrypted**.

## Prerequisites

- [Terraform](https://developer.hashicorp.com/terraform/downloads) >= 1.3
- AWS CLI configured for the target account
- `jq` (to extract the key from Secrets Manager)

Authenticate to the account:

```bash
export AWS_PROFILE=CoreProdWorkloadAccount
aws sts get-caller-identity   # should show account 986788162487
```

> **Authentication:** By default (`enable_assume_role = false`) the provider uses
> your current credentials directly. Since the `CoreProdWorkloadAccount` profile
> *already* assumes `OrganizationAccountAccessRole`, Terraform must **not** assume
> it again (a role cannot re-assume itself). Only set `enable_assume_role = true`
> when running from a different base account that is allowed to assume the role.

## Usage

```bash
cd terraform/ubuntu-ec2-sftp

# 1. (optional) copy and edit variables
cp terraform.tfvars.example terraform.tfvars

# 2. init + review
terraform init
terraform plan

# 3. apply
terraform apply
```

## Retrieve the SSH key & connect

Terraform prints ready-to-run commands as outputs. Example:

```bash
# Fetch the private key from Secrets Manager
aws secretsmanager get-secret-value \
  --secret-id ubuntu-base-prod/ec2/ssh-private-key \
  --region ap-south-1 \
  --query SecretString --output text | jq -r .private_key > ubuntu-base-prod-key.pem
chmod 600 ubuntu-base-prod-key.pem

# Admin SSH (ubuntu user)
ssh -i ubuntu-base-prod-key.pem ubuntu@<PUBLIC_IP>

# SFTP (chrooted sftpuser) — land in the jail, upload into upload/
sftp -i ubuntu-base-prod-key.pem sftpuser@<PUBLIC_IP>
sftp> cd upload
sftp> put localfile.txt
```

## Access files from your browser (Web Dashboard)

The [File Browser](https://filebrowser.org/) dashboard gives you a login page and
a full file manager (upload, download, drag-and-drop, preview) in the browser —
no SSH client needed. It manages the same `upload/` directory as SFTP.

1. Get the URL and login credentials (printed as Terraform outputs):

   ```bash
   terraform output web_dashboard_url
   # Fetch the auto-generated admin password from Secrets Manager
   aws secretsmanager get-secret-value \
     --secret-id ubuntu-base-prod/dashboard/credentials \
     --region ap-south-1 \
     --query SecretString --output text
   ```

2. Open the URL in your browser (e.g. `http://<PUBLIC_IP>:8080`) and log in with
   the `username` / `password` from the secret above.

> The dashboard may take ~1–2 minutes after `apply` to come online while
> cloud-init installs and starts the service.

**Disable it** by setting `enable_web_dashboard = false` (SFTP still works).

> 📖 **See [ACCESS_GUIDE.md](./ACCESS_GUIDE.md)** for a complete, step-by-step
> guide to all access methods (SSH, SFTP CLI/GUI, and the web dashboard login),
> including credential retrieval and troubleshooting.

## External FTP user (`vsftpuser`)

External users connect with a **username + password** (no SSH key needed). The
credentials are auto-generated and stored in Secrets Manager — hand these out to
external parties and nothing else.

```bash
# Fetch the external FTP user's username + password
aws secretsmanager get-secret-value \
  --secret-id ubuntu-base-prod/ftp/vsftpuser-credentials \
  --region ap-south-1 \
  --query SecretString --output text

# The external user then connects (they'll be prompted for the password):
sftp vsftpuser@<PUBLIC_IP>
sftp> cd files          # writable upload/download directory
sftp> put report.pdf    # upload
sftp> get data.csv      # download
```

Files land on the dedicated **100 GiB** volume at `/srv/ftp/vsftpuser/files`.

> **One login for both:** the same `vsftpuser` credentials also work in the
> **web dashboard** — external users can log in at the dashboard URL and are
> scoped to only their `files/` folder. So you share a single username/password
> and they can use SFTP *or* the browser.

## Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `aws_region` | `ap-south-1` | AWS region (Mumbai) |
| `enable_assume_role` | `false` | Whether to assume `assume_role_arn` (keep false if profile already resolves to the account) |
| `assume_role_arn` | Org role ARN | Role to assume (only used when `enable_assume_role = true`) |
| `project_name` | `ubuntu-base` | Resource name prefix |
| `environment` | `prod` | Environment tag |
| `instance_type` | `t3.large` | EC2 instance type (locked to t3.large) |
| `root_volume_size` | `20` | Root EBS size (GiB) |
| `enable_elastic_ip` | `true` | Allocate a fixed Elastic IP for the server |
| `rerun_user_data_on_change` | `true` | Apply config changes in place over SSH (no instance replacement) |
| `allowed_ssh_cidrs` | `["0.0.0.0/0"]` | **Restrict this in production** |
| `sftp_username` | `sftpuser` | Key-based SFTP account |
| `sftp_upload_dir` | `upload` | Writable dir inside chroot |
| `ftp_data_volume_size` | `100` | Size (GiB) of the dedicated FTP storage volume |
| `ftp_data_volume_type` | `gp3` | EBS type for the FTP volume |
| `ftp_data_mount_point` | `/srv/ftp` | Where the FTP volume is mounted |
| `vsftp_username` | `vsftpuser` | External password-based FTP user |
| `vsftp_password` | `""` (auto-gen) | Empty = strong random, stored in Secrets Manager |
| `vsftp_upload_dir` | `files` | Writable upload/download dir for the external user |
| `enable_web_dashboard` | `true` | Install the File Browser web dashboard |
| `web_dashboard_port` | `8080` | Port the dashboard listens on |
| `web_dashboard_admin_user` | `admin` | Dashboard login username |
| `web_dashboard_admin_password` | `""` (auto-gen) | Dashboard password; empty = strong random, stored in Secrets Manager |
| `allowed_web_cidrs` | `["0.0.0.0/0"]` | CIDRs allowed to reach the dashboard — **restrict in production** |

## In-place updates (no instance replacement)

By default the module **updates the existing instance** instead of destroying and
recreating it:

- `user_data_replace_on_change = false` — editing the cloud-init script no longer
  forces a new instance.
- `lifecycle { ignore_changes = [ami] }` — a newer Canonical AMI won't trigger a
  replacement either.
- `rerun_user_data_on_change = true` — when the script changes, Terraform re-runs
  it **over SSH on the running instance** (via a `null_resource`), so the new
  configuration takes effect immediately without downtime or a new IP.

This requires SSH (port 22) reachability as the `ubuntu` user (the module's key).
Set `rerun_user_data_on_change = false` to skip the automatic re-run (then reboot
the instance manually to apply script changes).

> The EBS data volume, Elastic IP, and Secrets Manager entries are always
> preserved across `apply`.

## Cleanup

```bash
terraform destroy
```

## Security notes

- Change `allowed_ssh_cidrs` to your specific IP/CIDR before applying in production.
- The Secrets Manager secret uses `recovery_window_in_days = 0` for easy re-creation during testing; set a recovery window for production.
