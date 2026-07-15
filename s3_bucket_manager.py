#!/usr/bin/env python3
"""
S3 Bucket Manager Script
==========================
Features:
1. Interactive prompts for AWS Account / Region / S3 Bucket Name
2. Download full bucket contents
3. Download only specific folders (including files and objects)
4. Create presigned URLs for sharing objects with external users
5. List bucket contents with folder structure
6. Upload files to bucket

Requirements:
    pip install boto3

Usage:
    python s3_bucket_manager.py
"""

import os
import sys
import time
import datetime

try:
    import boto3
    from botocore.exceptions import (
        ClientError,
        NoCredentialsError,
        PartialCredentialsError,
        ProfileNotFound,
    )
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False



# ANSI Color codes
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    RESET = '\033[0m'


def print_banner():
    """Display the script banner."""
    print("\n" + "#" * 70)
    print("#" + " " * 68 + "#")
    print("#     AWS S3 BUCKET MANAGER                                           #")
    print("#" + " " * 68 + "#")
    print("#" * 70)


def get_aws_configuration():
    """
    Interactively collect AWS configuration from the user.
    
    Returns:
        dict with aws_profile, region, bucket_name, and session
    """
    print(f"\n{'=' * 70}")
    print(f"  {Colors.BOLD}AWS CONFIGURATION{Colors.RESET}")
    print(f"{'=' * 70}")


    # AWS Authentication method
    print(f"\n  {Colors.CYAN}Authentication Method:{Colors.RESET}")
    print("  1. Use AWS Profile (from ~/.aws/credentials)")
    print("  2. Enter Access Key ID and Secret Access Key manually")
    print("  3. Use default credentials (environment variables / instance role)")
    
    auth_choice = input(f"\n  Select authentication method (1-3) [3]: ").strip() or "3"
    
    session_kwargs = {}
    
    if auth_choice == '1':
        profile = input("  Enter AWS Profile name [default]: ").strip() or "default"
        session_kwargs['profile_name'] = profile
        print(f"  Using profile: {Colors.GREEN}{profile}{Colors.RESET}")
    
    elif auth_choice == '2':
        access_key = input("  Enter AWS Access Key ID: ").strip()
        secret_key = input("  Enter AWS Secret Access Key: ").strip()
        if not access_key or not secret_key:
            print(f"  {Colors.RED}[ERROR] Access Key and Secret Key are required.{Colors.RESET}")
            return None
        session_kwargs['aws_access_key_id'] = access_key
        session_kwargs['aws_secret_access_key'] = secret_key
        
        session_token = input("  Enter Session Token (optional, press Enter to skip): ").strip()
        if session_token:
            session_kwargs['aws_session_token'] = session_token
    
    elif auth_choice == '3':
        print(f"  Using default credentials (env vars / instance role)")
    else:
        print(f"  {Colors.YELLOW}[WARNING] Invalid choice. Using default credentials.{Colors.RESET}")


    # AWS Region
    print(f"\n  {Colors.CYAN}Common AWS Regions:{Colors.RESET}")
    regions = [
        "us-east-1 (N. Virginia)", "us-east-2 (Ohio)",
        "us-west-1 (N. California)", "us-west-2 (Oregon)",
        "eu-west-1 (Ireland)", "eu-west-2 (London)",
        "eu-central-1 (Frankfurt)", "ap-south-1 (Mumbai)",
        "ap-southeast-1 (Singapore)", "ap-northeast-1 (Tokyo)",
    ]
    for i, region in enumerate(regions, 1):
        print(f"    {i:2}. {region}")
    
    region_input = input(f"\n  Enter AWS Region (name or number) [us-east-1]: ").strip() or "us-east-1"
    
    # Handle numeric selection
    region_names = [
        "us-east-1", "us-east-2", "us-west-1", "us-west-2",
        "eu-west-1", "eu-west-2", "eu-central-1", "ap-south-1",
        "ap-southeast-1", "ap-northeast-1",
    ]
    try:
        region_idx = int(region_input) - 1
        if 0 <= region_idx < len(region_names):
            region = region_names[region_idx]
        else:
            region = region_input
    except ValueError:
        region = region_input
    
    session_kwargs['region_name'] = region
    print(f"  Selected Region: {Colors.GREEN}{region}{Colors.RESET}")


    # Create session and validate
    try:
        session = boto3.Session(**session_kwargs)
        s3_client = session.client('s3')
        
        # Test credentials by listing buckets
        print(f"\n  Validating credentials...")
        response = s3_client.list_buckets()
        account_buckets = [b['Name'] for b in response.get('Buckets', [])]
        
        print(f"  {Colors.GREEN}[OK] Credentials validated successfully!{Colors.RESET}")
        print(f"  Found {len(account_buckets)} bucket(s) in this account.")
        
        if account_buckets:
            print(f"\n  {Colors.CYAN}Available Buckets:{Colors.RESET}")
            for i, bucket in enumerate(account_buckets, 1):
                print(f"    {i:3}. {bucket}")
    
    except NoCredentialsError:
        print(f"  {Colors.RED}[ERROR] No AWS credentials found.{Colors.RESET}")
        print("  Please configure credentials via:")
        print("    - AWS CLI: aws configure")
        print("    - Environment variables: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY")
        print("    - IAM Instance Role (if running on EC2)")
        return None
    except PartialCredentialsError:
        print(f"  {Colors.RED}[ERROR] Incomplete AWS credentials.{Colors.RESET}")
        return None
    except ProfileNotFound as e:
        print(f"  {Colors.RED}[ERROR] {e}{Colors.RESET}")
        return None
    except ClientError as e:
        print(f"  {Colors.RED}[ERROR] AWS Client Error: {e}{Colors.RESET}")
        return None


    # S3 Bucket Name
    print(f"\n  {Colors.CYAN}S3 Bucket Selection:{Colors.RESET}")
    bucket_input = input("  Enter S3 Bucket Name (or number from list above): ").strip()
    
    if not bucket_input:
        print(f"  {Colors.RED}[ERROR] Bucket name is required.{Colors.RESET}")
        return None
    
    # Handle numeric selection from bucket list
    try:
        bucket_idx = int(bucket_input) - 1
        if 0 <= bucket_idx < len(account_buckets):
            bucket_name = account_buckets[bucket_idx]
        else:
            bucket_name = bucket_input
    except (ValueError, UnboundLocalError):
        bucket_name = bucket_input
    
    # Verify bucket exists and is accessible
    try:
        s3_client.head_bucket(Bucket=bucket_name)
        print(f"  Selected Bucket: {Colors.GREEN}{bucket_name}{Colors.RESET}")
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == '404':
            print(f"  {Colors.RED}[ERROR] Bucket '{bucket_name}' does not exist.{Colors.RESET}")
        elif error_code == '403':
            print(f"  {Colors.RED}[ERROR] Access denied to bucket '{bucket_name}'.{Colors.RESET}")
        else:
            print(f"  {Colors.RED}[ERROR] Cannot access bucket: {e}{Colors.RESET}")
        return None
    
    print(f"\n{'=' * 70}")
    
    return {
        'session': session,
        's3_client': s3_client,
        'bucket_name': bucket_name,
        'region': region,
    }



