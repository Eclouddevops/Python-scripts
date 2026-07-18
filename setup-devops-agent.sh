#!/bin/bash
#
# AWS DevOps Agent Setup Script
# Account: 226563001214
# Region: us-east-1
# Includes: New Relic Integration
#
# Prerequisites:
#   - AWS CLI v2 installed and configured
#   - IAM permissions to create roles and attach policies
#   - New Relic User API Key (starts with NRAK-)
#
# Usage:
#   chmod +x setup-devops-agent.sh
#   ./setup-devops-agent.sh
#

set -euo pipefail

# ============================================================
# TEMP DIRECTORY - Cross-platform (Linux/macOS/Windows Git Bash)
# ============================================================
TMPDIR="${TMPDIR:-${TEMP:-${TMP:-/tmp}}}"
mkdir -p "$TMPDIR"

# ============================================================
# CONFIGURATION - Update these values as needed
# ============================================================
MONITORING_ACCOUNT_ID="226563001214"
REGION="us-east-1"
AGENT_SPACE_NAME="DevOps-Agent-Space"
AGENT_SPACE_DESCRIPTION="DevOps Agent Space for monitoring AWS infrastructure"
AUTH_FLOW="iam"

# AWS Profile (from ~/.aws/config)
# Available profiles in your config:
#   DevOps-Role (us-east-1), swap-devops (us-east-1),
#   devops-team (ap-south-1), ethinos (us-east-1),
#   core-nonprod-workload, core-prod-workload, etc.
AWS_PROFILE="${AWS_PROFILE:-DevOps-Role}"

# New Relic Configuration
NEW_RELIC_API_KEY="<YOUR_NEW_RELIC_API_KEY>"  # Replace with your NRAK-xxxx key
NEW_RELIC_ACCOUNT_ID="6349186"
NEW_RELIC_REGION="US"

# IAM Role Names
AGENTSPACE_ROLE_NAME="DevOpsAgentRole-AgentSpace"
OPERATOR_ROLE_NAME="DevOpsAgentRole-WebappAdmin"

# ============================================================
# HELPER FUNCTIONS
# ============================================================
log() {
    echo ""
    echo "============================================================"
    echo "  $1"
    echo "============================================================"
}

check_prerequisites() {
    log "Checking Prerequisites"

    if ! command -v aws &> /dev/null; then
        echo "ERROR: AWS CLI is not installed. Please install it first."
        echo "  https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
        exit 1
    fi

    echo "AWS CLI version: $(aws --version)"
    echo "Using AWS Profile: $AWS_PROFILE"
    export AWS_PROFILE

    # Check if credentials are configured
    if ! aws sts get-caller-identity --profile "$AWS_PROFILE" &> /dev/null; then
        echo "ERROR: AWS credentials not configured or expired for profile '$AWS_PROFILE'."
        echo "  Run 'aws configure --profile $AWS_PROFILE' or set environment variables."
        exit 1
    fi

    CALLER_ACCOUNT=$(aws sts get-caller-identity --profile "$AWS_PROFILE" --query 'Account' --output text)
    echo "Authenticated as account: $CALLER_ACCOUNT"

    if [ "$CALLER_ACCOUNT" != "$MONITORING_ACCOUNT_ID" ]; then
        echo "WARNING: Current account ($CALLER_ACCOUNT) does not match configured account ($MONITORING_ACCOUNT_ID)"
        read -p "Continue anyway? (y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi

    # Check if New Relic API key is set
    if [ "$NEW_RELIC_API_KEY" == "<YOUR_NEW_RELIC_API_KEY>" ]; then
        echo ""
        echo "WARNING: New Relic API key is not set."
        read -p "Enter your New Relic API Key (NRAK-xxx): " NEW_RELIC_API_KEY
        if [ -z "$NEW_RELIC_API_KEY" ]; then
            echo "No API key provided. New Relic integration will be skipped."
        fi
    fi

    echo "Prerequisites check passed!"
}

