#!/usr/bin/env python3
"""
AWS DevOps Agent Setup Script (Python - using AWS CLI)

Account: 226563001214
Region: us-east-1
Includes: New Relic Integration

Prerequisites:
    - Python 3.8+
    - AWS CLI v2 installed and configured
    - IAM permissions to create roles and attach policies

Usage:
    python setup_devops_agent.py

Cleanup:
    python setup_devops_agent.py --cleanup <AGENT_SPACE_ID>
"""

import json
import os
import subprocess
import sys
import tempfile
import time


# ============================================================
# CONFIGURATION - Update these values as needed
# ============================================================
CONFIG = {
    "monitoring_account_id": "226563001214",
    "region": "us-east-1",
    "agent_space_name": "DevOps-Agent-Space",
    "agent_space_description": "DevOps Agent Space for monitoring AWS infrastructure",
    "auth_flow": "iam",
    # AWS Profile (from ~/.aws/config)
    "aws_profile": "DevOps-Role",
    # IAM Role Names
    "agentspace_role_name": "DevOpsAgentRole-AgentSpace",
    "operator_role_name": "DevOpsAgentRole-WebappAdmin",
    # New Relic Configuration
    "new_relic": {
        "api_key": "<YOUR_NEW_RELIC_API_KEY>",  # Replace with your NRAK-xxxx key
        "account_id": "6349186",
        "region": "US",
    },
}


# ============================================================
# HELPER FUNCTIONS
# ============================================================
def log_step(step_num: int, title: str):
    print(f"\n{'=' * 60}")
    print(f"  Step {step_num}: {title}")
    print(f"{'=' * 60}")


def log_success(message: str):
    print(f"  [OK] {message}")


def log_error(message: str):
    print(f"  [ERROR] {message}")


def log_warning(message: str):
    print(f"  [WARNING] {message}")


def log_info(message: str):
    print(f"  [INFO] {message}")


def run_aws_cli(args: list, capture_output=True, check=True) -> dict:
    """
    Run an AWS CLI command and return parsed JSON output.
    Uses the configured profile and region.
    """
    cmd = ["aws"] + args

    # Add profile if configured
    profile = CONFIG.get("aws_profile")
    if profile and "--profile" not in args:
        cmd += ["--profile", profile]

    # Add region if not already specified
    if "--region" not in args:
        cmd += ["--region", CONFIG["region"]]

    # Always request JSON output for parsing
    if "--output" not in args:
        cmd += ["--output", "json"]

    try:
        result = subprocess.run(
            cmd,
            capture_output=capture_output,
            text=True,
            check=check,
        )

        if result.stdout and result.stdout.strip():
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                return {"raw_output": result.stdout.strip()}
        return {}

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip() if e.stderr else str(e)
        if check:
            raise RuntimeError(f"AWS CLI command failed: {error_msg}")
        return {"error": error_msg}


def run_aws_cli_raw(args: list, check=True) -> subprocess.CompletedProcess:
    """Run AWS CLI and return the raw result (for error checking)."""
    cmd = ["aws"] + args

    profile = CONFIG.get("aws_profile")
    if profile and "--profile" not in args:
        cmd += ["--profile", profile]

    if "--region" not in args:
        cmd += ["--region", CONFIG["region"]]

    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def write_temp_json(data: dict, filename: str) -> str:
    """Write JSON to a temp file and return the path (cross-platform)."""
    temp_dir = tempfile.gettempdir()
    filepath = os.path.join(temp_dir, filename)
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)
    return filepath


