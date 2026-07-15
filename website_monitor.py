#!/usr/bin/env python3
"""
Website Up/Down Monitor Script
================================
Features:
1. Check if a website is UP or DOWN
2. Display HTTP status codes with descriptions
3. Show detailed error messages (DNS failure, timeout, SSL errors, etc.)
4. Monitor multiple websites at once
5. Continuous monitoring mode with configurable intervals
6. Response time measurement
7. Color-coded output for quick status identification

Requirements:
    pip install requests

Usage:
    python website_monitor.py
"""

import sys
import time
import datetime
import signal

try:
    import requests
    from requests.exceptions import (
        ConnectionError,
        Timeout,
        SSLError,
        TooManyRedirects,
        HTTPError,
        RequestException,
    )
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


# ANSI Color codes for terminal output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    RESET = '\033[0m'


# HTTP Status Code descriptions
HTTP_STATUS_CODES = {
    # 1xx Informational
    100: "Continue",
    101: "Switching Protocols",
    102: "Processing",
    103: "Early Hints",
    # 2xx Success
    200: "OK",
    201: "Created",
    202: "Accepted",
    203: "Non-Authoritative Information",
    204: "No Content",
    205: "Reset Content",
    206: "Partial Content",
    # 3xx Redirection
    300: "Multiple Choices",
    301: "Moved Permanently",
    302: "Found (Temporary Redirect)",
    303: "See Other",
    304: "Not Modified",
    307: "Temporary Redirect",
    308: "Permanent Redirect",
    # 4xx Client Errors
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    406: "Not Acceptable",
    407: "Proxy Authentication Required",
    408: "Request Timeout",
    409: "Conflict",
    410: "Gone",
    411: "Length Required",
    412: "Precondition Failed",
    413: "Payload Too Large",
    414: "URI Too Long",
    415: "Unsupported Media Type",
    416: "Range Not Satisfiable",
    417: "Expectation Failed",
    418: "I'm a Teapot",
    421: "Misdirected Request",
    422: "Unprocessable Entity",
    423: "Locked",
    429: "Too Many Requests",
    431: "Request Header Fields Too Large",
    451: "Unavailable For Legal Reasons",
    # 5xx Server Errors
    500: "Internal Server Error",
    501: "Not Implemented",
    502: "Bad Gateway",
    503: "Service Unavailable",
    504: "Gateway Timeout",
    505: "HTTP Version Not Supported",
    507: "Insufficient Storage",
    508: "Loop Detected",
    510: "Not Extended",
    511: "Network Authentication Required",
}


def get_status_description(status_code):
    """Get a human-readable description for an HTTP status code."""
    return HTTP_STATUS_CODES.get(status_code, "Unknown Status Code")


def normalize_url(url):
    """Ensure URL has a proper scheme."""
    url = url.strip()
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    return url


