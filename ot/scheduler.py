"""
Cron scheduler management for Obsidian Timemachine.

Provides functions for managing cron jobs to automate sync.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .logger import get_logger


# Common schedule presets
SCHEDULE_PRESETS = {
    "15min": "*/15 * * * *",
    "30min": "*/30 * * * *",
    "hourly": "0 * * * *",
    "daily": "0 2 * * *",
    "daily_morning": "0 9 * * *",
    "daily_evening": "0 22 * * *",
}


@dataclass
class CronJob:
    """Represents a cron job entry.
    
    Attributes:
        schedule: Cron schedule expression.
        command: Command to execute.
        comment: Optional comment/identifier.
    """
    schedule: str
    command: str
    comment: str | None = None
    
    def to_cron_line(self) -> str:
        """Convert to cron entry line."""
        if self.comment:
            return f"{self.schedule} {self.command} # {self.comment}"
        return f"{self.schedule} {self.command}"
    
    @classmethod
    def from_cron_line(cls, line: str) -> "CronJob | None":
        """Parse a cron line into a CronJob object."""
        line = line.strip()
        if not line or line.startswith("#"):
            return None
        
        # Extract comment if present
        comment = None
        if "#" in line:
            line, comment = line.rsplit("#", 1)
            line = line.strip()
            comment = comment.strip()
        
        # Parse schedule and command
        parts = line.split(None, 5)
        if len(parts) < 6:
            return None
        
        schedule = " ".join(parts[:5])
        command = parts[5]
        
        return cls(schedule=schedule, command=command, comment=comment)


def get_current_crontab() -> str:
    """Get the current user's crontab contents.
    
    Returns:
        Crontab contents as string, empty string if none.
    """
    try:
        result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        if result.returncode == 0:
            return result.stdout
        
        # No crontab is not an error
        if "no crontab" in result.stderr.lower():
            return ""
        
        return ""
    except (subprocess.SubprocessError, OSError):
        return ""


def set_crontab(content: str) -> bool:
    """Set the user's crontab contents.
    
    Args:
        content: New crontab contents.
        
    Returns:
        True if successful.
    """
    logger = get_logger()
    
    try:
        result = subprocess.run(
            ["crontab", "-"],
            input=content,
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        if result.returncode == 0:
            return True
        
        logger.error(f"❌ Failed to set crontab: {result.stderr}")
        return False
    except subprocess.SubprocessError as e:
        logger.error(f"❌ Failed to set crontab: {e}")
        return False


def find_ot_cron_jobs() -> list[CronJob]:
    """Find existing OT sync cron jobs.
    
    Returns:
        List of CronJob objects for OT.
    """
    crontab = get_current_crontab()
    jobs: list[CronJob] = []
    
    for line in crontab.splitlines():
        # Look for lines containing 'ot sync' or 'ot-sync'
        if "ot sync" in line.lower() or "ot-sync" in line.lower():
            job = CronJob.from_cron_line(line)
            if job:
                jobs.append(job)
    
    return jobs


def get_ot_command() -> str:
    """Get the full path to the ot command.
    
    Returns:
        Path to ot command.
    """
    # Try to find ot in PATH
    try:
        result = subprocess.run(
            ["which", "ot"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except subprocess.SubprocessError:
        pass
    
    # Fallback to sys.executable based path
    return f"{sys.executable} -m ot.cli.main"


def add_sync_schedule(
    schedule: str,
    config_path: Path | None = None,
) -> bool:
    """Add a cron job for sync.
    
    Args:
        schedule: Cron schedule expression or preset name.
        config_path: Optional config file path.
        
    Returns:
        True if successful.
    """
    logger = get_logger()
    
    # Resolve schedule preset
    if schedule in SCHEDULE_PRESETS:
        cron_schedule = SCHEDULE_PRESETS[schedule]
    else:
        cron_schedule = schedule
    
    # Validate cron expression (basic check)
    parts = cron_schedule.split()
    if len(parts) != 5:
        logger.error(f"❌ Invalid cron schedule: {cron_schedule}")
        return False
    
    # Build command
    ot_cmd = get_ot_command()
    command = f"{ot_cmd} sync"
    if config_path:
        command += f" --config {config_path}"
    
    # Remove existing OT jobs
    crontab = get_current_crontab()
    new_lines = []
    
    for line in crontab.splitlines():
        # Skip existing OT sync jobs
        if "ot sync" in line.lower() or "ot-sync" in line.lower():
            continue
        new_lines.append(line)
    
    # Add new job
    new_job = CronJob(
        schedule=cron_schedule,
        command=command,
        comment="Obsidian Timemachine auto-sync",
    )
    new_lines.append(new_job.to_cron_line())
    
    # Ensure trailing newline
    new_crontab = "\n".join(new_lines)
    if not new_crontab.endswith("\n"):
        new_crontab += "\n"
    
    if set_crontab(new_crontab):
        logger.info(f"✅ Cron job added: {cron_schedule}")
        return True
    
    return False


def remove_sync_schedule() -> bool:
    """Remove all OT sync cron jobs.
    
    Returns:
        True if successful.
    """
    logger = get_logger()
    
    crontab = get_current_crontab()
    new_lines = []
    removed_count = 0
    
    for line in crontab.splitlines():
        if "ot sync" in line.lower() or "ot-sync" in line.lower():
            removed_count += 1
            continue
        new_lines.append(line)
    
    if removed_count == 0:
        logger.info("No OT sync jobs found in crontab.")
        return True
    
    new_crontab = "\n".join(new_lines)
    if new_crontab and not new_crontab.endswith("\n"):
        new_crontab += "\n"
    
    if set_crontab(new_crontab):
        logger.info(f"✅ Removed {removed_count} OT sync job(s)")
        return True
    
    return False


def get_current_schedule() -> str | None:
    """Get the current OT sync schedule.
    
    Returns:
        Cron schedule expression or None if not scheduled.
    """
    jobs = find_ot_cron_jobs()
    if jobs:
        return jobs[0].schedule
    return None


def describe_schedule(schedule: str) -> str:
    """Get a human-readable description of a cron schedule.
    
    Args:
        schedule: Cron schedule expression.
        
    Returns:
        Human-readable description.
    """
    # Check presets first
    for name, expr in SCHEDULE_PRESETS.items():
        if schedule == expr:
            descriptions = {
                "15min": "Every 15 minutes",
                "30min": "Every 30 minutes",
                "hourly": "Every hour",
                "daily": "Daily at 2:00 AM",
                "daily_morning": "Daily at 9:00 AM",
                "daily_evening": "Daily at 10:00 PM",
            }
            return descriptions.get(name, name)
    
    # Parse cron expression
    try:
        parts = schedule.split()
        if len(parts) != 5:
            return schedule
        
        minute, hour, dom, month, dow = parts
        
        if minute.startswith("*/"):
            interval = minute[2:]
            return f"Every {interval} minutes"
        
        if minute == "0" and hour == "*":
            return "Every hour"
        
        if minute == "0" and hour.isdigit():
            h = int(hour)
            period = "AM" if h < 12 else "PM"
            h12 = h if h <= 12 else h - 12
            if h12 == 0:
                h12 = 12
            return f"Daily at {h12}:00 {period}"
        
        return schedule
    except Exception:
        return schedule