def list_bucket_contents(s3_client, bucket_name, prefix="", show_tree=True):
    """
    List contents of an S3 bucket with folder structure.
    
    Args:
        s3_client: Boto3 S3 client
        bucket_name: Name of the S3 bucket
        prefix: Prefix/folder to list
        show_tree: Whether to display tree structure
    
    Returns:
        tuple of (folders, files)
    """
    folders = set()
    files = []
    total_size = 0
    
    paginator = s3_client.get_paginator('list_objects_v2')
    
    try:
        pages = paginator.paginate(Bucket=bucket_name, Prefix=prefix, Delimiter='/')
        
        for page in pages:
            # Get folders (common prefixes)
            for prefix_obj in page.get('CommonPrefixes', []):
                folder = prefix_obj['Prefix']
                folders.add(folder)
            
            # Get files
            for obj in page.get('Contents', []):
                key = obj['Key']
                # Skip the prefix itself if it's listed
                if key == prefix:
                    continue
                files.append({
                    'key': key,
                    'size': obj['Size'],
                    'last_modified': obj['LastModified'],
                })
                total_size += obj['Size']
    
    except ClientError as e:
        print(f"  {Colors.RED}[ERROR] Failed to list bucket: {e}{Colors.RESET}")
        return set(), []
    
    if show_tree:
        print(f"\n  {Colors.BOLD}Bucket: s3://{bucket_name}/{prefix}{Colors.RESET}")
        print(f"  {'─' * 60}")
        
        if folders:
            print(f"\n  {Colors.CYAN}Folders ({len(folders)}):{Colors.RESET}")
            for folder in sorted(folders):
                display_name = folder[len(prefix):] if prefix else folder
                print(f"    {Colors.BLUE}[DIR]{Colors.RESET} {display_name}")
        
        if files:
            print(f"\n  {Colors.CYAN}Files ({len(files)}):{Colors.RESET}")
            for f in sorted(files, key=lambda x: x['key']):
                display_name = f['key'][len(prefix):] if prefix else f['key']
                size_str = format_size(f['size'])
                modified = f['last_modified'].strftime('%Y-%m-%d %H:%M')
                print(f"    {Colors.GREEN}[FILE]{Colors.RESET} {display_name:<40} {size_str:>10}  {modified}")
        
        print(f"\n  Total: {len(folders)} folder(s), {len(files)} file(s), {format_size(total_size)}")
        print(f"  {'─' * 60}")
    
    return folders, files