# ============================================================
# STEP 0: Check Prerequisites
# ============================================================
def check_prerequisites() -> bool:
    log_step(0, "Checking Prerequisites")

    # Check AWS CLI is installed
    try:
        result = subprocess.run(
            ["aws", "--version"], capture_output=True, text=True, check=True
        )
        log_success(f"AWS CLI: {result.stdout.strip()}")
    except (FileNotFoundError, subprocess.CalledProcessError):
        log_error("AWS CLI is not installed or not in PATH.")
        log_info("Install from: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html")
        return False

    log_info(f"Using AWS Profile: {CONFIG.get('aws_profile', 'default')}")

    # Verify credentials
    try:
        identity = run_aws_cli(["sts", "get-caller-identity"])
        caller_account = identity.get("Account", "unknown")
        log_success(f"Authenticated as account: {caller_account}")
        log_info(f"ARN: {identity.get('Arn', 'N/A')}")

        if caller_account != CONFIG["monitoring_account_id"]:
            log_warning(
                f"Current account ({caller_account}) does not match "
                f"configured account ({CONFIG['monitoring_account_id']})"
            )
            response = input("  Continue anyway? (y/n): ").strip().lower()
            if response != "y":
                return False

    except RuntimeError as e:
        log_error(f"Failed to verify credentials: {e}")
        log_info("Run 'aws configure' or check your profile settings.")
        return False

    # Check New Relic API key
    if CONFIG["new_relic"]["api_key"] == "<YOUR_NEW_RELIC_API_KEY>":
        log_warning("New Relic API key is not set.")
        api_key = input("  Enter your New Relic API Key (NRAK-xxx) or press Enter to skip: ").strip()
        if api_key:
            CONFIG["new_relic"]["api_key"] = api_key
        else:
            log_info("New Relic integration will be skipped.")

    log_success("Prerequisites check passed!")
    return True


# ============================================================
# STEP 1: Create Agent Space IAM Role
# ============================================================
def create_agentspace_role() -> bool:
    log_step(1, "Creating Agent Space IAM Role")

    role_name = CONFIG["agentspace_role_name"]
    account_id = CONFIG["monitoring_account_id"]
    region = CONFIG["region"]

    # Check if role already exists
    result = run_aws_cli_raw(["iam", "get-role", "--role-name", role_name], check=False)
    if result.returncode == 0:
        log_info(f"Role '{role_name}' already exists. Skipping creation.")
        return True

    # Create trust policy
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "aidevops.amazonaws.com"},
                "Action": "sts:AssumeRole",
                "Condition": {
                    "StringEquals": {"aws:SourceAccount": account_id},
                    "ArnLike": {
                        "aws:SourceArn": f"arn:aws:aidevops:{region}:{account_id}:agentspace/*"
                    },
                },
            }
        ],
    }

    trust_policy_file = write_temp_json(trust_policy, "devops-agentspace-trust-policy.json")

    try:
        # Create the role
        run_aws_cli([
            "iam", "create-role",
            "--role-name", role_name,
            "--assume-role-policy-document", f"file://{trust_policy_file}",
            "--description", "IAM role for AWS DevOps Agent Space",
        ])
        log_success(f"Created role: {role_name}")

        # Attach managed policy
        run_aws_cli([
            "iam", "attach-role-policy",
            "--role-name", role_name,
            "--policy-arn", "arn:aws:iam::aws:policy/AIDevOpsAgentAccessPolicy",
        ])
        log_success("Attached AIDevOpsAgentAccessPolicy")

        # Create inline policy for Resource Explorer SLR
        inline_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "AllowCreateServiceLinkedRoles",
                    "Effect": "Allow",
                    "Action": ["iam:CreateServiceLinkedRole"],
                    "Resource": [
                        f"arn:aws:iam::{account_id}:role/aws-service-role/"
                        f"resource-explorer-2.amazonaws.com/AWSServiceRoleForResourceExplorer"
                    ],
                }
            ],
        }

        inline_policy_file = write_temp_json(inline_policy, "devops-agentspace-additional-policy.json")

        run_aws_cli([
            "iam", "put-role-policy",
            "--role-name", role_name,
            "--policy-name", "AllowCreateServiceLinkedRoles",
            "--policy-document", f"file://{inline_policy_file}",
        ])
        log_success("Attached inline policy: AllowCreateServiceLinkedRoles")

    except RuntimeError as e:
        log_error(f"Failed to create Agent Space role: {e}")
        return False

    return True


