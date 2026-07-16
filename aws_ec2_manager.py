#!/usr/bin/env python3
"""
AWS EC2 Instance Manager Script
- Prompts for EC2 instance name
- Checks instance state; offers to start if stopped
- Automatically retrieves SSH private key from AWS Secrets Manager
- SSHs into the instance (no manual SSH config needed)
- Tracks session duration and calculates usage cost
- After SSH session ends, shows cost report and offers to stop the instance

Note: Uses default AWS credentials and region from environment
      (AWS_PROFILE, AWS_REGION, ~/.aws/config, or IAM role)

SSH Key Convention:
    Secret name in Secrets Manager: ec2/<instance_name>/ssh-private-key
    This matches the Terraform-created secret automatically.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
except ImportError:
    print("Error: boto3 is required. Install it with: pip install boto3")
    sys.exit(1)


# Default SSH user for Ubuntu instances
DEFAULT_SSH_USER = "ubuntu"

# Secret name pattern (matches Terraform output)
SECRET_NAME_PATTERN = "ec2/{instance_name}/ssh-private-key"

# =============================================================================
# EC2 INSTANCE PRICING (On-Demand, USD per hour, us-east-1)
# Update these prices as needed for your region
# =============================================================================

EC2_HOURLY_PRICING = {
    # General Purpose
    "t2.nano": 0.0058,
    "t2.micro": 0.0116,
    "t2.small": 0.023,
    "t2.medium": 0.0464,
    "t2.large": 0.0928,
    "t2.xlarge": 0.1856,
    "t2.2xlarge": 0.3712,
    "t3.nano": 0.0052,
    "t3.micro": 0.0104,
    "t3.small": 0.0208,
    "t3.medium": 0.0416,
    "t3.large": 0.0832,
    "t3.xlarge": 0.1664,
    "t3.2xlarge": 0.3328,
    "t3a.nano": 0.0047,
    "t3a.micro": 0.0094,
    "t3a.small": 0.0188,
    "t3a.medium": 0.0376,
    "t3a.large": 0.0752,
    "t3a.xlarge": 0.1504,
    "t3a.2xlarge": 0.3008,
    # Compute Optimized
    "m5.large": 0.096,
    "m5.xlarge": 0.192,
    "m5.2xlarge": 0.384,
    "m5.4xlarge": 0.768,
    "m5.8xlarge": 1.536,
    "m5.12xlarge": 2.304,
    "m5.16xlarge": 3.072,
    "m5.24xlarge": 4.608,
    "m5a.large": 0.086,
    "m5a.xlarge": 0.172,
    "m5a.2xlarge": 0.344,
    "m5a.4xlarge": 0.688,
    "m6i.large": 0.096,
    "m6i.xlarge": 0.192,
    "m6i.2xlarge": 0.384,
    "m6i.4xlarge": 0.768,
    # Compute Optimized
    "c5.large": 0.085,
    "c5.xlarge": 0.17,
    "c5.2xlarge": 0.34,
    "c5.4xlarge": 0.68,
    "c5.9xlarge": 1.53,
    "c6i.large": 0.085,
    "c6i.xlarge": 0.17,
    "c6i.2xlarge": 0.34,
    # Memory Optimized
    "r5.large": 0.126,
    "r5.xlarge": 0.252,
    "r5.2xlarge": 0.504,
    "r5.4xlarge": 1.008,
    "r6i.large": 0.126,
    "r6i.xlarge": 0.252,
    "r6i.2xlarge": 0.504,
}


# =============================================================================
# SESSION SETUP
# =============================================================================


def create_session():
    """Create a boto3 session using default AWS credentials and region."""
    try:
        session = boto3.Session()
        # Verify credentials are available
        sts = session.client("sts")
        sts.get_caller_identity()
        return session
    except NoCredentialsError:
        print("Error: No AWS credentials found.")
        print("Configure credentials using one of:")
        print("  - AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY env vars")
        print("  - AWS_PROFILE env var")
        print("  - ~/.aws/credentials file (aws configure)")
        print("  - IAM instance role")
        sys.exit(1)
    except ClientError as e:
        print(f"Error: Unable to authenticate with AWS: {e}")
        sys.exit(1)


# =============================================================================
# COST TRACKING & REPORTING
# =============================================================================


def get_instance_hourly_rate(instance_type):
    """Get the hourly rate for an instance type."""
    return EC2_HOURLY_PRICING.get(instance_type, None)


def get_instance_launch_time(ec2_client, instance_id):
    """Get the time when the instance was last started (LaunchTime)."""
    try:
        response = ec2_client.describe_instances(InstanceIds=[instance_id])
        instance = response["Reservations"][0]["Instances"][0]
        return instance.get("LaunchTime")
    except (ClientError, IndexError, KeyError):
        return None


def calculate_session_cost(instance_type, duration_seconds):
    """Calculate the cost for the session duration."""
    hourly_rate = get_instance_hourly_rate(instance_type)
    if hourly_rate is None:
        return None, None

    hours = duration_seconds / 3600.0
    cost = hours * hourly_rate
    return cost, hourly_rate


def format_duration(seconds):
    """Format seconds into human-readable duration."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")

    return " ".join(parts)


