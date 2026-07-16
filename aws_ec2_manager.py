#!/usr/bin/env python3
"""
AWS EC2 Instance Manager & SSH Connector
=========================================
- Connect to EC2 instance by name
- Auto-start if stopped, auto-SSH via Secrets Manager
- Track usage time and show detailed cost report
- Real daily costs from AWS Cost Explorer + accumulated totals
- Smart, clean cost display when session ends

Usage: python3 aws_ec2_manager.py
Prerequisites: pip install boto3
IAM Permissions: ec2:*, secretsmanager:GetSecretValue, ce:GetCostAndUsage
"""

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone, timedelta

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
except ImportError:
    print("Error: boto3 is required. Install it with: pip install boto3")
    sys.exit(1)

# =============================================================================
# CONFIGURATION
# =============================================================================

DEFAULT_SSH_USER = "ubuntu"
SECRET_NAME_PATTERN = "ec2/{instance_name}/ssh-private-key"

# On-Demand pricing (USD/hr) - us-east-1
PRICING = {
    "t2.nano": 0.0058, "t2.micro": 0.0116, "t2.small": 0.023,
    "t2.medium": 0.0464, "t2.large": 0.0928, "t2.xlarge": 0.1856,
    "t2.2xlarge": 0.3712,
    "t3.nano": 0.0052, "t3.micro": 0.0104, "t3.small": 0.0208,
    "t3.medium": 0.0416, "t3.large": 0.0832, "t3.xlarge": 0.1664,
    "t3.2xlarge": 0.3328,
    "t3a.nano": 0.0047, "t3a.micro": 0.0094, "t3a.small": 0.0188,
    "t3a.medium": 0.0376, "t3a.large": 0.0752, "t3a.xlarge": 0.1504,
    "m5.large": 0.096, "m5.xlarge": 0.192, "m5.2xlarge": 0.384,
    "m5.4xlarge": 0.768, "m5.8xlarge": 1.536, "m5.12xlarge": 2.304,
    "m5a.large": 0.086, "m5a.xlarge": 0.172, "m5a.2xlarge": 0.344,
    "m6i.large": 0.096, "m6i.xlarge": 0.192, "m6i.2xlarge": 0.384,
    "m6i.4xlarge": 0.768,
    "c5.large": 0.085, "c5.xlarge": 0.17, "c5.2xlarge": 0.34,
    "c5.4xlarge": 0.68, "c5.9xlarge": 1.53,
    "c6i.large": 0.085, "c6i.xlarge": 0.17, "c6i.2xlarge": 0.34,
    "r5.large": 0.126, "r5.xlarge": 0.252, "r5.2xlarge": 0.504,
    "r5.4xlarge": 1.008,
    "r6i.large": 0.126, "r6i.xlarge": 0.252, "r6i.2xlarge": 0.504,
}

# EBS gp3 pricing: $0.08/GB/month
EBS_PRICE_PER_GB = 0.08
EBS_VOLUME_SIZE = 80  # GB (matches Terraform)


# =============================================================================
# HELPERS
# =============================================================================

def confirm(prompt):
    while True:
        r = input(f"{prompt} (yes/no): ").strip().lower()
        if r in ("yes", "y"):
            return True
        if r in ("no", "n"):
            return False
        print("  Please enter 'yes' or 'no'.")