# ============================================================
# STEP 2: Create Operator App IAM Role
# ============================================================
def create_operator_role() -> bool:
    log_step(2, "Creating Operator App IAM Role")

    role_name = CONFIG["operator_role_name"]
    account_id = CONFIG["monitoring_account_id"]
    region = CONFIG["region"]

    # Check if role already exists
    result = run_aws_cli_raw(["iam", "get-role", "--role-name", role_name], check=False)
    if result.returncode == 0:
        log_info(f"Role '{role_name}' already exists. Skipping creation.")
        return True

    # Create trust policy
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "aidevops.amazonaws.com"},
                "Action": ["sts:AssumeRole", "sts:TagSession"],
                "Condition": {
                    "StringEquals": {"aws:SourceAccount": account_id},
                    "ArnLike": {
                        "aws:SourceArn": f"arn:aws:aidevops:{region}:{account_id}:agentspace/*"
                    },
                },
            }
        ],
    }

    trust_policy_file = write_temp_json(trust_policy, "devops-operator-trust-policy.json")

    try:
        # Create the role
        run_aws_cli([
            "iam", "create-role",
            "--role-name", role_name,
            "--assume-role-policy-document", f"file://{trust_policy_file}",
            "--description", "IAM role for AWS DevOps Agent Operator Web App",
        ])
        log_success(f"Created role: {role_name}")

        # Attach managed policy
        run_aws_cli([
            "iam", "attach-role-policy",
            "--role-name", role_name,
            "--policy-arn", "arn:aws:iam::aws:policy/AIDevOpsOperatorAppAccessPolicy",
        ])
        log_success("Attached AIDevOpsOperatorAppAccessPolicy")

    except RuntimeError as e:
        log_error(f"Failed to create Operator role: {e}")
        return False

    return True


# ============================================================
# STEP 3: Create the Agent Space
# ============================================================
def create_agent_space():
    log_step(3, "Creating Agent Space")

    log_info("Waiting 10 seconds for IAM role propagation...")
    time.sleep(10)

    try:
        response = run_aws_cli([
            "devops-agent", "create-agent-space",
            "--name", CONFIG["agent_space_name"],
            "--description", CONFIG["agent_space_description"],
        ])

        agent_space_id = response.get("agentSpace", {}).get("agentSpaceId")

        if not agent_space_id:
            log_error(f"Failed to extract Agent Space ID. Response: {response}")
            return None

        log_success("Agent Space created!")
        log_info(f"Name: {CONFIG['agent_space_name']}")
        log_info(f"ID:   {agent_space_id}")
        return agent_space_id

    except RuntimeError as e:
        log_error(f"Failed to create Agent Space: {e}")
        return None


# ============================================================
# STEP 4: Associate AWS Account
# ============================================================
def associate_aws_account(agent_space_id: str) -> bool:
    log_step(4, "Associating AWS Account")

    account_id = CONFIG["monitoring_account_id"]
    role_name = CONFIG["agentspace_role_name"]

    configuration = json.dumps({
        "aws": {
            "assumableRoleArn": f"arn:aws:iam::{account_id}:role/{role_name}",
            "accountId": account_id,
            "accountType": "monitor",
        }
    })

    try:
        run_aws_cli([
            "devops-agent", "associate-service",
            "--agent-space-id", agent_space_id,
            "--service-id", "aws",
            "--configuration", configuration,
        ])
        log_success("AWS account associated as monitor account.")
        return True

    except RuntimeError as e:
        log_error(f"Failed to associate AWS account: {e}")
        return False


# ============================================================
# STEP 5: Enable Operator App
# ============================================================
def enable_operator_app(agent_space_id: str) -> bool:
    log_step(5, "Enabling Operator Web App")

    account_id = CONFIG["monitoring_account_id"]
    role_name = CONFIG["operator_role_name"]

    try:
        run_aws_cli([
            "devops-agent", "enable-operator-app",
            "--agent-space-id", agent_space_id,
            "--auth-flow", CONFIG["auth_flow"],
            "--operator-app-role-arn", f"arn:aws:iam::{account_id}:role/{role_name}",
        ])
        log_success(f"Operator Web App enabled (auth-flow: {CONFIG['auth_flow']})")
        return True

    except RuntimeError as e:
        log_error(f"Failed to enable Operator App: {e}")
        return False


