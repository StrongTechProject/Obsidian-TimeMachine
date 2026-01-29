"""
Interactive menu for Obsidian Timemachine.

Provides a TUI-style menu for common operations.
"""

from __future__ import annotations

import click

from ..config import load_config, ConfigError, DEFAULT_CONFIG_FILE
from ..git_ops import get_remote_url, get_current_branch, is_git_repo
from ..scheduler import get_current_schedule, describe_schedule


def clear_screen() -> None:
    """Clear the terminal screen."""
    click.clear()


def print_header() -> None:
    """Print the menu header."""
    click.echo()
    click.echo(click.style("╔══════════════════════════════════════════════════╗", fg="blue"))
    click.echo(click.style("║         Obsidian Timemachine - Menu              ║", fg="blue"))
    click.echo(click.style("╚══════════════════════════════════════════════════╝", fg="blue"))
    click.echo()


def print_status_summary() -> None:
    """Print a brief status summary."""
    try:
        cfg = load_config(DEFAULT_CONFIG_FILE)
        
        click.echo(click.style("📊 Current Status:", bold=True))
        click.echo(f"   Source: {cfg.source_dir.name}")
        
        if is_git_repo(cfg.dest_dir):
            branch = get_current_branch(cfg.dest_dir) or "unknown"
            remote = get_remote_url(cfg.dest_dir)
            if remote:
                # Extract repo name from URL
                repo_name = remote.split("/")[-1].replace(".git", "")
                click.echo(f"   Repo: {repo_name} ({branch})")
            else:
                click.echo(f"   Repo: local only ({branch})")
        
        schedule = get_current_schedule()
        if schedule:
            click.echo(f"   Schedule: {describe_schedule(schedule)}")
        else:
            click.echo("   Schedule: Manual only")
        
    except ConfigError:
        click.echo(click.style("   ⚠️ Not configured - run Setup first", fg="yellow"))
    
    click.echo()


def print_menu_options() -> None:
    """Print the menu options."""
    click.echo(click.style("─" * 50, fg="blue"))
    click.echo()
    click.echo("  1. 🔄 Run Sync Now")
    click.echo("  2. 📋 View Full Status")
    click.echo("  3. ⏰ Manage Schedule")
    click.echo("  4. ⚙️  Run Setup Wizard")
    click.echo("  5. 📁 View Logs")
    click.echo("  6. 🆕 Check for Updates")
    click.echo("  7. ❌ Exit")
    click.echo()


def handle_sync() -> None:
    """Handle the sync operation."""
    click.echo()
    click.echo(click.style("Starting sync...", fg="cyan"))
    click.echo()
    
    from ..runner import run_sync
    
    result = run_sync()
    
    if result.success:
        click.echo()
        click.echo(click.style("✅ Sync completed successfully!", fg="green"))
    else:
        click.echo()
        click.echo(click.style("❌ Sync failed", fg="red"))
        if result.errors:
            for error in result.errors:
                click.echo(f"   {error}")
    
    click.echo()
    click.pause("Press any key to continue...")


def handle_status() -> None:
    """Handle viewing full status."""
    from .main import status
    
    click.echo()
    
    # Invoke status command
    ctx = click.Context(status)
    ctx.invoke(status)
    
    click.echo()
    click.pause("Press any key to continue...")


def handle_schedule() -> None:
    """Handle schedule management submenu."""
    while True:
        clear_screen()
        click.echo()
        click.echo(click.style("⏰ Schedule Management", fg="blue", bold=True))
        click.echo()
        
        schedule = get_current_schedule()
        if schedule:
            click.echo(f"   Current: {describe_schedule(schedule)}")
        else:
            click.echo("   Current: Not scheduled")
        
        click.echo()
        click.echo("  1. Set to every 15 minutes")
        click.echo("  2. Set to every 30 minutes")
        click.echo("  3. Set to hourly")
        click.echo("  4. Set to daily (2 AM)")
        click.echo("  5. Remove schedule")
        click.echo("  6. Back to main menu")
        click.echo()
        
        choice = click.prompt("Select option", type=int, default=6)
        
        from ..scheduler import add_sync_schedule, remove_sync_schedule
        
        if choice == 1:
            add_sync_schedule("15min")
            click.echo(click.style("✅ Schedule set to every 15 minutes", fg="green"))
            click.pause()
        elif choice == 2:
            add_sync_schedule("30min")
            click.echo(click.style("✅ Schedule set to every 30 minutes", fg="green"))
            click.pause()
        elif choice == 3:
            add_sync_schedule("hourly")
            click.echo(click.style("✅ Schedule set to hourly", fg="green"))
            click.pause()
        elif choice == 4:
            add_sync_schedule("daily")
            click.echo(click.style("✅ Schedule set to daily at 2 AM", fg="green"))
            click.pause()
        elif choice == 5:
            remove_sync_schedule()
            click.echo(click.style("✅ Schedule removed", fg="green"))
            click.pause()
        elif choice == 6:
            break


