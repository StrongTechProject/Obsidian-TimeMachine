"""
CLI entry point for Obsidian Timemachine.

Provides the command-line interface for all sync operations.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from ..runner import run_sync
from ..config import load_config, ConfigError, DEFAULT_CONFIG_FILE


@click.group()
@click.version_option(package_name="obsidian-timemachine")
def cli() -> None:
    """Obsidian Timemachine - Automated backup for your Obsidian Vault.
    
    Syncs your Obsidian vault to a Git repository and pushes to GitHub.
    """
    pass


@cli.command()
@click.option(
    "-c", "--config",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to configuration file.",
)
def sync(config: Path | None) -> None:
    """Run the sync and push operation.
    
    This performs a complete backup cycle:
    1. Pull remote changes
    2. Wait for iCloud sync (if applicable)
    3. Sync files with rsync
    4. Commit and push to Git
    """
    result = run_sync(config_path=config)
    
    if not result.success:
        if result.errors:
            for error in result.errors:
                click.echo(f"Error: {error}", err=True)
        sys.exit(1)
    
    if result.warnings:
        for warning in result.warnings:
            click.echo(f"Warning: {warning}", err=True)
    
    click.echo("✅ Sync completed successfully!")


@cli.command()
@click.option(
    "-c", "--config",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to configuration file.",
)
def status(config: Path | None) -> None:
    """Check the current configuration and sync status."""
    config_path = config or DEFAULT_CONFIG_FILE
    
    try:
        cfg = load_config(config_path)
    except ConfigError as e:
        click.echo(f"❌ Configuration error: {e}", err=True)
        click.echo(f"\nNo configuration found at {config_path}")
        click.echo("Run 'ot setup' to create a configuration.")
        sys.exit(1)
    
    click.echo("📋 Current Configuration:")
    click.echo(f"   Source:      {cfg.source_dir}")
    click.echo(f"   Destination: {cfg.dest_dir}")
    click.echo(f"   Log Dir:     {cfg.log_dir}")
    click.echo(f"   SSH Key:     {cfg.ssh_key_path or 'Not configured'}")
    click.echo(f"   Log Retention: {cfg.log_retention_days} days")
    
    # Check paths
    click.echo("\n🔍 Path Status:")
    
    if cfg.source_dir.exists():
        click.echo(f"   ✅ Source exists")
    else:
        click.echo(f"   ❌ Source not found: {cfg.source_dir}")
    
    if cfg.dest_dir.exists():
        from ..git_ops import is_git_repo, get_remote_url, get_current_branch
        
        if is_git_repo(cfg.dest_dir):
            click.echo(f"   ✅ Destination is a Git repository")
            
            branch = get_current_branch(cfg.dest_dir)
            if branch:
                click.echo(f"      Branch: {branch}")
            
            remote = get_remote_url(cfg.dest_dir)
            if remote:
                click.echo(f"      Remote: {remote}")
            else:
                click.echo(f"      ⚠️ No remote configured")
        else:
            click.echo(f"   ⚠️ Destination exists but is not a Git repo")
    else:
        click.echo(f"   ❌ Destination not found: {cfg.dest_dir}")
    
    # Check schedule
    from ..scheduler import get_current_schedule, describe_schedule
    
    schedule = get_current_schedule()
    click.echo("\n⏰ Schedule Status:")
    if schedule:
        click.echo(f"   ✅ Auto-sync enabled: {describe_schedule(schedule)}")
    else:
        click.echo("   ⚠️ No auto-sync scheduled (manual only)")


@cli.command()
def setup() -> None:
    """Run the interactive configuration wizard.
    
    This will guide you through setting up the sync configuration.
    """
    from .wizard import run_wizard
    
    config = run_wizard()
    if config is None:
        click.echo("Setup cancelled.", err=True)
        sys.exit(1)


@cli.group()
def schedule() -> None:
    """Manage automatic sync schedule."""
    pass


@schedule.command("set")
@click.argument(
    "frequency",
    type=click.Choice(["15min", "30min", "hourly", "daily"]),
)
def schedule_set(frequency: str) -> None:
    """Set the auto-sync frequency.
    
    FREQUENCY: 15min, 30min, hourly, or daily
    """
    from ..scheduler import add_sync_schedule, describe_schedule, SCHEDULE_PRESETS
    
    if add_sync_schedule(frequency):
        cron_expr = SCHEDULE_PRESETS.get(frequency, frequency)
        click.echo(f"✅ Auto-sync enabled: {describe_schedule(cron_expr)}")
    else:
        click.echo("❌ Failed to set schedule", err=True)
        sys.exit(1)


@schedule.command("remove")
def schedule_remove() -> None:
    """Remove the auto-sync schedule."""
    from ..scheduler import remove_sync_schedule
    
    if remove_sync_schedule():
        click.echo("✅ Auto-sync disabled")
    else:
        click.echo("❌ Failed to remove schedule", err=True)
        sys.exit(1)


@schedule.command("show")
def schedule_show() -> None:
    """Show the current sync schedule."""
    from ..scheduler import get_current_schedule, describe_schedule
    
    schedule = get_current_schedule()
    if schedule:
        click.echo(f"Current schedule: {describe_schedule(schedule)}")
        click.echo(f"Cron expression: {schedule}")
    else:
        click.echo("No auto-sync schedule configured.")
        click.echo("Use 'ot schedule set <frequency>' to enable.")


if __name__ == "__main__":
    cli()