def format_size(size_bytes):
    """Convert bytes to human-readable format."""
    if size_bytes == 0:
        return "0 B"
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    unit_index = 0
    size = float(size_bytes)
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    return f"{size:.2f} {units[unit_index]}"


def download_full_bucket(s3_client, bucket_name, download_dir=None):
    """
    Download the entire S3 bucket contents to local directory.
    
    Args:
        s3_client: Boto3 S3 client
        bucket_name: Name of the S3 bucket
        download_dir: Local directory to download to
    """
    if download_dir is None:
        download_dir = input(f"  Enter local download directory [./s3-download/{bucket_name}]: ").strip()
        if not download_dir:
            download_dir = f"./s3-download/{bucket_name}"
    
    print(f"\n  {Colors.BOLD}Downloading full bucket: s3://{bucket_name}{Colors.RESET}")
    print(f"  Destination: {download_dir}")
    
    # First, count total objects
    paginator = s3_client.get_paginator('list_objects_v2')
    total_objects = 0
    total_size = 0
    objects_to_download = []
    
    try:
        for page in paginator.paginate(Bucket=bucket_name):
            for obj in page.get('Contents', []):
                total_objects += 1
                total_size += obj['Size']
                objects_to_download.append(obj)
    except ClientError as e:
        print(f"  {Colors.RED}[ERROR] Failed to list bucket: {e}{Colors.RESET}")
        return
    
    if total_objects == 0:
        print(f"  {Colors.YELLOW}[INFO] Bucket is empty. Nothing to download.{Colors.RESET}")
        return
    
    print(f"  Total objects: {total_objects}")
    print(f"  Total size: {format_size(total_size)}")
    
    confirm = input(f"\n  Proceed with download? (yes/no) [yes]: ").strip().lower() or "yes"
    if confirm not in ('yes', 'y'):
        print("  Download cancelled.")
        return


    # Download objects
    downloaded = 0
    failed = 0
    start_time = time.time()
    
    for obj in objects_to_download:
        key = obj['Key']
        local_path = os.path.join(download_dir, key)
        
        # Create directory structure
        local_dir = os.path.dirname(local_path)
        os.makedirs(local_dir, exist_ok=True)
        
        # Skip if key ends with '/' (folder marker)
        if key.endswith('/'):
            continue
        
        try:
            s3_client.download_file(bucket_name, key, local_path)
            downloaded += 1
            progress = (downloaded / total_objects) * 100
            print(f"\r  [{progress:5.1f}%] Downloaded: {downloaded}/{total_objects} - {key[:50]}", end="", flush=True)
        except ClientError as e:
            failed += 1
            print(f"\n  {Colors.RED}[FAILED] {key}: {e}{Colors.RESET}")
        except Exception as e:
            failed += 1
            print(f"\n  {Colors.RED}[FAILED] {key}: {e}{Colors.RESET}")
    
    elapsed = time.time() - start_time
    print(f"\n\n  {Colors.GREEN}Download Complete!{Colors.RESET}")
    print(f"  Downloaded: {downloaded} file(s)")
    print(f"  Failed: {failed} file(s)")
    print(f"  Time elapsed: {elapsed:.1f} seconds")
    print(f"  Location: {os.path.abspath(download_dir)}")



