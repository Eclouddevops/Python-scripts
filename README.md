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
- `boto3` - For AWS S3 operations
- `cryptography` - For SSL certificate creation

## License

MIT