# ============================================================
# STEP 1: Create Agent Space IAM Role
# ============================================================
create_agentspace_role() {
    log "Step 1: Creating Agent Space IAM Role"

    # Check if role already exists
    if aws iam get-role --role-name "$AGENTSPACE_ROLE_NAME" &> /dev/null; then
        echo "Role '$AGENTSPACE_ROLE_NAME' already exists. Skipping creation."
        return 0
    fi

    # Create trust policy
    cat > "$TMPDIR/devops-agentspace-trust-policy.json" << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "aidevops.amazonaws.com"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "aws:SourceAccount": "${MONITORING_ACCOUNT_ID}"
        },
        "ArnLike": {
          "aws:SourceArn": "arn:aws:aidevops:${REGION}:${MONITORING_ACCOUNT_ID}:agentspace/*"
        }
      }
    }
  ]
}
EOF

    # Create the role
    aws iam create-role \
        --role-name "$AGENTSPACE_ROLE_NAME" \
        --assume-role-policy-document "file://$TMPDIR/devops-agentspace-trust-policy.json" \
        --region "$REGION"

    echo "Role created: $AGENTSPACE_ROLE_NAME"

    # Attach managed policy
    aws iam attach-role-policy \
        --role-name "$AGENTSPACE_ROLE_NAME" \
        --policy-arn arn:aws:iam::aws:policy/AIDevOpsAgentAccessPolicy

    echo "Attached AIDevOpsAgentAccessPolicy"

    # Create and attach inline policy for Resource Explorer SLR
    cat > "$TMPDIR/devops-agentspace-additional-policy.json" << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowCreateServiceLinkedRoles",
      "Effect": "Allow",
      "Action": [
        "iam:CreateServiceLinkedRole"
      ],
      "Resource": [
        "arn:aws:iam::${MONITORING_ACCOUNT_ID}:role/aws-service-role/resource-explorer-2.amazonaws.com/AWSServiceRoleForResourceExplorer"
      ]
    }
  ]
}
EOF

    aws iam put-role-policy \
        --role-name "$AGENTSPACE_ROLE_NAME" \
        --policy-name AllowCreateServiceLinkedRoles \
        --policy-document "file://$TMPDIR/devops-agentspace-additional-policy.json"

    echo "Attached inline policy: AllowCreateServiceLinkedRoles"
    echo "Step 1 complete!"
}

# ============================================================
# STEP 2: Create Operator App IAM Role
# ============================================================
create_operator_role() {
    log "Step 2: Creating Operator App IAM Role"

    # Check if role already exists
    if aws iam get-role --role-name "$OPERATOR_ROLE_NAME" &> /dev/null; then
        echo "Role '$OPERATOR_ROLE_NAME' already exists. Skipping creation."
        return 0
    fi

    # Create trust policy
    cat > "$TMPDIR/devops-operator-trust-policy.json" << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "aidevops.amazonaws.com"
      },
      "Action": [
        "sts:AssumeRole",
        "sts:TagSession"
      ],
      "Condition": {
        "StringEquals": {
          "aws:SourceAccount": "${MONITORING_ACCOUNT_ID}"
        },
        "ArnLike": {
          "aws:SourceArn": "arn:aws:aidevops:${REGION}:${MONITORING_ACCOUNT_ID}:agentspace/*"
        }
      }
    }
  ]
}
EOF

    # Create the role
    aws iam create-role \
        --role-name "$OPERATOR_ROLE_NAME" \
        --assume-role-policy-document "file://$TMPDIR/devops-operator-trust-policy.json" \
        --region "$REGION"

    echo "Role created: $OPERATOR_ROLE_NAME"

    # Attach managed policy
    aws iam attach-role-policy \
        --role-name "$OPERATOR_ROLE_NAME" \
        --policy-arn arn:aws:iam::aws:policy/AIDevOpsOperatorAppAccessPolicy

    echo "Attached AIDevOpsOperatorAppAccessPolicy"
    echo "Step 2 complete!"
}

# ============================================================
# STEP 3: Create the Agent Space
# ============================================================
create_agent_space() {
    log "Step 3: Creating Agent Space"

    # Wait for IAM roles to propagate
    echo "Waiting 10 seconds for IAM role propagation..."
    sleep 10

    RESPONSE=$(aws devops-agent create-agent-space \
        --name "$AGENT_SPACE_NAME" \
        --description "$AGENT_SPACE_DESCRIPTION" \
        --region "$REGION" \
        --output json)

    AGENT_SPACE_ID=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['agentSpace']['agentSpaceId'])" 2>/dev/null || echo "")

    if [ -z "$AGENT_SPACE_ID" ]; then
        echo "ERROR: Failed to extract Agent Space ID from response."
        echo "Response: $RESPONSE"
        exit 1
    fi

    echo "Agent Space created!"
    echo "  Name: $AGENT_SPACE_NAME"
    echo "  ID:   $AGENT_SPACE_ID"

    # Export for subsequent steps
    export AGENT_SPACE_ID
    echo "Step 3 complete!"
}

# ============================================================
# STEP 4: Associate AWS Account
# ============================================================
associate_aws_account() {
    log "Step 4: Associating AWS Account"

    aws devops-agent associate-service \
        --agent-space-id "$AGENT_SPACE_ID" \
        --service-id aws \
        --configuration "{
            \"aws\": {
                \"assumableRoleArn\": \"arn:aws:iam::${MONITORING_ACCOUNT_ID}:role/${AGENTSPACE_ROLE_NAME}\",
                \"accountId\": \"${MONITORING_ACCOUNT_ID}\",
                \"accountType\": \"monitor\"
            }
        }" \
        --region "$REGION"

    echo "AWS account associated as monitor account."
    echo "Step 4 complete!"
}

