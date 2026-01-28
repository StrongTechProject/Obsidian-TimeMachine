"""
Interactive configuration wizard for Obsidian Timemachine.

Provides a guided setup experience for first-time configuration.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from ..config import (
    Config,
    DEFAULT_CONFIG_FILE,
    DEFAULT_LOG_DIR,
    DEFAULT_LOG_RETENTION_DAYS,
    save_config,
    validate_config,
)
from ..git_ops import (
    get_current_branch,
    get_remote_url,
    init_repo,
    is_git_repo,
    set_remote_url,
)
from ..ssh import find_ssh_keys, generate_ssh_key, SSHKey


def print_header(text: str) -> None:
    """Print a section header."""
    click.echo()
    click.echo(click.style("─" * 50, fg="blue"))
    click.echo(click.style(f"  {text}", fg="blue", bold=True))
    click.echo(click.style("─" * 50, fg="blue"))


def print_success(text: str) -> None:
    """Print a success message."""
    click.echo(click.style(f"✅ {text}", fg="green"))


def print_warning(text: str) -> None:
    """Print a warning message."""
    click.echo(click.style(f"⚠️  {text}", fg="yellow"))


def print_error(text: str) -> None:
    """Print an error message."""
    click.echo(click.style(f"❌ {text}", fg="red"))


def prompt_path(
    message: str,
    default: Path | None = None,
    must_exist: bool = True,
    create_if_missing: bool = False,
) -> Path:
    """Prompt for a path with validation.
    
    Args:
        message: Prompt message.
        default: Default value.
        must_exist: Whether path must exist.
        create_if_missing: Whether to create path if missing.
        
    Returns:
        Validated Path object.
    """
    while True:
        default_str = str(default) if default else None
        value = click.prompt(
            message,
            default=default_str,
            type=str,
        )
        
        # Handle drag-and-drop quoted paths
        value = value.strip().strip('"').strip("'")
        
        # Expand user and resolve
        path = Path(value).expanduser().resolve()
        
        if must_exist and not path.exists():
            if create_if_missing:
                if click.confirm(f"Directory {path} does not exist. Create it?"):
                    try:
                        path.mkdir(parents=True, exist_ok=True)
                        print_success(f"Created directory: {path}")
                        return path
                    except OSError as e:
                        print_error(f"Failed to create directory: {e}")
                        continue
            else:
                print_error(f"Path does not exist: {path}")
                continue
        
        if path.exists() and not path.is_dir():
            print_error("Path is not a directory")
            continue
        
        return path


def setup_source_directory() -> Path:
    """Configure the source (Obsidian vault) directory."""
    print_header("Step 1: Obsidian Vault Location")
    
    click.echo("Enter the path to your Obsidian vault.")
    click.echo("(Tip: You can drag the folder into this terminal window)")
    click.echo()
    
    # Try to detect common Obsidian locations
    common_locations = [
        Path.home() / "Library" / "Mobile Documents" / "iCloud~md~obsidian" / "Documents",
        Path.home() / "Documents" / "Obsidian",
        Path.home() / "Obsidian",
    ]
    
    for loc in common_locations:
        if loc.exists():
            click.echo(f"💡 Found potential vault location: {loc}")
    
    click.echo()
    
    return prompt_path("Obsidian vault path", must_exist=True)


def setup_dest_directory() -> Path:
    """Configure the destination (Git repository) directory."""
    print_header("Step 2: Git Repository Location")
    
    click.echo("Enter the path for the Git repository (backup destination).")
    click.echo("This can be:")
    click.echo("  - Same as source (Direct Mode: Git manages vault directly)")
    click.echo("  - Different path (Mirror Mode: rsync to separate Git repo)")
    click.echo()
    
    dest = prompt_path(
        "Git repository path",
        must_exist=False,
        create_if_missing=True,
    )
    
    # Check if it's a Git repo, offer to initialize
    if not is_git_repo(dest):
        print_warning("This directory is not a Git repository.")
        if click.confirm("Initialize as a Git repository?", default=True):
            result = init_repo(dest)
            if result.success:
                print_success("Git repository initialized.")
            else:
                print_error(f"Failed to initialize: {result.error}")
    else:
        print_success("Git repository detected.")
        
        # Show current remote
        remote = get_remote_url(dest)
        if remote:
            click.echo(f"   Remote: {remote}")
        else:
            print_warning("No remote 'origin' configured.")
    
    # Configure remote if needed
    if is_git_repo(dest) and not get_remote_url(dest):
        click.echo()
        click.echo("Configure a remote repository (e.g., GitHub)?")
        if click.confirm("Add remote origin?", default=True):
            remote_url = click.prompt(
                "Remote URL (e.g., git@github.com:user/repo.git)",
                type=str,
            )
            result = set_remote_url(dest, remote_url)
            if result.success:
                print_success(f"Remote configured: {remote_url}")
            else:
                print_error(f"Failed to set remote: {result.error}")
    
    return dest


def setup_ssh_key() -> Path | None:
    """Configure SSH key for Git authentication."""
    print_header("Step 3: SSH Key Configuration")
    
    click.echo("An SSH key is needed for pushing to GitHub/GitLab.")
    click.echo()
    
    # Find existing keys
    existing_keys = find_ssh_keys()
    
    if existing_keys:
        click.echo("Found existing SSH keys:")
        for i, key in enumerate(existing_keys, 1):
            key_type = key.key_type or "unknown"
            click.echo(f"  {i}. {key.private_key_path} ({key_type})")
        
        click.echo(f"  {len(existing_keys) + 1}. Enter another path")
        click.echo(f"  {len(existing_keys) + 2}. Generate a new key")
        click.echo()
        
        choice = click.prompt(
            "Select an option",
            type=int,
            default=1,
        )
        
        if 1 <= choice <= len(existing_keys):
            selected = existing_keys[choice - 1]
            print_success(f"Using: {selected.private_key_path}")
            return selected.private_key_path
        
        elif choice == len(existing_keys) + 1:
            path_str = click.prompt("Enter SSH key path", type=str)
            path = Path(path_str).expanduser().resolve()
            if path.exists():
                print_success(f"Using: {path}")
                return path
            else:
                print_error("Key file not found")
                return None
        
        elif choice == len(existing_keys) + 2:
            return _generate_new_key()
    
    else:
        click.echo("No SSH keys found in ~/.ssh")
        if click.confirm("Generate a new SSH key?", default=True):
            return _generate_new_key()
        else:
            path_str = click.prompt(
                "Enter SSH key path (or leave blank to skip)",
                default="",
                type=str,
            )
            if path_str:
                path = Path(path_str).expanduser().resolve()
                if path.exists():
                    return path
    
    return None


def _generate_new_key() -> Path | None:
    """Generate a new SSH key."""
    email = click.prompt("Enter your email (for key comment)", type=str)
    
    key = generate_ssh_key(email)
    
    if key and key.exists:
        print_success(f"SSH key generated: {key.private_key_path}")
        
        # Show public key
        public_content = key.get_public_key_content()
        if public_content:
            click.echo()
            click.echo(click.style("─" * 50, fg="yellow"))
            click.echo(click.style("IMPORTANT: Add this public key to GitHub", fg="yellow", bold=True))
            click.echo(click.style("─" * 50, fg="yellow"))
            click.echo("1. Go to https://github.com/settings/keys")
            click.echo("2. Click 'New SSH key'")
            click.echo("3. Paste the following key:")
            click.echo()
            click.echo(click.style(public_content, fg="cyan"))
            click.echo()
            click.pause("Press any key once you've added the key to GitHub...")
        
        return key.private_key_path
    
    print_error("Failed to generate SSH key")
    return None


def setup_schedule() -> str | None:
    """Configure automatic sync schedule."""
    print_header("Step 4: Auto-Sync Schedule")
    
    click.echo("Set up automatic synchronization?")
    click.echo()
    click.echo("Options:")
    click.echo("  1. Every 15 minutes (recommended)")
    click.echo("  2. Every 30 minutes")
    click.echo("  3. Every hour")
    click.echo("  4. Daily at 2:00 AM")
    click.echo("  5. Skip (manual sync only)")
    click.echo()
    
    choice = click.prompt("Select an option", type=int, default=1)
    
    presets = {
        1: "15min",
        2: "30min",
        3: "hourly",
        4: "daily",
    }
    
    return presets.get(choice)


def run_wizard() -> Config | None:
    """Run the complete setup wizard.
    
    Returns:
        Config object if successful, None otherwise.
    """
    click.echo()
    click.echo(click.style("╔════════════════════════════════════════════════╗", fg="blue"))
    click.echo(click.style("║   Obsidian Timemachine - Setup Wizard         ║", fg="blue"))
    click.echo(click.style("╚════════════════════════════════════════════════╝", fg="blue"))
    click.echo()
    click.echo("This wizard will help you configure automatic backup")
    click.echo("for your Obsidian vault.")
    click.echo()
    
    # Step 1: Source directory
    source_dir = setup_source_directory()
    
    # Step 2: Destination directory
    dest_dir = setup_dest_directory()
    
    # Step 3: SSH key
    ssh_key_path = setup_ssh_key()
    
    # Step 4: Schedule (save for after config)
    schedule = setup_schedule()
    
    # Create config
    config = Config(
        source_dir=source_dir,
        dest_dir=dest_dir,
        log_dir=DEFAULT_LOG_DIR,
        ssh_key_path=ssh_key_path,
        log_retention_days=DEFAULT_LOG_RETENTION_DAYS,
    )
    
    # Validate
    errors = validate_config(config)
    if errors:
        print_header("Configuration Issues")
        for error in errors:
            print_error(error)
        if not click.confirm("Save configuration anyway?"):
            return None
    
    # Save config
    print_header("Saving Configuration")
    
    config_path = DEFAULT_CONFIG_FILE
    try:
        save_config(config, config_path)
        print_success(f"Configuration saved to: {config_path}")
    except Exception as e:
        print_error(f"Failed to save config: {e}")
        return None
    
    # Set up schedule if requested
    if schedule:
        from ..scheduler import add_sync_schedule
        
        if add_sync_schedule(schedule):
            print_success(f"Auto-sync scheduled: {schedule}")
        else:
            print_warning("Failed to set up auto-sync schedule")
    
    # Summary
    print_header("Setup Complete!")
    
    click.echo("Your configuration:")
    click.echo(f"  Source:      {config.source_dir}")
    click.echo(f"  Destination: {config.dest_dir}")
    click.echo(f"  SSH Key:     {config.ssh_key_path or 'Not configured'}")
    click.echo(f"  Schedule:    {schedule or 'Manual only'}")
    click.echo()
    click.echo("Run 'ot sync' to start your first backup!")
    click.echo()
    
    return config