def download_folder(s3_client, bucket_name, folder_prefix=None, download_dir=None):
    """
    Download a specific folder from S3 bucket including all files and sub-objects.
    
    Args:
        s3_client: Boto3 S3 client
        bucket_name: Name of the S3 bucket
        folder_prefix: The folder/prefix to download
        download_dir: Local directory to download to
    """
    # List available folders first
    if folder_prefix is None:
        print(f"\n  {Colors.BOLD}Available folders in s3://{bucket_name}:{Colors.RESET}")
        folders, _ = list_bucket_contents(s3_client, bucket_name, prefix="", show_tree=False)
        
        if folders:
            sorted_folders = sorted(folders)
            for i, folder in enumerate(sorted_folders, 1):
                print(f"    {i:3}. {folder}")
            
            folder_input = input(f"\n  Enter folder name/path or number from above: ").strip()
            
            # Handle numeric selection
            try:
                folder_idx = int(folder_input) - 1
                if 0 <= folder_idx < len(sorted_folders):
                    folder_prefix = sorted_folders[folder_idx]
                else:
                    folder_prefix = folder_input
            except ValueError:
                folder_prefix = folder_input
        else:
            folder_prefix = input(f"\n  Enter folder path/prefix to download: ").strip()
    
    if not folder_prefix:
        print(f"  {Colors.RED}[ERROR] Folder path is required.{Colors.RESET}")
        return
    
    # Ensure prefix ends with /
    if not folder_prefix.endswith('/'):
        folder_prefix += '/'
    
    if download_dir is None:
        default_dir = f"./s3-download/{bucket_name}/{folder_prefix.rstrip('/')}"
        download_dir = input(f"  Enter local download directory [{default_dir}]: ").strip()
        if not download_dir:
            download_dir = default_dir


    print(f"\n  {Colors.BOLD}Downloading folder: s3://{bucket_name}/{folder_prefix}{Colors.RESET}")
    print(f"  Destination: {download_dir}")
    
    # List all objects under the prefix (recursively)
    paginator = s3_client.get_paginator('list_objects_v2')
    objects_to_download = []
    total_size = 0
    
    try:
        for page in paginator.paginate(Bucket=bucket_name, Prefix=folder_prefix):
            for obj in page.get('Contents', []):
                objects_to_download.append(obj)
                total_size += obj['Size']
    except ClientError as e:
        print(f"  {Colors.RED}[ERROR] Failed to list folder contents: {e}{Colors.RESET}")
        return
    
    if not objects_to_download:
        print(f"  {Colors.YELLOW}[INFO] No objects found under prefix '{folder_prefix}'{Colors.RESET}")
        return
    
    print(f"  Objects found: {len(objects_to_download)}")
    print(f"  Total size: {format_size(total_size)}")
    
    confirm = input(f"\n  Proceed with download? (yes/no) [yes]: ").strip().lower() or "yes"
    if confirm not in ('yes', 'y'):
        print("  Download cancelled.")
        return
    
    # Download objects
    downloaded = 0
    failed = 0
    start_time = time.time()
    
    for obj in objects_to_download:
        key = obj['Key']
        # Remove the folder prefix to create relative path
        relative_key = key[len(folder_prefix):]
        if not relative_key:
            continue
        
        local_path = os.path.join(download_dir, relative_key)
        
        # Create directory structure
        local_dir = os.path.dirname(local_path)
        os.makedirs(local_dir, exist_ok=True)
        
        # Skip folder markers
        if key.endswith('/'):
            continue
        
        try:
            s3_client.download_file(bucket_name, key, local_path)
            downloaded += 1
            progress = (downloaded / len(objects_to_download)) * 100
            print(f"\r  [{progress:5.1f}%] Downloaded: {downloaded}/{len(objects_to_download)} - {relative_key[:50]}", end="", flush=True)
        except ClientError as e:
            failed += 1
            print(f"\n  {Colors.RED}[FAILED] {key}: {e}{Colors.RESET}")
        except Exception as e:
            failed += 1
            print(f"\n  {Colors.RED}[FAILED] {key}: {e}{Colors.RESET}")
    
    elapsed = time.time() - start_time
    print(f"\n\n  {Colors.GREEN}Folder Download Complete!{Colors.RESET}")
    print(f"  Downloaded: {downloaded} file(s)")
    print(f"  Failed: {failed} file(s)")
    print(f"  Time elapsed: {elapsed:.1f} seconds")
    print(f"  Location: {os.path.abspath(download_dir)}")



