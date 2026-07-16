#!/usr/bin/env python3
"""
EC2 Instance Start/Stop Manager
================================
A smart, programmatic CLI tool for starting and stopping AWS EC2 instances.

Features:
    - Start / Stop / Restart individual or multiple instances
    - List all instances with status, type, and metadata
    - Rich formatted output with color-coded status
    - Tag-based filtering (e.g., --tag Environment=dev)
    - Dry-run mode for safe testing
    - Wait mode to block until desired state is reached
    - Multi-region and profile support

Requirements:
    pip install boto3 rich

Usage:
    python ec2_start_stop.py list
    python ec2_start_stop.py start i-0123456789abcdef0
    python ec2_start_stop.py stop i-0123456789abcdef0
    python ec2_start_stop.py restart i-0123456789abcdef0
    python ec2_start_stop.py start --tag Environment=dev
    python ec2_start_stop.py stop --tag Environment=dev --dry-run
"""

import sys
import argparse
from typing import Optional

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
except ImportError:
    print("\n  [ERROR] boto3 is required. Install with: pip install boto3\n")
    sys.exit(1)

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


# ─────────────────────────────────────────────────────────────────────────────
# Constants & Configuration
# ─────────────────────────────────────────────────────────────────────────────

VERSION = "1.0.0"
APP_NAME = "EC2 Start/Stop Manager"

STATUS_COLORS = {
    "running": "green",
    "stopped": "red",
    "pending": "yellow",
    "stopping": "yellow",
    "shutting-down": "magenta",
    "terminated": "dim red",
}

STATUS_ICONS = {
    "running": "[green]\u25cf[/green]",
    "stopped": "[red]\u25cb[/red]",
    "pending": "[yellow]\u25d0[/yellow]",
    "stopping": "[yellow]\u25d1[/yellow]",
    "shutting-down": "[magenta]\u25cc[/magenta]",
    "terminated": "[dim red]\u2715[/dim red]",
}


# ─────────────────────────────────────────────────────────────────────────────
# Console Setup
# ─────────────────────────────────────────────────────────────────────────────

console = Console() if RICH_AVAILABLE else None


def print_banner():
    """Display application banner."""
    if RICH_AVAILABLE:
        banner = Text()
        banner.append(f"\n  {APP_NAME} v{VERSION}\n", style="bold cyan")
        banner.append("  Manage your EC2 instances with ease\n", style="dim")
        console.print(Panel(banner, box=box.DOUBLE_EDGE, border_style="cyan"))
    else:
        print(f"\n{'='*50}")
        print(f"  {APP_NAME} v{VERSION}")
        print(f"  Manage your EC2 instances with ease")
        print(f"{'='*50}\n")


def print_success(message: str):
    """Print a success message."""
    if RICH_AVAILABLE:
        console.print(f"  [bold green]\u2713[/bold green] {message}")
    else:
        print(f"  [OK] {message}")


def print_error(message: str):
    """Print an error message."""
    if RICH_AVAILABLE:
        console.print(f"  [bold red]\u2717[/bold red] {message}")
    else:
        print(f"  [ERROR] {message}")


def print_warning(message: str):
    """Print a warning message."""
    if RICH_AVAILABLE:
        console.print(f"  [bold yellow]\u26a0[/bold yellow] {message}")
    else:
        print(f"  [WARN] {message}")


def print_info(message: str):
    """Print an info message."""
    if RICH_AVAILABLE:
        console.print(f"  [bold blue]\u2139[/bold blue] {message}")
    else:
        print(f"  [INFO] {message}")


# ─────────────────────────────────────────────────────────────────────────────
# EC2 Manager Class
# ─────────────────────────────────────────────────────────────────────────────

