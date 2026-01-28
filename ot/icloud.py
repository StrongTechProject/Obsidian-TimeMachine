"""
iCloud synchronization wait utilities.

Provides functions to wait for iCloud to finish syncing files before
performing backup operations.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from pathlib import Path

from .logger import get_logger


def find_icloud_placeholders(directory: Path) -> list[Path]:
    """Find iCloud placeholder files (.icloud files).
    
    These files indicate that the actual content hasn't been downloaded
    from iCloud yet.
    
    Args:
        directory: Directory to search.
        
    Returns:
        List of paths to .icloud placeholder files.
    """
    directory = Path(directory).expanduser().resolve()
    
    if not directory.exists():
        return []
    
    return list(directory.rglob("*.icloud"))


def find_recently_modified_files(
    directory: Path,
    seconds: int = 5,
    exclude_patterns: list[str] | None = None,
) -> list[Path]:
    """Find files modified within the last N seconds.
    
    Args:
        directory: Directory to search.
        seconds: Time window in seconds.
        exclude_patterns: Patterns to exclude (e.g., [".icloud", ".DS_Store"]).
        
    Returns:
        List of recently modified file paths.
    """
    directory = Path(directory).expanduser().resolve()
    exclude_patterns = exclude_patterns or [".icloud", ".DS_Store"]
    
    if not directory.exists():
        return []
    
    cutoff_time = datetime.now() - timedelta(seconds=seconds)
    recent_files: list[Path] = []
    
    try:
        for file_path in directory.rglob("*"):
            if not file_path.is_file():
                continue
            
            # Check exclusion patterns
            if any(pattern in file_path.name for pattern in exclude_patterns):
                continue
            
            try:
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                if mtime > cutoff_time:
                    recent_files.append(file_path)
            except OSError:
                # Skip files we can't stat
                continue
    except OSError:
        # Directory access error
        pass
    
    return recent_files


def wait_for_icloud_sync(
    source_dir: Path,
    max_wait_seconds: int = 60,
    check_interval: float = 2.0,
    stability_threshold: int = 2,
) -> bool:
    """Wait for iCloud to finish syncing files.
    
    This function checks for two conditions:
    1. No .icloud placeholder files (all files downloaded)
    2. No recently modified files (sync activity has stopped)
    
    Args:
        source_dir: Source directory to monitor.
        max_wait_seconds: Maximum time to wait in seconds.
        check_interval: Time between checks in seconds.
        stability_threshold: Number of consecutive stable checks required.
        
    Returns:
        True if sync completed within timeout, False if timed out.
    """
    logger = get_logger()
    source_dir = Path(source_dir).expanduser().resolve()
    
    logger.info("⏳ Checking iCloud sync status...")
    
    start_time = time.time()
    stable_count = 0
    
    while True:
        elapsed = time.time() - start_time
        
        if elapsed >= max_wait_seconds:
            logger.warning(
                f"⚠️ Timeout after {max_wait_seconds}s waiting for iCloud sync. "
                "Proceeding anyway."
            )
            return False
        
        # Check for .icloud placeholder files
        placeholders = find_icloud_placeholders(source_dir)
        if placeholders:
            logger.info(
                f"   Waiting for iCloud downloads... "
                f"({len(placeholders)} files pending, {elapsed:.0f}s elapsed)"
            )
            stable_count = 0
            time.sleep(check_interval)
            continue
        
        # Check for recently modified files
        recent_files = find_recently_modified_files(source_dir, seconds=5)
        if recent_files:
            logger.info(
                f"   Waiting for file stability... "
                f"({len(recent_files)} files recently modified)"
            )
            stable_count = 0
            time.sleep(check_interval)
            continue
        
        # No pending files and no recent modifications
        stable_count += 1
        
        if stable_count >= stability_threshold:
            logger.info("✅ iCloud sync appears complete. Files are stable.")
            
            # Extra safety delay for file system to settle
            time.sleep(1)
            return True
        
        time.sleep(check_interval)
    
    return False