def create_presigned_url(s3_client, bucket_name, region):
    """
    Create presigned URLs for S3 objects to share with external users.
    
    Args:
        s3_client: Boto3 S3 client
        bucket_name: Name of the S3 bucket
        region: AWS region
    """
    print(f"\n{'=' * 70}")
    print(f"  {Colors.BOLD}CREATE PRESIGNED URL{Colors.RESET}")
    print(f"  Generate a temporary URL to share S3 objects with external users")
    print(f"{'=' * 70}")
    
    # List bucket contents to help user select
    print(f"\n  {Colors.CYAN}Bucket contents:{Colors.RESET}")
    folders, files = list_bucket_contents(s3_client, bucket_name, prefix="", show_tree=True)
    
    # Ask if user wants to browse into a folder
    browse = input(f"\n  Browse into a folder? (enter folder name or press Enter to skip): ").strip()
    if browse:
        if not browse.endswith('/'):
            browse += '/'
        folders, files = list_bucket_contents(s3_client, bucket_name, prefix=browse, show_tree=True)
    
    # Get the object key
    object_key = input(f"\n  Enter the S3 object key (full path) for presigned URL: ").strip()
    
    if not object_key:
        print(f"  {Colors.RED}[ERROR] Object key is required.{Colors.RESET}")
        return
    
    # Verify object exists
    try:
        s3_client.head_object(Bucket=bucket_name, Key=object_key)
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == '404':
            print(f"  {Colors.RED}[ERROR] Object '{object_key}' does not exist in bucket.{Colors.RESET}")
        else:
            print(f"  {Colors.RED}[ERROR] Cannot access object: {e}{Colors.RESET}")
        return


    # Expiration time
    print(f"\n  {Colors.CYAN}Presigned URL Expiration:{Colors.RESET}")
    print("    1.  1 hour")
    print("    2.  6 hours")
    print("    3. 12 hours")
    print("    4. 24 hours (1 day)")
    print("    5. 72 hours (3 days)")
    print("    6.  7 days (maximum)")
    print("    7. Custom (enter seconds)")
    
    expiry_choice = input(f"\n  Select expiration (1-7) [4]: ").strip() or "4"
    
    expiry_map = {
        '1': 3600,
        '2': 21600,
        '3': 43200,
        '4': 86400,
        '5': 259200,
        '6': 604800,
    }
    
    if expiry_choice == '7':
        custom_seconds = input("  Enter expiration in seconds (max 604800): ").strip()
        try:
            expiry_seconds = int(custom_seconds)
            if expiry_seconds > 604800:
                print(f"  {Colors.YELLOW}[WARNING] Maximum is 604800 seconds (7 days). Using max.{Colors.RESET}")
                expiry_seconds = 604800
            elif expiry_seconds < 60:
                print(f"  {Colors.YELLOW}[WARNING] Minimum is 60 seconds. Using 60.{Colors.RESET}")
                expiry_seconds = 60
        except ValueError:
            print(f"  {Colors.YELLOW}[WARNING] Invalid input. Using 24 hours.{Colors.RESET}")
            expiry_seconds = 86400
    else:
        expiry_seconds = expiry_map.get(expiry_choice, 86400)
    
    # Calculate expiry time for display
    expiry_time = datetime.datetime.now() + datetime.timedelta(seconds=expiry_seconds)
    expiry_hours = expiry_seconds / 3600


    # HTTP method for presigned URL
    print(f"\n  {Colors.CYAN}Access Type:{Colors.RESET}")
    print("    1. Download (GET) - Allow downloading the object")
    print("    2. Upload (PUT) - Allow uploading/replacing the object")
    
    method_choice = input(f"  Select access type (1-2) [1]: ").strip() or "1"
    
    if method_choice == '2':
        client_method = 'put_object'
        access_type = "UPLOAD (PUT)"
    else:
        client_method = 'get_object'
        access_type = "DOWNLOAD (GET)"
    
    # Generate presigned URL
    try:
        presigned_url = s3_client.generate_presigned_url(
            ClientMethod=client_method,
            Params={
                'Bucket': bucket_name,
                'Key': object_key,
            },
            ExpiresIn=expiry_seconds,
        )
        
        print(f"\n  {'=' * 66}")
        print(f"  {Colors.GREEN}{Colors.BOLD}PRESIGNED URL GENERATED SUCCESSFULLY!{Colors.RESET}")
        print(f"  {'=' * 66}")
        print(f"\n  {Colors.CYAN}Object:{Colors.RESET}      s3://{bucket_name}/{object_key}")
        print(f"  {Colors.CYAN}Access:{Colors.RESET}      {access_type}")
        print(f"  {Colors.CYAN}Expires In:{Colors.RESET}  {expiry_hours:.1f} hours")
        print(f"  {Colors.CYAN}Expires At:{Colors.RESET}  {expiry_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  {Colors.CYAN}Region:{Colors.RESET}      {region}")
        print(f"\n  {Colors.BOLD}Presigned URL:{Colors.RESET}")
        print(f"  {Colors.GREEN}{presigned_url}{Colors.RESET}")
        print(f"\n  {Colors.YELLOW}[NOTE] Share this URL with external users. They can access the")
        print(f"  object without AWS credentials until the URL expires.{Colors.RESET}")
        print(f"  {'=' * 66}")
        
        # Ask if user wants to generate more
        another = input(f"\n  Generate another presigned URL? (yes/no) [no]: ").strip().lower()
        if another in ('yes', 'y'):
            create_presigned_url(s3_client, bucket_name, region)
    
    except ClientError as e:
        print(f"  {Colors.RED}[ERROR] Failed to generate presigned URL: {e}{Colors.RESET}")
    except Exception as e:
        print(f"  {Colors.RED}[ERROR] Unexpected error: {e}{Colors.RESET}")



