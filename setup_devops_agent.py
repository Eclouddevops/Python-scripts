#!/usr/bin/env python3
"""
AWS DevOps Agent Setup Script (Python)

Account: 226563001214
Region: us-east-1
Includes: New Relic Integration

Prerequisites:
    - Python 3.8+
    - boto3 installed (pip install boto3)
    - AWS credentials configured (~/.aws/credentials or environment variables)
    - IAM permissions to create roles and attach policies

Usage:
    pip install boto3
    python setup_devops_agent.py
"""

import json
import sys
import time
from typing import Optional

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
except ImportError:
    print("ERROR: boto3 is required. Install it with: pip install boto3")
    sys.exit(1)


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
    # Available profiles: DevOps-Role, swap-devops, devops-team, ethinos,
    #   ethinos-prod, core-nonprod-workload, core-prod-workload, etc.
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
    """Print a formatted step header."""
    print(f"\n{'=' * 60}")
    print(f"  Step {step_num}: {title}")
    print(f"{'=' * 60}")


def log_success(message: str):
    """Print a success message."""
    print(f"  [OK] {message}")


def log_error(message: str):
    """Print an error message."""
    print(f"  [ERROR] {message}")


def log_warning(message: str):
    """Print a warning message."""
    print(f"  [WARNING] {message}")


def log_info(message: str):
    """Print an info message."""
    print(f"  [INFO] {message}")


def get_boto3_session():
    """Get a boto3 session using the configured profile."""
    profile = CONFIG.get("aws_profile")
    if profile:
        return boto3.Session(profile_name=profile, region_name=CONFIG["region"])
    return boto3.Session(region_name=CONFIG["region"])


def get_iam_client():
    """Get IAM client."""
    session = get_boto3_session()
    return session.client("iam")


def get_devops_agent_client():
    """Get DevOps Agent client."""
    session = get_boto3_session()
    return session.client("devops-agent")


def get_sts_client():
    """Get STS client."""
    session = get_boto3_session()
    return session.client("sts")


# ============================================================
# STEP 0: Check Prerequisites
# ============================================================
def check_prerequisites() -> bool:
    """Verify AWS credentials and account."""
    log_step(0, "Checking Prerequisites")

    log_info(f"Using AWS Profile: {CONFIG.get('aws_profile', 'default')}")

    try:
        sts = get_sts_client()
        identity = sts.get_caller_identity()
        caller_account = identity["Account"]
        log_success(f"Authenticated as account: {caller_account}")
        log_info(f"ARN: {identity['Arn']}")

        if caller_account != CONFIG["monitoring_account_id"]:
            log_warning(
                f"Current account ({caller_account}) does not match "
                f"configured account ({CONFIG['monitoring_account_id']})"
            )
            response = input("  Continue anyway? (y/n): ").strip().lower()
            if response != "y":
                return False

    except NoCredentialsError:
        log_error("AWS credentials not configured.")
        log_info("Run 'aws configure' or set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY")
        return False
    except ClientError as e:
        log_error(f"Failed to verify credentials: {e}")
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
    """Create the Agent Space IAM role with required policies."""
    log_step(1, "Creating Agent Space IAM Role")

    iam = get_iam_client()
    role_name = CONFIG["agentspace_role_name"]
    account_id = CONFIG["monitoring_account_id"]
    region = CONFIG["region"]

    # Check if role already exists
    try:
        iam.get_role(RoleName=role_name)
        log_info(f"Role '{role_name}' already exists. Skipping creation.")
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] != "NoSuchEntity":
            log_error(f"Error checking role: {e}")
            return False

    # Trust policy
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

    try:
        # Create the role
        iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description="IAM role for AWS DevOps Agent Space",
        )
        log_success(f"Created role: {role_name}")

        # Attach managed policy
        iam.attach_role_policy(
            RoleName=role_name,
            PolicyArn="arn:aws:iam::aws:policy/AIDevOpsAgentAccessPolicy",
        )
        log_success("Attached AIDevOpsAgentAccessPolicy")

        # Attach inline policy for Resource Explorer SLR
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

        iam.put_role_policy(
            RoleName=role_name,
            PolicyName="AllowCreateServiceLinkedRoles",
            PolicyDocument=json.dumps(inline_policy),
        )
        log_success("Attached inline policy: AllowCreateServiceLinkedRoles")

    except ClientError as e:
        log_error(f"Failed to create Agent Space role: {e}")
        return False

    return True