class EC2Manager:
    """Manages AWS EC2 instance start/stop operations."""

    def __init__(self, region: Optional[str] = None, profile: Optional[str] = None):
        """
        Initialize EC2 Manager.

        Args:
            region: AWS region (e.g., 'us-east-1'). Uses default if None.
            profile: AWS CLI profile name. Uses default if None.
        """
        try:
            session_kwargs = {}
            if region:
                session_kwargs["region_name"] = region
            if profile:
                session_kwargs["profile_name"] = profile

            self.session = boto3.Session(**session_kwargs)
            self.ec2_client = self.session.client("ec2")
            self.ec2_resource = self.session.resource("ec2")
            self.region = self.session.region_name or "us-east-1"

            if RICH_AVAILABLE:
                print_info(f"Connected to AWS region: [bold]{self.region}[/bold]")
            else:
                print_info(f"Connected to AWS region: {self.region}")

        except NoCredentialsError:
            print_error("AWS credentials not found. Configure with 'aws configure' or set environment variables.")
            sys.exit(1)
        except Exception as e:
            print_error(f"Failed to initialize AWS session: {e}")
            sys.exit(1)

    def _get_instance_name(self, instance) -> str:
        """Extract the Name tag from an instance."""
        if instance.get("Tags"):
            for tag in instance["Tags"]:
                if tag["Key"] == "Name":
                    return tag["Value"]
        return "\u2014"

    def _get_instances_by_tag(self, tag_filter: str) -> list:
        """
        Get instance IDs filtered by tag.

        Args:
            tag_filter: Tag in format 'Key=Value'
        """
        try:
            key, value = tag_filter.split("=", 1)
        except ValueError:
            print_error(f"Invalid tag format '{tag_filter}'. Use Key=Value format.")
            return []

        response = self.ec2_client.describe_instances(
            Filters=[
                {"Name": f"tag:{key}", "Values": [value]},
                {"Name": "instance-state-name", "Values": ["running", "stopped", "pending", "stopping"]},
            ]
        )

        instance_ids = []
        for reservation in response["Reservations"]:
            for instance in reservation["Instances"]:
                instance_ids.append(instance["InstanceId"])

        if instance_ids:
            print_info(f"Found {len(instance_ids)} instance(s) matching tag '{tag_filter}'")
        else:
            print_warning(f"No instances found matching tag '{tag_filter}'")

        return instance_ids

    def list_instances(self, tag_filter: Optional[str] = None):
        """
        List all EC2 instances with detailed information.

        Args:
            tag_filter: Optional tag filter in 'Key=Value' format
        """
        filters = []
        if tag_filter:
            try:
                key, value = tag_filter.split("=", 1)
                filters.append({"Name": f"tag:{key}", "Values": [value]})
            except ValueError:
                print_error(f"Invalid tag format '{tag_filter}'. Use Key=Value format.")
                return

        try:
            response = self.ec2_client.describe_instances(Filters=filters if filters else [])
        except ClientError as e:
            print_error(f"Failed to list instances: {e}")
            return

        instances = []
        for reservation in response["Reservations"]:
            for instance in reservation["Instances"]:
                instances.append(instance)

        if not instances:
            print_warning("No instances found.")
            return

        if RICH_AVAILABLE:
            table = Table(
                title=f"\n  EC2 Instances \u2022 {self.region}",
                box=box.ROUNDED,
                header_style="bold cyan",
                border_style="dim",
                show_lines=True,
                padding=(0, 1),
            )

            table.add_column("Status", justify="center", width=12)
            table.add_column("Instance ID", style="bold", width=22)
            table.add_column("Name", width=25)
            table.add_column("Type", justify="center", width=13)
            table.add_column("Private IP", width=16)
            table.add_column("Public IP", width=16)
            table.add_column("Launch Time", width=20)

            for inst in sorted(instances, key=lambda x: x["State"]["Name"]):
                state = inst["State"]["Name"]
                status_icon = STATUS_ICONS.get(state, "?")
                color = STATUS_COLORS.get(state, "white")

                launch_time = inst.get("LaunchTime", "")
                if launch_time:
                    launch_time = launch_time.strftime("%Y-%m-%d %H:%M")

                table.add_row(
                    f"{status_icon} [{color}]{state}[/{color}]",
                    inst["InstanceId"],
                    self._get_instance_name(inst),
                    inst.get("InstanceType", "\u2014"),
                    inst.get("PrivateIpAddress", "\u2014"),
                    inst.get("PublicIpAddress", "\u2014"),
                    str(launch_time),
                )

            console.print(table)
            console.print(f"\n  [dim]Total: {len(instances)} instance(s)[/dim]\n")
        else:
            print(f"\n  EC2 Instances \u2022 {self.region}")
            print(f"  {'\u2500'*90}")
            print(f"  {'Status':<12} {'Instance ID':<22} {'Name':<20} {'Type':<12} {'Private IP':<16} {'Public IP':<16}")
            print(f"  {'\u2500'*90}")
            for inst in sorted(instances, key=lambda x: x["State"]["Name"]):
                state = inst["State"]["Name"]
                print(
                    f"  {state:<12} {inst['InstanceId']:<22} "
                    f"{self._get_instance_name(inst):<20} "
                    f"{inst.get('InstanceType', '\u2014'):<12} "
                    f"{inst.get('PrivateIpAddress', '\u2014'):<16} "
                    f"{inst.get('PublicIpAddress', '\u2014'):<16}"
                )
            print(f"\n  Total: {len(instances)} instance(s)\n")

    def start_instances(self, instance_ids: list, dry_run: bool = False, wait: bool = False):
        """
        Start one or more EC2 instances.

        Args:
            instance_ids: List of instance IDs to start
            dry_run: If True, only validate without executing
            wait: If True, wait until instances are running
        """
        if not instance_ids:
            print_warning("No instance IDs provided.")
            return

        print_info(f"Starting {len(instance_ids)} instance(s)...")

        if dry_run:
            print_warning("[DRY RUN] No changes will be made.")
            for iid in instance_ids:
                print(f"    \u2192 Would start: {iid}")
            return

        try:
            response = self.ec2_client.start_instances(InstanceIds=instance_ids)

            for change in response.get("StartingInstances", []):
                iid = change["InstanceId"]
                prev = change["PreviousState"]["Name"]
                curr = change["CurrentState"]["Name"]
                print_success(f"{iid}: {prev} \u2192 {curr}")

            if wait:
                self._wait_for_state(instance_ids, "instance_running", "running")

        except ClientError as e:
            print_error(f"Failed to start instances: {e.response['Error']['Message']}")

    def stop_instances(self, instance_ids: list, dry_run: bool = False, force: bool = False, wait: bool = False):
        """
        Stop one or more EC2 instances.

        Args:
            instance_ids: List of instance IDs to stop
            dry_run: If True, only validate without executing
            force: If True, force stop the instances
            wait: If True, wait until instances are stopped
        """
        if not instance_ids:
            print_warning("No instance IDs provided.")
            return

        print_info(f"Stopping {len(instance_ids)} instance(s)..." + (" [FORCE]" if force else ""))

        if dry_run:
            print_warning("[DRY RUN] No changes will be made.")
            for iid in instance_ids:
                print(f"    \u2192 Would stop: {iid}")
            return

        try:
            response = self.ec2_client.stop_instances(InstanceIds=instance_ids, Force=force)

            for change in response.get("StoppingInstances", []):
                iid = change["InstanceId"]
                prev = change["PreviousState"]["Name"]
                curr = change["CurrentState"]["Name"]
                print_success(f"{iid}: {prev} \u2192 {curr}")

            if wait:
                self._wait_for_state(instance_ids, "instance_stopped", "stopped")

        except ClientError as e:
            print_error(f"Failed to stop instances: {e.response['Error']['Message']}")

    def restart_instances(self, instance_ids: list, dry_run: bool = False):
        """
        Reboot one or more EC2 instances.

        Args:
            instance_ids: List of instance IDs to reboot
            dry_run: If True, only validate without executing
        """
        if not instance_ids:
            print_warning("No instance IDs provided.")
            return

        print_info(f"Rebooting {len(instance_ids)} instance(s)...")

        if dry_run:
            print_warning("[DRY RUN] No changes will be made.")
            for iid in instance_ids:
                print(f"    \u2192 Would reboot: {iid}")
            return

        try:
            self.ec2_client.reboot_instances(InstanceIds=instance_ids)
            for iid in instance_ids:
                print_success(f"{iid}: reboot initiated")
        except ClientError as e:
            print_error(f"Failed to reboot instances: {e.response['Error']['Message']}")

    def get_instance_status(self, instance_ids: list):
        """
        Get detailed status of specific instances.

        Args:
            instance_ids: List of instance IDs to check
        """
        try:
            response = self.ec2_client.describe_instance_status(
                InstanceIds=instance_ids,
                IncludeAllInstances=True,
            )

            if RICH_AVAILABLE:
                table = Table(
                    title="\n  Instance Health Status",
                    box=box.ROUNDED,
                    header_style="bold cyan",
                    border_style="dim",
                )
                table.add_column("Instance ID", style="bold", width=22)
                table.add_column("State", justify="center", width=12)
                table.add_column("System Status", justify="center", width=18)
                table.add_column("Instance Status", justify="center", width=18)

                for status in response["InstanceStatuses"]:
                    state = status["InstanceState"]["Name"]
                    color = STATUS_COLORS.get(state, "white")
                    sys_status = status.get("SystemStatus", {}).get("Status", "\u2014")
                    inst_status = status.get("InstanceStatus", {}).get("Status", "\u2014")

                    table.add_row(
                        status["InstanceId"],
                        f"[{color}]{state}[/{color}]",
                        sys_status,
                        inst_status,
                    )

                console.print(table)
            else:
                print("\n  Instance Health Status")
                print(f"  {'\u2500'*70}")
                for status in response["InstanceStatuses"]:
                    state = status["InstanceState"]["Name"]
                    sys_status = status.get("SystemStatus", {}).get("Status", "\u2014")
                    inst_status = status.get("InstanceStatus", {}).get("Status", "\u2014")
                    print(f"  {status['InstanceId']}  state={state}  system={sys_status}  instance={inst_status}")

        except ClientError as e:
            print_error(f"Failed to get status: {e.response['Error']['Message']}")

    def _wait_for_state(self, instance_ids: list, waiter_name: str, target_state: str):
        """Wait for instances to reach the target state with progress indication."""
        if RICH_AVAILABLE:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task(
                    f"  Waiting for instances to be {target_state}...", total=None
                )
                waiter = self.ec2_client.get_waiter(waiter_name)
                waiter.wait(InstanceIds=instance_ids)
                progress.update(task, description=f"  [green]Instances are now {target_state}![/green]")
        else:
            print(f"  Waiting for instances to be {target_state}...")
            waiter = self.ec2_client.get_waiter(waiter_name)
            waiter.wait(InstanceIds=instance_ids)
            print(f"  Instances are now {target_state}!")

        print_success(f"All {len(instance_ids)} instance(s) are now {target_state}.")


