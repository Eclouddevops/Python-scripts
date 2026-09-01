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
| `random_password` | Generates a strong dashboard admin password |
| `aws_security_group` | Allows SSH/SFTP on port 22 (+ dashboard port when enabled) |
| `aws_instance` | Ubuntu 22.04 LTS instance (IMDSv2, encrypted gp3 root volume) |
| cloud-init `user_data` | Creates a chrooted SFTP user AND installs the File Browser dashboard |

## Key design points

- **No key on disk** — the private key is generated in-memory and written only to Secrets Manager.
- **Secure SFTP** — a dedicated `sftpuser` is chroot-jailed to its home directory, has no shell (`/usr/sbin/nologin`), key-only auth, and a writable `upload/` subdirectory. This follows the standard OpenSSH `ChrootDirectory` + `internal-sftp` pattern.
- **Browser dashboard** — [File Browser](https://filebrowser.org/) runs as a systemd service on port `8080` (configurable), points at the **same** `upload/` directory as SFTP, and requires a login. Files uploaded via SFTP appear in the dashboard and vice-versa.
- **IMDSv2 enforced** and **root volume encrypted**.

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

## Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `aws_region` | `ap-south-1` | AWS region (Mumbai) |
| `enable_assume_role` | `false` | Whether to assume `assume_role_arn` (keep false if profile already resolves to the account) |
| `assume_role_arn` | Org role ARN | Role to assume (only used when `enable_assume_role = true`) |
| `project_name` | `ubuntu-base` | Resource name prefix |
| `environment` | `prod` | Environment tag |
| `instance_type` | `t3.micro` | EC2 instance type |
| `root_volume_size` | `20` | Root EBS size (GiB) |
| `allowed_ssh_cidrs` | `["0.0.0.0/0"]` | **Restrict this in production** |
| `sftp_username` | `sftpuser` | Dedicated SFTP account |
| `sftp_upload_dir` | `upload` | Writable dir inside chroot |
| `enable_web_dashboard` | `true` | Install the File Browser web dashboard |
| `web_dashboard_port` | `8080` | Port the dashboard listens on |
| `web_dashboard_admin_user` | `admin` | Dashboard login username |
| `web_dashboard_admin_password` | `""` (auto-gen) | Dashboard password; empty = strong random, stored in Secrets Manager |
| `allowed_web_cidrs` | `["0.0.0.0/0"]` | CIDRs allowed to reach the dashboard — **restrict in production** |

## Cleanup

```bash
terraform destroy
```

## Security notes

- Change `allowed_ssh_cidrs` to your specific IP/CIDR before applying in production.
- The Secrets Manager secret uses `recovery_window_in_days = 0` for easy re-creation during testing; set a recovery window for production.