def handle_setup() -> None:
    """Handle running the setup wizard."""
    from .wizard import run_wizard
    
    clear_screen()
    run_wizard()
    click.pause("Press any key to continue...")


def handle_logs() -> None:
    """Handle viewing logs."""
    from ..config import DEFAULT_LOG_DIR
    
    click.echo()
    click.echo(click.style("📁 Log Files", fg="blue", bold=True))
    click.echo()
    
    log_dir = DEFAULT_LOG_DIR
    
    if not log_dir.exists():
        click.echo("   No logs found yet.")
    else:
        log_files = sorted(log_dir.glob("*.log"), reverse=True)[:5]
        
        if not log_files:
            click.echo("   No log files found.")
        else:
            click.echo("   Recent log files:")
            for i, log_file in enumerate(log_files, 1):
                click.echo(f"   {i}. {log_file.name}")
            
            click.echo()
            click.echo(f"   Log directory: {log_dir}")
            
            if log_files:
                click.echo()
                if click.confirm("View latest log?", default=False):
                    click.echo()
                    click.echo(click.style(f"--- {log_files[0].name} ---", fg="cyan"))
                    try:
                        # Show last 30 lines
                        lines = log_files[0].read_text().splitlines()[-30:]
                        for line in lines:
                            click.echo(line)
                    except OSError as e:
                        click.echo(f"Error reading log: {e}")
    
    click.echo()
    click.pause("Press any key to continue...")


def handle_update() -> None:
    """Handle checking for updates."""
    from ..updater import (
        UpdateError,
        check_for_updates,
        perform_update,
        get_update_command,
    )
    
    click.echo()
    click.echo(click.style("🔍 Checking for updates...", fg="cyan"))
    click.echo()
    
    try:
        info = check_for_updates()
    except UpdateError as e:
        click.echo(click.style(f"❌ Failed to check: {e}", fg="red"))
        click.echo()
        click.pause("Press any key to continue...")
        return
    
    click.echo(f"   Current version: {info.current_version}")
    click.echo(f"   Latest version:  {info.latest_version}")
    click.echo()
    
    if info.is_latest:
        click.echo(click.style("✅ You are running the latest version!", fg="green"))
    else:
        click.echo(click.style("🆕 A new version is available!", fg="yellow"))
        if info.release_url:
            click.echo(f"   Release: {info.release_url}")
        click.echo()
        
        if click.confirm("Do you want to install the update?", default=True):
            click.echo()
            try:
                if perform_update():
                    click.echo()
                    click.echo(click.style("✅ Update completed!", fg="green"))
                    click.echo("   Please restart the application.")
                else:
                    click.echo(click.style("❌ Update failed.", fg="red"))
            except UpdateError as e:
                click.echo(click.style(f"❌ Update failed: {e}", fg="red"))
                click.echo(f"   Manual update: {get_update_command()}")
    
    click.echo()
    click.pause("Press any key to continue...")


def run_menu() -> None:
    """Run the interactive menu loop."""
    while True:
        clear_screen()
        print_header()
        print_status_summary()
        print_menu_options()
        
        try:
            choice = click.prompt("Select option", type=int, default=7)
        except click.Abort:
            break
        
        if choice == 1:
            handle_sync()
        elif choice == 2:
            handle_status()
        elif choice == 3:
            handle_schedule()
        elif choice == 4:
            handle_setup()
        elif choice == 5:
            handle_logs()
        elif choice == 6:
            handle_update()
        elif choice == 7:
            click.echo()
            click.echo("Goodbye! 👋")
            break
        else:
            click.echo("Invalid option, please try again.")
            click.pause()
