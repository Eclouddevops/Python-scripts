#!/usr/bin/env python3
"""
AWS EC2 Instance Manager Script
- Prompts for AWS account (profile), region, and EC2 instance name
- Checks instance state; offers to start if stopped
- SSHs into the instance
- After SSH session ends, offers to stop the instance
"""

import subprocess
import sys
import time

try:
    import boto3
    from botocore.exceptions import ClientError, ProfileNotFound, NoCredentialsError
except ImportError:
    print("Error: boto3 is required. Install it with: pip install boto3")
    sys.exit(1)


def get_user_input():
    """Gather AWS account profile, region, and instance name from user."""
    print("=" * 60)
    print("       AWS EC2 Instance Manager & SSH Connector")
    print("=" * 60)
    print()

    aws_profile = input("Enter AWS profile name (or press Enter for 'default'): ").strip()
    if not aws_profile:
        aws_profile = "default"

    region = input("Enter AWS region (e.g., us-east-1, eu-west-1): ").strip()
    if not region:
        print("Error: Region is required.")
        sys.exit(1)

    instance_name = input("Enter EC2 instance Name tag: ").strip()
    if not instance_name:
        print("Error: Instance name is required.")
        sys.exit(1)

    return aws_profile, region, instance_name


def create_ec2_client(aws_profile, region):
    """Create an EC2 client using the specified profile and region."""
    try:
        session = boto3.Session(profile_name=aws_profile, region_name=region)
        ec2_client = session.client("ec2")
        return ec2_client
    except ProfileNotFound:
        print(f"Error: AWS profile '{aws_profile}' not found.")
        print("Available profiles can be configured in ~/.aws/credentials")
        sys.exit(1)
    except NoCredentialsError:
        print("Error: No AWS credentials found.")
        print("Configure credentials using 'aws configure' or set environment variables.")
        sys.exit(1)


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

    # Wait a bit more for the instance to be fully initialized
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


def ssh_to_instance(public_ip):
    """SSH into the EC2 instance."""
    ssh_user = input("\nEnter SSH username (e.g., ec2-user, ubuntu, admin) [ec2-user]: ").strip()
    if not ssh_user:
        ssh_user = "ec2-user"

    key_path = input("Enter path to SSH private key file (e.g., ~/.ssh/my-key.pem): ").strip()
    if not key_path:
        print("Error: SSH key path is required.")
        return False

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


def main():
    """Main function to orchestrate the EC2 management workflow."""
    # Step 1: Get user input
    aws_profile, region, instance_name = get_user_input()

    # Step 2: Create EC2 client
    print(f"\nConnecting to AWS (profile: {aws_profile}, region: {region})...")
    ec2_client = create_ec2_client(aws_profile, region)

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

    print(f"\n  Public IP   : {public_ip}")

    # Step 6: SSH into the instance
    print("\n" + "=" * 60)
    print("  Initiating SSH Connection")
    print("=" * 60)

    ssh_to_instance(public_ip)

    # Step 7: After SSH session ends, offer to stop the instance
    print("\n" + "=" * 60)
    print("  SSH Session Ended")
    print("=" * 60)

    print(f"\nYour work on instance '{instance_name}' is complete.")
    if confirm("Would you like to STOP the instance to save costs?"):
        stop_instance(ec2_client, instance_id, instance_name)
    else:
        print(f"Instance '{instance_name}' will remain running.")
        print("Remember to stop it manually when you're done to avoid charges!")

    print("\nGoodbye!")


if __name__ == "__main__":
    main()
