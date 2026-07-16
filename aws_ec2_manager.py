#!/usr/bin/env python3
"""
AWS EC2 Instance Manager Script
- Prompts for EC2 instance name
- Checks instance state; offers to start if stopped
- Retrieves SSH private key from AWS Secrets Manager for secure access
- SSHs into the instance
- After SSH session ends, offers to stop the instance

Note: Uses default AWS credentials and region from environment
      (AWS_PROFILE, AWS_REGION, ~/.aws/config, or IAM role)
"""

import json
import os
import subprocess
import sys
import tempfile
import time

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
except ImportError:
    print("Error: boto3 is required. Install it with: pip install boto3")
    sys.exit(1)


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
# AWS SECRETS MANAGER - SSH KEY RETRIEVAL
# =============================================================================


def get_ssh_key_from_secrets_manager(session, secret_name):
    """
    Retrieve SSH private key from AWS Secrets Manager.

    The secret can be stored as:
    - Plain text (the PEM key content directly)
    - JSON with a key like 'private_key', 'ssh_key', or 'pem'
    """
    print(f"\nRetrieving SSH key from Secrets Manager: '{secret_name}'...")

    try:
        sm_client = session.client("secretsmanager")
        response = sm_client.get_secret_value(SecretId=secret_name)
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "ResourceNotFoundException":
            print(f"Error: Secret '{secret_name}' not found in Secrets Manager.")
        elif error_code == "AccessDeniedException":
            print(f"Error: Access denied to secret '{secret_name}'.")
            print("Ensure your IAM role/user has secretsmanager:GetSecretValue permission.")
        elif error_code == "InvalidRequestException":
            print(f"Error: Invalid request for secret '{secret_name}'.")
        else:
            print(f"Error retrieving secret: {e}")
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
        # If none of the common names found, show available keys
        print(f"  Available keys in secret: {list(secret_json.keys())}")
        field = input("  Enter the JSON field name containing the SSH key: ").strip()
        if field in secret_json:
            return secret_json[field]
        else:
            print(f"  Error: Field '{field}' not found in secret.")
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
        print(f"Error writing temporary key file: {e}")
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


def get_ssh_credentials(session):
    """Get SSH username and key (from Secrets Manager or local file)."""
    print("\n--- SSH Access Configuration ---")
    print("  1. Retrieve SSH key from AWS Secrets Manager (recommended)")
    print("  2. Use local SSH key file")
    print()

    while True:
        choice = input("Choose SSH key source (1 or 2): ").strip()
        if choice in ("1", "2"):
            break
        print("Please enter 1 or 2.")

    ssh_user = input("\nEnter SSH username (e.g., ec2-user, ubuntu, admin) [ec2-user]: ").strip()
    if not ssh_user:
        ssh_user = "ec2-user"

    key_path = None
    temp_key = False

    if choice == "1":
        # Retrieve from Secrets Manager
        secret_name = input("Enter Secrets Manager secret name (e.g., ec2/my-server/ssh-key): ").strip()
        if not secret_name:
            print("Error: Secret name is required.")
            sys.exit(1)

        key_content = get_ssh_key_from_secrets_manager(session, secret_name)
        if not key_content:
            print("Failed to retrieve SSH key. Falling back to local file.")
            key_path = input("Enter path to local SSH key file: ").strip()
            if not key_path:
                print("Error: SSH key path is required.")
                sys.exit(1)
        else:
            key_path = write_temp_key_file(key_content)
            if not key_path:
                print("Error: Failed to write temporary key file.")
                sys.exit(1)
            temp_key = True
            print("  SSH key retrieved and ready for use.")
    else:
        # Use local file
        key_path = input("Enter path to SSH private key file (e.g., ~/.ssh/my-key.pem): ").strip()
        if not key_path:
            print("Error: SSH key path is required.")
            sys.exit(1)
        key_path = os.path.expanduser(key_path)

    return ssh_user, key_path, temp_key


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

    # Step 2: Ask for instance name
    instance_name = input("\nEnter EC2 instance Name tag: ").strip()
    if not instance_name:
        print("Error: Instance name is required.")
        sys.exit(1)

    # Step 3: Find the instance by name
    print(f"Looking for instance with Name: '{instance_name}'...")
    instance = find_instance_by_name(ec2_client, instance_name)
    instance_id = instance["InstanceId"]
    state = get_instance_state(instance)

    print(f"\nFound instance:")
    print(f"  Instance ID : {instance_id}")
    print(f"  Name        : {instance_name}")
    print(f"  State       : {state}")
    print(f"  Type        : {instance.get('InstanceType', 'N/A')}")

    # Step 4: Handle instance state
    if state == "stopped":
        print(f"\nInstance '{instance_name}' is currently STOPPED.")
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

    print(f"\n  IP Address  : {public_ip}")

    # Step 6: Get SSH credentials (from Secrets Manager or local file)
    print("\n" + "=" * 60)
    print("  SSH Connection Setup")
    print("=" * 60)

    ssh_user, key_path, temp_key = get_ssh_credentials(session)

    # Step 7: SSH into the instance
    print("\n" + "=" * 60)
    print("  Initiating SSH Connection")
    print("=" * 60)

    ssh_to_instance(public_ip, key_path, ssh_user)

    # Cleanup temp key file if used
    if temp_key:
        cleanup_temp_key(key_path)

    # Step 8: After SSH session ends, offer to stop the instance
    print("\n" + "=" * 60)
    print("  SSH Session Ended")
    print("=" * 60)

    print(f"\nYour work on instance '{instance_name}' ({instance_id}) is complete.")
    if confirm("Would you like to STOP the instance to save costs?"):
        stop_instance(ec2_client, instance_id, instance_name)
    else:
        print(f"Instance '{instance_name}' will remain running.")
        print("Remember to stop it manually when you're done to avoid charges!")

    print("\nGoodbye!")


if __name__ == "__main__":
    main()