def check_website(url, timeout=15, verify_ssl=True):
    """
    Check if a website is up or down.
    
    Args:
        url: The URL to check
        timeout: Request timeout in seconds
        verify_ssl: Whether to verify SSL certificates
    
    Returns:
        dict with status information
    """
    url = normalize_url(url)
    result = {
        'url': url,
        'status': None,
        'status_code': None,
        'status_description': None,
        'response_time': None,
        'error': None,
        'error_type': None,
        'headers': {},
        'redirect_url': None,
        'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    
    try:
        start_time = time.time()
        response = requests.get(
            url,
            timeout=timeout,
            verify=verify_ssl,
            allow_redirects=True,
            headers={
                'User-Agent': 'Mozilla/5.0 (Website Monitor Script) Python/requests'
            }
        )
        end_time = time.time()
        
        result['response_time'] = round((end_time - start_time) * 1000, 2)  # ms
        result['status_code'] = response.status_code
        result['status_description'] = get_status_description(response.status_code)
        result['headers'] = dict(response.headers)
        
        # Check if there was a redirect
        if response.history:
            result['redirect_url'] = response.url
        
        # Determine UP/DOWN status
        if response.status_code < 400:
            result['status'] = 'UP'
        else:
            result['status'] = 'DOWN'
            result['error'] = f"HTTP {response.status_code}: {get_status_description(response.status_code)}"
            result['error_type'] = 'HTTP_ERROR'
    
    except ConnectionError as e:
        result['status'] = 'DOWN'
        result['error_type'] = 'CONNECTION_ERROR'
        error_str = str(e)
        
        if 'NameResolutionError' in error_str or 'getaddrinfo failed' in error_str:
            result['error'] = f"DNS Resolution Failed - Could not resolve hostname. The domain may not exist or DNS server is unreachable."
        elif 'ConnectionRefusedError' in error_str or 'Connection refused' in error_str:
            result['error'] = f"Connection Refused - The server actively refused the connection. The service may not be running on the specified port."
        elif 'Network is unreachable' in error_str:
            result['error'] = f"Network Unreachable - Cannot reach the network. Check your internet connection."
        elif 'No route to host' in error_str:
            result['error'] = f"No Route to Host - The server cannot be reached. It may be behind a firewall or the host is down."
        else:
            result['error'] = f"Connection Error - {error_str[:200]}"
    
    except Timeout as e:
        result['status'] = 'DOWN'
        result['error_type'] = 'TIMEOUT'
        result['error'] = f"Request Timed Out - The server did not respond within {timeout} seconds. The server may be overloaded or unreachable."
    
    except SSLError as e:
        result['status'] = 'DOWN'
        result['error_type'] = 'SSL_ERROR'
        error_str = str(e)
        
        if 'certificate has expired' in error_str.lower():
            result['error'] = f"SSL Certificate Expired - The server's SSL certificate has expired."
        elif 'certificate verify failed' in error_str.lower():
            result['error'] = f"SSL Certificate Verification Failed - The SSL certificate is invalid or not trusted."
        elif 'handshake' in error_str.lower():
            result['error'] = f"SSL Handshake Failed - Could not establish a secure connection."
        else:
            result['error'] = f"SSL Error - {error_str[:200]}"
    
    except TooManyRedirects as e:
        result['status'] = 'DOWN'
        result['error_type'] = 'REDIRECT_ERROR'
        result['error'] = f"Too Many Redirects - The URL resulted in too many redirects (redirect loop detected)."
    
    except RequestException as e:
        result['status'] = 'DOWN'
        result['error_type'] = 'REQUEST_ERROR'
        result['error'] = f"Request Failed - {str(e)[:200]}"
    
    except Exception as e:
        result['status'] = 'DOWN'
        result['error_type'] = 'UNKNOWN_ERROR'
        result['error'] = f"Unexpected Error - {type(e).__name__}: {str(e)[:200]}"
    
    return result


def display_result(result, verbose=False):
    """Display the check result in a formatted way."""
    url = result['url']
    status = result['status']
    timestamp = result['timestamp']
    
    # Status indicator
    if status == 'UP':
        status_icon = f"{Colors.GREEN}{Colors.BOLD}[UP]{Colors.RESET}"
        status_color = Colors.GREEN
    else:
        status_icon = f"{Colors.RED}{Colors.BOLD}[DOWN]{Colors.RESET}"
        status_color = Colors.RED
    
    print(f"\n  {'-' * 66}")
    print(f"  {Colors.CYAN}URL:{Colors.RESET} {url}")
    print(f"  {Colors.CYAN}Timestamp:{Colors.RESET} {timestamp}")
    print(f"  {Colors.CYAN}Status:{Colors.RESET} {status_icon}")
    
    # Status code
    if result['status_code']:
        code = result['status_code']
        desc = result['status_description']
        
        if code < 300:
            code_color = Colors.GREEN
        elif code < 400:
            code_color = Colors.YELLOW
        else:
            code_color = Colors.RED
        
        print(f"  {Colors.CYAN}HTTP Status:{Colors.RESET} {code_color}{code} - {desc}{Colors.RESET}")
    
    # Response time
    if result['response_time'] is not None:
        rt = result['response_time']
        if rt < 500:
            rt_color = Colors.GREEN
        elif rt < 2000:
            rt_color = Colors.YELLOW
        else:
            rt_color = Colors.RED
        print(f"  {Colors.CYAN}Response Time:{Colors.RESET} {rt_color}{rt} ms{Colors.RESET}")
    
    # Redirect info
    if result['redirect_url'] and result['redirect_url'] != url:
        print(f"  {Colors.CYAN}Redirected To:{Colors.RESET} {Colors.YELLOW}{result['redirect_url']}{Colors.RESET}")
    
    # Error details
    if result['error']:
        print(f"  {Colors.CYAN}Error Type:{Colors.RESET} {Colors.RED}{result['error_type']}{Colors.RESET}")
        print(f"  {Colors.CYAN}Error Detail:{Colors.RESET} {Colors.RED}{result['error']}{Colors.RESET}")
    
    # Verbose headers
    if verbose and result['headers']:
        print(f"\n  {Colors.CYAN}Response Headers:{Colors.RESET}")
        important_headers = ['Server', 'Content-Type', 'X-Powered-By', 'X-Frame-Options',
                          'Strict-Transport-Security', 'Content-Security-Policy']
        for header in important_headers:
            if header in result['headers']:
                print(f"    {header}: {result['headers'][header]}")
    
    print(f"  {'-' * 66}")


def display_summary_table(results):
    """Display a summary table of all results."""
    print(f"\n\n{'=' * 70}")
    print(f"  MONITORING SUMMARY")
    print(f"{'=' * 70}")
    print(f"  {'Website':<35} {'Status':<8} {'Code':<6} {'Response Time':<15}")
    print(f"  {'-'*35} {'-'*8} {'-'*6} {'-'*15}")
    
    up_count = 0
    down_count = 0
    
    for result in results:
        # Shorten URL for display
        display_url = result['url'].replace('https://', '').replace('http://', '')
        if len(display_url) > 33:
            display_url = display_url[:30] + "..."
        
        status = result['status']
        code = str(result['status_code']) if result['status_code'] else "N/A"
        rt = f"{result['response_time']} ms" if result['response_time'] else "N/A"
        
        if status == 'UP':
            up_count += 1
            status_display = f"{Colors.GREEN}UP{Colors.RESET}"
        else:
            down_count += 1
            status_display = f"{Colors.RED}DOWN{Colors.RESET}"
        
        print(f"  {display_url:<35} {status_display:<17} {code:<6} {rt:<15}")
    
    print(f"\n  Total: {len(results)} | "
          f"{Colors.GREEN}Up: {up_count}{Colors.RESET} | "
          f"{Colors.RED}Down: {down_count}{Colors.RESET}")
    print(f"{'=' * 70}")


def continuous_monitor(urls, interval=30, timeout=15):
    """
    Continuously monitor websites at specified intervals.
    
    Args:
        urls: List of URLs to monitor
        interval: Check interval in seconds
        timeout: Request timeout per URL
    """
    print(f"\n  {Colors.BOLD}Starting Continuous Monitoring{Colors.RESET}")
    print(f"  Monitoring {len(urls)} website(s) every {interval} seconds")
    print(f"  Press Ctrl+C to stop\n")
    
    # Handle graceful shutdown
    running = [True]
    
    def signal_handler(sig, frame):
        running[0] = False
        print(f"\n\n  {Colors.YELLOW}Stopping monitor...{Colors.RESET}")
    
    signal.signal(signal.SIGINT, signal_handler)
    
    check_count = 0
    
    while running[0]:
        check_count += 1
        print(f"\n  {'=' * 50}")
        print(f"  Check #{check_count} - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  {'=' * 50}")
        
        results = []
        for url in urls:
            result = check_website(url, timeout=timeout)
            results.append(result)
            display_result(result)
        
        display_summary_table(results)
        
        if running[0]:
            print(f"\n  Next check in {interval} seconds... (Ctrl+C to stop)")
            # Sleep in small increments to allow quick response to Ctrl+C
            for _ in range(interval * 2):
                if not running[0]:
                    break
                time.sleep(0.5)
    
    print(f"\n  {Colors.GREEN}Monitor stopped. Total checks performed: {check_count}{Colors.RESET}\n")


def main():
    """Main function with interactive menu."""
    if not REQUESTS_AVAILABLE:
        print("\n  [ERROR] The 'requests' package is required.")
        print("  Install it with: pip install requests")
        sys.exit(1)
    
    print("\n" + "#" * 70)
    print("#" + " " * 68 + "#")
    print("#     WEBSITE UP/DOWN MONITOR                                         #")
    print("#" + " " * 68 + "#")
    print("#" * 70)
    
    while True:
        print(f"\n  {Colors.BOLD}Choose an option:{Colors.RESET}")
        print("  " + "-" * 40)
        print("  1. Check a single website")
        print("  2. Check multiple websites")
        print("  3. Continuous monitoring mode")
        print("  4. Check website (verbose - show headers)")
        print("  5. Check website (skip SSL verification)")
        print("  6. Exit")
        print("  " + "-" * 40)
        
        choice = input(f"\n  Enter your choice (1-6): ").strip()
        
        if choice == '1':
            url = input("\n  Enter website URL (e.g., google.com): ").strip()
            if not url:
                print("  [ERROR] URL cannot be empty.")
                continue
            
            result = check_website(url)
            display_result(result)
        
        elif choice == '2':
            print("\n  Enter website URLs (comma-separated or one per line).")
            print("  Type 'done' on a new line when finished:")
            urls = []
            while True:
                line = input("  > ").strip()
                if line.lower() == 'done':
                    break
                for u in line.split(","):
                    u = u.strip()
                    if u:
                        urls.append(u)
            
            if urls:
                results = []
                for url in urls:
                    result = check_website(url)
                    results.append(result)
                    display_result(result)
                display_summary_table(results)
            else:
                print("  [ERROR] No URLs provided.")
        
        elif choice == '3':
            print("\n  Enter website URLs (comma-separated or one per line).")
            print("  Type 'done' on a new line when finished:")
            urls = []
            while True:
                line = input("  > ").strip()
                if line.lower() == 'done':
                    break
                for u in line.split(","):
                    u = u.strip()
                    if u:
                        urls.append(u)
            
            if not urls:
                print("  [ERROR] No URLs provided.")
                continue
            
            interval_str = input("  Enter check interval in seconds [30]: ").strip() or "30"
            try:
                interval = int(interval_str)
                if interval < 5:
                    print("  [WARNING] Minimum interval is 5 seconds.")
                    interval = 5
            except ValueError:
                print("  [ERROR] Invalid interval. Using 30 seconds.")
                interval = 30
            
            timeout_str = input("  Enter request timeout in seconds [15]: ").strip() or "15"
            try:
                timeout = int(timeout_str)
            except ValueError:
                timeout = 15
            
            continuous_monitor(urls, interval=interval, timeout=timeout)
        
        elif choice == '4':
            url = input("\n  Enter website URL: ").strip()
            if not url:
                print("  [ERROR] URL cannot be empty.")
                continue
            
            result = check_website(url)
            display_result(result, verbose=True)
        
        elif choice == '5':
            url = input("\n  Enter website URL: ").strip()
            if not url:
                print("  [ERROR] URL cannot be empty.")
                continue
            
            print(f"  {Colors.YELLOW}[WARNING] SSL verification disabled - connection may not be secure{Colors.RESET}")
            result = check_website(url, verify_ssl=False)
            display_result(result)
        
        elif choice == '6':
            print("\n  Goodbye! Keep monitoring.\n")
            sys.exit(0)
        
        else:
            print("  [ERROR] Invalid choice. Please enter 1-6.")


if __name__ == "__main__":
    main()
