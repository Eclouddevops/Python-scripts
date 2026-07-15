#!/usr/bin/env python3
"""
SSL Certificate Checker Script
===============================
Features:
1. Check SSL certificate validity for any domain
2. Display certificate details (issuer, subject, expiry dates)
3. Show days remaining until expiration
4. Alert if certificate is expired or expiring soon
5. Create a self-signed SSL certificate for testing/development

Requirements:
    pip install cryptography

Usage:
    python ssl_certificate_checker.py
"""

import ssl
import socket
import datetime
import sys
import os

try:
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False


def get_ssl_certificate_info(hostname, port=443, timeout=10):
    """
    Connect to a host and retrieve SSL certificate information.
    
    Args:
        hostname: Domain name to check
        port: Port number (default: 443)
        timeout: Connection timeout in seconds
    
    Returns:
        dict with certificate details or None on failure
    """
    context = ssl.create_default_context()
    
    try:
        with socket.create_connection((hostname, port), timeout=timeout) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
                return cert
    except ssl.SSLCertVerificationError as e:
        print(f"  [WARNING] SSL Verification Error: {e}")
        # Try again without verification to still get cert info
        context_no_verify = ssl.create_default_context()
        context_no_verify.check_hostname = False
        context_no_verify.verify_mode = ssl.CERT_NONE
        try:
            with socket.create_connection((hostname, port), timeout=timeout) as sock:
                with context_no_verify.wrap_socket(sock, server_hostname=hostname) as ssock:
                    # Get binary cert for parsing
                    cert_bin = ssock.getpeercert(binary_form=True)
                    cert = ssock.getpeercert()
                    if not cert:
                        # Parse binary cert manually
                        return {"error": "Certificate verification failed", "details": str(e)}
                    return cert
        except Exception as inner_e:
            return {"error": str(inner_e)}
    except socket.timeout:
        return {"error": f"Connection timed out after {timeout} seconds"}
    except socket.gaierror:
        return {"error": f"Could not resolve hostname: {hostname}"}
    except ConnectionRefusedError:
        return {"error": f"Connection refused on {hostname}:{port}"}
    except Exception as e:
        return {"error": str(e)}


def parse_cert_date(date_str):
    """Parse certificate date string to datetime object."""
    # SSL cert dates are in format: 'Mon DD HH:MM:SS YYYY GMT'
    return datetime.datetime.strptime(date_str, '%b %d %H:%M:%S %Y %Z')


def display_certificate_info(hostname, cert_info):
    """Display formatted certificate information."""
    print("\n" + "=" * 70)
    print(f"  SSL CERTIFICATE REPORT FOR: {hostname}")
    print("=" * 70)
    
    if "error" in cert_info:
        print(f"\n  [ERROR] {cert_info['error']}")
        return
    
    # Subject
    subject = dict(x[0] for x in cert_info.get('subject', []))
    print(f"\n  Subject:")
    print(f"    Common Name (CN) : {subject.get('commonName', 'N/A')}")
    print(f"    Organization (O) : {subject.get('organizationName', 'N/A')}")
    print(f"    Country (C)      : {subject.get('countryName', 'N/A')}")
    
    # Issuer
    issuer = dict(x[0] for x in cert_info.get('issuer', []))
    print(f"\n  Issuer:")
    print(f"    Common Name (CN) : {issuer.get('commonName', 'N/A')}")
    print(f"    Organization (O) : {issuer.get('organizationName', 'N/A')}")
    print(f"    Country (C)      : {issuer.get('countryName', 'N/A')}")
    
    # Validity dates
    not_before = cert_info.get('notBefore', 'N/A')
    not_after = cert_info.get('notAfter', 'N/A')
    print(f"\n  Validity Period:")
    print(f"    Valid From  : {not_before}")
    print(f"    Valid Until : {not_after}")
    
    # Calculate days remaining
    if not_after != 'N/A':
        expiry_date = parse_cert_date(not_after)
        now = datetime.datetime.utcnow()
        days_remaining = (expiry_date - now).days
        
        print(f"\n  Expiration Status:")
        if days_remaining < 0:
            print(f"    [EXPIRED] Certificate expired {abs(days_remaining)} days ago!")
        elif days_remaining <= 7:
            print(f"    [CRITICAL] Certificate expires in {days_remaining} days!")
        elif days_remaining <= 30:
            print(f"    [WARNING] Certificate expires in {days_remaining} days")
        elif days_remaining <= 90:
            print(f"    [NOTICE] Certificate expires in {days_remaining} days")
        else:
            print(f"    [OK] Certificate is valid for {days_remaining} more days")
    
    # Serial Number
    serial = cert_info.get('serialNumber', 'N/A')
    print(f"\n  Serial Number: {serial}")
    
    # Subject Alternative Names (SANs)
    sans = cert_info.get('subjectAltName', [])
    if sans:
        print(f"\n  Subject Alternative Names (SANs):")
        for san_type, san_value in sans[:10]:  # Limit to first 10
            print(f"    - {san_type}: {san_value}")
        if len(sans) > 10:
            print(f"    ... and {len(sans) - 10} more")
    
    # Version
    version = cert_info.get('version', 'N/A')
    print(f"\n  Certificate Version: {version}")
    
    print("\n" + "=" * 70)