def display_cost_report(instance_name, instance_id, instance_type, session_start, session_end, total_running_hours=None):
    """Display a detailed cost report for the session."""
    session_duration = (session_end - session_start).total_seconds()
    hourly_rate = get_instance_hourly_rate(instance_type)

    print("\n" + "=" * 60)
    print("  USAGE COST REPORT")
    print("=" * 60)
    print(f"\n  Instance Name   : {instance_name}")
    print(f"  Instance ID     : {instance_id}")
    print(f"  Instance Type   : {instance_type}")
    print(f"  Session Start   : {session_start.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"  Session End     : {session_end.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"  Session Duration: {format_duration(session_duration)}")

    print(f"\n  {'─' * 50}")
    print(f"  PRICING BREAKDOWN:")
    print(f"  {'─' * 50}")

    if hourly_rate is not None:
        session_cost = (session_duration / 3600.0) * hourly_rate
        print(f"  Hourly Rate     : ${hourly_rate:.4f}/hr")
        print(f"  Session Hours   : {session_duration / 3600.0:.4f} hrs")
        print(f"  Session Cost    : ${session_cost:.6f}")
        print(f"  {'─' * 50}")

        # Show projections
        daily_cost = hourly_rate * 24
        monthly_cost = hourly_rate * 24 * 30
        print(f"\n  COST PROJECTIONS (if running 24/7):")
        print(f"  Per Hour        : ${hourly_rate:.4f}")
        print(f"  Per Day         : ${daily_cost:.2f}")
        print(f"  Per Month (30d) : ${monthly_cost:.2f}")

        # Show total running time cost if available
        if total_running_hours is not None:
            total_cost = total_running_hours * hourly_rate
            print(f"\n  TOTAL SINCE LAST START:")
            print(f"  Running Time    : {format_duration(total_running_hours * 3600)}")
            print(f"  Total Cost      : ${total_cost:.4f}")
    else:
        print(f"  Hourly Rate     : Unknown (instance type '{instance_type}' not in pricing table)")
        print(f"  Session Hours   : {session_duration / 3600.0:.4f} hrs")
        print(f"  Session Cost    : Unable to calculate")
        print(f"\n  Tip: Check AWS Pricing at https://aws.amazon.com/ec2/pricing/on-demand/")

    print(f"\n  {'─' * 50}")

    # EBS storage cost estimate (gp3 default)
    print(f"  EBS STORAGE (estimated):")
    print(f"  30GB gp3 volume : ~$2.40/month")
    print(f"  Elastic IP      : $0.005/hr (when instance stopped)")

    print("\n" + "=" * 60)


# =============================================================================
# AWS SECRETS MANAGER - SSH KEY RETRIEVAL
# =============================================================================


def get_ssh_key_from_secrets_manager(session, secret_name):
    """
    Retrieve SSH private key from AWS Secrets Manager.

    The secret can be stored as:
    - Plain text (the PEM key content directly)
    - JSON with a key like 'private_key', 'ssh_key', or 'pem'
    """
    print(f"  Retrieving SSH key from Secrets Manager: '{secret_name}'...")

    try:
        sm_client = session.client("secretsmanager")
        response = sm_client.get_secret_value(SecretId=secret_name)
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "ResourceNotFoundException":
            print(f"  Error: Secret '{secret_name}' not found in Secrets Manager.")
        elif error_code == "AccessDeniedException":
            print(f"  Error: Access denied to secret '{secret_name}'.")
            print("  Ensure your IAM role/user has secretsmanager:GetSecretValue permission.")
        elif error_code == "InvalidRequestException":
            print(f"  Error: Invalid request for secret '{secret_name}'.")
        else:
            print(f"  Error retrieving secret: {e}")
        return None

    # Extract the secret value
    if "SecretString" in response:
        secret_value = response["SecretString"]
    else:
        # Binary secret
        import base64
        secret_value = base64.b64decode(response["SecretBinary"]).decode("utf-8")

    # Try to parse as JSON first
    try:
        secret_json = json.loads(secret_value)
        # Look for common key names
        key_names = ["private_key", "ssh_key", "pem", "key", "ssh_private_key", "ec2_key"]
        for key_name in key_names:
            if key_name in secret_json:
                print(f"  Found SSH key in JSON field: '{key_name}'")
                return secret_json[key_name]
        # If none found, try the first value that looks like a PEM key
        for key_name, value in secret_json.items():
            if isinstance(value, str) and "BEGIN" in value and "KEY" in value:
                print(f"  Found SSH key in JSON field: '{key_name}'")
                return value
        print(f"  Error: No SSH key found in secret. Available fields: {list(secret_json.keys())}")
        return None
    except (json.JSONDecodeError, TypeError):
        # Not JSON, treat as plain text PEM key
        if "BEGIN" in secret_value and "KEY" in secret_value:
            print("  Found SSH key as plain text PEM.")
            return secret_value
        else:
            print("  Error: Secret does not appear to contain a valid SSH key.")
            return None


def write_temp_key_file(key_content):
    """Write SSH key content to a secure temporary file."""
    try:
        tmp_file = tempfile.NamedTemporaryFile(
            mode="w", prefix="ec2_ssh_key_", suffix=".pem", delete=False
        )
        tmp_file.write(key_content)
        # Ensure key ends with newline
        if not key_content.endswith("\n"):
            tmp_file.write("\n")
        tmp_file.close()

        # Set strict permissions (required by SSH)
        os.chmod(tmp_file.name, 0o600)

        return tmp_file.name
    except Exception as e:
        print(f"  Error writing temporary key file: {e}")
        return None


def cleanup_temp_key(key_path):
    """Securely remove the temporary key file."""
    try:
        if key_path and os.path.exists(key_path):
            os.remove(key_path)
            print("  Temporary SSH key file removed.")
    except Exception:
        print(f"  Warning: Could not remove temp key file: {key_path}")
        print("  Please delete it manually for security.")


# =============================================================================
# EC2 INSTANCE MANAGEMENT
# =============================================================================


def find_instance_by_name(ec2_client, instance_name):
    """Find an EC2 instance by its Name tag."""
    try:
        response = ec2_client.describe_instances(
            Filters=[
                {"Name": "tag:Name", "Values": [instance_name]},
                {
                    "Name": "instance-state-name",
                    "Values": ["running", "stopped", "pending", "stopping"],
                },
            ]
        )
    except ClientError as e:
        print(f"Error querying EC2 instances: {e}")
        sys.exit(1)

    instances = []
    for reservation in response["Reservations"]:
        for instance in reservation["Instances"]:
            instances.append(instance)

    if not instances:
        print(f"Error: No instance found with Name tag '{instance_name}'.")
        sys.exit(1)

    if len(instances) > 1:
        print(f"Warning: Multiple instances found with Name '{instance_name}'.")
        print("Using the first one found.")

    return instances[0]


def get_instance_state(instance):
    """Get the current state of an instance."""
    return instance["State"]["Name"]


def get_instance_public_ip(ec2_client, instance_id):
    """Get the public IP address of a running instance."""
    response = ec2_client.describe_instances(InstanceIds=[instance_id])
    instance = response["Reservations"][0]["Instances"][0]
    public_ip = instance.get("PublicIpAddress")
    return public_ip


def start_instance(ec2_client, instance_id, instance_name):
    """Start a stopped EC2 instance and wait for it to be running."""
    print(f"\nStarting instance '{instance_name}' ({instance_id})...")
    try:
        ec2_client.start_instances(InstanceIds=[instance_id])
    except ClientError as e:
        print(f"Error starting instance: {e}")
        sys.exit(1)

    print("Waiting for instance to enter 'running' state...")
    waiter = ec2_client.get_waiter("instance_running")
    try:
        waiter.wait(
            InstanceIds=[instance_id],
            WaiterConfig={"Delay": 5, "MaxAttempts": 60},
        )
    except Exception as e:
        print(f"Error waiting for instance to start: {e}")
        sys.exit(1)

    print("Instance is now running!")

    # Wait for status checks
    print("Waiting for instance status checks to pass...")
    status_waiter = ec2_client.get_waiter("instance_status_ok")
    try:
        status_waiter.wait(
            InstanceIds=[instance_id],
            WaiterConfig={"Delay": 10, "MaxAttempts": 60},
        )
    except Exception:
        print("Warning: Status checks did not pass in time, but instance is running.")
        print("SSH connection may still work.")

    print("Instance is ready!")


def stop_instance(ec2_client, instance_id, instance_name):
    """Stop a running EC2 instance."""
    print(f"\nStopping instance '{instance_name}' ({instance_id})...")
    try:
        ec2_client.stop_instances(InstanceIds=[instance_id])
    except ClientError as e:
        print(f"Error stopping instance: {e}")
        return

    print("Waiting for instance to stop...")
    waiter = ec2_client.get_waiter("instance_stopped")
    try:
        waiter.wait(
            InstanceIds=[instance_id],
            WaiterConfig={"Delay": 5, "MaxAttempts": 60},
        )
    except Exception as e:
        print(f"Error waiting for instance to stop: {e}")
        return

    print("Instance has been stopped successfully.")


# =============================================================================
# SSH CONNECTION
# =============================================================================


def ssh_to_instance(public_ip, key_path, ssh_user):
    """SSH into the EC2 instance using the provided key file."""
    print(f"\nConnecting to {public_ip} as {ssh_user}...")
    print("(Type 'exit' or press Ctrl+D to disconnect)\n")
    print("-" * 60)

    ssh_command = [
        "ssh",
        "-i", key_path,
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "ConnectTimeout=30",
        f"{ssh_user}@{public_ip}",
    ]

    try:
        result = subprocess.run(ssh_command)
        return result.returncode == 0
    except FileNotFoundError:
        print("Error: 'ssh' command not found. Please install OpenSSH client.")
        return False
    except KeyboardInterrupt:
        print("\nSSH session interrupted.")
        return True


# =============================================================================
# UTILITIES
# =============================================================================


def confirm(prompt):
    """Ask user for yes/no confirmation."""
    while True:
        response = input(f"{prompt} (yes/no): ").strip().lower()
        if response in ("yes", "y"):
            return True
        elif response in ("no", "n"):
            return False
        else:
            print("Please enter 'yes' or 'no'.")


# =============================================================================
# MAIN WORKFLOW
# =============================================================================


def main():
    """Main function to orchestrate the EC2 management workflow."""
    print("=" * 60)
    print("       AWS EC2 Instance Manager & SSH Connector")
    print("=" * 60)
    print()

    # Step 1: Create session (uses default AWS credentials/region)
    print("Connecting to AWS...")
    session = create_session()
    ec2_client = session.client("ec2")
    print("  Authenticated successfully.")

    # Step 2: Ask for instance name (only user prompt needed)
    instance_name = input("\nEnter EC2 instance Name tag: ").strip()
    if not instance_name:
        print("Error: Instance name is required.")
        sys.exit(1)

    # Step 3: Find the instance by name
    print(f"\nLooking for instance with Name: '{instance_name}'...")
    instance = find_instance_by_name(ec2_client, instance_name)
    instance_id = instance["InstanceId"]
    instance_type = instance.get("InstanceType", "unknown")
    state = get_instance_state(instance)

    # Get hourly rate for display
    hourly_rate = get_instance_hourly_rate(instance_type)
    rate_display = f"${hourly_rate:.4f}/hr" if hourly_rate else "Unknown"

    print(f"\nFound instance:")
    print(f"  Instance ID   : {instance_id}")
    print(f"  Name          : {instance_name}")
    print(f"  State         : {state}")
    print(f"  Type          : {instance_type}")
    print(f"  Hourly Rate   : {rate_display}")

    # Step 4: Handle instance state
    if state == "stopped":
        print(f"\nInstance '{instance_name}' is currently STOPPED.")
        if hourly_rate:
            print(f"  Starting will cost: {rate_display}")
        if confirm("Would you like to start the instance?"):
            start_instance(ec2_client, instance_id, instance_name)
        else:
            print("Cannot SSH to a stopped instance. Exiting.")
            sys.exit(0)
    elif state == "pending":
        print("\nInstance is starting up. Waiting for it to be ready...")
        waiter = ec2_client.get_waiter("instance_running")
        waiter.wait(InstanceIds=[instance_id])
        print("Instance is now running!")
    elif state == "stopping":
        print("\nInstance is currently stopping. Please wait and try again later.")
        sys.exit(1)
    elif state != "running":
        print(f"\nInstance is in unexpected state: {state}. Cannot proceed.")
        sys.exit(1)

    # Record session start time
    session_start = datetime.now(timezone.utc)

    # Get total running time from LaunchTime
    launch_time = get_instance_launch_time(ec2_client, instance_id)

    # Step 5: Get public IP
    public_ip = get_instance_public_ip(ec2_client, instance_id)
    if not public_ip:
        print("\nError: Instance does not have a public IP address.")
        print("Make sure the instance is in a public subnet with a public IP assigned.")

        # Try private IP as fallback
        private_ip = instance.get("PrivateIpAddress")
        if private_ip:
            print(f"Private IP available: {private_ip}")
            if confirm("Would you like to try connecting via private IP?"):
                public_ip = private_ip
            else:
                sys.exit(1)
        else:
            sys.exit(1)

    print(f"  IP Address    : {public_ip}")

    # Step 6: Automatically retrieve SSH key from Secrets Manager
    print("\n" + "=" * 60)
    print("  SSH Connection (Automated via Secrets Manager)")
    print("=" * 60)

    # Auto-derive secret name from instance name
    secret_name = SECRET_NAME_PATTERN.format(instance_name=instance_name)
    ssh_user = DEFAULT_SSH_USER

    print(f"  SSH User    : {ssh_user}")
    print(f"  Secret Name : {secret_name}")

    key_content = get_ssh_key_from_secrets_manager(session, secret_name)

    if not key_content:
        print(f"\n  Could not retrieve key from '{secret_name}'.")
        print("  Ensure the secret exists in Secrets Manager with the SSH private key.")
        print(f"  Expected format: ec2/<instance_name>/ssh-private-key")
        sys.exit(1)

    key_path = write_temp_key_file(key_content)
    if not key_path:
        print("  Error: Failed to write temporary key file.")
        sys.exit(1)

    print("  SSH key retrieved successfully. Connecting...\n")

    # Step 7: SSH into the instance
    print("=" * 60)
    print("  Initiating SSH Connection")
    print("=" * 60)
    if hourly_rate:
        print(f"  (Billing at {rate_display} while connected)")

    ssh_to_instance(public_ip, key_path, ssh_user)

    # Record session end time
    session_end = datetime.now(timezone.utc)

    # Cleanup temp key file
    cleanup_temp_key(key_path)

    # Step 8: Calculate total running hours since launch
    total_running_hours = None
    if launch_time:
        total_running_seconds = (session_end - launch_time).total_seconds()
        total_running_hours = total_running_seconds / 3600.0

    # Step 9: Display cost report
    display_cost_report(
        instance_name=instance_name,
        instance_id=instance_id,
        instance_type=instance_type,
        session_start=session_start,
        session_end=session_end,
        total_running_hours=total_running_hours,
    )

    # Step 10: Offer to stop the instance
    print(f"\nYour work on instance '{instance_name}' ({instance_id}) is complete.")
    if confirm("Would you like to STOP the instance to save costs?"):
        stop_instance(ec2_client, instance_id, instance_name)
        print("\n  Instance stopped. No further compute charges will accrue.")
        if hourly_rate:
            print(f"  You saved: ~${hourly_rate:.4f} per hour by stopping.")
    else:
        print(f"  Instance '{instance_name}' will remain running.")
        if hourly_rate:
            print(f"  Ongoing cost: {rate_display} (~${hourly_rate * 24:.2f}/day)")
        print("  Remember to stop it manually when you're done to avoid charges!")

    print("\nGoodbye!")


if __name__ == "__main__":
    main()