# ============================================================
# STEP 2: Create Operator App IAM Role
# ============================================================
def create_operator_role() -> bool:
    """Create the Operator App IAM role."""
    log_step(2, "Creating Operator App IAM Role")

    iam = get_iam_client()
    role_name = CONFIG["operator_role_name"]
    account_id = CONFIG["monitoring_account_id"]
    region = CONFIG["region"]

    # Check if role already exists
    try:
        iam.get_role(RoleName=role_name)
        log_info(f"Role '{role_name}' already exists. Skipping creation.")
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] != "NoSuchEntity":
            log_error(f"Error checking role: {e}")
            return False

    # Trust policy
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

    try:
        # Create the role
        iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description="IAM role for AWS DevOps Agent Operator Web App",
        )
        log_success(f"Created role: {role_name}")

        # Attach managed policy
        iam.attach_role_policy(
            RoleName=role_name,
            PolicyArn="arn:aws:iam::aws:policy/AIDevOpsOperatorAppAccessPolicy",
        )
        log_success("Attached AIDevOpsOperatorAppAccessPolicy")

    except ClientError as e:
        log_error(f"Failed to create Operator role: {e}")
        return False

    return True


# ============================================================
# STEP 3: Create the Agent Space
# ============================================================
def create_agent_space() -> Optional[str]:
    """Create the DevOps Agent Space and return its ID."""
    log_step(3, "Creating Agent Space")

    # Wait for IAM role propagation
    log_info("Waiting 10 seconds for IAM role propagation...")
    time.sleep(10)

    client = get_devops_agent_client()

    try:
        response = client.create_agent_space(
            name=CONFIG["agent_space_name"],
            description=CONFIG["agent_space_description"],
        )

        agent_space_id = response["agentSpace"]["agentSpaceId"]
        log_success(f"Agent Space created!")
        log_info(f"Name: {CONFIG['agent_space_name']}")
        log_info(f"ID:   {agent_space_id}")
        return agent_space_id

    except ClientError as e:
        log_error(f"Failed to create Agent Space: {e}")
        return None


# ============================================================
# STEP 4: Associate AWS Account
# ============================================================
def associate_aws_account(agent_space_id: str) -> bool:
    """Associate the monitoring AWS account with the Agent Space."""
    log_step(4, "Associating AWS Account")

    client = get_devops_agent_client()
    account_id = CONFIG["monitoring_account_id"]
    role_name = CONFIG["agentspace_role_name"]

    configuration = {
        "aws": {
            "assumableRoleArn": f"arn:aws:iam::{account_id}:role/{role_name}",
            "accountId": account_id,
            "accountType": "monitor",
        }
    }

    try:
        client.associate_service(
            agentSpaceId=agent_space_id,
            serviceId="aws",
            configuration=configuration,
        )
        log_success("AWS account associated as monitor account.")
        return True

    except ClientError as e:
        log_error(f"Failed to associate AWS account: {e}")
        return False


# ============================================================
# STEP 5: Enable Operator App
# ============================================================
def enable_operator_app(agent_space_id: str) -> bool:
    """Enable the Operator Web App for the Agent Space."""
    log_step(5, "Enabling Operator Web App")

    client = get_devops_agent_client()
    account_id = CONFIG["monitoring_account_id"]
    role_name = CONFIG["operator_role_name"]

    try:
        client.enable_operator_app(
            agentSpaceId=agent_space_id,
            authFlow=CONFIG["auth_flow"],
            operatorAppRoleArn=f"arn:aws:iam::{account_id}:role/{role_name}",
        )
        log_success(f"Operator Web App enabled (auth-flow: {CONFIG['auth_flow']})")
        return True

    except ClientError as e:
        log_error(f"Failed to enable Operator App: {e}")
        return False