# ============================================================
# STEP 6: Register and Associate New Relic
# ============================================================
def setup_new_relic(agent_space_id: str) -> bool:
    log_step(6, "Setting Up New Relic Integration")

    nr_config = CONFIG["new_relic"]

    if nr_config["api_key"] == "<YOUR_NEW_RELIC_API_KEY>" or not nr_config["api_key"]:
        log_info("Skipping New Relic integration (no API key provided).")
        return True

    # Register New Relic service
    log_info("Registering New Relic service...")

    service_details = json.dumps({
        "mcpservernewrelic": {
            "authorizationConfig": {
                "apiKey": {
                    "apiKey": nr_config["api_key"],
                    "accountId": nr_config["account_id"],
                    "region": nr_config["region"],
                }
            }
        }
    })

    try:
        register_response = run_aws_cli([
            "devops-agent", "register-service",
            "--service", "mcpservernewrelic",
            "--service-details", service_details,
        ])

        service_id = register_response.get("serviceId")

        if not service_id:
            log_error(f"Failed to get service ID. Response: {register_response}")
            return False

        log_success(f"New Relic registered with Service ID: {service_id}")

    except RuntimeError as e:
        log_error(f"Failed to register New Relic: {e}")
        return False

    # Associate New Relic with Agent Space
    log_info("Associating New Relic with Agent Space...")

    association_config = json.dumps({
        "mcpservernewrelic": {
            "accountId": nr_config["account_id"],
            "endpoint": "https://mcp.newrelic.com/mcp/",
        }
    })

    try:
        run_aws_cli([
            "devops-agent", "associate-service",
            "--agent-space-id", agent_space_id,
            "--service-id", service_id,
            "--configuration", association_config,
        ])
        log_success("New Relic associated with Agent Space!")
        return True

    except RuntimeError as e:
        log_error(f"Failed to associate New Relic: {e}")
        return False


# ============================================================
# STEP 7: Verification
# ============================================================
def verify_setup(agent_space_id: str) -> bool:
    log_step(7, "Verifying Setup")

    try:
        # Get agent space details
        log_info("Getting agent space details...")
        space_details = run_aws_cli([
            "devops-agent", "get-agent-space",
            "--agent-space-id", agent_space_id,
        ])
        space = space_details.get("agentSpace", {})
        log_success(f"Agent Space: {space.get('name', 'N/A')}")
        log_info(f"Status: {space.get('status', 'N/A')}")

        # List associations
        log_info("Listing associations...")
        associations = run_aws_cli([
            "devops-agent", "list-associations",
            "--agent-space-id", agent_space_id,
        ])
        for assoc in associations.get("associations", []):
            log_success(f"Association: {assoc.get('serviceId', 'unknown')} - {assoc.get('status', 'N/A')}")

        return True

    except RuntimeError as e:
        log_error(f"Verification failed: {e}")
        return False


# ============================================================
# SUMMARY
# ============================================================
def print_summary(agent_space_id: str):
    region = CONFIG["region"]
    print(f"\n{'=' * 60}")
    print(f"  SETUP COMPLETE!")
    print(f"{'=' * 60}")
    print()
    print(f"  AWS DevOps Agent has been successfully created!")
    print()
    print(f"  Summary:")
    print(f"  {'─' * 50}")
    print(f"  Account ID:       {CONFIG['monitoring_account_id']}")
    print(f"  Region:           {region}")
    print(f"  Agent Space Name: {CONFIG['agent_space_name']}")
    print(f"  Agent Space ID:   {agent_space_id}")
    print(f"  Auth Flow:        {CONFIG['auth_flow']}")
    print(f"  New Relic:        Account {CONFIG['new_relic']['account_id']} ({CONFIG['new_relic']['region']})")
    print(f"  {'─' * 50}")
    print()
    print(f"  Next Steps:")
    print(f"  1. Access the Web App from the AWS DevOps Agent console")
    print(f"  2. The agent will begin discovering your AWS resources")
    print(f"  3. Set up CloudWatch alarms to trigger investigations")
    print()
    print(f"  Console URL:")
    print(f"  https://{region}.console.aws.amazon.com/devops-agent/home?region={region}")
    print()