# ─────────────────────────────────────────────────────────────────────────────
# CLI Argument Parser
# ─────────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="ec2_start_stop",
        description=f"{APP_NAME} - Start, stop, and manage EC2 instances from the command line.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s list                                   List all instances
  %(prog)s list --tag Environment=production      List instances by tag
  %(prog)s start i-0abc123def456789a              Start an instance
  %(prog)s stop i-0abc123def456789a --wait        Stop and wait for confirmation
  %(prog)s restart i-0abc123 i-0def456            Restart multiple instances
  %(prog)s start --tag Project=web --dry-run      Dry-run start by tag
  %(prog)s status i-0abc123def456789a             Check instance health
        """,
    )

    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    parser.add_argument("--region", "-r", help="AWS region (overrides default)")
    parser.add_argument("--profile", "-p", help="AWS CLI profile name")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ── list ──
    list_parser = subparsers.add_parser("list", aliases=["ls"], help="List EC2 instances")
    list_parser.add_argument("--tag", "-t", help="Filter by tag (Key=Value)")

    # ── start ──
    start_parser = subparsers.add_parser("start", help="Start EC2 instance(s)")
    start_parser.add_argument("instance_ids", nargs="*", help="Instance ID(s) to start")
    start_parser.add_argument("--tag", "-t", help="Start instances matching tag (Key=Value)")
    start_parser.add_argument("--dry-run", action="store_true", help="Validate without executing")
    start_parser.add_argument("--wait", "-w", action="store_true", help="Wait until running")

    # ── stop ──
    stop_parser = subparsers.add_parser("stop", help="Stop EC2 instance(s)")
    stop_parser.add_argument("instance_ids", nargs="*", help="Instance ID(s) to stop")
    stop_parser.add_argument("--tag", "-t", help="Stop instances matching tag (Key=Value)")
    stop_parser.add_argument("--dry-run", action="store_true", help="Validate without executing")
    stop_parser.add_argument("--force", "-f", action="store_true", help="Force stop")
    stop_parser.add_argument("--wait", "-w", action="store_true", help="Wait until stopped")

    # ── restart ──
    restart_parser = subparsers.add_parser("restart", aliases=["reboot"], help="Restart EC2 instance(s)")
    restart_parser.add_argument("instance_ids", nargs="*", help="Instance ID(s) to restart")
    restart_parser.add_argument("--tag", "-t", help="Restart instances matching tag (Key=Value)")
    restart_parser.add_argument("--dry-run", action="store_true", help="Validate without executing")

    # ── status ──
    status_parser = subparsers.add_parser("status", help="Get detailed instance health status")
    status_parser.add_argument("instance_ids", nargs="+", help="Instance ID(s) to check")

    return parser


# ─────────────────────────────────────────────────────────────────────────────
# Main Entry Point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    """Main entry point for the EC2 Start/Stop Manager CLI."""
    parser = build_parser()
    args = parser.parse_args()

    print_banner()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # Initialize manager
    manager = EC2Manager(region=args.region, profile=args.profile)

    # ── Execute command ──
    if args.command in ("list", "ls"):
        manager.list_instances(tag_filter=args.tag)

    elif args.command == "start":
        instance_ids = args.instance_ids or []
        if args.tag:
            instance_ids.extend(manager._get_instances_by_tag(args.tag))
        if not instance_ids:
            print_error("Provide instance ID(s) or use --tag to filter.")
            sys.exit(1)
        manager.start_instances(instance_ids, dry_run=args.dry_run, wait=args.wait)

    elif args.command == "stop":
        instance_ids = args.instance_ids or []
        if args.tag:
            instance_ids.extend(manager._get_instances_by_tag(args.tag))
        if not instance_ids:
            print_error("Provide instance ID(s) or use --tag to filter.")
            sys.exit(1)
        manager.stop_instances(instance_ids, dry_run=args.dry_run, force=args.force, wait=args.wait)

    elif args.command in ("restart", "reboot"):
        instance_ids = args.instance_ids or []
        if args.tag:
            instance_ids.extend(manager._get_instances_by_tag(args.tag))
        if not instance_ids:
            print_error("Provide instance ID(s) or use --tag to filter.")
            sys.exit(1)
        manager.restart_instances(instance_ids, dry_run=args.dry_run)

    elif args.command == "status":
        manager.get_instance_status(args.instance_ids)

    print()  # Final newline for clean output


if __name__ == "__main__":
    main()
