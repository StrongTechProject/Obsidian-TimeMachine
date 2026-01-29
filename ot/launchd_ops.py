"""
MacOS Launchd (LaunchAgents) management for Obsidian Timemachine.

Provides functionality to schedule background tasks using the native macOS launchd system,
which offers better reliability (e.g., wake-from-sleep catch-up) compared to cron.
"""

from __future__ import annotations

import os
import plistlib
import subprocess
from pathlib import Path
from typing import Any

from .logger import get_logger

# Standard user LaunchAgents directory
LAUNCH_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"
DOMAIN_TARGET = f"gui/{os.getuid()}"


def _get_plist_path(label: str) -> Path:
    """Get the path to the plist file for a given label."""
    return LAUNCH_AGENTS_DIR / f"{label}.plist"


def create_plist_content(
    label: str,
    program_args: list[str],
    schedule_interval: int | None = None,
    calendar_interval: dict[str, int] | None = None,
    stdout_path: str | None = None,
    stderr_path: str | None = None,
) -> bytes:
    """Generate the content of a LaunchAgent plist file.

    Args:
        label: Unique identifier for the job (e.g., com.user.ot.sync).
        program_args: List of command arguments to execute.
        schedule_interval: Interval in seconds (StartInterval).
        calendar_interval: Dictionary for specific times (StartCalendarInterval).
        stdout_path: Path to redirect stdout.
        stderr_path: Path to redirect stderr.

    Returns:
        XML plist content as bytes.
    """
    plist: dict[str, Any] = {
        "Label": label,
        "ProgramArguments": program_args,
        "RunAtLoad": True,  # potential catch-up trigger if load happens?
        # Note: "RunAtLoad" runs it immediately upon loading/login.
        # "KeepAlive": False is default.
    }

    # Interval scheduling (Repeat every X seconds)
    if schedule_interval is not None:
        plist["StartInterval"] = schedule_interval

    # Calendar scheduling (Specific time, e.g., Daily at 2am)
    if calendar_interval is not None:
        plist["StartCalendarInterval"] = calendar_interval

    if stdout_path:
        plist["StandardOutPath"] = stdout_path
    if stderr_path:
        plist["StandardErrorPath"] = stderr_path

    return plistlib.dumps(plist)


def install_agent(
    label: str,
    plist_content: bytes,
    plist_path: Path | None = None,
) -> bool:
    """Install and load a LaunchAgent.

    Args:
        label: Job label.
        plist_content: The content of the plist file.
        plist_path: Optional path to write to (defaults to ~/Library/LaunchAgents/label.plist).

    Returns:
        True if successful.
    """
    logger = get_logger()
    
    if plist_path is None:
        plist_path = _get_plist_path(label)
    
    # ensure directory exists
    if not plist_path.parent.exists():
        try:
            plist_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error(f"❌ Failed to create LaunchAgents directory: {e}")
            return False

    # write plist file
    try:
        plist_path.write_bytes(plist_content)
    except OSError as e:
        logger.error(f"❌ Failed to write plist file: {e}")
        return False

    # Load the service
    # We use 'bootstrap' for modern macOS, falling back to 'load' is usually not needed for 10.10+
    # syntax: launchctl bootstrap gui/<uid> <path>
    cmd = ["launchctl", "bootstrap", DOMAIN_TARGET, str(plist_path)]
    
    # First, try to bootout just in case it's already there (ignore errors)
    subprocess.run(
        ["launchctl", "bootout", DOMAIN_TARGET, str(plist_path)],
        capture_output=True,
    )

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            logger.info(f"✅ Successfully installed LaunchAgent: {label}")
            return True
        else:
            # Fallback to legacy 'load' if bootstrap fails (rare)
            logger.warning(f"Bootstrap failed ({result.stderr}), trying load...")
            legacy_result = subprocess.run(
                ["launchctl", "load", "-w", str(plist_path)],
                capture_output=True,
                text=True,
            )
            if legacy_result.returncode == 0:
                logger.info(f"✅ Successfully loaded LaunchAgent (legacy): {label}")
                return True
            
            logger.error(f"❌ Failed to load LaunchAgent: {result.stderr}")
            return False
            
    except subprocess.SubprocessError as e:
        logger.error(f"❌ Failed to execute launchctl: {e}")
        return False


def remove_agent(label: str) -> bool:
    """Unload and remove a LaunchAgent.
    
    Args:
        label: Job label.
        
    Returns:
        True if successful.
    """
    logger = get_logger()
    plist_path = _get_plist_path(label)
    
    if not plist_path.exists():
        return True

    # Unload
    subprocess.run(
        ["launchctl", "bootout", DOMAIN_TARGET, str(plist_path)],
        capture_output=True,
    )
    
    # Also try legacy unload just in case
    subprocess.run(
        ["launchctl", "unload", "-w", str(plist_path)],
        capture_output=True,
    )

    # Delete file
    try:
        plist_path.unlink()
        logger.info(f"✅ Removed LaunchAgent: {label}")
        return True
    except OSError as e:
        logger.error(f"❌ Failed to delete plist file: {e}")
        return False


def get_agent_schedule_info(label: str) -> dict[str, Any] | None:
    """Read the plist file and return schedule information.
    
    Args:
        label: Job label.
        
    Returns:
        Dictionary with schedule info, or None if not found.
        Keys may include:
        - schedule_interval: Interval in seconds
        - calendar_interval: Dictionary for specific times
        - exists: True if the plist exists
    """
    plist_path = _get_plist_path(label)
    
    if not plist_path.exists():
        return None
    
    try:
        with open(plist_path, "rb") as f:
            plist_data = plistlib.load(f)
        
        result: dict[str, Any] = {"exists": True}
        
        if "StartInterval" in plist_data:
            result["schedule_interval"] = plist_data["StartInterval"]
        
        if "StartCalendarInterval" in plist_data:
            result["calendar_interval"] = plist_data["StartCalendarInterval"]
        
        return result
    except (OSError, plistlib.InvalidFileException):
        return None