# ============================================================
# CLEANUP (Optional)
# ============================================================
def cleanup(agent_space_id=None):
    """Delete all resources created by this script."""
    print("\n  WARNING: This will delete all DevOps Agent resources!")
    response = input("  Are you sure? (type 'DELETE' to confirm): ").strip()

    if response != "DELETE":
        print("  Cleanup cancelled.")
        return

    # Delete agent space
    if agent_space_id:
        try:
            run_aws_cli([
                "devops-agent", "delete-agent-space",
                "--agent-space-id", agent_space_id,
            ])
            log_success(f"Deleted Agent Space: {agent_space_id}")
        except RuntimeError as e:
            log_error(f"Failed to delete Agent Space: {e}")

    # Delete IAM roles
    for role_name in [CONFIG["agentspace_role_name"], CONFIG["operator_role_name"]]:
        try:
            # List and detach managed policies
            result = run_aws_cli_raw([
                "iam", "list-attached-role-policies",
                "--role-name", role_name,
                "--output", "json",
            ], check=False)

            if result.returncode == 0 and result.stdout:
                policies = json.loads(result.stdout).get("AttachedPolicies", [])
                for policy in policies:
                    run_aws_cli_raw([
                        "iam", "detach-role-policy",
                        "--role-name", role_name,
                        "--policy-arn", policy["PolicyArn"],
                    ], check=False)

            # List and delete inline policies
            result = run_aws_cli_raw([
                "iam", "list-role-policies",
                "--role-name", role_name,
                "--output", "json",
            ], check=False)

            if result.returncode == 0 and result.stdout:
                policy_names = json.loads(result.stdout).get("PolicyNames", [])
                for policy_name in policy_names:
                    run_aws_cli_raw([
                        "iam", "delete-role-policy",
                        "--role-name", role_name,
                        "--policy-name", policy_name,
                    ], check=False)

            # Delete the role
            run_aws_cli_raw([
                "iam", "delete-role",
                "--role-name", role_name,
            ], check=False)
            log_success(f"Deleted role: {role_name}")

        except Exception as e:
            log_error(f"Failed to delete role {role_name}: {e}")


# ============================================================
# MAIN
# ============================================================
def main():
    print()
    print(f"  AWS DevOps Agent Setup Script (Python)")
    print(f"  Account: {CONFIG['monitoring_account_id']} | Region: {CONFIG['region']}")
    print(f"  Profile: {CONFIG.get('aws_profile', 'default')}")
    print()

    # Handle cleanup mode
    if len(sys.argv) > 1 and sys.argv[1] == "--cleanup":
        if len(sys.argv) > 2:
            cleanup(sys.argv[2])
        else:
            agent_space_id = input("  Enter Agent Space ID to delete: ").strip()
            cleanup(agent_space_id if agent_space_id else None)
        return

    # Run setup
    if not check_prerequisites():
        sys.exit(1)

    if not create_agentspace_role():
        sys.exit(1)

    if not create_operator_role():
        sys.exit(1)

    agent_space_id = create_agent_space()
    if not agent_space_id:
        sys.exit(1)

    if not associate_aws_account(agent_space_id):
        log_warning("Continuing despite AWS account association failure...")

    if not enable_operator_app(agent_space_id):
        log_warning("Continuing despite Operator App enablement failure...")

    setup_new_relic(agent_space_id)

    verify_setup(agent_space_id)

    print_summary(agent_space_id)


if __name__ == "__main__":
    main()
