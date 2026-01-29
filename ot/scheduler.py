"""
Scheduler management for Obsidian Timemachine.

Unified interface for managing background sync tasks.
Supports:
- macOS: LaunchAgents (native, reliable wake-up)
- Linux/Other: Cron (standard)
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .logger import get_logger

# Import OS-specific handler
if sys.platform == "darwin":
    from . import launchd_ops

# Common schedule presets
SCHEDULE_PRESETS = {
    "15min": "*/15 * * * *",
    "30min": "*/30 * * * *",
    "hourly": "0 * * * *",
    "daily": "0 2 * * *",
    "daily_morning": "0 9 * * *",
    "daily_evening": "0 22 * * *",
}

# Launchd preset mappings (Label suffix, Interval/Calendar)
LAUNCHD_LABEL = "com.user.ot.sync"
LAUNCHD_PRESETS = {
    "15min": {"schedule_interval": 900},
    "30min": {"schedule_interval": 1800},
    "hourly": {"schedule_interval": 3600},
    "daily": {"calendar_interval": {"Hour": 2, "Minute": 0}},
    "daily_morning": {"calendar_interval": {"Hour": 9, "Minute": 0}},
    "daily_evening": {"calendar_interval": {"Hour": 22, "Minute": 0}},
}


# ============================================================================
# Shared / Legacy Interface
# ============================================================================

def add_sync_schedule(schedule: str, config_path: Path | None = None) -> bool:
    """Add a sync schedule (Cross-platform)."""
    
    if sys.platform == "darwin":
        return _add_launchd_schedule(schedule, config_path)
    else:
        return _add_cron_schedule(schedule, config_path)


def remove_sync_schedule() -> bool:
    """Remove sync schedule (Cross-platform)."""
    if sys.platform == "darwin":
        # Also clean legacy cron jobs just in case
        _remove_cron_schedule()
        return launchd_ops.remove_agent(LAUNCHD_LABEL)
    else:
        return _remove_cron_schedule()


def get_current_schedule() -> str | None:
    """Get current schedule (Cross-platform)."""
    if sys.platform == "darwin":
        # Retrieve from plist checks
        info = launchd_ops.get_agent_schedule_info(LAUNCHD_LABEL)
        if info is None:
            return None
        
        # Try to reverse-engineer the preset name
        frequency = get_schedule_frequency_name(info)
        if frequency:
            return frequency
        return "custom"
    else:
        jobs = find_ot_cron_jobs()
        if jobs:
            return jobs[0].schedule
        return None


def get_schedule_frequency_name(info: dict) -> str | None:
    """Convert schedule info to a frequency name.
    
    Args:
        info: Dictionary with schedule_interval or calendar_interval.
        
    Returns:
        Frequency name like '15min', 'hourly', etc. or None if unknown.
    """
    if "schedule_interval" in info:
        interval = info["schedule_interval"]
        interval_map = {
            900: "15min",
            1800: "30min",
            3600: "hourly",
        }
        return interval_map.get(interval)
    
    if "calendar_interval" in info:
        cal = info["calendar_interval"]
        hour = cal.get("Hour")
        minute = cal.get("Minute", 0)
        
        if hour == 2 and minute == 0:
            return "daily"
        elif hour == 9 and minute == 0:
            return "daily_morning"
        elif hour == 22 and minute == 0:
            return "daily_evening"
        # Return a formatted string for other times
        return f"daily_{hour:02d}:{minute:02d}"
    
    return None


def describe_schedule(schedule: str) -> str:
    """Describe schedule human-readably."""
    # Standard preset names (returned by get_schedule_frequency_name)
    descriptions = {
        "15min": "Every 15 minutes",
        "30min": "Every 30 minutes",
        "hourly": "Every hour",
        "daily": "Daily at 2:00 AM",
        "daily_morning": "Daily at 9:00 AM",
        "daily_evening": "Daily at 10:00 PM",
        "custom": "Custom schedule",
    }
    
    # Generate base description
    description = schedule
    if schedule in descriptions:
        description = descriptions[schedule]
    elif schedule.startswith("daily_") and ":" in schedule:
        time_part = schedule.replace("daily_", "")
        description = f"Daily at {time_part}"
    
    # Legacy "Enabled (macOS Native)" string
    if schedule == "Enabled (macOS Native)":
        return "Active (MacOS Native Scheduler)"
    
    # Append scheduler type for clarity on macOS
    if sys.platform == "darwin" and "MacOS Native" not in description:
        description += " (MacOS Native Scheduler)"
            
    return description


# ============================================================================
# MacOS Launchd Impl
# ============================================================================

def _add_launchd_schedule(schedule: str, config_path: Path | None = None) -> bool:
    """Add macOS LaunchAgent."""
    logger = get_logger()
    
    # 1. Map schedule string to config
    launch_config = {}
    
    if schedule in LAUNCHD_PRESETS:
        launch_config = LAUNCHD_PRESETS[schedule]
    else:
        # Fallback/Error for custom cron expressions not supported in basic launchd mapping yet
        logger.error("❌ MacOS currently only supports presets: 15min, 30min, hourly, daily")
        return False
        
    # 2. Build Command
    # Must use absolute path to python/ot
    ot_cmd_list = _get_ot_command_list()
    if not ot_cmd_list:
        logger.error("❌ Could not determine command for LaunchAgent")
        return False
        
    cmd_args = ot_cmd_list + ["sync"]
    if config_path:
        cmd_args.extend(["--config", str(config_path)])
        
    # 3. Create Plist
    # Clean legacy cron first
    _remove_cron_schedule()
    
    content = launchd_ops.create_plist_content(
        label=LAUNCHD_LABEL,
        program_args=cmd_args,
        schedule_interval=launch_config.get("schedule_interval"),
        calendar_interval=launch_config.get("calendar_interval"),
        stdout_path="/tmp/ot_sync.out.log", # Optional: redirect for debug
        stderr_path="/tmp/ot_sync.err.log"
    )
    
    return launchd_ops.install_agent(LAUNCHD_LABEL, content)


def _get_ot_command_list() -> list[str]:
    """Get command as list for exec."""
    # Preferred: direct executable
    # But for python module, we want [python_exe, "-m", "ot.cli.main"]
    return [sys.executable, "-m", "ot.cli.main"]


# ============================================================================
# Legacy / Linux Cron Impl (Keep existing logic private)
# ============================================================================

@dataclass
class CronJob:
    """Represents a cron job entry."""
    schedule: str
    command: str
    comment: str | None = None
    
    def to_cron_line(self) -> str:
        if self.comment:
            return f"{self.schedule} {self.command} # {self.comment}"
        return f"{self.schedule} {self.command}"
    
    @classmethod
    def from_cron_line(cls, line: str) -> "CronJob | None":
        line = line.strip()
        if not line or line.startswith("#"):
            return None
        comment = None
        if "#" in line:
            line, comment = line.rsplit("#", 1)
            line = line.strip()
            comment = comment.strip()
        parts = line.split(None, 5)
        if len(parts) < 6:
            return None
        return cls(schedule=" ".join(parts[:5]), command=parts[5], comment=comment)


def _get_current_crontab() -> str:
    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0: return result.stdout
        return ""
    except Exception: return ""

def _set_crontab(content: str) -> bool:
    try:
        subprocess.run(["crontab", "-"], input=content, capture_output=True, text=True, timeout=10)
        return True
    except Exception: return False

def find_ot_cron_jobs() -> list[CronJob]:
    crontab = _get_current_crontab()
    jobs = []
    for line in crontab.splitlines():
        if "ot sync" in line.lower() or "ot-sync" in line.lower():
            job = CronJob.from_cron_line(line)
            if job: jobs.append(job)
    return jobs

def _add_cron_schedule(schedule: str, config_path: Path | None) -> bool:
    # (Simplified from original)
    logger = get_logger()
    cron_schedule = SCHEDULE_PRESETS.get(schedule, schedule)
    
    # Simple validation
    if len(cron_schedule.split()) != 5: return False
    
    ot_cmd = f"{sys.executable} -m ot.cli.main"
    command = f"{ot_cmd} sync"
    if config_path: command += f" --config {config_path}"
    
    crontab = _get_current_crontab()
    new_lines = [line for line in crontab.splitlines() 
                 if "ot sync" not in line.lower() and "ot-sync" not in line.lower()]
    
    job = CronJob(schedule=cron_schedule, command=command, comment="Obsidian Timemachine auto-sync")
    new_lines.append(job.to_cron_line())
    return _set_crontab("\n".join(new_lines) + "\n")

def _remove_cron_schedule() -> bool:
    crontab = _get_current_crontab()
    new_lines = [line for line in crontab.splitlines() 
                 if "ot sync" not in line.lower() and "ot-sync" not in line.lower()]
    return _set_crontab("\n".join(new_lines) + "\n")