def fmt_duration(seconds):
    """Format seconds as '2h 15m 30s'."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    parts = []
    if h > 0:
        parts.append(f"{h}h")
    if m > 0:
        parts.append(f"{m}m")
    parts.append(f"{s}s")
    return " ".join(parts)


def fmt_hours(seconds):
    """Format seconds as decimal hours."""
    return f"{seconds / 3600:.2f}"


# =============================================================================
# AWS SESSION
# =============================================================================

def create_session():
    try:
        session = boto3.Session()
        session.client("sts").get_caller_identity()
        return session
    except NoCredentialsError:
        print("\n  ERROR: No AWS credentials found.")
        print("  Configure via: aws configure / env vars / IAM role")
        sys.exit(1)
    except ClientError as e:
        print(f"\n  ERROR: AWS authentication failed: {e}")
        sys.exit(1)


# =============================================================================
# EC2 OPERATIONS
# =============================================================================

def find_instance(ec2, name):
    resp = ec2.describe_instances(Filters=[
        {"Name": "tag:Name", "Values": [name]},
        {"Name": "instance-state-name", "Values": ["running", "stopped", "pending", "stopping"]},
    ])
    instances = [i for r in resp["Reservations"] for i in r["Instances"]]
    if not instances:
        print(f"\n  ERROR: No instance found with Name '{name}'.")
        sys.exit(1)
    if len(instances) > 1:
        print(f"  Warning: {len(instances)} instances found. Using first.")
    return instances[0]


def get_public_ip(ec2, instance_id):
    resp = ec2.describe_instances(InstanceIds=[instance_id])
    return resp["Reservations"][0]["Instances"][0].get("PublicIpAddress")


def get_launch_time(ec2, instance_id):
    try:
        resp = ec2.describe_instances(InstanceIds=[instance_id])
        return resp["Reservations"][0]["Instances"][0].get("LaunchTime")
    except Exception:
        return None


def start_instance(ec2, instance_id, name):
    print(f"\n  Starting '{name}'...")
    ec2.start_instances(InstanceIds=[instance_id])
    print("  Waiting for running state...")
    ec2.get_waiter("instance_running").wait(
        InstanceIds=[instance_id], WaiterConfig={"Delay": 5, "MaxAttempts": 60})
    print("  Waiting for status checks...")
    try:
        ec2.get_waiter("instance_status_ok").wait(
            InstanceIds=[instance_id], WaiterConfig={"Delay": 10, "MaxAttempts": 60})
    except Exception:
        print("  Warning: Status checks timed out (instance is running).")
    print("  Instance is READY!")


def stop_instance(ec2, instance_id, name):
    print(f"\n  Stopping '{name}'...")
    ec2.stop_instances(InstanceIds=[instance_id])
    print("  Waiting for stopped state...")
    ec2.get_waiter("instance_stopped").wait(
        InstanceIds=[instance_id], WaiterConfig={"Delay": 5, "MaxAttempts": 60})
    print("  Instance STOPPED.")


# =============================================================================
# SECRETS MANAGER - SSH KEY
# =============================================================================

def get_ssh_key(session, secret_name):
    print(f"  Fetching key: {secret_name}")
    try:
        sm = session.client("secretsmanager")
        resp = sm.get_secret_value(SecretId=secret_name)
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "ResourceNotFoundException":
            print(f"  ERROR: Secret '{secret_name}' not found.")
        elif code == "AccessDeniedException":
            print(f"  ERROR: Access denied to '{secret_name}'.")
        else:
            print(f"  ERROR: {e}")
        return None

    value = resp.get("SecretString") or ""
    if not value:
        import base64
        value = base64.b64decode(resp["SecretBinary"]).decode("utf-8")

    # Parse JSON or plain PEM
    try:
        data = json.loads(value)
        for k in ["private_key", "ssh_key", "pem", "key", "ssh_private_key"]:
            if k in data:
                return data[k]
        for k, v in data.items():
            if isinstance(v, str) and "BEGIN" in v and "KEY" in v:
                return v
        return None
    except (json.JSONDecodeError, TypeError):
        if "BEGIN" in value and "KEY" in value:
            return value
        return None


def write_key_file(content):
    f = tempfile.NamedTemporaryFile(mode="w", prefix="ec2_key_", suffix=".pem", delete=False)
    f.write(content if content.endswith("\n") else content + "\n")
    f.close()
    os.chmod(f.name, 0o600)
    return f.name


def remove_key_file(path):
    if path and os.path.exists(path):
        os.remove(path)


# =============================================================================
# SSH
# =============================================================================

def ssh_connect(ip, key_path, user):
    print(f"\n  Connecting to {user}@{ip}...")
    print("  (Type 'exit' or Ctrl+D to disconnect)\n")
    print("  " + "─" * 56)
    cmd = ["ssh", "-i", key_path, "-o", "StrictHostKeyChecking=no",
           "-o", "UserKnownHostsFile=/dev/null", "-o", "ConnectTimeout=30",
           f"{user}@{ip}"]
    try:
        subprocess.run(cmd)
    except FileNotFoundError:
        print("  ERROR: 'ssh' not found. Install OpenSSH.")
    except KeyboardInterrupt:
        print("\n  SSH interrupted.")


# =============================================================================
# COST EXPLORER - REAL USAGE DATA
# =============================================================================

def fetch_daily_costs(session, instance_id, days=30):
    """Fetch real daily costs from AWS Cost Explorer."""
    try:
        ce = session.client("ce")
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=days)
        resp = ce.get_cost_and_usage(
            TimePeriod={"Start": str(start), "End": str(end)},
            Granularity="DAILY",
            Metrics=["UnblendedCost"],
            Filter={"And": [
                {"Dimensions": {"Key": "SERVICE", "Values": ["Amazon Elastic Compute Cloud - Compute"]}},
                {"Dimensions": {"Key": "RESOURCE_ID", "Values": [instance_id]}},
            ]},
        )
        costs = []
        for r in resp.get("ResultsByTime", []):
            amt = float(r["Total"]["UnblendedCost"]["Amount"])
            if amt > 0:
                costs.append({"date": r["TimePeriod"]["Start"], "cost": amt})
        return costs
    except Exception:
        return None


def fetch_monthly_cost(session, instance_id):
    """Fetch current month total from Cost Explorer."""
    try:
        ce = session.client("ce")
        today = datetime.now(timezone.utc).date()
        start = today.replace(day=1)
        resp = ce.get_cost_and_usage(
            TimePeriod={"Start": str(start), "End": str(today)},
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
            Filter={"And": [
                {"Dimensions": {"Key": "SERVICE", "Values": ["Amazon Elastic Compute Cloud - Compute"]}},
                {"Dimensions": {"Key": "RESOURCE_ID", "Values": [instance_id]}},
            ]},
        )
        for r in resp.get("ResultsByTime", []):
            return float(r["Total"]["UnblendedCost"]["Amount"])
        return 0.0
    except Exception:
        return None


# =============================================================================
# COST REPORT - SMART & CLEAN DISPLAY
# =============================================================================

def show_cost_report(session, instance_name, instance_id, instance_type,
                     session_start, session_end, launch_time):
    """Display a professional, easy-to-read cost report."""

    duration_sec = (session_end - session_start).total_seconds()
    rate = PRICING.get(instance_type)
    ebs_monthly = EBS_VOLUME_SIZE * EBS_PRICE_PER_GB

    # Calculate running time since last start
    total_run_sec = None
    if launch_time:
        total_run_sec = (session_end - launch_time).total_seconds()

    # Header
    print("\n")
    print("  ┌────────────────────────────────────────────────────────┐")
    print("  │              INSTANCE USAGE & COST REPORT              │")
    print("  └────────────────────────────────────────────────────────┘")

    # Instance Info
    print(f"""
  ┌─ INSTANCE INFO ─────────────────────────────────────────┐
  │  Name         : {instance_name:<39}│
  │  ID           : {instance_id:<39}│
  │  Type         : {instance_type:<39}│
  │  Rate         : {'$' + f'{rate:.4f}/hr' if rate else 'Unknown':<39}│
  │  Storage      : {EBS_VOLUME_SIZE}GB gp3 (${ebs_monthly:.2f}/month){' ' * (24 - len(f'{EBS_VOLUME_SIZE}GB gp3 (${ebs_monthly:.2f}/month)'))}│
  └─────────────────────────────────────────────────────────┘""")

    # Session Timing
    print(f"""
  ┌─ SESSION TIMING ────────────────────────────────────────┐
  │  Connected    : {session_start.strftime('%Y-%m-%d %H:%M:%S UTC'):<39}│
  │  Disconnected : {session_end.strftime('%Y-%m-%d %H:%M:%S UTC'):<39}│
  │  Duration     : {fmt_duration(duration_sec):<39}│
  │  Hours Used   : {fmt_hours(duration_sec) + ' hrs':<39}│
  └─────────────────────────────────────────────────────────┘""")

    # Session Cost
    if rate:
        session_cost = (duration_sec / 3600.0) * rate
        print(f"""
  ┌─ THIS SESSION COST ─────────────────────────────────────┐
  │  Compute      : ${session_cost:<37.4f}│
  │  ({fmt_hours(duration_sec)} hrs x ${rate:.4f}/hr){' ' * max(0, 37 - len(f'({fmt_hours(duration_sec)} hrs x ${rate:.4f}/hr)'))}│
  └─────────────────────────────────────────────────────────┘""")

    # Total Running Since Last Start
    if total_run_sec and rate:
        total_cost = (total_run_sec / 3600.0) * rate
        print(f"""
  ┌─ TOTAL SINCE LAST START ────────────────────────────────┐
  │  Uptime       : {fmt_duration(total_run_sec):<39}│
  │  Hours        : {fmt_hours(total_run_sec) + ' hrs':<39}│
  │  Cost         : ${'%.4f' % total_cost:<38}│
  └─────────────────────────────────────────────────────────┘""")

    # AWS Cost Explorer - Daily Breakdown
    print(f"""
  ┌─ DAILY COST HISTORY (AWS Cost Explorer) ────────────────┐""")

    daily = fetch_daily_costs(session, instance_id, days=7)
    if daily is not None and daily:
        total_7d = sum(d["cost"] for d in daily)
        print(f"  │{'':57}│")
        print(f"  │  {'Date':<12} {'Hours':>7} {'Cost':>10} {'Bar':<22}│")
        print(f"  │  {'─' * 12} {'─' * 7} {'─' * 10} {'─' * 22}│")

        for entry in daily[-7:]:
            cost = entry["cost"]
            # Estimate hours from cost
            hrs = cost / rate if rate and rate > 0 else 0
            bar_len = min(int(cost / (rate or 0.1) * 2), 20) if rate else 0
            bar = "█" * bar_len
            print(f"  │  {entry['date']:<12} {hrs:>6.1f}h ${cost:>8.4f} {bar:<22}│")

        print(f"  │  {'─' * 12} {'─' * 7} {'─' * 10} {'─' * 22}│")
        print(f"  │  {'7-DAY TOTAL':<12} {'':>7} ${total_7d:>8.4f}{' ' * 23}│")
    elif daily is not None:
        print(f"  │  No usage data in last 7 days (new instance?)        │")
    else:
        print(f"  │  Could not fetch data (needs ce:GetCostAndUsage)     │")

    print(f"  └─────────────────────────────────────────────────────────┘")

    # Monthly Total
    monthly = fetch_monthly_cost(session, instance_id)
    today = datetime.now(timezone.utc).date()
    month_label = today.strftime("%B %Y")

    print(f"""
  ┌─ MONTHLY SUMMARY ({month_label}) ──────────────────────┐""")

    if monthly is not None and monthly > 0:
        day_of_month = today.day
        daily_avg = monthly / day_of_month if day_of_month > 0 else 0
        projected = daily_avg * 30
        print(f"  │  Month-to-Date: ${monthly:<37.4f}│")
        print(f"  │  Daily Average: ${daily_avg:<37.4f}│")
        print(f"  │  Projected    : ${projected:<37.2f}│")
    elif monthly is not None:
        print(f"  │  Month-to-Date: $0.0000 (no usage yet)               │")
    else:
        if rate:
            est_daily = rate * 24
            est_monthly = est_daily * 30
            print(f"  │  Estimated    : ${est_monthly:<37.2f}│")
            print(f"  │  (based on 24/7 at ${rate:.4f}/hr)                     │")
        else:
            print(f"  │  Unable to calculate (unknown rate)                  │")

    print(f"  └─────────────────────────────────────────────────────────┘")

    # Cost Summary Box
    if rate:
        print(f"""
  ┌─ COST SUMMARY ──────────────────────────────────────────┐
  │                                                         │
  │  Per Hour     : ${rate:<10.4f}                              │
  │  Per Day      : ${rate * 24:<10.2f}  (24hr running)             │
  │  Per Month    : ${rate * 24 * 30:<10.2f}  (30 days, 24/7)           │
  │  Storage/Mo   : ${ebs_monthly:<10.2f}  ({EBS_VOLUME_SIZE}GB gp3)                  │
  │  EIP (stopped): ${'3.60':<10}  ($0.005/hr)                │
  │                                                         │
  │  ⚡ TOTAL/MONTH: ${rate * 24 * 30 + ebs_monthly:<10.2f}  (compute + storage)     │
  │                                                         │
  └─────────────────────────────────────────────────────────┘""")

    print()


# =============================================================================
# MAIN
# =============================================================================

def main():
    print()
    print("  ╔════════════════════════════════════════════════════════╗")
    print("  ║       AWS EC2 Instance Manager & SSH Connector        ║")
    print("  ╚════════════════════════════════════════════════════════╝")
    print()

    # Connect to AWS
    print("  Connecting to AWS...")
    session = create_session()
    ec2 = session.client("ec2")
    print("  ✓ Authenticated\n")

    # Get instance name
    instance_name = input("  Enter instance Name: ").strip()
    if not instance_name:
        print("  ERROR: Name is required.")
        sys.exit(1)

    # Find instance
    print(f"\n  Searching for '{instance_name}'...")
    inst = find_instance(ec2, instance_name)
    iid = inst["InstanceId"]
    itype = inst.get("InstanceType", "unknown")
    state = inst["State"]["Name"]
    rate = PRICING.get(itype)

    print(f"\n  ┌─ INSTANCE FOUND ──────────────────────────────────────┐")
    print(f"  │  Name  : {instance_name:<46}│")
    print(f"  │  ID    : {iid:<46}│")
    print(f"  │  Type  : {itype:<46}│")
    print(f"  │  State : {state.upper():<46}│")
    print(f"  │  Rate  : {'$' + f'{rate:.4f}/hr (${rate*24:.2f}/day)' if rate else 'Unknown':<46}│")
    print(f"  └─────────────────────────────────────────────────────────┘")

    # Handle state
    if state == "stopped":
        print(f"\n  Instance is STOPPED.")
        if rate:
            print(f"  Starting will cost ${rate:.4f}/hr (${rate*24:.2f}/day)")
        if not confirm("  Start the instance?"):
            print("  Exiting.")
            sys.exit(0)
        start_instance(ec2, iid, instance_name)
    elif state == "pending":
        print("\n  Instance is starting...")
        ec2.get_waiter("instance_running").wait(InstanceIds=[iid])
        print("  Ready!")
    elif state == "stopping":
        print("\n  Instance is stopping. Try again later.")
        sys.exit(1)
    elif state != "running":
        print(f"\n  Unexpected state: {state}")
        sys.exit(1)

    # Session timer starts
    session_start = datetime.now(timezone.utc)
    launch_time = get_launch_time(ec2, iid)

    # Get IP
    ip = get_public_ip(ec2, iid)
    if not ip:
        ip = inst.get("PrivateIpAddress")
        if ip:
            print(f"\n  No public IP. Private: {ip}")
            if not confirm("  Connect via private IP?"):
                sys.exit(1)
        else:
            print("\n  ERROR: No IP available.")
            sys.exit(1)

    # SSH via Secrets Manager
    print(f"\n  ┌─ SSH CONNECTION ───────────────────────────────────────┐")
    print(f"  │  IP     : {ip:<45}│")
    print(f"  │  User   : {DEFAULT_SSH_USER:<45}│")

    secret = SECRET_NAME_PATTERN.format(instance_name=instance_name)
    key_content = get_ssh_key(session, secret)
    if not key_content:
        print(f"  │  ERROR: Key not found in Secrets Manager             │")
        print(f"  │  Expected: {secret:<43}│")
        print(f"  └─────────────────────────────────────────────────────────┘")
        sys.exit(1)

    key_path = write_key_file(key_content)
    print(f"  │  Key    : ✓ Retrieved from Secrets Manager            │")
    if rate:
        print(f"  │  Billing: ${rate:.4f}/hr while connected{' ' * (19 - len(f'{rate:.4f}'))}│")
    print(f"  └─────────────────────────────────────────────────────────┘")

    # Connect
    ssh_connect(ip, key_path, DEFAULT_SSH_USER)

    # Session ends
    session_end = datetime.now(timezone.utc)
    remove_key_file(key_path)

    # Show cost report
    show_cost_report(
        session=session,
        instance_name=instance_name,
        instance_id=iid,
        instance_type=itype,
        session_start=session_start,
        session_end=session_end,
        launch_time=launch_time,
    )

    # Offer to stop
    if confirm("  Would you like to STOP the instance?"):
        stop_instance(ec2, iid, instance_name)
        if rate:
            print(f"  💰 Saving ${rate:.4f}/hr (${rate*24:.2f}/day) by stopping!")
    else:
        if rate:
            print(f"  ⚠️  Instance running at ${rate:.4f}/hr (${rate*24:.2f}/day)")
        print("  Remember to stop it when done!")

    print("\n  Done. Goodbye!\n")


if __name__ == "__main__":
    main()