def check_multiple_domains(domains):
    """Check SSL certificates for multiple domains."""
    results = []
    
    for domain in domains:
        domain = domain.strip()
        if not domain:
            continue
        
        print(f"\n  Checking: {domain} ...")
        cert_info = get_ssl_certificate_info(domain)
        
        if cert_info:
            display_certificate_info(domain, cert_info)
            results.append({"domain": domain, "cert": cert_info})
        else:
            print(f"  [ERROR] Could not retrieve certificate for {domain}")
            results.append({"domain": domain, "cert": None})
    
    return results


def create_self_signed_certificate():
    """Create a self-signed SSL certificate for testing/development."""
    if not CRYPTOGRAPHY_AVAILABLE:
        print("\n  [ERROR] The 'cryptography' package is required for certificate creation.")
        print("  Install it with: pip install cryptography")
        return
    
    print("\n" + "=" * 70)
    print("  CREATE SELF-SIGNED SSL CERTIFICATE")
    print("=" * 70)
    
    # Get user inputs
    common_name = input("\n  Enter Common Name (domain/hostname) [localhost]: ").strip() or "localhost"
    organization = input("  Enter Organization Name [My Organization]: ").strip() or "My Organization"
    country = input("  Enter Country Code (2 letters) [US]: ").strip() or "US"
    state = input("  Enter State/Province [California]: ").strip() or "California"
    city = input("  Enter City [San Francisco]: ").strip() or "San Francisco"
    
    validity_days_str = input("  Enter validity period in days [365]: ").strip() or "365"
    try:
        validity_days = int(validity_days_str)
    except ValueError:
        print("  [ERROR] Invalid number of days. Using 365.")
        validity_days = 365
    
    output_dir = input("  Enter output directory [./certs]: ").strip() or "./certs"
    key_file = input("  Enter key filename [server.key]: ").strip() or "server.key"
    cert_file = input("  Enter certificate filename [server.crt]: ").strip() or "server.crt"
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"\n  Generating RSA 2048-bit private key...")
    
    # Generate private key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    
    # Build certificate subject
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, country[:2]),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, state),
        x509.NameAttribute(NameOID.LOCALITY_NAME, city),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization),
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
    ])
    
    # Build certificate
    now = datetime.datetime.utcnow()
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=validity_days))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName(common_name),
                x509.DNSName(f"*.{common_name}"),
                x509.DNSName("localhost"),
                x509.IPAddress(ipaddress_from_string("127.0.0.1")),
            ]),
            critical=False,
        )
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True,
        )
        .sign(private_key, hashes.SHA256())
    )
    
    # Write private key
    key_path = os.path.join(output_dir, key_file)
    with open(key_path, "wb") as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ))
    
    # Write certificate
    cert_path = os.path.join(output_dir, cert_file)
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    
    print(f"  Private Key saved to : {key_path}")
    print(f"  Certificate saved to : {cert_path}")
    print(f"\n  Certificate Details:")
    print(f"    Subject     : CN={common_name}, O={organization}, C={country}")
    print(f"    Valid From  : {now.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"    Valid Until : {(now + datetime.timedelta(days=validity_days)).strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"    Key Size    : 2048 bits")
    print(f"    Algorithm   : SHA-256 with RSA")
    print(f"\n  [SUCCESS] Self-signed certificate created successfully!")
    print("=" * 70)


def ipaddress_from_string(ip_str):
    """Convert IP string to ipaddress object for SAN extension."""
    import ipaddress
    return ipaddress.ip_address(ip_str)


def display_summary(results):
    """Display a summary table of all checked domains."""
    if not results:
        return
    
    print("\n\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    print(f"  {'Domain':<30} {'Status':<12} {'Days Left':<12} {'Expiry Date'}")
    print(f"  {'-'*30} {'-'*12} {'-'*12} {'-'*20}")
    
    for result in results:
        domain = result['domain']
        cert = result['cert']
        
        if cert is None or 'error' in cert:
            print(f"  {domain:<30} {'ERROR':<12} {'N/A':<12} N/A")
            continue
        
        not_after = cert.get('notAfter', '')
        if not_after:
            expiry_date = parse_cert_date(not_after)
            days_remaining = (expiry_date - datetime.datetime.utcnow()).days
            
            if days_remaining < 0:
                status = "EXPIRED"
            elif days_remaining <= 30:
                status = "WARNING"
            else:
                status = "VALID"
            
            print(f"  {domain:<30} {status:<12} {days_remaining:<12} {not_after}")
        else:
            print(f"  {domain:<30} {'UNKNOWN':<12} {'N/A':<12} N/A")
    
    print("=" * 70)


def main():
    """Main function with interactive menu."""
    print("\n" + "#" * 70)
    print("#" + " " * 68 + "#")
    print("#     SSL CERTIFICATE CHECKER & CREATOR TOOL                         #")
    print("#" + " " * 68 + "#")
    print("#" * 70)
    
    while True:
        print("\n  Choose an option:")
        print("  " + "-" * 40)
        print("  1. Check SSL certificate for a single domain")
        print("  2. Check SSL certificates for multiple domains")
        print("  3. Check SSL certificate with custom port")
        print("  4. Create a self-signed SSL certificate")
        print("  5. Exit")
        print("  " + "-" * 40)
        
        choice = input("\n  Enter your choice (1-5): ").strip()
        
        if choice == '1':
            domain = input("\n  Enter domain name (e.g., google.com): ").strip()
            if not domain:
                print("  [ERROR] Domain name cannot be empty.")
                continue
            # Remove protocol if provided
            domain = domain.replace("https://", "").replace("http://", "").split("/")[0]
            cert_info = get_ssl_certificate_info(domain)
            if cert_info:
                display_certificate_info(domain, cert_info)
            else:
                print(f"  [ERROR] Could not retrieve certificate for {domain}")
        
        elif choice == '2':
            print("\n  Enter domain names (comma-separated or one per line).")
            print("  Type 'done' on a new line when finished:")
            domains = []
            while True:
                line = input("  > ").strip()
                if line.lower() == 'done':
                    break
                # Handle comma-separated
                for d in line.split(","):
                    d = d.strip().replace("https://", "").replace("http://", "").split("/")[0]
                    if d:
                        domains.append(d)
            
            if domains:
                results = check_multiple_domains(domains)
                display_summary(results)
            else:
                print("  [ERROR] No domains provided.")
        
        elif choice == '3':
            domain = input("\n  Enter domain name: ").strip()
            port_str = input("  Enter port number [443]: ").strip() or "443"
            try:
                port = int(port_str)
            except ValueError:
                print("  [ERROR] Invalid port number.")
                continue
            
            domain = domain.replace("https://", "").replace("http://", "").split("/")[0]
            cert_info = get_ssl_certificate_info(domain, port=port)
            if cert_info:
                display_certificate_info(domain, cert_info)
            else:
                print(f"  [ERROR] Could not retrieve certificate for {domain}:{port}")
        
        elif choice == '4':
            create_self_signed_certificate()
        
        elif choice == '5':
            print("\n  Goodbye! Stay secure.\n")
            sys.exit(0)
        
        else:
            print("  [ERROR] Invalid choice. Please enter 1-5.")


if __name__ == "__main__":
    main()