# ============================================================
# STEP 6: Register and Associate New Relic
# ============================================================
def setup_new_relic(agent_space_id: str) -> bool:
    """Register and associate New Relic with the Agent Space."""
    log_step(6, "Setting Up New Relic Integration")

    nr_config = CONFIG["new_relic"]

    if nr_config["api_key"] == "<YOUR_NEW_RELIC_API_KEY>" or not nr_config["api_key"]:
        log_info("Skipping New Relic integration (no API key provided).")
        return True

    client = get_devops_agent_client()

    # Register New Relic service
    log_info("Registering New Relic service...")

    service_details = {
        "mcpservernewrelic": {
            "authorizationConfig": {
                "apiKey": {
                    "apiKey": nr_config["api_key"],
                    "accountId": nr_config["account_id"],
                    "region": nr_config["region"],
                }
            }
        }
    }

    try:
        register_response = client.register_service(
            service="mcpservernewrelic",
            serviceDetails=service_details,
        )

        service_id = register_response["serviceId"]
        log_success(f"New Relic registered with Service ID: {service_id}")

    except ClientError as e:
        log_error(f"Failed to register New Relic: {e}")
        return False

    # Associate New Relic with Agent Space
    log_info("Associating New Relic with Agent Space...")

    association_config = {
        "mcpservernewrelic": {
            "accountId": nr_config["account_id"],
            "endpoint": "https://mcp.newrelic.com/mcp/",
        }
    }

    try:
        client.associate_service(
            agentSpaceId=agent_space_id,
            serviceId=service_id,
            configuration=association_config,
        )
        log_success("New Relic associated with Agent Space!")
        return True

    except ClientError as e:
        log_error(f"Failed to associate New Relic: {e}")
        return False


# ============================================================
# STEP 7: Verification
# ============================================================
def verify_setup(agent_space_id: str) -> bool:
    """Verify the Agent Space setup."""
    log_step(7, "Verifying Setup")

    client = get_devops_agent_client()

    try:
        # Get agent space details
        log_info("Getting agent space details...")
        space_details = client.get_agent_space(agentSpaceId=agent_space_id)
        log_success(f"Agent Space: {space_details['agentSpace']['name']}")
        log_info(f"Status: {space_details['agentSpace'].get('status', 'N/A')}")

        # List associations
        log_info("Listing associations...")
        associations = client.list_associations(agentSpaceId=agent_space_id)
        for assoc in associations.get("associations", []):
            log_success(f"Association: {assoc.get('serviceId', 'unknown')} - {assoc.get('status', 'N/A')}")

        return True

    except ClientError as e:
        log_error(f"Verification failed: {e}")
        return False


# ============================================================
# SUMMARY
# ============================================================
def print_summary(agent_space_id: str):
    """Print the setup summary."""
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
def cleanup(agent_space_id: Optional[str] = None):
    """Delete all resources created by this script."""
    print("\n  WARNING: This will delete all DevOps Agent resources!")
    response = input("  Are you sure? (type 'DELETE' to confirm): ").strip()

    if response != "DELETE":
        print("  Cleanup cancelled.")
        return

    client = get_devops_agent_client()
    iam = get_iam_client()

    # Delete agent space
    if agent_space_id:
        try:
            client.delete_agent_space(agentSpaceId=agent_space_id)
            log_success(f"Deleted Agent Space: {agent_space_id}")
        except ClientError as e:
            log_error(f"Failed to delete Agent Space: {e}")

    # Delete IAM roles
    for role_name in [CONFIG["agentspace_role_name"], CONFIG["operator_role_name"]]:
        try:
            # Detach managed policies
            attached = iam.list_attached_role_policies(RoleName=role_name)
            for policy in attached["AttachedPolicies"]:
                iam.detach_role_policy(RoleName=role_name, PolicyArn=policy["PolicyArn"])

            # Delete inline policies
            inline = iam.list_role_policies(RoleName=role_name)
            for policy_name in inline["PolicyNames"]:
                iam.delete_role_policy(RoleName=role_name, PolicyName=policy_name)

            # Delete the role
            iam.delete_role(RoleName=role_name)
            log_success(f"Deleted role: {role_name}")

        except ClientError as e:
            if e.response["Error"]["Code"] != "NoSuchEntity":
                log_error(f"Failed to delete role {role_name}: {e}")


# ============================================================
# MAIN
# ============================================================
def main():
    """Main execution flow."""
    print()
    print(f"  AWS DevOps Agent Setup Script (Python)")
    print(f"  Account: {CONFIG['monitoring_account_id']} | Region: {CONFIG['region']}")
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
