# Python Scripts Collection

A collection of useful Python scripts for DevOps and Cloud operations.

## Scripts

### 1. SSL Certificate Checker (`ssl_certificate_checker.py`)

Check SSL certificate validity and create self-signed certificates.

**Features:**
- Check SSL certificate for single or multiple domains
- Display certificate details (issuer, subject, SANs, expiry dates)
- Show days remaining until expiration with status alerts
- Support custom port numbers
- Create self-signed SSL certificates for development/testing

**Usage:**
```bash
python ssl_certificate_checker.py
```

---

### 2. Website Up/Down Monitor (`website_monitor.py`)

Monitor website availability with detailed error reporting.

**Features:**
- Check if websites are UP or DOWN
- Display HTTP status codes with human-readable descriptions
- Detailed error messages (DNS failure, timeout, SSL errors, connection refused, etc.)
- Monitor multiple websites simultaneously
- Continuous monitoring mode with configurable intervals
- Response time measurement
- Color-coded terminal output
- Verbose mode showing response headers

**Usage:**
```bash
python website_monitor.py
```

---

### 3. S3 Bucket Manager (`s3_bucket_manager.py`)

Interactive AWS S3 bucket management tool.

**Features:**
- Interactive prompts for AWS Account / Region / S3 Bucket Name
- Multiple authentication methods (AWS Profile, Access Keys, Default credentials)
- List bucket contents with folder structure
- Download full bucket contents
- Download specific folders (including all files and sub-objects)
- Create presigned URLs for sharing objects with external users
- Upload files to bucket
- Browse bucket folder structure

**Usage:**
```bash
python s3_bucket_manager.py
```

---

### 4. EC2 Start/Stop Manager (`ec2_start_stop.py`)

Programmatic CLI tool for starting and stopping AWS EC2 instances with beautiful output.

**Features:**
- Start / Stop / Restart individual or multiple instances
- List all instances with color-coded status table
- Tag-based filtering (e.g., `--tag Environment=dev`)
- Dry-run mode for safe testing (`--dry-run`)
- Wait mode to block until desired state is reached (`--wait`)
- Force stop option for unresponsive instances
- Multi-region and AWS profile support
- Rich formatted output with status icons (graceful fallback without `rich`)
- Detailed health status checks (system + instance)

**Usage:**
```bash
# List all instances (pretty table)
python ec2_start_stop.py list

# List by tag
python ec2_start_stop.py list --tag Environment=production

# Start an instance
python ec2_start_stop.py start i-0123456789abcdef0

# Stop with wait
python ec2_start_stop.py stop i-0123456789abcdef0 --wait

# Start all dev instances (dry-run first)
python ec2_start_stop.py start --tag Environment=dev --dry-run

# Restart multiple instances
python ec2_start_stop.py restart i-0abc123 i-0def456

# Check instance health
python ec2_start_stop.py status i-0123456789abcdef0

# Use specific region/profile
python ec2_start_stop.py --region eu-west-1 --profile prod list
```

---

## Installation

```bash
# Clone the repository
git clone git@github.com:Eclouddevops/Python-scripts.git
cd Python-scripts

# Install dependencies
pip install -r requirements.txt
```

## Requirements

- Python 3.7+
- `requests` - For HTTP website monitoring
- `boto3` - For AWS EC2 and S3 operations
- `cryptography` - For SSL certificate creation
- `rich` - For beautiful terminal output (optional, graceful fallback)

## License

MIT