def upload_file(s3_client, bucket_name):
    """
    Upload a local file to S3 bucket.
    
    Args:
        s3_client: Boto3 S3 client
        bucket_name: Name of the S3 bucket
    """
    print(f"\n  {Colors.BOLD}Upload File to S3{Colors.RESET}")
    
    local_file = input("  Enter local file path: ").strip()
    if not local_file:
        print(f"  {Colors.RED}[ERROR] File path is required.{Colors.RESET}")
        return
    
    if not os.path.isfile(local_file):
        print(f"  {Colors.RED}[ERROR] File not found: {local_file}{Colors.RESET}")
        return
    
    file_size = os.path.getsize(local_file)
    filename = os.path.basename(local_file)
    
    s3_key = input(f"  Enter S3 key/path [{filename}]: ").strip() or filename
    
    print(f"\n  Uploading: {local_file}")
    print(f"  Destination: s3://{bucket_name}/{s3_key}")
    print(f"  Size: {format_size(file_size)}")
    
    confirm = input(f"  Proceed? (yes/no) [yes]: ").strip().lower() or "yes"
    if confirm not in ('yes', 'y'):
        print("  Upload cancelled.")
        return
    
    try:
        start_time = time.time()
        s3_client.upload_file(local_file, bucket_name, s3_key)
        elapsed = time.time() - start_time
        
        print(f"\n  {Colors.GREEN}[SUCCESS] File uploaded successfully!{Colors.RESET}")
        print(f"  Location: s3://{bucket_name}/{s3_key}")
        print(f"  Time: {elapsed:.1f} seconds")
    except ClientError as e:
        print(f"  {Colors.RED}[ERROR] Upload failed: {e}{Colors.RESET}")
    except Exception as e:
        print(f"  {Colors.RED}[ERROR] {e}{Colors.RESET}")