# ============================================================
# STEP 5: Enable Operator App
# ============================================================
enable_operator_app() {
    log "Step 5: Enabling Operator Web App"

    aws devops-agent enable-operator-app \
        --agent-space-id "$AGENT_SPACE_ID" \
        --auth-flow "$AUTH_FLOW" \
        --operator-app-role-arn "arn:aws:iam::${MONITORING_ACCOUNT_ID}:role/${OPERATOR_ROLE_NAME}" \
        --region "$REGION"

    echo "Operator Web App enabled with auth-flow: $AUTH_FLOW"
    echo "Step 5 complete!"
}

# ============================================================
# STEP 6: Register and Associate New Relic
# ============================================================
setup_new_relic() {
    log "Step 6: Setting Up New Relic Integration"

    if [ "$NEW_RELIC_API_KEY" == "<YOUR_NEW_RELIC_API_KEY>" ] || [ -z "$NEW_RELIC_API_KEY" ]; then
        echo "Skipping New Relic integration (no API key provided)."
        return 0
    fi

    echo "Registering New Relic service..."

    REGISTER_RESPONSE=$(aws devops-agent register-service \
        --service mcpservernewrelic \
        --service-details "{
            \"mcpservernewrelic\": {
                \"authorizationConfig\": {
                    \"apiKey\": {
                        \"apiKey\": \"${NEW_RELIC_API_KEY}\",
                        \"accountId\": \"${NEW_RELIC_ACCOUNT_ID}\",
                        \"region\": \"${NEW_RELIC_REGION}\"
                    }
                }
            }
        }" \
        --region "$REGION" \
        --output json)

    NEW_RELIC_SERVICE_ID=$(echo "$REGISTER_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['serviceId'])" 2>/dev/null || echo "")

    if [ -z "$NEW_RELIC_SERVICE_ID" ]; then
        echo "ERROR: Failed to register New Relic. Response:"
        echo "$REGISTER_RESPONSE"
        return 1
    fi

    echo "New Relic registered with Service ID: $NEW_RELIC_SERVICE_ID"

    echo "Associating New Relic with Agent Space..."

    aws devops-agent associate-service \
        --agent-space-id "$AGENT_SPACE_ID" \
        --service-id "$NEW_RELIC_SERVICE_ID" \
        --configuration "{
            \"mcpservernewrelic\": {
                \"accountId\": \"${NEW_RELIC_ACCOUNT_ID}\",
                \"endpoint\": \"https://mcp.newrelic.com/mcp/\"
            }
        }" \
        --region "$REGION"

    echo "New Relic associated with Agent Space!"
    echo "Step 6 complete!"
}

# ============================================================
# STEP 7: Verification
# ============================================================
verify_setup() {
    log "Step 7: Verifying Setup"

    echo "Listing agent spaces..."
    aws devops-agent list-agent-spaces --region "$REGION"

    echo ""
    echo "Getting agent space details..."
    aws devops-agent get-agent-space \
        --agent-space-id "$AGENT_SPACE_ID" \
        --region "$REGION"

    echo ""
    echo "Listing associations..."
    aws devops-agent list-associations \
        --agent-space-id "$AGENT_SPACE_ID" \
        --region "$REGION"

    echo ""
    echo "Step 7 complete!"
}

# ============================================================
# SUMMARY
# ============================================================
print_summary() {
    log "SETUP COMPLETE!"

    echo ""
    echo "  AWS DevOps Agent has been successfully created!"
    echo ""
    echo "  Summary:"
    echo "  ----------------------------------------"
    echo "  Account ID:       $MONITORING_ACCOUNT_ID"
    echo "  Region:           $REGION"
    echo "  Agent Space Name: $AGENT_SPACE_NAME"
    echo "  Agent Space ID:   $AGENT_SPACE_ID"
    echo "  Auth Flow:        $AUTH_FLOW"
    echo "  New Relic:        Account $NEW_RELIC_ACCOUNT_ID ($NEW_RELIC_REGION)"
    echo "  ----------------------------------------"
    echo ""
    echo "  Next Steps:"
    echo "  1. Access the Web App from the AWS DevOps Agent console"
    echo "  2. The agent will begin discovering your AWS resources"
    echo "  3. Set up CloudWatch alarms to trigger investigations"
    echo ""
    echo "  Console URL:"
    echo "  https://${REGION}.console.aws.amazon.com/devops-agent/home?region=${REGION}"
    echo ""
}

# ============================================================
# MAIN EXECUTION
# ============================================================
main() {
    echo ""
    echo "  AWS DevOps Agent Setup Script"
    echo "  Account: $MONITORING_ACCOUNT_ID | Region: $REGION"
    echo ""

    check_prerequisites
    create_agentspace_role
    create_operator_role
    create_agent_space
    associate_aws_account
    enable_operator_app
    setup_new_relic
    verify_setup
    print_summary
}

# Run
main "$@"