def main():
    """Main function with interactive menu."""
    if not BOTO3_AVAILABLE:
        print("\n  [ERROR] The 'boto3' package is required.")
        print("  Install it with: pip install boto3")
        sys.exit(1)
    
    print_banner()
    
    # Get AWS configuration
    config = get_aws_configuration()
    if config is None:
        print(f"\n  {Colors.RED}Configuration failed. Exiting.{Colors.RESET}")
        sys.exit(1)
    
    s3_client = config['s3_client']
    bucket_name = config['bucket_name']
    region = config['region']
    
    while True:
        print(f"\n  {Colors.BOLD}S3 Bucket Operations - s3://{bucket_name}{Colors.RESET}")
        print("  " + "-" * 50)
        print("  1. List bucket contents (top-level)")
        print("  2. Browse folder contents")
        print("  3. Download full bucket")
        print("  4. Download specific folder (including files & objects)")
        print("  5. Create presigned URL (share with external users)")
        print("  6. Upload file to bucket")
        print("  7. Change bucket / Reconfigure")
        print("  8. Exit")
        print("  " + "-" * 50)
        
        choice = input(f"\n  Enter your choice (1-8): ").strip()
        
        if choice == '1':
            list_bucket_contents(s3_client, bucket_name, prefix="", show_tree=True)
        
        elif choice == '2':
            prefix = input("  Enter folder/prefix to browse [root]: ").strip()
            if prefix and not prefix.endswith('/'):
                prefix += '/'
            list_bucket_contents(s3_client, bucket_name, prefix=prefix, show_tree=True)
        
        elif choice == '3':
            download_full_bucket(s3_client, bucket_name)
        
        elif choice == '4':
            download_folder(s3_client, bucket_name)
        
        elif choice == '5':
            create_presigned_url(s3_client, bucket_name, region)
        
        elif choice == '6':
            upload_file(s3_client, bucket_name)
        
        elif choice == '7':
            config = get_aws_configuration()
            if config:
                s3_client = config['s3_client']
                bucket_name = config['bucket_name']
                region = config['region']
            else:
                print(f"  {Colors.YELLOW}[WARNING] Reconfiguration failed. Keeping current settings.{Colors.RESET}")
        
        elif choice == '8':
            print(f"\n  {Colors.GREEN}Goodbye! Happy cloud managing.{Colors.RESET}\n")
            sys.exit(0)
        
        else:
            print(f"  {Colors.RED}[ERROR] Invalid choice. Please enter 1-8.{Colors.RESET}")


if __name__ == "__main__":
    main()
